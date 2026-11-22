# TEL99 — REGISTRE CANONIQUE DU SUPERVISEUR / REUSE FIRST

**Date de vérification : 19 novembre 2026.**
**Nature : documentation et règle de reprise, pas une autorisation d'exécution.**
**Responsable : coordination TEL99.**
**Objectif du propriétaire : finir le système multi-agents avec zéro copier-coller humain entre exécuteurs, en réutilisant tout travail démontré.**

> **RÈGLE ABSOLUE : RECHERCHER ET RÉUTILISER AVANT DE CRÉER.**
> Ne jamais prétendre qu'un superviseur est absent, « à construire », ou « non commencé » avant d'avoir exploré les branches/PR historiques, les fichiers, les checkpoints et les preuves ci-dessous. Ne pas répéter des tests, audits, prototypes ou connecteurs déjà achevés sans montrer un écart concret. Cette règle vaut aussi après interruption de session et pour tout nouvel agent.

## 1. Pourquoi cette note existe

Le 19/11, plusieurs instructions successives demandaient de « créer le superviseur » alors que **des superviseurs et leurs composants existaient déjà dans des PR de la veille**. Cette redécouverte tardive a causé des itérations et des copier-coller inutiles. Le propriétaire a explicitement demandé une prévention durable de cette erreur.

**La bonne lecture :** plusieurs *pilotes prouvés mais limités* existent. Aucun ne prouve encore, à lui seul, que 12 agents distincts, GitHub, Hermes, OpenHands et le travail cloud continu s'exécutent de bout en bout. Il faut **intégrer les existants**, pas reconstruire un troisième superviseur.

## 2. Inventaire contrôlé (ne pas confondre code, tests et production)

| Date UTC / lot | Référence | Éléments effectivement présents | Limites connues |
| --- | --- | --- | --- |
| 16/11 | [PR #76](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/76) | Convergence d'une pile d'agents historique (bus, routeur, mémoire, gardes, composants cloud) ; PR fusionnée | La présence dans main n'active ni autonomie ni cloud |
| 16/11 | [PR #79](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/79) | Correctifs OpenHands de confirmation autonome et lecture d'événements ; preuve de blocages réels corrigés dans ce périmètre | PR encore brouillon/non fusionnée lors de la revue ; ne pas inférer cloud actif |
| 17/11 | [PR #89](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/89) | Recette d'automatisation OpenHands, tests hors ligne | Deux automatisations signalées inactives ; recette non activée |
| 18/11 | **[PR #106 — superviseur Codex Windows](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/106)**, `agents/codex-superviseur-local`, `936ef0ba` | `scripts/run_autonomous_loop.ps1`, `scripts/agents/automation/local_codex.py`, `docs/agents/CODEX_LOCAL_WINDOWS.md` ; deux vraies tâches pilotes Codex CLI, commits et tests consignés | Pilote limité ; file GitHub initialement vide ; pas d'acceptation GitHub complète |
| 18–19/11 | **[PR #107 — raccord superviseur à #94](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/107)**, `agents/codex-superviseur-shared-94`, `7510f86a` | Découverte du backlog GitHub `sync_github` / `discover_queue`, validation du contenu/approbations, coordination CAS et preuves, `-SessionMinutes`, `-Status`, `-RequestStop`, `-DiscoverOnly`, `-Preflight`; guide détaillé | CAS KV réel / droits non établis partout ; ne pas qualifier de file GitHub livrée de bout en bout |
| 18/11 | [PR #108 — routeur de modèles Codex](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/108) | Routage Sol/Astra et réserves de quota avec tests et checkpoints | Tests du routeur, pas une preuve d'appels réels sur la recette PR |
| 18–19/11 | [PR #105](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/105), [PR #110](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/110), [PR #120](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/120) | Moteur natif et fournisseur Kilo gratuit, artefacts et tests Docker, amélioration Windows | Périmètre borné à des tâches définies et aux modèles gratuits autorisés |
| 19/11 | [PR #117](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/117), [PR #118](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/118), [PR #119](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/119) | Contrôles G3, journal CAS, handoff interprocessus, raccord bus et superviseur, reprise | Recette entre runtimes réels / tickets nouveaux encore à établir |
| 19/11 | **[PR #124 — intégration actuelle](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/124)**, `assist/autonomy-integration-20261119`, SHA constaté `4c40f9ee` | `start-agents.ps1`, `scripts/agents/automation/autonomy_runtime.py`, `kilo_executor.py`, intégration du `local_codex.py` historique ; deux tâches texte synthétiques enchaînées en un seul lancement via fournisseur Kilo gratuit, vérification en processus distinct, conservation des états | Les identités analyst/dev sont des rôles du fournisseur natif, **pas deux sessions Agent Manager** ; file locale approuvée, **pas une ingestion complète de nouveaux tickets GitHub** ; 12 sessions et cloud PC éteint non établis |

### Preuves de #124 à relire avant de réécrire quoi que ce soit

- [PR #124](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/124), `docs/agents/AUTONOMY_RUNBOOK.md` : protocole de lancement et limites.
- `docs/agents/autonomy-evidence/live-chain.json` : deux identités de spécialiste, deux appels gratuits annoncés HTTP 200, `cost_usd=0`, artefacts et contrôles séparés, reprise sans nouveau fournisseur.
- `docs/agents/autonomy-evidence/tests-summary.json` : 381 tests Windows annoncés, 378 réussis, 3 probes OpenHands ignorées.
- Au SHA `4c40f9ee` : quatre workflows GitHub Actions au statut success.
- `docs/agents/AUTONOMY_BACKLOG_CHECKPOINT.json` et `docs/agents/AWAITING_HUMAN.md` : 20 tâches et portes G0–G7 toujours **PARTIEL / AWAITING_HUMAN**.
- Les journaux privés et les anciennes preuves locales ne doivent pas être effacés ni reconstitués à l'aveugle.

**Important :** des documents sur une branche ne sont pas automatiquement présents sur `main`. Le nom d'un rôle ou un ACK ne prouve pas qu'un agent distinct a travaillé. Un `PASS` de test synthétique n'implique ni livraison d'application réelle ni cloud actif.

## 3. Check-list obligatoire AVANT toute nouvelle tâche « superviseur / agents autonomes »

1. Lire cette note, `AGENTS.md`, [issue maître #94](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94), [issue #123](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/123), [backlog PR #93](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/93) et [critères G0–G7](https://github.com/khalidd692/telcoin-trading-intelligence99/blob/coordination/zero-copy-autonomous-completion-20261118/docs/agents/AUTONOMIE_ZERO_COPIER_COLLER/CRITERES_DE_FIN.md).
2. Inspecter **branches et PR ouvertes/fusionnées**, y compris les PR #106, #107, #108, #110, #117–#124 ; chercher les fichiers de superviseur, routeur, transports, STOP, mémoire et tests avant de proposer du code.
3. Examiner les chemins en priorité : `scripts/run_autonomous_loop.ps1` (ancien lanceur), `scripts/agents/automation/local_codex.py`, `local_coordination.py`, `start-agents.ps1` (nouveau), `autonomy_runtime.py`, `kilo_executor.py`, `scripts/agents/protocol/handoff.py`, scripts Kilo locaux, les checkpoints `.tel99-automation-state` disponibles et les tests correspondants. Ne pas supposer qu'un chemin absent de `main` est absent du projet.
4. Produire **une matrice REUSE / PATCH / GAP**, associant chaque fonctionnalité aux PR, au SHA, aux tests et à une limite confirmée ; ne développer qu'un `GAP` prouvé. Signaler honnêtement les preuves non consultables et les checkpoints présents seulement sur le PC.
5. Vérifier propriétaire des fichiers et worktree actif avant écriture. Ne pas modifier le worktree de Kilo ou Codex en cours : développer sur branche isolée, tests reproductibles, PR brouillon ; aucune fusion automatisée.
6. Après livraison, mettre à jour l'inventaire avec nouveaux SHA/preuves, et transmettre les faits via GitHub au lieu de demander au propriétaire de recopier les réponses entre agents.
7. **Prouver les critères**, ne pas déclarer « fini » parce que le fichier, la documentation, des statuts ou des mocks existent.

### Contrat de réponse obligatoire à une nouvelle demande de développement

Avant toute action lourde, chaque agent annonce brièvement :
- `REUSE:` quelle implémentation historique et quel SHA il réutilise ;
- `GAP:` quelle capacité manque réellement, avec référence observable ;
- `OWNER:` quel agent et quel worktree détiennent les fichiers ;
- `NEXT:` la correction minimale avec test d'acceptation et preuve attendue.

Si l'inventaire ne peut pas être vérifié, **ne pas reconstruire « au cas où »**. Faire une lecture des sources ou déclarer `BLOCKED_DISCOVERY`.

## 4. Cap à ne pas perdre

**But utilisateur :** zéro copier-coller humain entre agents et poursuite automatique des tâches autorisées jusqu'à la livraison du système de 12 agents, sous contrôle de quota, permissions, STOP et validation indépendante.

**Priorité d'intégration :** réutiliser #107 (admission et découverte GitHub) et #124 (exécuteur Kilo local + vérification + mémoire) **sans créer un troisième superviseur** ; tester deux **nouveaux** contrats GitHub approuvés dans un environnement autorisé avec déduplication et reprise, puis raccorder les autres spécialistes, Hermes et OpenHands si leurs adaptateurs/runtime sont réellement disponibles.

**Limites inchangées :** aucune dépense, aucun ordre financier, aucune fusion `main`, aucun déploiement, aucune activation de service permanent ni modification des permissions sans accord. Ne jamais promettre que des exécuteurs locaux continuent PC éteint. Le secret OpenHands historique signalé dans `AWAITING_HUMAN.md` exige une révocation attestée avant mise en production.

## 5. Évolution du présent registre

Ce fichier est un inventaire vérifié à une date, **pas une vérité intemporelle**. Actualiser après chaque livraison importante. Une nouvelle version ne supprime pas les anciennes preuves ; les erreurs documentées restent visibles.

La prévention de la duplication n'est effective que si les agents relisent la documentation. Pour généraliser l'instruction, incorporer son lien dans `AGENTS.md` et signaler ce registre à la coordination #94. Les nouvelles PR se fondent sur les travaux antérieurs, pas sur une reconstruction.
