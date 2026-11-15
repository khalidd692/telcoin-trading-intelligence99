# Capacités cloud réelles — mesures du 15/11/2026

Chaque ligne est une **sonde exécutée**, pas une supposition. Reproductible :

```bash
python -m scripts.agents.protocol.cli capabilities
TEL99_LIVE_PROBES=1 python -m unittest tests.test_agent_protocol.OpenHandsAdapterTests
```

| Capacité | État | Preuve mesurée |
|---|---|---|
| Agent-server local | **VÉRIFIÉ** | `GET /` → HTTP 200, version `1.62.0`, sdk `1.62.0` |
| Création de conversation | **VÉRIFIÉ (route vivante)** | `POST /api/conversations` corps vide → **HTTP 422** (aucune conversation créée, aucun coût) |
| Quota gratuit | **VÉRIFIÉ** | `GET /api/quota/status` → `remaining=10`, `daily_limit=20`, `used_today=10`, reset `2026-11-16T00:00:00Z` |
| Automatisations planifiées | **VÉRIFIÉ (aucune active)** | `GET /api/automation/v1` → `{"automations": [], "total": 0}` |
| Crons GitHub actifs | **VÉRIFIÉ** | `actions/runs?event=schedule` renvoie des runs récents sur `main` (voir ci-dessous) |
| Reprise après interruption | **VÉRIFIÉ (bus)** | étape 6 de la démo : mission `running` → `resume()` → `queued`, prochaine étape intacte |
| Détection d'erreurs | **VÉRIFIÉ (bus)** | étape 5 et 7 de la démo : erreur enregistrée, code, `retryable`, `fatal` |
| Anti-boucle | **VÉRIFIÉ (bus)** | plafond 3 tentatives/étape et 50 étapes/mission, testés (`test_step_cap_prevents_runaway`) |

## Exécution « ordinateur éteint »

- **VÉRIFIÉ, partiel et honnête** : des workflows GitHub Actions **planifiés**
  tournent sur `main` sans le PC (runs récents observés). Mais **aucune
  automatisation OpenHands Cloud n'est active** (`total: 0`) : la partie
  « mission distribuée orchestrée par OpenHands » **ne tourne pas encore** sans
  intervention. Le bus fournit le substrat (enveloppes sur disque + reprise),
  pas un planificateur cloud.
- Les **crons GitHub sont des workflows du dépôt**, pas des agents IA : ils font
  de la validation/publication en lecture seule, pas des missions d'agents.

## Boucles incontrôlées

- Le bus **plafonne** : `MAX_STEPS_PER_MISSION = 50`, `MAX_ATTEMPTS_PER_STEP = 3`.
- Une étape fatale échoue **immédiatement** ; une étape non fatale est retentée
  puis échoue **déterminstiquement**. Aucun chemin ne reboucle sans borne.

## Ce qui n'est PAS vérifié (à ne pas déclarer opérationnel)

- **Kilo** : aucun composant dans le dépôt → `connected: false`, non vérifié.
- **Planification d'une mission d'agents sans le PC** : pas d'automation
  OpenHands active ; ce serait la prochaine étape (créer une automation qui
  appelle le bus), non faite ici.
- **Modèles gratuits** : le routeur refuse tout run réel car aucune disponibilité
  n'est `verified` (fail-closed).
