"""End-to-end context-first market intelligence runner and Telegram delivery."""
from __future__ import annotations
import argparse,json,os
from pathlib import Path
import requests
from src.ai_crosscheck import cross_check
from src.event_memory import remember
from src.market_data import snapshot
from src.news_intelligence import build_ai_payload,collect_fresh_news
STATE_FILE=Path("data/news_intelligence_state.json")

def send_telegram(message:str)->None:
    token=os.getenv("TELEGRAM_BOT_TOKEN"); chat_id=os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")
    for i in range(0,len(message),3900):
        r=requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id":chat_id,"text":message[i:i+3900]},
            timeout=30
        )
        r.raise_for_status()

def _market_cache(payload):
    cache={}
    for item in payload.get("items",[]):
        for symbol in item.get("symbols",[])[:3]:
            if symbol not in cache:
                cache[symbol]=snapshot(symbol)
    return cache

def _ai_section(title,analysis):
    if not analysis:
        return f"{title}: Unavailable"
    if analysis.startswith(title.split()[0].upper()+"_ERROR:"):
        return f"{title}: Unavailable ({analysis})"
    return analysis

def final_report(phase,payload,result):
    header={
        "night":"🌙 NIGHT MARKET INTELLIGENCE",
        "pre_market":"🌅 PRE-MARKET INTELLIGENCE",
        "live_scan":"📡 LIVE MARKET INTELLIGENCE",
        "final_session":"🏁 FINAL SESSION INTELLIGENCE"
    }.get(phase,"📊 MARKET INTELLIGENCE")

    cache=_market_cache(payload)
    lines=[
        header,
        "━━━━━━━━━━━━━━━━━━",
        "📖 CONTEXT-FIRST NEWS ANALYSIS",
        "I will explain what happened, why it happened, who is affected, possible positive/negative effects, and what to watch next.",
        "Positive/negative is NOT decided from the headline alone.",
        ""
    ]

    # Compact source facts before the AI interpretation.
    for i,item in enumerate(payload.get("items",[])[:15],1):
        symbol=item.get("symbols",["MARKET/SECTOR"])[0]
        lines.extend([
            f"📰 SOURCE FACT #{i}",
            f"🏢 {', '.join(item.get('symbols',[])) or 'MARKET / SECTOR'}",
            f"Headline: {item.get('headline','')}",
            f"Source: {item.get('source','Unknown')}",
            f"Published: {item.get('published','Unknown')}",
            f"Freshness: {item.get('freshness','unknown')}",
        ])
        m=cache.get(symbol,{}) if symbol!="MARKET/SECTOR" else {}
        if m.get("available"):
            lines.append(f"Market: ₹{m.get('price')} | {m.get('change_pct',0):+.2f}% | Volume {m.get('volume','n/a')}")
        else:
            lines.append("Market: unavailable")
        lines.append("")

    if result.get("status")=="DUAL_AI_AVAILABLE":
        lines += [
            "━━━━━━━━━━━━━━━━━━",
            "🤖 OPENAI — CONTEXT ANALYSIS",
            result.get("openai_analysis") or "Unavailable",
            "",
            "━━━━━━━━━━━━━━━━━━",
            "🤖 GEMINI — INDEPENDENT CONTEXT ANALYSIS",
            result.get("gemini_analysis") or "Unavailable",
            "",
            "━━━━━━━━━━━━━━━━━━",
            "🔎 CROSS-CHECK",
            "Two independent AI analyses were generated. Read their factual agreement/disagreement; do not treat AI disagreement as a trading signal."
        ]
    elif result.get("status")=="SINGLE_AI_AVAILABLE":
        available=result.get("available_models",["AI"])[0]
        analysis=result.get("openai_analysis") or result.get("gemini_analysis") or "Unavailable"
        lines += [
            "━━━━━━━━━━━━━━━━━━",
            f"🤖 {available} — CONTEXT ANALYSIS",
            analysis,
            "",
            "⚠️ Only one AI model was available for this run."
        ]
    else:
        lines += [
            "━━━━━━━━━━━━━━━━━━",
            "⚠️ AI ANALYSIS UNAVAILABLE",
            "Source facts were collected, but no AI key/model responded. No trade interpretation is generated."
        ]

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━",
        "📌 IMPORTANT",
        "News alone is not a CE/PE recommendation. Market data may be delayed or unavailable. Missing evidence is shown as unavailable rather than guessed."
    ]
    return "\n".join(lines)

def save_state(phase,payload,result,report):
    STATE_FILE.parent.mkdir(parents=True,exist_ok=True)
    STATE_FILE.write_text(
        json.dumps({
            "phase":phase,
            "ai_status":result["status"],
            "available_models":result["available_models"],
            "generated_at_utc":payload["generated_at_utc"],
            "news_count":len(payload["items"]),
            "report":report
        },ensure_ascii=False,indent=2),
        encoding="utf-8"
    )

def run(phase):
    news=remember(collect_fresh_news())
    payload=build_ai_payload(news,phase)
    result=cross_check(payload,phase)
    report=final_report(phase,payload,result)
    save_state(phase,payload,result,report)
    send_telegram(report)
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--phase",choices=["night","pre_market","live_scan","final_session"],required=True)
    args=p.parse_args()
    print(run(args.phase))

if __name__=="__main__":
    main()
