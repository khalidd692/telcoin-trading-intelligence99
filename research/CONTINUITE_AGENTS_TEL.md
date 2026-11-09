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

Branch research/tel-discovery-unrestricted was created from main HEAD 05184036e9c4fcadf56fb3d2028a3e52997fbf13. It was last verified 2026-11-09 as 4 commits ahead and 1 commit behind main; the branch has diverged. Do not merge or rebase automatically. Inspect the one new main commit and reconcile only on this research branch after review, without modifying main. It contains:
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

## Session de reprise — 2026-11-09 01:52–01:53 UTC

### Contrôle du dépôt
- Lecture des trois fichiers de référence effectuée depuis `research/tel-discovery-unrestricted`.
- Comparaison GitHub vérifiée : branche divergée, 5 commits ahead et 2 behind `main` ; merge-base `05184036e9c4fcadf56fb3d2028a3e52997fbf13`, HEAD actuel de `main` `ce85a6fe9a47b3e69031b1d475cf6b41f40e5777`. Aucun merge/rebase et aucun changement de `main`.
- Aucun fichier de stratégie, board, alerte ou code moteur modifié pendant cette session.

### État TradingView/MCP observé
- MCP TradingView officiel accessible ; cotation KRAKEN:TELUSD `0.0014912 USD`, `update_mode=streaming`, variation affichée `-0.7719%` au moment de l'appel (2026-11-09 vers 01:52 UTC).
- OHLCV 4h : dernières barres retournées : 2026-11-08 20:00 UTC clôture 0.001500 ; barre 2026-11-09 00:00 UTC encore en formation, clôture provisoire 0.001477. Exclure cette dernière des calculs clôturés.
- Snapshot technique 4h : RSI14 44.18, ADX 35.12, EMA20 0.00155392, EMA50 0.00151127, MACD 0.00001588 sous signal 0.00003728, recommandation TradingView SELL.
- Snapshot technique 1h : RSI14 23.06, ADX 30.43, EMA20 0.00154456, EMA50 0.00156835, MACD -0.00002834 sous signal -0.00002154, recommandation SELL.
- Nouvelle vérification des pages intraday récentes : 1h, 5,000 barres de 2026-04-11 20:00 à 2026-11-09 01:00 UTC, 65 ruptures sur cette page, historique plus ancien disponible ; 15m, 5,000 barres de 2026-09-08 12:45 à 2026-11-09 01:45 UTC, 664 ruptures sur cette page, historique plus ancien disponible. Ces nombres de ruptures ne couvrent que les pages récentes observées et ne remplacent pas les totaux paginés consignés plus haut.
- Tentative de refresh des deux boards refusée : quota hebdomadaire à 100 %, zéro refresh restant, réinitialisation annoncée le 2026-11-13 vers 14:52 UTC. Les lectures de boards restent donc anciennes : radar 15m dernier refresh 2026-11-08 22:28:36 UTC ; repli 4h dernier refresh 2026-11-08 20:01:28 UTC. Ne pas présenter leurs signaux comme actuels.

### Paper broker — état vérifié
- Equity/cash : 997.50 USD sur 1,000 USD ; P&L réalisé -2.50 USD ; aucune position et aucun ordre en attente.
- Derniers fills : achat paper 33,500 TEL à 0.001680 le 2026-11-06 23:32 UTC ; stop exécuté à 0.00160546 le 2026-11-07 11:59 UTC. Aucun nouvel ordre ni aucune modification effectués pendant cette session.
- Politique lue : risque 0.25 % par trade, perte quotidienne 1 %, une position, levier max 1, cooldown 240 min, symbole autorisé KRAKEN:TELUSD, minimum R/R paper 1.51. Ce minimum reste une règle d'admission paper active ; il ne doit pas devenir un filtre universel de découverte.

### Boards et qualité du suivi
- Radar retournement 15m : 0 setup, 4 watch et 5 none sur la fenêtre de 14 jours ; 0 signal scoré. Les signaux récents sont non scorables et le volume par barre requis par la règle est indiqué indisponible dans la lecture du board.
- Repli 4h : 0 setup, 10 watch ; 0 signal scoré. Dernier plan lu (ancien) : entrée 0.00151475, stop 0.00145996, cible 0.001578, R/R 1.15 ; déclencheur de reprise EMA20 non satisfait. Les règles du board sont marquées unsettled. Aucun plan n'est une instruction d'ordre.

### Tests historiques automatiques MCP — fréquences, pas backtests de trading
Fenêtre demandée par le service : 1,000 barres, du 2026-05-26 au 2026-11-09, horizon 20 barres sauf gaps (intra-barre). Ces réponses ne modélisent ni entrée/exécution réaliste, ni stop, ni sizing, ni frais/slippage : aucune n'est une preuve d'avantage net.
- 4h `rsi_oversold` : 10/17 (58.8 %), baseline 38.9 %, IC95 36.0–78.4 %, médiane forward +1.20 %, faible échantillon.
- 4h `rsi_ma_cross_up` : 36/82 (43.9 %), baseline 38.9 %, IC95 33.7–54.7 %, médiane -0.77 %, 1 observation en attente.
- 4h `gap_up_fill` : 16/19 (84.2 %), IC95 62.4–94.5 %, médiane forward -0.08 %, baseline non fournie, faible échantillon ; définition = retour au close précédent pendant la même barre.
- 4h `bb_lower_reentry` : 30/30 succès, mais baseline 100 % également ; définition = retour de clôture à l'intérieur des bandes sous 20 barres. Pas de pouvoir discriminant établi.
- 4h `gap_down_fill` : 11/16 (68.8 %), IC95 44.4–85.8 %, médiane forward -0.78 %, baseline non fournie ; taux de seconde moitié 40 % (2/5), stabilité faible.
- Rappel résultats 1h déjà obtenus le 2026-11-08 : `rsi_oversold` 9/19 (47.4 %) vs baseline 38.3 %, médiane -0.31 % ; `rsi_ma_cross_up` 30/78 (38.5 %) vs baseline 38.3 %, médiane -0.85 % ; `bb_lower_reentry` 35/35 mais baseline 100 %.

### Conclusion de cette session
- Aucune stratégie nouvelle validée. Le test 4h RSI sous 30 est une fréquence de signal (n=17), pas la validation de la stratégie RSI<30 sous EMA50 (16 trades du screen précédent) ; ne pas confondre ces définitions.
- La réversion RSI 4h reste une piste de recherche à tester avec des règles d'entrée/sortie pré-enregistrées et des coûts réalistes ; l'IC est large et n=17.
- RSI cross-up 4h n'apporte pas d'avantage évident sur la baseline ; les gaps et BB reentry n'établissent pas une stratégie rentable.
- L'état des boards ne peut pas être actualisé avant le reset du quota. Le cours OHLCV/technique reste consultable directement via le MCP officiel, mais il ne remplace pas la lecture fraîche Smart View.

### Prochaine action concrète
1. Après reset du quota, rafraîchir les deux boards et relire leurs signaux/horodatages, sans modifier leurs règles.
2. Poursuivre l'exploration avec données OHLCV 4h clôturées et règles pré-enregistrées ; vérifier les coûts Kraken et slippage avant toute simulation nette.
3. Reprendre l'audit du moteur historique existant uniquement après inspection de ses fichiers/tests ; aucun résultat de moteur ni test logiciel n'a été exécuté pendant cette session.
4. Maintenir la séparation entre fréquences MCP, résultats exploratoires, simulation paper et validation OOS (100 trades minimum).


## Sweep multi-combinaisons — 2026-11-09

- Exécution d'un sweep local sur OHLCV TradingView via MCP, sans modifier stratégies, boards ou moteur du dépôt. Rapport complet : `research/EXPLORATION_MULTI_COMBINAISONS_2026-11-09.md`.
- 4h : 1,743 barres (2026-01-22 → 2026-11-09), 1 trou de 8h ; anomalie initiale et dernière bougie en formation exclues.
- 1h : 5,000 barres (2026-04-11 → 2026-11-09), 65 trous ; segmentation stricte : 19 segments >=80 barres, 3,550 barres retenues, 1,450 barres de segments courts écartées. 1D seulement 292 barres ; 1W 43 barres.
- Sweep brut 4h : 1,200 variantes (RSI/mean reversion, Donchian breakout, momentum, pullback). Sweep risque-contraint 4h : 2,400 variantes RSI avec risque max 0.25% equity/trade, exposition max 1x, coûts 0.70% et stress 1.40%. Sensibilité locale : 144 variantes, 96 avec n>=15, 43 positives à 0.70%, seulement 21 positives à 1.40%. Sweep 1h : 2,704 variantes (RSI, Stoch, CCI, Bollinger, momentum) ; aucun candidat >=30 trades dans les segments propres conservés.
- Aucun candidat robuste : RSI30 / SL1.5 ATR / TP3R / H12 (27 trades) PF 1.37 à 0.70%, 1.09 à 1.40%, mais holdout récent 6 trades PF 0.76, négatif. RSI30 / SL2.5 / TP3.5R / H16 (18 trades) PF 2.06 à 0.70%, 1.69 à 1.40%, mais holdout 5 trades PF 0.17, négatif. RSI40 cross / EMA20<EMA50 / SL1.5 / TP3R / H36 (36 trades) PF 1.33 à 0.70%, 1.08 à 1.40%, validation négative. Transfert RSI30 1h : 56 trades, PF 1.25 à 0.70% et 0.78 à 1.40%; holdout 18 trades PF 1.12 / 0.72.
- Les meilleurs résultats initiaux all-in ou avec R/R 1R sont rejetés : sizing incompatible avec risque 0.25% et/ou R/R paper minimum 1.51. Aucun candidat ne doit être activé en paper.
- Limitation majeure : historique TradingView consulté commence le 2026-01-22 en 4h/1D ; impossible de démontrer 100 trades OOS robustes avec cette profondeur seule. Le flux intraday 1h/15m comporte des trous et ne doit pas être interpolé.
- Suite : obtenir davantage d'historique propre, auditer le moteur de backtest du dépôt et poursuivre les familles non-RSI (Keltner, Donchian, failed breakouts, ATR compression/expansion, swing structure, volume, multi-timeframe) avec règles pré-enregistrées, coûts et validation OOS.


## Audit moteur historique — 2026-11-09

Audit statique enregistré dans [`research/AUDIT_MOTEUR_HISTORIQUE_2026-11-09.md`](AUDIT_MOTEUR_HISTORIQUE_2026-11-09.md). Constats prioritaires : `run_oos.py` et `check_causality.py` utilisent KuCoin/TEL-USDT, pas KRAKEN:TELUSD ; `history_store.coverage()` détecte les trous mais le chemin `load_timeframe` → `Bundle` → `engine` ne segmente pas les séries ; `engine.py` mesure la qualité prédictive d'un détecteur et n'est pas un simulateur complet de trades. Les tests existants utilisent des fixtures continues et ne couvrent pas le passage d'un horizon ou d'indicateurs à travers une rupture réelle. Aucun test n'a été exécuté pendant cet audit statique. Les cinq demandes TradingView historiques (`rq_3fbd24d7858c4e9e`, `rq_304062157ba54962`, `rq_81fc211a3a43405b`, `rq_4f665100b71f4f6a`, `rq_919a53432a114077`) ont été relues et sont toujours queued ; ne pas les dupliquer. Aucun code, stratégie, board, paper setting ou main modifié.


## Dépistage exploratoire 4H Kraken — 2026-11-09

Rapport : [`research/EXPLORATION_SIGNAL_KRAKEN_4H_2026-11-09.md`](EXPLORATION_SIGNAL_KRAKEN_4H_2026-11-09.md). 1,500 bougies TradingView KRAKEN:TELUSD, 2026-03-05 → 2026-11-09. Dépistage brut des règles RSI<30, croisement RSI30, reclaim EMA20, balayage de plus bas, EMA20>EMA50. Résultats instables selon la tranche récente : RSI<30 +2.17% brut à 12 barres globalement mais -2.02% sur la tranche récente ; reclaim EMA20 -0.78% global mais +1.80% récent ; pattern sweep/reclaim -1.42% global et -4.81% récent. Ce n'est pas un backtest de portefeuille : pas de coûts/exécution/stops/sizing, événements chevauchants, holdout non scellé, dernière bougie possiblement en formation. Aucune règle validée, aucun paper setting ni code de production modifié. Prochaine étape : protocole causal sur clôtures et segmentation, puis interaction 4H régime × 1H déclencheur × 15m timing. Kraken OHLC REST limité à 720 points ; historique plus long à reconstruire depuis Trades, selon FAQ Kraken.


## Backtest exploratoire direct TradingView — 2026-11-09
Rapport : [`research/BACKTEST_EXPLORATOIRE_DIRECT_TV_KRAKEN_4H_2026-11-09.md`](BACKTEST_EXPLORATOIRE_DIRECT_TV_KRAKEN_4H_2026-11-09.md). Contournement de la file de recherche par récupération OHLCV directe MCP : 1 748 barres 4h de KRAKEN:TELUSD (2026-01-22 → 2026-11-09), une rupture 8h exclue localement et une mèche initiale extrême signalée. Simulation causale : entrée à l'ouverture suivante, stop structurel sous le plus bas des 5 dernières barres moins 0,05 ATR, cible 1,5R, expiration 20 barres, trades non chevauchants, stop prioritaire si stop et cible touchés dans la même barre, coûts hypothétiques 0,70% et stress 1,40% A/R, IS/OOS chronologique 70/30. Le croisement RSI14 au-dessus de 30 ressort à 22 trades, moyenne nette +1,786% / PF 2,14 à 0,70% de coûts et +1,086% / PF 1,60 à 1,40%, mais seulement 6 trades OOS et drawdown -18,7% à -21,98% : exploration insuffisante, aucun signal validé. Sweep/reclaim 10 barres : 55 trades, moyenne nette -0,348% / PF 0,82 à 0,70% ; Bollinger reentry : 41 trades, moyenne +0,204% / PF 1,13 à 0,70%, négative à 1,40% ; breakout Donchian 20 + volume : 8 trades, moyenne -2,298% à 0,70%. Aucun changement production/paper/boards/ordres. Quote au contrôle : 0,0014932 USD, update_mode streaming ; 4h TradingView rating SELL (ADX 26, RSI 46), daily SELL (RSI 46,97). Les frais/slippage restent des scénarios, pas des coûts Kraken vérifiés. Les 5 demandes TradingView restent queued ; aucune duplication.


## Exploration simultanée multi-signaux / multi-timeframes — 2026-11-09
Rapport : [`research/EXPLORATION_SIMULTANEE_MULTI_SIGNaux_TF_2026-11-09.md`](EXPLORATION_SIMULTANEE_MULTI_SIGNaux_TF_2026-11-09.md). Nouvelle passe parallèle sur KRAKEN:TELUSD : 4h (1 748 barres, 1 trou), 1h (5 000 barres, 64 trous, 18 segments >=80 barres, 3 481 retenues) et 15m (5 000 barres, 656 trous, seulement 318 barres dans 3 segments >=80). En 4h, certains filtres RSI + EMA200/EMA20>EMA50 semblent prometteurs en screening mais seulement 4–7 trades OOS et nombreuses variantes testées ; pas de validation. RSI-cross-SMA non filtré : 91 trades, moyenne +1,075% à 0,70% hypothétique, +0,375% à 1,40%, 29 OOS. 1h segmenté : RSI30 26 trades +0,332% PF1.32 ; Donchian20 10 trades +2,15% PF2.22, insuffisant ; sweep, BB, EMA20 pullback majoritairement négatifs. 15m inutilisable pour conclure faute de barres propres. Huit tests historiques TradingView immédiats supplémentaires : RSI oversold 1h horizon12 (21 événements, 57.1%, base 40.1%, médiane +0.41%) ; RSI cross-up 1h (79, 44.3%, base40.1%, médiane -0.21%) ; BB reentry 1h/4h 100% mais base rate 100%, aucune discrimination ; gaps 1h/4h avec taux variables et médianes quasi nulles/négatives ; RSI cross-up 4h (82, 40.2%, base37.4%, médiane -1.29%). Snapshot 2026-11-09 20:25 UTC : prix 0.0014919 ; 15m BUY, 1h NEUTRAL, 4h SELL, 1D SELL ; rebond court terme contre tendance supérieure baissière. Les 5 demandes en file n'ont pas été dupliquées. Aucun changement production/paper/boards/ordres.
