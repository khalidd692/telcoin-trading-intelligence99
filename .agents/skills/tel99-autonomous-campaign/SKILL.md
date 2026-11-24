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
