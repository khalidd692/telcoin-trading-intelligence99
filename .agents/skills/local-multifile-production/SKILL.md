---
name: local-multifile-production
description: Procédure réutilisable pour produire, vérifier et réparer une application multifichiers avec des agents locaux bornés (Ollama 7-9B sur CPU, sans modifier le superviseur TEL99).
---

# Production multifichiers autonome par agents locaux (Procédure capitalisée)

Ce Skill formalise les règles empiriques validées lors de la mise en service d'AI Radar avec le superviseur TEL99 (`autonomy_runtime.Runtime`) et `gemma4:e4b-tel99-8k` sur PC 16 Go RAM (concurrence = 1). Il est prêt à être promu dans `.agents/skills/` de TEL99 après revue propriétaire.

## 1. Décomposition automatique selon le budget du modèle local
- Pour un modèle local 7–9B sur CPU avec `OllamaNativeProvider` (`max_tokens <= 1024`, `timeout <= 90 s`), découper chaque module applicatif en **unités atomiques de 30 à 65 lignes** (1 à 3 fonctions par fichier Python, séparation `render.js` / `app.js` en frontend).
- Chaque unité expose un contrat d'interface explicite (signatures, endpoints JSON, IDs DOM) et une façade de composition si nécessaire.

## 2. Distinction stricte : erreur modèle vs erreur d'environnement
Toujours classer chaque échec avant de décider d'une réparation ou d'un correctif d'outillage :
- **Erreurs d'environnement / harness** (à corriger dans le lanceur/extracteur, jamais imputables au modèle) :
  - `validate_contract()` / `validate_scope()` trop restrictif pour un projet externe,
  - `ProviderError` dû à un dépassement de bornes (`max_tokens > 1024` ou `timeout > 90 s`),
  - Saturation RAM hôte au démarrage (`available_memory_mib < 1024` avant `keep_alive=0`),
  - Extracteur de code ne gérant pas une balise markdown ```` ```lang ```` non fermée après troncature,
  - Dump d'erreur non borné (> 10 Ko) saturant le prompt de réparation.
- **Erreurs du modèle** (à traiter par la boucle de réparation autonome `tel99-verifier` -> `tel99-dev`) :
  - `AttributeError`, `AssertionError`, mauvais noms de champs (`speed` au lieu de `avg_latency_s`), validation manquante sur entrées invalides, syntaxe JS/Python erronée.

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
