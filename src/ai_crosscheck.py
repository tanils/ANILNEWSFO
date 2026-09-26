"""Independent OpenAI + Gemini market intelligence cross-check."""
from __future__ import annotations
import json, os
from typing import Any
from openai import OpenAI
import time
import requests

OPENAI_MODEL=os.getenv("OPENAI_MODEL","gpt-5-mini")
GEMINI_MODEL=os.getenv("GEMINI_MODEL","gemini-3.8-flash")

PROMPT="""You are a neutral Indian-market news analyst writing for an ordinary trader.
Your job is CONTEXT FIRST, not simply positive/negative.

Analyze only the supplied evidence. Never invent live price, volume, OI, option-chain, earnings, targets, stop losses, probabilities, company guidance, deal values, margins, or facts not present in the evidence.
If information is missing, explicitly say "Not available in supplied data".
Do not assume that a headline is positive or negative without explaining why.

For EACH of the most important supplied news items, write a separate, easy-to-read report using EXACTLY this structure:

🔥/🟢/🔴/🟡/⚪ IMPORTANCE + DIRECTION
🏢 COMPANY / SECTOR
📰 WHAT HAPPENED?
Explain the event in plain language, including the important factual details present in the source.
📖 CONTEXT
Explain what led to this event, what it changes, and any relevant earlier context present in the evidence.
👤 WHO IS AFFECTED?
Company, sector, customers, suppliers, competitors, government/regulator, etc., only when supported.
💰 BUSINESS IMPACT
Revenue:
Cost:
Profit:
Growth:
Order book / cash flow:
For each, explain the mechanism. Use "Unknown" where unsupported.
🟢 POSSIBLE POSITIVE IMPACT
Give evidence-based reasons the event could help.
🔴 POSSIBLE NEGATIVE IMPACT
Give evidence-based reasons it could hurt or disappoint.
🟡 OTHER / NEUTRAL INTERPRETATION
Explain why the event may have limited impact or why the market could interpret it differently.
📈 MARKET REACTION
Use supplied market data only. Say unavailable if absent. Do not invent reaction.
🧩 NEWS VS MARKET
Explain whether price action confirms, contradicts, or cannot yet confirm the news. Do not call something a "trap" unless there is actual contradictory evidence; if there is, explain the possible alternative explanation.
⏰ FRESHNESS / PRICED-IN
State whether it is new, repeated, or unknown. Discuss "priced in" only if the supplied evidence supports it.
🔎 WATCH NEXT
List concrete follow-up facts/events that would help determine the eventual impact.
🧠 WHY SHOULD I CARE?
One simple paragraph explaining why an ordinary trader/investor should pay attention.
📌 STATUS
Use only: TRADEABLE, WAIT, AVOID, NO TRADE.
This is an evidence status, NOT a forced buy/sell recommendation. News alone must never create a CE/PE recommendation.

Use simple English with occasional Telugu explanation where it makes the meaning clearer. Avoid technical AI jargon, raw scores, and JSON in the trader-facing report.
At the end add:
🤖 AI CROSS-CHECK
OpenAI and Gemini should be compared only on factual agreement/disagreement. Do not declare a trading winner.

Important: distinguish FACTS from INTERPRETATION. If OpenAI/Gemini disagree, explicitly show the disagreement rather than hiding it.
"""

def build_prompt(payload:dict[str,Any],phase:str)->str:
    return f"{PROMPT}\n\nPHASE: {phase}\nSOURCE EVIDENCE:\n{json.dumps(payload,ensure_ascii=False,indent=2)}"

def call_openai(payload,phase):
    key=os.getenv("OPENAI_API_KEY")
    if not key:return None
    try:
        r=OpenAI(api_key=key).responses.create(model=OPENAI_MODEL,input=build_prompt(payload,phase))
        return (r.output_text or "").strip() or None
    except Exception as e:
        return f"OPENAI_ERROR: {type(e).__name__}: {e}"

def call_gemini(payload,phase):
    """Call Gemini through REST so a closed SDK client cannot break the run."""
    key=os.getenv("GEMINI_API_KEY")
    if not key:return None
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    body={
        "contents":[{"parts":[{"text":build_prompt(payload,phase)}]}],
        "generationConfig":{"temperature":0.2,"maxOutputTokens":12000}
    }
    last_error=None
    for attempt in range(1,4):
        try:
            r=requests.post(
                url,
                headers={"x-goog-api-key":key,"Content-Type":"application/json"},
                json=body,
                timeout=90
            )
            if r.status_code >= 400:
                last_error=f"HTTP {r.status_code}: {r.text[:1000]}"
                if r.status_code in (429,500,502,503,504) and attempt < 3:
                    time.sleep(attempt * 2)
                    continue
                return f"GEMINI_ERROR: {last_error}"
            data=r.json()
            parts=[]
            for candidate in data.get("candidates",[]):
                for part in candidate.get("content",{}).get("parts",[]):
                    if part.get("text"):
                        parts.append(part["text"])
            text="\n".join(parts).strip()
            return text or "GEMINI_ERROR: Empty response"
        except Exception as e:
            last_error=f"{type(e).__name__}: {e}"
            if attempt < 3:
                time.sleep(attempt * 2)
            else:
                return f"GEMINI_ERROR: {last_error}"
    return f"GEMINI_ERROR: {last_error or 'Unknown error'}"

def cross_check(payload,phase):
    o=call_openai(payload,phase)
    g=call_gemini(payload,phase)
    available=[n for n,v in (("OPENAI",o),("GEMINI",g)) if v and not v.startswith(n+"_ERROR:")]
    return {
        "status":"DUAL_AI_AVAILABLE" if len(available)==2 else "SINGLE_AI_AVAILABLE" if len(available)==1 else "NO_AI_AVAILABLE",
        "available_models":available,
        "openai_analysis":o,
        "gemini_analysis":g
    }
