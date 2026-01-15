from typing import Literal, List
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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
    score: int = Field(ge=1, le=10)
    summary: str
    bugs: List[ReviewItem] = []
    security: List[ReviewItem] = []
    performance: List[ReviewItem] = []
    best_practices: List[ReviewItem] = []


app = FastAPI(title="AI Code Reviewer API", version="0.1.0")

# Allow Angular dev server to call backend during local dev
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
    """
    Phase A: backend mock.
    Next phase: replace heuristics with real AI call.
    """
    code = req.content or ""
    empty = code.strip() == ""

    bugs: List[ReviewItem] = []
    security: List[ReviewItem] = []
    performance: List[ReviewItem] = []
    best_practices: List[ReviewItem] = []

    if empty:
        best_practices.append(
            ReviewItem(
                title="Provide input code",
                description="Paste a snippet or a diff to review.",
                severity="low",
            )
        )
        return ReviewResponse(
            score=1,
            summary="No code provided. Paste some code to get a review.",
            bugs=bugs,
            security=security,
            performance=performance,
            best_practices=best_practices,
        )

    has_eval = "eval(" in code
    has_console = "console.log" in code
    has_any = " any" in code or "\nany" in code or "\tany" in code
    is_large = len(code) > 1200

    if has_eval:
        security.append(
            ReviewItem(
                title="Use of eval()",
                description="Avoid eval() because it can execute untrusted code. Prefer safer parsing/validation.",
                severity="high",
            )
        )

    if has_console:
        best_practices.append(
            ReviewItem(
                title="Debug logging left in code",
                description="Remove console.log or use a logger with levels.",
                severity="low",
            )
        )

    if has_any and req.language.lower() in ["typescript", "ts"]:
        best_practices.append(
            ReviewItem(
                title='TypeScript "any" usage',
                description='Replace "any" with specific types or generics for better safety.',
                severity="medium",
            )
        )

    if is_large:
        performance.append(
            ReviewItem(
                title="Large input detected",
                description="Consider reviewing diffs or smaller sections for better signal and lower cost.",
                severity="low",
            )
        )

    score = 9
    if has_eval:
        score -= 4
    if has_any and req.language.lower() in ["typescript", "ts"]:
        score -= 1
    if has_console:
        score -= 1
    if is_large:
        score -= 1
    score = max(1, min(10, score))

    summary = (
        "Looks solid overall. Minor improvements recommended."
        if score >= 8
        else "Some issues found. Fix these before merging."
        if score >= 5
        else "Several important issues found. Please refactor before merging."
    )

    return ReviewResponse(
        score=score,
        summary=summary,
        bugs=bugs,
        security=security,
        performance=performance,
        best_practices=best_practices,
    )
