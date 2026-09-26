"""Trader-friendly context-first Telegram formatting."""
from __future__ import annotations

def _reaction(market:dict|None)->str:
    if not market or not market.get("available"):
        return "Market data unavailable"
    price=market.get("price")
    change=market.get("change_pct")
    volume=market.get("volume")
    parts=[]
    if price is not None: parts.append(f"Price ₹{price}")
    if change is not None: parts.append(f"Today {change:+.2f}%")
    if volume is not None: parts.append(f"Volume {volume:,}")
    return " | ".join(parts) if parts else "Market data unavailable"

def format_event(item:dict,market:dict|None=None)->str:
    symbols=", ".join(item.get("symbols",[])) or "MARKET / SECTOR"
    freshness=item.get("freshness","unknown")
    headline=item.get("headline","")
    return (
        f"🏢 {symbols}\n"
        f"📰 {headline}\n"
        f"⏰ Freshness: {freshness}\n"
        f"📈 Market data: {_reaction(market)}\n"
    )
