# TEL99 — Référence officielle TradingView Smart View (12 novembre 2026)

**Décision produit :** faire ressembler le terminal TEL99 existant au tableau TradingView Smart Search « TEL/USD — Radar de retournement précoce », visuellement ET fonctionnellement. Cette référence est destinée à tous les agents. Ne pas créer de troisième site ni de nouveau dépôt.

## Sources de vérité
- TradingView original : https://alpha.tradingview.com/dashboards/9f6534d9-4eb8-4ded-a6ca-b694fb98dfd3
- Audit TinyFish authentifié (lecture seule) : https://agent.tinyfish.ai/runs/1831271e-e0d2-4590-ac1d-e162d508cf3b
- Notion référence commune : https://app.notion.com/p/41635b7d665281009792d40745540b1f?pvs=204
- Terminal officiel : https://tel99-quant-terminal.skkly.chatgpt.site/#market
- Branche produit : `codex/tel99-quant-terminal` ; PR #58 déjà fusionnée, conserver l'existant.

## 12 cartes dans l'ordre TradingView
1. Synthèse / décision, confiance, invalidation, qualité des données
2. Structure 15m : chandeliers, swings, BOS/CHoCH, EMA20/50, VWAP, SMC
3. Lecture multi-unités : 3 jauges Oscillateurs/Résumé/Moyennes mobiles, sélecteur 15m/1h/4h/1D/1W/1M, tables détaillées
4. Niveaux et invalidation : Fibonacci, supports, résistances, swing high/low
5. Zones et structure 1h : FVG, order blocks, statut et distance
6. Profil de volume 1h : 8D, 60 bins, VAH/POC/VAL, histogramme
7. Fiche prix TEL/USD Kraken, sélecteur de période
8. Guide de lecture du radar et états de décision
9. Structure 1h
10. Confirmation 4h
11. Contexte 1D
12. Contexte BTC/ETH en tableau

## Exigences non négociables
- Design sombre soigné, cartes compactes et lisibles, sidebar repliable sur mobile, cartes pleine largeur, contrôles tactiles, zéro scroll horizontal ; pas de longues colonnes de texte ou chiffres illisibles.
- Conserver les widgets déjà livrés dans TEL99, ne corriger que les écarts. Comparer captures mobile 360–430px et desktop.
- Kraken TEL/USD primaire ; sources et timestamps visibles ; fraîcheur contrôlée ; pas de valeurs inventées. Les prix de l'audit TradingView sont HISTORIQUES et parfois incohérents entre cartes : ne jamais les recopier comme données courantes.
- Décision conditionnelle ACHAT PRÉCOCE / ACHAT CONFIRMÉ / ATTENDRE / INVALIDATION, niveaux d'entrée, stop, objectifs, frais/spread, RR net >=1.5, risques et qualité des données. En cas de données insuffisantes ou périmées : indiquer explicitement l'impossibilité de conclure.
- Aucun ordre réel ou paper ; lecture seule ; spot uniquement. Réserve long terme de 2M TEL intouchable. Budget de travail 1000 EUR, plafond de perte flottante 200 EUR pour scénarios.
- Backtests antérieurs : zéro trade admissible ; ne pas annoncer de stratégie validée.
- Déploiement sur terminal officiel uniquement après tests Python/JS, contrôles données, responsivité, actualisation automatique et preuves visuelles.

## Statut
Inspection TinyFish authentifiée réussie le 12/11/2026. Ceci est la référence de livraison, non une validation de conformité du terminal existant.
