#!/usr/bin/env python3
"""TEL99 pilot runner — create a coordinator conversation that delegates.

Read-only with respect to the TEL99 repository: it only talks to the local
OpenHands agent-server HTTP API and never writes inside the repo.

The coordinator gets the three active sub-agents (dev, analyst, verifier) with
per-run unique names, a terminal-only allowlist, ``confirm_risky`` permissions,
a shared PreToolUse guard, and configurable iteration/budget limits.

The LLM credentials are read at runtime from a saved profile (default:
openhands_deepseek-v4.1-flash) and are never written to disk.

Usage (inside an OpenHands session, agent-server on :60000):

    python scripts/agents/run_pilot.py --dry-run
    python scripts/agents/run_pilot.py --wait

Environment:
    TEL99_API_BASE        default http://localhost:60000
    TEL99_SESSION_KEY     session API key (else read from /proc/1/environ)
    TEL99_LLM_PROFILE     profile filename without .json (default below)
    TEL99_MAX_ITERATIONS  parent iteration cap
    TEL99_MAX_BUDGET_USD  parent USD cap
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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import team_config as cfg  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PROFILE_DIR = pathlib.Path.home() / ".openhands" / "profiles"
DEFAULT_PROFILE = os.environ.get("TEL99_LLM_PROFILE", "openhands_deepseek-v4.1-flash")
LLM_KEYS = (
    "model", "api_key", "auth_type", "base_url", "native_tool_calling",
    "usage_id", "reasoning_effort",
)

DEFAULT_MISSION = (
    "Diagnostic lecture seule TEL99. Identifie les trois blocages verifiables les "
    "plus importants pour une utilisation mobile fiable. Pour chacun: fichier ou "
    "source, preuve (commande + sortie), gravite, correctif minimal suggere, test de "
    "non-regression. Ne modifie aucun fichier, ne passe aucun ordre."
)


def api_base() -> str:
    return os.environ.get("TEL99_API_BASE", "http://localhost:60000").rstrip("/")


def session_key() -> str:
    key = os.environ.get("TEL99_SESSION_KEY")
    if key:
        return key
    try:
        blob = pathlib.Path("/proc/1/environ").read_bytes().decode(errors="ignore")
    except OSError:
        return ""
    for part in blob.split("\x00"):
        if part.startswith("SESSION_API_KEY="):
            return part.split("=", 1)[1]
    return ""


def llm_config(profile: str = DEFAULT_PROFILE) -> dict:
    """Load the free LLM profile at runtime (never committed to the repo)."""
    path = PROFILE_DIR / f"{profile}.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"LLM profile not found: {path}. Set TEL99_LLM_PROFILE to an existing profile."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: raw[k] for k in LLM_KEYS if k in raw}


def request(method: str, path: str, payload: dict | None = None) -> tuple[int, object]:
    url = api_base() + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    key = session_key()
    if key:
        req.add_header("X-Session-API-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode()
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="ignore")


def build_agent_definitions(suffix: str) -> list[dict]:
    """Inline agent definitions with per-run unique names and the guard hook."""
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
                "system_prompt": spec.full_prompt(),
                "permission_mode": spec.permission_mode,
                "max_iteration_per_run": cfg.DEFAULT_AGENT_MAX_ITERATIONS,
                "max_budget_per_run": cfg.DEFAULT_AGENT_MAX_BUDGET_USD,
                "hooks": hooks,
                "when_to_use_examples": [f"read-only {spec.role} check"],
                "level": "project",
            }
        )
    return definitions


def build_mission(mission: str, suffix: str) -> str:
    names = cfg.unique_names(suffix)
    roles = ", ".join(f"{r}={n}" for r, n in names.items())
    return (
        "Tu es le coordinateur de l'equipe TEL99 (lecture seule). "
        f"Sous-agents disponibles: {roles}. "
        "Delegue chaque sous-tache avec l'outil de delegation, en restreignant les "
        "outils du parent (sub_agent_scope). Verifie chaque preuve, distingue constat "
        "et hypothese, puis resume preuves, limites et actions necessitant un accord. "
        "N'essaie jamais de contourner le garde-fou.\n\n"
        f"Mission: {mission}"
    )


def build_payload(mission: str, suffix: str, llm: dict | None = None) -> dict:
    llm = llm if llm is not None else llm_config()
    return {
        "workspace": {"kind": "LocalWorkspace", "working_dir": str(REPO_ROOT)},
        "worktree": False,
        "confirmation_policy": {"kind": "ConfirmRisky", "threshold": "HIGH",
                                "confirm_unknown": True},
        "security_analyzer": {"kind": "LLMSecurityAnalyzer"},
        "max_iterations": cfg.DEFAULT_MAX_ITERATIONS,
        "max_budget_per_run": cfg.DEFAULT_MAX_BUDGET_USD,
        "stuck_detection": True,
        "autotitle": False,
        "hook_config": cfg.hook_config(),
        "initial_message": {
            "role": "user",
            "content": [{"type": "text", "text": build_mission(mission, suffix)}],
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
        "agent_definitions": build_agent_definitions(suffix),
        "tags": {"purpose": "tel99-pilot", "mode": "readonly"},
    }


def wait_for(cid: str, timeout: int) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        _, info = request("GET", f"/api/conversations/{cid}")
        if isinstance(info, dict):
            state = info.get("execution_status")
            if state in ("finished", "error", "stopped"):
                return state
        time.sleep(5)
    return "timeout"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the TEL99 read-only pilot.")
    parser.add_argument("--mission", default=DEFAULT_MISSION)
    parser.add_argument("--suffix", default=None,
                        help="unique per-run suffix (default: HHMMSS)")
    parser.add_argument("--profile", default=DEFAULT_PROFILE,
                        help="saved LLM profile name (no .json)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the payload without calling the API")
    parser.add_argument("--wait", action="store_true",
                        help="poll until the conversation finishes")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    cfg.validate()
    suffix = args.suffix or time.strftime("%H%M%S")
    llm = llm_config(args.profile)
    payload = build_payload(args.mission, suffix, llm)

    if args.dry_run:
        safe = json.loads(json.dumps(payload))
        safe["agent"]["llm"]["api_key"] = "***"
        print(json.dumps(safe, indent=2))
        print(f"\n[dry-run] agent names: {cfg.unique_names(suffix)}")
        return 0

    status, body = request("POST", "/api/conversations", payload)
    print(f"POST /api/conversations -> HTTP {status}")
    if status not in (200, 201) or not isinstance(body, dict):
        print(body)
        return 1
    cid = body.get("id") or body.get("conversation_id")
    print(f"conversation: {cid}")
    print(f"agent names: {cfg.unique_names(suffix)}")
    print(f"verify with: python scripts/agents/verify_delegation.py {cid} --suffix {suffix}")
    if args.wait and cid:
        print(f"final status: {wait_for(cid, args.timeout)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
