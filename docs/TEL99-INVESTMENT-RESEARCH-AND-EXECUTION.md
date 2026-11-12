# TEL99 — Investment decision system / Hermes agent brief
Updated: 2026-11-12. Owner-approved research and product direction. This is a specification, not proof of deployed functionality.

## Objective
Build upon the existing TEL99 mobile terminal to support evidence-based timing for buying TEL, selling portions into strength and rebuying to increase TEL holdings while also realizing EUR profits. The investor has already chosen TEL as their preferred asset. Monitor material fundamental thesis-breakers, but do not block every timing decision on repeating a complete investment thesis. Never promise a rebound.

## Investor constraints (confirmed)
- Total currently available new capital: approximately **EUR 1,000**, **not** EUR 1,000 in addition to the previously discussed EUR 500.
- Tolerated aggregate **unrealized** drawdown: **EUR 200 across accumulation and swing combined**, corresponding to 20% of the EUR 1,000 envelope. Historical cold-storage TEL is excluded. This is a monitoring/review threshold, **not** a guaranteed loss cap, automatic stop, per-trade risk allowance or automatic authorization to average down.
- Flexible allocation between accumulation and swing; potential future weekly additions are variable, not committed.
- Swing horizon days to weeks. Prefer confirmed entries; take partial profits and potentially let the rest run. Do not automatically convert invalidated swings into long-term holds.
- Kraken Pro primary, compare actual total execution costs elsewhere when reliably supported.
- All orders are **proposals for manual user execution only**. No live or paper orders, transfers or credential handling by the agent.
- Preserve the TradingView global policy until explicitly changed: spot-only, mandatory technical stop for swing plans, max 0.25% risk per trade, minimum net reward/risk 1.51. The EUR 200 drawdown tolerance does not override these controls.

## Data source priority and coverage tests
1. Existing TradingView MCP: 15m/1h/4h/1D/1W OHLCV, structure, indicators, alerts, BTC/ETH and macro calendars.
2. Kraken **public** API: authoritative executable TEL/USD bid/ask, order book depth, trade prints, OHLCV, spread and slippage estimates. Do not conflate TEL/USD, TEL/EUR and TEL/USDT prices or reuse duplicated/stale cross-exchange quotes.
3. CoinMarketCap MCP and CoinGecko MCP: independently cross-check TEL circulating/max supply, market cap, exchange coverage, liquidity, distribution and global sentiment. Record source timestamps and inconsistencies.
4. Telcoin primary documents, regulator records, explorers, GitHub: verify banking status and scope, roadmap vs delivered product, team, security, token utility, token-holder concentration and actual token value capture.
5. DeFiLlama, GeckoTerminal, DEX Screener: TVL, pools, DEX liquidity, volumes and fees where TEL is actually supported.
6. Arkham and potentially Nansen: on-chain wallet labels, large holders, exchange flows, with explicit confidence and false-positive checks.
7. CoinGlass and optionally Glassnode/CryptoQuant: BTC/ETH derivatives, funding, liquidations and cycle context; verify TEL-specific market availability. Avoid paying for APIs before coverage and incremental value are demonstrated.
8. FRED, Federal Reserve, CME FedWatch and other primary macro sources: inflation, rates, dollar, liquidity, employment, economic-event risk; distinguish current values from forecast.
9. Dune, Messari, Token Terminal: optional only if TEL coverage and measurable incremental value justify integration.
Use free/public data first; check availability, quota, reliability, timestamp and legal terms. Never present untested tool coverage as established.

## Eight analysis dimensions
1. Team, execution and governance.
2. Product-market fit, actual adoption, differentiated utility and competitors.
3. Tokenomics, emissions, distribution, staking and especially **economic value captured by TEL token**, not merely Telcoin corporate success.
4. Technology, validators, code activity, audits, incidents.
5. Economic usage: users, transactions, revenue, fees, TVL, liquidity.
6. Licenses, regulation, partnerships verified independently, competitive risks.
7. Macro and market regime: Fed, CPI, liquidity, BTC/ETH, ETF, dominance, altcoin rotation, derivatives, sentiment.
8. Valuation scenarios plus 1W/1D/4h/1h technical timing, order-book depth and total trading costs.
Classify each important assertion as VERIFIED FACT, PROJECT CLAIM, HYPOTHESIS or PROJECTION; cite dated sources. No backtest edge claim without robust evidence.

## Operational decision engine
Produce separate **ACCUMULATION** and **SWING** verdicts: BUY CONFIRMED, BUY ON PULLBACK (conditional), SELL PARTIAL, REBUY, WAIT, or DO NOT BUY, as appropriate. For each actionable scenario give:
- Data as-of and freshness, venue and pair; confirmation conditions (including 4h close and volume), invalidation and expiry.
- Proposed manual order type (limit/market), USD price, estimated EUR budget, TEL quantity, estimated spread, maker/taker fees and slippage; use real verified account fees or label assumptions.
- Technical invalidation/stop for swing, TP1/TP2, percentage sold, remaining TEL and EUR profit estimate, net R/R and portfolio exposure/drawdown.
- Confidence with evidence and counter-evidence. No false precision; never force a trade just to avoid WAIT.
- If WAIT, always include specific monitored trigger levels and alternative scenarios.
- Recalculate price levels from current data. Previously recorded example levels are **not** standing orders.

## Delivery and integration
- Reuse existing repo, TEL99 terminal, Smart View board, data pipeline and mobile UI. Avoid unnecessary architectural rewrites.
- Do **not** block implementation on the pending TradingView strategy proposal. Use independent read-only analytics and price alerts now.
- Existing TradingView price-crossing alerts created on 2026-11-12 for KRAKEN:TELUSD: 0.001425 up (6056988239), 0.001510 up (6056988529), 0.001383 down (6056989265), 0.001310 down (6056989880). These are price-only, not validated 4h signals; verify activation and renewal before expiry around 2026-12-12.
- Add mobile-readable decision cards, manual order-plan calculator, partial profit and rebuy scenarios, combined EUR 200 unrealized drawdown monitor, timestamp and data-quality guards.
- Prove scheduled data refresh works with PC off before claiming autonomous operation. Test calculations and costs; fail closed on stale or contradictory feeds.
- No real or simulated order placement.

## Acceptance criteria
Evidence-backed TEL source-coverage matrix; reproducible multi-factor decision with separate accumulation/swing plans; executable-price/cost checks; risk and stale-data safeguards; mobile output; test evidence and deployment verification. Distinguish implemented from planned features in all reports.
