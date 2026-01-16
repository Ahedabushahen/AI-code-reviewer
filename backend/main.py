from typing import Literal, List, Optional
from pathlib import Path
import ast
import re

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from analyzers.temp_project import make_temp_project
from analyzers.semgrep_runner import run_semgrep_on_folder, semgrep_results_to_categories
from analyzers.eslint_runner import run_eslint, eslint_to_schema
from analyzers.bandit_runner import run_bandit, bandit_to_schema

load_dotenv()

Severity = Literal["low", "medium", "high"]
Recommendation = Literal["block_merge", "review_required", "ok"]


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
    # ai_used = automated tools used (Semgrep/ESLint/Bandit), not LLM
    ai_used: bool = False
    ai_error: Optional[str] = None

    score: int = Field(ge=1, le=10)
    summary: str
    recommendation: Recommendation = "ok"

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


def validate_python_syntax(code: str) -> Optional[str]:
    """
    Validate Python code syntax. Returns error message if invalid, None if valid.
    """
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        return f"Python syntax error at line {e.lineno}: {e.msg}"
    except Exception as e:
        return f"Python parsing error: {str(e)}"


def check_undefined_names(code: str) -> Optional[str]:
    """
    Check for undefined names in Python code. Returns error message if found, None if OK.
    """
    try:
        tree = ast.parse(code)
        
        class NameCollector(ast.NodeVisitor):
            def __init__(self):
                self.defined = set()
                self.used = set()
            
            def visit_Import(self, node):
                # Handle: import os, import sys as s
                for alias in node.names:
                    self.defined.add(alias.asname if alias.asname else alias.name)
                self.generic_visit(node)
            
            def visit_ImportFrom(self, node):
                # Handle: from os import path
                for alias in node.names:
                    if alias.name == '*':
                        # Can't track star imports, skip
                        pass
                    else:
                        self.defined.add(alias.asname if alias.asname else alias.name)
                self.generic_visit(node)
            
            def visit_Name(self, node):
                if isinstance(node.ctx, ast.Store):
                    self.defined.add(node.id)
                elif isinstance(node.ctx, ast.Load):
                    self.used.add(node.id)
                self.generic_visit(node)
            
            def visit_FunctionDef(self, node):
                self.defined.add(node.name)
                # Add function parameters as defined
                for arg in node.args.args:
                    self.defined.add(arg.arg)
                self.generic_visit(node)
            
            def visit_AsyncFunctionDef(self, node):
                self.defined.add(node.name)
                # Add function parameters as defined
                for arg in node.args.args:
                    self.defined.add(arg.arg)
                self.generic_visit(node)
            
            def visit_ClassDef(self, node):
                self.defined.add(node.name)
                self.generic_visit(node)
            
            def visit_ExceptHandler(self, node):
                # Handle: except Exception as e
                if node.name:
                    self.defined.add(node.name)
                self.generic_visit(node)
        
        collector = NameCollector()
        collector.visit(tree)
        
        # Common Python builtins and special variables
        builtins_set = {
            'print', 'len', 'range', 'str', 'int', 'float', 'bool', 'list', 'dict', 'set', 'tuple', 
            'None', 'True', 'False', 'open', 'input', 'sum', 'min', 'max', 'enumerate', 'zip',
            'map', 'filter', 'sorted', 'reversed', 'abs', 'round', 'pow', 'divmod', 'isinstance',
            'issubclass', 'callable', 'hasattr', 'getattr', 'setattr', 'delattr', 'type', 'object',
            'super', 'property', 'staticmethod', 'classmethod', 'Exception', 'ValueError', 'TypeError',
            'KeyError', 'IndexError', 'RuntimeError', 'ImportError', 'AttributeError', 'NameError',
            'StopIteration', 'iter', 'next', 'all', 'any', 'bin', 'hex', 'oct', 'ord', 'chr',
            'format', 'repr', 'ascii', 'eval', 'exec', 'compile', '__import__', 'vars', 'dir',
            'id', 'hash', 'bytes', 'bytearray', 'complex', 'memoryview', 'slice', 'frozenset',
            '__name__', '__file__', '__doc__', '__package__', '__loader__', '__spec__', 'self',
            'cls', 'BaseException', 'StopAsyncIteration', 'GeneratorExit', 'KeyboardInterrupt',
            'SystemExit', 'Exception', 'ArithmeticError', 'BufferError', 'LookupError', 'EnvironmentError'
        }
        
        undefined = collector.used - collector.defined - builtins_set
        
        if undefined:
            undefined_list = sorted(list(undefined))
            return f"Undefined names: {', '.join(undefined_list)}"
        
        return None
    except Exception:
        # If we can't check, just return None (let other tools catch issues)
        return None


def check_undefined_names_js(code: str) -> Optional[str]:
    """
    Smart check for truly undefined names in JavaScript/TypeScript.
    Only flags variables actually used in code, not keywords or string contents.
    """
    try:
        # All JavaScript/TypeScript keywords to exclude
        js_keywords = {
            'abstract', 'arguments', 'await', 'boolean', 'break', 'byte', 'case', 'catch', 'char',
            'class', 'const', 'continue', 'debugger', 'default', 'delete', 'do', 'double', 'else',
            'enum', 'eval', 'export', 'extends', 'false', 'final', 'finally', 'float', 'for',
            'function', 'goto', 'if', 'implements', 'import', 'in', 'instanceof', 'int', 'interface',
            'let', 'long', 'native', 'new', 'null', 'package', 'private', 'protected', 'public',
            'return', 'short', 'static', 'super', 'switch', 'synchronized', 'this', 'throw',
            'throws', 'transient', 'true', 'try', 'typeof', 'var', 'void', 'volatile', 'while',
            'with', 'yield', 'async', 'from', 'as', 'get', 'set', 'of', 'target', 'readonly',
            'declare', 'namespace', 'module', 'type', 'keyof', 'unique', 'infer'
        }
        
        # Common JavaScript/TypeScript built-ins and globals
        js_builtins = {
            'console', 'print', 'log', 'warn', 'error', 'Array', 'Object', 'String', 'Number', 
            'Boolean', 'Math', 'JSON', 'Date', 'RegExp', 'Error', 'Function', 'Symbol',
            'Promise', 'Map', 'Set', 'WeakMap', 'WeakSet', 'ArrayBuffer', 'DataView',
            'Int8Array', 'Uint8Array', 'Uint8ClampedArray', 'Int16Array', 'Uint16Array',
            'Int32Array', 'Uint32Array', 'Float32Array', 'Float64Array', 'BigInt64Array',
            'BigUint64Array', 'Proxy', 'Reflect', 'undefined', 'null', 'true', 'false',
            'parseInt', 'parseFloat', 'isNaN', 'isFinite', 'encodeURI', 'decodeURI',
            'encodeURIComponent', 'decodeURIComponent', 'setTimeout', 'setInterval',
            'clearTimeout', 'clearInterval', 'alert', 'confirm', 'prompt', 'fetch',
            'window', 'document', 'navigator', 'location', 'localStorage', 'sessionStorage',
            'XMLHttpRequest', 'FormData', 'Blob', 'FileReader', 'Request', 'Response', 'Headers',
            'getElementById', 'querySelector', 'querySelectorAll', 'getElementsByClassName',
            'getElementsByTagName', 'createElement', 'appendChild', 'removeChild', 'innerHTML',
            'textContent', 'setAttribute', 'getAttribute', 'removeAttribute', 'classList',
            'addEventListener', 'removeEventListener', 'preventDefault', 'stopPropagation',
            'then', 'catch', 'finally', 'resolve', 'reject', 'axios', 'fetch',
            'parse', 'stringify', 'slice', 'splice', 'push', 'pop', 'shift', 'unshift',
            'map', 'filter', 'reduce', 'forEach', 'find', 'findIndex', 'includes',
            'indexOf', 'lastIndexOf', 'join', 'split', 'trim', 'toUpperCase', 'toLowerCase',
            'charAt', 'charCodeAt', 'substring', 'substr', 'replace', 'match', 'search',
            'startsWith', 'endsWith', 'repeat', 'padStart', 'padEnd', 'hasOwnProperty',
            'keys', 'values', 'entries', 'assign', 'create', 'defineProperty', 'freeze', 'seal',
            'isArray', 'write', 'read', 'send', 'open', 'execute', 'express', 'require', 'module'
        }
        
        # Combined exclusion list
        exclude = js_keywords | js_builtins
        
        # Remove all strings and comments to avoid checking string content
        code_no_strings = re.sub(r'"[^"]*"', '""', code)  # Remove double quoted strings
        code_no_strings = re.sub(r"'[^']*'", "''", code_no_strings)  # Remove single quoted strings
        code_no_strings = re.sub(r'`[^`]*`', '``', code_no_strings)  # Remove template strings
        code_no_strings = re.sub(r'//.*$', '', code_no_strings, flags=re.MULTILINE)  # Remove line comments
        code_no_strings = re.sub(r'/\*[\s\S]*?\*/', '', code_no_strings)  # Remove block comments
        
        # Remove TypeScript type annotations (: type patterns)
        code_no_strings = re.sub(r':\s*[a-zA-Z_$<>[\]{}|&\s,]*(?=[,;)\]\}])', '', code_no_strings)
        
        # Extract variable declarations
        defined_vars = set()
        var_decls = re.findall(r'(?:let|const|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)', code_no_strings)
        defined_vars.update(var_decls)
        
        # Function declarations
        func_defs = re.findall(r'function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)', code_no_strings)
        defined_vars.update(func_defs)
        
        # Class declarations
        class_defs = re.findall(r'class\s+([a-zA-Z_$][a-zA-Z0-9_$]*)', code_no_strings)
        defined_vars.update(class_defs)
        
        # Function parameters
        param_matches = re.findall(r'\(\s*([^)]+)\s*\)\s*(?:=>|{)', code_no_strings)
        for params_str in param_matches:
            params = re.findall(r'([a-zA-Z_$][a-zA-Z0-9_$]*)', params_str)
            defined_vars.update(params)
        
        # Catch block exceptions
        catch_exceptions = re.findall(r'catch\s*\(\s*([a-zA-Z_$][a-zA-Z0-9_$]*)', code_no_strings)
        defined_vars.update(catch_exceptions)
        
        # Find truly standalone variable references (not part of property access)
        # Exclude anything preceded by a dot (property/method access)
        used_vars = set()
        
        # Match identifiers NOT preceded by dot
        # Negative lookbehind: (?<!\.) means "not preceded by dot"
        standalone = re.findall(r'(?<!\.)(?<!\w)\b([a-zA-Z_$][a-zA-Z0-9_$]*)\b(?!\w)(?!\s*\.)', code_no_strings)
        used_vars.update(standalone)
        
        # Find undefined: used but not defined and not in exclusion list
        undefined = used_vars - defined_vars - exclude
        
        # Additional filters: exclude very short names and obvious false positives
        undefined = {u for u in undefined if len(u) > 2 or u in ['io', 'fs', 'os', 'db', 'api']}
        
        if undefined and len(undefined) > 0:
            undefined_list = sorted(list(undefined))
            return f"Undefined names: {', '.join(undefined_list)}"
        
        return None
    except Exception:
        return None


@app.post("/review", response_model=ReviewResponse)
def review(req: ReviewRequest) -> ReviewResponse:
    code = req.content or ""
    if not code.strip():
        return ReviewResponse(
            ai_used=True,
            ai_error=None,
            score=1,
            summary="No code provided. Paste some code to get a review.",
            recommendation="review_required",
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

    # -------------------------
    # Validate Python syntax if language is Python
    # -------------------------
    is_python = req.language.strip().lower() in ["python", "py"]
    if is_python:
        syntax_error = validate_python_syntax(code)
        if syntax_error:
            return ReviewResponse(
                ai_used=True,
                ai_error=None,
                score=2,
                summary=f"Python code has syntax errors: {syntax_error}",
                recommendation="review_required",
                bugs=[
                    ReviewItem(
                        title="Syntax Error",
                        description=syntax_error,
                        severity="high",
                    )
                ],
                security=[],
                performance=[],
                best_practices=[],
            )
        
        # Let Bandit and Semgrep handle semantic checks - skip hardcoded validation

    # Check for trivial code (single identifier or very short)
    lines = [l.strip() for l in code.split('\n') if l.strip()]
    if len(lines) == 1 and len(lines[0]) < 10 and not any(c in lines[0] for c in '()[]{}:='):
        return ReviewResponse(
            ai_used=True,
            ai_error=None,
            score=3,
            summary="Code snippet is too trivial to review. Please provide meaningful code with logic.",
            recommendation="review_required",
            bugs=[
                ReviewItem(
                    title="Trivial Code",
                    description="Single identifier or very short snippet is not meaningful code. Add functions, classes, or logic.",
                    severity="medium",
                )
            ],
            security=[],
            performance=[],
            best_practices=[],
        )

    # -------------------------
    # Check for undefined names in JavaScript/TypeScript
    # -------------------------
    is_js = req.language.strip().lower() in ["javascript", "js", "typescript", "ts"]
    if is_js:
        # Let ESLint handle this - skip hardcoded check
        pass

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
        # Bandit (Python only, best effort)
        # -------------------------
        bandit_error_note: Optional[str] = None
        bandit_security: List[ReviewItem] = []

        if is_python:
            try:
                bandit_res = run_bandit(project_dir=temp_dir.name)
                if not bandit_res.get("ok", False):
                    bandit_error_note = f"bandit_failed: {str(bandit_res.get('error', 'unknown'))[:160]}"
                else:
                    bandit_cat = bandit_to_schema(bandit_res)
                    bandit_security = [ReviewItem(**x) for x in bandit_cat["security"]]
            except Exception as e:
                bandit_error_note = f"bandit_failed: {str(e)[:160]}"

        # -------------------------
        # Merge categories
        # -------------------------
        security_items = semgrep_security + eslint_security + bandit_security
        bugs_items = eslint_bugs
        best_practices_items = semgrep_best + eslint_best
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

        # -------------------------
        # Recommendation (CI-friendly)
        # -------------------------
        has_high_security = any(it.severity == "high" for it in security_items)
        if has_high_security:
            recommendation: Recommendation = "block_merge"
        elif score <= 6:
            recommendation = "review_required"
        else:
            recommendation = "ok"

        # Combine tool error notes (if any)
        notes = []
        if eslint_error_note:
            notes.append(eslint_error_note)
        if bandit_error_note:
            notes.append(bandit_error_note)
        ai_error = "; ".join(notes) if notes else None

        return ReviewResponse(
            ai_used=True,
            ai_error=ai_error,
            score=score,
            summary=summary,
            recommendation=recommendation,
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
            recommendation="review_required",
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
