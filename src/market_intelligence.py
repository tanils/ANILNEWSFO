"""End-to-end context-first market intelligence runner and Telegram delivery."""
from __future__ import annotations
import argparse, json, os
from pathlib import Path
import requests
from src.ai_crosscheck import cross_check
from src.event_memory import remember
from src.market_data import snapshot, option_chain_summary
from src.news_intelligence import build_ai_payload, collect_fresh_news

STATE_FILE = Path("data/news_intelligence_state.json")

# Liquid NSE F&O universe used for candidate discovery. The AI may reject every
# candidate; this is deliberately a discovery universe, not a recommendation list.
LIQUID_FNO_UNIVERSE = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK",
    "KOTAKBANK", "INDUSINDBK", "BAJFINANCE", "BAJAJFINSV", "SHRIRAMFIN",
    "LT", "TATAMOTORS", "M&M", "MARUTI", "TATASTEEL",
    "JINDALSTEL", "ADANIPORTS", "ADANIPOWER", "BEL", "BHARTIARTL",
    "INFY", "TCS", "WIPRO", "PERSISTENT", "HCLTECH",
    "SUNPHARMA", "LUPIN", "TRENT", "TITAN", "ITC",
]

def send_telegram(message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")
    for i in range(0, len(message), 3900):
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message[i:i + 3900]},
            timeout=30,
        )
        r.raise_for_status()

def _candidate_score(symbol: str, market: dict, news_items: list[dict]) -> float:
    news_score = max(
        (float(x.get("materiality_score", 0)) for x in news_items
         if symbol in (x.get("symbols") or [])),
        default=0,
    )
    move = abs(float(market.get("change_pct") or 0))
    # News relevance is weighted more than raw movement; movement alone cannot
    # create a trade setup.
    return news_score * 2.0 + min(move, 10.0)

def _market_cache(payload):
    news_items = payload.get("items", [])
    news_symbols = {
        symbol for item in news_items for symbol in (item.get("symbols") or [])
        if symbol and symbol not in {"MARKET", "SECTOR"}
    }
    discovery_symbols = list(dict.fromkeys(
        ["NIFTY", "BANKNIFTY"] + list(news_symbols) + LIQUID_FNO_UNIVERSE
    ))

    cache = {}
    for symbol in discovery_symbols:
        cache[symbol] = snapshot(symbol)

    # First pass: select liquid/active candidates using supplied news relevance
    # and observed price movement. Then fetch option chains only for the
    # shortlist to avoid hammering the public fallback provider.
    ranked = sorted(
        (
            (symbol, market)
            for symbol, market in cache.items()
            if symbol not in {"NIFTY", "BANKNIFTY"} and market.get("available")
        ),
        key=lambda pair: _candidate_score(pair[0], pair[1], news_items),
        reverse=True,
    )

    # Always include the indices; add the most relevant liquid stock candidates.
    chain_symbols = ["NIFTY", "BANKNIFTY"]
    for symbol, _ in ranked[:8]:
        if symbol not in chain_symbols:
            chain_symbols.append(symbol)

    for symbol in chain_symbols:
        if symbol in cache:
            cache[symbol]["option_chain"] = option_chain_summary(symbol)

    payload["fno_candidate_universe"] = discovery_symbols
    payload["fno_option_candidates"] = [
        {
            "symbol": symbol,
            "price": cache[symbol].get("price"),
            "change_pct": cache[symbol].get("change_pct"),
            "technical": cache[symbol].get("technical"),
            "option_chain_available": bool(cache[symbol].get("option_chain", {}).get("available")),
            "candidate_score": round(_candidate_score(symbol, cache[symbol], news_items), 2),
        }
        for symbol, _ in ranked[:12]
    ]
    return cache

def final_report(phase, payload, result):
    header = {
        "night": "🌙 NIGHT MARKET INTELLIGENCE",
        "pre_market": "🌅 PRE-MARKET INTELLIGENCE",
        "live_scan": "📡 LIVE MARKET INTELLIGENCE",
        "final_session": "🏁 FINAL SESSION INTELLIGENCE",
    }.get(phase, "📊 MARKET INTELLIGENCE")

    cache = payload.get("market_data") or _market_cache(payload)
    lines = [
        header,
        "━━━━━━━━━━━━━━━━━━",
        "📖 CONTEXT-FIRST NEWS + F&O ANALYSIS",
        "F&O candidate scan covers a liquid NSE universe plus NIFTY/BANK NIFTY.",
        "Only options with sufficient chain evidence can become qualified CE/PE setups.",
        "",
    ]

    for i, item in enumerate(payload.get("items", [])[:15], 1):
        symbols = item.get("symbols") or ["MARKET/SECTOR"]
        symbol = symbols[0]
        lines.extend([
            f"📰 SOURCE FACT #{i}",
            f"🏢 {', '.join(symbols)}",
            f"Headline: {item.get('headline', '')}",
            f"Source: {item.get('source', 'Unknown')}",
            f"Published: {item.get('published', 'Unknown')}",
            f"Freshness: {item.get('freshness', 'unknown')}",
        ])
        m = cache.get(symbol, {}) if symbol != "MARKET/SECTOR" else {}
        if m.get("available"):
            lines.append(
                f"Market: ₹{m.get('price')} | {m.get('change_pct', 0):+.2f}% | "
                f"Volume {m.get('volume', 'n/a')}"
            )
        else:
            lines.append("Market: unavailable")
        lines.append("")

    # Make the actual option-selection section visible even when an AI provider
    # is unavailable. It shows data availability, not a guessed recommendation.
    lines += ["━━━━━━━━━━━━━━━━━━", "🔎 F&O OPTION CANDIDATE SCAN"]
    for item in payload.get("fno_option_candidates", [])[:12]:
        status = "CHAIN READY" if item.get("option_chain_available") else "CHAIN UNAVAILABLE"
        lines.append(
            f"{item['symbol']}: ₹{item.get('price', 'n/a')} | "
            f"{item.get('change_pct', 0):+.2f}% | {status}"
        )

    analyses = result.get("analyses", [])
    if analyses:
        lines += ["━━━━━━━━━━━━━━━━━━"]
        for item in analyses:
            lines += [
                f"🤖 {item.get('provider')} — MASTER F&O ANALYSIS",
                item.get("analysis") or "Unavailable",
                "",
            ]
        if len(analyses) >= 2:
            lines += [
                "🔎 CROSS-CHECK",
                "Two independent AI analyses were generated. Compare factual agreement/disagreement; AI disagreement is not a trading signal.",
            ]
        else:
            lines += ["⚠️ Only one AI model was available for this run."]
    else:
        lines += [
            "━━━━━━━━━━━━━━━━━━",
            "⚠️ AI ANALYSIS UNAVAILABLE",
            "Source facts and F&O candidates were collected, but no configured AI provider responded.",
            "No CE/PE recommendation is generated without the required evidence.",
        ]
        if result.get("errors"):
            lines.append(
                "Provider errors: " + " | ".join(
                    f"{k}: {v}" for k, v in result["errors"].items()
                )
            )

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━",
        "📌 IMPORTANT",
        "News alone is not a CE/PE recommendation. Market data may be delayed or unavailable. "
        "Missing evidence is shown as unavailable rather than guessed.",
    ]
    return "\n".join(lines)

def save_state(phase, payload, result, report):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps({
            "phase": phase,
            "ai_status": result["status"],
            "available_models": result["available_models"],
            "generated_at_utc": payload["generated_at_utc"],
            "news_count": len(payload["items"]),
            "fno_candidate_count": len(payload.get("fno_option_candidates", [])),
            "report": report,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def run(phase):
    news = remember(collect_fresh_news())
    payload = dict(build_ai_payload(news, phase))
    payload["market_data"] = _market_cache(payload)
    result = cross_check(payload, phase)
    report = final_report(phase, payload, result)
    save_state(phase, payload, result, report)
    send_telegram(report)
    return report

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--phase", choices=["night", "pre_market", "live_scan", "final_session"], required=True)
    args = p.parse_args()
    print(run(args.phase))

if __name__ == "__main__":
    main()
