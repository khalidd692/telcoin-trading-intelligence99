# TEL99 — Autonomie cloud contrôlée (préparée, non activée)

Ce document décrit le plugin d'autonomie préparé sur la branche isolée
`feat/cloud-autonomy-plugin-20261115`. **Aucune automatisation permanente n'est
activée.** Le plugin se déclenche uniquement si un opérateur le crée et
l'active explicitement.

## Ce que fait le plugin

À chaque déclenchement (cron proposé : `0 3 * * *` UTC), il exécute un
orchestrateur **sans LLM propre** :

1. vérifie que le dépôt est dans l'allowlist et que le quota gratuit restant
   est suffisant ;
2. sélectionne **une seule** mission GitHub ouverte portant le label
   `tel99-mission` (les autres issues, y compris #60/#61, sont ignorées) ;
3. vérifie les préconditions : branche de base non protégée, branche de travail
   isolée, une seule mission active ;
4. en `dry_run` (défaut) : journalise et s'arrête sans rien dépenser ;
5. sinon : démarre le coordinateur, qui délègue aux trois agents existants
   (`tel99-dev`, `tel99-analyst`, `tel99-verifier`) via `task_tool_set`.

L'orchestrateur **réutilise** `scripts/agents/team_config.py` et
`scripts/agents/guard/guard.py` : il ne réimplémente ni les agents, ni le
contrat lecture seule, ni le garde-fou.

## Garanties

| Exigence | Mécanisme |
|---|---|
| Une seule mission active | `max_concurrent_missions` figé à 1 (schéma) + `policy.MAX_CONCURRENT_MISSIONS` (code) |
| Délai maximum | `max_runtime_seconds` (défaut 1800) ; les enfants sont interrompus au délai |
| Quota vérifié | `quota_min_remaining` ; refus si le quota gratuit est trop bas |
| Limite d'itérations | `max_iterations` (coordinateur) et `agent_max_iterations` (sous-agents) |
| Budget plafonné | `max_budget_usd` et `agent_max_budget_usd` |
| Arrêt en cas d'erreur | la première précondition qui échoue arrête le run (exit 2) |
| Journal d'exécution | événements JSON écrits dans l'état (KV store en Cloud) |
| Branches protégées | `main`, `tel99-live-data`, `tel99-evaluation-data`, tout préfixe `tel99-` refusés |
| Pas de fusion | le plugin ne fusionne jamais et n'ouvre pas de PR automatiquement |

## Le quota de conversations n'est pas un plafond financier

`/api/quota/status` limite le **nombre** de conversations gratuites par jour
(20). Ce n'est **pas** une garantie de coût nul : les crédits, la facturation et
les tarifs peuvent changer. Le budget par run (`max_budget_usd`) est donc la
limite réelle, et le quota n'est qu'un garde-fou supplémentaire.

## Vérifier que les sous-agents chargent réellement leurs restrictions

`allowed_tools` dans la charge de création est une **demande**, pas une preuve.
Après un run, exécuter :

```bash
python3 scripts/agents/automation/verify_runtime.py <conversation_id> --suffix <HHMMSS>
```

Il lit `base_state.json` persisté pour chaque sous-agent et exige : outils
réellement `["terminal"]`, hook PreToolUse présent, politique de confirmation
présente. Il exécute aussi le garde-fou sur un échantillon de commandes
interdites. Un rapport vert signifie que le garde-fou **agit**, pas seulement
qu'il est configuré.

## Méthode d'activation (à faire par un opérateur, hors de ce dépôt)

1. **Créer une issue de mission** et lui appliquer le label `tel99-mission`.
   Ne pas étiqueter les anciennes issues (#60, #61, etc.) : elles resteraient
   ignorées tant qu'elles n'ont pas le label.
2. **Créer l'automatisation** à partir du manifeste de ce plugin
   (`POST /api/automation/v1/plugin-spec`), en pointant le dépôt sur cette
   branche, avec un `config` minimal :

   ```json
   {
     "repository": "khalidd692/telcoin-trading-intelligence99",
     "mission_label": "tel99-mission",
     "dry_run": true
   }
   ```

3. **Observer un premier run en `dry_run`** : le journal doit montrer
   `mission_selected` puis `dry_run`, sans conversation démarrée.
4. **Passer `dry_run` à `false`** seulement après avoir vu un run sec se
   terminer proprement, et vérifié le quota et le budget.
5. **Vérifier** avec `verify_runtime.py` après le premier vrai run.

L'activation est un acte explicite : elle n'est pas réalisée par ce dépôt.

## Risques restants (honnêtes)

- **Le garde-fou est heuristique** : défense en profondeur, pas une isolation.
  Les contrôles primaires restent l'allowlist `terminal`, `sub_agent_scope` et
  la politique de confirmation.
- **Le quota n'est pas un plafond financier** (voir plus haut).
- **L'isolation des sous-agents** est vérifiée après coup (`base_state.json`),
  pas empêchée par construction.
- **Aucun run réel n'a exécuté le travail des agents** : le run `dry_run`
  observé sélectionne une mission et s'arrête ; il ne prouve pas le
  comportement des sous-agents sur une vraie mission.
- **Le cron n'est pas encore prouvé pour ce manifeste** : le déclenchement cron
  de la plateforme a été démontré séparément, mais pas encore avec ce plugin.

## Constats de validation (faits observés)

Validé contre la plateforme réelle le 15/11/2026 :

- **Manifeste accepté** : `POST /api/automation/v1/plugin-spec` → HTTP 201,
  `state: INACTIVE`, `enabled: false`. Aucune automation permanente créée.
- **Le schéma rejette les métacaractères shell** dans `entrypoint.command`
  (`;&|` + `$(){}<>!\`). D'où une commande simple et le chemin de config lu via
  `AUTOMATION_CONFIG_PATH`.
- **Run `dry_run` terminé** : `status: COMPLETED`, `conversation_id: null`,
  `cost: null` — aucune conversation, aucune dépense.
- **Défaut trouvé et corrigé** : un runner `script` **ne marque pas** son run
  terminé tout seul. Sans `fire_callback`, le run restait `RUNNING` jusqu'au
  timeout plateforme (observé ~15 min en « Starting automation »). Après ajout
  de `fire_callback` sur chaque chemin de sortie, le même run termine en
  **5 secondes** (`completed_at` renseigné).
- Le plugin est bien **récupéré depuis GitHub** à la résolution
  (`fetched_plugins[].resolved_ref` = commit de la branche).

Ces constats sont des mesures de plateforme, pas des garanties : les tarifs,
quotas et comportements peuvent changer.

