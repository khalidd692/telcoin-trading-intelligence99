# Telcoin Trading Intelligence

A read-only TEL/USDT market monitor. It collects public exchange data, calculates transparent indicators, checks data quality, and reports **SURVEILLER** or **ATTENDRE**.

## Safety rules
- No exchange credentials, account access, or order placement.
- Missing, stale, malformed, or inconsistent required data means **ATTENDRE**.
- **SURVEILLER is not a buy/sell instruction** and does not imply a profitable edge.
- Initial version monitors public market data only. News and sentiment are not yet integrated.
- No backtest results or profitability claims are included.

## Automation
GitHub Actions uses the cron schedule `*/15 * * * *` (at minutes 0, 15, 30 and 45 of each hour; GitHub may delay scheduled runs). You can also run it manually from the Actions tab.

Each run tests the indicator functions, collects public MEXC TEL/USDT ticker and 15-minute candles, checks the public KuCoin TEL-USDT price as an independent comparison, then publishes a short run summary and a downloadable JSON artifact.

## Indicators
EMA 12/26/50, RSI 14, ATR 14, candle age, and volume comparison. The current 15-minute candle is excluded from indicators.

## Statuses
- **ATTENDRE** — a required feed is missing/stale/invalid, spread is too wide, or exchange prices disagree.
- **SURVEILLER** — basic feed checks passed; this is not an entry signal.
- Errors fail closed to **ATTENDRE**.

## Run locally
Python 3.11+; no third-party packages required.
```bash
python -m unittest discover -s tests -v
python -m src.monitor --output report.json
```

This is decision-support software, not financial advice. It does not place orders and does not establish a trading edge.

## Multi-timeframe read-only analysis layer

The detailed collector already gathers closed OHLCV candles from MEXC and KuCoin for 15m, 1h, 4h, 1d, 1w and 1M. The deterministic analysis layer in `src/agent_analysis.py` reads the detailed snapshot and publishes `site/agent_analysis.json`.

It calculates EMA20/EMA50, RSI14, MACD histogram and relative volume per timeframe, then summarizes broad timeframe alignment and descriptive early-warning flags. It does not use the forming candle, does not infer a reversal from an oversold RSI, and never places orders. If the snapshot is stale, a timeframe is missing, or there is insufficient coherent history, the result is `ATTENDRE`. `SURVEILLER` means only that the data and analysis passed basic checks; it is not an entry instruction.

The JSON output is published alongside the existing report and detailed snapshot. Tests cover stale/missing data, duplicate candles, timeframe coverage and oversold conditions.
