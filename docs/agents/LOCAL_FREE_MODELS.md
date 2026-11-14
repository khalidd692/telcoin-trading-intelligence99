# Faire tourner l'équipe TEL99 avec des modèles gratuits sur votre PC

Objectif : pouvoir relancer les agents TEL99 sans dépendre d'OpenHands Cloud ni
d'un service payant. Trois pistes, du plus simple au plus intégré. Aucune n'est
requise pour la sauvegarde GitHub ; ce document explique comment continuer à
faire travailler l'équipe localement.

Rappel des règles TEL99 : lecture seule, aucun ordre (réel ou simulé), aucun
déploiement, aucune installation payante. Les agents définis dans
`.agents/agents/` n'ont que l'outil `terminal` et un garde-fou PreToolUse.

## Option 1 — Ollama (le plus simple)

Ollama expose une API compatible OpenAI sur `http://localhost:11434/v1`.

```bash
# Installation (gratuite) puis un modèle léger
ollama pull qwen2.5-coder:7b      # bon compromis code/outils
ollama serve                       # écoute sur 127.0.0.1:11434
```

Le SDK OpenHands attend une configuration LLM. Pour un lancement manuel, le
profil ressemble à ceci (à enregistrer dans
`~/.openhands/profiles/ollama-local.json`, **jamais** commité) :

```json
{
  "model": "openai/qwen2.5-coder:7b",
  "base_url": "http://localhost:11434/v1",
  "api_key": "ollama",
  "native_tool_calling": true
}
```

Puis : `TEL99_LLM_PROFILE=ollama-local python scripts/agents/run_pilot.py --dry-run`
pour vérifier, et sans `--dry-run` pour lancer.

## Option 2 — LM Studio

LM Studio fournit un serveur local compatible OpenAI (par défaut
`http://localhost:1234/v1`). Chargez un modèle quantifié (par ex. Qwen2.5-Coder
7B Q4), démarrez le serveur, puis réutilisez le même profil que ci-dessus en
changeant `base_url` :

```json
{
  "model": "openai/<nom-du-modele-charge>",
  "base_url": "http://localhost:1234/v1",
  "api_key": "lm-studio",
  "native_tool_calling": true
}
```

## Option 3 — Hermes

« Hermes » ici désigne le nom de l'équipe (voir
`docs/agents/HERMES_SIMPLE_TEAM.md`), pas un logiciel distinct. Deux
interprétations possibles :

- **Modèle Hermes (NousResearch)** : un modèle de la famille Hermes peut être
  servi par Ollama ou LM Studio (`ollama pull hermes3`), avec la même
  configuration que ci-dessus. Vérifiez que le modèle supporte l'appel d'outils
  (`native_tool_calling`) ; sinon, l'agent ne pourra pas utiliser `terminal`.
- **Équipe Hermes TEL99** : elle tourne déjà sur le modèle gratuit
  `openhands/deepseek-v4.1-flash`. Pour la relancer, voir
  `docs/agents/RELAUNCH_TEAM.md`.

## Ce que le garde-fou protège encore en local

Le garde-fou `scripts/agents/guard/guard.py` est un hook PreToolUse indépendant
du modèle. Même avec un modèle local, il bloque les commandes de mutation
(suppression, `git` écrivain, installations, écritures réseau, ordres). Le
modèle choisi n'affaiblit pas cette barrière.

## Limites honnêtes

- Un modèle local de 7B est **moins fiable** qu'un modèle cloud pour le
  raisonnement long : attendez-vous à plus d'erreurs de jugement, mais le
  garde-fou reste la barrière déterministe.
- L'appel d'outils (`native_tool_calling`) n'est pas supporté par tous les
  modèles locaux. Sans lui, les agents ne peuvent pas exécuter `terminal`.
- Aucune de ces options n'a été testée dans cet environnement (pas d'Ollama ni
  de LM Studio ici). Ce sont des pistes documentées, pas des résultats vérifiés.
