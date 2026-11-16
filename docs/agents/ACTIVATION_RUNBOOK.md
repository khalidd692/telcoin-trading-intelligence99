# TEL99 — Runbook d'activation de l'autonomie cloud

Ce document décrit **ce qui est déjà prouvé**, **ce qui reste bloqué**, et la
**séquence exacte** des actions humaines à exécuter pour activer l'autonomie.
Aucune action de ce runbook n'est déclenchée par un agent : l'agent n'exécute
rien tant qu'un humain n'a pas franchi l'étape correspondante.

État : Mission C. Branche isolée `converge/tel99-main-20261116` (PR #76).
Aucun merge, aucun déploiement, aucun cron, aucune automation, aucun ordre.

---

## 1. Ce qui est terminé et vérifié

| Élément | Preuve |
|---|---|
| Modèle gratuit | Run réel `TEL99-FREE-OK` avec `openhands/deepseek-v4.1-flash` ; quota inchangé (20/20, `used_today=0`) |
| Délégation 3 sous-agents | 3 sous-conversations réelles, outils `["terminal"]` seuls, hook actif, budgets plafonnés, rapports rendus |
| Garde-fou | `rm -rf` → `HookExecutionEvent.exit_code=2`, action bloquée, cible intacte |
| Verrou KV (CAS) | `scripts/agents/automation/verify_kv.py --local` → **10/10 PASS** (CAS, verrou, dédup, reprise, persistance) |
| Manifeste plugin | preflight serveur HTTP 200, ref résolu, trigger `0 3 * * *` UTC |
| Arrêt d'urgence | **Nouveau** : `TEL99_EMERGENCY_STOP=1` → run `exit=3` avant tout réseau ; journalisé |
| Tests | 679 tests OK (`skipped=6`) ; CI PR #76 = 4/4 verte |

## 2. Ce qui reste bloqué (cause exacte)

| Blocage | Cause mesurée | Qui débloque |
|---|---|---|
| KV cloud réel | `GET/PUT /api/automation/v1/kv` → **400 « automation_id required »** : sans automation matérialisée, il n'existe aucun KV user-scoped | Action humaine 4 |
| `main` non protégée | `protected:false`, `rulesets:[]`, `GET protection` → 403 (jeton sans droit Administration) | Action humaine 2 |
| Workflow `repository_dispatch` absent de `main` | Il n'existe que sur les branches de PR #71/#76 | Action humaine 1 (merge) |
| Jeton GitHub exposé | Rotation non encore faite | Action humaine 3 |

## 3. Les cinq actions humaines indispensables

### Action 1 — Fusionner PR #76 dans `main`
- La PR est `mergeable: clean`, **100 % additive** (+12444/-0), CI 4/4 verte, 679 tests.
- C'est la convergence unique : après fusion, PR #71 devient inutile.
- Aucun agent ne fusionne.

### Action 2 — Protéger `main`
- GitHub → Settings → Branches → Add rule : exiger une PR, exiger la CI verte,
  interdire le force-push. Le jeton actuel n'a pas le droit `Administration`.

### Action 3 — Révoquer le jeton GitHub exposé
- Révoquer l'ancien PAT, en générer un neuf, le stocker **hors dépôt**.

### Action 4 — Créer l'automation OpenHands (INACTIVE, `dry_run=true`)
- Source : GitHub, dépôt `khalidd692/telcoin-trading-intelligence99`, ref `main`,
  `repo_path` `.plugin`.
- Config : coller `scripts/agents/automation/automation.config.json`
  (`dry_run: true`, `require_durable_bus: true`).
- **Ne pas activer de cron.** Après création, relever `automation_id`.
- Puis lancer la vérification du **vrai** KV de cette automation :
  ```bash
  AUTOMATION_API_URL=<base> AUTOMATION_KV_TOKEN=<token> \
      python3 scripts/agents/automation/verify_kv.py
  ```
  Attendu : `RESULT: PASS` (les 5 propriétés sur le KV réel, pas un mock).

### Action 5 — Autoriser un lancement ponctuel (mission pilote #70)
- Mission #70 = lecture seule, label `tel99-mission`, critère d'acceptation défini.
- Lancer **une** fois, `dry_run=false`, sans cron. Vérifier ensuite la preuve des
  trois rôles (dev / analyst / verifier) dans le journal et sur le bus.

## 4. Arrêt d'urgence (kill-switch)

Trois sources, l'une suffit ; vérifiée **en premier** dans `run()`, avant tout réseau :

```bash
# A. Variable d'environnement (le plus rapide)
TEL99_EMERGENCY_STOP=1

# B. Fichier sentinelle local (hôte / hors ligne)
touch .tel99-automation-state/EMERGENCY_STOP

# C. Clé KV durable (survit à la destruction du pod)
#    écriture via l'API KV de l'automation : clé "emergency_stop" = {"stopped": true}
```

Un run stoppé retourne `exit=3` et journalise
`{"event": "emergency_stop", "reason": ...}`. Le frein agit aussi sur un `dry_run`
(« ne rien faire », pas seulement « ne rien dépenser »).

## 5. Quotas, journaux, PC éteint

- **Quotas** : `quota_min_remaining=2` ; une mission réelle est refusée si le
  quota est inconnu (fail-closed). Le quota n'est **pas** un plafond d'argent.
- **Journaux** : JSON d'exécution dans `.tel99-automation-state/` (local) et KV
  (cloud) ; le bus conserve le registre des missions.
- **PC éteint** : la démonstration finale exige un run planifié **indépendant du
  PC**. Le workflow GitHub/Cloudflare d'audit **n'est pas** une automation
  OpenHands et ne prouve rien sur l'exécution des agents IA : la preuve doit venir
  d'un run d'automation réel.

## 6. Séquence de validation finale (après les 5 autorisations)

1. Automation créée → `verify_kv.py` (KV réel) = PASS.
2. Run ponctuel #70 `dry_run=false` → vérifier les 3 rôles + le bus.
3. Programmer le cron quotidien (`0 3 * * *` UTC) → observer un run sans le PC.
4. Seulement alors : retirer `dry_run` du cron permanent.

Rollback à tout instant : Action « arrêt d'urgence » (§4), puis désactiver
l'automation. Aucune donnée n'est détruite : les snapshots, alertes, historiques
et évaluations ne sont jamais écrasés.
