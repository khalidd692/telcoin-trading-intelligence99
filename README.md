# Telcoin Trading Intelligence

A read-only TEL/USD market monitor using Kraken Spot public REST market-data endpoints. It calculates transparent indicators, validates data quality, and reports **SURVEILLER** or **ATTENDRE**.

## Safety rules
- Public market data only. No API keys, private/account endpoints, or order placement.
- Missing, stale, malformed, or inconsistent required data means **ATTENDRE**.
- Kraken Ticker REST does not provide a quote timestamp. The collector records this limitation and cross-checks ticker values against timestamped trades and the just-retrieved order-book snapshot.
- Order-book level timestamps describe price-level events, not the time of the whole REST snapshot.
- **TEL/USD is not TEL/USDT**. The monitor does not silently convert currencies or fall back to another quote currency.
- **SURVEILLER is not a buy/sell instruction** and does not imply a profitable edge.
- No backtest results or profitability claims are included.

## Public Kraken endpoints
The collector uses only:
- `GET /0/public/AssetPairs` — resolve the exact TEL/USD pair.
- `GET /0/public/Time` — Kraken server time for timestamp checks.
- `GET /0/public/Ticker` — last, bid and ask.
- `GET /0/public/Depth` — public L2 prices and quantities.
- `GET /0/public/Trades` — recent trades with timestamps.
- `GET /0/public/OHLC?interval=15` — 15-minute candles; the still-forming candle is excluded.

Requests are spaced to respect Kraken's published public API rate guidance. HTTP status codes are captured in the live smoke-test output. The live smoke test is required on pull requests; stale or invalid live data fails the check.

## Automation
GitHub Actions runs unit tests and dashboard checks on pull requests. On pull requests, a required public Kraken live smoke test validates API reachability and data freshness. Scheduled data collection and publication only occur on the default branch.

## Indicators
EMA 12/26/50, RSI 14, ATR 14, candle age, and volume comparison. The current 15-minute candle is excluded from indicators.

## Statuses
- **ATTENDRE** — a required feed is missing/stale/invalid, spread is too wide, or the source checks are incomplete.
- **SURVEILLER** — the available feed checks passed; this is not an entry signal.
- Errors fail closed to **ATTENDRE**.

## Run locally
Python 3.11+; no third-party packages required.
```bash
python -m unittest discover -s tests -v
python -m scripts.kraken_live_smoke
python -m src.monitor --output report.json
```

The live smoke command uses public endpoints only. If the network blocks DNS or HTTP access, it reports the failure and must not be interpreted as a live validation.

This is decision-support software, not financial advice. It does not place orders and does not establish a trading edge.
