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
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import policy  # noqa: E402
import team_config as cfg  # noqa: E402

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
    fallback, used read-only here.
    """
    return (
        os.environ.get("TEL99_GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or ""
    )


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
def build_payload(mission_issue: dict, work_branch: str, config: dict, llm: dict) -> dict:
    """Assemble the coordinator payload from the existing team configuration.

    The three agent definitions, their prompts, the read-only contract and the
    PreToolUse guard all come from ``team_config`` — this function only wires
    them together and adds the mission text.
    """
    suffix = time.strftime("%H%M%S")
    names = cfg.unique_names(suffix)
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
        "confirmation_policy": {
            "kind": "ConfirmRisky",
            "threshold": "HIGH",
            "confirm_unknown": True,
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
# Main
# --------------------------------------------------------------------------- #
def load_config(path: str | None) -> dict:
    config = dict(DEFAULT_CONFIG)
    if path:
        try:
            loaded = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                config.update(loaded)
        except (OSError, ValueError) as exc:
            raise SystemExit(f"cannot read config {path}: {exc}")
    return config


def run(config: dict, offline: bool = False) -> int:
    state = load_state()
    started = time.time()
    deadline = started + int(config["max_runtime_seconds"])

    journal_entry(state, "run_start", dry_run=bool(config["dry_run"]),
                  repository=config["repository"], offline=offline)

    # --- Stop on error: refuse before any spend when a precondition fails. ---
    if not policy.repository_allowed(config["repository"]):
        journal_entry(state, "abort", reason="repository not allowed")
        save_state(state)
        return 2

    # One mission at a time.
    active = state.get("active")
    if active and not config["dry_run"]:
        journal_entry(state, "abort", reason="a mission is already active", active=active)
        save_state(state)
        return 2

    if offline:
        journal_entry(state, "offline", note="no network calls; selection logic only")
        print(json.dumps(config, indent=2))
        save_state(state)
        return 0

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
    mission = policy.select_mission(issues, config["mission_label"], processed)
    if mission is None:
        journal_entry(state, "idle", note="no eligible mission")
        save_state(state)
        return 0

    work_branch = policy.work_branch_name(
        config["work_branch_prefix"], mission["number"], mission.get("title", "")
    )
    reasons = policy.evaluate_preconditions(
        repository=config["repository"],
        base_branch=config["base_branch"],
        work_branch=work_branch,
        quota_remaining=remaining,
        quota_min_remaining=config["quota_min_remaining"],
        active_missions=1 if active else 0,
        max_concurrent_missions=config["max_concurrent_missions"],
        dry_run=config["dry_run"],
    )
    if reasons:
        journal_entry(state, "abort", reasons=reasons, mission=mission["number"])
        save_state(state)
        return 2

    journal_entry(state, "mission_selected", issue=mission["number"],
                  title=mission.get("title", ""), work_branch=work_branch)

    if config["dry_run"]:
        journal_entry(state, "dry_run", note="no conversation started",
                      would_run_until=policy.utcnow_iso())
        save_state(state)
        return 0

    # --- Start the coordinator (existing team, unchanged). ---
    profile = os.environ.get("TEL99_LLM_PROFILE", "openhands_deepseek-v4.1-flash")
    llm = {"model": cfg.DEFAULT_MODEL, "usage_id": "default"}
    profile_path = pathlib.Path.home() / ".openhands" / "profiles" / f"{profile}.json"
    if profile_path.is_file():
        raw = json.loads(profile_path.read_text(encoding="utf-8"))
        llm = {k: raw[k] for k in ("model", "api_key", "auth_type", "base_url",
                                   "native_tool_calling", "usage_id",
                                   "reasoning_effort") if k in raw}

    payload = build_payload(mission, work_branch, config, llm)
    state["active"] = {"issue": mission["number"], "work_branch": work_branch,
                       "started_at": policy.utcnow_iso()}
    save_state(state)

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
    journal_entry(state, "conversation_started", conversation=cid, issue=mission["number"])

    # --- Wait, bounded by the deadline; stop children on timeout. ---
    final = wait_for(cid, deadline)
    journal_entry(state, "conversation_finished", conversation=cid, status=final)

    state["processed"] = sorted(processed | {mission["number"]})
    state["active"] = None
    save_state(state)
    return 0 if final == "finished" else 2


TERMINAL_STATES = ("finished", "error", "stopped")


def wait_for(cid: str, deadline: float, poll: float = 5.0) -> str:
    """Poll a conversation until a terminal state or the deadline."""
    headers = {"X-Session-API-Key": session_key()}
    while time.time() < deadline:
        status, body = _request(
            "GET", f"{agent_server_base()}/api/conversations/{cid}", headers=headers
        )
        if status == 200 and isinstance(body, dict):
            state = body.get("execution_status")
            if state in TERMINAL_STATES:
                return state
        time.sleep(poll)
    # Deadline reached: stop the child so no work is left running unattended.
    _request("POST", f"{agent_server_base()}/api/conversations/{cid}/interrupt",
             headers=headers)
    return "timeout"


def main() -> int:
    parser = argparse.ArgumentParser(description="TEL99 cloud-autonomy orchestrator.")
    parser.add_argument("--config", default=None,
                        help="path to the validated plugin config JSON")
    parser.add_argument("--offline", action="store_true",
                        help="selection logic only; no network calls")
    args = parser.parse_args()
    config = load_config(args.config)
    return run(config, offline=args.offline)


if __name__ == "__main__":
    sys.exit(main())
