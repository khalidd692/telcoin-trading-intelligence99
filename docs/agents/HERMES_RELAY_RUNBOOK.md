# RUNBOOK — Relais Hermes GitHub → superviseur #124 (branche hermes/relay-two-mission-20261121)

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

- **Modèle préféré depuis la branche Qwen4** : `qwen/qwen4-max:free` (provider `nous`), déjà joignable lors d’une sonde manuelle Windows. `meituan/longcat-2.5:free` et `upstage/solar-mini4:free` restent sélectionnables. **Aucune bascule automatique en cas de 429** et aucun repli payant.
- **Important :** la sonde Qwen répondant « OK » ne prouve pas encore son coût nul pour le worker. Le worker exige pour chaque session réelle une identité `model`/`billing_provider` exacte ET `estimated_cost_usd == actual_cost_usd == 0.0` dans la base Hermes ; sinon la mission est bloquée. Confirmer une session Qwen réussie et la persister avant de déclarer le modèle qualifié en production.
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

## Durciment fiabilité — sept corrections (#126-1 .. #126-7, audit lecture seule 2026-11-21)

1. **#126-1 encodage gh** : `default_fetcher` et `publish_comment` fixent
   `encoding="utf-8"` (sous Windows cp1252, `UnicodeDecodeError`/`json.loads(None)`
   faisait planter le relais au lieu du fail-closed). Test
   `test_gh_calls_pin_utf8_encoding`.
2. **#126-2 boucle principale protégée** : `run` encapsule poll/sync dans un
   `try/except` (OSError, ValueError, KeyError, TypeError, AttributeError,
   Blocked) → `observe(BLOCKED, BLOCKER=...)`, sortie 2 ; jamais de boucle morte
   ni de repli payant. Tests `test_main_loop_unexpected_error_fail_closed` et
   `test_main_loop_attribute_error_fail_closed`.
3. **#126-3 propose verrouillé** : la publication PROPOSED passe sous
   `exclusive(session.lock)` (verrou non bloquant) avec re-check CAS avant le
   POST ; `Blocked` → `already_proposed`, échec publication → sortie 1 propre.
   Tests `test_propose_dedup_via_main`, `test_propose_concurrent_single_publication`,
   `test_propose_publish_failure_returns_error`.
4. **#126-4 recovery liée au contrat** : `existing_events` renvoie
   `{url, contract_sha256}` ; une ré-approbation d'un même `mid` avec un contrat
   différent n'est plus enregistrée comme « recovered » mais publiée. Une
   empreinte absente n'est pas une preuve : **fail-closed**, on publie (le
   marqueur anti-boucle évite la ré-admission). Tests
   `test_f3_scan_recovers_existing_event_without_repost`,
   `test_f3_scan_same_id_different_contract_is_not_swallowed`,
   `test_contractless_recovered_event_is_published_fail_closed`.
5. **#126-5 journal durable** : la ligne `relay-events.jsonl` est appendue AVANT le
   marqueur CAS (append-before-mark) : un crash entre les deux laisse une ligne
   auditable plutôt qu'une transition perdue. Test
   `test_journal_appends_before_cas_mark`.
6. **#126-6 mandat épinglé en contenu** : `--mandate-sha256` (SHA-256 du corps du
   commentaire mandat) vérifié dans `fetch_mandate` ; sans l'option, le
   comportement historique (auteur seul) est conservé. Tests
   `test_mandate_content_pinned_by_sha256` et
   `test_main_wires_mandate_sha256_into_source`.
7. **#126-7 JSON durci** : `parse_approvals` rejette les clés dupliquées
   (`object_pairs_hook=_unique_keys`). Test `test_duplicate_json_key_rejected`.

## Recette — deux missions synthétiques A puis B (#123)

Recette hors ligne, sans appel modèle (fixtures + publisher injecté) :
`tests/test_hermes_relay.py::TwoMissionRecipeTests::test_recipe_a_then_b_end_to_end_and_idempotent`
— admission GitHub authentifiée (auteur, mandat, expiration, fingerprint) de deux
missions distinctes, ACK A puis ACK B, ACCEPTED A puis ACCEPTED B, exécution A avant B
(dépendance CAS), 2 entrées mémoire, puis second run sur le même état : 0 réexécution,
0 publication supplémentaire. Aucun copier-coller humain.

Recette live (à exécuter **uniquement** sur approbation explicite du propriétaire) :

1. Épingler le mandat : publier le mandat borné sur #67, puis calculer
   `SHA-256` du corps du commentaire (`gh api .../issues/comments/<id> --jq .body`).
2. Publier deux commentaires `hermes-mission/v1` distincts sur #94 (A puis B, B
   dépend de A), approuvés par `khalidd692`, `mandate_comment_id` = mandat,
   `expires_at` futur, `mission_sha256` = fingerprint du contrat.
3. Démarrer **une seule fois** le relais borné :
   `python -B scripts/agents/automation/hermes_github_adapter.py run --state <state>
   --issue 94 --mandate-issue 67 --mandate-comment <id> --mandate-sha256 <sha>
   --seconds 570 --max-tasks 5 --cli-exe <hermes.exe>`
4. Contrôler : 2 ACK distincts + 2 ACCEPTED sur #94, `status` = ACCEPTED/ACCEPTED,
   2 entrées mémoire, coût 0.
5. Interruption/reprise : `stop`, archiver `stop.request`, relancer `--once` →
   aucun doublon (vérifié live sur la démo C).
6. STOP : ne jamais rejouer automatiquement une mission `AWAITING_HUMAN`.

## Preuves live (2026-11-19/20)

`docs/agents/autonomy-evidence/hermes-relay-live.json` — sessions Hermes réelles, SHA-256 des
artefacts, commentaires GitHub d'approbation/ACK/résultat, coût 0 attesté, rappel mémoire 2/2,
sonde crash/reprise sans doublon. Tests offline : `tests/test_hermes_relay.py` 61/61 +
régressions moteur 14/14, CAS 7/7, kilo executor 8/8 = **90/90** (2026-11-21).


## Recette réelle #123 — 21/11/2026, 21:39 UTC (branche #135)

Les commentaires GitHub [mission A](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94#issuecomment-7069311118) et [mission B](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94#issuecomment-7069311451) ont été admis depuis Windows sur le **même état durable** `recipe-20261121-AB`. Sessions Hermes réelles LongCat 2.5 Free et vérification indépendante fixe :

- A : [ACK](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94#issuecomment-7069625064) → [ACCEPTED](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94#issuecomment-7069631309), session `local-3139741921003cb68e6b35387e61ef623a8c1517b56431e4cdb6f7de17e29e62`.
- B : [ACK](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94#issuecomment-7069628348) → [ACCEPTED](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94#issuecomment-7069631966), session `local-5e538a446c010b0cac78b968f64f1d7280fbc2baa58670c325e242e6884e9c86`.
- Deux verdicts indépendants `MISSION_ACCEPTED`, cinq contrôles réussis chacun, dont coût nul attesté par les relevés de session locaux ; code de sortie relais 0 ; session arrêtée après deux exécutions autorisées.
- **Restant à prouver :** reprise `--once` sur cet état exact sans doublon de publication ni nouvel appel modèle, puis deux **nouvelles issues GitHub** avec modifications de code, PR brouillons et revue indépendante. Les tâches A/B sont des commentaires synthétiques texte, pas des issues de développement.

## Qualification Qwen4 — priorité après A/B

Cette branche donne `qwen/qwen4-max:free` comme **préférence pour les nouvelles sessions** (ancienne session LongCat inchangée). Le modèle n’est pas encore déclaré qualifié de bout en bout : avant promotion dans la branche principale, exécuter un mandat synthétique neuf et borné, inspecter `session_model_usage` et la vérification indépendante ; zéro coût estimé ET réel obligatoire. Le fournisseur, le modèle réellement utilisé, la durée, le quota et le statut seront consignés dans une nouvelle preuve GitHub. Aucun nouveau superviseur, aucune fusion automatique, aucune dépense ni ordre de trading.
