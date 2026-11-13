# TEL99 — Passation Smart View détaillée — 13 novembre 2026, 15:42 UTC

> **Archive additive.** Ne pas écraser la passation initiale `PASSATION_SMART_VIEW_2026-11-13.md`, ni les règles, widgets, historiques, workflows ou évaluations TEL99. Ce document transcrit le dernier rapport fourni par Smart View via l'utilisateur. Aucun résultat n'a été vérifié indépendamment ici. Aucun ordre réel ou simulé. Aucun observateur à modifier. L'état du 13/11 est historique et non une recommandation actuelle.

## Inventaire exact annoncé : 21 widgets (20 rendus, 1 vide selon Smart View)
| # | ID | Type | Symbole / UT | Paramètres / données | État |
|---|---|---|---|---|---|
|1|hero|narrative_compare|KRAKEN:TELUSD|lens 4 états|Rendu IA|
|2|chart15|price_chart|TELUSD 15m|full, structure, levels, EMA20/50, VWAP, 400 barres|6 lignes|
|3|gauge|technical_gauge|TELUSD 15m/1h/4h/1D|rsi ma true|rendu|
|4|levels|key_levels|TELUSD 1h|volume levels true, 250 barres 03/11 06:00→13/11 15:00 UTC|rendu|
|5|smc|smc_zones|TELUSD 1h|1 zone|rendu limité|
|6|vprofile|volume_profile|TELUSD 1h|POC, VAH, VAL|3 lignes|
|7|snapshot|company_snapshot|TELUSD|qualité données|rendu|
|8|note|annotated_insight|TELUSD|lens 4 états|rendu IA|
|9|chart1h|price_chart|TELUSD 1h|structure, EMA20/50, 400 barres|1 ligne|
|10|chart4h|price_chart|TELUSD 4h|structure, EMA20/50, 400 barres|2 lignes|
|11|chart1d|price_chart|TELUSD 1D|structure, EMA20/50, 300 barres|1 ligne|
|12|ctx|comparison_table|BTCUSD/ETHUSD Kraken|technicals|2 lignes|
|13|w_vyh5kx|setup_stats|TELUSD 1D|rsi_oversold, 296 barres|n=5|
|14|w_h05m4d|correlation_matrix|TEL/BTC/ETH 1D|30 rendements|3 lignes|
|15|rulescan|rule_scan|TEL/BTC/ETH 15m|2 setups, 11 conditions, limit 3|3 lignes de prix, **aucun booléen de règle**|
|16|patterns|pattern_scan|TELUSD 1h|limit 10|0 ligne, degraded=no_rows|
|17|season|seasonality|TELUSD 1M|years 5|1 année, aucune complète|
|18|news|news_sentiment|TEL/BTC/ETH|TV news|3 lignes, aucun titre TEL|
|19|watchlist|watchlist|liste 18763815|18 lignes|rendu|
|20|mkt|market_snapshot|crypto|—|DATA-EMPTY|
|21|alerts|my_alerts|TELUSD|compte|rendu|

**Correction documentaire :** la passation précédente évoquait 22 cartes, dont Notebook. Le dernier inventaire du schéma en compte **21 et ne contient pas Notebook**. Ne pas interpréter « 20 alimentés » comme « 20 utiles » : Rule Scan, Pattern Scanner, Seasonality et News sont partiels/inexploitables.

## Rule Scan — EXPRESSIONS EXACTES CONFIGURÉES, ÉVALUATION NON PROUVÉE
**Alerte précoce non confirmée** (side long, 15m), 6 conditions :
```pine
close > ta.ema(close, 20)
ta.ema(close, 20) > ta.ema(close, 50)
ta.rsi(close, 14) > ta.sma(ta.rsi(close, 14), 14)
ta.ema(close, 12) - ta.ema(close, 26) > ta.ema(ta.ema(close, 12) - ta.ema(close, 26), 9)
volume > 1.5 * ta.sma(volume, 20)
close > ta.vwap
```
**Invalidation à la clôture** (side short, 15m), 5 conditions :
```pine
close < ta.ema(close, 20)
ta.ema(close, 20) < ta.ema(close, 50)
ta.rsi(close, 14) < ta.sma(ta.rsi(close, 14), 14)
ta.ema(close, 12) - ta.ema(close, 26) < ta.ema(ta.ema(close, 12) - ta.ema(close, 26), 9)
close < ta.vwap
```
Rendu observé : 3 lignes de prix BTC 68570, ETH 1927.24, TEL 0.001455 ; **aucun vrai/faux par condition**, aucun horodatage de dernière évaluation. Ces expressions ne sont **pas** une stratégie validée, ni la preuve de l'exécution du scanner. La conjonction de 6 conditions peut être trop restrictive pour une alerte précoce : tester chaque facteur indépendamment et les délais.

## Paramètres techniques accessibles
- Pivots HH/HL/LH/LL : swings confirmés avec `n` barres à gauche/droite, **n inconnu**. BOS/CHoCH uniquement à la clôture au-delà du swing, respectivement dans/contre tendance.
- OB : dernière bougie opposée avant impulsion, seuil inconnu ; FVG : écart `high[i-2]` / `low[i]` non comblé, tolérance inconnue.
- EMA20/50 ; RSI14 et SMA(RSI14,14) ; MACD12/26/9 ; Stoch K14/D3 ; ADX/DMI14 ; ATR14 Wilder ; volume/SMA20, seuil 1.5 ; VWAP ancré UTC ; Fibonacci 0/38.2/50/61.8/78.6/100.
- Volume Profile : fenêtre 250 bougies 1h, value area 70 %, nombre de tranches **inconnu**.
- Corrélation : Pearson des rendements logarithmiques 1D, fenêtre 30.
- Score agrégé Technical Gauge : pondération **propriétaire inconnue**.
- Rappel : les valeurs historiques POC 0.001608, VAH 0.001725, VAL 0.001438 et résistances 0.001499/0.0015045/0.001524 ne sont **pas des seuils permanents**.

## Données quantitatives historiques (rapport Smart View)
- Setup Stats RSI14 croise sous 30 après >=30, 1D, 296 bougies 22/01–13/11/2026 : n=5, 2 succès à +5 bougies, 40 %, IC95 rapporté [11.8 %, 76.9 %], taux de base 37.8 %, rendement médian à +5 bougies -4.63 %. `low_sample:true`, `refused:true`. Dates et rendements individuels **non disponibles** ; aucune supériorité statistique démontrée.
- Corrélations 30 rendements 15/10–13/11 : BTC/ETH 0.924 ; TEL/BTC -0.046 ; TEL/ETH 0.038. Fenêtre insuffisante pour conclure à une décorrélation structurelle.
- Gauge 15:42 UTC : 15m Vente -0.224 (5 achats/9 neutres/12 ventes) ; 1h Neutre +0.067 ; 4h Neutre -0.042 ; 1D Vente -0.309 ; 1W Vente -0.40 ; 1M Vente -0.371. ADX 23.7/26.5/16.7/12.8/10.5/45.9 ; ATR% 15m 1.14 ; RSI 47.21 vs moyenne 58.19, croisement baissier 2 barres auparavant.
- SMC 1h : 1 OB haussier à -9.19 %. News : 0 titre TEL. Market Snapshot : DATA-EMPTY. Pattern Scanner : 0 hit sur 1 symbole ; pas preuve d'absence de pattern.

## Observateurs — preuve de NON fonctionnement effectif
- `w15` : bar close 15m, CHoCH+MACD+volume, `enabled=false`, dernier contrôle 13/11 15:33:35 UTC, `last_result=skipped_plan`, `fire_count=0`. Offre Essential : fréquence minimale 60 minutes.
- `w1h` : bar close 1h, invalidation sous swing low, `enabled=true`, dernier contrôle 15:21:32 UTC, prochain 16:00 UTC, `last_result=skipped_plan`, `fire_count=0`. Offre Essential : 5 observateurs simultanés max.
- Alertes déclenchées : 0 ; contrôles effectifs observés : 0 ; alertes manquées **non mesurables** ; livraison e-mail seulement. Ne pas affirmer que la surveillance fonctionne.

## Rebonds des 12–13 novembre : NON REJOUÉS
Smart View n'expose pas la série OHLCV 15m/1h barre par barre du 10/11 00:00 au 14/11 00:00 UTC, ni le volume par tranche de prix. Il faut rechercher ces données indépendamment dans Kraken et les archives TEL99, rejouer chronologiquement et mesurer délais/faux négatifs/faux positifs **sans fuite temporelle**. Ne pas affirmer que Kraken lui-même ne les possède pas.

## Critères PROPOSÉS, NON CODÉS, NON VALIDÉS
- Alerte précoce : CHoCH haussier 15m ET vol>=1.5 SMA20 ET RSI>SMA(RSI14,14) ET TEL surperforme BTC 3j.
- Confirmation : clôture 15m ET 1h > swing historique 0.001499 et ADX1h>25.
- Invalidation : clôture 1h < VAL historique 0.001438 puis swing historique 0.001401.
- Défaut : ATTENDRE.
**Ne jamais activer ces règles sans replay prospectif ; ne pas bloquer les alertes précoces sur les critères de risque d'un achat.** Les seuils de prix sont datés, jamais des constantes.

## Tests de conformité recommandés (et limites)
1. RSI14 Wilder sur 296 barres Kraken : rechercher 5 croisements sous 30, avec tolérance de définition et d'initialisation (pas une vérité garantie).
2. Pearson 30 rendements log TEL/BTC ≈ -0.046 (tolérance 0.01) si données/symboles/horodatages identiques.
3. POC/VAH/VAL ≈ 0.001608/0.001725/0.001438 sur 250 bougies 1h ; **ne pas imposer ±0.1 % comme identité garantie** puisque méthode de binning inconnue.
4. Rejouer les 11 expressions 15m sur TEL/BTC/ETH, produire booléens et timestamps ; impossible de comparer les booléens aux trois lignes Smart View car elles ne les contiennent pas.
5. ATR% 15m ≈ 1.14 sur le snapshot historique.

## Propriétaire / lacunes
Pondération gauge, classifieur IA quatre états, géométrie Pattern Scanner, sentiment IA news, moteur Rule Scan, détails pivots/OB/FVG, tranches du profil : non exportés. Historique individuel des cinq RSI, carnet Kraken, spread, profondeur, perp TEL : non disponibles dans Smart View ; ne pas inventer.

## Instructions obligatoires aux agents TEL99
1. Lire **les deux** passations datées, l'issue #60 et l'issue de continuité #61 ; inspecter le code et les tests existants AVANT toute modification.
2. Préserver intégralement les branches `codex/tel99-quant-terminal`, `tel99-live-data`, `tel99-evaluation-data`, les workflows et les journaux ; pas de force-push ni de refonte.
3. Ne pas remplacer les stratégies existantes par les expressions non validées de Smart View. Ajouter des expérimentations séparées avec versionnage et preuves.
4. Séparer `early_market_alert`, `market_confirmation`, `market_invalidation` et `risk_checked_buy`. Pas de faux « ACHAT CONFIRMÉ » sans spread/frais et RR net.
5. Évaluer les rebonds manqués et journaliser prospective 1h/4h/24h/7j ; pas de fuite temporelle ni de conclusion de performance sans échantillon.
6. Ne pas déployer sans tests et preuve d'actualisation automatique réelle. Aucun ordre réel ou paper order.
7. Pour les prochaines extractions Smart View : **nouveau fichier daté**, pas de remplacement de cette archive.
