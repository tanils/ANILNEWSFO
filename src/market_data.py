"""NSE-first market-data layer with Yahoo Finance fallback.

NSE is the primary source for F&O option-chain fields. Yahoo Finance remains
a fallback when NSE data cannot be obtained. Missing fields are never guessed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import math
import pandas as pd
import requests
import yfinance as yf

INDEX_TICKERS = {"NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK"}
NSE_BASE = "https://www.nseindia.com"
NSE_TIMEOUT = 12
_NSE_SESSION: requests.Session | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nse_session() -> requests.Session:
    global _NSE_SESSION
    if _NSE_SESSION is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{NSE_BASE}/",
            "Connection": "keep-alive",
        })
        try:
            s.get(NSE_BASE, timeout=NSE_TIMEOUT)
        except requests.RequestException:
            pass
        _NSE_SESSION = s
    return _NSE_SESSION


def _nse_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    response = _nse_session().get(f"{NSE_BASE}{path}", params=params, timeout=NSE_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("NSE response was not a JSON object")
    return data


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


def _snapshot_yahoo(symbol: str) -> dict[str, Any]:
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
            "fetched_at_utc": _utc_now(),
            "technical": _technical(hist),
        })
        if prev:
            result["change_pct"] = round((price - prev) / prev * 100, 2)
        if len(hist) >= 21:
            result["average_volume"] = int(hist["Volume"].iloc[-21:-1].mean())
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def snapshot(symbol: str) -> dict[str, Any]:
    """Use NSE for current quotes; fall back to Yahoo if NSE is unavailable."""
    result = {
        "symbol": symbol, "price": None, "previous_close": None, "volume": None,
        "average_volume": None, "change_pct": None, "source": "nse",
        "available": False, "fetched_at_utc": None, "technical": {}
    }
    try:
        if symbol.upper() in INDEX_TICKERS:
            data = _nse_get("/api/allIndices", {})
            row = next(
                (x for x in data.get("data", [])
                 if str(x.get("index", "")).upper() == symbol.upper()),
                None,
            )
            if row and row.get("last") is not None:
                result.update({
                    "price": float(row["last"]),
                    "previous_close": float(row["previousClose"]) if row.get("previousClose") is not None else None,
                    "change_pct": float(row["percentChange"]) if row.get("percentChange") is not None else None,
                    "available": True,
                    "fetched_at_utc": _utc_now(),
                })
                return result

        data = _nse_get("/api/quote-equity", {"symbol": symbol.upper()})
        price_info = data.get("priceInfo") or {}
        if price_info.get("lastPrice") is not None:
            result.update({
                "price": float(price_info["lastPrice"]),
                "previous_close": float(price_info["previousClose"]) if price_info.get("previousClose") is not None else None,
                "change_pct": float(price_info["pChange"]) if price_info.get("pChange") is not None else None,
                "volume": (data.get("marketDeptOrderBook") or {}).get("totalTradedVolume"),
                "available": True,
                "fetched_at_utc": _utc_now(),
            })
            try:
                hist = yf.Ticker(_ticker(symbol)).history(period="1y", auto_adjust=False)
                result["technical"] = _technical(hist)
                if len(hist) >= 21:
                    result["average_volume"] = int(hist["Volume"].iloc[-21:-1].mean())
            except Exception:
                pass
            return result
    except Exception as exc:
        result["nse_error"] = f"{type(exc).__name__}: {exc}"

    fallback = _snapshot_yahoo(symbol)
    if fallback.get("available"):
        fallback["fallback_reason"] = result.get("nse_error", "NSE quote unavailable")
    return fallback


def _normalise_nse_row(row: dict[str, Any], spot: float | None, option_type: str) -> dict[str, Any]:
    oi = row.get("openInterest")
    doi = row.get("changeinOpenInterest")
    volume = row.get("totalTradedVolume")
    bid = row.get("bidprice")
    ask = row.get("askPrice")
    ltp = row.get("lastPrice")
    strike = row.get("strikePrice")
    spread = round(float(ask) - float(bid), 4) if bid is not None and ask is not None else None
    return {
        "option_type": option_type,
        "strike": float(strike) if strike is not None else None,
        "lastPrice": float(ltp) if ltp is not None else None,
        "bid": float(bid) if bid is not None else None,
        "ask": float(ask) if ask is not None else None,
        "volume": int(volume) if volume is not None else None,
        "openInterest": int(oi) if oi is not None else None,
        "changeInOpenInterest": int(doi) if doi is not None else None,
        "impliedVolatility": float(row["impliedVolatility"]) if row.get("impliedVolatility") is not None else None,
        "change": float(row["change"]) if row.get("change") is not None else None,
        "spread": spread,
        "distance_from_spot": round(abs(float(strike) - spot), 4) if strike is not None and spot is not None else None,
        "source": "nse",
    }


def _chain_stats(calls: list[dict[str, Any]], puts: list[dict[str, Any]], spot: float | None) -> dict[str, Any]:
    call_oi = sum(float(x.get("openInterest") or 0) for x in calls)
    put_oi = sum(float(x.get("openInterest") or 0) for x in puts)
    call_vol = sum(float(x.get("volume") or 0) for x in calls)
    put_vol = sum(float(x.get("volume") or 0) for x in puts)
    return {
        "pcr_oi": round(put_oi / call_oi, 3) if call_oi else None,
        "total_call_oi": call_oi,
        "total_put_oi": put_oi,
        "total_call_volume": call_vol,
        "total_put_volume": put_vol,
        "total_call_change_oi": sum(float(x.get("changeInOpenInterest") or 0) for x in calls),
        "total_put_change_oi": sum(float(x.get("changeInOpenInterest") or 0) for x in puts),
        "highest_call_oi": max(calls, key=lambda x: float(x.get("openInterest") or 0), default=None),
        "highest_put_oi": max(puts, key=lambda x: float(x.get("openInterest") or 0), default=None),
        "spot": spot,
    }


def _chain_from_nse(symbol: str, expiry: str | None = None) -> dict[str, Any]:
    endpoint = "/api/option-chain-indices" if symbol.upper() in INDEX_TICKERS else "/api/option-chain-equities"
    data = _nse_get(endpoint, {"symbol": symbol.upper()})
    records = data.get("records") or {}
    spot = records.get("underlyingValue")
    rows = records.get("data") or []
    expiries = records.get("expiryDates") or []
    exp = expiry or (expiries[0] if expiries else None)
    if not exp:
        raise ValueError("NSE returned no option expiry")

    calls, puts = [], []
    for item in rows:
        if str(item.get("expiryDate", "")) != str(exp):
            continue
        for key, dest in (("CE", calls), ("PE", puts)):
            leg = item.get(key)
            if isinstance(leg, dict):
                dest.append(_normalise_nse_row(leg, float(spot) if spot is not None else None, key))

    key_fn = lambda x: x.get("distance_from_spot") if x.get("distance_from_spot") is not None else math.inf
    calls.sort(key=key_fn)
    puts.sort(key=key_fn)
    return {
        "symbol": symbol, "expiry": exp, "available": bool(calls or puts),
        "calls": calls[:31], "puts": puts[:31], "source": "nse",
        "fetched_at_utc": _utc_now(),
        "provider_timestamp": data.get("timestamp") or records.get("timestamp"),
        "stats": _chain_stats(calls, puts, float(spot) if spot is not None else None),
        "available_expiries": expiries,
    }


def _chain_rows(frame, spot: float | None) -> list[dict[str, Any]]:
    cols = [c for c in ("strike", "lastPrice", "bid", "ask", "volume", "openInterest", "impliedVolatility") if c in frame.columns]
    if not cols:
        return []
    rows = frame[cols].fillna(0).to_dict("records")
    for row in rows:
        row["spread"] = round(float(row.get("ask", 0)) - float(row.get("bid", 0)), 4)
        row["source"] = "yfinance"
    if spot and "strike" in frame.columns:
        rows.sort(key=lambda r: abs(float(r.get("strike", 0)) - spot))
    return rows[:31]


def _chain_from_yahoo(symbol: str, expiry: str | None = None) -> dict[str, Any]:
    t = yf.Ticker(_ticker(symbol))
    exp = expiry or (t.options[0] if t.options else None)
    if not exp:
        raise ValueError("Yahoo returned no option expiry")
    chain = t.option_chain(exp)
    spot = None
    try:
        spot = float(t.history(period="5d", auto_adjust=False)["Close"].iloc[-1])
    except Exception:
        pass
    calls, puts = _chain_rows(chain.calls, spot), _chain_rows(chain.puts, spot)
    return {
        "symbol": symbol, "expiry": exp, "available": True,
        "calls": calls, "puts": puts, "source": "yfinance",
        "fetched_at_utc": _utc_now(), "stats": _chain_stats(calls, puts, spot),
        "available_expiries": list(t.options),
        "warning": "Yahoo Finance fallback does not reliably provide change-in-OI.",
    }


def option_expiries(symbol: str) -> list[str]:
    try:
        endpoint = "/api/option-chain-indices" if symbol.upper() in INDEX_TICKERS else "/api/option-chain-equities"
        data = _nse_get(endpoint, {"symbol": symbol.upper()})
        expiries = (data.get("records") or {}).get("expiryDates") or []
        if expiries:
            return list(expiries)
    except Exception:
        pass
    try:
        return list(yf.Ticker(_ticker(symbol)).options)
    except Exception:
        return []


def option_chain_summary(symbol: str, expiry: str | None = None) -> dict[str, Any]:
    try:
        return _chain_from_nse(symbol, expiry)
    except Exception as nse_exc:
        try:
            result = _chain_from_yahoo(symbol, expiry)
            result["fallback_reason"] = f"NSE option chain unavailable: {type(nse_exc).__name__}: {nse_exc}"
            return result
        except Exception as yahoo_exc:
            return {
                "symbol": symbol, "expiry": expiry, "available": False,
                "calls": [], "puts": [], "source": "unavailable",
                "fetched_at_utc": _utc_now(), "stats": {},
                "error": f"NSE: {type(nse_exc).__name__}: {nse_exc}; Yahoo: {type(yahoo_exc).__name__}: {yahoo_exc}",
            }
