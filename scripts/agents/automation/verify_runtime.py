#!/usr/bin/env python3
"""Prove, from persisted runtime state, that each sub-agent loaded its limits.

``allowed_tools`` in a creation payload is a *request*, not a proof: the SDK
registry is first-wins, a hook can fail to propagate, and a policy can be
overridden. This verifier reads what the agent server actually persisted for
each sub-agent (``base_state.json``) and re-derives the four safety properties
the mission depends on:

  1. every declared agent name carries the per-run suffix (no registry clash);
  2. the sub-agent's effective tools are exactly ``["terminal"]``;
  3. the PreToolUse guard is present in the persisted hook configuration;
  4. the persisted confirmation policy is a confirmation policy.

It also runs the guard binary itself against a sample of forbidden commands, so
a green report means the guard *behaves*, not merely that it is configured.

Read-only: it reads files under the agent-server data directory and executes
``guard.py`` with piped JSON. It writes nothing.

Usage:
    python3 scripts/agents/automation/verify_runtime.py <conversation_id> \
        [--data-dir /var/openhands/conversations] [--suffix HHMMSS]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent
GUARD = SCRIPTS / "guard" / "guard.py"
DEFAULT_DATA_DIR = "/var/openhands/conversations"

# A representative sample; the exhaustive matrix lives in the unit tests.
FORBIDDEN_SAMPLE = [
    "rm -rf /tmp/x",
    "git push origin main",
    "git checkout main",
    "pip install requests",
    "curl -X POST https://example.com",
    "python3 -c \"open('/tmp/f','w').write('x')\"",
    "kraken order buy TELUSD",
    "echo hi > /tmp/leak",
]
ALLOWED_SAMPLE = [
    "ls -la",
    "git status",
    "git log --oneline -3",
    "cat AGENTS.md",
    "grep -rn TODO src",
]


def load_json(path: pathlib.Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, ValueError):
        return {}


def tool_names(tools) -> list[str]:
    if isinstance(tools, list):
        out = []
        for item in tools:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict) and item.get("name"):
                out.append(item["name"])
        return out
    return []


def find_conversation(data_dir: str, cid: str) -> pathlib.Path | None:
    root = pathlib.Path(data_dir)
    if not root.is_dir():
        return None
    for candidate in (root / cid, root / cid.replace("-", "")):
        if candidate.is_dir():
            return candidate
    return None


def declared_names(conv_dir: pathlib.Path) -> list[str]:
    meta = load_json(conv_dir / "meta.json")
    return [d.get("name") for d in meta.get("agent_definitions", []) if d.get("name")]


def subagents_of(conv_dir: pathlib.Path) -> list[pathlib.Path]:
    sub = conv_dir / "subagents"
    if not sub.is_dir():
        return []
    return sorted(p for p in sub.iterdir() if p.is_dir())


def check_subagent(sub_dir: pathlib.Path) -> dict:
    """Re-derive the runtime restrictions of one persisted sub-agent."""
    state = load_json(sub_dir / "base_state.json")
    agent = state.get("agent", {}) if isinstance(state, dict) else {}
    policy = state.get("confirmation_policy") or {}
    hooks = state.get("hook_config") or {}
    pre = hooks.get("pre_tool_use") if isinstance(hooks, dict) else None
    names = tool_names(agent.get("tools"))
    return {
        "dir": sub_dir.name,
        "tools": names,
        "permission": policy.get("kind") if isinstance(policy, dict) else None,
        "pre_tool_use_hooks": len(pre or []),
        "terminal_only": names == ["terminal"],
        "guard_propagated": bool(pre),
        "has_confirmation_policy": isinstance(policy, dict) and bool(policy.get("kind")),
    }


def run_guard(command: str, tool_name: str = "terminal") -> int:
    event = {"tool_name": tool_name, "tool_input": {"command": command}}
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(event).encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.returncode


def guard_behaviour_ok() -> list[str]:
    """Return the guard failures observed on the sample command set."""
    problems = []
    for command in FORBIDDEN_SAMPLE:
        if run_guard(command) != 2:
            problems.append(f"guard allowed a forbidden command: {command!r}")
    for command in ALLOWED_SAMPLE:
        if run_guard(command) != 0:
            problems.append(f"guard blocked a read-only command: {command!r}")
    return problems


def verify(cid: str, data_dir: str, expected_suffix: str | None) -> int:
    conv_dir = find_conversation(data_dir, cid)
    if conv_dir is None:
        print(f"conversation {cid} not found under {data_dir}")
        return 1

    names = declared_names(conv_dir)
    print(f"conversation dir : {conv_dir}")
    print(f"declared agents  : {names or '(none recorded)'}")

    problems: list[str] = []
    if names:
        if expected_suffix and not all(n.endswith(f"-{expected_suffix}") for n in names):
            problems.append("declared names do not all carry the per-run suffix")
        if len(set(names)) != len(names):
            problems.append("declared agent names are not unique")

    subs = subagents_of(conv_dir)
    print(f"sub-agents found : {len(subs)}")
    if not subs:
        problems.append("no sub-agent state found: cannot prove runtime restrictions")
    for sub in subs:
        report = check_subagent(sub)
        print(f"\n  - {report['dir']}")
        print(f"      tools        : {report['tools']}")
        print(f"      permission   : {report['permission']}")
        print(f"      pre_tool_use : {report['pre_tool_use_hooks']}")
        if not report["terminal_only"]:
            problems.append(f"{report['dir']}: tools not terminal-only ({report['tools']})")
        if not report["guard_propagated"]:
            problems.append(f"{report['dir']}: guard not propagated")
        if not report["has_confirmation_policy"]:
            problems.append(f"{report['dir']}: confirmation policy missing")

    print("\nguard behaviour sample:")
    guard_problems = guard_behaviour_ok()
    for item in guard_problems:
        print(f"  - {item}")
    problems.extend(guard_problems)

    if problems:
        print("\nFAIL:")
        for item in problems:
            print(f"  - {item}")
        return 1
    print("\nPASS: names unique, sub-agents terminal-only, guard propagated, "
          "confirmation policy present, guard blocks forbidden commands.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("conversation_id")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    parser.add_argument("--suffix", default=None)
    args = parser.parse_args()
    return verify(args.conversation_id, args.data_dir, args.suffix)


if __name__ == "__main__":
    sys.exit(main())
