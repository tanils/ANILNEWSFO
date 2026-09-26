"""End-to-end market intelligence runner and Telegram delivery."""
from __future__ import annotations
import argparse,json,os
from pathlib import Path
from typing import Any
import requests
from src.ai_crosscheck import cross_check
from src.news_intelligence import build_ai_payload,collect_fresh_news
STATE_FILE=Path("data/news_intelligence_state.json")
def send_telegram(message:str)->None:
    token=os.getenv("TELEGRAM_BOT_TOKEN"); chat_id=os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id: raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")
    for i in range(0,len(message),3900):
        r=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",json={"chat_id":chat_id,"text":message[i:i+3900]},timeout=30); r.raise_for_status()
def final_report(phase,payload,result):
    header={"night":"🌙 NIGHT MARKET INTELLIGENCE","pre_market":"🌅 PRE-MARKET INTELLIGENCE","live_scan":"📡 LIVE MARKET INTELLIGENCE","final_session":"🏁 FINAL SESSION INTELLIGENCE"}.get(phase,"📊 MARKET INTELLIGENCE")
    lines=[header,f"AI status: {result['status']}","","FACT / SOURCE DATA:"]
    for item in payload["items"][:15]:
        symbols=", ".join(item["symbols"]) if item["symbols"] else "MARKET/SECTOR"; lines.append(f"• {symbols} | {item['headline']} | {item['source']} | materiality {item['materiality_score']}/10")
    lines += ["","GEMINI ANALYSIS:",result.get("gemini_analysis") or "Unavailable","","OPENAI ANALYSIS:",result.get("openai_analysis") or "Unavailable","","Live price/OI/option-chain confirmation is not supplied by this news-only pipeline. News alone is not a CE/PE signal."]
    return "\n".join(lines)
def save_state(phase,payload,result,report):
    STATE_FILE.parent.mkdir(parents=True,exist_ok=True); STATE_FILE.write_text(json.dumps({"phase":phase,"ai_status":result["status"],"available_models":result["available_models"],"generated_at_utc":payload["generated_at_utc"],"news_count":len(payload["items"]),"report":report},ensure_ascii=False,indent=2),encoding="utf-8")
def run(phase):
    news=collect_fresh_news(); payload=build_ai_payload(news,phase); result=cross_check(payload,phase); report=final_report(phase,payload,result); save_state(phase,payload,result,report); send_telegram(report); return report
def main():
    p=argparse.ArgumentParser(); p.add_argument("--phase",choices=["night","pre_market","live_scan","final_session"],required=True); args=p.parse_args(); print(run(args.phase))
if __name__=="__main__": main()
