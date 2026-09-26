"""Multi-provider AI market intelligence cross-check with graceful fallbacks."""
from __future__ import annotations
import json
import os
import time
from typing import Any
import requests
from openai import OpenAI

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

PROMPT = """You are a neutral Indian-market news analyst writing for an ordinary trader.
Your job is CONTEXT FIRST, not simply positive/negative.

Analyze only the supplied evidence. Never invent live price, volume, OI, option-chain, earnings, targets, stop losses, probabilities, company guidance, deal values, margins, or facts not present in the evidence.
If information is missing, explicitly say "Not available in supplied data".
Do not assume that a headline is positive or negative without explaining why.

For EACH of the most important supplied news items, write a separate, easy-to-read report using EXACTLY this structure:

🔥/🟢/🔴/🟡/⚪ IMPORTANCE + DIRECTION
🏢 COMPANY / SECTOR
📰 WHAT HAPPENED?
📖 CONTEXT
👤 WHO IS AFFECTED?
💰 BUSINESS IMPACT
Revenue:
Cost:
Profit:
Growth:
Order book / cash flow:
🟢 POSSIBLE POSITIVE IMPACT
🔴 POSSIBLE NEGATIVE IMPACT
🟡 OTHER / NEUTRAL INTERPRETATION
📈 MARKET REACTION
🧩 NEWS VS MARKET
⏰ FRESHNESS / PRICED-IN
🔎 WATCH NEXT
🧠 WHY SHOULD I CARE?
📌 STATUS
Use only: TRADEABLE, WAIT, AVOID, NO TRADE.
This is an evidence status, NOT a forced buy/sell recommendation. News alone must never create a CE/PE recommendation.

Use simple English with occasional Telugu explanation where it makes the meaning clearer. Avoid technical AI jargon, raw scores, and JSON in the trader-facing report.
Distinguish FACTS from INTERPRETATION. If different AI analyses disagree, explicitly show the disagreement.
"""

def build_prompt(payload: dict[str, Any], phase: str) -> str:
    return f"{PROMPT}\n\nPHASE: {phase}\nSOURCE EVIDENCE:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"

def _openai_compatible(base_url: str, key: str, model: str, payload: dict, phase: str, extra_headers=None):
    client = OpenAI(api_key=key, base_url=base_url)
    response = client.responses.create(
        model=model,
        input=build_prompt(payload, phase),
    )
    return (response.output_text or "").strip() or None

def call_openai(payload, phase):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    try:
        return _openai_compatible("https://api.openai.com/v1", key, OPENAI_MODEL, payload, phase)
    except Exception as e:
        return f"OPENAI_ERROR: {type(e).__name__}: {e}"

def call_gemini(payload, phase):
    """Call Gemini through REST so SDK client lifecycle cannot break the run."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    body = {
        "contents": [{"parts": [{"text": build_prompt(payload, phase)}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 12000},
    }
    last_error = None
    for attempt in range(1, 4):
        try:
            r = requests.post(
                url,
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=body,
                timeout=90,
            )
            if r.status_code >= 400:
                last_error = f"HTTP {r.status_code}: {r.text[:1000]}"
                if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(attempt * 2)
                    continue
                return f"GEMINI_ERROR: {last_error}"
            data = r.json()
            parts = []
            for candidate in data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if part.get("text"):
                        parts.append(part["text"])
            text = "\n".join(parts).strip()
            return text or "GEMINI_ERROR: Empty response"
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            if attempt < 3:
                time.sleep(attempt * 2)
            else:
                return f"GEMINI_ERROR: {last_error}"
    return f"GEMINI_ERROR: {last_error or 'Unknown error'}"

def call_openrouter(payload, phase):
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return None
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/tanils/ANILNEWSFO",
                "X-Title": "ANILNEWSFO Market Intelligence",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": build_prompt(payload, phase)}],
                "temperature": 0.2,
                "max_tokens": 12000,
            },
            timeout=120,
        )
        if r.status_code >= 400:
            return f"OPENROUTER_ERROR: HTTP {r.status_code}: {r.text[:1000]}"
        data = r.json()
        text = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        return text or "OPENROUTER_ERROR: Empty response"
    except Exception as e:
        return f"OPENROUTER_ERROR: {type(e).__name__}: {e}"

def call_groq(payload, phase):
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return None
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": build_prompt(payload, phase)}],
                "temperature": 0.2,
                "max_tokens": 12000,
            },
            timeout=120,
        )
        if r.status_code >= 400:
            return f"GROQ_ERROR: HTTP {r.status_code}: {r.text[:1000]}"
        data = r.json()
        text = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        return text or "GROQ_ERROR: Empty response"
    except Exception as e:
        return f"GROQ_ERROR: {type(e).__name__}: {e}"

def cross_check(payload, phase):
    # Stop after two successful providers so free quotas are conserved.
    providers = [
        ("GEMINI", call_gemini),
        ("OPENROUTER", call_openrouter),
        ("GROQ", call_groq),
        ("OPENAI", call_openai),
    ]
    analyses = []
    errors = {}
    for name, fn in providers:
        result = fn(payload, phase)
        if not result:
            continue
        if result.startswith(name + "_ERROR:"):
            errors[name] = result
            continue
        analyses.append({"provider": name, "analysis": result})
        if len(analyses) >= 2:
            break

    available = [item["provider"] for item in analyses]
    if len(available) == 2:
        status = "DUAL_AI_AVAILABLE"
    elif len(available) == 1:
        status = "SINGLE_AI_AVAILABLE"
    else:
        status = "NO_AI_AVAILABLE"

    # Keep legacy fields for compatibility with saved state/older tooling.
    by_provider = {item["provider"]: item["analysis"] for item in analyses}
    return {
        "status": status,
        "available_models": available,
        "analyses": analyses,
        "errors": errors,
        "openai_analysis": by_provider.get("OPENAI"),
        "gemini_analysis": by_provider.get("GEMINI"),
        "openrouter_analysis": by_provider.get("OPENROUTER"),
        "groq_analysis": by_provider.get("GROQ"),
    }
