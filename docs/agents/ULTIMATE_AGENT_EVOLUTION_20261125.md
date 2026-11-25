# TEL99 — Ultimate Agent Evolution (2026-11-25)

Ce document consolide l'évolution globale des 12 agents TEL99 sur la branche isolée `agents/tel99-capability-upgrade-20261125` (dérivée de la livraison stable `0f16ec90` / PR #208), en stricte conformité avec `#214` (dont `issuecomment-7153409310`), `#94` et `AGENTS.md`.

---

## 1. Principe Reuse-First & Architecture Unifiée

Aucun deuxième superviseur, routeur, système de mémoire ou cockpit n'a été créé. Tous les nouveaux modules s'intègrent directement dans l'existant :

| Composant | Statut | Fichier |
|---|---|---|
| Superviseur CAS + contrats natifs `project-file` + taxonomie 6 classes | `INTEGRATED` / `PROVEN` | `scripts/agents/automation/autonomy_runtime.py` |
| Budgets adaptatifs CPU/RAM + `response_format` JSON + continuation sûre | `INTEGRATED` / `PROVEN` | `scripts/agents/automation/ollama_native.py` |
| Décomposition DAG & re-planification dynamique préservant `ACCEPTED` | `INTEGRATED` / `PROVEN` | `scripts/agents/automation/mission_planner.py` |
| Réparation intelligente (diff borné, anti-répétition SHA-256, stratégie) | `INTEGRATED` / `PROVEN` | `scripts/agents/automation/smart_repair.py` |
| Routage par spécialité & repli strictement `LOCAL_FREE` (zéro API payante) | `INTEGRATED` / `PROVEN` | `scripts/agents/automation/provider_router.py` |
| Context Engineering + Graphe AST live (96 fichiers / 867 symboles) + RAG SQLite FTS5 | `INTEGRATED` / `PROVEN` | `scripts/agents/automation/context_engine.py` |
| Raisonnement exploratoire + Métacognition/Calibration + Failure Library + Trajectoires | `INTEGRATED` / `PROVEN` | `scripts/agents/automation/metacognition.py` |
| Agent Academy (calibration vs held-out) + porte de promotion + rollback profil | `INTEGRATED` / `PROVEN` | `scripts/agents/automation/agent_academy.py` |
| Passeports 12 agents (L1–L7) + Champion–Challenger (`improvement.py`) + Mutation + DR + Red-Team | `INTEGRATED` / `PROVEN` | `scripts/agents/automation/evolution_lab.py` |
| Gouvernance 12 rôles (spécialité, mémoire, délégation, escalade, réparation) | `INTEGRATED` / `PROVEN` | `scripts/agents/specialist_dispatch.py` |
| Mémoire segmentée vérifiée (`retrieve_scoped_lessons`) | `INTEGRATED` / `PROVEN` | `scripts/agents/automation/learning_loop.py` |
| Cockpit unifié (métriques réelles, passeports, calibration, failure library, trajectoires) | `INTEGRATED` / `PROVEN` | `scripts/agents/automation/multi_cockpit.py` |

### Limitations artificielles identifiées et supprimées (Harness Engineering P0)
1. **Plafond statique `OllamaNativeProvider` (`1024 tokens / 90 s`)** : causait troncatures et timeouts sur tout module > 65 lignes (`radar-server` 0/4). Remplacé par `TASK_PROFILE_LIMITS` (`patch` 1024/90 s conservé intact, `module` 2048/240 s, `large_module` 4096/360 s).
2. **Faux bridage RAM à `1400 MiB`** : un modèle `gemma4:e4b-tel99-8k` déjà résident en RAM (`keep_alive=120s`) laisse légitimement `1100–1800 MiB` libres sur 13,85 Go visibles ; l'ancien seuil `1400 MiB` rétrogradait silencieusement `module -> patch (90 s)`, coupant `radar-api` à `90,17 s` ! Seuil recalibré à `700 MiB` (zone critique OOM) pour `module` et `2200 MiB` pour `large_module`.
3. **Masquage `TimeoutError` -> `"Ollama native API unavailable"` et rupture de ligne en continuation** : corrigés dans `ollama_native.py` (`ProviderError("Ollama request timed out")` + jointure contextuelle sans casser une ligne terminée par `,`/`(`/`.`/`=`).

---

## 2. Audit Factuel `TEL99-LORA` & Corpus SFT (§22)

Audit direct sur disque (`C:\Users\sabri\Desktop\TEL99-LORA`, Ollama `0.40.16`, aucun réentraînement déclenché) :
- **`adapter_config.json`** : `peft_type: LORA`, `r=16`, `lora_alpha=16`, `peft_version: 0.21.2`, base `unsloth/gemma-4-E4B-it-unsloth-bnb-4bit`, `Gemma4ForConditionalGeneration`.
- **`adapter_model.safetensors`** : `139 602 808` octets (présent, préservé).
- **`tel99-lora-adapter.gguf`** : `66,57 MiB`, en-tête valide `GGUF v3`, `516` tenseurs, `11` métadonnées KV.
- **`gemma-4-E4B-it-Q8_0.gguf`** : `7 813,41 MiB` (~7,63 GiB), en-tête valide `GGUF v3`, `720` tenseurs, `56` métadonnées KV.
- **`Modelfile`** : `FROM gemma4:e4b` + `ADAPTER ./tel99-lora-adapter.gguf`.
- **Constat de blocage & gouvernance (#214)** :
  1. Le chargement dynamique d'adaptateur LoRA GGUF via `Modelfile` Ollama (`FROM gemma4:e4b` + `ADAPTER`) reste bloqué, **mais** le lancement direct via `C:\Users\sabri\Desktop\TEL99-LORA\llama-bin\llama-server.exe --model gemma-4-E4B-it-Q8_0.gguf --lora tel99-lora-adapter.gguf --port 8080 --ctx-size 2048` a été observé actif en direct (`http://127.0.0.1:8080/health` → `{"status":"ok"}`, empreinte **5,02 Go RAM**).
  2. **Contrainte matérielle vérifiée** : faire tourner simultanément ce serveur `llama-server` LoRA Q8 (`5,02 Go`) et Ollama `gemma4:e4b-tel99-8k` (`3,14 Go`) fait chuter la RAM libre à **411 Mo** sur 13,85 Go visibles et provoque des timeouts CPU ; la règle de **concurrence locale = 1 serveur d'inférence à la fois** s'applique à tous les moteurs (`ollama` + `llama-server`).
  3. **Audit corpus (#214)** : sur 453 expériences SFT historiques, **429 ont été exclues** au premier filtre (seulement **24 admissibles**), et les 50 tâches historiques de benchmark ne contiennent que **12 textes distincts normalisés**.
  4. **Décision factuelle** : **NE PAS promouvoir LoRA** en production tant qu'un jeu d'évaluation indépendant (train/dev/test séparés par familles, dédupliqué, sans fuite ni secrets) et une évaluation comparative (Gemma base vs Harness/RAG/Skills vs LoRA) en fenêtre mono-inférence dédiée n'ont pas démontré un gain supérieur sans régression. Tous les fichiers `TEL99-LORA` restent intacts.

---

## 3. Matrice d'Évaluation des Technologies (§27)

Chaque technologie a été évaluée selon sa compatibilité Windows/16 Go RAM, son coût, sa licence, son alternative existante dans TEL99 et son bénéfice mesurable :

| Technologie | Licence | État local | Alternative TEL99 existante | Décision | Justification |
|---|---|---|---|---|---|
| **SQLite FTS5** | Domaine public (stdlib Python 3.12) | Installé (`ENABLE_FTS5=True`) | `MemoryStore.search()` token overlap | **ADOPT** | Déjà intégré dans `context_engine.HybridMemoryIndex` (BM25 + boost vérifié/rôle, 0 dépendance externe, source unique = JSON `MemoryStore`). |
| **Ollama JSON `format` (natif)** | MIT | Installé (`ollama 0.40.16`) | Extraction regex markdown | **ADOPT** | Intégré dans `ollama_native.OllamaNativeProvider.complete(..., response_format=...)` + `validate_structured_json()`. |
| **Pydantic** | MIT | Déjà installé | Validation stdlib stricte | **ADOPT (optionnel)** | Utilisable pour schémas complexes sans imposer de rupture sur les contrats légers stdlib existants. |
| **AST stdlib (Graphe de code)** | PSF (stdlib) | Intégré | Lecture manuelle de fichiers | **ADOPT** | `context_engine.build_code_graph()` cartographie 96 fichiers / 867 symboles en < 1 s sans dérive. |
| **Mutation Testing AST isolé** | Interne TEL99 | Intégré | Tests unitaires seuls | **ADOPT** | `evolution_lab.run_mutation_check()` prouve que les tests tuent réellement les mutants (score 1.0 sur tests ciblés). |
| **AgentDojo (principes Red-Team)** | MIT (conceptuel) | Intégré (7 tests) | Tests sécurité statiques | **ADOPT (principes)** | `evolution_lab.run_red_team_suite()` exécute 7 scénarios adversariaux isolés (7/7 PASS) sans cible externe. |
| **METR / Terminal-Bench (méthodes)** | Recherche ouverte | Intégré (passeports) | Durée brute de campagne | **ADOPT (méthodes)** | Mesure de l'horizon de tâche (lignes/complexité/minutes utiles) distinguée des benchmarks officiels. |
| **AgentTuning (trajectoires)** | Apache-2.0 (principes) | Intégré | Logs bruts dispersés | **ADOPT (principes)** | `metacognition.TrajectoryRecorder` enregistre des trajectoires vérifiées et expurgées de tout secret. |
| **GEPA / DSPy** | MIT | Non installé | `improvement.py` + `agent_academy.py` | **DEFER (lib) / ADOPT (Champion–Challenger)** | Le mécanisme Champion–Challenger statistique (test des signes apparié `p <= 0.05`) est déjà intégré via `evolution_lab.run_champion_challenger()` sans surconsommation de quota Gemini ; `dspy` différé tant qu'un grand corpus held-out n'est pas constitué. |
| **Tree-sitter** | MIT | Non installé | AST Python + `node --check` | **DEFER** | Inutile tant que les projets principaux sont Python/JS simples ; à réévaluer si un projet polyglotte massif (TS/Rust/Go) est confié aux agents. |
| **llama.cpp GBNF** | MIT | Via Ollama `format` | Ollama `format` JSON Schema | **DEFER** | Ollama 0.40.16 expose déjà la contrainte JSON Schema nativement ; GBNF brut inutile sauf besoins hors JSON. |
| **Hypothesis** | MPL-2.0 | Non installé | Tests négatifs/limites manuels | **DEFER** | Pertinent pour un lot ultérieur de tests génératifs intensifs sur parseurs financiers ; non requis à ce stade. |
| **Playwright** | Apache-2.0 | Installé | `HTTPConnection` + `browser` subagent | **ADOPT (validation UI)** | Disponible pour vérifications UI isolées ; priorité maintenue aux API déterministes. |
| **Embeddings locaux / Vector DB** | Divers | Non installé | SQLite FTS5 BM25 | **DEFER** | Aucun gain démontré sous < 500 entrées mémoire ; FTS5 BM25 consomme 0 Mo RAM additionnelle. |
| **Unsloth / QLoRA** | Apache-2.0 | Artefacts existants `TEL99-LORA` | Harness + RAG + Skills | **DEFER** | Ne pas relancer Colab tant que le corpus (24/453) et l'intégration Ollama ne sont pas assainis. |
| **DPO / GRPO** | Recherche | Non installé | Trajectoires + Failure Library | **DEFER** | Différé jusqu'à disposer de centaines de trajectoires vérifiées avec récompenses objectives et GPU dédié. |
| **MCP / A2A / OpenTelemetry** | Ouvert | Natif Antigravity / JSONL local | Bus CAS + Cockpit + JSONL | **DEFER** | Observabilité locale déjà couverte ; A2A/OTel non justifiés pour 1 PC mono-inférence. |
| **SWE-bench (complet)** | MIT | Non installé | Agent Academy held-out + AI Radar | **REJECT (local 16 Go)** | Trop lourd en Docker/disque/CPU pour un PC 16 Go ; principes d'évaluation indépendante adoptés dans Academy. |

---

## 4. Commandes Quotidiennes & Procédure de Restauration (§24 & §36)

```powershell
# 1. Suite de tests Evolution + Capacités + SDK + Vérification des 12 rôles
python -B -m unittest tests.test_ultimate_evolution tests.test_capability_upgrades -v
python -B scripts/agents/render_agents.py --check

# 2. Audit Red-Team (7 contrôles adversariaux isolés) & Restauration DR en bac à sable
python -B -c "import json; from scripts.agents.automation import evolution_lab; print(json.dumps(evolution_lab.run_red_team_suite(), indent=2))"

# 3. Lancer le Cockpit TEL99 (lecture seule par défaut, http://127.0.0.1:8765/)
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Cockpit

# 4. Lancer AI Radar (une commande, http://127.0.0.1:8780/)
pwsh -NoProfile -File C:\Users\sabri\Desktop\AI_RADAR\start-ai-radar.ps1

# 5. Rollback instantané d'un profil agent ou de la branche
# - Profil : agent_academy.rollback_agent_profile_version(store_dir, target_version="champ-v1")
# - Git    : git checkout agents/tel99-antigravity-v2-20261124 (branche stable PR #208 intacte)
```
