"""Evidence-based market reaction and trade-status helpers."""
from __future__ import annotations
from typing import Any
def reaction(snapshot:dict[str,Any])->str:
    if not snapshot.get("available"): return "MARKET_DATA_UNAVAILABLE"
    change=snapshot.get("change_pct")
    if change is None:return "MARKET_REACTION_UNAVAILABLE"
    if change>=2:return "STRONG_UP"
    if change<=-2:return "STRONG_DOWN"
    return "UP" if change>0 else "DOWN" if change<0 else "FLAT"
def contradiction(news_sentiment:str,snapshot:dict[str,Any])->bool:
    if not snapshot.get("available") or snapshot.get("change_pct") is None:return False
    change=snapshot["change_pct"]
    positive=news_sentiment.lower() in {"positive","bullish"}
    negative=news_sentiment.lower() in {"negative","bearish"}
    return (positive and change<0) or (negative and change>0)
def trade_status(*,evidence_ok:bool,market_data_ok:bool,contradiction_flag:bool)->str:
    if not evidence_ok:return "NO TRADE"
    if contradiction_flag:return "WAIT"
    if not market_data_ok:return "WAIT"
    return "TRADEABLE"
