from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List


def _pretty_path(path_str: str) -> str:
    if not path_str:
        return ""
    try:
        return Path(path_str).name
    except Exception:
        return path_str


def run_bandit(project_dir: str) -> Dict[str, Any]:
    """
    Run Bandit recursively on project_dir and return parsed JSON.
    Non-zero exit is OK (issues found).
    """
    project_path = Path(project_dir).resolve()

    cmd = [
        "python",
        "-m",
        "bandit",
        "-r",
        str(project_path),
        "-f",
        "json",
        "-q",
    ]

    proc = subprocess.run(
        cmd,
        cwd=str(project_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()

    if not stdout:
        return {"ok": False, "error": f"Bandit produced no JSON. stderr: {stderr[:2000]}", "issues": []}

    try:
        raw = json.loads(stdout)
    except Exception:
        return {"ok": False, "error": f"Failed parsing Bandit JSON. stderr: {stderr[:2000]}", "issues": []}

    issues: List[Dict[str, Any]] = []
    for r in raw.get("results", []) or []:
        issues.append(
            {
                "tool": "bandit",
                "test_id": r.get("test_id", "B000"),
                "test_name": r.get("test_name", "bandit.issue"),
                "severity": (r.get("issue_severity") or "").lower(),  # low/medium/high
                "confidence": (r.get("issue_confidence") or "").lower(),
                "file": r.get("filename", ""),
                "line": r.get("line_number", 0),
                "message": r.get("issue_text", ""),
            }
        )

    return {"ok": True, "error": None if not stderr else stderr[:2000], "issues": issues}


def bandit_to_schema(bandit_result: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Convert Bandit issues into your main response buckets.
    Bandit is security-focused, so findings go into 'security'.
    """
    security: List[Dict[str, Any]] = []
    bugs: List[Dict[str, Any]] = []
    best_practices: List[Dict[str, Any]] = []
    performance: List[Dict[str, Any]] = []

    for it in bandit_result.get("issues", []):
        sev = (it.get("severity") or "low").lower()
        if sev not in ("low", "medium", "high"):
            sev = "low"

        pf = _pretty_path(it.get("file") or "")
        line = it.get("line") or 0
        test_id = it.get("test_id") or "bandit"
        test_name = it.get("test_name") or "issue"

        security.append(
            {
                "title": f"bandit.{test_id}",
                "description": f"{test_name}: {it.get('message')} ({pf}:{line})",
                "severity": sev,
            }
        )

    return {
        "security": security,
        "bugs": bugs,
        "best_practices": best_practices,
        "performance": performance,
    }
