"""Public market-data fallback layer.

Uses Yahoo Finance for publicly accessible NSE quotes/options when available.
All values carry a source and availability flag; missing data is never guessed.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import yfinance as yf

INDEX_TICKERS = {"NIFTY":"^NSEI","BANKNIFTY":"^NSEBANK"}

def _ticker(symbol: str) -> str:
    return INDEX_TICKERS.get(symbol.upper(), f"{symbol}.NS")

def _technical(hist) -> dict[str, Any]:
    if hist.empty:
        return {}
    close=hist["Close"].astype(float)
    volume=hist["Volume"].astype(float)
    out={}
    for period in (20,50,200):
        if len(close)>=period:
            out[f"ema{period}"]=round(float(close.ewm(span=period,adjust=False).mean().iloc[-1]),2)
    if len(close)>=15:
        delta=close.diff()
        gain=delta.clip(lower=0).rolling(14).mean()
        loss=(-delta.clip(upper=0)).rolling(14).mean()
        rs=gain/loss.replace(0,float("nan"))
        rsi=100-(100/(1+rs))
        out["rsi14"]=round(float(rsi.iloc[-1]),2) if rsi.iloc[-1]==rsi.iloc[-1] else None
    if len(close)>=15:
        tr=__import__("pandas").concat([
            hist["High"]-hist["Low"],
            (hist["High"]-hist["Close"].shift()).abs(),
            (hist["Low"]-hist["Close"].shift()).abs(),
        ],axis=1).max(axis=1)
        out["atr14"]=round(float(tr.rolling(14).mean().iloc[-1]),2)
    if len(volume)>=20:
        out["volume_vs_20d_avg"]=round(float(volume.iloc[-1]/volume.iloc[-21:-1].mean()),2) if volume.iloc[-21:-1].mean() else None
    out["previous_day_high"]=float(hist["High"].iloc[-2]) if len(hist)>1 else None
    out["previous_day_low"]=float(hist["Low"].iloc[-2]) if len(hist)>1 else None
    return out

def snapshot(symbol: str) -> dict[str, Any]:
    ticker=yf.Ticker(_ticker(symbol))
    result={"symbol":symbol,"price":None,"previous_close":None,"volume":None,
            "average_volume":None,"change_pct":None,"source":"yfinance",
            "available":False,"as_of_utc":None,"technical":{}}
    try:
        hist=ticker.history(period="1y",auto_adjust=False)
        if hist.empty:return result
        last=hist.iloc[-1]; price=float(last["Close"])
        prev=float(hist.iloc[-2]["Close"]) if len(hist)>1 else None
        result.update({
            "price":price,"previous_close":prev,
            "volume":int(last["Volume"]) if last["Volume"]==last["Volume"] else None,
            "available":True,
            "as_of_utc":datetime.now(timezone.utc).isoformat(),
            "technical":_technical(hist),
        })
        if prev: result["change_pct"]=round((price-prev)/prev*100,2)
        if len(hist)>1:
            result["average_volume"]=int(hist["Volume"].iloc[-21:-1].mean()) if len(hist)>=21 else None
    except Exception as exc:
        result["error"]=f"{type(exc).__name__}: {exc}"
    return result

def option_expiries(symbol:str)->list[str]:
    try:return list(yf.Ticker(_ticker(symbol)).options)
    except Exception:return []

def option_chain_summary(symbol:str, expiry:str|None=None)->dict[str,Any]:
    result={"symbol":symbol,"expiry":expiry,"available":False,"calls":[],
            "puts":[],"source":"yfinance","as_of_utc":None}
    try:
        t=yf.Ticker(_ticker(symbol)); exp=expiry or (t.options[0] if t.options else None)
        if not exp:return result
        chain=t.option_chain(exp)
        for key,frame in (("calls",chain.calls),("puts",chain.puts)):
            cols=[c for c in ("strike","lastPrice","bid","ask","volume","openInterest","impliedVolatility") if c in frame.columns]
            result[key]=frame[cols].fillna(0).to_dict("records")[:80]
        result.update({"expiry":exp,"available":True,"as_of_utc":datetime.now(timezone.utc).isoformat()})
    except Exception as exc:
        result["error"]=f"{type(exc).__name__}: {exc}"
    return result
