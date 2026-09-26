"""Compact Telugu-friendly report formatting."""
from __future__ import annotations
def format_event(item:dict,market:dict|None=None)->str:
    symbols=", ".join(item.get("symbols",[])) or "MARKET/SECTOR"
    freshness=item.get("freshness","unknown")
    score=item.get("materiality_score","?")
    reaction=(market or {}).get("change_pct")
    reaction_text="unavailable" if reaction is None else f"{reaction:+.2f}%"
    return (f"📰 {symbols}\nHeadline: {item.get('headline')}\n"
            f"Source: {item.get('source')}\nFreshness: {freshness}\n"
            f"Materiality: {score}/10\nMarket reaction: {reaction_text}\n"
            f"Why care: AI analysis required for business/earnings impact.\n")
