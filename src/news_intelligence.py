"""Fresh market-news collection and materiality ranking."""

from __future__ import annotations
import hashlib, re
from datetime import datetime, timezone
from typing import Any
import feedparser

FEEDS = {
    "Economic Times Markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "Economic Times Stocks": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "Moneycontrol Latest": "https://www.moneycontrol.com/rss/latestnews.xml",
    "Moneycontrol Business": "https://www.moneycontrol.com/rss/business.xml",
}
HIGH_IMPACT_TERMS = ("order","contract","acquisition","merger","stake","results","profit","loss","guidance","approval","ban","penalty","rbi","sebi","government","tariff","duty","regulation","court","default","downgrade","upgrade","fraud","investigation","capex","dividend","buyback","funding","ipo","block deal","promoter","resignation","forecast","rate cut","rate hike","policy")
SYMBOL_MAP = {"reliance industries":"RELIANCE","hdfc bank":"HDFCBANK","icici bank":"ICICIBANK","state bank of india":"SBIN","axis bank":"AXISBANK","tata motors":"TATAMOTORS","tata steel":"TATASTEEL","tata power":"TATAPOWER","infosys":"INFY","persistent systems":"PERSISTENT","bel":"BEL","bharat electronics":"BEL","adani ports":"ADANIPORTS","adani power":"ADANIPOWER","lupin":"LUPIN","shriram finance":"SHRIRAMFIN","hfcl":"HFCL","nykaa":"NYKAA","pb fintech":"POLICYBZR","policybazaar":"POLICYBZR","hero motocorp":"HEROMOTOCO","bse":"BSE"}

def _norm(value: str) -> str:
    return re.sub(r"\\s+", " ", re.sub(r"[^a-z0-9]+", " ", (value or "").lower())).strip()

def _symbols(text: str) -> list[str]:
    normalized = _norm(text); found=[]
    for name, symbol in SYMBOL_MAP.items():
        if name in normalized and symbol not in found: found.append(symbol)
    return found

def _materiality(title: str, summary: str, symbols: list[str]) -> int:
    text=_norm(f"{title} {summary}"); score=1+min(sum(term in text for term in HIGH_IMPACT_TERMS),6)+(2 if symbols else 0)
    if any(term in text for term in ("fraud","ban","default","investigation","approval")): score += 1
    return min(score,10)

def _published(entry: Any) -> str:
    return str(getattr(entry,"published","") or getattr(entry,"updated","")).strip()

def collect_fresh_news(limit: int=40) -> list[dict[str,Any]]:
    dedup={}; fetched_at=datetime.now(timezone.utc).isoformat()
    for source,url in FEEDS.items():
        try: parsed=feedparser.parse(url)
        except Exception: continue
        for entry in getattr(parsed,"entries",[]):
            title=str(getattr(entry,"title","") or "").strip(); summary=str(getattr(entry,"summary","") or "").strip(); link=str(getattr(entry,"link","") or "").strip()
            if not title: continue
            key=hashlib.sha1(_norm(title).encode()).hexdigest(); symbols=_symbols(f"{title} {summary}"); score=_materiality(title,summary,symbols)
            item={"headline":title,"summary":re.sub(r"<[^>]+>"," ",summary).strip(),"source":source,"url":link,"published":_published(entry),"symbols":symbols,"materiality_score":score,"fetched_at":fetched_at}
            if key not in dedup or score>dedup[key]["materiality_score"]: dedup[key]=item
    return sorted(dedup.values(),key=lambda x:(x["materiality_score"],x["published"]),reverse=True)[:limit]

def build_ai_payload(news:list[dict[str,Any]],phase:str)->dict[str,Any]:
    return {"phase":phase,"generated_at_utc":datetime.now(timezone.utc).isoformat(),"items":news}
