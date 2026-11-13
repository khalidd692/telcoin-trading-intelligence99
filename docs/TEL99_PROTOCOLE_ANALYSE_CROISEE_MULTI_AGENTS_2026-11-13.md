# TEL99 — Protocole permanent d'analyse croisée (13 novembre 2026)

## Mandat
Pour chaque demande de décision TEL, analyser des données indépendantes et fraîches, jamais un terminal TEL99 périmé. Faire converger analyse technique, marché crypto, dérivés, macro, fondamentaux et liquidité. Toujours séparer données vérifiées, hypothèses, lacunes et décision. Aucun ordre réel ou simulé.

## Périmètre complet
1. **TEL/USD Kraken** : cotation horodatée, 15m/1h/4h/1D/1W, bougies clôturées, EMA20/50, VWAP, RSI14, MACD, ATR, ADX, Bollinger, pivots, volumes, SMC/BOS/CHoCH, POC/VAH/VAL, supports/résistances, liquidité, spread et profondeur du carnet. Contrôler symboles et source.
2. **Marché crypto** : BTC, ETH, SOL, XRP, BNB, dominance BTC, TOTAL/TOTAL2/TOTAL3, corrélations TEL/BTC/ETH, volatilité, flux stablecoins, ETF, rotations sectorielles, sentiment, peur/avidité.
3. **Dérivés / flux** : open interest, funding, liquidations, long/short, flux d'exchanges, volumes spot vs dérivés; indiquer « indisponible » si non vérifiable.
4. **Macro** : S&P 500, Nasdaq/QQQ, DXY, rendements obligataires US, Fed, inflation, emploi, calendrier économique, liquidité globale, événements géopolitiques pertinents.
5. **Fondamentaux TEL** : actualités Telcoin, Telcoin Network, réglementation, banques/paiements, partenariats, tokenomics, calendrier de déblocage, annonces officielles; vérifier dates et sources.
6. **Qualité et recherche** : âge de chaque donnée, désaccord entre sources, échantillons, faux signaux, événements de rebond manqués, journal prospectif 1h/4h/24h/7j sans fuite temporelle, backtests hors échantillon, frais/slippage, pas de stratégie « validée » sans preuve.
7. **Décision actionnable** : ACHAT PRÉCOCE / ACHAT CONFIRMÉ / ATTENDRE / INVALIDATION, prix précis des ordres limites *à envisager* même si ATTENDRE, déclencheurs, invalidation, objectifs, probabilités seulement si calibrées, RR **net** >=1,5 si calculable, taille et risque selon budget demandé, scénarios alternatifs. Pas d'achat au marché par FOMO; ne pas confondre signal de marché et ordre admissible.

## Séquence obligatoire
- Collecter en parallèle sources publiques fiables (Kraken, TradingView, CoinGecko/CMC, macro et actualités officielles); croiser les horodatages.
- Présenter tableau du marché et lecture croisée crypto + macro + TEL, avec facteurs favorables et défavorables.
- Vérifier liquidité Kraken, frais et spread avant de qualifier un ordre « admissible ».
- Si données manquantes ou périmées : ATTENDRE / DONNÉES INSUFFISANTES, jamais de confirmation fictive.
- Préciser ce qui a réellement été consulté. Ne jamais prétendre avoir vérifié une catégorie sans source.
- Aucun ordre, ni réel ni paper. Les agents peuvent analyser et documenter en lecture seule.

## Références de travail antérieures à préserver
- Méthode TEL : accumulation de long terme + swing, entrée limite, évitement FOMO, surveillance BTC/ETH.
- Cadre de risque de recherche : capital paper 1000 USD, risque max 0,25 %/trade, spot long, RR net >=1,5. Ne pas appliquer mécaniquement au portefeuille réel.
- Journal prospectif : distinguer ALERTE PRÉCOCE, CONFIRMATION, INVALIDATION, ATTENDRE; mesurer signaux et rebonds manqués à 1h/4h/24h/7j.
- Smart View : correspondance fonctionnelle/visuelle réelle des widgets; 21 cartes TEL99 + radar ne prouvent pas 22 widgets Smart View identiques.
- Audits et backtests historiques non concluants : ne pas présenter comme stratégie validée.
- Analyse du 13/11/2026 : TEL ~0,0014298 USD, BTC ~68371, ETH ~1930, contexte crypto vendeur, TEL en résistance relative, décision ATTENDRE; niveaux illustratifs 0,001395–0,001405 / reprise 0,00144–0,00145 / EMA20 daily ~0,001486 / invalidation récente <0,001389. **Ces chiffres sont une photographie historique, jamais des ordres ou niveaux valables ultérieurement.**

## Continuité multi-agents
Tout agent TEL99 doit consulter ce protocole avant analyse de marché et lire les passations existantes; conserver les garde-fous et le code. Les changements de terminal se font en branche isolée, tests et prévisualisation avant déploiement. La priorité est la fiabilité des données, pas l'ajout de widgets factices.

Références :
- https://github.com/khalidd692/telcoin-trading-intelligence99
- https://tel99-quant-terminal.skkly.chatgpt.site/#market
- https://alpha.tradingview.com/dashboards/9f6534d9-4eb8-4ded-a6ca-b694fb98dfd3


## Extension multifactorielle — critères de couverture et de non-redondance
8. **On-chain TEL et réseau** : activité réelle et adresses actives si observables, distribution et concentration, mouvements des grands détenteurs, flux entrants/sortants des exchanges, transferts exceptionnels, émissions/déblocages et provenance des données. Ne jamais inférer « accumulation des whales » d'un simple transfert.
9. **Microstructure et qualité d'exécution** : order-book imbalance à plusieurs profondeurs, liquidité affichée vs exécutée, spread médian, impact de marché pour le montant envisagé, slippage estimé, qualité des venues, risque de spoofing, volumes réels et volatilité pendant les annonces.
10. **Dérivés et positionnement** : variation d'open interest, funding, basis, options/skew si disponible, concentrations de liquidations, divergences spot/futures, données CEX vs agrégateurs. Absence de marché dérivé TEL ≠ valeur nulle.
11. **Régime de marché** : tendance/range, momentum, volatilité réalisée et implicite si disponible, BTC dominant ou rotation altcoins, volatilité des corrélations, choc macro et stress de liquidité. Adapter les seuils aux régimes sans réoptimisation opportuniste.
12. **Facteurs indépendants** : regrouper RSI/MACD/EMA dans « tendance/momentum » pour ne pas compter trois fois la même information; familles distinctes : structure, liquidité, dérivés, on-chain, macro, fondamentaux, sentiment, risque/exécution. Documenter pondérations et données manquantes; ne pas fabriquer de score global ou de probabilité sans calibration historique.
13. **Validation scientifique** : signaux définis avant observation, validation walk-forward / hors échantillon, sensibilité aux frais et au spread, biais de survivance, fuites temporelles, tests de stabilité par régime, faux positifs et opportunités manquées. Une absence de trades admissibles n'est pas une preuve de performance.
14. **Calendrier et risques extrêmes** : CPI/PCE/NFP/FOMC, déblocages, migrations, incidents techniques, liquidité de week-end, réglementations, annonces Telcoin vérifiées. Préciser quand un catalyseur n'a pas été vérifié.
15. **Sortie standard** : horodatage, couverture par famille (« vérifié », « indisponible », « périmé »), matrice pour/contre, scénario principal et scénario opposé, conditions d'activation/invalidation, niveaux limites indicatifs, frais et RR net, décision prudente. Ne pas qualifier « analyse complète » une analyse où des familles essentielles sont indisponibles; expliquer ces limites.
