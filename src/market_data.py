"""Optional live market-data layer.

Uses Yahoo Finance for publicly accessible NSE quotes/options when available.
Every field is marked unavailable when the provider does not return it; the
engine never substitutes fabricated values.
"""
from __future__ import annotations
from typing import Any
import yfinance as yf

def snapshot(symbol: str) -> dict[str, Any]:
    ticker = yf.Ticker(f"{symbol}.NS")
    result={"symbol":symbol,"price":None,"previous_close":None,"volume":None,"average_volume":None,"change_pct":None,"source":"yfinance","available":False}
    try:
        hist=ticker.history(period="5d",auto_adjust=False)
        if hist.empty:return result
        last=hist.iloc[-1]; price=float(last["Close"]); prev=float(hist.iloc[-2]["Close"]) if len(hist)>1 else None
        result.update({"price":price,"previous_close":prev,"volume":int(last["Volume"]) if last["Volume"]==last["Volume"] else None,"available":True})
        if prev: result["change_pct"]=round((price-prev)/prev*100,2)
        if len(hist)>1: result["average_volume"]=int(hist["Volume"].iloc[:-1].mean())
    except Exception as exc:
        result["error"]=f"{type(exc).__name__}: {exc}"
    return result

def option_expiries(symbol:str)->list[str]:
    try:return list(yf.Ticker(f"{symbol}.NS").options)
    except Exception:return []

def option_chain_summary(symbol:str, expiry:str|None=None)->dict[str,Any]:
    result={"symbol":symbol,"expiry":expiry,"available":False,"calls":[],"puts":[]}
    try:
        t=yf.Ticker(f"{symbol}.NS"); exp=expiry or (t.options[0] if t.options else None)
        if not exp:return result
        chain=t.option_chain(exp)
        for key,frame in (("calls",chain.calls),("puts",chain.puts)):
            cols=[c for c in ("strike","lastPrice","volume","openInterest","impliedVolatility") if c in frame.columns]
            result[key]=frame[cols].fillna(0).to_dict("records")[:50]
        result.update({"expiry":exp,"available":True})
    except Exception as exc: result["error"]=f"{type(exc).__name__}: {exc}"
    return result
