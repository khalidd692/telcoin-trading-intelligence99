# Audit de continuité — données Kraken et moteur de backtest
Date : 2026-11-09
Branche : research/tel-discovery-unrestricted

## Objet
Poursuivre la recherche sans reconstruire le projet, sans modifier les stratégies, les boards, la politique de risque ni le paper broker.

## Constat 1 — le moteur existant n'est pas un moteur de rentabilité de stratégies
- `scripts/backtest/run_backtest.py` décrit et exécute le backtest du détecteur de retournement précoce TEL/USDT.
- Il fixe `VENUE = "kucoin"` et `SYMBOL = store.KUCOIN_SYMBOL` (`TEL-USDT`).
- Il mesure les épisodes de signaux, les retournements de référence, les taux de détection et un test de nullité. Il ne simule pas un portefeuille avec entrées/sorties, frais, slippage, taille de position, stop/target, drawdown et P&L de stratégie.
- `scripts/backtest/engine.py` appelle le détecteur de production et mesure la qualité prédictive des alertes ; ce n'est pas un moteur de trading rentable.
- `scripts/backtest/fetch_history.py` ne prend que `--venue kucoin` ou `--venue mexc`. Il ne collecte pas KRAKEN:TELUSD. Le cache et les constantes sont également orientés KuCoin/MEXC.
- `scripts/backtest/evaluate_prospective.py` mesure les rendements futurs des signaux consignés ; ce n'est pas non plus une simulation complète d'exécution d'une stratégie.

Conséquence : il faut conserver ces outils pour leur objectif actuel, mais ne pas présenter leur sortie comme une validation de rentabilité d'une stratégie spot Kraken.

## Constat 2 — historique TradingView disponible pour KRAKEN:TELUSD
Nouvelle lecture MCP du 2026-11-09 :
- 1D : 292 bougies, du 2026-01-22 au 2026-11-09 ; `has_more=false`.
- 1W : 43 bougies ; `has_more=false`.
- Recherche symbole confirme le symbole routable `KRAKEN:TELUSD`.
La pagination TradingView ne permet donc pas, sur ces unités, de retrouver un historique de plusieurs années pour TEL/USD dans le flux actuellement accessible.

## Constat 3 — source officielle Kraken pour les historiques complets
La documentation officielle Kraken indique que son archive OHLCVT téléchargeable contient les bougies de toutes les paires Kraken depuis la première transaction de chaque marché, avec des intervalles 1, 5, 15, 30, 60, 240, 720 et 1440 minutes. Les lignes contiennent timestamp, open, high, low, close, volume et nombre de trades. L'archive complète est publiée en plusieurs parties d'environ 2 Go ; des archives trimestrielles incrémentales existent.
Source officielle consultée le 2026-11-09 :
https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data
La page de support mise à jour le 2026-11-02 indique une couverture de l'historique complet jusqu'au 2026-09-30 et les liens des parties `Kraken_OHLCVT_Full.zip.part00` à `part04`, plus les mises à jour trimestrielles 2026Q1, 2026Q2 et 2026Q3.
Important : Kraken précise que seules les périodes ayant eu des transactions sont présentes ; une bougie absente peut signifier qu'aucun trade n'a eu lieu. Il ne faut donc ni remplir ni interpoler ces périodes automatiquement.

## Conclusion technique
Le principal blocage n'est pas le manque d'indicateurs. C'est le décalage entre :
1. l'instrument de référence demandé (KRAKEN:TELUSD),
2. le collecteur historique existant (KuCoin/MEXC uniquement),
3. le moteur de backtest existant (évaluation du détecteur, pas P&L de stratégie).

L'archive Kraken est la source de données appropriée pour l'étude cross-paires et pour TEL/USD, mais son téléchargement complet est volumineux et doit être récupéré/filtré dans un environnement disposant du stockage et de la bande passante nécessaires. Aucun accès à l'ordinateur local de l'utilisateur n'est disponible depuis cette session mobile.

## Prochaine étape — sans repartir de zéro
1. Vérifier si l'archive Kraken complète ou des extraits OHLCVT existent déjà sur le PC/cache de recherche ; ne pas retélécharger si elles sont présentes.
2. Sinon, récupérer l'archive officielle Kraken une seule fois, vérifier les SHA256 publiés, puis extraire uniquement les paires spot admissibles et leurs CSV utiles.
3. Faire un inventaire des paires réellement négociables, de leur ancienneté, de la continuité, du volume/notional, du nombre de trades et des coûts d'exécution. Exclure les paires illiquides avant toute recherche de signal.
4. Réutiliser les rapports et les résultats déjà obtenus ; ne pas répéter les 6 304 configurations déjà testées sur TEL.
5. Avant de prétendre qu'une stratégie est rentable, auditer ou sélectionner un moteur de simulation P&L adapté aux règles spot Kraken. Le moteur de détection existant reste inchangé.

## Constat 4 — les coûts Kraken utilisés précédemment ne sont pas assez ancrés
Le barème public Kraken Pro consulté le 2026-11-09 affiche, au niveau Spot Tier 1, 0,40 % Maker et 0,80 % Taker par exécution. À titre de repère avant spread/slippage :
- Maker à l'entrée + Maker à la sortie : environ 0,80 % aller-retour ;
- Maker + Taker : environ 1,20 % ;
- Taker + Taker : environ 1,60 %.
Les niveaux réels dépendent du palier applicable au compte et du type d'exécution ; le palier personnel n'est pas connu ici. Les hypothèses 0,70 % et 1,40 % du sweep antérieur ne doivent donc pas être traitées comme des frais Kraken confirmés. Les candidats devront être retestés avec un scénario de frais correspondant au compte et avec spread/slippage séparés.
Source : https://www.kraken.com/features/fee-schedule

## Garde-fous
- Recherche et paper trading uniquement.
- Aucun ordre réel, aucune connexion au compte Kraken réel.
- Aucun ordre paper lancé par cet audit.
- Aucune modification de stratégie, board, politique de risque, code de production ou branche principale.
- Ne pas fusionner, rebaser ou déployer.
- Ne pas annoncer de stratégie validée sans tests hors échantillon, frais, slippage, drawdown et échantillon suffisant.
