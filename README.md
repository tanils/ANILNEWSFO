# ANILNEWSFO

AI-powered Indian market intelligence engine for news and F&O context.

## Architecture
- RSS-based fresh news collection and deduplication
- Materiality ranking
- Independent OpenAI + Gemini analysis
- FACT / MARKET OBSERVATION / AI INTERPRETATION separation
- Telugu-friendly trader reports
- Telegram delivery
- Scheduled GitHub Actions
- Persistent JSON state

## Required GitHub Actions secrets
- OPENAI_API_KEY
- GEMINI_API_KEY
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

Optional model overrides: OPENAI_MODEL and GEMINI_MODEL.

## Run locally
```bash
pip install -r requirements.txt
python -m src.market_intelligence --phase pre_market
```

The pipeline does not invent live prices, OI, option-chain values, earnings, targets or stop losses. News alone is not a CE/PE recommendation.
