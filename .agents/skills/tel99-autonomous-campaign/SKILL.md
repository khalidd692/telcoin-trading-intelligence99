---
name: tel99-autonomous-campaign
description: Exploiter le cycle complet TEL99 Antigravity V2 (diagnostic, préparation de propositions vérifiées baseline-red, auto-feed des mandats GitHub approuvés, boucle d'apprentissage et cockpit).
---

# Cycle d'exploitation autonome TEL99 V2

Ce Skill décrit le flux opérationnel standard pour exécuter des campagnes autonomes multi-agents sans copier-coller, tout en respectant les garde-fous propriétaire (aucune auto-approbation, aucune fusion automatique, aucun ordre réel ou simulé).

## 1. Diagnostic de l'environnement (`Doctor`)

Avant toute session, vérifier Python, Git, GitHub CLI (`khalidd692` + permission push), Ollama (`gemma4:e4b-tel99-8k`), Docker (image Python épinglée), la RAM libre et l'absence de marqueurs `STOP` :

```powershell
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Doctor -AutoFeed -StateDir "$HOME\Desktop\TEL99_ANTIGRAVITY_STATE"
```

Code de sortie `0` = environnement prêt. Code `2` = un ou plusieurs bloqueurs listés dans `blockers`.

## 2. Préparation locale de propositions (`DraftProposal`)

Avant qu'un propriétaire publie ou approuve un nouveau lot de 2 à 10 missions sur GitHub, valider localement le graphe, les SHA-256 canoniques et le test **baseline-red** dans Docker (élimine les faux tests déjà verts) :

```powershell
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode DraftProposal -SpecPath path\to\spec.json -VerifyBaseline -OutputPath proposal.json
```

Cet outil est strictement en lecture seule vis-à-vis de GitHub (`github_writes_performed: 0`). Le propriétaire relit `proposal.json` et publie/approuve lui-même les issues sur GitHub.

## 3. Découverte et exécution auto-feed (`Preflight` puis `Run`)

```powershell
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Preflight -AutoFeed -StateDir "$HOME\Desktop\TEL99_ANTIGRAVITY_STATE"
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Run -AutoFeed -StateDir "$HOME\Desktop\TEL99_ANTIGRAVITY_STATE" -Minutes 60 -PollInterval 30
```

Pipeline exécuté pour chaque mission approuvée :
`tel99-coordination` (scope SHA-256) → `tel99-analyst` (Ollama + leçons mémoire vérifiées) → `tel99-dev` (Ollama) → `tel99-security` (diff confiné à la fonction, 0 import externe non-stdlib) → `tel99-verifier` (Docker baseline-red / candidate-green) → reçus GitHub (`ACK`, `EVIDENCE`, `RESULT`) + PR brouillon.

## 4. Apprentissage mesuré & Cockpit d'observation

```powershell
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Learn -StateDir "$HOME\Desktop\TEL99_ANTIGRAVITY_STATE"
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Cockpit -StateDir "$HOME\Desktop\TEL99_ANTIGRAVITY_STATE" -Port 8765
```

## 5. Arrêt sûr et reprise après incident

- Arrêt propre : `-Mode Stop -StateDir ...` (écrit `stop.request` parent et par campagne).
- Reprise : ne jamais supprimer le ledger CAS ni les reçus ; auditer les missions `AWAITING_HUMAN`, supprimer explicitement les marqueurs `stop.request` après contrôle, puis relancer `Run`.
- Pour un nouveau projet hors TEL99 : `python -B -m scripts.agents.project_kit scaffold --project <nom> --repository <owner/repo> --directory <dossier>`.
