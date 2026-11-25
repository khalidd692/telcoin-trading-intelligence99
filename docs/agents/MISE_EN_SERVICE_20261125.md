# TEL99 — Mise en service du 25 novembre 2026

## Verdict

- **GO** pour l'exploitation locale autonome (Ollama `gemma4:e4b-tel99-8k` + Docker + superviseur TEL99 + mémoire + boucle d'apprentissage + cockpit `http://127.0.0.1:8765/` + intégration opt-in du SDK Antigravity `0.1.24` + kit de réutilisation externe `project_kit`).
- **BLOQUÉ (revue propriétaire requise)** sur la recette GitHub `#211` : la mission A (`#212`, approbation `7150425706`) a été exécutée à `2026-11-25T02:13:19Z` et a terminé honnêtement en `BLOCKED` après ses 2 tentatives contractuelles (`RESULT` publié en commentaire `7150542423`), laissant la mission B (`#213`, dépendante de A) en attente. Aucun reçu durable n'a été effacé ni rejoué.
- **Correctif prouvé localement** : après correction des prompts de réparation dans `local_codegen.py` et `local_team.py`, les deux contrats de `RECETTE_COORDINATION_211.json` (A puis B) ont été validés localement en isolation dans Ollama + Docker (**`ACCEPTED` au 1er essai chacun**, durée totale `194,97 s`).

## Réconciliation des travaux (dépôt principal + SDK + preuves)

- **Branche de livraison unique** : `agents/tel99-antigravity-v2-20261124` (PR brouillon `#208`). Les travaux SDK du worktree `TEL99_FINAL_20261125` ont été réconciliés sans écraser les commits `402d38c8` et `f01bee2d` :
  - `scripts/agents/automation/antigravity_sdk_backend.py` (opt-in, localhost uniquement, `compaction_token_threshold >= 2500`, nettoyage déterministe du `harness_pid`, repli sûr vers `OllamaNativeProvider`).
  - `scripts/agents/automation/start-local-autonomy.ps1` et `tests/run_hour_autonomy_acceptance.py` (corrigés : vagues mono-mission SDK sans violation `proposal requires 2..10 missions`, vraie erreur Docker dans `hour-repair-proof`, métriques `active_seconds` / `wait_seconds` / `duplicates_count` / `skills_discovered`).
  - `tests/test_antigravity_sdk_integration.py` : **8/8 PASS** dans le `.venv` SDK `google-antigravity 0.1.24`.
- **Cockpit `http://127.0.0.1:8765/`** : rafraîchissement non-bloquant des sondes fournisseurs en arrière-plan (`/health` `{"ok":true}` en `277 ms`, `/api/snapshot.json` en `81 ms`), exposition de `sdk_backend`, `skills`, `auto_recovery_count` et `backend`, protection CSRF `403` vérifiée.
- **Benchmark conservé** (`TEL99_FINAL_EVIDENCE_20261125/benchmark_models_and_backends.json`, SHA-256 `62e0311341d6486b4440b9656f698b481befb7a59a9c0d2c3ecacd6879dd821a`) : Ollama natif `50,594 s` (`ACCEPTED`) vs SDK `262,875 s` (`ACCEPTED`). Ollama natif reste le moteur par défaut pour le quotidien ; le SDK est opt-in (`-UseSdkBackend`).
- **Kit externe hors TEL99** : `scripts/agents/project_kit.py` vérifié sur `acme-webapp` (`status: PLANNED`, 3 rôles, mémoire isolée avec `0` fuite vers `tel99`, invocation réelle du skill `plan-verification`).

## Commandes quotidiennes vérifiées

Depuis `C:\Users\sabri\Desktop\TEL99_ANTIGRAVITY_20261124` :

```powershell
# 1. Campagne autonome 100 % locale (indépendante de Gemini / Antigravity IDE / Codex)
pwsh -NoProfile -File scripts/agents/automation/start-local-autonomy.ps1 -Minutes 60
pwsh -NoProfile -File scripts/agents/automation/start-local-autonomy.ps1 -Status
pwsh -NoProfile -File scripts/agents/automation/start-local-autonomy.ps1 -Stop

# 2. Cycle GitHub auto-feed complet (Doctor -> Preflight -> Run -> Learn)
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Start -ExitWhenDone

# 3. Cockpit local (port 8765), état, baux, arrêt sûr et reprise
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Cockpit -Port 8765 -AllowControls
Invoke-RestMethod http://127.0.0.1:8765/health
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Status
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Leases
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Stop
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Recover
```
