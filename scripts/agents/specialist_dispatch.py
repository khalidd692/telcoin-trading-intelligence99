"""On-demand mobilization of all 12 TEL99 specialist roles without launching all at once.

Keeps ``team_config.ACTIVE_AGENTS`` (3) and ``.agents/agents/reserve/`` (9)
untouched so SDK auto-discovery and CI checks remain strictly intact, while
allowing Antigravity IDE / CLI orchestrators to select and brief up to
``MAX_CONCURRENT_SPECIALISTS`` specialists on demand.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.agents import team_config

MAX_CONCURRENT_SPECIALISTS = 4
MAX_BRIEF_TASK_CHARS = 2000
MAX_BRIEF_LESSONS = 3

ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "development": ("python", "js", "javascript", "code", "bug", "fix", "patch", "function", "refactor", "test"),
    "quant": ("signal", "backtest", "leakage", "indicator", "kraken", "strategy", "quant", "freshness"),
    "quality": ("verify", "verifier", "reproduce", "audit", "regression", "acceptance", "check", "proof"),
    "coordination": ("plan", "split", "coordinate", "orchestrate", "dependency", "dag", "handoff", "multi"),
    "cloud": ("cloud", "github actions", "workflow", "ci", "cron", "schedule", "dispatch", "pages"),
    "security": ("security", "guard", "secret", "token", "permission", "read-only", "sandbox", "policy", "lease"),
    "mobile": ("mobile", "android", "responsive", "viewport", "touch", "ui", "cockpit"),
    "documentation": ("doc", "docs", "readme", "handover", "passation", "guide", "journal"),
    "evaluation": ("evaluate", "evaluation", "prospective", "oos", "look-ahead", "metric", "benchmark"),
    "market_data": ("kraken", "candle", "ohlcv", "snapshot", "stale", "timestamp", "telusd", "market"),
    "monitoring": ("monitor", "alert", "log", "incident", "watcher", "heartbeat", "status"),
    "release": ("release", "pr", "branch", "publish", "deploy", "diff", "rollback"),
}


def _definition_path(spec: team_config.AgentSpec) -> str:
    if spec.active:
        return f".agents/agents/{spec.name}.md"
    return f".agents/agents/reserve/{spec.name}.md"


def list_specialists() -> list[dict]:
    """Return the canonical inventory of all 12 TEL99 specialist profiles."""
    catalog = team_config.role_catalog()
    rows: list[dict] = []
    for role, spec in catalog.items():
        rows.append({
            "role": role,
            "name": spec.name,
            "active": bool(spec.active),
            "mobilization": "active_default" if spec.active else "on_demand_reserved",
            "definition_path": _definition_path(spec),
            "tools": list(spec.tools),
            "permission_mode": spec.permission_mode,
            "read_only": True,
            "description": spec.description,
        })
    return rows


def resolve_specialist(role_or_name: str) -> team_config.AgentSpec:
    """Resolve a TEL99 specialist by role key or canonical ``tel99-*`` name."""
    if not isinstance(role_or_name, str) or not role_or_name.strip():
        raise ValueError("specialist identifier is required")
    needle = role_or_name.strip().lower()
    catalog = team_config.role_catalog()
    if needle in catalog:
        return catalog[needle]
    for spec in catalog.values():
        if spec.name.lower() == needle:
            return spec
    raise ValueError(f"unknown TEL99 specialist: {role_or_name!r}")


def select_specialists(
    task: str,
    *,
    include_verifier: bool = True,
    max_specialists: int = 3,
) -> list[dict]:
    """Select a bounded subset of specialists matching a task description."""
    if not isinstance(task, str) or not task.strip():
        raise ValueError("task description must be non-empty")
    if not 1 <= max_specialists <= MAX_CONCURRENT_SPECIALISTS:
        raise ValueError(f"max_specialists must be within 1..{MAX_CONCURRENT_SPECIALISTS}")

    lower = task.lower()
    scores: list[tuple[int, int, str]] = []
    catalog = team_config.role_catalog()
    order = list(catalog.keys())

    for idx, role in enumerate(order):
        keywords = ROLE_KEYWORDS.get(role, ())
        hits = sum(1 for kw in keywords if re.search(rf"\b{re.escape(kw)}\b", lower))
        if hits > 0:
            scores.append((hits, -idx, role))

    scores.sort(reverse=True)
    selected_roles: list[str] = [role for _, _, role in scores[:max_specialists]]

    if not selected_roles:
        selected_roles = ["quant", "development", "quality"][:max_specialists]

    if include_verifier and "quality" not in selected_roles:
        if len(selected_roles) < max_specialists:
            selected_roles.append("quality")
        elif max_specialists > 1:
            selected_roles[-1] = "quality"

    all_rows = {row["role"]: row for row in list_specialists()}
    return [all_rows[role] for role in selected_roles]


def build_subagent_brief(
    role_or_name: str,
    *,
    task: str,
    mission_id: str,
    memory_lessons: list[str] | None = None,
    run_suffix: str | None = None,
) -> dict:
    """Build a bounded, read-only Antigravity subagent brief for one specialist."""
    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be non-empty")
    if len(task) > MAX_BRIEF_TASK_CHARS:
        raise ValueError(f"task exceeds {MAX_BRIEF_TASK_CHARS} characters")
    if not isinstance(mission_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", mission_id):
        raise ValueError("invalid mission_id")

    spec = resolve_specialist(role_or_name)
    suffix = run_suffix or team_config.time.strftime("%H%M%S")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", suffix):
        raise ValueError("invalid run_suffix")

    lessons = [
        str(item).strip() for item in (memory_lessons or [])
        if isinstance(item, str) and item.strip()
    ][:MAX_BRIEF_LESSONS]

    lesson_section = ""
    if lessons:
        lesson_section = "\n\nLeçons mémoire vérifiées (lecture seule) :\n- " + "\n- ".join(lessons)

    system_prompt = f"{spec.full_prompt()}\n\n{team_config.BUDGET_DISCIPLINE}"
    prompt = (
        f"Mission: {mission_id}\n"
        f"Spécialiste mobilisé: {spec.name} (rôle: {spec.role}, actif par défaut: {spec.active})\n"
        f"Tâche:\n{task.strip()}"
        f"{lesson_section}\n\n"
        "Rends un rapport factuel concis: constats vérifiés (fichiers/commandes/sorties), "
        "risques éventuels, et verdict (PROVEN / UNPROVEN / UNCERTAIN)."
    )
    return {
        "agent_id": f"{spec.name}-{suffix}",
        "role": spec.role,
        "name": spec.name,
        "active": bool(spec.active),
        "mobilization": "active_default" if spec.active else "on_demand_reserved",
        "definition_path": _definition_path(spec),
        "read_only": True,
        "max_iterations": team_config.DEFAULT_AGENT_MAX_ITERATIONS,
        "max_budget_usd": team_config.DEFAULT_AGENT_MAX_BUDGET_USD,
        "system_prompt": system_prompt,
        "prompt": prompt,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List all 12 TEL99 specialist roles")

    sel = sub.add_parser("select", help="Select up to N matching specialists for a task")
    sel.add_argument("--task", required=True)
    sel.add_argument("--max", type=int, default=3)
    sel.add_argument("--no-verifier", action="store_true")

    brief = sub.add_parser("brief", help="Generate a read-only subagent brief")
    brief.add_argument("--role", required=True)
    brief.add_argument("--task", required=True)
    brief.add_argument("--mission-id", required=True)
    brief.add_argument("--suffix", default=None)

    args = parser.parse_args(argv)
    if args.cmd == "list":
        rows = list_specialists()
        out = {
            "total": len(rows),
            "active_count": sum(1 for r in rows if r["active"]),
            "reserved_on_demand_count": sum(1 for r in rows if not r["active"]),
            "max_concurrent_specialists": MAX_CONCURRENT_SPECIALISTS,
            "specialists": rows,
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "select":
        rows = select_specialists(
            args.task,
            include_verifier=not args.no_verifier,
            max_specialists=args.max,
        )
        print(json.dumps({"selected": rows, "count": len(rows)}, indent=2, ensure_ascii=False))
        return 0
    payload = build_subagent_brief(
        args.role,
        task=args.task,
        mission_id=args.mission_id,
        run_suffix=args.suffix,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
