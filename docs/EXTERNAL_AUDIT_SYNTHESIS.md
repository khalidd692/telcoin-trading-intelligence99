# Synthèse cumulative des audits externes — Telcoin Trading Intelligence

**Mis à jour :** 23 octobre 2026  
**Branche de travail :** `feat/autonomous-supervisor-v1`  
**Règle de gouvernance :** cette synthèse ne vaut pas approbation de mise en production. Aucun changement de cette branche n'est fusionné dans `main` à ce stade.

## Conclusion commune

Les rapports Gemini, Grok et l'audit indépendant convergent sur un point : conserver le moteur déterministe et l'architecture de collecte existante. Le principal manque pour l'objectif d'agent autonome n'est pas un LLM ni une flotte d'agents, mais une couche opérationnelle vérifiable : qualité/provenance des données, supervision, mémoire des événements, notification externe et évaluation prospective.

Les décisions quantitatives doivent rester déterministes, explicables et read-only. Aucun ordre, aucune clé privée, aucune modification automatique des règles. Une éventuelle IA de langage pourra expliquer les preuves et incidents après validation de ces fondations, jamais remplacer ou modifier la décision.

## Priorités consolidées

### P0 — Intégrité et qualité des données
1. Ne pas traiter une source `PARTIEL` comme saine sans vérifier que la fenêtre continue requise par les indicateurs est disponible.
2. Étendre l'empreinte du snapshot pour couvrir les champs décisionnels : bougies OHLCV, transactions, qualité, carnet, fraîcheur et diagnostics inter-plateformes.
3. Conserver le fail-closed si la provenance ou les données sont douteuses.

### P1 — Supervision opérationnelle
4. Produire un rapport de santé séparé de l'état de marché.
5. Vérifier fraîcheur, unités de temps, cohérence entre artefacts et état d'alertes.
6. Publier le rapport de santé avec les artefacts pour le rendre observable.
7. Ajouter ensuite un watchdog et un canal de notification indépendants de GitHub Actions; cette partie nécessite de choisir/configurer un canal et n'est pas encore considérée comme terminée.

### P2 — Mémoire et mesure prospective
8. Journal append-only des décisions avec horodatage, identifiant de collecte, hash du code, empreinte des données, preuves, invalidation et état de notification.
9. Mesurer les résultats uniquement quand les horizons sont arrivés à maturité, y compris les signaux manqués et les références simples.
10. Distinguer un critère de mouvement d'une performance économique nette. Frais, spread et slippage doivent être explicités; les résultats OOS exploratoires ne prouvent pas la rentabilité.

### P3 — Recherche supplémentaire
11. Mesurer, sans présumer leur utilité, l'apport du carnet, des transactions, de BTC/ETH et de TEL/BTC.
12. Ne modifier ni le niveau `CRITICAL_LEVEL = 0.001526` ni les règles d'« exploitable » sans protocole, version candidate, tests OOS non consultés et approbation humaine.
13. Ne pas payer une base de données, une API LLM ou un runtime permanent avant que des besoins mesurés le justifient.

## Points à vérifier dans le dépôt avant décision finale

- Les constats détaillés des rapports externes doivent être confirmés sur le commit courant; un rapport d'audit n'est pas une preuve en soi.
- Les métriques OOS mentionnées dans les rapports sont issues de protocoles exploratoires déjà consultés; elles ne doivent pas être présentées comme une preuve indépendante.
- Les rapports externes citent des estimations de coûts et certains détails fournisseurs susceptibles de changer; aucune dépense n'est décidée sur cette base.
- Les affirmations concernant la production, la cadence, la disponibilité durable et les notifications nécessitent des mesures d'exploitation sur une période suffisante.

## Modifications apportées sur cette branche

1. Ajout d'un superviseur opérationnel en lecture seule et de tests unitaires associés.
2. Workflow ajusté pour auditer les artefacts avec ce superviseur et joindre le rapport de santé aux artefacts publiés lorsqu'il est généré.
3. Ajout d'un déclencheur `pull_request` afin que les tests puissent s'exécuter sans lancer la collecte de marché ni publier.
4. Le fingerprint du snapshot couvre maintenant l'ensemble des blocs `sources` et `cross_check` en JSON canonique, au lieu de ne hacher qu'un sous-ensemble de prix/carnet.
5. `analyze_timeframe()` refuse une source `PARTIEL` lorsque la queue continue est insuffisante, lorsque la qualité requise est inconnue, ou lorsque la fenêtre utilisée contient un volume nul. Un trou ancien hors fenêtre peut être toléré si la queue utilisée reste continue et saine.
6. Les tests de provenance ont été ajustés pour hacher le même `cross_check` complet que celui présent dans le snapshot; le vérificateur de projet recalcule son empreinte uniquement en mémoire pour tester la forme de l'analyse sur un ancien artefact de démonstration. La porte runtime continue de refuser les empreintes incohérentes.
7. Tests ajoutés pour les mutations de bougies, transactions, statuts qualité et historiques partiels.

## Ce qui n'est PAS encore terminé

- CI vérifiée sur le commit courant : suite principale réussie, tests Python et Node réussis; contrôle projet rapide **32/32 vérifications réussies**. Cinq tests sont ignorés dans la suite principale parce qu'ils nécessitent l'accès réseau de marché public. La collecte de marché est volontairement ignorée sur pull request.
- Le watchdog extérieur et la livraison d'alertes avec accusé de réception ne sont pas encore implémentés.
- Le journal prospectif des outcomes n'est pas encore finalisé.
- La valeur prédictive de la microstructure et du contexte BTC/ETH n'est pas démontrée.
- Aucun changement n'est fusionné dans `main`.

## Références des rapports

- [Gemini](./external-reviews/Gemini.md) — rapport externe; son auteur précise ne pas avoir consulté directement le dépôt.
- [Grok](./external-reviews/Grok.md) — audit externe présenté comme basé sur le code public.
- [Audit indépendant](./external-reviews/Audit-independant.md) — auteur/modèle non précisé dans le texte transmis.

## Critères avant toute fusion

- CI complète verte sur la branche de travail.
- Tests adverses couvrant les deux défauts P0 et non-régression des données saines.
- Diff revu fichier par fichier, sans changement des règles de trading non prévu.
- Supervision clairement distinguée du statut de signal.
- Aucun secret de trading ni chemin d'envoi d'ordre.
- Revue humaine explicite avant fusion; aucune promotion automatique de règles.
