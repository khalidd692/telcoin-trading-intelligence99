# TEL research continuity — agent handoff

Last updated: 2026-11-09
Repository: https://github.com/khalidd692/telcoin-trading-intelligence99
Active research branch: research/tel-discovery-unrestricted
Main branch: unchanged; do not merge or push to main without explicit permission.

## Read these first

1. research/RECHERCHE_ELARGIE_TEL_CADRE.md — scope, discovery framework, validation rules and safety boundaries.
2. research/RESULTATS_PRELIMINAIRES_4H.md — observed data coverage, anomalies, preliminary strategy screen and limitations.
3. Existing benchmark and engine files under scripts/strategy_backtest/ and results/strategy_validation/ are historical reference only; do not silently rewrite them.

## User mandate and non-negotiable boundaries

- Continue research autonomously and record every durable decision, result, defect, data limitation and next step here and in dated research notes.
- Instrument: KRAKEN:TELUSD only.
- Spot, long-only. Paper trading only. No real Kraken account access, no real orders, no automatic trading.
- No changes to TradingView Smart View boards, alerts, or existing strategy rules without explicit approval.
- No changes to main, no merge, no deployment, no deletion of project history without explicit approval.
- No invented data, backtest outcomes, costs, or claims of profitability.
- Keep discovery broad: do not use raw R/R >= 1.51 as a universal discovery filter. Report R/R; judge viability on net results, costs, drawdown, stability and out-of-sample evidence.
- Preserve paper safeguards: max virtual risk 0.25% per trade, max one position, daily loss cap 1%, cooldown after stop 240 minutes, no leverage. These are not discovery parameters to optimize.
- Distinguish hypothesis, exploratory result, incomplete test, and validated strategy.
- Do not claim autonomous subagents were launched. Notion agent discovery previously required a Business plan; use parallel tool workstreams where possible and report this limitation honestly.

## Current durable work

Branch research/tel-discovery-unrestricted was created from main HEAD 05184036e9c4fcadf56fb3d2028a3e52997fbf13. It is currently 3 commits ahead and 0 behind main (last verified 2026-11-09). It contains:
- research/RECHERCHE_ELARGIE_TEL_CADRE.md
- research/RESULTATS_PRELIMINAIRES_4H.md

No changes have been made to main.

## Data coverage and quality findings (TradingView MCP, 2026-11-09)

- 4h: 1,743 bars from 2026-01-22 12:00 UTC to 2026-11-09 00:00 UTC; one 8-hour timestamp gap. Excluding the potentially forming last bar leaves 1,742 bars through 2026-11-08 20:00 UTC.
- 1h: paginated and concatenated 6,779 bars from 2026-01-22 14:00 UTC to 2026-11-09 01:00 UTC; 166 gaps from the expected hourly cadence.
- 15m: paginated and concatenated 5,529 bars from 2026-09-01 00:00 UTC to 2026-11-09 01:15 UTC; 791 gaps from expected 15-minute cadence.
- Major OHLCV anomaly: first 1h candle at 2026-01-22 14:00 UTC has O=0.004400, H=0.020000, L=0.003929, C=0.004049, volume=30,402,785 TEL. Second-highest hourly high in the observed history is 0.004875; the anomalous high is not reflected in the corresponding 4h aggregate. Quarantine/exclude this bar from levels, ATR and signal calculations.
- 1h and 15m cannot be treated as continuous series. Segment at every timestamp gap; do not interpolate missing candles. Multi-timeframe tests remain blocked until data is cleaned and aligned on closed bars.
- TradingView data can be delayed depending on plan/subscription; last bar may be forming. Exclude incomplete bars.

## Preliminary strategy screen (exploratory only)

Using 4h closed candles, EMA20/EMA50, RSI14 and ATR14:
- Breakout Donchian20 + rising EMA50: 15 trades, mean net/trade -2.76%, gross PF 0.60.
- Breakout Donchian40 + rising EMA50: 7 trades, mean net/trade -0.55%, gross PF 1.03.
- EMA20 pullback in EMA20>EMA50 regime: 19 trades, mean net/trade -1.68%, gross PF 0.60.
- Mean reversion RSI<25 below EMA50: 8 trades, mean net/trade +6.62%, gross PF 11.62.
- Mean reversion RSI<30 below EMA50: 16 trades, mean net/trade +4.62%, gross PF 4.24.
- Momentum RSI>60 + EMA20>EMA50: 22 trades, mean net/trade +1.28%, gross PF 1.53.
Assumed round-trip cost was 0.70%; stress case 1.40%. These are hypotheses, not verified personal Kraken fees. First-screen code did not yet implement every paper broker guardrail and is not a full paper simulation.

RSI<30 rule: signal RSI14<30 and close<EMA50; entry next bar open; stop 2*ATR14; target 1.5R; exit RSI>50 or after 12 bars; one position; 0.70% round-trip cost.
Chronological split:
- Early 60%: 7 trades, 71.4% wins, mean net/trade +7.68%, gross PF 7.21, compounded net +63.6%.
- Validation 20%: 5 trades, 60.0% wins, mean net/trade +0.64%, gross PF 1.60, compounded net +2.4%.
- Recent holdout 20%: 4 trades, 75.0% wins, mean net/trade +4.18%, gross PF 4.49, compounded net +16.7%.
The holdout is not truly sealed: variants and thresholds were inspected in this exploratory pass. Four trades are far too few to infer edge. This is a research lead only, not a validated or paper-approved strategy.

## Next work — continue without asking the user to copy commands

1. Preserve raw TradingView responses and exact timestamps for 4h/1h/15m in a versioned dataset on this branch; compute hashes and provenance.
2. Clean 1h/15m by quarantining the anomalous candle and splitting into contiguous segments. Never interpolate.
3. Audit the existing backtest engine before reuse:
   - daily loss guard date/equity accounting;
   - phase runner resetting equity/cooldown/open position at phase boundaries;
   - future leakage/truncation tests for retest/pivot logic;
   - stop/target ordering, gap fills, fees/slippage, position sizing.
4. Add independent tests for causality, gap segmentation, incomplete bars, costs, and continuous walk-forward state.
5. Expand discovery families independently: mean reversion variants, failed breakouts, volatility compression/expansion, momentum, trend continuation, and cash/regime filters. Include simple baselines.
6. Pre-register parameters and cost assumptions before final holdout. Do not retune against holdout.
7. Simulate continuous state across phase boundaries, or exclude any entry whose lifecycle crosses a boundary. Do not reset equity or open-position state artificially.
8. Require adequate out-of-sample sample size (100 trades minimum for a robust-validation claim); if unavailable, report exploratory status.
9. Only after independent validation and explicit user approval consider a paper-broker test. Never connect real Kraken execution.

## Required handoff practice

At the end of each substantial work session:
- update this handoff with current branch/head, exact work done, files changed, raw data source and timestamp, test commands/results actually executed, known failures, and next concrete action;
- add a dated research result note rather than overwriting old results;
- verify the GitHub write and branch diff;
- keep the Notion project memory linked to this repository/branch.
Future agents must read this file and the two research documents before doing any work.