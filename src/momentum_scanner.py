"""Live NSE F&O momentum discovery: top gainers and losers."""
from __future__ import annotations
from typing import Any
from src.market_data import _nse_get

FALLBACK_FNO_UNIVERSE = [
    "RELIANCE","HDFCBANK","ICICIBANK","SBIN","AXISBANK","KOTAKBANK",
    "INDUSINDBK","BAJFINANCE","BAJAJFINSV","SHRIRAMFIN","LT","TATAMOTORS",
    "M&M","MARUTI","TATASTEEL","JINDALSTEL","ADANIPORTS","ADANIPOWER",
    "BEL","BHARTIARTL","INFY","TCS","WIPRO","PERSISTENT","HCLTECH",
    "SUNPHARMA","LUPIN","TRENT","TITAN","ITC",
]

def _rows(value: Any) -> list[dict[str, Any]]:
    found = []
    if isinstance(value, dict):
        if value.get("symbol") and any(k in value for k in ("netPrice","pChange","percentChange","perChange","ltp")):
            found.append(value)
        for child in value.values():
            found.extend(_rows(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_rows(child))
    return found

def _pct(row: dict[str, Any]) -> float | None:
    for key in ("pChange","percentChange","perChange","netPrice"):
        try:
            if row.get(key) is not None:
                return float(str(row[key]).replace("%","").replace(",",""))
        except (TypeError, ValueError):
            pass
    return None

def _fetch(kind: str, limit: int) -> list[dict[str, Any]]:
    data = _nse_get("/api/live-analysis-variations", {"index": kind, "type": "FOSec"})
    unique = {}
    for row in _rows(data):
        symbol = str(row.get("symbol") or "").strip().upper()
        pct = _pct(row)
        if not symbol or symbol in {"NIFTY","BANKNIFTY"} or pct is None:
            continue
        unique[symbol] = {
            "symbol": symbol, "change_pct": pct,
            "direction": "GAINER" if kind == "gainers" else "LOSER",
            "source": "NSE F&O movers",
            "raw_rank": row.get("rank") or row.get("rankIndex"),
        }
    rows = sorted(unique.values(), key=lambda x: x["change_pct"], reverse=(kind == "gainers"))
    for rank, row in enumerate(rows[:limit], 1):
        row["mover_rank"] = rank
    return rows[:limit]

def top_fno_movers(limit_each: int = 15) -> tuple[list[dict[str, Any]], list[str]]:
    movers, errors = [], []
    for kind in ("gainers","losers"):
        try:
            movers.extend(_fetch(kind, limit_each))
        except Exception as exc:
            errors.append(f"{kind}: {type(exc).__name__}: {exc}")
    symbols = list(dict.fromkeys(x["symbol"] for x in movers))
    if not symbols:
        symbols = FALLBACK_FNO_UNIVERSE.copy()
    else:
        symbols.extend(x for x in FALLBACK_FNO_UNIVERSE if x not in symbols)
    return movers, errors
