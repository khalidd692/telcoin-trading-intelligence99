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
