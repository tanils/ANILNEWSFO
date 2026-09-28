"""End-to-end context-first market intelligence runner and Telegram delivery."""
from __future__ import annotations
import argparse, json, os
from pathlib import Path
import requests
from src.ai_crosscheck import cross_check
from src.event_memory import remember
from src.market_data import snapshot, option_chain_summary
from src.momentum_scanner import top_fno_movers, FALLBACK_FNO_UNIVERSE
from src.news_intelligence import build_ai_payload, collect_fresh_news

STATE_FILE = Path("data/news_intelligence_state.json")
APP_FEED_FILE = Path("data/app_feed.json")

# Liquid NSE F&O universe used for candidate discovery. The AI may reject every
# candidate; this is deliberately a discovery universe, not a recommendation list.
0
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
    """Score setup quality for shortlist selection; never means probability of profit."""
    news_score = max(
        (float(x.get("materiality_score", 0)) for x in news_items
         if symbol in (x.get("symbols") or [])),
        default=0,
    )
    technical = market.get("technical") or {}
    score = min(news_score * 1.5, 15.0)
    change = float(market.get("change_pct") or 0)
    score += min(abs(change) * 1.5, 12.0)
    volume_ratio = technical.get("volume_vs_20d_avg")
    if volume_ratio is not None:
        score += min(max(float(volume_ratio) - 1.0, 0.0) * 8.0, 12.0)
    price = market.get("price")
    ema20, ema50, ema200 = technical.get("ema20"), technical.get("ema50"), technical.get("ema200")
    # Directional structure is rewarded only when the supplied price/EMA
    # relationship is internally consistent; this score is not a win probability.
    direction_bonus = 0.0
    if price is not None and ema20 is not None and ema50 is not None:
        if change >= 0 and float(price) > ema20 > ema50:
            direction_bonus += 14.0
        elif change < 0 and float(price) < ema20 < ema50:
            direction_bonus += 14.0
        elif change >= 0 and float(price) > ema20:
            direction_bonus += 6.0
        elif change < 0 and float(price) < ema20:
            direction_bonus += 6.0
    if price is not None and ema200 is not None:
        if (change >= 0 and float(price) > ema200) or (change < 0 and float(price) < ema200):
            direction_bonus += 5.0
    score += min(direction_bonus, 19.0)
    rsi = technical.get("rsi14")
    if rsi is not None:
        if (change >= 0 and 50 <= float(rsi) <= 68) or (change < 0 and 32 <= float(rsi) <= 50):
            score += 8.0
    if technical.get("atr14") is not None:
        score += 5.0
    if technical.get("previous_day_high") is not None and technical.get("previous_day_low") is not None:
        score += 4.0
    available_fields = sum(x is not None for x in (
        market.get("price"), market.get("volume"), market.get("change_pct"),
        technical.get("atr14"), technical.get("rsi14"), technical.get("ema20"),
        technical.get("ema50"), technical.get("previous_day_high"), technical.get("previous_day_low"),
    ))
    score += min(available_fields, 10.0)
    return round(min(score, 100.0), 2)


def _market_cache(payload):
    news_items = payload.get("items", [])
    movers, mover_errors = top_fno_movers(limit_each=15)
    mover_map = {item["symbol"]: item for item in movers}
    mover_symbols = [item["symbol"] for item in movers]
    news_symbols = {
        symbol for item in news_items for symbol in (item.get("symbols") or [])
        if symbol and symbol not in {"MARKET", "SECTOR"}
    }
    discovery_symbols = list(dict.fromkeys(
        ["NIFTY", "BANKNIFTY"] + mover_symbols + list(news_symbols) + FALLBACK_FNO_UNIVERSE
    ))
    cache = {}
    for symbol in discovery_symbols:
        cache[symbol] = snapshot(symbol)
        if symbol in mover_map:
            cache[symbol]["mover"] = mover_map[symbol]

    ranked = sorted(
        ((symbol, market) for symbol, market in cache.items()
         if symbol not in {"NIFTY", "BANKNIFTY"} and market.get("available")),
        key=lambda pair: (
            1 if pair[0] in mover_map else 0,
            _candidate_score(pair[0], pair[1], news_items),
        ),
        reverse=True,
    )
    chain_symbols = ["NIFTY", "BANKNIFTY"]
    for symbol, _ in ranked[:5]:
        if symbol not in chain_symbols:
            chain_symbols.append(symbol)
    for symbol in chain_symbols:
        if symbol in cache:
            cache[symbol]["option_chain"] = option_chain_summary(symbol)

    payload["fno_movers"] = movers
    payload["fno_mover_errors"] = mover_errors
    payload["fno_candidate_universe"] = discovery_symbols
    payload["fno_option_candidates"] = [
        {
            "rank": rank,
            "symbol": symbol,
            "price": cache[symbol].get("price"),
            "change_pct": cache[symbol].get("change_pct"),
            "mover": cache[symbol].get("mover"),
            "technical": cache[symbol].get("technical"),
            "option_chain_available": bool(cache[symbol].get("option_chain", {}).get("available")),
            "setup_quality_score": _candidate_score(symbol, cache[symbol], news_items),
            "deep_chain_checked": symbol in chain_symbols,
        }
        for rank, (symbol, _) in enumerate(ranked[:5], 1)
    ]
    return cache
def _ai_evidence_payload(payload):
    """Keep the reasoning prompt compact enough for free AI provider limits."""
    evidence = dict(payload)
    evidence["items"] = payload.get("items", [])[:15]
    evidence["fno_movers"] = payload.get("fno_movers", [])[:30]
    market = payload.get("market_data") or {}
    allowed = {"NIFTY", "BANKNIFTY"} | {
        x.get("symbol") for x in payload.get("fno_option_candidates", [])[:5] if x.get("symbol")
    }
    compact = {}
    for symbol in allowed:
        data = market.get(symbol)
        if not data:
            continue
        item = {
            "symbol": symbol,
            "price": data.get("price"),
            "previous_close": data.get("previous_close"),
            "volume": data.get("volume"),
            "change_pct": data.get("change_pct"),
            "source": data.get("source"),
            "fetched_at_utc": data.get("fetched_at_utc"),
            "technical": data.get("technical"),
        }
        chain = data.get("option_chain")
        if isinstance(chain, dict):
            item["option_chain"] = {
                "expiry": chain.get("expiry"),
                "source": chain.get("source"),
                "fetched_at_utc": chain.get("fetched_at_utc"),
                "provider_timestamp": chain.get("provider_timestamp"),
                "stats": chain.get("stats"),
                "calls": (chain.get("calls") or [])[:9],
                "puts": (chain.get("puts") or [])[:9],
                "warning": chain.get("warning"),
            }
        compact[symbol] = item
    evidence["market_data"] = compact
    evidence["fno_candidate_universe"] = payload.get("fno_candidate_universe", [])[:20]
    evidence["fno_option_candidates"] = payload.get("fno_option_candidates", [])[:12]
    return evidence

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
        "Discovery pool: LIVE NSE F&O TOP 15 GAINERS + TOP 15 LOSERS. Deep F&O analysis covers the top 5 setup candidates plus NIFTY/BANK NIFTY.",
        "Setup-quality score is an evidence score, NOT a probability of profit.",
        "News freshness gate: only current/recent items up to 72 hours are used; older items are excluded.",
        "Each important item includes the report summary so the user can see key numbers/context.",
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
        summary = (item.get("summary") or "").strip()
        if summary:
            lines.append(f"📝 WHAT THE REPORT SAYS: {summary[:700]}")
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
    lines += ["━━━━━━━━━━━━━━━━━━", "🔥 TOP 5 SUPER-SETUP SCREEN"]
    for item in payload.get("fno_option_candidates", [])[:5]:
        status = "CHAIN READY" if item.get("option_chain_available") else "CHAIN UNAVAILABLE"
        score = item.get("setup_quality_score", 0)
        tier = "🔥 SUPER SETUP CANDIDATE" if float(score) >= 90 else "🟡 DEVELOPING CANDIDATE"
        lines.append(
            f"#{item.get('rank')} {item['symbol']}: ₹{item.get('price', 'n/a')} | "
            f"{item.get('change_pct', 0):+.2f}% | SCORE {score}/100 | {tier} | {status}"
        )
    lines.append("Only one qualified trade may be returned; if none clears all evidence gates, the result is NO TRADE.")

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
            "fno_mover_count": len(payload.get("fno_movers", [])),
            "fno_candidate_count": len(payload.get("fno_option_candidates", [])),
            "report": report,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def save_app_feed(phase, payload, result):
    """Write a public, secret-free feed consumed by the Android app."""
    APP_FEED_FILE.parent.mkdir(parents=True, exist_ok=True)
    news = []
    for item in payload.get("items", [])[:15]:
        news.append({
            "headline": item.get("headline", ""),
            "summary": (item.get("summary") or "")[:1200],
            "source": item.get("source", "Unknown"),
            "url": item.get("url", ""),
            "published": item.get("published", ""),
            "freshness": item.get("freshness", "unknown"),
            "news_type": item.get("news_type", "context"),
            "symbols": ", ".join(item.get("symbols") or ["MARKET/SECTOR"]),
        })

    fno = []
    market = payload.get("market_data") or {}
    for item in payload.get("fno_option_candidates", [])[:5]:
        symbol = item.get("symbol")
        chain = market.get(symbol, {}).get("option_chain") or {}
        stats = chain.get("stats") or {}
        calls = (chain.get("calls") or [])[:5]
        puts = (chain.get("puts") or [])[:5]
        option_summary = (
            f"Expiry: {chain.get('expiry', 'n/a')} | "
            f"PCR OI: {stats.get('pcr_oi', 'n/a')} | "
            f"Call OI: {stats.get('total_call_oi', 'n/a')} | "
            f"Put OI: {stats.get('total_put_oi', 'n/a')} | "
            f"Highest Call OI: {stats.get('highest_call_oi', 'n/a')} | "
            f"Highest Put OI: {stats.get('highest_put_oi', 'n/a')}"
        )
        fno.append({
            "rank": item.get("rank"),
            "symbol": symbol,
            "price": item.get("price"),
            "change_pct": item.get("change_pct"),
            "setup_quality_score": item.get("setup_quality_score"),
            "option_chain_available": item.get("option_chain_available", False),
            "expiry": chain.get("expiry"),
            "option_summary": option_summary,
            "calls": calls,
            "puts": puts,
            "chain_source": chain.get("source"),
            "chain_fetched_at_utc": chain.get("fetched_at_utc"),
            "chain_provider_timestamp": chain.get("provider_timestamp"),
            "chain_warning": chain.get("warning"),
        })

    analyses = [
        {"provider": x.get("provider", "AI"), "analysis": x.get("analysis", "")}
        for x in result.get("analyses", [])
    ]

    APP_FEED_FILE.write_text(
        json.dumps({
            "app_version": 1,
            "phase": phase,
            "generated_at_utc": payload.get("generated_at_utc"),
            "news": news,
            "fno_movers": payload.get("fno_movers", [])[:30],
            "fno_candidates": fno,
            "breakouts": [],
            "strategy": "top 15 F&O gainers + top 15 F&O losers -> catalyst + momentum + breakout + OI/options -> CE/PE or NO TRADE",
            "ai_analyses": analyses,
            "ai_status": result.get("status", "unknown"),
            "available_models": result.get("available_models", []),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run(phase):
    news = remember(collect_fresh_news())
    payload = dict(build_ai_payload(news, phase))
    payload["market_data"] = _market_cache(payload)
    result = cross_check(_ai_evidence_payload(payload), phase)
    report = final_report(phase, payload, result)
    save_state(phase, payload, result, report)
    save_app_feed(phase, payload, result)
    send_telegram(report)
    return report

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--phase", choices=["night", "pre_market", "live_scan", "final_session"], required=True)
    args = p.parse_args()
    print(run(args.phase))

if __name__ == "__main__":
    main()
