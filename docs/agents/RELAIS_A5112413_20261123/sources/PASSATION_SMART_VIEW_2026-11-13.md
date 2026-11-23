# TEL99 — Passation Smart View — 13 novembre 2026

> DOCUMENT DE RÉFÉRENCE POUR TOUS LES AGENTS. Documentation additive : **ne pas reconstruire TEL99, ne pas écraser le code, les règles, les données, les widgets ou les journaux existants**. Aucun ordre réel ni simulé. Vérifier l'état actuel du dépôt avant toute modification. Les valeurs ci-dessous sont des instantanés historiques, jamais des seuils permanents. Distinction stricte entre observation, déclaration Smart View, hypothèse et validation.

## Sources et branches
- Produit : https://tel99-quant-terminal.skkly.chatgpt.site/#market
- JSON public : https://tel99-quant-terminal.skkly.chatgpt.site/data.json
- Dépôt : https://github.com/khalidd692/telcoin-trading-intelligence99
- Branche produit : `codex/tel99-quant-terminal` ; données : `tel99-live-data` ; évaluations : `tel99-evaluation-data` ; workflows : `main`.
- Smart View : https://alpha.tradingview.com/dashboards/9f6534d9-4eb8-4ded-a6ca-b694fb98dfd3
- Incident rebonds manqués : issue #60.
- Source : dossier transmis par l'utilisateur, audit Smart View du 13/11/2026 15:42 UTC, inspections TinyFish. Les 8 derniers ajouts sont **déclarés par Smart View et non revérifiés indépendamment**.

## Inventaire
12 widgets initiaux : Narrative Summary, Price Chart 15m/1h/4h/1D, Technical Gauge, Key Levels, SMC Zones, Volume Profile, Company Snapshot, Annotated Insight, Comparison Table BTC/ETH.
2 widgets ajoutés par TinyFish et observés : Setup Stats, Correlation Matrix.
8 widgets supplémentaires déclarés ajoutés par Smart View : Rule Scan, Pattern Scanner, Seasonality, News, Watchlist, Market Snapshot, Notebook, My TV Alerts. **Total déclaré : 22** ; ne pas supposer que les cartes sont alimentées.

## État réel des widgets (13/11/2026 15:42 UTC)
| Widget | État | Preuves et limites |
|---|---|---|
| Rule Scan | PARTIEL / NON VALIDÉ | 3 lignes BTC 68570, ETH 1927.24, TEL 0.001455, **aucune colonne de résultat de règle** ; évaluation des 6+5 conditions non prouvée. |
| Pattern Scanner | VIDE | `scanned:1, hits:0, degraded:no_rows` ; absence de détection sur un symbole, pas preuve d'absence de figure. |
| Setup Stats | FAIBLE ÉCHANTILLON | RSI(14) croise sous 30 en 1D, 296 barres 22/01–13/11/2026 ; n=5, succès 2/5 (40 %), IC95 rapporté [11.8,76.9] %, taux de base 37.8 %, médiane à +5 barres -4.63 % ; `low_sample:true`, `refused:true`. AUCUN avantage démontré. |
| Correlation Matrix | ALIMENTÉ | Pearson des rendements logarithmiques 1D, 30 observations 15/10–13/11 : BTC/ETH 0.924 ; TEL/BTC -0.046 ; TEL/ETH 0.038. Ne prouve aucune décorrélation structurelle ; BTC/ETH restent contexte, filtre à tester. |
| Volume Profile | ALIMENTÉ | POC 0.001608 (+11.52 %), VAH 0.001725 (+19.63 %), VAL 0.001438 (-0.27 %). |
| SMC Zones | PAUVRE | Un order block haussier à environ -9.19 %. |
| Technical Gauge | ALIMENTÉ | 15m Vente -0.224 (5 achats/9 neutres/12 ventes), 1h Neutre +0.067, 4h Neutre -0.042, 1D Vente -0.309, 1W Vente -0.40, 1M Vente -0.371 ; ADX 23.7/26.5/16.7/12.8/10.5/45.9 ; ATR% 15m 1.14 ; RSI 47.21 vs SMA(RSI) 58.19, croisement baissier 2 barres avant. Score agrégé propriétaire. |
| Key Levels | ALIMENTÉ | 250 bougies 1h du 03/11 06:00 au 13/11 15:00 UTC ; prix 0.0014419. |
| Seasonality | INEXPLOITABLE | Historique Kraken TELUSD depuis 2026, zéro année complète. |
| News | PARTIEL | 12 titres BTC/ETH, zéro titre Telcoin. |
| Market Snapshot | VIDE | `DATA-EMPTY` pour ce mode crypto. |
| Watchlist / My TV Alerts / Notebook | AFFICHÉS | Watchlist 18 lignes, alertes lues, notebook vide. |

## Formules indépendantes reproductibles depuis OHLCV
- RSI(14) Wilder : moyennes des gains/pertes lissées `(prev*13 + x)/14` ; `RSI=100-100/(1+RS)`. SMA(RSI,14) ; paramètres du board `rsi_period:14, ma_period:14`.
- MACD : EMA12 - EMA26 ; signal EMA9 ; histogramme différence ; `alpha=2/(n+1)`.
- Stochastique : `%K=100*(close-LL14)/(HH14-LL14)` ; `%D=SMA(%K,3)`.
- ATR14 : Wilder du True Range ; 15m rapporté 1.64152e-05, soit environ 1.14 % du prix.
- ADX/DMI14 : TR, +DM/-DM, lissage Wilder ; DI±=100*DM/ATR ; DX=100*abs(DI+-DI-)/(DI++DI-) ; ADX=Wilder(DX,14).
- VWAP crypto : somme(prix typique*volume)/somme(volume), ancré à 00:00 UTC.
- Volume relatif : volume / SMA(volume,20).
- Volume Profile : histogramme volume par tranches de prix ; POC tranche max ; Value Area 70 % autour POC. Approximation OHLCV ; les ticks permettent plus de précision.
- Corrélation : Pearson sur rendements log `ln(P_t/P_(t-1))`, 1D, fenêtre 30 ; tester 30/90/365 jours seulement si historique disponible.
- Setup Stats : événement = RSI14 clôture sous 30 après clôture >=30 ; succès = clôture supérieure 5 bougies plus tard ; taux de base = fréquence des clôtures plus hautes à +5 barres ; IC95 Wilson ou Clopper-Pearson (vérifier méthode exacte).
- Structure HH/HL/LH/LL : pivots confirmés avec n bougies à droite et gauche ; BOS = clôture au-delà swing dans sens tendance, CHoCH = clôture au-delà swing contre tendance. Ne jamais utiliser un pivot avant sa confirmation (anti look-ahead). n exact NON DOCUMENTÉ.
- SMC : OB dernière bougie opposée avant impulsion ; FVG gap entre high[i-2] et low[i] (ou inverse) ; taille d'impulsion et tolérance NON DOCUMENTÉES : approximation seulement.
- Niveaux : swings, Fibonacci 0/38.2/50/61.8/78.6/100 sur 250 bougies, fusion POC/VAH/VAL ; trendline régression pivots NON DOCUMENTÉE.

## Propriétaire / non exportable à l'identique
Score Technical Gauge agrégé (~26 lectures, pondération inconnue), synthèse IA 4 états, algorithme géométrique Pattern Scanner, sentiment IA des news, évaluateur Rule Scan. Les expressions Pine-like des règles (`ta.ema`, `ta.rsi`, `ta.sma`, `ta.vwap`, `ta.barssince`) sont potentiellement reproductibles **si les expressions exactes sont récupérées**.

## Critères PROPOSÉS, NON VALIDÉS, NE PAS ACTIVER EN PRODUCTION
- Alerte précoce : CHoCH haussier 15m ET volume >=1.5*SMA20 ET RSI>SMA(RSI,14) ET TEL surperforme BTC sur 3j.
- Confirmation : clôtures 15m ET 1h >0.001499 (swing historique), ADX 1h>25.
- Invalidation : clôture 1h <0.001438 (VAL historique), puis <0.001401 (swing historique).
- Défaut : ATTENDRE.
**Attention :** conjonction trop restrictive pour détection précoce ; tester séparément les facteurs et les alertes, distinguer alerte de marché de décision d'achat. Niveaux 0.001499/0.001438/0.001401 datés, jamais coder en constantes permanentes.

## Rebond des 12–13 novembre
Smart View n'a pas fourni les bougies 15m/1h barre par barre ; impossible de valider son replay. Rechercher OHLCV Kraken 10/11 00:00 à 14/11 00:00 UTC et données archivées TEL99 ; rejouer chronologiquement sans fuite temporelle. Évaluer délai, rappel, faux positifs, rebonds non signalés selon définition pré-enregistrée.

## Alertes et liquidité
Watchers Smart View `skipped_plan`, Essential limite 5 watchers et fréquence horaire ; pas de garantie de surveillance 15m. Spread, profondeur et liquidité Kraken non fournis par ces widgets ; récupérer depuis source indépendante et horodater. TEL perp Kraken non prouvé ; ne pas inventer.

## Contrat de travail pour les agents TEL99
1. Lire ce document, l'issue #60, les branches et tests existants **avant toute modification** ; rechercher fonctions et widgets déjà implémentés. Ne pas reconstruire ni remplacer l'architecture.
2. Protéger les historiques, branches de données/évaluation, journal prospectif et règles actuelles ; changements minimaux, compatibles, additifs ; pas de force-push.
3. **Ne jamais assimiler carte présente à carte alimentée ni signal affiché à signal validé.** Ne pas activer Rule Scan tant que ses sorties sont invérifiables.
4. Séparer `market_early_alert`, `market_confirmation`, `market_invalidation`, `risk_checked_buy` ; absence de frais/spread/profondeur => jamais de confirmation d'achat inventée.
5. Rejouer les données historiques avec provenance et contrôles temporels, évaluer prospective 1h/4h/24h/7j ; conserver les faux négatifs et les raisons d'ATTENDRE.
6. Tester frais, spread, fraîcheur des données, qualité et RR net >=1.5 uniquement pour validation d'achat, pas comme verrou sur alertes précoces.
7. Tests et preuves avant tout déploiement ; aucune affirmation d'autonomie cloud sans exécutions planifiées observées PC éteint.
8. Aucun ordre réel ni simulé. Ne modifier aucun observateur Smart View.
9. À l'arrivée du rapport Copilot final, **ajouter un nouveau document daté** et lier celui-ci ; ne jamais écraser cette passation ni les recherches précédentes.
