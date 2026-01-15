import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List
import os


def _semgrep_exe_path() -> str:
    py = Path(sys.executable)
    win = py.parent / "semgrep.exe"
    if win.exists():
        return str(win)
    nix = py.parent / "semgrep"
    if nix.exists():
        return str(nix)
    return "semgrep"


def run_semgrep_on_folder(folder: Path) -> Dict[str, Any]:
    semgrep = _semgrep_exe_path()

    local_rules = Path(__file__).resolve().parents[1] / "rules" / "quick-rules.yml"

    cmd = [
        semgrep,
        "--config",
        str(local_rules),
        "--config",
        "p/ci",
        "--json",
        str(folder),
    ]

    # Force UTF-8 so Semgrep doesn't crash on Windows encoding issues
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

    if not out:
        raise RuntimeError(
            "Semgrep produced no JSON output. "
            f"returncode={proc.returncode} stderr={err[:600]}"
        )

    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise RuntimeError(
            "Semgrep output was not valid JSON. "
            f"returncode={proc.returncode} stderr={err[:600]} stdout_head={out[:200]}"
        )


def _pretty_path(path_str: str) -> str:
    """
    Make the output look professional:
    - If it's a Windows temp path, show only the filename
    - Otherwise, show the original
    """
    if not path_str:
        return ""
    try:
        p = Path(path_str)
        # In your project, temp files are often like ...\\Temp\\tmpxxxx\\main.ts
        # Showing just "main.ts" looks much better
        return p.name
    except Exception:
        return path_str


def _normalize_severity(semgrep_sev: str) -> str:
    s = (semgrep_sev or "").upper()
    if s in ["ERROR", "CRITICAL", "HIGH"]:
        return "high"
    if s in ["WARNING", "MEDIUM"]:
        return "medium"
    return "low"


def semgrep_results_to_categories(data: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
    """
    Convert Semgrep JSON into your response buckets.
    We categorize a few known rules; everything else stays in security by default.
    """
    findings = data.get("results", []) or []

    security: List[Dict[str, str]] = []
    best_practices: List[Dict[str, str]] = []

    for f in findings:
        check_id = f.get("check_id", "semgrep.issue")
        message = (f.get("extra", {}) or {}).get("message", "") or "Semgrep finding"
        severity = _normalize_severity(((f.get("extra", {}) or {}).get("severity", "") or ""))

        path = f.get("path") or ""
        start = ((f.get("start") or {}) or {}).get("line")
        end = ((f.get("end") or {}) or {}).get("line")

        pretty_file = _pretty_path(path)
        where = pretty_file
        if start:
            where += f":{start}"
            if end and end != start:
                where += f"-{end}"

        item = {
            "title": f"{check_id}",
            "description": f"{message} ({where})",
            "severity": severity,
        }

        # Categorization rules:
        # - eval is security
        # - console.log is best practice
        cid = str(check_id).lower()
        if "no-console" in cid or "console-log" in cid:
            best_practices.append(item)
        else:
            security.append(item)

    return {
        "security": security,
        "best_practices": best_practices,
    }
