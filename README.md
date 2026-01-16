AI Code Reviewer

An automated, CI-ready code review system built with FastAPI and Angular that analyzes source code using static analysis tools and provides a clear merge recommendation for pull requests.

This project focuses on deterministic, tool-based analysis (not LLM-generated reviews) and is designed to behave like a real production-grade code review gate.

---

Features

* Multi-tool static analysis

  * Semgrep for security and code quality rules
  * ESLint for JavaScript / TypeScript best practices
  * Bandit for Python security analysis

* Unified review output

  * Normalized findings across all tools
  * Severity levels: low, medium, high
  * Final score from 1 to 10

* Merge recommendation logic

  * block_merge: high-severity security issues detected
  * review_required: issues found, manual review recommended
  * ok: safe to merge

* GitHub Pull Request integration

  * Automatically runs on pull requests using GitHub Actions
  * Posts a summary comment with score and recommendation
  * Can block merges when critical issues are detected

* Frontend UI (Angular) 

  * Displays findings by category
  * Shows score and recommendation clearly

---

Design Principles

* No paid APIs
* No LLM dependency
* Deterministic and explainable results
* Production-style CI behavior
* Cross-platform (Windows and Linux)

---

Tech Stack

Backend:

* Python
* FastAPI

Frontend:

* Angular

Static Analysis:

* Semgrep
* ESLint
* Bandit

CI/CD:

* GitHub Actions

---

How It Works

1. Code is submitted via API or through a Pull Request
2. Static analysis tools run on the codebase
3. Results are normalized into a single schema
4. A score and merge recommendation are calculated
5. In CI, results are posted automatically on the Pull Request

---

Project Structure

backend/

* analyzers/

  * semgrep_runner.py
  * eslint_runner.py
  * bandit_runner.py
* ci_review.py
* main.py

frontend/

* Angular UI

.github/workflows/

* code_review.yml

---

Local Development

Run backend server:
cd backend
python -m uvicorn main:app --reload

Run CI review locally:
python backend/ci_review.py

---

Motivation

This project demonstrates how automated code review systems used in real software companies are built:

* rule-based
* CI-integrated
* deterministic
* security-focused

---

License

MIT


