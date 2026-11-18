# TEL99 — Lanceur de mission natif (`scripts/agents/native/`)

**Issue #86 / directive de souveraineté (18/11/2026).** Ce document décrit la
plus petite amélioration qui permet de lancer **une vraie mission bornée depuis
une commande native de notre projet**, avec un **fournisseur de modèle
interchangeable**, sans ouvrir Hermes Desktop, Kilo Agent Manager ni OpenHands
Cloud.

_Statut : code + tests livrés en PR draft sur branche isolée. Aucune fusion,
aucun déploiement, aucun cron, aucun ordre (réel ou simulé), aucun secret._

## 1. Ce qui est livré

| Fichier | Rôle |
|---|---|
| `scripts/agents/native/provider.py` | Contrat `ModelProvider` + `ScriptedProvider` (offline) + `OpenAICompatibleProvider` (HTTP réel, `urllib`) |
| `scripts/agents/native/mission.py` | Noyau borné : quota fail-closed, idempotence, verdict déterministe, journal |
| `scripts/agents/native/cli.py` | Entrée native : `python -m scripts.agents.native.cli {demo,run,recall}` |
| `tests/test_agent_native.py` | 33 tests stdlib, sans réseau ni LLM |
| `.github/workflows/tel99-agent-team-audit.yml` | Étape de test ajoutée (additif) |

**Aucune reconstruction** : le noyau réutilise `intelligence/router.py`,
`intelligence/memory.py`, `intelligence/catalog.py`, `protocol/store.py` et
`team_config.FREE_MODEL_IDS`. Le bus, la mémoire et le routeur existants sont
inchangés.

## 2. Commande native (preuve)

```bash
# Démonstration hors-ligne, déterministe : un vrai module Python est produit,
# de vrais tests sont relancés, le verdict est calculé par le noyau.
python -m scripts.agents.native.cli demo
# -> DEMO: PASS
```

La démo prouve, en une commande et sans réseau :

- un **artefact Python réel** (`mathutils.py`) est écrit sur disque ;
- les **contrôles déterministes** (`py_compile`, `assert double(21) == 42`) sont
  relancés par le noyau, pas par le modèle ;
- un **second lancement de la même mission ne rappelle pas le fournisseur**
  (`second_provider_calls: 0`) — pas de double run ;
- le **fixture négatif** où le modèle écrit `VERDICT: PASS` mais où le contrôle
  échoue donne `verdict: FAIL` — le verdict ne vient jamais du texte du modèle ;
- la **mémoire est rappelée depuis une session neuve** (`recalled_from_fresh_session`).

## 3. Mission réelle (modèle interchangeable)

```bash
# Le modèle, l'URL et la clé sont lus au runtime et NE SONT PAS commités.
TEL99_NATIVE_MODEL=openhands/deepseek-v4.1-flash \
TEL99_NATIVE_BASE_URL=http://localhost:1234/v1 \
python -m scripts.agents.native.cli --quota 18 \
  run --mission-id my-fix --mission "Ecris mathutils.py avec add et double." \
  --artifact mathutils.py
```

Changer de fournisseur ne change **pas** le noyau : le contrat `ModelProvider`
n'exige qu'un attribut `name` et une méthode `complete(system, prompt)`. Un test
d'intégration HTTP réel (`HttpContractTests`) prouve que le **même noyau** tourne
avec le `ScriptedProvider` et avec l'`OpenAICompatibleProvider` face à un serveur
local qui parle le protocole OpenAI.

### Fournisseurs gratuits

Seuls les modèles de `team_config.FREE_MODEL_IDS` sont acceptés (`0 modèle
payant`). Un endpoint non-local exige une clé (fail-closed). L'endpoint cloud
géré par OpenHands **refuse les clients externes par politique** (HTTP 403) :
lancer une mission réelle contre ce proxy depuis notre CLI est donc **BLOCKED** ;
la démonstration la plus forte disponible ici est le contrat HTTP local réel.

## 4. Règles de sûreté encodées (et testées)

| Règle | Où | Test |
|---|---|---|
| Quota inconnu ⇒ STOP (jamais « suffisant ») | `mission._check_quota` | `test_quota_unknown_refuses` |
| Quota < 12 ⇒ STOP | idem | `test_quota_below_reserve_refuses` |
| Pas de double run (idempotent sur `mission_id`) | `mission.run` (lecture du store) | `test_idempotency_no_double_run` |
| Pas de double run concurrent (verrou atomique `O_EXCL`) | `mission._claim` | `test_concurrent_second_launch_is_refused_by_atomic_claim` |
| Un run refusé ne laisse aucun verrou | `mission.run` (claim après préconditions) | `test_refused_run_leaks_no_claim` |
| Le verdict ne vient jamais du modèle | `mission.decide_verdict` | `test_negative_fixture_...` |
| `mission_id` / artefacts sans traversée de chemin | `mission.MissionSpec.validate` | `test_unsafe_mission_id_is_rejected` |
| Le journal ne contient aucun secret | `mission._persist` | `test_journal_never_contains_a_secret` |
| Les commandes lancées sont guard-clean | `mission.Check.run` | `test_kernel_check_commands_are_guard_clean` |
| Échec fournisseur ⇒ FAIL, pas crash | `mission.run` | `test_provider_error_yields_fail_not_crash` |
| Mémoire isolée par projet | `memory.MemoryStore` | `test_memory_is_project_isolated` |

`run --project projet-b` et `recall --project projet-b` sélectionnent le
même espace de projet. Les noms acceptent des lettres minuscules, des
chiffres et des tirets simples entre les groupes. `common` est réservé à
la mémoire partagée. L’espace par défaut `tel99` conserve ses chemins de
stockage. Les autres projets stockent leurs artefacts sous
`.tel99-native-state/artifacts/_projects/<projet>/<mission>`.

La CLI renvoie `0` pour un succès ou une préparation à blanc, `2` pour
un refus avant exécution et `3` pour un résultat `FAIL` ou `NEEDS_HUMAN`.
Une mission relue conserve le code de sortie de son verdict.

## 5. Ce qui reste une action humaine

- **Lancer** une mission réelle (le propriétaire ou l'opérateur).
- Fournir `TEL99_NATIVE_API_KEY` / l'endpoint — jamais dans le dépôt.
- Toute fusion, tout déploiement, toute activation de planificateur.
- La rotation du jeton exposé en PR #88 (voir le rapport d'audit).

## 6. Limites honnêtes

- Aucun runtime de modèle **local** prouvé (les LLM locaux sont écartés par
  décision du propriétaire).
- Le proxy de modèle cloud géré n'est pas accessible à un client externe : la
  mission réelle « cloud » est **BLOCKED** ici, remplacée par un test de contrat
  HTTP local réel.
- Le noyau exécute des contrôles déterministes ; il **ne juge pas** la qualité
  métier d'un livrable. `NEEDS_HUMAN` reste le verdict quand rien n'est
  démontrable.
