#!/usr/bin/env python3
"""Read-only TEL99 multi-role audit. No LLM/API credentials required."""
import argparse
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROLES = {
    "coordination": ["AGENTS.md", "docs/agents/HERMES_SIMPLE_TEAM.md"],
    "development": ["src/terminal", "site/terminal", "tests"],
    "quant": ["scripts/terminal", "research/terminal"],
    "cloud": [".github/workflows"],
    "quality": ["tests", "AGENTS.md"],
    "security": ["AGENTS.md", ".github/workflows"],
    "mobile": ["site/terminal"],
    "documentation": ["docs/smart-view"],
    "evaluation": ["results/terminal"],
    "market_data": ["collector", "scripts/terminal/collect.py"],
    "monitoring": [".github/workflows", "site/terminal/data.json"],
    "release": [".github/workflows/tel99-terminal.yml"],
}
def audit():
    checks = {}
    for role, paths in ROLES.items():
        checks[role] = {"paths": [{"path": p, "exists": (ROOT / p).exists()} for p in paths],
                        "status": "inventory_only"}
    return {"schema": 1, "mode": "read_only", "agents_running": 0,
            "roles_defined": len(ROLES), "orders_allowed": False,
            "deploy_allowed": False, "timestamp_utc": int(time.time()),
            "roles": checks}
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/tmp/tel99-team-audit.json")
    args = parser.parse_args()
    report = audit()
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Read-only audit: {len(report['roles'])} roles inventoried; 0 agents launched; report={out}")
if __name__ == "__main__":
    main()
