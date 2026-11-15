"""Fail-closed preflight for the TEL99 cloud-autonomy orchestrator.

The orchestrator must refuse to start any conversation unless the guard, the
hooks, the permissions and the team definitions are provably active. This
module answers one question: *is it safe to run?* It never starts work; it only
reads files and inspects the payload it is about to send.

A single failed check returns a non-empty list of reasons, and the orchestrator
aborts with exit 2 before any spend.

The checks are deliberately structural, not behavioural:
  * the guard file exists and blocks a forbidden command (executed for real);
  * ``team_config`` is valid (three terminal-only agents, guard wired);
  * the coordinator payload declares exactly the three expected roles;
  * each declared sub-agent is terminal-only, carries the guard hook, and a
    confirmation policy.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
GUARD = SCRIPTS / "guard" / "guard.py"

# A command that must be blocked. If the guard lets it through, the guard is
# not doing its job and the run must not start.
FORBIDDEN_PROBE = "git push origin main"
ALLOWED_PROBE = "git status"


def _load_team_config():
    sys.path.insert(0, str(SCRIPTS))
    import team_config  # noqa: PLC0415 - local import keeps this module importable

    return team_config


def _run_guard(command: str) -> int:
    event = {"tool_name": "terminal", "tool_input": {"command": command}}
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(event).encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.returncode


def check_guard_active() -> list[str]:
    """The guard file must exist and block a forbidden command for real."""
    problems: list[str] = []
    if not GUARD.is_file():
        return [f"guard missing at {GUARD}"]
    if _run_guard(FORBIDDEN_PROBE) != 2:
        problems.append("guard did not block a forbidden command")
    if _run_guard(ALLOWED_PROBE) != 0:
        problems.append("guard blocked a read-only command")
    return problems


def check_team_config() -> list[str]:
    """team_config must validate and expose three terminal-only agents."""
    problems: list[str] = []
    try:
        cfg = _load_team_config()
        cfg.validate()
    except Exception as exc:  # noqa: BLE001 - any failure is a blocking problem
        return [f"team_config invalid: {exc}"]
    if len(cfg.ACTIVE_AGENTS) != 3:
        problems.append(f"expected 3 active agents, found {len(cfg.ACTIVE_AGENTS)}")
    for spec in cfg.ACTIVE_AGENTS:
        if tuple(spec.tools) != ("terminal",):
            problems.append(f"{spec.name} is not terminal-only: {spec.tools}")
        if spec.permission_mode not in (
            "always_confirm", "never_confirm", "confirm_risky"
        ):
            problems.append(f"{spec.name} has no valid permission mode")
    return problems


def check_payload(payload: dict) -> list[str]:
    """The coordinator payload must declare three restricted sub-agents."""
    problems: list[str] = []
    definitions = payload.get("agent_definitions") or []
    if len(definitions) != 3:
        problems.append(f"payload declares {len(definitions)} sub-agents, expected 3")
    names = [d.get("name") for d in definitions]
    if len(set(names)) != len(names):
        problems.append("payload sub-agent names are not unique")
    for definition in definitions:
        name = definition.get("name")
        if list(definition.get("tools") or []) != ["terminal"]:
            problems.append(f"{name}: tools not terminal-only")
        hooks = (definition.get("hooks") or {}).get("pre_tool_use")
        if not hooks:
            problems.append(f"{name}: guard hook not declared")
        if not definition.get("permission_mode"):
            problems.append(f"{name}: permission mode missing")
    parent_tools = [t.get("name") for t in (payload.get("agent") or {}).get("tools", [])]
    if "task_tool_set" not in parent_tools:
        problems.append("parent cannot delegate (task_tool_set missing)")
    if "terminal" not in parent_tools:
        problems.append("parent is not terminal-capable")
    return problems


def preflight(payload: dict | None = None) -> list[str]:
    """Return every reason the run must NOT proceed. Empty means safe."""
    reasons = []
    reasons += check_guard_active()
    reasons += check_team_config()
    if payload is not None:
        reasons += check_payload(payload)
    return reasons
