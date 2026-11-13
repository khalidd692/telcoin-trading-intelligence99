# Audit différentiel TEL99 / Smart View / écosystème crypto — 13 novembre 2026

**Périmètre** : inspection GitHub en lecture seule du produit `codex/tel99-quant-terminal`, workflows `main`, instantané `tel99-live-data`, résumé `tel99-evaluation-data`. Aucune modification du moteur, du site ou des stratégies. Aucun ordre.

## Constats vérifiés

| Domaine | État observé | Écart / décision |
|---|---|---|
| Smart View Rule Scan | Les 11 expressions exactes sont archivées, mais `site/terminal/radar.js` utilise un détecteur différent (`context && supporting` : structure/support/zone + volume/RSI/convergence/reclaim) | **ÉCART CONFIRMÉ** : implémenter un module d'évaluation séparé fidèle aux 6 conditions haussières ET et 5 baissières ET, sans remplacer le radar existant ; exposer chaque booléen, 6/6, 5/5, horodatage et version |
| Statuts | `radar.js` présente `CONFIRMATION` comme « ACHAT CONFIRMÉ », sur la base d'un plan `PRÊT À ÉVALUER` avec `confirmed` et RR net >=1,5 | **RISQUE SÉMANTIQUE** : vérifier que frais personnels, spread, liquidité et actualité ont été vérifiés avant d'utiliser le libellé ; sinon distinguer confirmation technique et achat contrôlé |
| RSI / EMA / MACD / VWAP | `smartview.js` possède un moteur indicateurs, EMA et RMA seed SMA ; `build.py` documente RSI Wilder et VWAP session UTC entièrement observée | **EXISTANT** : comparer aux références Smart View sur mêmes bougies ; ancrage VWAP Smart View non confirmé |
| SMC / structures | `smartview.js` détecte pivots 2+2, BOS/CHoCH et zones estimées | **PARTIEL** : paramètres Smart View propriétaires, ne pas annoncer équivalence exacte |
| Volume Profile | `smartview.js` utilise 192 bougies 1h et 60 bins | **ÉCART** avec passation Smart View indiquant 250 bougies 1h, bins inconnus ; vérifier avant changement, ne pas prétendre à l'identique |
| Liquidité Kraken | `smartwidgets.js` calcule bid/ask, spread, profondeur, déséquilibre, impact d'achat à partir du carnet | **EXISTANT** : vérifier fraîcheur, profondeur et intégration effective au filtre de risque ; pas besoin de nouveau fournisseur pour ce socle |
| Données marché | `scripts/terminal/collect.py` collecte TEL 15m/1h/4h/1D, BTC4h, ETH4h via Kraken REST ; limite 720 barres rappelée | **EXISTANT** : historique court, ne pas prétendre à un backtest 3 ans à partir de ce collecteur |
| Recherche de signaux | `scripts/terminal/research.py` teste des familles propres (cassure + EMA + volume, RSI) | **DISTINCT DE SMART VIEW** : garder la séparation entre exploration et règles exactes |
| Journal prospectif | Sur `main`, `evaluate_observations.py` et tests existent ; observations, transitions, résultats à 1h/4h/24h/7j sans exécution | **EXISTANT** : tester la détection des rebonds manqués et le comptage par type de signal, pas seulement les changements d'état |
| Automatisation | GitHub Actions `tel99-live-publication.yml` cron 5 min et `tel99-forward-evaluation.yml` cron horaire + workflow_run ; runs planifiés réussis le 13/11 | **PREUVE PARTIELLE** : exécutions cloud indépendantes du PC constatées ; cadence durable, latence, notifications, site public et conservation à mesurer |
| Données publiées | `tel99-live-data/site/terminal/data.json` affiche une capture horodatée 2026-11-13 16:39:49 UTC, source Kraken, 720 bougies 15m validées, une bougie en formation exclue, `fresh:true` | **PREUVE** d'un snapshot de branche, pas automatiquement preuve de déploiement identique sur le site |
| Journal publié | `tel99-evaluation-data/evaluation/summary.json` : 26 observations, 25 valides, 14 horizons 1h, 3 horizons 4h, 0 à 24h et 7j | **ÉCHANTILLON INSUFFISANT** : aucun taux de performance robuste ; les moyennes concernent des rendements de prix observés, pas des trades |

## Écosystème crypto : intégration priorisée (non implémentée par cet audit)

1. **Kraken REST/WebSocket** : meilleur retour immédiat. Compléter le contrôle de fraîcheur et d'impact de carnet, si absent ; conserver une provenance unique TEL/USD.
2. **CoinGecko / CoinMarketCap** : contexte de marché, comparaison multi-plateformes et volumes ; ne pas mélanger leurs prix à la cotation d'exécution Kraken. Couverture et quotas à vérifier.
3. **CoinGlass et dérivés** : funding, open interest, liquidations surtout BTC/ETH ; couverture TEL/USD et accès payant **non vérifiés**. À ajouter seulement si l'information améliore réellement la détection.
4. **On-chain TEL** : transferts vers plateformes, concentration, activité ; nécessite attribution d'adresses, qualité et anti-faux-positifs. **Recherche ultérieure**, pas un blocage de livraison.
5. **Actualités** : utile pour annoter les événements et éviter les explications a posteriori ; pas une preuve de signal prédictif.

## Ordre de travail recommandé

**P0** Vérifier le site public contre le JSON publié, le déclenchement automatique, la fraîcheur, et la livraison effective des alertes.

**P1** Ajouter en parallèle le Rule Scan exact, avec tests de conformité sur bougies clôturées ; ne pas remplacer le détecteur précoce existant ni transformer les comptes partiels en alertes non configurées.

**P1** Séparer clairement `market_confirmation` et `risk_checked_buy` ; aucune qualification « achat confirmé » sans données de risque complètes.

**P1** Auditer le journal : alertes précoces, invalidations, changements significatifs, faux positifs, rebonds manqués, horizons 1h/4h/24h/7j, absence de fuite temporelle.

**P2** Comparer indicateurs/SMC/Volume Profile aux références Smart View, documenter les écarts non reproductibles.

**P3** Tester en lecture seule les fournisseurs crypto externes, puis n'intégrer que les facteurs démontrant un bénéfice mesurable.

**Pas de reconstruction, pas de nouvelle stratégie inventée, pas d'ordre réel ou simulé.** Cet audit est une photographie de fichiers/branches consultés, pas un test d'intégration exécuté en environnement cloud.
