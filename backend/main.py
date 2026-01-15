from typing import Literal, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from analyzers.temp_project import make_temp_project
from analyzers.semgrep_runner import run_semgrep_on_folder, semgrep_results_to_review_items

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
    # We keep ai_used to match your frontend style, but now it means "automated tools used"
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

    # Create temp folder with a file so semgrep can scan it
    temp_dir, folder = make_temp_project(req.language, code)

    try:
        semgrep_json = run_semgrep_on_folder(folder)
        semgrep_items = semgrep_results_to_review_items(semgrep_json)

        # Put all Semgrep findings into "security" for now (we can split later)
        security_items = [ReviewItem(**x) for x in semgrep_items]

        # Simple scoring: start at 10 and decrease by issues/severity
        score = 10
        for it in security_items:
            if it.severity == "high":
                score -= 3
            elif it.severity == "medium":
                score -= 2
            else:
                score -= 1
        score = max(1, min(10, score))

        summary = (
            "No major issues found by automated checks."
            if len(security_items) == 0
            else "Automated checks found issues. Review before merging."
        )

        return ReviewResponse(
            ai_used=True,
            ai_error=None,
            score=score,
            summary=summary,
            bugs=[],
            security=security_items,
            performance=[],
            best_practices=[],
        )

    except Exception as e:
        return ReviewResponse(
            ai_used=False,
            ai_error=f"semgrep_failed: {str(e)[:250]}",
            score=5,
            summary="Semgrep analysis failed; returned fallback response.",
            bugs=[],
            security=[],
            performance=[],
            best_practices=[
                ReviewItem(
                    title="Semgrep failed",
                    description="Could not run Semgrep on the provided code.",
                    severity="medium",
                )
            ],
        )
    finally:
        # cleanup temp folder
        temp_dir.cleanup()
