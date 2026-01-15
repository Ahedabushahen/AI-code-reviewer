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


def semgrep_results_to_review_items(data: Dict[str, Any]) -> List[Dict[str, str]]:
    findings = data.get("results", []) or []
    items: List[Dict[str, str]] = []

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

        path = (f.get("path") or "")
        start = ((f.get("start") or {}) or {}).get("line")
        end = ((f.get("end") or {}) or {}).get("line")

        where = path
        if start:
            where += f":{start}"
            if end and end != start:
                where += f"-{end}"

        items.append(
            {
                "title": f"{check_id}",
                "description": f"{message} ({where})",
                "severity": sev,
            }
        )

    return items
