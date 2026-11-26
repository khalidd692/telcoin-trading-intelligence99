---
name: local-multifile-production
description: Procédure réutilisable pour produire, vérifier et réparer une application multifichiers avec des agents locaux bornés (Ollama 7-9B sur CPU, sans modifier le superviseur TEL99).
---

# Production multifichiers autonome par agents locaux (Procédure capitalisée)

Ce Skill formalise les règles empiriques validées lors de la mise en service d'AI Radar avec le superviseur TEL99 (`autonomy_runtime.Runtime`) et `gemma4:e4b-tel99-8k` sur PC 16 Go RAM (concurrence = 1). Il est prêt à être promu dans `.agents/skills/` de TEL99 après revue propriétaire.

## 1. Décomposition automatique & budgets adaptatifs
- Appeler `mission_planner.assess_and_decompose_mission()` avant exécution : pour un modèle local 7–9B sur CPU, cibler des unités atomiques (30–95 lignes) avec profil adapté via `ollama_native.compute_adaptive_budget()` (`patch`: 1024/90 s, `module`: 2048/180 s, `large_module`: 4096/300 s avec bridage RAM automatique).
- Utiliser le contrat natif `owner="project-file"` d'`autonomy_runtime.Runtime` (`workspace_root`, `allowed_paths`, `target_file`, `specialist`) pour tout projet externe au dépôt TEL99.
- En cas d'échec répété sur une sous-tâche, utiliser `mission_planner.revise_plan_after_failure()` pour re-découper uniquement la tâche échouée en préservant tous les checkpoints `ACCEPTED`.

## 2. Distinction stricte : taxonomie d'erreurs en 6 classes (`autonomy_runtime.ERROR_TAXONOMY`)
Classer chaque échec via `autonomy_runtime.classify_failure()` avant toute réparation :
- `MODEL_ERROR` (logique/signature), `VERIFICATION_ERROR` (assertion/syntaxe détectée par le vérificateur),
- `PROVIDER_ERROR` (HTTP/quota), `ENVIRONMENT_ERROR` (RAM/Docker/timeout/STOP),
- `CONTRACT_ERROR` (périmètre/traversal/chemin hors `allowed_paths`), `COORDINATION_ERROR` (bail/CAS/dépendance).

## 3. Gestion des générations tronquées
- Inspecter `provider.last_metadata.get("done_reason")`.
- Si `done_reason == "length"`, déclencher au plus 1 continuation bornée (<= 640 tokens) à partir de la fin du fichier généré, et tolérer dans `_extract_code()` l'absence de clôture ```` ``` ````.

## 4. Boucle de réparation ciblée
- Fournir à `tel99-dev` :
  1. L'erreur exacte du vérificateur **bornée à `<= 300` caractères**,
  2. Le fichier précédent à réparer **borné à `<= 2 400` caractères**,
  3. Les leçons vérifiées pertinentes issues de `MemoryStore` (`learning_loop.retrieve_lessons`, max 3 notes).
- Ne jamais injecter un dump JSON complet de dataset dans un prompt de réparation.

## 5. Persistance, reprise sans doublon & garde-fou RAM
- Avant lancement, si un modèle local reste chargé en veille et réduit la RAM libre sous `1 400 Mo`, libérer via `POST /api/generate` (`keep_alive: 0`).
- Persister chaque checkpoint CAS (`Runtime`) et fusionner la télémétrie en reprise afin de **ne jamais rejouer une mission déjà `ACCEPTED`**.
- Exécuter systématiquement un audit sécurité statique (`tel99-security`) + une suite de tests indépendants (`tel99-verifier`) avant d'enregistrer une leçon `verified=True` dans `MemoryStore`.
