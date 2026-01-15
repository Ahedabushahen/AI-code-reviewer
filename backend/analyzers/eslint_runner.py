from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List


JS_TS_GLOBS = ["**/*.js", "**/*.jsx", "**/*.ts", "**/*.tsx"]


def _repo_root_from_backend_dir(backend_dir: Path) -> Path:
    # backend/.. = repo root
    return backend_dir.parent


def _eslint_bin_path(repo_root: Path) -> Path:
    """
    Local eslint binary under tools/eslint.
    Windows uses eslint.cmd
    """
    base = repo_root / "tools" / "eslint" / "node_modules" / ".bin"
    return (base / "eslint.cmd") if os.name == "nt" else (base / "eslint")


def _collect_targets(project_dir: Path) -> List[str]:
    files: List[str] = []
    for pattern in JS_TS_GLOBS:
        files.extend([str(p) for p in project_dir.glob(pattern) if p.is_file()])

    # Deduplicate while preserving order
    seen = set()
    out: List[str] = []
    for f in files:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def run_eslint(project_dir: str, backend_dir: str) -> Dict[str, Any]:
    """
    Runs ESLint on JS/TS files inside project_dir and returns parsed JSON.
    Non-zero exit is OK (means issues found).
    """
    project_path = Path(project_dir).resolve()
    backend_path = Path(backend_dir).resolve()
    repo_root = _repo_root_from_backend_dir(backend_path)

    eslint_bin = _eslint_bin_path(repo_root)
    config_path = repo_root / "tools" / "eslint" / "eslint.config.mjs"

    if not eslint_bin.exists():
        return {"ok": False, "error": f"ESLint not found: {eslint_bin}", "issues": []}

    if not config_path.exists():
        return {"ok": False, "error": f"ESLint config not found: {config_path}", "issues": []}

    targets = _collect_targets(project_path)
    if not targets:
        return {"ok": True, "error": None, "issues": []}

    cache_dir = repo_root / ".cache" / "eslint"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / ".eslintcache"

    cmd = [
        str(eslint_bin),
        "--config",
        str(config_path),
        "--format",
        "json",
        "--cache",
        "--cache-location",
        str(cache_file),
        "--no-error-on-unmatched-pattern",
        *targets,
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
        return {"ok": False, "error": f"ESLint produced no JSON. stderr: {stderr[:2000]}", "issues": []}

    try:
        raw = json.loads(stdout)
    except Exception:
        return {"ok": False, "error": f"Failed parsing ESLint JSON. stderr: {stderr[:2000]}", "issues": []}

    issues: List[Dict[str, Any]] = []
    for file_report in raw:
        file_path = file_report.get("filePath", "")
        for m in (file_report.get("messages") or []):
            issues.append(
                {
                    "tool": "eslint",
                    "file": file_path,
                    "line": m.get("line", 0),
                    "column": m.get("column", 0),
                    "rule_id": m.get("ruleId") or "eslint",
                    "severity_num": m.get("severity", 1),  # 2=error, 1=warn
                    "message": m.get("message", ""),
                }
            )

    return {"ok": True, "error": None if not stderr else stderr[:2000], "issues": issues}


def eslint_to_schema(eslint_result: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Convert ESLint issues into your main response buckets.
    """
    security: List[Dict[str, Any]] = []
    bugs: List[Dict[str, Any]] = []
    best_practices: List[Dict[str, Any]] = []
    performance: List[Dict[str, Any]] = []

    def pretty_file(path_str: str) -> str:
        if not path_str:
            return ""
        try:
            return Path(path_str).name  # main.ts instead of full temp path
        except Exception:
            return path_str

    for it in eslint_result.get("issues", []):
        rule_id = it.get("rule_id") or "eslint"
        rule = rule_id.lower()
        sev_num = it.get("severity_num", 1)

        file_path = it.get("file") or ""
        line = it.get("line") or 0
        pf = pretty_file(file_path)

        # Avoid duplicates: Semgrep already flags eval as security
        if rule == "no-eval":
            continue

        # Treat TS "any" as best practice (medium), not a high bug
        if rule == "@typescript-eslint/no-explicit-any":
            best_practices.append(
                {
                    "title": f"eslint.{rule_id}",
                    "description": f"{it.get('message')} ({pf}:{line})",
                    "severity": "medium",
                }
            )
            continue

        # Default mapping:
        # - ESLint error => bugs high
        # - ESLint warn  => best_practices medium
        if sev_num == 2:
            bugs.append(
                {
                    "title": f"eslint.{rule_id}",
                    "description": f"{it.get('message')} ({pf}:{line})",
                    "severity": "high",
                }
            )
        else:
            best_practices.append(
                {
                    "title": f"eslint.{rule_id}",
                    "description": f"{it.get('message')} ({pf}:{line})",
                    "severity": "medium",
                }
            )

    return {
        "security": security,
        "bugs": bugs,
        "best_practices": best_practices,
        "performance": performance,
    }
