# TEL99 Antigravity V2 — Unification 5 Couches, Boucle d'Apprentissage et Harness Opérationnel

Branche : `agents/tel99-antigravity-v2-20261124` (dérivée de `agents/tel99-owner-autofeed-20261124` au commit `8a662db4`).

## 1. Améliorations par couche

| Couche | Ce qui a été corrigé / unifié | Fichiers clés |
| --- | --- | --- |
| **Prompt** | Consignes explicites des cas limites (`strip`, types, `None`, racines non-listes, préservation d'ordre) pour `tel99-analyst` et `tel99-dev`, plus injection bornée du contexte de réparation et des leçons vérifiées. | [local_team.py](scripts/agents/automation/local_team.py), [local_codegen.py](scripts/agents/automation/local_codegen.py) |
| **Context** | Boucle mémoire fermée : récupération des entrées vérifiées isolées par projet avant exécution (`retrieve_lessons`), capitalisation automatique des réparations (`fix`) et échecs (`error`) via `MemoryStore`. | [learning_loop.py](scripts/agents/automation/learning_loop.py), [autonomy_runtime.py](scripts/agents/automation/autonomy_runtime.py) |
| **Harness** | Diagnostic complet en lecture seule (`env_doctor`), préparateur de propositions locales avec pré-check Docker `baseline-red` (`proposal_builder`), cockpit multi-mandats loopback (`multi_cockpit`), CLI PowerShell unifiée (`tel99-agent.ps1`), scaffolding multi-projets (`project_kit.py scaffold`) et Skill opérationnel. | [env_doctor.py](scripts/agents/automation/env_doctor.py), [proposal_builder.py](scripts/agents/automation/proposal_builder.py), [multi_cockpit.py](scripts/agents/automation/multi_cockpit.py), [tel99-agent.ps1](scripts/agents/automation/tel99-agent.ps1), [project_kit.py](scripts/agents/project_kit.py), [SKILL.md](.agents/skills/tel99-autonomous-campaign/SKILL.md) |
| **Loop** | Transmission du diagnostic de réparation à l'analyste lors des tentatives suivantes (`repair_context`), métriques mesurées multi-missions sans limite artificielle à 2 tâches (`collect_campaign_metrics`), injection dans `local_model_routing.choose`, et archivage CAS sûr des contrôleurs 100 % terminés et fermés (`pinned_owner_feed`). | [local_codegen.py](scripts/agents/automation/local_codegen.py), [learning_loop.py](scripts/agents/automation/learning_loop.py), [local_model_routing.py](scripts/agents/automation/local_model_routing.py), [github_multi_mandate_session.py](scripts/agents/automation/github_multi_mandate_session.py), [github_owner_feed.py](scripts/agents/automation/github_owner_feed.py) |
| **Graph** | Coordination déterministe par empreinte SHA-256 du périmètre (`coordinate`) et revue statique de sécurité avant Docker (`review_candidate` bloquant toute modification hors fonction et tout nouvel import non-stdlib). | [local_team.py](scripts/agents/automation/local_team.py), [local_codegen.py](scripts/agents/automation/local_codegen.py) |

## 2. Vérifications reproductibles exécutées

- **Tests unitaires et d'intégration** (15 modules dont [test_antigravity_v2_architecture.py](tests/test_antigravity_v2_architecture.py)) : **247 tests réussis** en 26.058 s (`OK`).
- **Cohérence des définitions d'agents** (`python -B scripts/agents/render_agents.py --check`) : **OK** (13 fichiers synchronisés avec `team_config.py`).
- **Diagnostic environnement réel** (`python -B -m scripts.agents.automation.env_doctor --auto-feed`) : `ready: true`, `owner: khalidd692`, `push: true`, Ollama `gemma4:e4b-tel99-8k` prêt, Docker `29.9.2` + image Python épinglée présents, `5453` MiB disponibles, contrôleur `#205` découvert en lecture seule.

## 3. Preuves réelles observées (Ollama + Docker + GitHub)

### A. Campagne auto-feed live `#205` (`C:\Users\sabri\Desktop\TEL99_ANTIGRAVITY_AUTOFEED_20261124_STATE`)
1. `Preflight` auto-feed (sans manifeste) : `{"preflight": "READY", "controllers": [205], "missions": [2]}`.
2. Exécution réelle de `#206` (`tel99-feed-tool-names-20261124`, 2 tentatives) :
   - `tel99-coordination`, `tel99-analyst`, `tel99-dev` (`21.375s` puis `22.609s`), `tel99-security` (`scope-verified`) et `tel99-verifier` (Docker `baseline-fails` exit 1 ligne 5, `candidate-passes` exit 1 ligne 5) ont tous fonctionné.
   - Reçus GitHub authentifiés publiés sur `#206` :
     - `ACK` : https://github.com/khalidd692/telcoin-trading-intelligence99/issues/206#issuecomment-7119083593
     - `EVIDENCE` : https://github.com/khalidd692/telcoin-trading-intelligence99/issues/206#issuecomment-7119113186
     - `RESULT` : https://github.com/khalidd692/telcoin-trading-intelligence99/issues/206#issuecomment-7119114337
   - Comportement fail-closed vérifié : `#206` a terminé `BLOCKED` (le modèle 4B avait omis `.strip()` sur `"  "` avant le correctif Prompt/Loop), `#207` n'a pas été lancé et aucune PR erronée n'a été ouverte.
   - Boucle d'apprentissage vérifiée : `learning_loop` a enregistré `error-tel99-feed-tool-names-20261124` dans `learning/memory/projects/tel99.json` et mis à jour `learning/measured_quality.json`.
   - Idempotence / zéro doublon vérifiée : une relance `--once` sur le même état retourne immédiatement `BLOCKED` (`exit 2`), le nombre de commentaires sur `#206` reste exactement `4`.

### B. Banc local isolé après correctif Prompt/Loop (zéro écriture GitHub)
- `proposal_builder.build_proposal(..., verify_baseline=True)` a confirmé `baseline_red: true` dans Docker pour `tool_names` (ligne 5) et `dedup_key` (ligne 4).
- Sur le même `gemma4:e4b-tel99-8k` + Docker réel avec les correctifs Prompt/Loop :
  - `bench-dedup-key` (`dedup_key`) : **`ACCEPTED` au 1er essai** (4/4 checks Docker verts).
  - `bench-tool-names` (`tool_names`) : **`ACCEPTED` au 1er essai** (4/4 checks Docker verts).
  - Métriques mesurées : `2/2` réussites (`success_rate: 1.0`, `first_pass_rate: 1.0`, `avg_generation_seconds: 19.812s`, `avg_verification_seconds: 2.203s`).

## 4. Exploitation quotidienne (`tel99-agent.ps1`)

```powershell
# 1. Vérifier la pile locale et les contrôleurs disponibles
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Doctor -AutoFeed -StateDir "$HOME\Desktop\TEL99_ANTIGRAVITY_STATE"

# 2. Préparer localement une proposition (zéro écriture GitHub, vérifie baseline-red dans Docker)
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode DraftProposal -SpecPath spec.json -VerifyBaseline -OutputPath proposal.json

# 3. Lancer la boucle auto-feed bornée
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Preflight -AutoFeed -StateDir "$HOME\Desktop\TEL99_ANTIGRAVITY_STATE"
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Run -AutoFeed -StateDir "$HOME\Desktop\TEL99_ANTIGRAVITY_STATE" -Minutes 60 -PollInterval 30

# 4. Observer l'apprentissage et le cockpit loopback
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Learn -StateDir "$HOME\Desktop\TEL99_ANTIGRAVITY_STATE"
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Cockpit -StateDir "$HOME\Desktop\TEL99_ANTIGRAVITY_STATE" -Port 8765
```

## 5. Limites restantes

- L'exécution des modèles locaux (Ollama) et de la vérification Docker exige le PC Windows allumé.
- Le contrôleur `#205` reste en état `BLOCKED` sur `#206` dans son ledger historique (`TEL99_ANTIGRAVITY_AUTOFEED_20261124_STATE`) : pour produire les deux PR brouillons sur `#206` → `#207`, l'opérateur doit soit relancer depuis un nouvel état propre après revue humaine, soit émettre un nouveau mandat.
- Aucune fusion automatique vers `main`, aucune auto-approbation GitHub et aucun ordre de trading ne sont activés.
