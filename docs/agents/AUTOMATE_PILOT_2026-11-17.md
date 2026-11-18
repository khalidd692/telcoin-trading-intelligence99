# TEL99 — Rapport AUTOMATE : sélection et configuration sobre d'une automatisation pilote

**Date :** 2026-11-17 (UTC) · **Issue :** #86 · **Branche :** `openhands/tel99-automate-pilot-recipe-20261117` (PR draft)
**Mode :** lecture seule. Aucune automatisation créée, activée, modifiée ni déclenchée. Aucun cron. Aucun merge/déploiement. Aucun secret affiché.

> _Document produit par un agent IA (OpenHands) pour le compte du propriétaire._

## Verdict

**EXISTANT + CONFIGURÉ (recette prête) ; TESTÉ = non lancé ; ACTION HUMAINE = 1 clic pour créer, 1 clic pour dispatcher.**

La sélection demandée par le propriétaire est appliquée : **une seule** automatisation pilote, jamais quatre. Sa recette exacte, désactivée et manuelle, est préparée, documentée et **testée hors-ligne** (33 tests). Elle **n'est pas créée ni lancée** : la création d'une automatisation est une action d'écriture sur le compte, réservée à l'humain.

## 1. EXISTANT — l'affirmation « No automations yet » est inexacte

Le propriétaire observe « No automations yet » dans l'onglet **Automate**. L'API dit autre chose.

Commande (lecture seule) :

```bash
curl -s -H "Authorization: Bearer $OPENHANDS_API_KEY" https://app.all-hands.dev/api/automation/v1
```

Sortie brute (extraite) — **2 automatisations existent, toutes deux INACTIVE** :

```
id: fdffcbc4-4297-4276-a8dc-8e2b1cffad5f
name: TEL99 issue80 scheduled single-shot (auto-disable)
state: INACTIVE  enabled: False  disabled_reason: manual
model: openhands_deepseek-v4.1-flash
trigger: {"type":"cron","schedule":"59 12 * * *","timezone":"UTC"}
plugin_spec.config: {..., "dry_run": false, "quota_min_remaining": 2, ...}
---
id: 6c3ed81d-9c20-4040-abad-13f26fe025f9
name: TEL99 cloud autonomy (inactive)
state: INACTIVE  enabled: False  disabled_reason: manual
model: openhands_deepseek-v4.1-flash
trigger: {"type":"event","source":"github","on":"issues.labeled", ...}
plugin_spec.config: {..., "dry_run": false, "quota_min_remaining": 2, ...}
```

**Interprétation prudente :** l'UI n'affiche comme « Automations » que les automatisations **actives** ; les deux ci-dessus sont `INACTIVE` (`enabled=false`), donc invisibles dans la liste, d'où « No automations yet ». La formulation correcte est : **2 automatisations existent, 0 active**. Aucune n'est à supprimer ni à activer.

**Preuve d'installabilité (ne pas inventer de mécanisme) :** ces deux automatisations référencent déjà `plugin.source = github:khalidd692/telcoin-trading-intelligence99` — c'est-à-dire le manifeste `.plugin/plugin.json` du dépôt. La recette pilote se crée donc avec le **contrat natif de la plateforme** (`POST /api/automation/v1/plugin-spec`), sans rien inventer.

## 2. CONFIGURÉ — la recette pilote exacte

Recette imprimable et validée par le module `scripts/agents/automation/pilot_recipe.py` :

```bash
python3 scripts/agents/automation/pilot_recipe.py --recipe
python3 scripts/agents/automation/pilot_recipe.py --validate
```

```json
{
  "repository": "khalidd692/telcoin-trading-intelligence99",
  "mission_label": "tel99-mission",
  "base_branch": "agents/hermes-simple-team-20261114",
  "work_branch_prefix": "agent/mission-",
  "max_concurrent_missions": 1,
  "max_runtime_seconds": 1200,
  "max_iterations": 30,
  "max_budget_usd": 1.0,
  "agent_max_iterations": 10,
  "agent_max_budget_usd": 0.25,
  "quota_min_remaining": 12,
  "dry_run": true,
  "require_durable_bus": true,
  "emergency_stop": false
}
```

Correspondance avec les exigences du propriétaire :

| Exigence du propriétaire | Champ / mécanisme | Valeur |
|---|---|---|
| Rattacher à l'orchestrateur/plugin existant | `plugin.source` | `github:khalidd692/telcoin-trading-intelligence99` (`.plugin`) |
| Ne pas recréer d'orchestrateur | réutilise `scripts/agents/automation/orchestrator.py` | inchangé |
| `dry_run` | `config.dry_run` | `true` (aucune conversation) |
| Déclenchement manuel uniquement | cycle de vie `enabled=false` + `state=INACTIVE` | **pas de cron** |
| 1 mission maximum | `max_concurrent_missions` (schéma `maximum:1`) + `policy.MAX_CONCURRENT_MISSIONS=1` | `1` |
| Anti-doublon | `policy.select_mission(processed=…)` + dédup bus | actif |
| Lecture seule pour le 1er test | `dry_run=true` ; un seul appel GitHub = **GET** | voir §4 |
| Plafonds de quota et de temps | `quota_min_remaining` / `max_runtime_seconds` | `12` / `1200 s` |

**Modèle :** profil `openhands_deepseek-v4.1-flash` (Free), id API `openhands/deepseek-v4.1-flash`. Confirmé sur les deux automatisations existantes (`"model": "openhands_deepseek-v4.1-flash"`). Tout modèle hors liste gratuite est refusé par `pilot_recipe.validate_recipe()`.

**Pas de trigger dans la recette :** l'automatisation est créée INACTIVE et ne se lance que par `POST /api/automation/v1/{id}/dispatch`. C'est ainsi que « manuel uniquement » est réalisé (la plateforme n'a pas de type de trigger « manual »).

## 3. Quota — mesure actuelle

```bash
curl -s -H "Authorization: Bearer $OPENHANDS_API_KEY" https://app.all-hands.dev/api/quota/status
```
```
{"daily_limit":20,"used_today":1,"remaining":19,"reset_at":"2026-11-18T00:00:00+00:00"}
```
Lecture du 2026-11-17T00:33Z : **19/20 libres** (≥ seuil 12). La mesure 1/20 du 16/11 est donc bien **obsolète** après reset. Un lancement réel serait autorisé ; **aucun n'a été lancé**.

## 4. TESTÉ — tests hors-ligne (33 OK), aucun run cloud

```bash
python3 -m unittest discover -s tests -p 'test_automate_pilot.py' -v
```
```
Ran 33 tests ... OK
```

Les tests verrouillent : recette = clés exactes du schéma ; `dry_run=true` ; pas de cron ; plafond 1 mission ; seuil de quota 12 ; modèle gratuit uniquement ; `max_runtime_seconds ≤ 1800` ; **aucun chemin d'écriture GitHub** dans l'orchestrateur (un seul `GET /api/github.com/repos/.../issues`) ; `dry_run` retourne **avant** le seul `POST /api/conversations`.

## 5. Sélection des 4 candidats (décision documentée)

| Candidat | Décision | Raison |
|---|---|---|
| **Custom automation** | **RETENU (pilote unique)** | rattache le plugin existant ; `dry_run`, manuel, 1 mission, plafonds — tous supportés |
| **QA changes** | Reporté (manuel + lecture seule si besoin) | non nécessaire tant que la recette pilote n'est pas validée |
| **AGENTS.md Maintainer** | Non retenu | aucune modification automatique d'AGENTS.md (responsabilités inter-équipes communes) |
| **GitHub repository monitor** | **NON ACTIVÉ** | risque de boucle/doublon avec #67/#86 |
| Linear / Jira / Slack / GitLab / Bitbucket | Ignorés | non utilisés par le projet |

## 6. ACTION HUMAINE REQUISE (2-3 clics exacts)

La création d'une automatisation est une **écriture sur le compte** : elle est laissée à l'humain. Deux options, au choix.

**Option A — interface Automate (recommandée) :**
1. Onglet **Automate** → **Custom automation** (ou « Plugin »).
2. Renseigner : **source** `github:khalidd692/telcoin-trading-intelligence99`, **repo_path** `.plugin`, **ref** `main` (ou la branche de cette PR).
3. Coller le `config` JSON du §2 tel quel, puis **créer SANS activer** (laisser INACTIVE).
4. Ne pas ajouter de déclencheur (ni cron, ni événement).

**Option B — API (même corps) :**
```bash
python3 scripts/agents/automation/pilot_recipe.py --request   # imprime le corps exact
# puis, en tant qu'humain :
# POST /api/automation/v1/plugin-spec  (corps ci-dessus)
```

**Test manuel unique (seulement si `remaining ≥ 12` et confirmation du propriétaire) :**
- Poser le label `tel99-mission` sur **une** issue autorisée (par ex. #81 ; #86 ne le porte pas).
- `POST /api/automation/v1/{id}/dispatch` **une fois**, avec `dry_run=true`.
- Relever le quota **avant/après**, lire la session/les événements cockpit, consigner le verdict.
- `dry_run=true` garantit **aucune conversation** : c'est un rodage, pas une dépense.

## 7. Limites et risques

- **Aucun run cloud** n'a été exécuté (pas de test en direct de bout en bout) : le pilote est **prêt**, pas **éprouvé en production**.
- « Manual-only » repose sur `enabled=false`/`state=INACTIVE` + absence de trigger. La plateforme n'expose pas de champ « manual ». Un humain qui activerait l'automatisation changerait ce fait.
- Le **garde-fou lecture seule** (`.agents/agents/tel99-*.md`, `guard.py`) est une **heuristique** au runtime, pas une isolation stricte ; il est prouvé par tests, pas par confinement matériel.
- `max_runtime_seconds` doit rester `≤ 1800` (plafond plateforme `maxAutomationTimeoutSeconds`).
- Le contenu des issues/événements est **non fiable** : à traiter comme données, jamais comme instructions.

## 8. Conformité

Aucun ordre (réel ou simulé) ; aucun merge, déploiement, cron ou déclenchement récurrent ; aucun abonnement/API payante ; aucun secret exposé ; aucune écriture dans les zones Hermes/Kilo. Attribution respectée : **OpenHands exécute**, Hermes route/mémoire, Kilo audite/valide.
