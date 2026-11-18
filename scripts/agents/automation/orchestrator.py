#!/usr/bin/env python3
"""TEL99 cloud-autonomy orchestrator (deterministic ``script`` runner).

This is the entrypoint declared in ``.plugin/plugin.json``. It runs inside an
OpenHands Cloud sandbox when the plugin-spec automation fires, with no LLM of
its own: it selects one authorised mission from a GitHub queue, checks the
preconditions, then drives the *existing* three-agent team.

It reuses, and never re-implements:
  * ``scripts/agents/team_config.py``  — the three agent definitions, the
    read-only contract and the PreToolUse guard wiring;
  * ``scripts/agents/guard/guard.py``  — the deterministic command guard;
  * the same ``confirm_risky`` policy and terminal-only allowlist.

Guarantees enforced here:
  * one mission at a time (policy.MAX_CONCURRENT_MISSIONS);
  * a work branch on an isolated, non-protected branch name;
  * a hard runtime deadline and a per-run budget/iteration cap;
  * stop-on-error: the first failing precondition aborts before any spend;
  * a JSON execution journal written to the workspace and to the KV store.

Read-only with respect to the TEL99 repository history: it never pushes to the
base, product, data or deployment branches, and never merges. When dry_run is
true (the default) it starts no conversation at all.

Usage (Cloud script runner):
    python3 scripts/agents/automation/orchestrator.py --config "$AUTOMATION_CONFIG_PATH"

Local dry-run (no network, no spend):
    python3 scripts/agents/automation/orchestrator.py --config config.json --offline
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import policy  # noqa: E402
import preflight  # noqa: E402
import team_config as cfg  # noqa: E402

try:
    import emergency  # noqa: E402
except Exception:  # noqa: BLE001 - the brake is additive; its absence must not crash
    emergency = None

# Optional: the bus bridge adds a durable ledger (KV in the cloud) on top of the
# orchestrator's own state. It is imported defensively so the orchestrator keeps
# working even if the protocol package is absent.
try:
    from automation import bus_bridge  # noqa: E402
except Exception:  # noqa: BLE001 - the bus is an enhancement, not a dependency
    bus_bridge = None

try:
    from protocol.bus import Bus  # noqa: E402
    from protocol.store import default_store  # noqa: E402
except Exception:  # noqa: BLE001
    Bus = None

REPO_ROOT = SCRIPTS.parents[1]
DEFAULT_CONFIG = {
    "repository": "khalidd692/telcoin-trading-intelligence99",
    "mission_label": "tel99-mission",
    "base_branch": "agents/hermes-simple-team-20261114",
    "work_branch_prefix": "agent/mission-",
    "max_concurrent_missions": 1,
    "max_runtime_seconds": 1800,
    "max_iterations": 30,
    "max_budget_usd": 1.0,
    "agent_max_iterations": 10,
    "agent_max_budget_usd": 0.25,
    "quota_min_remaining": 2,
    "dry_run": True,
    # A real run must be able to prove durable storage, deduplication and mission
    # opening on the bus. When false, a missing bus degrades to a warning instead
    # of a refusal; this is only meant for local experiments, never for cloud.
    "require_durable_bus": True,
    # Kill-switch, mirrored from the plugin schema. When true the run stops
    # immediately (exit 3) before any probe, spend or conversation.
    "emergency_stop": False,
}


# --------------------------------------------------------------------------- #
# Environment / credentials
# --------------------------------------------------------------------------- #
def cloud_api_base() -> str:
    """Base URL of the OpenHands Cloud API (for quota + git lookups)."""
    return (
        os.environ.get("OPENHANDS_CLOUD_API_URL")
        or os.environ.get("TEL99_CLOUD_API_BASE")
        or "https://app.all-hands.dev"
    ).rstrip("/")


def agent_server_base() -> str:
    """Base URL of the agent server that will host the conversations."""
    return (
        os.environ.get("AGENT_SERVER_URL")
        or os.environ.get("TEL99_API_BASE")
        or "http://localhost:60000"
    ).rstrip("/")


def session_key() -> str:
    """Session API key: env first, then the process environment on Linux."""
    for name in ("SESSION_API_KEY", "OH_SESSION_API_KEYS_0"):
        value = os.environ.get(name)
        if value:
            return value
    try:
        blob = pathlib.Path("/proc/1/environ").read_bytes().decode(errors="ignore")
    except OSError:
        return ""
    for part in blob.split("\x00"):
        if part.startswith("SESSION_API_KEY="):
            return part.split("=", 1)[1]
    return ""


def github_token() -> str:
    """Token used for the read-only GitHub mission queue.

    A dedicated ``TEL99_GITHUB_TOKEN`` is preferred so the automation is not
    granted more rights than reading issues. The injected provider token is a
    fallback, used read-only here. On Cloud the token may be stored as a secret
    and fetched through the agent server, so ``get_secret`` is tried last.
    """
    for name in ("TEL99_GITHUB_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(name)
        if value:
            return value
    for name in ("TEL99_GITHUB_TOKEN", "GITHUB_TOKEN"):
        try:
            value = get_secret(name)
        except Exception:
            value = ""
        if value:
            return value
    return ""


def get_secret(name: str) -> str:
    """Fetch a named secret from the agent server (Cloud and local).

    Uses ``AGENT_SERVER_URL`` on a local Agent Canvas and
    ``OPENHANDS_CLOUD_API_URL`` + ``SANDBOX_ID`` on Cloud.
    """
    key = os.environ.get("SESSION_API_KEY") or os.environ.get("OH_SESSION_API_KEYS_0", "")
    url = os.environ.get("AGENT_SERVER_URL", "").rstrip("/")
    if url:
        url = f"{url}/api/settings/secrets/{name}"
    else:
        api = os.environ["OPENHANDS_CLOUD_API_URL"].rstrip("/")
        url = f"{api}/api/v1/sandboxes/{os.environ['SANDBOX_ID']}/settings/secrets/{name}"
    req = urllib.request.Request(url, headers={"X-Session-API-Key": key})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode().strip()


def fire_callback(status: str = "COMPLETED", error: str | None = None,
                  outcome: dict | None = None) -> None:
    """Signal run completion to the automation service.

    The script runner does not mark a run complete on its own, so this must be
    called on every exit path — success and error alike. Without it the run
    stays RUNNING until the platform timeout.

    ``outcome`` carries the run report's business fields (``mission_id``,
    ``mission_accepted``, ``outcome_verification``, ``config_digest``) so the
    platform sees a mission verdict, not only "COMPLETED"/"FAILED". It is a
    summary, never the full journal, and contains no secret.
    """
    url = os.environ.get("AUTOMATION_CALLBACK_URL", "")
    if not url:
        return
    body = {"status": status, "run_id": os.environ.get("AUTOMATION_RUN_ID", "")}
    if error:
        body["error"] = error
    if outcome:
        body["mission_id"] = outcome.get("mission_id")
        body["mission_accepted"] = outcome.get("mission_accepted")
        body["outcome_verification"] = outcome.get("outcome_verification")
        body["config_digest"] = outcome.get("config_digest")
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ.get('AUTOMATION_CALLBACK_API_KEY', '')}",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=30)
    except Exception as exc:  # never fail the run on a callback error
        print(f"callback error: {exc}", file=sys.stderr)


def _request(method, url, payload=None, headers=None, timeout=60):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        if value:
            req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="ignore")


# --------------------------------------------------------------------------- #
# State persistence (KV store, local-file fallback)
# --------------------------------------------------------------------------- #
_KV_TOKEN = os.environ.get("AUTOMATION_KV_TOKEN", "")
_KV_BASE = os.environ.get("AUTOMATION_API_URL", "").rstrip("/")
_STATE_KEY = "state"


def kv_available() -> bool:
    return bool(_KV_TOKEN and _KV_BASE)


def kv_get(key):
    req = urllib.request.Request(
        f"{_KV_BASE}/v1/kv/{key}",
        headers={"Authorization": f"Bearer {_KV_TOKEN}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["value"]
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def kv_set(key, value) -> None:
    req = urllib.request.Request(
        f"{_KV_BASE}/v1/kv/{key}",
        data=json.dumps(value).encode(),
        headers={
            "Authorization": f"Bearer {_KV_TOKEN}",
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


class LockUnsupported(RuntimeError):
    """The KV backend cannot support an atomic conditional write.

    Raised when a lock read cannot return the record *version* the compare-and-
    set needs. The caller then refuses to start a real mission rather than risk
    two runs working the same mission at once.
    """


def kv_get_meta(key) -> tuple:
    """Read ``key`` with its version, for a compare-and-set write.

    Returns ``(value, version)``; ``(None, None)`` when the key is absent.

    The automation KV store exposes the record version under ``?meta=true`` and
    accepts a conditional write with ``?if_version=<version>`` (HTTP 409 on a
    mismatch). This is the mechanism the shipped ``github`` /
    ``github-pr-reviewer`` skills use for their own coordination. A backend that
    answers without a version cannot do an atomic compare-and-set, so we raise
    :class:`LockUnsupported` and the caller fails closed.
    """
    status, body = _request(
        "GET", f"{_KV_BASE}/v1/kv/{key}?meta=true",
        headers={"Authorization": f"Bearer {_KV_TOKEN}"},
    )
    if status == 404:
        return None, None
    if status != 200 or not isinstance(body, dict):
        raise LockUnsupported(f"KV metadata read failed: HTTP {status}")
    if "value" not in body:
        return None, None
    version = body.get("version")
    if version is None:
        raise LockUnsupported(
            "KV backend does not expose a record version: no atomic compare-and-set"
        )
    return body.get("value"), version


def kv_meta_probe(key) -> dict:
    """Report whether the KV backend really supports a conditional write.

    ``?meta=true`` is only *assumed* to return a record version. This probe
    records the raw answer for a key, so a run (or a ``--diagnose`` report) can
    show whether the atomic compare-and-set the lock relies on is actually
    available, instead of trusting the assumption. Read-only.
    """
    if not kv_available():
        return {"available": False, "reason": "no AUTOMATION_KV_TOKEN/AUTOMATION_API_URL"}
    try:
        status, body = _request(
            "GET", f"{_KV_BASE}/v1/kv/{key}?meta=true",
            headers={"Authorization": f"Bearer {_KV_TOKEN}"}, timeout=15,
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics must never raise
        return {"available": False, "reason": f"{type(exc).__name__}"}
    if status == 404:
        return {"available": True, "status": 404, "key_absent": True}
    if status != 200 or not isinstance(body, dict):
        return {"available": True, "status": status, "supported": False}
    return {
        "available": True,
        "status": status,
        "key_absent": "value" not in body,
        "supported": body.get("version") is not None,
        "has_version": "version" in body,
    }


def _state_path() -> pathlib.Path:
    payload = json.loads(os.environ.get("AUTOMATION_EVENT_PAYLOAD", "{}") or "{}")
    automation_id = payload.get("automation_id", "default")
    state_dir = REPO_ROOT / ".tel99-automation-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / f"orchestrator_{automation_id}.json"


def load_state() -> dict:
    if kv_available():
        data = kv_get(_STATE_KEY)
        if isinstance(data, dict):
            return data
    path = _state_path()
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {"version": 1, "processed": [], "active": None, "journal": []}


def save_state(state: dict) -> None:
    if kv_available():
        kv_set(_STATE_KEY, state)
        return
    path = _state_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------------- #
# Cross-run lock (one mission at a time, across distinct cloud runs)
# --------------------------------------------------------------------------- #
_LOCK_KEY = "active_mission_lock"
_LOCK_MAX_ATTEMPTS = 5


def _lock_held(record) -> bool:
    """True when ``record`` is a live lock (a real owner, not expired)."""
    return (
        isinstance(record, dict)
        and bool(record.get("owner"))
        and not _lock_expired(record)
    )


def acquire_lock(owner: str, ttl_seconds: int = 7200) -> tuple[bool, str]:
    """Take the single mission lock with an atomic compare-and-set.

    Two cloud runs racing for the same mission must not both start it. The KV
    API has no "set-if-not-exists that also handles an expired record", so the
    lock is taken with a genuine compare-and-set (CAS), the same mechanism the
    shipped ``github`` / ``github-pr-reviewer`` skills use:

    * read the record **with its version** (``GET ?meta=true``);
    * write conditionally: ``?nx=true`` when the key is absent, else
      ``?if_version=<version>``;
    * the backend answers **HTTP 409** when the condition fails, i.e. when
      another run won the race. We then re-read and retry, and only one run can
      ever win a given version.

    This removes the read -> check -> write race of the previous version (which
    re-read and DELETEd an expired record before a non-atomic ``nx`` write).

    Fail-closed: without a backend that reports a record version there is no
    atomic guarantee, so a real mission must NOT start. Returns ``(False,
    reason)`` in that case.
    """
    if not kv_available():
        return False, "no atomic KV lock available: refusing to start a real mission"

    record = {
        "owner": owner,
        "acquired_at": policy.utcnow_iso(),
        "expires_at": _expiry_iso(ttl_seconds),
    }

    for _ in range(_LOCK_MAX_ATTEMPTS):
        try:
            current, version = kv_get_meta(_LOCK_KEY)
        except LockUnsupported as exc:
            return False, f"no atomic compare-and-set: refusing to start a real mission ({exc})"

        if _lock_held(current):
            return False, (
                f"lock held by {current.get('owner')} until {current.get('expires_at')}"
            )

        # The key is absent (create with nx) or holds an expired/released record
        # (overwrite only if it is still at the version we just read).
        condition = "nx=true" if version is None else f"if_version={version}"
        status, _body = _request(
            "PUT", f"{_KV_BASE}/v1/kv/{_LOCK_KEY}?{condition}", record,
            headers={"Authorization": f"Bearer {_KV_TOKEN}"},
        )
        if status in (200, 201, 204):
            # CAS won: no other run can hold this version. No re-read needed.
            return True, "lock acquired"
        if status == 409:
            continue  # lost the race; re-read and retry
        return False, f"lock write failed: HTTP {status}"

    return False, "lock contention: could not acquire within the retry budget"


def release_lock(owner: str) -> None:
    """Release the lock only if this run owns it, using a conditional write.

    A plain read -> DELETE is unsafe: between the two, an expired lock could be
    taken over by another run, whose fresh lock our DELETE would then remove.
    Instead we compare-and-set the record we read (``?if_version=<version>``) to
    a released tombstone. A 409 means someone else changed the record, so we
    re-read and retry; we never clobber a lock we no longer own.
    """
    if not kv_available():
        return
    for _ in range(_LOCK_MAX_ATTEMPTS):
        try:
            current, version = kv_get_meta(_LOCK_KEY)
        except LockUnsupported:
            return
        if not isinstance(current, dict) or current.get("owner") != owner:
            return  # not ours (or already gone): leave it untouched
        if version is None:
            return
        tombstone = {
            "owner": "",
            "released_at": policy.utcnow_iso(),
            "expires_at": _expiry_iso(-1),
            "released_by": owner,
        }
        status, _body = _request(
            "PUT", f"{_KV_BASE}/v1/kv/{_LOCK_KEY}?if_version={version}", tombstone,
            headers={"Authorization": f"Bearer {_KV_TOKEN}"},
        )
        if status in (200, 201, 204):
            return
        if status == 409:
            continue  # changed under us; re-read
        return



def _expiry_iso(ttl_seconds: int) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")


def _lock_expired(record: dict) -> bool:
    expires = (record or {}).get("expires_at")
    if not expires:
        return False
    from datetime import datetime, timezone

    try:
        when = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    except ValueError:
        return False
    return when <= datetime.now(timezone.utc)


def reconcile_stale_active(state: dict, dry_run: bool) -> str | None:
    """Reconcile a mission left ``active`` by an interrupted run.

    A run that is killed mid-mission (deploy, quota exhaustion, host reboot)
    leaves ``state["active"]`` set and the mission out of ``processed``. Without
    reconciliation the next run would abort forever with "a mission is already
    active" — the queue would be wedged by a mission that no longer runs.

    Two independent sources of truth are consulted, and the run only proceeds
    when BOTH say nothing is running:

    * the atomic KV lock (covers a second *run* racing for the mission);
    * the recorded conversation id, probed on the agent server (covers a run
      killed after it created a conversation but before it cleared ``active``).

    So:

    * If the KV lock is still held and unexpired, another run owns the mission:
      return a reason string and let the caller abort.
    * Else, if ``active`` carries a ``conversation_id`` and that conversation is
      still alive on the agent server, the mission is genuinely running: return
      a reason string (the caller then re-attaches to it instead of starting a
      duplicate).
    * Else clear ``active`` and return ``None`` so the mission becomes eligible
      again and is resumed (never lost, never duplicated: it is not in
      ``processed`` yet).

    Never clears ``active`` when the lock cannot be read (KV unavailable) or
    when the liveness probe cannot reach the agent server, so a real run can
    never silently run two missions at once (fail-closed).
    """
    if dry_run:
        # A dry run does not touch persistent state; it only reports.
        return None
    if not state.get("active"):
        return None
    action, detail = _reconcile_decision(state)
    if action == "abort":
        return detail
    if action == "reattach":
        return (
            f"a mission is recorded as active with a live conversation {detail}; "
            "re-attaching rather than duplicating"
        )
    # "proceed": nothing is running; the mission is re-queued for a fresh attempt.
    journal_entry(
        state, "stale_active_reconciled", previous=state.get("active"),
        note="lock expired or absent; mission re-queued for resume",
    )
    state["active"] = None
    save_state(state)
    return None


def _reconcile_decision(state: dict) -> tuple[str, str]:
    """Decide what to do with an ``active`` record, from two independent proofs.

    Returns ``(action, detail)`` where ``action`` is one of:

    * ``"proceed"`` — nothing is running; the mission may be re-queued.
    * ``"reattach"`` — a live conversation exists; ``detail`` is its id.
    * ``"abort"`` — the state cannot be proven safe; ``detail`` is the reason.

    The decision is fail-closed: any uncertainty (unreadable lock, unreachable
    agent server) is an ``abort``, never a silent re-queue that could start a
    second conversation for a mission that is actually still running. This
    function never mutates ``state``.
    """
    active = state.get("active")
    if not active:
        return "proceed", ""
    if not kv_available():
        return "abort", (
            "a mission is recorded as active but the atomic KV lock cannot be "
            "read; refusing to reconcile without proof it is not running"
        )
    try:
        lock = kv_get(_LOCK_KEY)
    except Exception as exc:  # noqa: BLE001 - a KV read error is "cannot prove"
        return "abort", (
            "a mission is recorded as active but the atomic KV lock could not be "
            f"read ({type(exc).__name__}: {exc}); refusing to reconcile without proof"
        )
    if _lock_held(lock):
        return "abort", (
            f"a mission is already active (lock held by {lock.get('owner')} "
            f"until {lock.get('expires_at')})"
        )
    cid = active.get("conversation_id")
    if cid:
        outcome, status = conversation_status(cid)
        if outcome == "alive":
            return "reattach", cid
        if outcome == "unknown":
            return "abort", (
                f"a mission is recorded as active with conversation {cid} but the "
                "agent server is unreachable; refusing to reconcile without proof"
            )
        # outcome == "gone": the conversation is not running. Note the residual
        # assumption: a 404 is trusted as proof of absence. In this architecture
        # the conversation is created on the same agent server the resume probes,
        # and the KV lock above already covered the window (its TTL is
        # max_runtime_seconds + 600) during which a run could still be alive, so a
        # 404 after the lock expired means the conversation is really gone.
    return "proceed", ""


# --------------------------------------------------------------------------- #
# Run phase reporting (so the platform shows real progress, not "Starting")
# --------------------------------------------------------------------------- #
def report_phase(phase: str) -> None:
    """Report the current phase to the automation service, if configured."""
    run_id = os.environ.get("AUTOMATION_RUN_ID", "")
    base = os.environ.get("AUTOMATION_API_URL", "").rstrip("/")
    token = os.environ.get("AUTOMATION_KV_TOKEN", "")
    if not (run_id and base):
        return
    _request(
        "POST", f"{base}/v1/runs/{run_id}/phase", {"phase": phase},
        headers={"Authorization": f"Bearer {token}"},
    )


# --------------------------------------------------------------------------- #
# Environment diagnostics (read-only; printed to the run journal)
# --------------------------------------------------------------------------- #
def diagnose_environment() -> dict:
    """Report what the run can actually reach, without changing anything.

    This is what turns an assumption into a fact: whether an agent server is
    reachable, whether the KV lock is available, and which API base is used.
    """
    server = agent_server_base()
    reachable = False
    detail = ""
    try:
        headers = {}
        key = session_key()
        if key:
            headers["X-Session-API-Key"] = key
        status, body = _request(
            "GET", f"{server}/api/conversations/count", headers=headers, timeout=15
        )
        reachable = status == 200
        detail = f"HTTP {status}" + (" (authenticated)" if status == 200 else "")
    except Exception as exc:  # noqa: BLE001 - diagnostics must never raise
        detail = f"unreachable: {type(exc).__name__}"
    if emergency is not None:
        stop_state, stop_reason = emergency.stop_requested(
            _state_path().parent, kv_get if kv_available() else None
        )
    else:
        stop_state, stop_reason = False, "module absent"
    return {
        "agent_server_base": server,
        "agent_server_reachable": reachable,
        "agent_server_detail": detail,
        "cloud_api_base": cloud_api_base(),
        "kv_lock_available": kv_available(),
        "kv_lock_capability": kv_meta_probe(_LOCK_KEY),
        "session_key_present": bool(session_key()),
        "github_token_present": bool(github_token()),
        # ``scope`` makes the limit explicit: this brake stops the NEXT run and
        # interrupts a conversation THIS run is driving; it is not a promise of
        # an instant global stop for a mission another container already runs.
        "emergency_stop": {"stopped": stop_state, "reason": stop_reason,
                           "scope": "next_run_and_owned_conversation"},
    }


# --------------------------------------------------------------------------- #
# GitHub mission queue (read-only)
# --------------------------------------------------------------------------- #
def list_mission_issues(repository: str, mission_label: str) -> list[dict]:
    token = github_token()
    url = (
        f"https://api.github.com/repos/{repository}/issues"
        f"?state=open&labels={mission_label}&per_page=100"
    )
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    status, body = _request("GET", url, headers=headers)
    if status != 200 or not isinstance(body, list):
        raise RuntimeError(f"GitHub issue listing failed: HTTP {status} {body!r:.200}")
    return body


def quota_remaining() -> int | None:
    """Remaining free daily conversations, or None when it cannot be read."""
    key = os.environ.get("OPENHANDS_API_KEY") or os.environ.get("TEL99_CLOUD_API_KEY")
    if not key:
        return None
    status, body = _request(
        "GET", f"{cloud_api_base()}/api/quota/status",
        headers={"Authorization": f"Bearer {key}"},
    )
    if status == 200 and isinstance(body, dict):
        return body.get("remaining")
    return None


# --------------------------------------------------------------------------- #
# Conversation payload — reuses the existing team, unchanged
# --------------------------------------------------------------------------- #
def build_payload(mission_issue: dict, work_branch: str, config: dict, llm: dict,
                  names: dict | None = None) -> dict:
    """Assemble the coordinator payload from the existing team configuration.

    The three agent definitions, their prompts, the read-only contract and the
    PreToolUse guard all come from ``team_config`` — this function only wires
    them together and adds the mission text. ``names`` lets the caller reuse the
    exact per-run agent names it will later verify against.
    """
    if names is None:
        names = cfg.unique_names(time.strftime("%H%M%S"))
    hooks = cfg.hook_config()

    definitions = []
    for spec in cfg.ACTIVE_AGENTS:
        definitions.append(
            {
                "name": names[spec.role],
                "description": spec.description,
                "model": "inherit",
                "tools": list(spec.tools),
                "system_prompt": spec.full_prompt() + "\n\n" + cfg.BUDGET_DISCIPLINE,
                "permission_mode": spec.permission_mode,
                "max_iteration_per_run": config["agent_max_iterations"],
                "max_budget_per_run": config["agent_max_budget_usd"],
                "hooks": hooks,
                "when_to_use_examples": [f"read-only {spec.role} check"],
                "level": "project",
            }
        )

    issue_number = mission_issue["number"]
    mission = (
        f"Mission GitHub #{issue_number}: {mission_issue.get('title', '').strip()}\n\n"
        f"{(mission_issue.get('body') or '').strip()}\n\n"
        f"Travaille uniquement sur la branche isolee `{work_branch}`. "
        "Ne pousse jamais sur une branche protegee, ne fusionne pas, "
        "n'ouvre pas de PR sans validation."
    )
    roles = ", ".join(f"{r}={n}" for r, n in names.items())
    mission_text = (
        "Tu es le coordinateur de l'equipe TEL99 (lecture seule). "
        f"Sous-agents disponibles: {roles}. "
        "Delegue chaque sous-tache avec l'outil de delegation, en restreignant les "
        "outils du parent (sub_agent_scope). Verifie chaque preuve, distingue constat "
        "et hypothese, puis resume preuves, limites et actions necessitant un accord. "
        "N'essaie jamais de contourner le garde-fou.\n"
        "BUDGET: si un sous-agent atteint sa limite, ne le relance pas automatiquement; "
        "exploite son rapport partiel et signale la limite.\n\n"
        f"{mission}"
    )

    return {
        "workspace": {"kind": "LocalWorkspace", "working_dir": str(REPO_ROOT)},
        "worktree": False,
        # ``confirm_unknown`` must stay False for an unattended cloud run. The
        # security analyzer classifies the coordination actions the mission
        # depends on (``task_tool_set`` delegation, ``task_tracker``) as UNKNOWN
        # risk, and no human is present to answer a confirmation. With
        # ``confirm_unknown: True`` the coordinator stalls in
        # ``waiting_for_confirmation`` until the platform timeout kills the run
        # — a guaranteed failure. HIGH-risk actions still require confirmation
        # (``threshold: HIGH``); the deterministic PreToolUse guard remains the
        # primary control on terminal commands.
        "confirmation_policy": {
            "kind": "ConfirmRisky",
            "threshold": "HIGH",
            "confirm_unknown": False,
        },
        "security_analyzer": {"kind": "LLMSecurityAnalyzer"},
        "max_iterations": config["max_iterations"],
        "max_budget_per_run": config["max_budget_usd"],
        "stuck_detection": True,
        "autotitle": False,
        "hook_config": hooks,
        "initial_message": {
            "role": "user",
            "content": [{"type": "text", "text": mission_text}],
            "run": False,
        },
        "agent": {
            "kind": "Agent",
            "llm": llm,
            "tools": [
                {"name": "task_tool_set", "params": {"sub_agent_scope": {"tools": True}}},
                {"name": "task_tracker", "params": {}},
                {"name": "terminal", "params": {}},
            ],
            "include_default_tools": ["FinishTool"],
            "agent_context": {"skills": []},
        },
        "agent_definitions": definitions,
        "tags": {"purpose": "tel99-mission", "mode": "readonly", "issue": str(issue_number)},
    }


# --------------------------------------------------------------------------- #
# Execution journal
# --------------------------------------------------------------------------- #
def journal_entry(state: dict, event: str, **fields) -> None:
    entry = {"at": policy.utcnow_iso(), "event": event}
    entry.update(fields)
    state.setdefault("journal", []).append(entry)
    print(f"[journal] {json.dumps(entry, ensure_ascii=False)}")


# --------------------------------------------------------------------------- #
# Durable run report (survives sandbox destruction)
# --------------------------------------------------------------------------- #
# The platform deletes the sandbox after a run, so a report that only lives in
# the workspace file or on stdout is lost ("Sandbox has been deleted - logs are
# no longer available"). This section writes ONE structured report per run to the
# durable KV store (the same namespace/mechanism as ``state``) and, best-effort,
# to the local workspace file, so a cockpit can always read what a run did.
#
# It deliberately separates two things that were previously conflated:
#   * SCRIPT SUCCESS   - the process exit code (``0`` == the script ran fine);
#   * MISSION_ACCEPTED - the business verdict (``outcome_verdict.validated``).
# A run can exit ``0`` having accepted NO mission (idle / dry-run / offline), and
# a mission can be attempted and rejected (exit ``2``) while the script itself
# succeeded. ``status`` and ``mission_accepted`` make that explicit instead of
# hiding it behind a single integer.
_RUN_REPORT_KEY = "run_report"
# Per-run copies (history) so a later run never silently erases the only
# durable trace of an earlier one. Single path segment: the KV namespace is
# flat, so the separator is a dot, not a slash.
_RUN_REPORT_PREFIX = "run_report."
# Only these keys are hashed into ``config_digest``. The config carries no secret
# today, but hashing a whitelist (never the raw merged dict) keeps a future config
# field from leaking into a durable, broadly readable record.
_REPORT_CONFIG_KEYS = (
    "repository", "mission_label", "base_branch", "work_branch_prefix",
    "max_concurrent_missions", "max_runtime_seconds", "max_iterations",
    "max_budget_usd", "agent_max_iterations", "agent_max_budget_usd",
    "quota_min_remaining", "dry_run", "require_durable_bus", "emergency_stop",
)


def config_digest(config: dict) -> str:
    """Stable short digest of the whitelisted configuration. Never a secret."""
    projection = {k: config.get(k) for k in _REPORT_CONFIG_KEYS if k in config}
    blob = json.dumps(projection, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _report_key(run_id: str) -> str:
    """Stable per-run KV key. Sanitised so it stays a single flat segment."""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", run_id or "") or "unknown"
    return f"{_RUN_REPORT_PREFIX}{safe}"


def _journal_entries(state: dict) -> list:
    """Return only the well-formed (dict) journal entries.

    ``load_state`` returns a dict read back from the KV store or a local file,
    which is not schema-checked: a corrupted or hand-edited ``state`` could hold
    ``journal: None`` or non-dict entries. The report builder must survive that
    rather than raise (a missing report is preferable to a crashed run).
    """
    journal = state.get("journal") if isinstance(state, dict) else None
    if not isinstance(journal, list):
        return []
    return [e for e in journal if isinstance(e, dict)]


def _last_journal_value(state: dict, event: str, key: str):
    """Return ``key`` from the last journal entry named ``event``, or ``None``."""
    for entry in reversed(_journal_entries(state)):
        if entry.get("event") == event and key in entry:
            return entry[key]
    return None


def build_run_report(state: dict, config: dict, code: int, *,
                     quota_after=None) -> dict:
    """Build the durable run report from the run's own state (pure function).

    Reads the run's journal so the report reflects what actually happened
    (mission selected, quota reading, outcome verdict) rather than a guess.
    """
    mission_number = _last_journal_value(state, "mission_selected", "issue")
    if mission_number is None:
        mission_number = _last_journal_value(state, "mission_resume", "issue")
    started = [
        e for e in _journal_entries(state)
        if e.get("event") in ("conversation_started", "conversation_resumed")
    ]
    mission_id = str(mission_number) if mission_number is not None else "NO_MISSION"
    validated = _last_journal_value(state, "outcome_verdict", "validated")
    if validated is None:
        outcome_verification = "NOT_ATTEMPTED"
    else:
        outcome_verification = "ACCEPTED" if validated else "REJECTED"
    error_reason = _last_journal_value(state, "abort", "reason")
    if error_reason is None and code == 3:
        error_reason = _last_journal_value(state, "emergency_stop", "reason")
    # The business verdict is separate from the script exit code.
    mission_accepted = bool(validated is True and code == 0)
    if mission_accepted:
        status = "MISSION_ACCEPTED"
    elif code == 3:
        status = "STOPPED"
    elif code != 0:
        status = "FAILED"
    elif mission_id == "NO_MISSION":
        status = "SUCCESS_SCRIPT_NO_MISSION"
    else:
        status = "SUCCESS_SCRIPT_MISSION_NOT_ACCEPTED"
    run_id = (os.environ.get("AUTOMATION_RUN_ID", "")
              or _last_journal_value(state, "run_start", "owner") or "")
    return {
        "schema_version": 1,
        "record_type": "tel99_run_report",
        "run_id": run_id,
        "ts": policy.utcnow_iso(),
        "config_digest": config_digest(config),
        "dry_run": bool(config.get("dry_run")),
        "quota_before": _last_journal_value(state, "quota", "remaining"),
        "quota_after": quota_after,
        "mission_id": mission_id,
        "started_children": len(started),
        "status": status,
        "mission_accepted": mission_accepted,
        "outcome_verification": outcome_verification,
        "error_reason": error_reason,
        "evidence_uri": f"kv://{_report_key(run_id)}",
    }


def write_run_report(state: dict, config: dict, code: int, *,
                     quota_after=None, write_kv: bool = True) -> dict:
    """Persist the run report durably (KV), then to the local file; best-effort.

    Never raises: a failure to write a report must not turn a completed run into
    a crash. The report is always returned so the caller can print it too.

    ``write_kv=False`` skips the durable-store write and keeps only the local
    workspace file. The emergency-brake path uses it so that halting a run never
    touches the network (the brake must not depend on a remote store).
    """
    try:
        report = build_run_report(state, config, code, quota_after=quota_after)
    except Exception as exc:  # noqa: BLE001 - a report must never break the run
        print(f"[journal] run_report_build_error: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return {}
    # Durable store first (survives container destruction), local file second.
    # Two keys: ``run_report`` (the latest, for the cockpit/callback) and a
    # per-run ``run_report.<run_id>`` (history, so a later run cannot erase the
    # only durable trace of an earlier one).
    if write_kv and kv_available():
        for key in (_RUN_REPORT_KEY, _report_key(report.get("run_id", ""))):
            try:
                kv_set(key, report)
            except Exception as exc:  # noqa: BLE001
                print(f"[journal] run_report_kv_error[{key}]: "
                      f"{type(exc).__name__}: {exc}", file=sys.stderr)
    try:
        path = _state_path()
        report_path = path.with_name(path.stem + "_run_report.json")
        tmp = report_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(report_path)
    except Exception as exc:  # noqa: BLE001
        print(f"[journal] run_report_file_error: {type(exc).__name__}: {exc}",
              file=sys.stderr)
    print(f"[journal] run_report {json.dumps(report, ensure_ascii=False)}")
    return report


def read_run_report() -> dict:
    """Read the last run report: the local file first, then the durable store.

    Best-effort and read-only: returns ``{}`` when no report is readable, so a
    caller can always use it without guarding. The local file is tried first
    because the same process just wrote it (no network call in the common case);
    the KV store is the fallback that still works after the sandbox is deleted.
    Used by ``main`` to attach the business verdict to the completion callback.
    """
    try:
        path = _state_path()
        report_path = path.with_name(path.stem + "_run_report.json")
        return json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a missing report is not an error
        pass
    if kv_available():
        try:
            data = kv_get(_RUN_REPORT_KEY)
            if isinstance(data, dict):
                return data
        except Exception:  # noqa: BLE001
            pass
    return {}


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def load_config(path: str | None) -> dict:
    """Load the validated plugin config.

    The plugin entrypoint has no shell metacharacters, so the config path is
    taken from the environment variable the script runner injects
    (``AUTOMATION_CONFIG_PATH``) when ``--config`` is not given.
    """
    if not path:
        path = os.environ.get("AUTOMATION_CONFIG_PATH")
    config = dict(DEFAULT_CONFIG)
    if path:
        try:
            loaded = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                config.update(loaded)
        except (OSError, ValueError) as exc:
            raise SystemExit(f"cannot read config {path}: {exc}")
    return config


def _finish_mission(*, state, mission, work_branch, cid, final,
                    agent_names, bus, bus_corr, require_bus, owner,
                    processed) -> int:
    """Verify, persist and close out a mission conversation.

    Shared by a fresh start and a re-attach, so both paths apply exactly the same
    evidence gate: a mission is only ever marked processed (done) when
    ``verify_outcome`` proves every required role reported. On any failure the
    mission stays out of ``processed`` and remains resumable. The caller holds
    the KV lock and releases it in its ``finally``.
    """
    journal_entry(state, "conversation_finished", conversation=cid, status=final)

    if final == "confirmation_required":
        # An unattended run has no one to answer a confirmation. Fail fast and
        # loudly rather than let the platform timeout kill the run; the mission
        # stays out of ``processed`` so it is resumable.
        journal_entry(state, "abort", conversation=cid,
                      reason="conversation stalled waiting for a confirmation "
                             "that no operator can answer in an unattended run")
        state["active"] = None
        save_state(state)
        return 2

    if final == "stopped":
        # An operator set the brake while this mission ran. The conversation was
        # interrupted; the mission stays resumable.
        journal_entry(state, "emergency_interrupt", conversation=cid,
                      scope="active_mission",
                      note="conversation interrupted; mission left resumable")
        state["active"] = None
        save_state(state)
        return 3

    # --- Validation: a finished status is NOT a success by itself. ---
    evidence = collect_evidence(cid, expected_roles=agent_names,
                                mission_body=mission.get("body") or "")
    validated, verdict = verify_outcome(final, evidence,
                                        expected_roles=agent_names,
                                        mission_body=mission.get("body") or "")
    journal_entry(state, "outcome_verdict", validated=validated,
                  roles={r: info.get("proven") for r, info in verdict["roles"].items()},
                  checks=verdict["checks"])

    # --- Persist the outcome on the bus (survives container destruction). ---
    # Fail-closed: if the durable record cannot be written, the mission must NOT
    # be declared done nor marked processed, otherwise it would be lost from the
    # ledger and never retried.
    if bus is not None and bus_corr is not None:
        try:
            outcome = bus_bridge.record_outcome(
                bus, bus_corr, success=validated,
                summary=(f"validated outcome for issue #{mission['number']}"
                         if validated else
                         f"unvalidated outcome ({final}) for issue #{mission['number']}"),
                conversation_id=str(cid), work_branch=work_branch,
                status_detail=f"final status {final}; validated={validated}",
                evidence=evidence, verdict=verdict,
            )
            journal_entry(state, "bus_outcome", mission_state=outcome["state"],
                          learning=(outcome.get("learning") or {}).get("id"))
        except Exception as exc:  # noqa: BLE001
            journal_entry(state, "abort",
                          reason="final bus record failed: mission NOT marked done",
                          detail=f"{type(exc).__name__}: {exc}")
            state["active"] = None
            save_state(state)
            return 2
    elif require_bus:
        journal_entry(state, "abort",
                      reason="bus unavailable at completion: mission NOT marked done")
        state["active"] = None
        save_state(state)
        return 2

    # Only a validated mission is marked processed; an unvalidated one stays out
    # of ``processed`` so the next run resumes it.
    if validated:
        state["processed"] = sorted(processed | {mission["number"]})
    state["active"] = None
    save_state(state)
    return 0 if validated else 2


def run(config: dict, offline: bool = False) -> int:
    """Run one orchestrator cycle and persist a durable report for it.

    Thin wrapper around :func:`_run_impl` so that every exit code (0, 2, 3, and
    the crash path that ``main`` turns into 1) is covered by a single durable
    report write, without threading a return value through the ~20 exit paths of
    the body. The report is best-effort: a failure to write it never changes the
    run's exit code and never raises.
    """
    holder: dict = {}
    try:
        code = _run_impl(config, offline, holder)
    except BaseException:  # noqa: BLE001 - report the crash, then re-raise
        # A crash is exit code 1 (``main`` maps it). Persist a report so the run
        # is not invisible after the sandbox is deleted, then re-raise unchanged.
        state = holder.get("state")
        if not isinstance(state, dict):
            state = {"version": 1, "processed": [], "active": None, "journal": []}
        write_run_report(state, config, 1, quota_after=None, write_kv=True)
        raise
    state = holder.get("state")
    if isinstance(state, dict):
        brake = bool(holder.get("brake"))
        quota_after = None
        # Never probe quota on the emergency-brake path: the halt must not depend
        # on the network. On other paths it is a best-effort second reading and
        # ``quota_remaining`` returns ``None`` when no API key is configured.
        if not offline and not brake:
            try:
                quota_after = quota_remaining()
            except Exception:  # noqa: BLE001 - the report must never break the run
                quota_after = None
        write_run_report(state, config, code, quota_after=quota_after,
                         write_kv=not brake)
    return code


def _run_impl(config: dict, offline: bool, holder: dict) -> int:
    started = time.time()
    owner = os.environ.get("AUTOMATION_RUN_ID") or f"local-{int(started)}"

    # --- Emergency stop, local sources first: NO network before the brake. ----
    # ``load_state`` may read the KV store over the network; a local stop must
    # not wait for it. The env flag, the sentinel file and the config flag are
    # all evaluated here, before any remote call, so an operator halting a run
    # does not depend on network reachability. The durable KV flag is checked
    # further down, once the KV reader is legitimately needed.
    state_dir = _state_path().parent
    if emergency is not None:
        stopped, reason = emergency.local_stop(state_dir)
        if not stopped and config.get("emergency_stop"):
            stopped, reason = True, "config emergency_stop is true"
        if stopped:
            # No network at all on this path: neither ``load_state`` nor
            # ``save_state`` is called, so the brake returns before any KV read
            # or write. The stop is still reported on stdout via the journal.
            state = {"version": 1, "processed": [], "active": None, "journal": []}
            holder["state"] = state
            holder["brake"] = True
            journal_entry(state, "run_start", dry_run=bool(config["dry_run"]),
                          repository=config["repository"], offline=offline, owner=owner)
            journal_entry(state, "emergency_stop", reason=reason, scope="next_run")
            return 3

    state = load_state()
    holder["state"] = state
    deadline = started + int(config["max_runtime_seconds"])

    journal_entry(state, "run_start", dry_run=bool(config["dry_run"]),
                  repository=config["repository"], offline=offline, owner=owner)

    # --- Emergency stop, durable KV flag (network; after the local sources). --
    # Reaching here means no local brake is set. The KV flag is what stops the
    # next run started by *any* container, so it is checked before any spend.
    if emergency is not None and kv_available() and emergency.kv_stop(kv_get):
        journal_entry(state, "emergency_stop",
                      reason=f"KV key {emergency.KV_KEY!r} is set", scope="next_run")
        save_state(state)
        return 3

    # --- Stop on error: refuse before any spend when a precondition fails. ---
    if not policy.repository_allowed(config["repository"]):
        journal_entry(state, "abort", reason="repository not allowed")
        save_state(state)
        return 2

    # One mission at a time, with automatic recovery from interruption.
    # A prior run killed mid-mission may have left an active record. Decide, from
    # two independent proofs (the KV lock and the recorded conversation's real
    # status), whether to abort, re-attach, or re-queue -- never to duplicate.
    active = state.get("active")
    resume_cid = None
    resume_issue = None
    if active and not config["dry_run"]:
        action, detail = _reconcile_decision(state)
        if action == "abort":
            journal_entry(state, "abort", reason=detail, active=active)
            save_state(state)
            return 2
        if action == "reattach":
            resume_cid = detail
            resume_issue = active.get("issue")
            journal_entry(state, "resume_reattach", conversation=resume_cid,
                          issue=resume_issue,
                          note="a live conversation exists; re-attaching instead "
                               "of starting a duplicate")
        else:
            journal_entry(state, "stale_active_reconciled", previous=active,
                          note="lock expired or absent; mission re-queued for resume")
            state["active"] = None
            save_state(state)
            active = None

    if offline:
        journal_entry(state, "offline", note="no network calls; selection logic only")
        print(json.dumps(config, indent=2))
        save_state(state)
        return 0

    # --- Environment facts (read-only). Turns assumptions into evidence. ---
    env = diagnose_environment()
    journal_entry(state, "environment", **env)

    # --- Fail-closed preflight: refuse unless the guard and team are active. ---
    reasons = preflight.preflight()
    if reasons:
        journal_entry(state, "abort", reason="preflight failed", problems=reasons)
        save_state(state)
        return 2
    journal_entry(state, "preflight_ok", checks=["guard", "team_config"])

    # --- Quota check (never assume the conversation quota is a money cap). ---
    remaining = quota_remaining()
    journal_entry(state, "quota", remaining=remaining)

    # --- Select exactly one authorised mission. ---
    try:
        issues = list_mission_issues(config["repository"], config["mission_label"])
    except RuntimeError as exc:
        journal_entry(state, "abort", reason=str(exc))
        save_state(state)
        return 2

    processed = set(state.get("processed", []))
    resuming = resume_cid is not None

    if resuming:
        # Re-attaching to a mission that a prior run already started: bind this
        # run to the SAME mission (its stable id is the issue number), so the
        # conversation we resume is never confused with a different mission.
        mission = next(
            (i for i in issues if i.get("number") == resume_issue), None
        )
        if mission is None:
            journal_entry(
                state, "abort",
                reason=f"conversation {resume_cid} is still running for issue "
                       f"#{resume_issue}, which is no longer an eligible mission; "
                       "refusing to start a different one while it runs",
                conversation=resume_cid, issue=resume_issue,
            )
            save_state(state)
            return 2
    else:
        mission = policy.select_mission(issues, config["mission_label"], processed)
    if mission is None:
        journal_entry(state, "idle", note="no eligible mission")
        save_state(state)
        return 0

    work_branch = policy.work_branch_name(
        config["work_branch_prefix"], mission["number"], mission.get("title", "")
    )
    # When re-attaching, the one active mission IS this mission: it must not be
    # counted as an *extra* concurrent mission, and no new conversation (thus no
    # new quota spend) is started, so those two preconditions do not apply.
    reasons = policy.evaluate_preconditions(
        repository=config["repository"],
        base_branch=config["base_branch"],
        work_branch=work_branch,
        quota_remaining=(config["quota_min_remaining"] if resuming else remaining),
        quota_min_remaining=config["quota_min_remaining"],
        active_missions=(0 if resuming else (1 if active else 0)),
        max_concurrent_missions=config["max_concurrent_missions"],
        dry_run=config["dry_run"],
    )
    if reasons:
        journal_entry(state, "abort", reasons=reasons, mission=mission["number"])
        save_state(state)
        return 2

    journal_entry(state, "mission_selected", issue=mission["number"],
                  title=mission.get("title", ""), work_branch=work_branch)

    # --- Bus ledger: dedup (read-only). A finished mission is never retried. ---
    # For a real run the bus is not an enhancement: without it there is no
    # deduplication and no durable ledger, so the mission must not start. This is
    # a deliberate fail-closed guard, not a best-effort feature.
    bus = None
    bus_corr = None
    require_bus = bool(config.get("require_durable_bus", True)) and not config["dry_run"]
    if bus_bridge is not None and Bus is not None:
        try:
            bus = Bus(REPO_ROOT / "bus", store=default_store(REPO_ROOT / "bus"))
            bus_corr = bus_bridge.correlation_id(config["repository"], mission["number"])
            if bus_bridge.is_already_finished(bus, bus_corr):
                journal_entry(state, "bus_skip", reason="mission already finished",
                              correlation_id=bus_corr)
                save_state(state)
                return 0
        except Exception as exc:  # noqa: BLE001 - never let the bus crash the run
            journal_entry(state, "bus_error", detail=f"{type(exc).__name__}: {exc}")
            bus = None
    elif require_bus:
        journal_entry(state, "abort", reason="bus unavailable: cannot deduplicate",
                      mission=mission["number"])
        save_state(state)
        return 2

    if require_bus:
        if bus is None or bus_corr is None:
            journal_entry(state, "abort", reason="bus unavailable: refusing to start",
                          mission=mission["number"])
            save_state(state)
            return 2
        report = bus.storage_report()
        if not report.get("durable_across_container"):
            journal_entry(state, "abort",
                          reason="bus storage is not durable across containers",
                          storage=report, mission=mission["number"])
            save_state(state)
            return 2

    if config["dry_run"]:
        journal_entry(state, "dry_run", note="no conversation started",
                      would_run_until=policy.utcnow_iso())
        save_state(state)
        return 0

    # --- Cross-run lock: only one mission may run, across distinct runs. ---
    acquired, detail = acquire_lock(owner, ttl_seconds=int(config["max_runtime_seconds"]) + 600)
    if not acquired:
        journal_entry(state, "abort", reason="mission lock not acquired", detail=detail)
        save_state(state)
        return 2
    journal_entry(state, "lock_acquired", detail=detail, owner=owner)

    # --- Open (or resume) the bus mission now that we hold the single lock. ---
    # Fail-closed: if the mission cannot be opened on the ledger, the run must not
    # proceed, otherwise it would work with no deduplication and no durable record.
    if bus is not None and bus_corr is not None:
        try:
            opened = bus_bridge.open_or_resume(
                bus, repository=config["repository"], issue=mission,
                work_branch=work_branch,
            )
            journal_entry(state, "bus_mission", action=opened["action"],
                          correlation_id=opened["correlation_id"],
                          mission_state=opened["state"],
                          storage=bus.storage_report())
        except Exception as exc:  # noqa: BLE001
            release_lock(owner)
            journal_entry(state, "abort", reason="bus mission could not be opened",
                          detail=f"{type(exc).__name__}: {exc}")
            save_state(state)
            return 2
    elif require_bus:
        release_lock(owner)
        journal_entry(state, "abort", reason="bus unavailable: refusing to start")
        save_state(state)
        return 2

    # --- Resume: re-attach to a live conversation instead of duplicating it. ---
    # A prior run may have created a conversation and then been killed before it
    # could record the outcome. ``_reconcile_decision`` proved (via the KV lock
    # and a live status probe) that this conversation is still running; adopt it.
    if resume_cid:
        journal_entry(state, "conversation_resumed", conversation=resume_cid,
                      issue=resume_issue)
        report_phase("resuming coordinator")
        agent_names = cfg.unique_names(time.strftime("%H%M%S"))
        try:
            final = wait_for(resume_cid, deadline, state_dir=state_dir)
            return _finish_mission(
                state=state, mission=mission, work_branch=work_branch,
                cid=resume_cid, final=final, agent_names=agent_names, bus=bus,
                bus_corr=bus_corr, require_bus=require_bus, owner=owner,
                processed=processed,
            )
        finally:
            release_lock(owner)

    # --- Build the coordinator payload and prove it declares 3 restricted agents. ---
    profile = os.environ.get("TEL99_LLM_PROFILE", "openhands_deepseek-v4.1-flash")
    llm = {"model": cfg.DEFAULT_MODEL, "usage_id": "default"}
    profile_path = pathlib.Path.home() / ".openhands" / "profiles" / f"{profile}.json"
    if profile_path.is_file():
        raw = json.loads(profile_path.read_text(encoding="utf-8"))
        llm = {k: raw[k] for k in ("model", "api_key", "auth_type", "base_url",
                                   "native_tool_calling", "usage_id",
                                   "reasoning_effort") if k in raw}

    agent_names = cfg.unique_names(time.strftime("%H%M%S"))
    payload = build_payload(mission, work_branch, config, llm, names=agent_names)
    payload_problems = preflight.check_payload(payload)
    payload_problems += preflight.check_budget(payload)
    payload_problems += preflight.check_model(payload)
    if payload_problems:
        release_lock(owner)
        journal_entry(state, "abort", reason="payload preflight failed",
                      problems=payload_problems)
        save_state(state)
        return 2
    journal_entry(state, "payload_ok",
                  sub_agents=[d.get("name") for d in payload.get("agent_definitions", [])])

    # Record the active mission BEFORE the conversation exists so a kill in the
    # next instant is still visible to the next run. The real conversation id is
    # added the moment the server returns it (below), so an interrupted run can
    # always be re-attached rather than duplicated.
    state["active"] = {"issue": mission["number"], "work_branch": work_branch,
                       "started_at": policy.utcnow_iso(), "owner": owner,
                       "conversation_id": None}
    save_state(state)
    report_phase("starting coordinator")

    try:
        status, body = _request(
            "POST", f"{agent_server_base()}/api/conversations", payload,
            headers={"X-Session-API-Key": session_key()},
        )
        if status not in (200, 201) or not isinstance(body, dict):
            journal_entry(state, "abort", reason=f"conversation start failed: HTTP {status}")
            state["active"] = None
            save_state(state)
            return 2

        cid = body.get("id") or body.get("conversation_id")
        # Persist the real conversation id at once: a hard kill after this point
        # leaves a recoverable record, and the next run re-attaches to it.
        state["active"] = {"issue": mission["number"], "work_branch": work_branch,
                           "started_at": state["active"]["started_at"], "owner": owner,
                           "conversation_id": cid}
        save_state(state)
        journal_entry(state, "conversation_started", conversation=cid,
                      issue=mission["number"])

        # --- Wait, bounded by the deadline; stop children on timeout or stop. ---
        report_phase("running coordinator")
        final = wait_for(cid, deadline, state_dir=state_dir)
        return _finish_mission(
            state=state, mission=mission, work_branch=work_branch,
            cid=cid, final=final, agent_names=agent_names, bus=bus,
            bus_corr=bus_corr, require_bus=require_bus, owner=owner,
            processed=processed,
        )
    finally:
        release_lock(owner)
        release_lock(owner)


TERMINAL_STATES = ("finished", "error", "stopped")

# ``TaskObservation.status`` value that means a delegated role ran to completion.
_TASK_COMPLETED = ("completed",)
# Base agent names per role (``tel99-dev`` …), used to recognise a delegation
# even if the coordinator reports the name without its per-run suffix.
_BASE_NAMES = {spec.role: spec.name for spec in cfg.ACTIVE_AGENTS}
_ROLE_LABELS = {"development": "developer", "quant": "analyst", "quality": "verifier"}

# A mission's declared acceptance criterion, e.g. "### Critère d'acceptation".
_ACCEPTANCE_HEADING = re.compile(r"crit[èe]res?\s+d['’]acceptation", re.IGNORECASE)


def _get_json(path: str) -> dict:
    status, body = _request("GET", f"{agent_server_base()}{path}",
                            headers={"X-Session-API-Key": session_key()})
    return body if status == 200 and isinstance(body, dict) else {}


def _iter_events(cid: str, page_limit: int = 100, max_pages: int = 200):
    """Yield every persisted event of a conversation, oldest first.

    The agent-server exposes two different event endpoints: the batch
    ``GET /api/conversations/{cid}/events`` takes a *list of event ids* in the
    request body (a bare GET answers HTTP 422), while
    ``GET .../events/search`` is the paginated reader. Reading the batch
    endpoint here silently returned no events, so every delegation was recorded
    as "no proof" and a real mission was marked failed. This walks
    ``events/search`` page by page.
    """
    page_id = ""
    for _ in range(max_pages):
        query = f"?limit={page_limit}"
        if page_id:
            query += f"&page_id={urllib.parse.quote(page_id)}"
        status, body = _request(
            "GET",
            f"{agent_server_base()}/api/conversations/{cid}/events/search{query}",
            headers={"X-Session-API-Key": session_key()},
        )
        if status != 200 or not isinstance(body, dict):
            return
        items = body.get("items") or []
        for item in items:
            yield item
        page_id = body.get("next_page_id") or ""
        if not page_id:
            return


def _observation_text(observation: dict) -> str:
    """Concatenate the text parts of a TaskObservation's ``content``."""
    parts = []
    for item in observation.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(item.get("text") or "")
    return "\n".join(parts).strip()


# Placeholder strings the SDK's ``TaskExecutor`` substitutes when a sub-agent
# produced no usable result. They are non-empty, so a plain length check would
# treat "the role crashed" or "the role returned nothing" as proof the role
# reported. They are matched (case/whitespace-insensitively) and never counted.
_PLACEHOLDER_RESULTS = frozenset(
    {
        "task completed with no result.",
        "task failed.",
    }
)
_PLACEHOLDER_PREFIXES = ("failed to execute task:",)


def _is_placeholder_result(text: str) -> bool:
    """True when ``text`` is an SDK placeholder, not a real sub-agent result."""
    normalized = " ".join((text or "").split()).strip().lower()
    if not normalized:
        return True
    if normalized in _PLACEHOLDER_RESULTS:
        return True
    return normalized.startswith(_PLACEHOLDER_PREFIXES)


def extract_acceptance_criteria(body: str) -> str:
    """Return the mission's declared acceptance criterion, or ``""``.

    Deterministic: it reads the section under a heading mentioning "critère
    d'acceptation" up to the next heading. An empty result means the mission
    declares no acceptance criterion, which makes it unvalidatable — we never
    invent one.
    """
    if not body:
        return ""
    captured: list[str] = []
    capturing = False
    for raw in body.splitlines():
        line = raw.strip()
        is_heading = line.startswith("#") or (line.startswith("**") and line.endswith("**"))
        if _ACCEPTANCE_HEADING.search(line):
            capturing = True
            rest = _ACCEPTANCE_HEADING.sub("", line).strip(" #*:–-")
            if rest:
                captured.append(rest)
            continue
        if capturing:
            if is_heading:
                break
            if line:
                captured.append(line)
    return " ".join(captured).strip()


def _role_proves(obs: dict) -> bool:
    """True when one observation is a real, completed, non-empty result.

    ``is_placeholder`` is precomputed by :func:`collect_evidence`; a raw dict
    that carries only ``result_text`` (or nothing) is normalised here so the
    verdict is identical whether roles were precomputed or recomputed.
    """
    if obs.get("status") not in _TASK_COMPLETED or obs.get("is_error"):
        return False
    if int(obs.get("response_chars", 0)) <= 0:
        return False
    if "is_placeholder" in obs:
        return not obs["is_placeholder"]
    if "result_text" in obs:
        return not _is_placeholder_result(obs.get("result_text") or "")
    # No text available: cannot prove a non-placeholder result.
    return False


def _role_evidence(observations: list, expected_name: str, base_name: str) -> dict:
    """Find the proof a single role produced a result.

    A role is proven only by a ``TaskObservation`` whose ``subagent`` matches the
    role's agent name for this run (identity), that is not an error, whose
    ``status`` is ``completed`` (state) and that carries a *real*, non-placeholder
    result (the SDK writes "Task completed with no result." when a sub-agent
    returns nothing, which is not a report).
    """
    matches = []
    for obs in observations:
        subagent = obs.get("subagent") or ""
        if subagent == expected_name or (base_name and subagent.startswith(base_name)):
            matches.append(obs)
    proven = [o for o in matches if _role_proves(o)]
    return {
        "expected_name": expected_name,
        "delegations": len(matches),
        "proven": len(proven),
        "status": proven[0].get("status") if proven else (
            matches[0].get("status") if matches else ""),
        "task_id": proven[0].get("task_id") if proven else "",
        "response_chars": proven[0].get("response_chars") if proven else 0,
    }


def collect_evidence(cid: str, expected_roles: dict | None = None,
                     mission_body: str = "",
                     acceptance_checks: list | None = None) -> dict:
    """Gather observable proof that each required role actually ran and reported.

    A ``finished`` execution status only says the conversation stopped; it says
    nothing about whether the three roles ran or produced anything. This reads
    what the agent server actually persisted:

      * the coordinator's final response text;
      * every sub-agent delegation the coordinator made, from the ``task_tool_set``
        tool: ``TaskAction`` (the delegation, with ``subagent_type``) and the
        matching ``TaskObservation`` (the result: ``subagent``, ``status``,
        ``content``);
      * any child conversations, as a secondary signal.

    Everything is best-effort: a missing endpoint yields an empty value, which
    the verdict treats as *absence of proof* — never as a success.
    """
    final = _get_json(f"/api/conversations/{cid}/agent_final_response")
    coordinator_response = (final.get("response") or "").strip()

    observations: list[dict] = []
    delegations: list[dict] = []
    children: list[str] = []
    seen_children: set[str] = set()
    for event in _iter_events(cid):
        if not isinstance(event, dict):
            continue
        action = event.get("action")
        if isinstance(action, dict) and action.get("kind") in (
            "TaskAction", "TaskActionWithRisk"
        ):
            delegations.append({
                "subagent_type": action.get("subagent_type") or "",
                "description": action.get("description") or "",
            })
        observation = event.get("observation")
        if not isinstance(observation, dict):
            continue
        kind = observation.get("kind")
        if kind == "TaskObservation":
            text = _observation_text(observation)
            observations.append({
                "task_id": observation.get("task_id") or "",
                "subagent": observation.get("subagent") or "",
                "status": observation.get("status") or "",
                "is_error": bool(observation.get("is_error")),
                "response_chars": len(text),
                "result_text": text[:2000],
                "is_placeholder": _is_placeholder_result(text),
            })
        elif kind == "StartChildConversationObservation":
            child_id = observation.get("conversation_id")
            if isinstance(child_id, str) and child_id and child_id not in seen_children:
                seen_children.add(child_id)
                children.append(child_id)

    child_reports = []
    for child_id in children:
        info = _get_json(f"/api/conversations/{child_id}")
        child_final = _get_json(f"/api/conversations/{child_id}/agent_final_response")
        child_reports.append({
            "id": child_id,
            "status": info.get("execution_status", ""),
            "response_chars": len((child_final.get("response") or "").strip()),
        })

    roles = {}
    for role, expected_name in (expected_roles or {}).items():
        roles[role] = _role_evidence(
            observations, expected_name, _BASE_NAMES.get(role, "")
        )

    return {
        "conversation_id": cid,
        "coordinator_response_chars": len(coordinator_response),
        "observations": observations,
        "delegations": delegations,
        "children": child_reports,
        "roles": roles,
        "acceptance_criteria": extract_acceptance_criteria(mission_body),
        # Structured acceptance-check results, when the caller supplies them.
        # Absent (None) means "no executable criterion was produced", which keeps
        # the historical behaviour: only the declared criterion *text* is checked.
        "acceptance_checks": acceptance_checks,
    }


def verify_outcome(final: str, evidence: dict, *,
                   expected_roles: dict | None = None,
                   mission_body: str = "",
                   acceptance_checks: list | None = None) -> tuple[bool, dict]:
    """Decide whether an outcome is *validated*, from evidence alone.

    The verdict is deliberately conservative. A run is validated only when:

      * the conversation finished;
      * the coordinator produced a final response;
      * **every required role** (Analyst, Developer, Verifier by default) left a
        distinct proof: a ``TaskObservation`` naming that role's agent, in state
        ``completed``, with a non-empty result;
      * the mission declares an acceptance criterion to validate against.

    Any missing proof makes the outcome unvalidated: the mission stays resumable
    and no ``verified`` learning is recorded. This never asserts that the
    acceptance criterion is *satisfied* — it proves the required roles ran and
    reported, and carries the declared criterion so a human or independent
    verifier can judge it.

    Returns ``(validated, verdict)`` where the verdict lists each check, so the
    journal shows exactly why an outcome was or was not accepted.
    """
    checks = []

    def check(name: str, ok: bool, detail: str = "") -> bool:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    finished = check("conversation_finished", final == "finished",
                     f"final status {final!r}")
    has_response = check(
        "coordinator_produced_a_response",
        int(evidence.get("coordinator_response_chars", 0)) > 0,
        f"{evidence.get('coordinator_response_chars', 0)} chars",
    )

    roles = evidence.get("roles")
    if roles is None:
        # Callers that pass a raw evidence dict get the roles recomputed from the
        # observations, so the verdict can never silently skip the role checks.
        roles = {}
        for role, expected_name in (expected_roles or {}).items():
            roles[role] = _role_evidence(
                evidence.get("observations") or [],
                expected_name, _BASE_NAMES.get(role, ""),
            )
    if not roles:
        roles = {spec.role: _role_evidence(
            evidence.get("observations") or [], spec.name, spec.name)
            for spec in cfg.ACTIVE_AGENTS}

    role_checks = []
    for role, info in roles.items():
        label = _ROLE_LABELS.get(role, role)
        role_checks.append(check(
            f"role_{role}_reported",
            int(info.get("proven", 0)) > 0,
            f"{label}: {info.get('proven', 0)} completed proof(s), "
            f"status {info.get('status') or 'none'!r}",
        ))

    criteria = evidence.get("acceptance_criteria")
    if criteria is None:
        criteria = extract_acceptance_criteria(mission_body)
    criteria_check = check(
        "acceptance_criteria_declared",
        bool((criteria or "").strip()),
        f"{len((criteria or '').strip())} chars declared",
    )

    # --- Acceptance checks: the criterion must be *satisfied*, not just declared.
    # A criterion is satisfied only by reproducible external evidence: a recorded
    # command exit code 0, marked reproducible, with an output digest. A red
    # check makes the mission REJECTED even when every role reported PASS (this is
    # gate G3/S-05: "trois rapports PASS mensongers + test echoue => false").
    # A criterion that cannot be automated is NEEDS_HUMAN, never a silent PASS.
    if acceptance_checks is None:
        acceptance_checks = evidence.get("acceptance_checks")
    check_results = []
    satisfied: list[str] = []
    failed: list[str] = []
    needs_human: list[str] = []
    for raw in (acceptance_checks or []):
        if isinstance(raw, dict):
            cid = str(raw.get("id") or raw.get("command") or "check")
            automatable = (bool(raw.get("command")) if raw.get("automatable") is None
                           else bool(raw.get("automatable")))
            exit_code = raw.get("exit_code")
            reproducible = bool(raw.get("reproducible"))
            digest = raw.get("output_digest")
        else:  # an Evidence object or similar: read the attributes defensively
            cid = str(getattr(raw, "claim", None) or getattr(raw, "kind", "check"))
            automatable = bool(getattr(raw, "command", None))
            exit_code = getattr(raw, "exit_code", None)
            reproducible = bool(getattr(raw, "reproducible", False))
            digest = getattr(raw, "output_digest", None)
        if not automatable:
            needs_human.append(cid)
            check_results.append(check(
                f"criterion_{cid}", False,
                "not automatable -> NEEDS_HUMAN"))
            continue
        ok = (exit_code == 0 and reproducible and bool(digest))
        check_results.append(check(
            f"criterion_{cid}", ok,
            f"exit_code={exit_code!r} reproducible={reproducible}"))
        (satisfied if ok else failed).append(cid)

    validated = all([finished, has_response, criteria_check, *role_checks,
                     *check_results])
    return validated, {"validated": validated, "checks": checks,
                       "roles": roles, "acceptance_criteria": criteria,
                       "acceptance_checks": list(acceptance_checks or []),
                       "satisfied": satisfied, "failed": failed,
                       "needs_human": needs_human,
                       "observations": evidence.get("observations") or [],
                       "children": evidence.get("children") or []}



def conversation_status(cid: str) -> tuple[str, str]:
    """Classify a conversation as ``alive``, ``gone`` or ``unknown``.

    Returns ``(outcome, status)`` where ``outcome`` is one of:

    * ``"alive"`` — the server answered 200 and the execution status is not
      terminal: the conversation is still running. ``status`` is that status.
    * ``"gone"`` — the server answered 200 with a terminal status, or answered
      404: the conversation is not running (finished, errored, or removed).
    * ``"unknown"`` — the server could not be reached or answered anything else.
      The caller must fail closed: it cannot prove the conversation is dead.

    A 404 is treated as ``gone`` (a positive proof of absence), while a transport
    error is ``unknown`` — the distinction is what lets the resume path re-queue
    a genuinely dead conversation yet still refuse to duplicate an unreachable
    one.
    """
    if not cid:
        return "gone", ""
    try:
        code, body = _request(
            "GET", f"{agent_server_base()}/api/conversations/{cid}",
            headers={"X-Session-API-Key": session_key()},
        )
    except Exception:  # noqa: BLE001 - a transport error is "cannot tell"
        return "unknown", ""
    if code == 404:
        return "gone", ""
    if code == 200 and isinstance(body, dict):
        status = str(body.get("execution_status") or "")
        if status in TERMINAL_STATES:
            return "gone", status
        return "alive", status
    return "unknown", ""


def interrupt_conversation(cid: str) -> bool:
    """Ask the agent server to interrupt a running conversation.

    This is the *interrupt an active mission* half of the kill-switch. It only
    reaches a conversation the caller can address on its agent server; it does
    not reach a conversation hosted by another container, which must be handled
    by the operator procedure in the runbook. Returns True when the server
    accepted the request.
    """
    headers = {"X-Session-API-Key": session_key()}
    status, _ = _request(
        "POST", f"{agent_server_base()}/api/conversations/{cid}/interrupt",
        headers=headers,
    )
    return status in (200, 202, 204)


def wait_for(cid: str, deadline: float, poll: float = 5.0,
             state_dir: str | pathlib.Path | None = None,
             confirm_grace_polls: int = 3) -> str:
    """Poll a conversation until a terminal state, the deadline or a stop.

    While a conversation runs, the *local* emergency brake is re-read on every
    poll (no network, so a stop is honoured within one poll interval). When it is
    set, the conversation is interrupted and the function returns ``"stopped"``.
    The deadline path also interrupts the child, so no work is left running
    unattended. This only interrupts the conversation this run is driving.

    ``waiting_for_confirmation`` is not terminal: an unattended run has no one to
    answer it. Left alone it burns the whole deadline and is then killed by the
    platform timeout. After ``confirm_grace_polls`` consecutive polls in that
    state the conversation is interrupted and ``"confirmation_required"`` is
    returned, so the run fails fast, on purpose, and the mission stays resumable.
    """
    headers = {"X-Session-API-Key": session_key()}
    brake_dir = pathlib.Path(state_dir) if state_dir is not None else _state_path().parent
    waiting_polls = 0
    while time.time() < deadline:
        if emergency is not None and emergency.local_stop(brake_dir)[0]:
            interrupt_conversation(cid)
            return "stopped"
        status, body = _request(
            "GET", f"{agent_server_base()}/api/conversations/{cid}", headers=headers
        )
        if status == 200 and isinstance(body, dict):
            state = body.get("execution_status")
            if state in TERMINAL_STATES:
                return state
            if state == "waiting_for_confirmation":
                waiting_polls += 1
                if waiting_polls >= confirm_grace_polls:
                    interrupt_conversation(cid)
                    return "confirmation_required"
            else:
                waiting_polls = 0
        time.sleep(poll)
    # Deadline reached: stop the child so no work is left running unattended.
    interrupt_conversation(cid)
    return "timeout"


def main() -> int:
    parser = argparse.ArgumentParser(description="TEL99 cloud-autonomy orchestrator.")
    parser.add_argument("--config", default=None,
                        help="path to the validated plugin config JSON")
    parser.add_argument("--offline", action="store_true",
                        help="selection logic only; no network calls")
    parser.add_argument("--diagnose", action="store_true",
                        help="print environment facts and preflight, then exit")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.diagnose:
        report = {"environment": diagnose_environment(),
                  "preflight_problems": preflight.preflight()}
        print(json.dumps(report, indent=2))
        return 0 if not report["preflight_problems"] else 2
    try:
        code = run(config, offline=args.offline)
    except Exception as exc:  # noqa: BLE001 - report any failure to the platform
        print(f"ERROR: {exc}", file=sys.stderr)
        fire_callback("FAILED", str(exc))
        return 1
    # The script runner does not complete a run on its own: signal it on every
    # exit path so the run never stays RUNNING until the platform timeout. The
    # callback carries the durable report's business verdict when one is readable,
    # so the platform sees MISSION_ACCEPTED vs SCRIPT-OK, not just COMPLETED.
    outcome = None if args.offline else read_run_report()
    fire_callback("COMPLETED" if code == 0 else "FAILED",
                  None if code == 0 else f"orchestrator exit {code}",
                  outcome=outcome)
    return code


if __name__ == "__main__":
    sys.exit(main())
