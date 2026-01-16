from __future__ import annotations

import json
from pathlib import Path

from analyzers.semgrep_runner import run_semgrep_on_folder, semgrep_results_to_categories
from analyzers.eslint_runner import run_eslint, eslint_to_schema
from analyzers.bandit_runner import run_bandit, bandit_to_schema


def main() -> int:
    """
    CI entrypoint:
    - Semgrep scans the whole repo
    - Bandit scans the whole repo (Python security)
    - ESLint scans only project JS/TS folders (backend + frontend) to avoid Windows path-length issues
    - Outputs a single JSON summary to stdout
    - Exits non-zero when recommendation == block_merge
    """

    repo_root = Path(__file__).resolve().parents[1]
    backend_dir = Path(__file__).resolve().parent

    target_dir = repo_root
    eslint_targets = [repo_root / "backend", repo_root / "frontend"]

    # -------------------------
    # Semgrep (whole repo)
    # -------------------------
    semgrep_json = run_semgrep_on_folder(target_dir)
    semgrep_cat = semgrep_results_to_categories(semgrep_json)
    semgrep_security = semgrep_cat["security"]
    semgrep_best = semgrep_cat["best_practices"]

    # -------------------------
    # ESLint (best effort, limited targets)
    # -------------------------
    eslint_error = None
    eslint_security, eslint_bugs, eslint_best, eslint_perf = [], [], [], []

    for t in eslint_targets:
        if not t.exists():
            continue

        try:
            eslint_res = run_eslint(project_dir=str(t), backend_dir=str(backend_dir))

            if not eslint_res.get("ok", False):
                eslint_error = str(eslint_res.get("error") or "unknown")[:200]
                break

            eslint_cat = eslint_to_schema(eslint_res)
            eslint_security += eslint_cat["security"]
            eslint_bugs += eslint_cat["bugs"]
            eslint_best += eslint_cat["best_practices"]
            eslint_perf += eslint_cat["performance"]

        except Exception as e:
            eslint_error = str(e)[:200]
            break

    # -------------------------
    # Bandit (best effort, whole repo)
    # -------------------------
    bandit_error = None
    bandit_security = []
    try:
        bandit_res = run_bandit(project_dir=str(target_dir))
        if not bandit_res.get("ok", False):
            bandit_error = str(bandit_res.get("error") or "unknown")[:200]
        else:
            bandit_cat = bandit_to_schema(bandit_res)
            bandit_security = bandit_cat["security"]
    except Exception as e:
        bandit_error = str(e)[:200]

    # -------------------------
    # Merge categories
    # -------------------------
    security_items = semgrep_security + eslint_security + bandit_security
    bugs_items = eslint_bugs
    best_items = semgrep_best + eslint_best
    perf_items = eslint_perf

    # -------------------------
    # Deduplicate by title
    # -------------------------
    def dedupe(items):
        out = {}
        for it in items:
            out[it["title"]] = it
        return list(out.values())

    security_items = dedupe(security_items)
    bugs_items = dedupe(bugs_items)
    best_items = dedupe(best_items)
    perf_items = dedupe(perf_items)

    # -------------------------
    # Scoring (same logic as API)
    # -------------------------
    def penalty(sev: str) -> int:
        if sev == "high":
            return 2
        if sev == "medium":
            return 1
        return 0

    security_pen = sum(penalty(it["severity"]) for it in security_items)
    bugs_pen = sum(penalty(it["severity"]) for it in bugs_items)
    perf_pen = sum(penalty(it["severity"]) for it in perf_items)
    best_pen = min(sum(penalty(it["severity"]) for it in best_items), 2)

    score = max(1, min(10, 10 - (security_pen + bugs_pen + perf_pen + best_pen)))

    # -------------------------
    # Recommendation
    # -------------------------
    has_high_security = any(it["severity"] == "high" for it in security_items)
    if has_high_security:
        recommendation = "block_merge"
    elif score <= 6:
        recommendation = "review_required"
    else:
        recommendation = "ok"

    # -------------------------
    # Notes
    # -------------------------
    notes = []
    if eslint_error:
        notes.append(f"eslint_failed: {eslint_error}")
    if bandit_error:
        notes.append(f"bandit_failed: {bandit_error}")

    # -------------------------
    # Output JSON
    # -------------------------
    has_any = bool(security_items or bugs_items or best_items or perf_items)
    result = {
        "ai_used": True,
        "ai_error": "; ".join(notes) if notes else None,
        "score": score,
        "summary": (
            "Automated checks found issues. Review before merging."
            if has_any
            else "No major issues found by automated checks."
        ),
        "recommendation": recommendation,
        "counts": {
            "security": len(security_items),
            "bugs": len(bugs_items),
            "best_practices": len(best_items),
            "performance": len(perf_items),
        },
        "security": security_items[:50],
        "bugs": bugs_items[:50],
        "best_practices": best_items[:50],
        "performance": perf_items[:50],
    }

    print(json.dumps(result, indent=2))
    return 2 if recommendation == "block_merge" else 0


if __name__ == "__main__":
    raise SystemExit(main())
