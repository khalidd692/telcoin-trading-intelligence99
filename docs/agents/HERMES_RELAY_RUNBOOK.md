# RUNBOOK — Relais Hermes GitHub → superviseur #124 (branche hermes/relay-github-adapter-20261120)

Statut : **TESTÉ + DÉMO LIVE RÉUSSIE** (2 missions synthétiques enchaînées automatiquement,
reprise sans doublon). Pas un service permanent : chaque exécution est bornée et lancée explicitement.

## Architecture (REUSE FIRST, aucun second superviseur)

```
GitHub (issue #94, commentaires hermes-mission/v1 approuvés par khalidd692)
  → github_mission_source.py   (admission authentifiée : auteur, mandat épinglé, expiration, fingerprint)
  → autonomy_runtime.Runtime   (superviseur #124 INCHANGÉ hors allowlist owner additive kilo/hermes)
      claim CAS → Inbox ACK → RUNNING → worker → WORKER_EXITED → vérificateur → mémoire → ACCEPTED/REJECTED
  → hermes_executor.py         (CLI Hermes one-shot, modèle gratuit épinglé, session_id + coût 0 vérifiés)
  → hermes_verifier.py         (subprocess fixe indépendant, 5 contrôles dont SHA-256 approuvé)
  → hermes_github_adapter.py   (publication ACK/résultat idempotente CAS + journal relay-events.jsonl)
```

## Commandes (Windows, bash git-bash, chemins natifs C:/...)

```bash
cd C:/Users/sabri/Desktop/telcoin-trading-intelligence99-worktree-hermes-relay
python -B scripts/agents/automation/hermes_github_adapter.py run \
  --state C:/Users/sabri/AppData/Local/hermes-tel99/autonomous/relay-live \
  --issue 94 --mandate-issue 67 --mandate-comment 7024804657 \
  --once --seconds 570 \
  --cli-exe C:/Users/sabri/AppData/Local/hermes/installs/8ddc43e438efe657/environments/20f33f9fbe1641249cc951b62c3c0ce1/venv/Scripts/hermes.exe
# status / stop :
python -B scripts/agents/automation/hermes_github_adapter.py status --state <state>
python -B scripts/agents/automation/hermes_github_adapter.py stop   --state <state>
```

- `--once` : un seul poll (toutes les missions admissibles sont traitées dans ce poll, dépendances incluses).
- Sans `--once` : polls toutes les 10 s jusqu'à `--seconds` (1..3600) ou STOP.
- `--no-publish` : exécution locale sans publication GitHub (le journal reste écrit).
- État durable : `<state>/ledger/` (CAS), `<state>/relay-events.jsonl`, `<state>/memory/`.
  Ne jamais mettre cet état dans un scratch éphémère.

## Modèle d'approbation (ne pas contourner)

Un commentaire n'est exécutable que si : auteur GitHub ∈ {khalidd692} ; bloc `hermes-mission/v1`
avec `mission.owner=hermes`, `project=synthetic`, `synthetic_data=true`, spécialiste ∈
{tel99-analyst, tel99-dev, tel99-verifier} ; `approval.mandate_comment_id` égal au mandat épinglé
en ligne de commande (vérifié authentiquement auteur propriétaire) ; `expires_at` futur ;
`approval.mission_sha256` égal au fingerprint du contrat ; contrat valide selon `validate_contract`.
`expected_sha256` épingle l'artefact exact attendu : le vérificateur indépendant rejette tout écart.
Les événements publiés par le relais (`hermes-relay-event/v1`) ne sont jamais réadmis (anti-boucle).

## Quotas / coûts

- Modèles autorisés : `meituan/longcat-2.5:free`, `upstage/solar-mini4:free` (provider `nous`).
  Aucun modèle local, aucun repli payant.
- Preuve de coût : ligne `session_model_usage` de `state.db` (lecture seule) — estimated/actual
  cost_usd doit être 0 ; sinon `NONZERO_COST_REFUSED`.
- 429/quota → `BLOCKED_PROVIDER_RATE_LIMIT`, checkpoint BLOCKED durable, cooldown borné
  (60..3600 s) dans `<state>/provider-cooldown.json`. Pas de boucle de retry.
- Reprise d'un BLOCKED : relancer la commande après expiration du cooldown (décision opérateur).

## Reprise / anti-doublon (sémantique #124, vérifiée live)

- Crash pendant RUNNING → au redémarrage : `AWAITING_HUMAN` (« uncertain worker outcome; never replay »).
  Jamais de second appel modèle. Réconciliation humaine requise (nouvelle mission ou reset explicite).
- Crash après WORKER_EXITED → reprise de la vérification sans nouvel appel worker.
- ACK/publications : dédup CAS durable par mission/phase ; un redémarrage ne republie rien.
  Durcissement F3 : avant tout POST, scan des événements déjà publiés sur GitHub
  (`existing_events`) — recovery sans repost si crash entre POST et CAS ; scan
  indisponible → publication différée (jamais de blind-post). Fenêtre résiduelle
  at-least-once assumée : le marqueur `hermes-relay-event/v1` empêche toute
  ré-admission d'un événement dupliqué.
- STOP : fichier `stop.request` ; le worker est tué, aucun replay automatique.

## Phase 2 — sessions bornées et frontière d'approbation (GO 2026-11-20)

- **Pagination complète bornée** : `fetch_comments` traverse jusqu'à 100 pages
  (10 000 commentaires) ; cap atteint sur page pleine → `ValueError` fail-closed
  (jamais de file tronquée silencieusement). Le scan anti-duplication
  `existing_events` utilise la même traversée. Tests >300 commentaires inclus.
- **Coût strictement nul** : `estimated_cost_usd == 0.0` ET `actual_cost_usd == 0.0`
  exigés (executor + vérificateur). Un coût réel INCONNU (`None`) est REFUSÉ
  (`COST_UNKNOWN_OR_NONZERO_REFUSED`) — inconnu ≠ preuve de zéro.
- **Frontière d'approbation** (`approval.origin`) :
  - `delegated-mandate` (défaut, rétro-compatible démo) : publiées via le gh
    authentifié du propriétaire sous mandat GO épinglé ; **structurellement
    limitées aux missions texte synthétiques** (contrat engine + worker sans
    outils) — aucune permission nouvelle, aucune opération sensible possible.
  - `owner-direct` : exige en plus un artefact local
    `<state>/owner-approvals/<mission_id>.json`
    `{approved_by: khalidd692, channel: owner-local, mission_sha256: <fingerprint>}`
    que l'adaptateur **lit seulement, n'écrit jamais**. Limite résiduelle assumée :
    même compte utilisateur sur la machine — la séparation est procédurale et
    auditée ; une séparation cryptographique exigerait un canal/credential
    réservé au propriétaire (hors périmètre actuel).
  - Les modifications productives (code, permissions, sensible) restent hors du
    contrat synthétique : elles passent par le flux dev normal (branche isolée,
    tests, revue, PR brouillon) sur autorisation humaine explicite, jamais par
    auto-approbation IA dans la file.
- **Backlog → propositions** : `hermes_github_adapter.py propose --state <s>
  --issue 94 [--task I-02] [--backlog chemin] [--no-publish]` publie des
  événements `hermes-relay-proposal/v1` (PROPOSED, jamais exécutables, jamais
  réadmis comme approbations). Dédup CAS par ensemble de tâches.
- **Session bornée** : `run --seconds 1..7200 --max-tasks 1..20`. Le budget de
  session compte les missions ayant consommé un slot d'exécution (transitions
  fraîches au-delà de ACK) ; atteint → arrêt propre `SESSION_BUDGET_REACHED`.
  STOP : `stop --state <s>` puis acknowledging au prochain lancement = retirer
  `stop.request` (action opérateur explicite ; archiver le fichier avant).
  1 worker principal séquentiel (engine) ; sous-agents Hermes ≤ 2 en parallèle.

## Preuves live (2026-11-19/20)

`docs/agents/autonomy-evidence/hermes-relay-live.json` — sessions Hermes réelles, SHA-256 des
artefacts, commentaires GitHub d'approbation/ACK/résultat, coût 0 attesté, rappel mémoire 2/2,
sonde crash/reprise sans doublon. Tests offline : `tests/test_hermes_relay.py` 30/30 +
régressions moteur 14/14, CAS 7/7, kilo executor 8/8.
