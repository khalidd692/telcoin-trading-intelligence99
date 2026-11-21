# ÉTAT INITIAL, PR ET DÉPENDANCES — PHOTO AU 18 NOVEMBRE 2026

**Cette liste est une photographie au moment de la création du dossier.** Chaque chef doit reconsulter GitHub et les logs du runtime avant de déclarer une tâche ou une PR résolue.

## Acquis présents dans le dépôt

- **PR #76** — merged sur main : socle équipe, routeur déterministe, mémoire, bus, garde-fous et orchestrateur. La présence de ce code n'est pas une preuve que les environnements Hermes, Kilo et OpenHands sont connectés en production.
- **scripts/agents/protocol/bus.py** — machine à états, registre d'acteurs, enveloppes et reprise de mission file backed. **Pas encore un bus GitHub transactionnel réellement livré à Kilo.**
- **scripts/agents/protocol/store.py** — FileStore/KvStore existants. N'ajoutez pas une nouvelle base sans prouver le besoin.
- **scripts/agents/intelligence/memory.py** — schéma versionné et séparation projet/common. Il faut prouver rappel inter-sessions et confidentialité, pas recréer l'interface.
- **scripts/agents/intelligence/router.py** — routeur déterministe. Une sélection de modèle ne prouve pas que ce modèle peut réellement répondre au runtime.
- **scripts/agents/intelligence/cli.py** — interface stdlib pour demo/route/remember/recall/improve ; « offline » n'est pas un runtime LLM natif réel.
- **scripts/agents/protocol/adapters/kilo.py** — connected=False : pas de réception automatique de message sur le PC Windows.
- **scripts/agents/automation/policy.py** — exclusion des PR de la sélection d'issues déjà implémentée. Ne pas refaire ce correctif.
- **Workflow .github/workflows/tel99-agent-team-audit.yml** — tests déterministes, pas ordonnanceur de missions autonomes.
- **automation.config.json** — dry_run=true, quota_min_remaining=2, travail sur branche agents/hermes-simple-team-20261114 : aucune activation continue réelle par ce fichier.

## PR ouvertes à rapprocher avant travaux

| PR | Contenu connu | Décision pour les chefs |
|---|---|---|
| #78 | Preuves de smoke test cloud | Archiver comme preuve, ne pas confondre avec autonomie complète |
| #79 | Correctifs confirmation unknown et /events/search | Revoir en lien avec #92 ; pas deux implémentations concurrentes |
| #83 | Preuves ponctuelles cloud manual/event/cron | Ne démontre pas service permanent, utiliser pour tests |
| #85 | Mémoire KV et cohérence TEL99 | Comparer au memory.py sur main et à #91 |
| #87 | Cockpit mobile cloud en lecture seule | Réutiliser, ne pas recréer d'UI |
| #88 | Capacités MCP/Context7 ; risque ancien secret exposé | Vérifier révocation, scanner les surfaces publiques |
| #89 | Recette pilote manuelle inactive | Comparer à #92 pour éviter duplication |
| #90 | Charte des chefs et archives des 4 IA | Conserver comme docs, pas preuve de rappel mémoire |
| #91 | Mémoire charte OpenHands documentaire | Lire avant la fusion mémoire |
| #92 | Reprise de conversation orpheline + correctifs #79 + recette pilote | PR DRAFT nouvelle : revendique 747 tests OK et correctif anti-doublon. Vérifier diff et CI, puis examiner l'intégration ; ce n'est PAS automatiquement un succès sur main |

PR #92 :
https://github.com/khalidd692/telcoin-trading-intelligence99/pull/92

## Obstacles principaux vérifiables

1. **HUMAIN / SÉCURITÉ** — jeton OpenHands historiquement exposé, rotation non attestée dans les sources consultées. Les agents n'ont pas à publier ni manipuler la valeur.
2. **CODE / FONCTIONNALITÉ** — verify_outcome n'établit pas que les critères d'acceptation sont réellement satisfaits ; un résultat agent ne suffit pas.
3. **CODE / REPRISE** — #92 corrige une classe de reprise mais le comportement en conditions réelles sur main, l'atomicité de toutes les écritures d'état et les races restent à vérifier.
4. **RUNTIME LOCAL / CRITIQUE** — réceptionnaire Kilo GitHub non connecté ; moteur Hermes local ne lit pas automatiquement chaque demande dans GitHub.
5. **PRODUIT / CRITIQUE** — pas de démonstration d'une commande propriétaire qui fait travailler les agents sans ouvrir les trois clients, au-delà de la CLI offline.
6. **EVALUATION** — auto-amélioration avec keeper auto-certifié, sans jeu de contrôle indépendant, est une ébauche et non un apprentissage fiable.

## Priorité immédiate décidée ici

P0 : secret + validation des résultats + réconciliation de #79/#92 + garde-fous. **En parallèle**, construire et tester le transport local Kilo/Hermes et la CLI native sur des fixtures sans secrets ni appels dangereux, pour supprimer le besoin de copier-coller.

## Ne pas inventer une capacité déjà livrée

Chaque chef doit donner état EXACT :
- CODE_PRESENT
- TESTED_OFFLINE
- VERIFIED_LIVE
- IN_REVIEW
- BLOCKED
- NEEDS_HUMAN

Une documentation ou une PR DRAFT n'autorise pas l'état VERIFIED_LIVE.

## Checkpoint du 21 novembre 2026

Le backlog de #93 et ses dépendances restent la référence. Les constats ci-dessous s’appuient sur les têtes publiées des PR, leurs tests et leurs preuves. Les quatre audits ont été relus dans la branche de #90. Les seuils et estimations qui y sont proposés restent à mesurer. [Backlog #93](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/93) · [Archives Claude, Gemini, Grok et DeepSeek](https://github.com/khalidd692/telcoin-trading-intelligence99/tree/e729ec8a377b8674ce0ef5fb5f7e11643e447463/docs/agents/audits)

### Composants déjà présents

| Couche | Implémentation et preuve | Écart qui reste |
| --- | --- | --- |
| Prompt | Charte #90, enveloppes v1, accords liés au contenu, rôles analyste/dev/vérificateur. #103/#104 et #127/#128 couvrent des refus d’accords modifiés ou non autorisés. | Prouver le parcours autorisé sur deux nouvelles issues et l’exécution de missions techniques avec critères indépendants. [#90](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/90) · [#128](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/128) |
| Contexte | La configuration versionnée expose trois rôles actifs et neuf réservés. #121 apporte export, restauration et isolation de la mémoire. #126 atteste le rappel local de deux missions synthétiques après redémarrage. Les décisions, erreurs et remplacements sont conservés dans la mémoire existante. | Vérifier l’export privé et la restauration inter-runtime sur deux projets. Ancrer les rapports d’évaluation indépendants aux octets du jeu de contrôle et des règles effectivement exécutés. [#121](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/121) · [#126](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/126) |
| Harnais | #124 réutilise le worker Kilo sans outils et le vérificateur séparé. #128 couvre les branches dédiées, les refus de publication et le verrouillage Windows. Le routeur Codex de #108 vérifie compte, catalogue, réserve et limite de tentatives. | Identifier l’exécuteur autorisé de la recette P0. Vérifier le quota disponible et l’identité GitHub dans cet environnement. [#124](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/124) · [#108](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/108) |
| Boucle | #118/#119 apportent le journal et la passation. #128 couvre ordre de publication, reprise et arrêt. #92/#104 contiennent la réconciliation cloud et le rapport durable. | Vérifier #92/#104 contre l’API réelle avant intégration cloud. La pile de #128 a encore l’ancien orchestrateur cloud. [#119](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/119) · [#92](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/92) · [#104](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/104) |
| Graphe | #107 découvre et admet les missions GitHub. #126 et #127/#128 branchent Hermes et Kilo sur le même superviseur local. La séquence de #128 attend la preuve et le résultat du prédécesseur dans les scénarios testés. | Démontrer la chaîne GitHub réelle, la continuité PC hors ligne et l’arbitrage entre exécuteurs partageant un état durable. [#107](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/107) · [#128](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/128) |

### Lacunes classées par impact

| Impact | Tâches de #93 | État et reprise |
| --- | --- | --- |
| 1 — Recette et sécurité | Z-02, S-01, S-02 | Z-02 est vérifié hors ligne au SHA `19530b0a`, avec deux nouveaux tickets et leurs PR encore à produire. S-01 attend l’attestation de révocation du propriétaire. S-02 attend la preuve des règles et privilèges effectifs. [Checkpoint P0](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/123#issuecomment-7061880076) |
| 1 — Exécution sûre | S-03, S-04, S-05, S-06 | OpenHands reprend le rapprochement #92/#104 et le contrôle réel de l’API. CAS local et refus d’accord testés. L’acceptation spécifique de #114 sous #117 est une preuve bornée. Restent la concurrence multi-exécuteur, le verdict métier générique et la vérification d’approbation sur le parcours vivant. [#117](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/117) · [#94](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94) |
| 2 — Modèles et mémoire | I-01, I-02 | Hermes conserve les deux lots. Deux appels historiques #126 attestent un coût nul. Le quota courant, la latence et un repli réellement accessible restent à mesurer. I-02 exige export/restauration privés et preuve S-05 avant acceptation. [#126](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/126) · [Mandat I-02](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94#issuecomment-7026817464) |
| 2 — Continuité | Z-01, Z-03, Z-04, Z-05 | Le noyau natif et deux missions texte sont prouvés dans un périmètre borné. Z-01 attend la preuve d’un programme produit et testé. Le relais Hermes Z-03 est prouvé sur la démo bornée. La passation entre chefs, la poursuite hors PC et la reprise croisée restent à démontrer. [#124](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/124) · [#126](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/126) |
| 3 — Qualité contrôlée | I-03, P-01, P-02, P-03 | #122 fournit le correctif de séparation entre évaluation et routage. La réconciliation avec #124 accompagne ce checkpoint. I-03 reste conditionné à S-05 et I-02 chez Hermes, avec un jeu de tâches réservé, un évaluateur distinct et une réversion à prouver. P-01 garde #125 comme inventaire de réutilisation. P-02 réutilise #87 après S-05/Z-04. P-03 attend Z-01/I-02 pour deux projets. [#122](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/122) · [#125](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/125) · [Mandat I-03](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94#issuecomment-7026825714) |
| 4 — Livraison complète | F-01, F-02, F-03 | Les guides et les tests de reprise existent. Restent une application vérifiée de bout en bout, la preuve de fonctionnement en l’absence de chacun des ateliers et la livraison avec les gates G0–G7. [Critères de fin](https://github.com/khalidd692/telcoin-trading-intelligence99/blob/315fd08c11a18093c99ccaff2bd3b69358e6fbbc/docs/agents/AUTONOMIE_ZERO_COPIER_COLLER/CRITERES_DE_FIN.md) |

### Pratiques externes retenues

- OpenAI décrit une documentation de dépôt courte à l’entrée, des références ciblées et des invariants contrôlés par le harnais. Le guide à cinq couches place les bornes de transport dans le harnais et les dépendances dans le graphe. TEL99 conserve `AGENTS.md`, les contrats et le superviseur existant. Le lot Codex applique les limites à l’interface de découverte, au niveau où les blocages ont été reproduits. [OpenAI Harness engineering](https://openai.com/index/harness-engineering/) · [Michael Gentile, Prompt, context, harness, loop, graph](https://michael-gentile.github.io/me/blog/prompt-context-harness-loop-graph/)
- `harness-eval` propose des contrôles statiques déterministes sur des configurations d’agents. Les recommandations d’Anthropic distinguent le jugement sur l’artefact de l’analyse de sa trace. Les régressions TEL99 contrôlent les octets du fichier actif, l’archive de proposition et les refus du transport avec les tests existants. [Red Hat Community AI Tools](https://github.com/redhat-community-ai-tools/harness-eval) · [Anthropic, Demystifying evals for AI agents](https://www.anthropic.com/research/demystifying-evals-for-ai-agents)
- Hermes documente des contextes enfants isolés et une livraison pouvant être rejouée après reprise. TEL99 conserve les identifiants de corrélation et les claims CAS. Les contrôles d’accord et de portée restent dans le harnais, en ligne avec OWASP. [Hermes Subagent Delegation](https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation) · [OWASP LLM01](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
- Kilo documente une limite anonyme de 200 requêtes par heure et par IP pour les modèles gratuits. Le quota restant derrière l’IP et la réponse réelle du modèle demeurent à observer. Pour Codex, le protocole App Server permet de lire les fenêtres et leurs regroupements. Les deux améliorations courantes ont été mesurées hors ligne, sans appel à un modèle. [Kilo Gateway](https://kilo.ai/docs/gateway/authentication) · [Codex App Server](https://developers.openai.com/codex/app-server)
