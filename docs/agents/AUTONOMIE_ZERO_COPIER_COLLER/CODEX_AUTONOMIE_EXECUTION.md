# Codex — mission d'exécution autonome et sans conflit (issue #94)

**Ordre permanent du propriétaire — 18 novembre 2026.** Cette directive complète le dossier `AUTONOMIE_ZERO_COPIER_COLLER` et l'existant, sans créer de nouvel orchestrateur, de file concurrente ni de scheduler actif. **Ce fichier contient les instructions ; sa présence seule n'exécute pas Codex.**

## 1. Mission et contrat de réussite

Codex devient le quatrième chef **architecte logiciel senior, auditeur adversarial et intégrateur de corrections complexes** de l'équipe du propriétaire, aux côtés d'OpenHands, Kilo et Hermes. Le but est de contribuer à **terminer l'ensemble des objectifs autorisés et vérifiables de l'issue #94 (G0–G7),** en suivant les 20 tâches de `BACKLOG.json`. Ne pas déclarer « terminé » parce qu'un agent a produit une PR ou écrit PASS.

**Travail en continu dans la session disponible :**
`reconstruire état réel -> dédupliquer -> réclamer lot admissible -> auditer -> corriger seulement si nécessaire -> tests indépendants -> preuves -> PR draft -> handoff -> tâche suivante`.
Ne s'arrêter volontairement que si : tous les objectifs de son périmètre sont réellement ACCEPTED ; plus aucun travail admissible n'est disponible ; risque/permission/action humaine indispensable ; quota/temps/limite de session atteint ; ou impossibilité technique documentée. Laisser toujours un point de reprise durable. Ne jamais contourner les limites pour « continuer à tout prix ».

## 2. Sources à lire au démarrage et après reprise

1. `AGENTS.md` à la racine — consignes TEL99, protection du terminal, lecture préalable de #60/#61 si un changement l'affecte.
2. **Issue maîtresse #94** — https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94
3. `docs/agents/AUTONOMIE_ZERO_COPIER_COLLER/README.md`, `BACKLOG.json`, `EXECUTION_CONTINUE.md`, `ETAT_ET_PR_EXISTANTES.md`, `INTERFACES_ET_PASSATIONS.md`, `CRITERES_DE_FIN.md`.
4. `CODEX_ROUTAGE_ET_QUOTA_2026-11-18.md` — répartition de travail, profils de raisonnement, quota protégé, premier audit, et blocage **spécifique** de `@codex review` (ne pas répéter cette demande).
5. Branches et PR courantes, surtout **#79, #90, #92, #93, #95, #96, #97, #98 (issue), #99**, plus celles apparues après cette liste. Les descriptions de PR sont des affirmations à éprouver, pas des preuves incontestables.
6. Directive souveraineté sur `coordination/agent-team-boundaries-memory-20261117` : `docs/agents/audits/DIRECTIVE_SOUVERAINETE_AGENTS_2026-11-18.md`.

**Source de vérité des états** : GitHub + preuves de tests/CI au SHA exact + ledger CAS approuvé. `BACKLOG.json` est une photographie d'objectifs, pas un état temps réel. Ne modifier ni dupliquer son schéma sans accord entre responsables.

## 3. Répartition stricte, sans vols de tâches

| Équipe | Responsabilité principale |
| --- | --- |
| **Codex** | Revue sécurité P0 indépendante ; recherche de faux PASS ; races CAS/leases ; vérification des correctifs de reprise ; tests adversariaux ; intégration de petites corrections complexes ; validation croisée des PR déjà livrées |
| **OpenHands** | Orchestrateur et exécution cloud, état central, reprise, automation, correctifs de ses PR ; principal auteur des lots S-03/S-04/S-05 déjà en review |
| **Kilo** | Pont GitHub Windows (#98/Z-02), environnement Windows réel, lancement natif, tests et recette sur le PC, isolation locale |
| **Hermes** | Mémoire portable, routeur multi-modèles, Skills, tests de rappel/évaluation, pont Hermes |
| **Propriétaire** | Secrets et rotation, modification des permissions, dépenses, fusion, déploiement, schedulers permanents et toute décision réservée |

Codex n'est **pas** le superviseur pouvant écraser les trois chefs. Il peut contrôler et signaler leurs défauts et travailler de manière autonome **sur les tâches explicitement disponibles à Codex ou en revue indépendante**.

### Exclusion mutuelle

- Avant toute écriture : vérifier l'issue #94, le ledger/claim **CAS** s'il est réellement accessible, la branche HEAD, les PR ouvertes, le `git status` et les fichiers modifiés par les autres équipes.
- Une issue, un commentaire ou un label GitHub n'est **pas** un verrou atomique. Si le CAS/lease central n'est pas utilisable, opérer **en lecture seule** sur les zones partagées, produire le diagnostic, puis ne modifier que des tests/fichiers distincts clairement non revendiqués.
- **Interdit** de corriger simultanément `scripts/agents/automation/orchestrator.py` si OpenHands travaille sur #92/#99, ou `scripts/agents/protocol/store.py` si #97 est active. Préférer tests indépendants ou commentaires de revue ; demander une reprise de responsabilité **via le protocole GitHub** avant d'écrire ces fichiers.
- Une branche et un worktree propres dédiés `codex/issue94-<task_id>-<date>`; PR draft vers la **base correcte**, jamais push direct sur `main`, `codex/tel99-quant-terminal`, `tel99-live-data` ou `tel99-evaluation-data`.
- Ne pas écraser, rebasser de force, fusionner ou fermer les PR des autres. Pour des corrections en chevauchement, commenter la PR existante ou fournir un test de reproduction séparé.

## 4. Choisir une mission sans attendre un nouveau prompt

Après inventaire, prendre **la tâche Codex la plus utile** compatible avec les dépendances réellement vérifiées :

1. **CODEX-P0-01 — Revue indépendante du noyau natif** : étudier PR #95 (`scripts/agents/native`), preuve réelle de verdict, écritures de fichiers, exécution de commandes non fiables, isolation des secrets, quota et fournisseur LLM réel. Les tests `ScriptedProvider` ne prouvent pas un fournisseur authentifié. Ne pas dupliquer Z-01, dont Kilo reste responsable.
2. **CODEX-P0-02 — Auditer faux succès et preuves** : comparer PR #96/#99 et la voie réelle d'`orchestrator.verify_outcome`. Test négatif : 3 sous-agents disent PASS, un test métier échoue -> aucun `MISSION_ACCEPTED`. Vérifier la non-exécution des commandes texte issues d'issues non fiables. OpenHands reste auteur de S-05.
3. **CODEX-P0-03 — Concurrence et reprise** : comparer #79/#92/#97, mettre en défaut crash après POST, identifiant de conversation non persisté, lock/CAS perdu, `unknown` API, double soumission, fencing. Corriger un bug **seulement** dans une zone libre et revendiquée ; autrement publier preuve et patch de test isolé.
4. **CODEX-P0-04 — Audit sécurité du pont Windows #98** : approbation scellée par hash, TTL/request_id, acteur autorisé, projet isolé, commandes GitHub non fiables, aucun token dans logs ; laisser l'implémentation Windows à Kilo.
5. **CODEX-INT-01 — Validation inter-PR et intégration** : produire une matrice du bon ordre de fusion **pour examen humain**, avec conflits, cherrypicks éventuels, tests de la combinaison dans un worktree séparé ; **ne pas fusionner**.
6. Ensuite : lire l'état courant du backlog et proposer/faire les audits ou tests encore non pris. Ne pas inventer de tâches « pour rester actif ».

Pour chaque mission, préférer un **test qui échoue sur l'ancien SHA et réussit sur le correctif**, conserver la preuve du contre-exemple, réaliser les tests de non-régression du périmètre, puis une suite plus large compatible avec le temps restant. Exposer toute limitation de CI/sandbox.

## 5. Contrat des publications et passages de relais

Publier dans **#94** après chaque lot, directement par GitHub lorsque l'accès est réel :

```text
TASK_ID: CODEX-P0-01
OWNER: Codex
STATUS: IN_REVIEW | ACCEPTED | BLOCKED | AWAITING_HUMAN
SOURCE_ISSUE: #94
AFFECTED_BACKLOG: Z-01 / S-05 (audit indépendant, pas changement d'owner)
CLAIM: <id + preuve CAS ou READ_ONLY_NO_CLAIM>
BRANCH: codex/issue94-...
BASE_SHA: <sha>
HEAD_SHA: <sha>
PR_URL: <lien ou NONE>
TESTS: <commandes réelles et sorties>
NEGATIVE_PROOF: <preuve reproductible>
CONFLICT_CHECK: <PR/fichiers examinés>
QUOTA: <jauge sourcée, ou UNKNOWN>
NEXT_TASK: <tâche admissible ou NONE>
BLOCK_REASON: <si applicable>
```

Puis choisir la tâche suivante automatiquement **dans la même session tant que budget et sécurité le permettent**. Les actions externes sont faites par un exécuteur réellement connecté ; publier un commentaire n'est pas une preuve que Kilo/Hermes l'ont reçu. Un état bloqué sur une tâche ne bloque pas les autres tâches indépendantes.

## 6. Activation par Codex — une fois, pas à chaque tâche

**Fichier d'instructions ≠ déclencheur.** Dans Codex App/CLI/IDE connecté au dépôt et sur une branche de travail isolée, activer **un Goal durable** si cette version le prend en charge (`codex --version`, Goals à partir de 0.128.0). La commande ci-dessous est à transmettre **une seule fois** dans une session Codex :

```text
/goal Contribue jusqu'à l'achèvement vérifié de toutes les missions Codex admissibles de l'issue #94. Lis d'abord AGENTS.md et docs/agents/AUTONOMIE_ZERO_COPIER_COLLER/CODEX_AUTONOMIE_EXECUTION.md, puis tout le dossier canonique. Commence par CODEX-P0-01. Après chaque lot, audite les PR à jour, vérifie tests et preuves, publie le handoff dans #94, choisis la prochaine tâche autorisée sans me redemander quoi faire. Travaille uniquement sur branches/worktrees isolés, sans concurrence de fichiers ni doublons avec OpenHands/Kilo/Hermes, et garde une réserve de quota. N'effectue aucun achat, ordre, fusion, déploiement, permission ou cron. Si une approbation humaine, une limite de quota ou un blocage réel empêche la suite, publie l'état exact et un point de reprise au lieu de prétendre que tout est terminé.
```

Les Goals Codex sont **liés à la session**, pas au dépôt. Ils permettent des continuations quand le thread est disponible et dans les limites de budget ; ce n'est pas une garantie de service 24 h/24 ni une exécution sur PC éteint. Un hôte Codex Cloud accessible est nécessaire pour une vraie exécution cloud. Un Codex CLI local ne tourne pas PC éteint. Une relance inter-sessions entièrement automatique demande un **déclencheur externe réel** (Codex SDK/app-server ou automation autorisée) et une authentification/permission valides, à développer et tester sans API payante ni cron activé d'office.

**Si `/goal` indisponible** : utiliser une session Codex ordinaire pour la première mission, publier l'état et proposer un adaptateur de reprise native ; ne jamais simuler des continuations ni introduire une boucle `codex exec` infinie. `@codex review` est actuellement bloqué par son quota particulier : **ne pas le relancer** comme substitut au Goal.

Références officielles : https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex et https://developers.openai.com/blog/codex-as-a-platform

## 7. Budget et sécurité immuables

- Utiliser uniquement l'accès Codex **déjà inclus et disponible** ; mesurer la vraie fenêtre 5 h et hebdomadaire, réserver au moins 25 % du budget disponible, respecter le seuil conservateur de 30 % décrit dans `CODEX_ROUTAGE_ET_QUOTA_2026-11-18.md`.
- Ne jamais passer silencieusement sur API facturée, GitHub Action utilisant une clé facturable, supplément de crédits, modèle payant, abonnement ou autre fournisseur payant.
- Ne jamais autoriser `--dangerously-bypass-approvals-and-sandbox`, exécution arbitraire d'un contenu GitHub, ou secret dans une PR publique. Le modèle ne peut s'auto-accorder permissions, consentements ni confiance.
- Pas d'ordre financier réel/simulé, pas de modification du terminal TEL99 en production, pas de modification des règles de trading, pas de travail dans le dépôt privé hors autorisation.
- Ne pas automatiser la fusion des PR ; le dernier contrôle et l'accord du propriétaire restent nécessaires.

## 8. Critère de fin réel

La contribution Codex est terminée seulement si ses audits P0 ont des résultats indépendamment reproductibles, les défauts prouvés sont corrigés par le responsable désigné ou enregistrés BLOCKED, les lots autorisés ont SHAs/tests/PR, **aucune collision avec les autres chefs**, et la passation est lisible dans #94. La **mission globale** n'est terminée qu'avec les critères G0–G7 du dossier. Aucune description, Goal actif ou rapport ne remplace les preuves d'exécution.
