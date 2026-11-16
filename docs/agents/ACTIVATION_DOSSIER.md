# TEL99 — Dossier final d'activation (index)

Ce dossier est le point d'entrée unique de l'activation de l'autonomie cloud.
Il ne décrit aucune action à exécuter par un agent : il liste ce qui est
**prouvé**, ce qui est **bloqué**, et les **5 actions humaines** à autoriser.

Dernière mise à jour : clôture technique Mission C.

## Contenu du dossier

| Pièce | Chemin | Rôle |
|---|---|---|
| Runbook d'activation | `docs/agents/ACTIVATION_RUNBOOK.md` | Actions humaines, séquence, arrêt d'urgence, rollback |
| Preuves mesurées (Mission B) | `docs/agents/CLOUD_AUTONOMY_PROVEN_2026-11-16.md` | Modèle gratuit, 3 sous-agents, garde-fou, CAS |
| Config d'automation | `scripts/agents/automation/automation.config.json` | À coller à la création (`dry_run=true`) |
| Manifeste plugin | `.plugin/plugin.json` | Schéma validé côté serveur (`emergency_stop` inclus) |
| Harnais KV | `scripts/agents/automation/verify_kv.py` | Preuve CAS/verrou/dédup/reprise/persistance |
| Arrêt d'urgence | `scripts/agents/automation/emergency.py` | Kill-switch, deux portées distinctes |
| Orchestrateur | `scripts/agents/automation/orchestrator.py` | Sélection mission, frein, préflight, journal |
| PR de convergence | PR #76 (`converge/tel99-main-20261116`) | 100 % additive, CI verte |

## État vérifié (à la date du dossier)

- PR #76 : `mergeable: clean`, **100 % additive**, **CI 4/4 verte**.
- Tests : **688 OK** (`skipped=6`), dont validation config↔schéma et kill-switch.
- Harnais KV : `verify_kv.py --local` → **10/10 PASS**.
- Config d'automation : **acceptée** par le schéma du plugin
  (`additionalProperties: false`, aucune clé parasite).
- Arrêt d'urgence : `TEL99_EMERGENCY_STOP=1` → `exit=3` **sans accès réseau**.
- Automations existantes : **0**. Cron actifs : **0**. Aucun ordre.

## Les 5 actions humaines (détail dans le runbook)

1. **Fusionner PR #76** dans `main`.
2. **Protéger `main`** (PR + CI requises, pas de force-push).
3. **Révoquer le jeton GitHub exposé** et en générer un neuf.
4. **Créer l'automation OpenHands INACTIVE** (`dry_run=true`, sans cron), puis
   lancer `verify_kv.py` contre son **vrai** KV.
5. **Autoriser un lancement ponctuel** de la mission pilote #70 (`dry_run=false`,
   une fois).

## Limites assumées (ne pas les présenter comme résolues)

- Le workflow GitHub/Cloudflare d'audit **n'est pas** une automation OpenHands :
  il ne prouve rien sur l'exécution des agents IA dans le cloud.
- L'arrêt d'urgence empêche le **prochain** run et interrompt une conversation
  **pilotée par le run courant** ; il n'interrompt pas à distance une mission
  hébergée par un autre conteneur (procédure opérationnelle §4c du runbook).
- Le KV cloud réel n'existe qu'une fois l'automation matérialisée (action 4).
- Aucune performance statistique de stratégie n'est démontrée.

## Après autorisation

1. Automation créée → `verify_kv.py` (KV réel) = PASS.
2. Run ponctuel #70 → preuve des 3 rôles (dev / analyst / verifier) + bus.
3. Cron quotidien (`0 3 * * *` UTC) → run observé **sans le PC**.
4. Seulement ensuite : retirer `dry_run` du cron permanent.

Rollback à tout instant : poser le frein (§4 du runbook), interrompre la
conversation active, désactiver l'automation. Aucune donnée n'est détruite.
