#!/usr/bin/env python3
"""Render the TEL99 agent definition files from team_config.py.

Keeping the Markdown files generated from one source avoids drift between the
documented roles and the actual definitions.

- Active roles  -> .agents/agents/<name>.md        (auto-discovered by the SDK)
- Reserved roles -> .agents/agents/reserve/<name>.md (ignored by the SDK,
  which only reads top-level *.md files, so they cannot be triggered)

Usage:
    python scripts/agents/render_agents.py            # write files
    python scripts/agents/render_agents.py --check     # fail if out of date
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import team_config as cfg  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / ".agents" / "agents"
RESERVE_DIR = AGENTS_DIR / "reserve"

RESERVE_README = """# Reserved TEL99 specializations

These definitions mirror the remaining roles of `docs/agents/ROLE_CATALOG.md`.
They are **prepared but not active**.

The OpenHands SDK only loads top-level `*.md` files from `.agents/agents`, so
nothing in this subdirectory can be triggered as a sub-agent. To activate one,
move its file up one level (`.agents/agents/`) and add its name to
`ACTIVE_AGENTS` in `scripts/agents/team_config.py`.

No reserved role runs, is scheduled, or has any permission until an operator
does that explicitly.
"""


def render(spec: cfg.AgentSpec) -> str:
    fm = spec.frontmatter()
    tools = "\n".join(f"  - {t}" for t in fm["tools"])
    header = (
        "---\n"
        f"name: {fm['name']}\n"
        f"description: {fm['description']}\n"
        f"model: {fm['model']}\n"
        f"permission_mode: {fm['permission_mode']}\n"
        f"max_iteration_per_run: {fm['max_iteration_per_run']}\n"
        f"max_budget_per_run: {fm['max_budget_per_run']}\n"
        "tools:\n"
        f"{tools}\n"
        "hooks:\n"
        "  pre_tool_use:\n"
        "    - matcher: terminal\n"
        "      hooks:\n"
        "        - type: command\n"
        f"          command: {cfg.guard_command()}\n"
        "          timeout: 20\n"
        "---\n\n"
    )
    return header + spec.full_prompt() + "\n"


def expected_files() -> dict[pathlib.Path, str]:
    files: dict[pathlib.Path, str] = {}
    for spec in cfg.ACTIVE_AGENTS:
        files[AGENTS_DIR / f"{spec.name}.md"] = render(spec)
    for spec in cfg.reserved_agents():
        files[RESERVE_DIR / f"{spec.name}.md"] = render(spec)
    files[RESERVE_DIR / "README.md"] = RESERVE_README
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="do not write; fail if any file differs")
    args = parser.parse_args()

    files = expected_files()
    stale = []
    for path, content in files.items():
        if args.check:
            current = path.read_text(encoding="utf-8") if path.is_file() else None
            if current != content:
                stale.append(path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"wrote {path.relative_to(REPO_ROOT)}")

    if args.check and stale:
        print("Out of date:")
        for path in stale:
            print(f"  - {path.relative_to(REPO_ROOT)}")
        return 1
    if args.check:
        print(f"OK: {len(files)} agent definition files match team_config.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
