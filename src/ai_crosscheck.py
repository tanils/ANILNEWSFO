"""Independent OpenAI + Gemini market intelligence cross-check."""
from __future__ import annotations
import json, os
from typing import Any
from openai import OpenAI
from google import genai
OPENAI_MODEL=os.getenv("OPENAI_MODEL","gpt-5-mini")
GEMINI_MODEL=os.getenv("GEMINI_MODEL","gemini-3.8-flash")
PROMPT="""You are a neutral Indian-market intelligence analyst. Analyze only supplied evidence. Never invent live price, volume, OI, option-chain, earnings, targets, stop losses or probabilities. Separate FACT, MARKET OBSERVATION, AI INTERPRETATION and TRADE ASSESSMENT. Explain cause -> business -> earnings/cost/order-book -> sector -> stock. Check freshness and priced-in only when evidence supports it. Check contradictions and alternative explanations. State what to watch and conditional invalidation. Trade status may only be TRADEABLE, WAIT, AVOID or NO TRADE. Never recommend a CE/PE contract from news alone. Prefer Telugu for trader-facing explanation."""
def build_prompt(payload:dict[str,Any],phase:str)->str:
    return f"{PROMPT}\n\nPHASE: {phase}\n{json.dumps(payload,ensure_ascii=False,indent=2)}"
def call_openai(payload,phase):
    key=os.getenv("OPENAI_API_KEY")
    if not key:return None
    try:
        r=OpenAI(api_key=key).responses.create(model=OPENAI_MODEL,input=build_prompt(payload,phase)); return (r.output_text or "").strip() or None
    except Exception as e:return f"OPENAI_ERROR: {type(e).__name__}: {e}"
def call_gemini(payload,phase):
    key=os.getenv("GEMINI_API_KEY")
    if not key:return None
    try:
        r=genai.Client(api_key=key).models.generate_content(model=GEMINI_MODEL,contents=build_prompt(payload,phase)); return (r.text or "").strip() or None
    except Exception as e:return f"GEMINI_ERROR: {type(e).__name__}: {e}"
def cross_check(payload,phase):
    o=call_openai(payload,phase); g=call_gemini(payload,phase); available=[n for n,v in (("OPENAI",o),("GEMINI",g)) if v and not v.startswith(n+"_ERROR:")]
    return {"status":"DUAL_AI_AVAILABLE" if len(available)==2 else "SINGLE_AI_AVAILABLE" if len(available)==1 else "NO_AI_AVAILABLE","available_models":available,"openai_analysis":o,"gemini_analysis":g}
