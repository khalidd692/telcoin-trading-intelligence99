# Audit indépendant — Telcoin Trading Intelligence

**Source :** rapport transmis par l'utilisateur le 23 octobre 2026; le nom du modèle/auditeur n'était pas indiqué.  
**Dépôt examiné selon le rapport :** `khalidd692/telcoin-trading-intelligence99`, branche `main`.  
**Statut :** conclusions externes à confronter au code et aux tests de la branche de travail.

## Verdict

Le rapport recommande de conserver l'architecture et de ne pas réécrire le projet. Il distingue surveillance automatisée, analyse technique déterministe, apprentissage démontré (pas encore établi en production) et trading autonome (absent et volontairement désactivé).

## Deux défauts techniques prioritaires signalés

### 1. Bougies PARTIEL requalifiées implicitement

Le rapport affirme que le collecteur marque des timeframes `PARTIEL` en présence de trous ou de volumes nuls, alors que `analyze_timeframe()` accepte ces données si l'historique numérique et l'horodatage paraissent suffisants. Cela pourrait permettre des indicateurs calculés sur une fenêtre récente discontinue. La politique proposée n'est pas de rejeter tout historique partiel : vérifier la queue continue requise par les indicateurs et refuser l'analyse exploitable si cette fenêtre est dégradée.

### 2. Empreinte du snapshot trop étroite

Le rapport relève que `compute_snapshot_fingerprint()` couvre essentiellement prix médians, meilleurs prix, quelques niveaux du carnet et le contrôle croisé, mais pas les bougies OHLCV, transactions et métadonnées de qualité qui peuvent influencer l'analyse. Proposition : empreinte canonique de tous les champs décisionnels, et tests prouvant qu'une modification d'une clôture, d'un volume, d'une transaction ou d'un statut invalide l'empreinte.

## Résultats OOS et prudence économique

Le rapport cite `OOS_RAPPORT.md` : dans le segment OOS exploratoire, les taux de réussite rapportés restent sous ou proches des références selon les scénarios; le sous-ensemble `EXPLOITABLE` est de faible effectif et son intervalle de confiance est large. Les métriques évaluent un critère de mouvement défini par le protocole, pas directement un rendement net de portefeuille. Les frais et le slippage restent des hypothèses; la rentabilité robuste n'est pas démontrée.

## Autres angles morts

- Absence de watchdog indépendant et de canal de notification externe fiable.
- Carnet et transactions collectés mais peu exploités par le détecteur.
- Deux chemins de collecte/cohérence peuvent produire des mesures différentes; il faut nommer précisément prix, horodatage et méthode.
- Niveau `CRITICAL_LEVEL = 0.001526` fixe à justifier, versionner et réévaluer; ne pas le remplacer arbitrairement sans protocole.
- Le détecteur est ancré sur le 15m; les rôles des autres timeframes doivent être explicités et testés.
- Les erreurs de cadence/relance doivent être visibles dans un état de santé.
- Les rapports de recherche doivent référencer hash du moteur, données et protocole exacts.
- Mettre à jour les actions GitHub concernées et considérer l'épinglage des dépendances de workflow à un SHA complet.

## Plan proposé

1. Corriger la politique de qualité des bougies partielles et renforcer l'empreinte d'intégrité.
2. Formaliser les sorties : état, direction, preuves, contradictions, horodatages, durée de validité et invalidation.
3. Ajouter supervision indépendante et notifications avec déduplication, livraison vérifiable et reprises bornées.
4. Construire un journal prospectif relié au hash du moteur et aux données décisionnelles, puis évaluer les résultats aux horizons prédéfinis.
5. Tester la valeur incrémentale de chaque famille de preuves sur des fenêtres chronologiques non consultées.
6. N'envisager qu'ensuite une IA explicative facultative, sans autorité de décision.

## Sécurité

Pas de clés de trading, pas d'ordres, pas de décision LLM, pas d'auto-modification des règles. Toute règle candidate doit être versionnée, testée hors ligne, éventuellement exécutée en observation parallèle, puis promue seulement après validation explicite.
