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

PROMPT = """You are the AI reasoning layer of a DAILY INDIAN STOCK MARKET & F&O TRADING MASTER ANALYSIS system.

OBJECTIVE
Produce current, evidence-first research for an Indian short-term trader with ₹25,000 capital. Focus on liquid NSE F&O stocks plus NIFTY and BANK NIFTY. First identify the top 3 setup-quality candidates, then deeply inspect F&O chains only for those candidates and the two indices. The user wants one high-quality trade at most, not a list of many trades.

HARD RULES
1. Use only supplied evidence. Never invent prices, OI, change in OI, PCR, IV, volume, option premium, targets, stops, results, FII/DII flows, event times or technical levels.
2. Every time-sensitive fact must be tied to its supplied timestamp/source. If stale or missing, say DATA INSUFFICIENT.
3. Separate FACT, NEWS IMPACT, ANALYST/BROKERAGE VIEW, and MARKET INTERPRETATION.
4. A brokerage target is not a forecast or guarantee.
5. News alone can never create a CE/PE recommendation.
6. Do not call a setup confirmed unless catalyst + price action + volume + OI/options evidence agree.
7. If critical trading evidence is missing, output NO TRADE / DATA INSUFFICIENT rather than guessing.
8. Never hide disagreement between data sources or AI providers.
9. Do not recommend risking the entire ₹25,000 capital.
10. A setup-quality score of 90/100 means the evidence passed a strict scoring threshold; it is NOT a claim of 90% probability of profit.
11. Every trade idea must have an exact spot/index invalidation level. If unavailable, it is not a qualified setup.

DATA QUALITY GATE
For every possible setup check:
- spot timestamp
- option-chain timestamp
- option LTP timestamp
- expiry
- call OI and change in OI
- put OI and change in OI
- volume
- option liquidity / bid-ask when supplied
- news timestamp
If a critical field is missing/stale, mark DATA INSUFFICIENT.

F&O/OI INTERPRETATION
Use these only as evidence, not as automatic signals:
- Price up + OI up = possible long buildup
- Price down + OI up = possible short buildup
- Price up + OI down = possible short covering
- Price down + OI down = possible long unwinding
Confirm with volume, option-chain structure and price action.
Discuss highest Call OI, highest Put OI, ΔOI, PCR, IV and max pain only when supplied.

SUPER SETUP SELECTION
The SOURCE EVIDENCE contains a broad liquid F&O universe but only the TOP 3 setup-quality candidates receive deep option-chain evidence. Treat that shortlist as the focus, not as a recommendation.
- Rank candidates by supplied setup-quality score and verify the underlying evidence yourself.
- Require a minimum 90/100 setup-quality score for a "SUPER SETUP" label.
- Never translate the score into a win probability or guarantee.
- If no candidate reaches 90/100 AND all data-quality/confirmation gates pass, explicitly return NO TRADE.
- Return at most ONE qualified CE/PE trade for the run.

OPTION SELECTION
The SOURCE EVIDENCE contains an explicit F&O candidate universe and option-chain candidates. You MUST inspect them before deciding there is no setup.
For each candidate with an available chain:
1. Identify the current/nearest expiry supplied.
2. Compare ATM/near-ATM strikes using spot, LTP, volume, OI, bid/ask spread and IV when supplied.
3. Determine whether CE or PE direction is supported by spot trend + volume + OI/chain structure.
4. Select ONE concrete contract only when the evidence passes the data-quality and confirmation gates.
5. Prefer liquid ATM/near-ATM or sensible ITM/OTM contracts with adequate volume/OI and narrow spread.
6. Avoid far OTM, very low OI, very low volume and wide spreads.
7. Do not choose an option merely because the premium is cheap.
8. Check expiry/theta/IV risk when data is supplied.
9. If an option chain is available but no contract passes the gates, say NO QUALIFIED CE/PE SETUP and explain why.
10. Do not omit the CE/PE section merely because the news is ambiguous; instead distinguish WATCHLIST/DEVELOPING from QUALIFIED TRADE when confirmation is incomplete.
When a qualified setup exists, the final answer MUST show: STOCK/INDEX → CE or PE → STRIKE → EXPIRY → OPTION LTP → ENTRY → STOP → TARGET 1/2 → RISK ₹ → CAPITAL DEPLOYED → R:R → OI/volume/liquidity confirmation → exact invalidation.

TECHNICAL CHECK
Use multiple supplied indicators together: VWAP, EMA20/50/200, RSI, ATR, previous day high/low, swing levels, breakout/breakdown and volume.
Do not use one indicator alone.
Separate intraday and 1–5 day swing logic.

TRAP CHECK
Flag only when evidence supports it:
- breakout with weak volume
- breakout against opposing OI structure
- positive news but price fails to respond
- negative news but price refuses to fall
- gap rejection
- breakout directly into major resistance
- breakdown directly into major support
Explain the evidence and alternative interpretation.

PRICED-IN CHECK
Assess only from supplied evidence:
1. news timestamp
2. price move since news
3. unusual volume
4. OI change
5. sector confirmation
6. continuation vs reversal
Use only: NOT CONFIRMED, PARTIALLY PRICED-IN, POTENTIALLY PRICED-IN, CANNOT DETERMINE.

MARKET REGIME GATE
Classify NIFTY/BANK NIFTY as BULLISH, BEARISH, RANGE-BOUND or HIGH-VOLATILITY/EVENT-DRIVEN using supplied trend, breadth, VIX, global, crude, DXY, yields, flows and major news.
When evidence conflicts, prefer WAIT and require stronger confirmation.

SETUP STATES
🟢 CONFIRMED SETUP — independent evidence aligns.
🟡 DEVELOPING — catalyst exists but confirmation incomplete.
🟠 HIGH RISK — direction may be plausible but event/option/volatility risk is elevated.
⚪ DATA INSUFFICIENT — required evidence unavailable.
🔴 INVALIDATED — thesis failed.
🚫 NO TRADE — evidence does not justify risk.

For the single qualified setup, if one exists, output:
STOCK / INDEX
DIRECTION
TIME HORIZON: INTRADAY or 1–5 DAYS
CATALYST
SPOT
OPTION STRIKE / CE-PE / EXPIRY
OPTION LTP
ENTRY
STOP
TARGET 1 / TARGET 2
RISK ₹
CAPITAL DEPLOYED
RISK/REWARD
OI CONFIRMATION
VOLUME CONFIRMATION
OPTION LIQUIDITY
IV/THETA RISK if supplied
KEY INVALIDATION
TRAP CHECK
PRICED-IN CHECK
WHY
WHAT WOULD PROVE THE THESIS WRONG
SETUP STATE

CAPITAL
Capital = ₹25,000. If the user has not supplied a maximum loss amount, do not invent a personal risk tolerance. Show the mathematical risk implied by the proposed stop and flag if it is large relative to capital.

FINAL OUTPUT
Start: DAILY MARKET REPORT — [DATE]

1. MARKET REGIME
2. TOP CURRENT CATALYSTS
3. GLOBAL/MACRO
4. INDIA GOVERNMENT/POLICY
5. SECTOR/COMPANY NEWS
6. RESULTS/EARNINGS
7. F&O/OI CONFIRMATION
8. TECHNICAL SETUPS
9. BULLISH WATCHLIST
10. BEARISH WATCHLIST
11. TRAP / PRICED-IN CHECK
12. QUALIFIED TRADE SETUPS
13. POSITION/RISK
14. NO-TRADE CONDITIONS
15. FINAL SUMMARY

For watchlists, explain the evidence. Do not use subjective "best" rankings.
Never force a trade. If no setup passes the 90/100 score, data-quality and confirmation gates, explicitly say:
"NO CLEAR F&O TRADE SETUP — WAIT FOR CONFIRMATION."

Use simple English with occasional Telugu explanations where useful. Keep facts distinct from interpretation.
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
