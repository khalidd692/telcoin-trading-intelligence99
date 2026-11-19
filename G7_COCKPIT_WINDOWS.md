# Kilo G7 — Cockpit d'état (Windows)

## Aperçu

Le cockpit G7 permet de surveiller et contrôler les workers Kilo depuis une
session Windows PowerShell. Il maintient un registre d'état par worker dans
`.kilo/cockpit/<worker_id>.json`.

## États

| État | Signification |
|------|---------------|
| `CONNECTED` | Worker connecté et disponible |
| `IDLE` | Connecté, aucune mission en cours |
| `BUSY` | Mission en cours d'exécution |
| `BLOCKED` | Mission bloquée (dépendance, acteur non connecté, erreur) |
| `STOPPED` | Arrêt demandé, plus de nouvelles missions |

## Commandes PowerShell

### STATUS — consulter l'état d'un worker

```powershell
# État d'un worker spécifique
python scripts/kilocli/g7_cockpit.py status --worker kilo-worker-01

# État de tous les workers
python scripts/kilocli/g7_cockpit.py status --all
```

Exemple de sortie :

```json
{
  "worker_id": "kilo-worker-01",
  "state": "BUSY",
  "detail": "Exécution de mission-001-audit-receiver par tel99-analyst",
  "mission_id": "mission-001-audit-receiver",
  "updated_at": "2026-11-19T15:45:00Z"
}
```

### STOP — demander l'arrêt d'un worker

```powershell
python scripts/kilocli/g7_cockpit.py stop --worker kilo-worker-01
```

## Intégration avec le receveur

Le receveur GitHub (`scripts/kilocli/github_receiver.ps1`) met à jour le cockpit
à chaque réception :

- À la réception d'une mission : état `BUSY`, `mission_id` renseigné
- Après l'ACK : état `IDLE`
- En cas de conflit CAS : état `BLOCKED`
- En cas d'erreur fatale : état `STOPPED`

## G4 — Mémoire inter-sessions

L'état persiste dans `.kilo/memory/<session_id>.json`. Une nouvelle session
peut recharger l'état de la précédente sans aucun copier-coller :

```powershell
python scripts/kilocli/g4_memory.py load --session session-20261119-152535
```

## G5 — Rollback contrôlé

Les changements sont enregistrés dans `.kilo/changelog/` avec sauvegarde dans
`.kilo/backups/`. Jamais de `git reset --hard` :

```powershell
# Rollback d'un changement identifié
python scripts/kilocli/g5_rollback.py rollback --change-id <change_id>
```

## Fichiers

- `.kilo/cockpit/<worker_id>.json` — état courant d'un worker
- `.kilo/memory/<session_id>.json` — état persistant d'une session
- `.kilo/changelog/<change_id>.json` — registre des changements appliqués
- `.kilo/backups/` — copies de sauvegarde avant modification
