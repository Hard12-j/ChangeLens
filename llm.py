"""
llm.py
------
LLM integration: build prompt, call API, return structured JSON report.
Supports OpenAI and OpenAI-compatible APIs (Groq, Together, Ollama, etc.).
"""

import json
import os
import re
import time

from openai import OpenAI

_client = None

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
MAX_DIFF_CHARS = 12_000


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        if base_url:
            _client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            _client = OpenAI(api_key=api_key)
    return _client


_SYSTEM = """You are ChangeLens, an expert software change analyst for Spring Boot applications.
Your audience is engineering managers and non-technical stakeholders.
Respond with ONLY valid JSON matching this schema exactly -- no text outside the JSON:

{
  "summary": "<3-5 plain-English sentences, no jargon>",
  "risk_level": "<Low | Medium | High>",
  "risk_reason": "<one short sentence>",
  "changes": [
    {
      "what": "<concise description>",
      "who": "<author name>",
      "when": "<date>",
      "why": "<best-guess reason (inferred)>",
      "what_could_break": "<potential breakage or Nothing obvious>"
    }
  ],
  "technical_findings": ["<finding1>", "<finding2>"]
}

Rules:
- Mark every "why" with "(inferred)" since you are guessing from the diff.
- Use plain English in summary and changes. Avoid Spring jargon.
- If nothing is risky, set risk_level to Low and be honest about it.
"""


def _build_prompt(diff_text, commit_info_text, mode, rule_findings_text, rag_context):
    diff_snippet = diff_text[:MAX_DIFF_CHARS]
    if len(diff_text) > MAX_DIFF_CHARS:
        diff_snippet += "\n... [diff truncated] ..."
    parts = [
        f"## Commit information\n{commit_info_text}",
        f"## Git diff\n```diff\n{diff_snippet}\n```",
    ]
    if mode in ("B", "C") and rule_findings_text:
        parts.append(f"## Rule-based findings\n{rule_findings_text}")
    if mode == "C" and rag_context:
        parts.append(f"## Retrieved code context\n{rag_context}")
    parts.append("Return ONLY the JSON object. No prose, no markdown wrapping.")
    return "\n\n".join(parts)


def analyse(diff_text, commit_info_text, mode="A",
            rule_findings_text="", rag_context="") -> dict:
    """
    Call the LLM and return parsed JSON report.
    mode A = diff only | B = diff + rules | C = diff + rules + RAG
    """
    client = _get_client()
    prompt = _build_prompt(diff_text, commit_info_text, mode, rule_findings_text, rag_context)
    t0 = time.time()
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    elapsed = round(time.time() - t0, 2)
    raw = response.choices[0].message.content or "{}"
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        result = json.loads(m.group(0)) if m else {}
    result["_mode"] = mode
    result["_elapsed_s"] = elapsed
    result["_model"] = LLM_MODEL
    return result


def format_commit_info(commits) -> str:
    if not commits:
        return "No commit information available."
    lines = []
    for c in commits:
        lines.append(
            f"- SHA: {c.short_sha}  Author: {c.author} <{c.email}>  "
            f"Date: {c.date}  Message: {c.message}"
        )
    return "\n".join(lines)


def format_rule_findings(findings) -> str:
    if not findings:
        return "No deterministic findings."
    lines = []
    for f in findings:
        lines.append(
            f"[{f.severity.upper()}] ({f.category}) {f.description}"
            + (f"\n  Detail: {f.detail}" if f.detail else "")
        )
    return "\n".join(lines)
