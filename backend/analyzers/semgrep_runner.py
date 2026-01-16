from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


def _semgrep_exe_path() -> str:
    """
    Prefer the semgrep executable installed in this Python environment.
    This avoids relying on PATH and avoids deprecated `python -m semgrep`.
    """
    py = Path(sys.executable)
    scripts_dir = py.parent / "Scripts"  # Windows venv/system python
    cand = scripts_dir / "semgrep.exe"
    if cand.exists():
        return str(cand)

    # Sometimes semgrep.exe ends up next to python.exe
    cand2 = py.parent / "semgrep.exe"
    if cand2.exists():
        return str(cand2)

    # Fallback: rely on PATH
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


def semgrep_results_to_categories(data: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
    findings = data.get("results", []) or []

    security: List[Dict[str, str]] = []
    best_practices: List[Dict[str, str]] = []
    bugs: List[Dict[str, str]] = []
    performance: List[Dict[str, str]] = []

    def pretty_path(path_str: str) -> str:
        if not path_str:
            return ""
        try:
            return Path(path_str).name
        except Exception:
            return path_str

    for f in findings:
        check_id = f.get("check_id", "semgrep.issue")
        message = (f.get("extra", {}) or {}).get("message", "") or "Semgrep finding"
        severity = ((f.get("extra", {}) or {}).get("severity", "") or "").upper()

        if severity in ["ERROR", "CRITICAL", "HIGH"]:
            sev = "high"
        elif severity in ["WARNING", "MEDIUM"]:
            sev = "medium"
        else:
            sev = "low"

        path = pretty_path(f.get("path") or "")
        start = ((f.get("start") or {}) or {}).get("line")
        end = ((f.get("end") or {}) or {}).get("line")

        where = path
        if start:
            where += f":{start}"
            if end and end != start:
                where += f"-{end}"

        item = {
            "title": f"{check_id}",
            "description": f"{message} ({where})",
            "severity": sev,
        }

        cid = str(check_id).lower()
        if "no-eval" in cid:
            security.append(item)
        elif "no-console" in cid:
            best_practices.append(item)
        else:
            best_practices.append(item)

    return {
        "security": security,
        "bugs": bugs,
        "performance": performance,
        "best_practices": best_practices,
    }
