import json
from typing import Any, Dict, Optional

from openai import OpenAI


SYSTEM_PROMPT = """
You are a strict code review assistant.

Return ONLY valid JSON matching this schema:
{
  "score": integer 1-10,
  "summary": string,
  "bugs": [{"title": string, "description": string, "severity": "low"|"medium"|"high"}],
  "security": [...same item schema...],
  "performance": [...same item schema...],
  "best_practices": [...same item schema...]
}

Rules:
- Output JSON only (no markdown, no backticks).
- Be concise but helpful.
- Prefer fewer, higher-signal items over many low-signal notes.
"""


def generate_review_json(
    *,
    api_key: str,
    model: str,
    language: str,
    content_type: str,
    content: str,
) -> Dict[str, Any]:
    """
    Calls OpenAI Responses API and returns parsed JSON (dict).
    """
    client = OpenAI(api_key=api_key)

    user_prompt = f"""
Language: {language}
Content-Type: {content_type}

CODE/DIFF:
{content}
""".strip()

    # Responses API example pattern: client.responses.create(...), then use response.output_text
    # :contentReference[oaicite:2]{index=2}
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    text = resp.output_text.strip()

    # Parse JSON only
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("AI output was not a JSON object")
    return data
