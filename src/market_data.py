"""Public market-data fallback layer.

Uses Yahoo Finance for publicly accessible NSE quotes/options when available.
All values carry a source and availability flag; missing data is never guessed.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import math
import pandas as pd
import yfinance as yf

INDEX_TICKERS = {"NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK"}

def _ticker(symbol: str) -> str:
    return INDEX_TICKERS.get(symbol.upper(), f"{symbol}.NS")

def _technical(hist) -> dict[str, Any]:
    if hist.empty:
        return {}
    close = hist["Close"].astype(float)
    volume = hist["Volume"].astype(float)
    out: dict[str, Any] = {}
    for period in (20, 50, 200):
        if len(close) >= period:
            out[f"ema{period}"] = round(float(close.ewm(span=period, adjust=False).mean().iloc[-1]), 2)
    if len(close) >= 15:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi = 100 - (100 / (1 + rs))
        out["rsi14"] = round(float(rsi.iloc[-1]), 2) if rsi.iloc[-1] == rsi.iloc[-1] else None
        tr = pd.concat([
            hist["High"] - hist["Low"],
            (hist["High"] - hist["Close"].shift()).abs(),
            (hist["Low"] - hist["Close"].shift()).abs(),
        ], axis=1).max(axis=1)
        out["atr14"] = round(float(tr.rolling(14).mean().iloc[-1]), 2)
    if len(volume) >= 20:
        avg = volume.iloc[-21:-1].mean()
        out["volume_vs_20d_avg"] = round(float(volume.iloc[-1] / avg), 2) if avg else None
    out["previous_day_high"] = float(hist["High"].iloc[-2]) if len(hist) > 1 else None
    out["previous_day_low"] = float(hist["Low"].iloc[-2]) if len(hist) > 1 else None
    return out

def snapshot(symbol: str) -> dict[str, Any]:
    ticker = yf.Ticker(_ticker(symbol))
    result = {
        "symbol": symbol, "price": None, "previous_close": None, "volume": None,
        "average_volume": None, "change_pct": None, "source": "yfinance",
        "available": False, "fetched_at_utc": None, "technical": {}
    }
    try:
        hist = ticker.history(period="1y", auto_adjust=False)
        if hist.empty:
            return result
        last = hist.iloc[-1]
        price = float(last["Close"])
        prev = float(hist.iloc[-2]["Close"]) if len(hist) > 1 else None
        result.update({
            "price": price,
            "previous_close": prev,
            "volume": int(last["Volume"]) if last["Volume"] == last["Volume"] else None,
            "available": True,
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "technical": _technical(hist),
        })
        if prev:
            result["change_pct"] = round((price - prev) / prev * 100, 2)
        if len(hist) >= 21:
            result["average_volume"] = int(hist["Volume"].iloc[-21:-1].mean())
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result

def option_expiries(symbol: str) -> list[str]:
    try:
        return list(yf.Ticker(_ticker(symbol)).options)
    except Exception:
        return []

def _chain_rows(frame, spot: float | None) -> list[dict[str, Any]]:
    cols = [c for c in ("strike", "lastPrice", "bid", "ask", "volume", "openInterest", "impliedVolatility")
            if c in frame.columns]
    if not cols:
        return []
    rows = frame[cols].fillna(0).to_dict("records")
    for row in rows:
        row["spread"] = round(float(row.get("ask", 0)) - float(row.get("bid", 0)), 4)
    if spot and "strike" in frame.columns:
        rows.sort(key=lambda r: abs(float(r.get("strike", 0)) - spot))
        return rows[:31]
    return rows[:31]

def _chain_stats(calls: list[dict[str, Any]], puts: list[dict[str, Any]], spot: float | None) -> dict[str, Any]:
    call_oi = sum(float(x.get("openInterest", 0)) for x in calls)
    put_oi = sum(float(x.get("openInterest", 0)) for x in puts)
    call_vol = sum(float(x.get("volume", 0)) for x in calls)
    put_vol = sum(float(x.get("volume", 0)) for x in puts)
    call_max = max(calls, key=lambda x: float(x.get("openInterest", 0)), default=None)
    put_max = max(puts, key=lambda x: float(x.get("openInterest", 0)), default=None)
    return {
        "pcr_oi": round(put_oi / call_oi, 3) if call_oi else None,
        "total_call_oi": call_oi,
        "total_put_oi": put_oi,
        "total_call_volume": call_vol,
        "total_put_volume": put_vol,
        "highest_call_oi": call_max,
        "highest_put_oi": put_max,
        "spot": spot,
    }

def option_chain_summary(symbol: str, expiry: str | None = None) -> dict[str, Any]:
    result = {
        "symbol": symbol, "expiry": expiry, "available": False, "calls": [], "puts": [],
        "source": "yfinance", "fetched_at_utc": None, "stats": {}
    }
    try:
        t = yf.Ticker(_ticker(symbol))
        exp = expiry or (t.options[0] if t.options else None)
        if not exp:
            return result
        chain = t.option_chain(exp)
        spot = None
        try:
            spot = float(t.history(period="5d", auto_adjust=False)["Close"].iloc[-1])
        except Exception:
            pass
        calls = _chain_rows(chain.calls, spot)
        puts = _chain_rows(chain.puts, spot)
        result.update({
            "expiry": exp,
            "available": True,
            "calls": calls,
            "puts": puts,
            "stats": _chain_stats(calls, puts, spot),
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result
