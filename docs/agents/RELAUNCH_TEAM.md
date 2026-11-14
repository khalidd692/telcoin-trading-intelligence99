# TEL99 — Relancer l'équipe multi-agents dans une nouvelle session

Procédure pour retrouver une équipe TEL99 fonctionnelle et sécurisée après
fermeture d'une session OpenHands, sans rien reconstruire.

Tout est en **lecture seule** : aucune modification du code du terminal, aucun
déploiement, aucun ordre (réel ou simulé), aucun secret dans le dépôt.

## Ce qui est enregistré

| Élément | Chemin |
|---|---|
| Définitions actives (3) | `.agents/agents/tel99-{dev,analyst,verifier}.md` |
| Définitions réservées (9) | `.agents/agents/reserve/*.md` (non chargées) |
| Configuration unique | `scripts/agents/team_config.py` |
| Générateur des définitions | `scripts/agents/render_agents.py` |
| Lanceur du pilote | `scripts/agents/run_pilot.py` |
| Garde-fou PreToolUse | `scripts/agents/guard/guard.py` |
| Vérificateur post-run | `scripts/agents/verify_delegation.py` |
| Tests automatisés | `tests/test_agent_team.py` |

## Prérequis

- Une session OpenHands dont le serveur d'agents tourne sur `http://localhost:60000`.
- Un profil de modèle gratuit enregistré, par défaut
  `~/.openhands/profiles/openhands_deepseek-v4.1-flash.json`.
- Le dépôt cloné et la branche `agents/hermes-simple-team-20261114` extraite.

Le lanceur lit les identifiants du modèle **au moment de l'exécution** depuis le
profil ; aucun secret n'est écrit dans le dépôt.

## Étape 1 — Vérifier la configuration et les tests

```bash
cd telcoin-trading-intelligence99
python -m unittest discover -s tests -p 'test_agent_team*.py' -v
python scripts/agents/render_agents.py --check
```

`render_agents.py --check` échoue si un fichier d'agent a dérivé de
`team_config.py`. Pour corriger : `python scripts/agents/render_agents.py`.

## Étape 2 — Inspecter le lancement (sans créer d'agent)

```bash
python scripts/agents/run_pilot.py --dry-run
```

Vérifiez dans la sortie : noms uniques suffixés (`tel99-dev-<HHMMSS>`), outils
réduits à `terminal`, `permission_mode: confirm_risky`, hook `pre_tool_use` et
`sub_agent_scope: {tools: true}`.

## Étape 3 — Lancer l'équipe (lecture seule)

```bash
python scripts/agents/run_pilot.py --wait
```

Le lanceur imprime l'identifiant de conversation et les noms d'agents. Chaque
exécution utilise un suffixe d'heure distinct, ce qui évite la collision du
registre global d'agents (voir « Pourquoi des noms uniques »).

## Étape 4 — Vérifier la délégation

```bash
python scripts/agents/verify_delegation.py <conversation_id> --suffix <HHMMSS>
```

Attendu : `PASS`, chaque sous-agent en `terminal` seul, garde-fou propagé,
politique `ConfirmRisky`.

## Limites de consommation

Réglables par variables d'environnement, sans toucher au code :

| Variable | Défaut | Effet |
|---|---|---|
| `TEL99_MAX_BUDGET_USD` | 1.0 | budget du coordinateur (USD) |
| `TEL99_MAX_ITERATIONS` | 30 | itérations du coordinateur |
| `TEL99_AGENT_MAX_BUDGET_USD` | 0.25 | budget par sous-agent |
| `TEL99_AGENT_MAX_ITERATIONS` | 10 | itérations par sous-agent |
| `TEL99_MAX_BUDGET_CEILING_USD` | 5.0 | plafond dur, jamais dépassé |
| `TEL99_LLM_PROFILE` | openhands_deepseek-v4.1-flash | profil du modèle |

Exemple économique :

```bash
TEL99_MAX_BUDGET_USD=0.2 TEL99_AGENT_MAX_BUDGET_USD=0.05 \
  python scripts/agents/run_pilot.py --wait
```

## Pourquoi des noms uniques

Le SDK conserve un registre d'agents **global au processus**, où le premier nom
enregistré gagne. Réutiliser un nom entre deux exécutions applique
silencieusement la **première** définition. Un suffixe d'heure par exécution rend
chaque enregistrement distinct. `verify_delegation.py` contrôle que les noms
déclarés portent bien le suffixe attendu.

## Sécurité — le garde-fou

`scripts/agents/guard/guard.py` est un hook `PreToolUse` : il lit un événement
JSON sur l'entrée standard et renvoie le code de sortie **2** pour bloquer, **0**
pour autoriser. Il bloque les écritures de fichiers, les commandes Git
mutantes, les installations de paquets, les appels réseau mutants, les
déploiements et toute commande liée à un ordre de trading. Il n'inspecte que
l'outil `terminal` ; les autres outils sont limités par la liste d'outils de
l'agent.

Le garde-fou est une couche de défense en profondeur : le contrôle principal
reste la liste d'outils `terminal` seul, plus `sub_agent_scope`.

## Activer une spécialisation réservée

Les 9 rôles supplémentaires vivent dans `.agents/agents/reserve/`. Le SDK ne
charge que les fichiers `*.md` de premier niveau, donc aucun n'est actif.

Pour en activer un :

1. Déplacer son fichier d'un niveau : `git mv .agents/agents/reserve/tel99-cloud.md .agents/agents/`
2. L'ajouter à `ACTIVE_AGENTS` dans `scripts/agents/team_config.py`.
3. Relancer `render_agents.py` et les tests.

Aucun rôle réservé ne s'exécute, n'est planifié ni ne détient de permission tant
que cette activation explicite n'a pas eu lieu.

## Ce qui n'est pas automatisé

- Aucune planification cloud (automation) n'est créée par ces fichiers.
- Aucun webhook, aucun cron.
- Aucune fusion de pull request.
- Aucun ordre de trading, réel ou simulé.

L'automatisation planifiée existe côté OpenHands Cloud, mais elle n'est **pas**
configurée ici.
