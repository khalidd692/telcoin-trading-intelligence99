# TEL99 Quant Intelligence — livraison de l’incrément 01

10 novembre 2026. Branche isolée `codex/tel99-quant-terminal`, issue de `b7cccbb9ef672f6f7da543c0159c7c025d79c995` (recherche / continuité des phases). Aucune fusion dans main, aucun ordre réel ou paper, aucune publication publique. L’ancien dashboard et les règles primaires sont conservés.

## Utiliser le terminal

L’aperçu privé est fourni dans le message de livraison. Navigation : **Marché**, **Laboratoire**, **Simulateur de risque**, **Données & preuves**. Sur téléphone, les quatre onglets sont en bas. Les choix d’unité et de moyennes mobiles sont conservés dans ce navigateur.

- **Actualiser le cours** lit uniquement le ticker public Kraken. Il ne recalcule pas les indicateurs ou signaux.
- Le graphique et l’analyse utilisent une capture datée. La décision devient « DONNÉES INSUFFISANTES » lorsque les données 1h/4h vieillissent. Une erreur réseau n’efface pas la provenance du snapshot.
- Le laboratoire permet de comparer trois hypothèses de coûts, filtrer les études et consulter les transactions historiques simulées. Les exports JSON sont disponibles dans Laboratoire et Données.
- Le simulateur calcule une quantité théorique, avec frais et slippage. Référence : 1 000 USD, risque 0,25 %, RR brut minimal 1,51. Il ne crée aucune position et n’est pas synchronisé avec le compte paper existant.

Utilisation locale, Python 3.12 et Node 22 pour la vérification (aucun paquet Python à installer) :

```sh
python -m http.server 8000 --directory site/terminal
```

Ouvrir `http://localhost:8000`. Ne pas ouvrir directement `index.html` en `file://` : le navigateur doit pouvoir charger `data.json`.

Actualisation analytique manuelle, six requêtes publiques et finies, sans compte :

```sh
python -m scripts.terminal.collect --output research/terminal/raw/kraken_nouvelle_capture.json
python -m scripts.terminal.build --market-input research/terminal/raw/kraken_nouvelle_capture.json
```

Le collecteur refuse d’écraser un fichier existant. Cette opération actualise le marché ; l’échantillon du laboratoire reste figé. Servir le nouveau fichier ou enregistrer une nouvelle version privée pour le rendre visible. Aucun collecteur serveur périodique n’a été ajouté.

## État fonctionnel

| Domaine | État livré | Limite concrète |
|---|---|---|
| Interface | Quatre écrans sombres, bureau et largeur mobile 375 px vérifiés | Test en navigateur Chromium ; pas de test physique sur Android |
| Graphiques | Chandeliers, volumes, zoom, quatre unités, EMA20/50, SMA200, RSI/MACD | Historique borné ; capture analytique, pas de flux OHLCV permanent |
| Indicateurs | EMA/SMA, RSI, MACD, ATR, ADX/DMI, CCI, stochastique, VWAP calculés | CCI, DMI, stochastique et VWAP accessibles dans le JSON, pas de panneau dédié ; RSI arithmétique documenté |
| Décision | Cinq états, preuves, contradictions, invalidation, garde de fraîcheur | Heuristique expérimentale non validée ; contexte BTC/ETH descriptif, pas de probabilité |
| Laboratoire | Primaire figée, 27 études existantes, deux variantes, trois fenêtres et trois coûts, journal/export | Pas de holdout vierge, faible effectif, pas de modèle ajusté ni de walk-forward avec apprentissage |
| Risque | Calculateur frais/slippage, plafond de cash, RR brut/net | Pas de portefeuille persistant, pas d’ordre paper ; gap réel susceptible de dépasser le budget |
| Qualité | Horodatages, SHA-256, exclusions, trous, remise à zéro des indicateurs entre segments | Un trou n’est pas automatiquement une panne ; absence de transactions possible |
| Surveillance | Vieillissement détecté dans la page | Alertes persistantes/dédupliquées, macro, carnet et multi-exchanges non réalisés |

## Résultats reproductibles

**Stratégie primaire inchangée : 53 candidats, 53 rejets RR, 0 trade.** RR maximal 0,8010878 pour un seuil de 1,51. Phases IS/VAL/OOS conservées : 39/7/7 candidats ; ces noms ne constituent pas la preuve d’un nouvel échantillon indépendant. Capital inchangé, expectancy et profit factor non calculables. Source : `results/strategy_validation/results.json`.

Deux variantes ont été définies séparément dans `research/terminal/EXPERIMENT_PROTOCOL.json` avant leur première exécution. Le moteur d’exécution primaire est réutilisé, ses règles ne sont pas réécrites. Signal à la clôture, entrée à l’ouverture suivante, stop sur creux antérieurs moins 0,5 ATR, cible expérimentale fixée à 2R, sortie temporelle selon le moteur existant. Positions dont la fenêtre maximale dépasse la fin du fold exclues. Les données étaient déjà exposées : résultats exploratoires, pas une validation hors échantillon indépendante.

Coût central hypothétique par côté : frais 0,25 %, slippage 0,10 %. Chaque fenêtre redémarre avec **son propre capital de 1 000 USD**.

| Variante | Fenêtre | Trades | Capital final USD | Expectancy R | Profit factor | DD réalisé % |
|---|---:|---:|---:|---:|---:|---:|
| Cassure 20 | 1 | 0 | 1 000,0000 | — | — | — |
| Cassure 20 | 2 | 2 | 996,9694 | −0,6064 | 0,0000 | 0,3031 |
| Cassure 20 | 3 | 4 | 1 001,9517 | +0,1962 | 1,7287 | 0,1645 |
| Reprise RSI30 | 1 | 4 | 999,4335 | −0,0553 | 0,8806 | 0,4233 |
| Reprise RSI30 | 2 | 6 | 997,1919 | −0,1862 | 0,6406 | 0,7219 |
| Reprise RSI30 | 3 | 4 | 999,1525 | −0,0833 | 0,8303 | 0,4939 |

20 transactions simulées au total pour le scénario central, réparties entre deux familles. Les scénarios de coûts réévaluent ces mêmes hypothèses : ils n’ajoutent pas 40 observations indépendantes. La somme descriptive des PnL de fenêtres indépendantes est négative pour chaque famille ; ce n’est pas une courbe de portefeuille continu. La seule fenêtre positive ne valide pas Cassure 20.

Références cash et buy-and-hold présentes dans les résultats ; le buy-and-hold utilise tout le capital et n’a pas le même risque. Drawdown sur capital **réalisé**, pas sur valorisation intratrade. Aucun Sharpe annualisé inventé à partir de quelques transactions. Le scénario prudent utilise 0,40 % de frais et 0,30 % de slippage par côté ; le tarif réel du compte n’est pas connu.

Les 27 études d’événements (survente RSI, divergence, repli EMA) restent des statistiques de rendements, pas des backtests tradables. Une ambiguïté a été détectée : l’étude existante arrondit 6h sur des bougies 4h à une seule barre, soit 4h. L’interface affiche désormais l’horizon effectif et la demande d’origine, sans altérer les résultats source.

## Données et audit

Inventaire du dépôt de base : `evidence/source-inventory.txt`. Audit des composants critiques : collecteurs, moteur d’analyse, moteur de simulation, tests, rapports et workflows ; il ne s’agit pas d’un audit de sécurité ligne par ligne de l’intégralité du dépôt.

- `collector/`, `src/agent_analysis.py`, `scripts/strategy_backtest/engine.py`, `site/index.html` et `site/realtime.js` sont réutilisés ou préservés. Aucun fichier existant de la base n’a été modifié.
- Le MCP TradingView officiel a réellement fourni des bougies dans cette session. Les limitations d’un ancien connecteur ne sont donc pas généralisées à celui-ci. Export brut conservé à `research/terminal/raw/tradingview_2026-11-10.json`.
- Capture analytique publique Kraken : **2026-11-10T11:21:15.961961+00:00**. Après validation : 720 bougies 15m, 720 en 1h, 720 en 4h, 291 quotidiennes ; aucun trou interne dans ces séries retournées. Les bougies en formation sont exclues. L’API ne donne qu’une fenêtre récente, pas un historique complet extensible arbitrairement.
- Historique TradingView utilisé pour la recherche : 1 747 bougies 4h retenues, une barre manquante, dernière séquence continue de 1 746 barres. Le 15m historique contient 1 120 intervalles manquants et sa dernière séquence n’a qu’une barre ; il serait impropre à une décision récente. Le 1h a 193 intervalles manquants.
- Les cours Kraken directs et ceux des exports TradingView peuvent différer par leur couverture et leur traitement des périodes sans transactions. Ils ne sont pas fusionnés. Empreintes distinctes pour source analytique et source de recherche.
- Seuils de quarantaine (>3× pour certaines anomalies de prix), méthodes d’indicateurs et hypothèses de coûts sont explicités dans le code et testés. Ils sont conservateurs, pas des preuves qu’une bougie est erronée.
- Le workflow historique `monitor.yml` comporte une planification et un mécanisme de relance ; il écrit des artefacts et publie le dashboard existant. Il n’a pas été déclenché ni modifié. Aucune protection supprimée.
- Nouveau workflow `tel99-terminal.yml` : branche isolée seulement, lecture seule, plafond 10 minutes, aucun cron, aucun déploiement ; vérifie et produit un ZIP conservé 14 jours.

## Preuves de vérification

- `python -m unittest discover -s tests -v` : **455 tests**, 3 ignorés, aucun échec (452 exécutés avec succès).
- `python -m unittest discover -s collector -p 'test_*.py' -v` : **42 tests**, aucun échec.
- `node tests/test_terminal.js` : **16 assertions** ; anciens tests `test_dashboard.js` et `test_realtime.js` réussis.
- Syntaxe `app.js` vérifiée, construction JSON stricte déterministe vérifiée, aucun fichier préexistant modifié.
- Contrôles navigateur : quatre onglets, unités, moyennes mobiles, RSI/MACD, sélection des coûts, filtres, calculateur et rejet d’un stop invalide, récupération explicite du ticker public, largeur mobile sans débordement horizontal, absence de bougies avec effacement du graphique.
- Revue indépendante : débordement numérique du calculateur et gestion d’une série vide corrigés. Régressions numériques testées ; cas d’interface reproduit avant correction puis revérifié.
- Les logs contiennent des messages `FAIL` issus de scénarios négatifs délibérés des anciens tests ; le bilan unittest faisant autorité est `OK (skipped=3)`.

Logs et captures : `evidence/`. Les tests hors ligne ne prouvent ni disponibilité permanente d’un fournisseur, ni rentabilité d’une stratégie. Les 42 tests du collecteur sont comptés séparément, pas ajoutés comme garantie statistique.

## Suite, classée par valeur

1. **Historique continu et fiable** : archivage incrémental Kraken, rapprochement des transactions et des bougies sans activité, preuve de couverture. Prérequis de tout progrès scientifique.
2. **Actualisation analytique utilisable depuis le terminal** : service public en lecture seule, cache, état de panne, limites de requêtes ; remplacer la reconstruction manuelle sans créer de boucle coûteuse.
3. **Validation future préenregistrée** : protocole verrouillé, données réellement nouvelles, drawdown mark-to-market, frais du palier réel, profondeur/spread observés. Pas de nouvelle grille de paramètres sur les mêmes données.
4. **Surveillance explicable** : état persistant et déduplication, transitions significatives, alertes de données ; aucune exécution d’ordres.
5. **Journal de portefeuille manuel** puis comparaison à Smart View sur les mêmes dates, règles et données. L’exécution automatique paper reste soumise à une autorisation explicite.

Passation : poursuivre sur cette branche, préserver le protocole et les résultats négatifs. La mission complète reste ouverte ; cet incrément livre un terminal de recherche utilisable et vérifiable, pas encore une équivalence totale à Smart View.
