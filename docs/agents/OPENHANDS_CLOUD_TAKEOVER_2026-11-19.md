# TEL99 — PASSATION UNIQUE À OPENHANDS CLOUD, REPRISE SANS KILO LOCAL

**19 novembre 2026 — consigne du propriétaire, sources GitHub et état des preuves.**
**Responsable actif : OpenHands Cloud ; Kilo Windows indisponible ; Codex en réserve (environ 20 % de quota restant).**
Ce document est une **passation durable**, pas une activation d'automatisation ni un processus en cours. Il ne représente pas une permission d'effectuer des actions financières, de payer, de fusionner sur main ou d'élever les droits.

## Objectif prioritaire
Terminer autant que possible le système TEL99 des 12 agents avec **zéro copier-coller humain inter-agents**. Le propriétaire donne l'ordre une seule fois. OpenHands reprend en autonomie pendant sa session, fait coder/tester/vérifier les lots admissibles, publie preuves et checkpoints GitHub et poursuit ceux sans dépendance bloquante. Ne pas répondre après une simple analyse, une série de tests ou une PR documentaire.

## Sources indispensables, déjà construites (REUSE FIRST)
- [PR #125 — registre anti-duplication](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/125) et `docs/agents/SUPERVISOR_REUSE_FIRST_2026-11-19.md`. Relever REUSE, GAP, OWNER, NEXT.
- [Issue maître #94](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94), [blocage Kilo #123](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/123), [backlog 20 tâches #93](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/93), critères G0–G7.
- [PR #79](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/79) (cloud : confirmation UNKNOWN, récupération d'événements /events/search), [PR #92](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/92) (reprise sans double conversation, état KV), [PR #89](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/89) (recette Automate, 33 tests).
- [PR #104](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/104) (candidat d'intégration des composants existants).
- [PR #106](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/106), [#107](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/107), [#118](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/118), [#119](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/119) (superviseur Windows, transport GitHub, CAS, bus).
- **[PR #124](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/124)**, SHA initial consulté `4c40f9ee` (moteur Kilo gratuit, deux tâches texte synthétiques, STOP, reprise, vérification déterministe). Réutiliser, ne pas dupliquer.
- [PR #90](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/90) et audits historiques ; ne pas refaire d'audit général.

**Important** : travail Kilo local `assist/receiver-safe-20261119` non poussé / tests **6/10** signalés et localement inaccessibles au cloud. Ne pas déclarer ce travail réparé, ni altérer / effacer ce worktree. Cloud ne peut pas démarrer un worker Windows sur le PC éteint.

## OpenHands : exploiter les modes existants plutôt que réinventer

1. **OpenHands Cloud / conversation et workspace GitHub** : clone la branche d'intégration isolée, utilise le terminal, le code, Git, la suite de tests et les sous-agents **si la délégation est réellement exposée** ; les rapports doivent refléter les outils réellement invoqués.
2. **Automate / Automations** : inspecte d'abord les automatisations existantes et leur état courant, leur modèle, leurs triggers, quotas, autorisations et historique. La PR #89 attestait au 17/11 deux configurations **INACTIVE** (une planifiée, une événementielle). C'est un précédent historique, pas une preuve de statut actuel. Préférer **une seule automatisation déjà créée**, corrigée et bornée, plutôt que plusieurs nouveaux crons. Vérifier que GitHub App/événements arrivent réellement : succès d'un manuel ne prouve pas l'ingestion d'un événement.
3. **Plugin-spec `.plugin` / Skills OpenHands / Software Agent SDK** : réutiliser `scripts/agents/automation/orchestrator.py`, `pilot_recipe.py`, bus/MemoryStore/policy, le plugin existant et les garde-fous PreToolUse. Préférer une partie déterministe sans LLM pour l'admission et le polling lorsque supporté ; réserver le modèle aux corrections nécessitant raisonnement.
4. **Modèle et quotas** : priorité au `openhands/deepseek-v4.1-flash` précédemment utilisé, **uniquement s'il reste accessible sans dépense**. Vérifier le catalogue, quotas et tarifs actuels ; sans garantie de gratuité ou en cas d'information inconnue, BLOCKED et aucun fallback payant. Borne : 1 exécution concurrente au plus, durée limitée, budget nul, aucun run récurrent hors contrôle explicite. Éviter les automatisations déclenchées par les commentaires de statut eux-mêmes (boucles).
5. **Continuité cloud** : démontrer par un run cloud indépendant du PC, un événement d'entrée, une sortie durable, puis un second run/étape. Ne jamais la déduire du simple fait qu'une automation est listée dans l'interface.

## Plan de livraison sans aller-retour humain

### Lot A — inspection factuelle, sans refaire
Vérifier les HEAD des PR, les composants fusionnés dans `main`, les systèmes toujours déployés et les automations réellement actives. Vérifier GitHub App + droits minimum, le fournisseur gratuit et quota, puis choisir une branche isolée. Reporter REUSE / GAP / OWNER / NEXT et les commandes de tests. Le manque de preuves d'authentification/secret révoqué doit rester fail-closed.

### Lot B — correction du vrai transport cloud, G0/G2/G6
Réutiliser #79 + #92 (fix UNKNOWN et API événements paginés, reprise sur `conversation_id`). Réutiliser le protocole GitHub et CAS de #107/#118/#119, sans introduire un second bus ou une seconde file de vérité. Garantir :
- tâches nées de GitHub approuvées/authentifiées, corps et périmètre épinglés, pas d'exécution de commentaires arbitraires ;
- réservations inter-exécuteurs, idempotence, ACK, résultat/empreintes, état vérifié ;
- absence de double appel modèle après crash, interruption, ACK perdu ou double événement ;
- STOP et BLOCKED réels ;
- garde-fous pour quotas, secrets, séparation des projets, branches.
Le raccord Windows Kilo reste optionnel tant que son worker est indisponible : la recette peut démontrer le **cloud** sans présenter le rôle Kilo comme une session active.

### Lot C — validation de travail réel
Valider d'abord la suite hors réseau et des mocks pour les cas adversariaux. Puis, **si l'intégration, les permissions et un mode strictement gratuit sont réellement disponibles**, mener une recette cloud bornée avec deux **nouvelles tâches synthétiques non financières** et effectivement approuvées par le propriétaire dans un canal authentifié ; vérifier réception depuis GitHub → agent OpenHands → artefact → vérificateur séparé → journal → prochaine tâche **sans copie humaine**. Publier ID des runs, timestamps, code/commit, tests et preuves SHA. Un test simulé seul ne prouve pas G2.
Ne pas faire semblant d'avoir reçu une approbation propriétaire en copiant son nom dans un fichier ; si la procédure exige une validation utilisateur réelle, documenter cette étape unique et poursuivre le reste.

### Lot D — continue le backlog de 20 tâches
Reprendre les tâches OpenHands admissibles des lots S-03/S-04/S-05/S-06 et Z-04/Z-05 d'abord selon leurs dépendances réelles ; ne pas prendre les fichiers Kilo ou Codex déjà réservés. Quand une tâche est vérifiée, passer à la suivante sans nouvelle consigne. Respecter le statut non accepté des tâches de #93/#124. Préparer adaptateurs Hermes et Kilo pour les sessions futures, sans revendiquer une connexion non démontrée. Ne pas fusionner main.

### Lot E — preuve de la continuité et passation finale
Enregistrer à chaque lot : SHA, commande et sortie de tests, branche et PR brouillon, état G0–G7, actions bloquées et raison, prochaine tâche admissible, statut de l'automate et coût observé. Poster un unique compte rendu final et un checkpoint réutilisable sur #94, sans demander au propriétaire de recopier des rapports entre les agents.

## Conditions de sûreté non négociables
- Le secret OpenHands historique potentiellement exposé dans #88 doit être révoqué/vérifié par le propriétaire avant toute mise en production. **Ne pas réécrire ni afficher sa valeur.**
- Aucun achat de crédits, modèle payant, ordre de trading, merge sur main, déploiement, cron permanent, modification de permissions ou secret nouveau sans approbation explicite.
- Une automatisation existante **INACTIVE** ne doit pas être présentée comme exécutante. Examiner un pilote manuel/dry-run avant toute activation d'événements ou de fréquence ; lorsque la plateforme réclame une validation, c'est une vraie décision utilisateur et non une étape à contourner.
- Ne pas créer plusieurs superviseurs concurrents. Un seul moteur de coordination, interfaces interchangeables, runtime différent par environnement.
- Un rôle de spécialiste dans un prompt n'est pas une session indépendante. Toute annonce de délégation doit citer les appels réels et les sorties.
- Pas de promesse de poursuite hors session sans automation créée, activée, tests d'événements et quotas validés.

## Format de sortie attendu
`REUSE` (références), `PATCH` (commits), `TESTS` (réussis/échecs/ignorés), `LIVE` (runs authentifiés et coût), `G0-G7` (preuve par gate), `BLOCKED` (décisions strictement humaines), `NEXT` (tâche suivante stockée durablement).
**Le texte « Done » sans livrables n'est pas accepté.**

**Ce document n'a aucun pouvoir de déclenchement : OpenHands ne le lira que si une conversation ou une automation réellement connectée le récupère.**
