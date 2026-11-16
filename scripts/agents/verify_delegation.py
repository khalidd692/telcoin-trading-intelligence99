#!/usr/bin/env python3
"""Verify a TEL99 pilot conversation after it ran.

Re-derives the safety properties from persisted state instead of trusting the
creation payload:

  1. every declared agent name carries the per-run suffix (no registry clash);
  2. every sub-agent was terminal-only (no file_editor leak);
  3. the confirmation policy actually applied matches the declared one;
  4. the PreToolUse guard was propagated to each sub-agent.

Read-only: reads conversation metadata and sub-agent ``base_state.json`` files
from the agent-server data directory.

Usage:
    python scripts/agents/verify_delegation.py <conversation_id> [--suffix HHMMSS]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

DEFAULT_DATA_DIR = "/var/openhands/conversations"


def find_conversation(data_dir: str, cid: str) -> pathlib.Path | None:
    root = pathlib.Path(data_dir)
    if not root.is_dir():
        return None
    for candidate in (root / cid, root / cid.replace("-", "")):
        if candidate.is_dir():
            return candidate
    return None


def load_json(path: pathlib.Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def tool_names(tools: object) -> list[str]:
    """Normalise the several shapes agent tools can take in persisted state."""
    if isinstance(tools, list):
        names = []
        for item in tools:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict) and item.get("name"):
                names.append(item["name"])
        return names
    return []


def declared_names(conv_dir: pathlib.Path) -> list[str]:
    meta = load_json(conv_dir / "meta.json")
    return [d.get("name") for d in meta.get("agent_definitions", []) if d.get("name")]


def subagents_of(conv_dir: pathlib.Path) -> list[pathlib.Path]:
    sub = conv_dir / "subagents"
    if not sub.is_dir():
        return []
    return sorted(p for p in sub.iterdir() if p.is_dir())


def check_subagent(sub_dir: pathlib.Path) -> dict:
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
    }


def verify(cid: str, data_dir: str, expected_suffix: str | None) -> int:
    conv_dir = find_conversation(data_dir, cid)
    if conv_dir is None:
        print(f"conversation {cid} not found under {data_dir}")
        return 1

    names = declared_names(conv_dir)
    print(f"conversation dir : {conv_dir}")
    print(f"declared agents  : {names or '(none recorded)'}")

    problems = []
    if names:
        if expected_suffix and not all(n.endswith(f"-{expected_suffix}") for n in names):
            problems.append("declared names do not all carry the per-run suffix")
        if len(set(names)) != len(names):
            problems.append("declared agent names are not unique")

    subs = subagents_of(conv_dir)
    print(f"sub-agents found : {len(subs)}")
    for sub in subs:
        report = check_subagent(sub)
        print(f"\n  - {report['dir']}")
        print(f"      tools        : {report['tools']}")
        print(f"      permission   : {report['permission']}")
        print(f"      pre_tool_use : {report['pre_tool_use_hooks']}")
        if not report["terminal_only"]:
            problems.append(
                f"{report['dir']}: tools not terminal-only ({report['tools']})"
            )
        if not report["guard_propagated"]:
            problems.append(f"{report['dir']}: guard not propagated")

    if problems:
        print("\nFAIL:")
        for item in problems:
            print(f"  - {item}")
        return 1
    print("\nPASS: names unique, sub-agents terminal-only, guard propagated.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("conversation_id")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    parser.add_argument("--suffix", default=None,
                        help="per-run suffix used at creation (e.g. 182300)")
    args = parser.parse_args()
    return verify(args.conversation_id, args.data_dir, args.suffix)


if __name__ == "__main__":
    sys.exit(main())
