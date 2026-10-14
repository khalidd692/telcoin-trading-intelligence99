# Telcoin Trading Intelligence

A read-only TEL/USDT market monitor. It collects public exchange data, calculates transparent indicators, checks data quality, and reports **SURVEILLER** or **ATTENDRE**.

## Safety rules
- No exchange credentials, account access, or order placement.
- Missing, stale, malformed, or inconsistent required data means **ATTENDRE**.
- **SURVEILLER is not a buy/sell instruction** and does not imply a profitable edge.
- Initial version monitors public market data only. News and sentiment are not yet integrated.
- No backtest results or profitability claims are included.

## Automation
GitHub Actions is scheduled for 7, 22, 37 and 52 minutes past each hour (approximately every 15 minutes; GitHub may delay scheduled runs). You can also run it manually from the Actions tab.

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