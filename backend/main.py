from typing import Literal, List, Optional
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from analyzers.temp_project import make_temp_project
from analyzers.semgrep_runner import run_semgrep_on_folder, semgrep_results_to_categories
from analyzers.eslint_runner import run_eslint, eslint_to_schema

load_dotenv()

Severity = Literal["low", "medium", "high"]


class ReviewItem(BaseModel):
    title: str
    description: str
    severity: Severity


class ReviewRequest(BaseModel):
    source: Literal["manual", "github"] = "manual"
    language: str = Field(min_length=1)
    content_type: Literal["code", "diff"] = "code"
    content: str


class ReviewResponse(BaseModel):
    # ai_used = automated tools used (Semgrep/ESLint), not LLM
    ai_used: bool = False
    ai_error: Optional[str] = None

    score: int = Field(ge=1, le=10)
    summary: str

    bugs: List[ReviewItem] = []
    security: List[ReviewItem] = []
    performance: List[ReviewItem] = []
    best_practices: List[ReviewItem] = []


app = FastAPI(title="AI Code Reviewer API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/review", response_model=ReviewResponse)
def review(req: ReviewRequest) -> ReviewResponse:
    code = req.content or ""
    if not code.strip():
        return ReviewResponse(
            ai_used=True,
            ai_error=None,
            score=1,
            summary="No code provided. Paste some code to get a review.",
            bugs=[],
            security=[],
            performance=[],
            best_practices=[
                ReviewItem(
                    title="Provide input code",
                    description="Paste a snippet or a diff to review.",
                    severity="low",
                )
            ],
        )

    # Create temp folder with a file so tools can scan it
    temp_dir, folder = make_temp_project(req.language, code)

    try:
        # -------------------------
        # Semgrep
        # -------------------------
        semgrep_json = run_semgrep_on_folder(folder)
        semgrep_cat = semgrep_results_to_categories(semgrep_json)
        semgrep_security = [ReviewItem(**x) for x in semgrep_cat["security"]]
        semgrep_best = [ReviewItem(**x) for x in semgrep_cat["best_practices"]]

        # -------------------------
        # ESLint (best effort)
        # -------------------------
        backend_dir = str(Path(__file__).resolve().parent)
        eslint_error_note: Optional[str] = None

        eslint_security: List[ReviewItem] = []
        eslint_bugs: List[ReviewItem] = []
        eslint_best: List[ReviewItem] = []
        eslint_perf: List[ReviewItem] = []

        try:
            # IMPORTANT: use temp_dir.name (temp project root) to ensure ESLint sees generated files
            eslint_res = run_eslint(project_dir=temp_dir.name, backend_dir=backend_dir)

            if not eslint_res.get("ok", False):
                eslint_error_note = f"eslint_failed: {str(eslint_res.get('error', 'unknown'))[:160]}"
            else:
                eslint_cat = eslint_to_schema(eslint_res)
                eslint_security = [ReviewItem(**x) for x in eslint_cat["security"]]
                eslint_bugs = [ReviewItem(**x) for x in eslint_cat["bugs"]]
                eslint_best = [ReviewItem(**x) for x in eslint_cat["best_practices"]]
                eslint_perf = [ReviewItem(**x) for x in eslint_cat["performance"]]
        except Exception as e:
            eslint_error_note = f"eslint_failed: {str(e)[:160]}"

        # -------------------------
        # Merge categories
        # -------------------------
        security_items = semgrep_security + eslint_security
        bugs_items = eslint_bugs
        best_practices_items = semgrep_best + eslint_best  # ✅ FIX HERE
        performance_items = eslint_perf

        # -------------------------
        # Scoring (realistic + capped)
        # -------------------------
        all_items = security_items + bugs_items + best_practices_items + performance_items

        # Deduplicate by title so we don't double-penalize similar findings
        unique_by_title = {}
        for it in all_items:
            unique_by_title[it.title] = it
        all_items = list(unique_by_title.values())

        def penalty(item: ReviewItem) -> int:
            if item.severity == "high":
                return 2
            if item.severity == "medium":
                return 1
            return 0

        security_pen = sum(penalty(it) for it in security_items)
        bugs_pen = sum(penalty(it) for it in bugs_items)
        perf_pen = sum(penalty(it) for it in performance_items)

        best_pen = sum(penalty(it) for it in best_practices_items)
        best_pen = min(best_pen, 2)

        total_pen = security_pen + bugs_pen + perf_pen + best_pen
        score = 10 - total_pen
        score = max(1, min(10, score))

        # -------------------------
        # Summary
        # -------------------------
        total_issues = len(all_items)
        summary = (
            "No major issues found by automated checks."
            if total_issues == 0
            else "Automated checks found issues. Review before merging."
        )

        ai_error = eslint_error_note

        return ReviewResponse(
            ai_used=True,
            ai_error=ai_error,
            score=score,
            summary=summary,
            bugs=bugs_items,
            security=security_items,
            performance=performance_items,
            best_practices=best_practices_items,
        )

    except Exception as e:
        return ReviewResponse(
            ai_used=False,
            ai_error=f"analysis_failed: {str(e)[:250]}",
            score=5,
            summary="Analysis failed; returned fallback response.",
            bugs=[],
            security=[],
            performance=[],
            best_practices=[
                ReviewItem(
                    title="Analysis failed",
                    description="Could not run automated analysis tools on the provided code.",
                    severity="medium",
                )
            ],
        )
    finally:
        temp_dir.cleanup()
