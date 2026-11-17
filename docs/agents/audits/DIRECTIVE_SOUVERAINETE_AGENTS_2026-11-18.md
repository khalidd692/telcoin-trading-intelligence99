# DIRECTIVE OFFICIELLE DU PROPRIÉTAIRE — SOUVERAINETÉ DES AGENTS IA
**18 novembre 2026.** Complément prioritaire au plan maître des quatre audits IA, issue #67 et charte PR #90.

## Vision explicitement confirmée par le propriétaire
« Hermes, Kilo et OpenHands m'aident à construire mes agents ; c'est ça le but. Je veux être libre. »

**Produit à livrer : nos propres agents IA et leur moteur d'orchestration, pas un assemblage qui ne fonctionne qu'en exécutant les trois applications tierces.** Hermes, Kilo Crew et OpenHands sont des ateliers de développement, test et déploiement temporaires, dont les adaptateurs doivent pouvoir être remplacés.

Ce texte est une précision d'objectif. **Il ne justifie pas de reconstruire le code existant, d'ajouter des frameworks, de supprimer des PR, d'effectuer une fusion ou d'activer un service payant.**

## Ce qui doit nous appartenir ou être portable
1. **Code et logique d'agents** : planification, rôles Analyste/Développeur/Vérificateur, définition des outils, Skills, instructions, tests, politiques et critères d'acceptation.
2. **Exécution indépendante des trois outils** : point d'entrée natif (par exemple une CLI Python) capable de lancer au moins une mission réelle bornée via un fournisseur de modèle interchangeable, sans lancer les applications Hermes/Kilo/OpenHands. Ne pas confondre la CLI de démonstration offline existante avec un runtime LLM prouvé.
3. **Adaptateurs optionnels** : un contrat de fournisseur de modèle (API, quota, outils), un contrat d'exécuteur (local/cloud), un contrat de transport (GitHub ou autre). Aucun nom de plateforme ne doit être gravé dans la logique métier du noyau sauf dans un adaptateur isolé.
4. **Mémoire et données exportables** : stockage local contrôlé par le propriétaire, import/export versionnés et sauvegarde/restauration privées ; GitHub peut synchroniser les missions et les artefacts autorisés mais ne doit pas être l'unique format de mémoire.
5. **Bus/protocole existant réutilisé** : scripts/agents/protocol/bus.py, envelope et store.py existent déjà. Garder GitHub comme moyen de coordination actuel entre environnements ; rendre le noyau capable de fonctionner localement sans GitHub, puis tester un transport de rechange seulement si besoin prouvé.
6. **Permissions et sécurité maîtrisées** : garde-fous déterministes, secrets hors dépôt, séparation multi-projets, tests négatifs, aucun ordre financier, aucun déploiement/merge sans consentement.
7. **Auto-amélioration vérifiable** : améliorer version de Skills/prompts/stratégies via proposition, tests indépendants, jeu réservé et rollback. Jamais d'autocertification de réussite.
8. **Interface à nous** : une entrée propriétaire (CLI puis éventuellement UI) permettant d'envoyer une mission, suivre la progression et récupérer les artefacts, indépendante des interfaces tierces ; réutiliser le cockpit #87 quand cela économise du travail.

## Ce qu'il ne faut PAS promettre
- Posséder les poids des modèles cloud tiers, accéder gratuitement à des ressources illimitées ou conserver l'inférence sans réseau/modèle installé.
- Faire tourner les agents cloud PC éteint sans infrastructure/fournisseur d'exécution ; le remplacement du fournisseur doit être préparé mais pas magiquement garanti.
- Migrer immédiatement tout le système vers un nouveau dépôt/framework ou relancer des modèles locaux que le propriétaire a mis de côté.
- Affirmer qu'une boucle fonctionne parce que trois sous-agents ont rendu du texte.

## Ordre de travail qui complète et ne remplace pas le plan maître
**P0 sécurité et vérité** : rotation jeton exposé, #79 revue, preuve de réussite des tâches, état CAS et reprise fiable ; les corrections du plan maître restent prioritaires pour toute exécution autonome.

**P1 noyau propre minimum viable** (Hermes chef intelligence, Kilo tests/exécution locale, OpenHands essais cloud) :
- Inventorier la dépendance réelle de chaque fonctionnalité du dépôt aux SDK, fichiers, API et environnements tiers.
- Définir le **plus petit** contrat d'adaptateur de modèle/exécuteur nécessaire ; ne pas réécrire router.py, memory.py, bus.py ou improvement.py s'ils peuvent être réutilisés.
- Démontrer une vraie mission Python/JS depuis une **commande native du projet** (sans ouvrir aucun des trois logiciels), avec un modèle cloud gratuit vérifié si accessible, critères exécutables, livrable sur disque, journal, reprise et mémoire.
- Démontrer le même moteur de mission avec un **second adaptateur/fournisseur** (si une autre API gratuite compatible est réellement disponible), ou marquer BLOCKED et démontrer par un test simulé de contrat que le remplacement n'exige aucune modification du noyau.
- Démontrer que le runtime natif peut fonctionner localement avec bus FileStore même si GitHub n'est pas disponible ; tâches inter-machines peuvent attendre un transport.
- Prouver export/import et rappel de mémoire sans outil tiers.

**P2 compatibilité et indépendance d'exploitation** :
- Hermes/Kilo/OpenHands interviennent comme constructeurs/testeurs de nos agents, pas comme propriétaires de notre logique.
- Intégration GitHub/bus demandée par le propriétaire, mais transport optionnel pour exécution native locale.
- Préparer substituabilité fournisseur/exécuteur et documentation de démarrage/reprise/sauvegarde, sans nouvelles dépenses.
- Tester l'expérience « désinstaller/arrêter un outil tiers » : chaque capacité native annoncée reste disponible ; les capacités propres à cet outil apparaissent honnêtement comme indisponibles.

## Répartition des trois chefs
- **Hermes** : rendre le routeur et la mémoire des agents natifs, exporter les Skills/stratégies/évaluations en code et formats ouverts ; pas de dépendance à Hermes Desktop dans le coeur.
- **Kilo** : développer/tester le point d'entrée natif et les livrables, runner Windows, tests de non-dépendance et client GitHub optionnel ; pas de dépendance à Kilo Agent Manager au runtime.
- **OpenHands** : utiliser ses sous-agents pour aider au développement, CI, validation, exécution cloud ; assurer que le coeur ne requiert pas OpenHands Cloud API pour toute mission et que le scheduler peut être remplacé.
- **Responsabilité partagée** : un seul bus et un seul protocole, revues croisées et tests d'acceptation indépendants, pas de doublons d'orchestrateurs.

## Critères de réception « je suis libre »
1. Une commande de **notre application**, documentée et réellement exécutée, accepte une mission, appelle un modèle via un adaptateur, produit des fichiers/test/rapport vérifiés, sans avoir lancé les trois applications.
2. Le moteur et les données restent utilisables après désactivation de l'un de ces logiciels ; démonstration avec journal.
3. Changer d'adaptateur de fournisseur ne change pas les règles des agents ; tests contractuels et un vrai essai si possible.
4. La mémoire est récupérée dans une session neuve, avec export/restauration ; pas de secret dans GitHub.
5. GitHub reste un bus de coordination opérationnel lorsque disponible ; sans GitHub, les missions locales autonomes n'en dépendent pas.
6. Toute indisponibilité réelle est annoncée « BLOCKED » sans faux succès, avec preuve, quota et prochain prérequis.
7. Le propriétaire peut conserver un clone, une sauvegarde et une procédure pour redémarrer son système sans l'aide d'un des trois ateliers.

## Sources et conduite
Plan maître : docs/agents/audits/PLAN_MAITRE_4_IA_2026-11-17.md (sur branche coordination)
Issue #67 : https://github.com/khalidd692/telcoin-trading-intelligence99/issues/67
Charte PR #90 : https://github.com/khalidd692/telcoin-trading-intelligence99/pull/90

**Cette directive complète la stratégie. Ne pas confondre sauvegarde de document sur GitHub avec application de l'instruction dans les runtimes locaux. Aucun code de production modifié par cette directive.**
