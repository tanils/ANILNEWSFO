"""Fresh market-news collection and materiality ranking."""

from __future__ import annotations
import hashlib, re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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
MAX_NEWS_AGE_HOURS = 72

def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (value or "").lower())).strip()

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

def _published_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except (TypeError, ValueError):
            return None

def _clean_summary(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", value).strip()

def _freshness_from_age(published: str, now: datetime) -> tuple[str, float | None]:
    dt = _published_dt(published)
    if not dt:
        return "unknown", None
    age_hours = max(0.0, (now - dt).total_seconds() / 3600)
    if age_hours <= 24:
        return "new", round(age_hours, 1)
    if age_hours <= MAX_NEWS_AGE_HOURS:
        return "recent", round(age_hours, 1)
    return "stale", round(age_hours, 1)

LOW_VALUE_PATTERNS = ("share price highlights", "share price history", "stock price history", "market wrap", "top gainers and losers")

def _news_type(title: str, summary: str) -> str:
    text = _norm(f"{title} {summary}")
    if any(term in text for term in LOW_VALUE_PATTERNS): return "low_value"
    if any(term in text for term in HIGH_IMPACT_TERMS): return "catalyst"
    return "context"

def collect_fresh_news(limit: int=40) -> list[dict[str,Any]]:
    dedup={}; now=datetime.now(timezone.utc); fetched_at=now.isoformat()
    for source,url in FEEDS.items():
        try: parsed=feedparser.parse(url)
        except Exception: continue
        for entry in getattr(parsed,"entries",[]):
            title=str(getattr(entry,"title","") or "").strip()
            summary=_clean_summary(str(getattr(entry,"summary","") or "").strip())
            link=str(getattr(entry,"link","") or "").strip()
            if not title: continue
            published=_published(entry)
            freshness, age_hours = _freshness_from_age(published, now)
            if freshness == "stale": continue
            key=hashlib.sha1(_norm(title).encode()).hexdigest()
            symbols=_symbols(f"{title} {summary}"); score=_materiality(title,summary,symbols)
            item={"headline":title,"summary":summary[:1200],"source":source,"url":link,"published":published,"symbols":symbols,"materiality_score":score,"news_type":_news_type(title, summary),"fetched_at":fetched_at,"freshness":freshness,"age_hours":age_hours}
            if key not in dedup or score>dedup[key]["materiality_score"]: dedup[key]=item
    items=list(dedup.values())
    # Keep catalysts first, then useful market context; suppress generic stock-page articles.
    items=[x for x in items if x.get("news_type") != "low_value"]
    return sorted(items,key=lambda x:(x.get("news_type")=="catalyst", x["materiality_score"], -(x.get("age_hours") if x.get("age_hours") is not None else 999999)),reverse=True)[:limit]

def build_ai_payload(news:list[dict[str,Any]],phase:str)->dict[str,Any]:
    return {"phase":phase,"generated_at_utc":datetime.now(timezone.utc).isoformat(),"items":news}
