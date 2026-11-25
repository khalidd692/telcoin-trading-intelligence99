---
name: tel99-autonomous-campaign
description: Exploiter le cycle complet TEL99 (diagnostic, planification d'objectifs, routeur multi-fournisseurs, auto-feed GitHub, boucle d'apprentissage, reprise sûre et cockpit).
---

# Cycle d'exploitation autonome TEL99

Ce Skill décrit le flux opérationnel unifié pour piloter l'équipe d'agents TEL99 sans copier-coller, tout en respectant les garde-fous propriétaire (aucune auto-approbation, aucune fusion automatique vers `main`, aucune dépense API cachée, aucun ordre de trading).

## 1. Démarrage complet en une commande (`Start`)

```powershell
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Start
```

Lit [tel99-config.json](../../scripts/agents/automation/tel99-config.json) et exécute :
`Doctor` → `Preflight -AutoFeed` → `Run -AutoFeed -IsolateBlocked` → `Learn` (mesures + promotion des procédures).
Le backend SDK `google-antigravity` (`0.1.24`) est opt-in (`-UseSdkBackend` ou `sdk_backend.enabled: true`) avec repli automatique sûr vers `OllamaNativeProvider` ; les fonctionnalités expérimentales instables sur Gemma 4 8k CPU (`skills_paths_on_gemma4_8k`, `multi_subagent_single_root_cpu`) restent désactivées par défaut.
Pour une campagne 100 % locale détachée d'Antigravity/Gemini/Codex :
```powershell
pwsh -NoProfile -File scripts/agents/automation/start-local-autonomy.ps1 -Minutes 60
```

## 2. Modèles, quotas et routage (`Providers`)

```powershell
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Providers
```

Vérifie en lecture seule : Ollama (`LOCAL_FREE`), Codex CLI (`SUBSCRIPTION_VERIFIED` via RPC + réserve 10 %), Antigravity (`SUBSCRIPTION_OPT_IN` uniquement avec `allow_subscription_cli=True`), Claude (`BILLING_UNVERIFIED` bloqué par défaut), Gemini (`NOT_INSTALLED`), Kilo (`FREE_GATEWAY` synthétique uniquement).

## 3. Planification et proposition vérifiée (`Plan` / `DraftProposal`)

```powershell
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Plan -SpecPath goal.json -VerifyBaseline -OutputPath plan.json
```

Décompose l'objectif, vérifie l'AST et l'ordre topologique, confirme `baseline-red` dans Docker et produit un registre scellé + un brouillon GitHub prêt à relire (zéro écriture GitHub).

## 4. Cockpit et reprise après incident (`Cockpit`, `Stop`, `Recover`)

```powershell
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Cockpit -AllowControls
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Stop
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Recover
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Recover -ClearStop
```

- `Recover` inspecte les `stop.request`, les checkpoints `BLOCKED`/`AWAITING_HUMAN`/`RUNNING` et les outbox en attente.
- `-ClearStop` vérifie l'absence de verrous actifs et supprime uniquement `stop.request`, sans jamais toucher au ledger CAS ni aux reçus.
- Pour un nouveau projet hors TEL99 : `python -B -m scripts.agents.project_kit scaffold --project <nom> --repository <owner/repo> --directory <dossier>`.

## 5. Raccordement Antigravity IDE, 12 spécialistes et coordination multi-acteurs

- **État partagé sans rejeu** : [tel99-config.json](../../scripts/agents/automation/tel99-config.json) pointe vers `~/Desktop/TEL99_ANTIGRAVITY_AUTOFEED_20261124_STATE` afin de conserver les épinglages et checkpoints historiques (`#205`/`#206` en `BLOCKED`).
- **Mobilisation à la demande des 12 rôles** (`scripts/agents/specialist_dispatch.py`, plafond `<= 4` simultanés, sans altérer `.agents/agents/` ni `team_config.py`) :

```powershell
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Specialists
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode AuditAgents
python -B -m scripts.agents.specialist_dispatch select --task "security audit and market data freshness" --max 3
```

- **Routage des modèles & quotas** (`scripts/agents/automation/provider_router.py`) :
  - Orchestration / planification : `agy/gemini-4-neon-medium` (si `allow_subscription_cli=True` et non confidentiel) ; exécution : `agy/gemini-4-hydrogen-medium` ; `gemini-4-neon-high` réservé à `difficulty="hard"`.
  - Tâches confidentielles ou mode local gratuit par défaut (`allow_subscription_cli: false`) : Ollama local (`gemma4:e4b-tel99-8k`) sans coût supplémentaire.
  - Les candidats admissibles sont classés par score, y compris pour les tâches difficiles. Les profils Antigravity sont des préférences de rôle et nécessitent une vérification de disponibilité et d’abonnement. Le récepteur GitHub de code local utilise Ollama.

- **Santé du cockpit** : `Invoke-RestMethod http://127.0.0.1:8765/health` vérifie la réponse du processus HTTP corrigé. Consulter `Status`, `Leases` et le snapshot pour l’état opérationnel. Voir [le rapport et le guide PowerShell](../../../REPORT_FINAL.md).

- **Cycle autonome complet et arrêt propre (`-ExitWhenDone`)** :

```powershell
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Run -AutoFeed -IsolateBlocked -ExitWhenDone -Minutes 60 -PollInterval 15
```

  - Active la reprise automatique bornée (`auto_recover_local_crash=True`, max 1 reprise locale avant reçu irréversible) et stoppe proprement dès achèvement des contrôleurs actifs.
  - `learning_loop.py` génère `measured_quality.json`, `learned_procedures.md` et `improvement_proposals.json` (amélioration procédurale uniquement, aucun réentraînement ni relâchement des garde-fous).

- **Coordination sans collision IDE / CLI / Codex** (`scripts/agents/automation/ide_coordination.py`) :

```powershell
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Leases
python -B -m scripts.agents.automation.ide_coordination acquire --state "$HOME\Desktop\TEL99_ANTIGRAVITY_AUTOFEED_20261124_STATE" --actor antigravity-ide --resource mission:demo --branch agents/tel99-antigravity-v2-20261124 --path scripts/agents/automation/policy.py
```

- **Workflows, vérification et automatisations natives IDE** :
  - Utiliser `plan-verification` (`python -IB .agents/skills/plan-verification/scripts/plan_checks.py`) pour planifier les contrôles sous budget avant lancement.
  - Utiliser `scripts/agents/workflows/tel99_validation_workflow.py` avec `run_workflow` pour orchestrer une revue parallèle bornée (<= 3 spécialistes + vérificateur indépendant).
  - Les automatisations `schedule` sont limitées aux vérifications bornées en cours de session ; aucun service permanent Windows ni fusion vers `main` n'est activé sans accord explicite.
