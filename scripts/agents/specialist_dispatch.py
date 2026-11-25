"""On-demand mobilization and 10-criteria audit of all 12 TEL99 specialist roles.

Keeps ``team_config.ACTIVE_AGENTS`` (3) and ``.agents/agents/reserve/`` (9)
untouched so SDK auto-discovery and CI checks remain strictly intact, while
allowing Antigravity IDE / CLI orchestrators to select, audit, and brief up to
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

ROLE_METADATA: dict[str, dict] = {
    "development": {
        "skills": ("tel99-autonomous-campaign",),
        "preferred_tier": "executor",
        "acceptance_criteria": "Propose minimal Python/JS changes with paths, logs, and hypothesis/fact separation.",
        "evidence_contract": "File paths, line ranges, raw command output, and SHA-256 or test verdict.",
    },
    "quant": {
        "skills": ("tel99-autonomous-campaign", "plan-verification"),
        "preferred_tier": "orchestrator",
        "acceptance_criteria": "Distinguish early alert from confirmed buy; report freshness, temporal leakage, fees, and costs.",
        "evidence_contract": "Timestamps, dataset bounds, signal/alert separation, and reproducible checks.",
    },
    "quality": {
        "skills": ("plan-verification", "tel99-autonomous-campaign"),
        "preferred_tier": "executor",
        "acceptance_criteria": "Independently reproduce claims and classify each item PROVEN / UNPROVEN / UNCERTAIN.",
        "evidence_contract": "Independent command execution, raw exit codes, and Docker/unit check results.",
    },
    "coordination": {
        "skills": ("plan-verification", "tel99-autonomous-campaign"),
        "preferred_tier": "orchestrator",
        "acceptance_criteria": "Split mission into independent tasks with explicit DAG order and CAS lease boundaries.",
        "evidence_contract": "Dependency graph, lease IDs, handoff records, and completion criteria.",
    },
    "cloud": {
        "skills": ("tel99-autonomous-campaign",),
        "preferred_tier": "orchestrator",
        "acceptance_criteria": "Audit GitHub Actions, schedules, and publication; require non-PC run proof before autonomy claims.",
        "evidence_contract": "Workflow run IDs, trigger definitions, branch state, and HTTP/JSON probes.",
    },
    "security": {
        "skills": ("plan-verification", "tel99-autonomous-campaign"),
        "preferred_tier": "orchestrator",
        "acceptance_criteria": "Verify read-only contract, scrubbed env, CAS leases, branch protection, and guard hook.",
        "evidence_contract": "Guard exit code 2 proofs, scrubbed env keys, and lease conflict traces.",
    },
    "mobile": {
        "skills": ("tel99-autonomous-campaign",),
        "preferred_tier": "executor",
        "acceptance_criteria": "Audit Android/mobile cockpit and terminal usability without redesigning Smart View.",
        "evidence_contract": "Viewport/DOM checks, HTTP status, and concrete usability findings.",
    },
    "documentation": {
        "skills": ("tel99-autonomous-campaign",),
        "preferred_tier": "executor",
        "acceptance_criteria": "Maintain traceability, handovers, and precedence while preserving historical archives intact.",
        "evidence_contract": "Commit SHAs, PR links, archive preservation checks, and exact file links.",
    },
    "evaluation": {
        "skills": ("plan-verification",),
        "preferred_tier": "orchestrator",
        "acceptance_criteria": "Measure prospective metrics and detect look-ahead bias or temporal leakage.",
        "evidence_contract": "Out-of-sample metrics, timestamps, and statistical limitation notes.",
    },
    "market_data": {
        "skills": ("tel99-autonomous-campaign",),
        "preferred_tier": "executor",
        "acceptance_criteria": "Verify Kraken data freshness and candle integrity; fail closed on stale snapshots.",
        "evidence_contract": "Snapshot timestamps, age calculation, and fail-closed status checks.",
    },
    "monitoring": {
        "skills": ("tel99-autonomous-campaign",),
        "preferred_tier": "executor",
        "acceptance_criteria": "Audit logs, alerts, and delivery status without inferring delivery from UI display alone.",
        "evidence_contract": "Log excerpts, watcher status, and outbox/delivery receipts.",
    },
    "release": {
        "skills": ("plan-verification", "tel99-autonomous-campaign"),
        "preferred_tier": "orchestrator",
        "acceptance_criteria": "Compare before/after diffs and publication gates; never merge into main by default.",
        "evidence_contract": "Diff stats, remote SHA verification, draft PR URLs, and CI status.",
    },
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
        meta = ROLE_METADATA.get(role, {})
        rows.append({
            "role": role,
            "name": spec.name,
            "active": bool(spec.active),
            "mobilization": "active_default" if spec.active else "on_demand_reserved",
            "definition_path": _definition_path(spec),
            "tools": list(spec.tools),
            "permission_mode": spec.permission_mode,
            "read_only": True,
            "skills": list(meta.get("skills", ())),
            "preferred_tier": meta.get("preferred_tier", "executor"),
            "acceptance_criteria": meta.get("acceptance_criteria", ""),
            "evidence_contract": meta.get("evidence_contract", ""),
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
    meta = ROLE_METADATA.get(spec.role, {})
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
    acceptance = meta.get("acceptance_criteria", "")
    evidence = meta.get("evidence_contract", "")
    prompt = (
        f"Mission: {mission_id}\n"
        f"Spécialiste mobilisé: {spec.name} (rôle: {spec.role}, actif par défaut: {spec.active})\n"
        f"Critère d'acceptation: {acceptance}\n"
        f"Preuves attendues: {evidence}\n"
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
        "skills": list(meta.get("skills", ())),
        "preferred_tier": meta.get("preferred_tier", "executor"),
        "acceptance_criteria": acceptance,
        "evidence_contract": evidence,
        "max_iterations": team_config.DEFAULT_AGENT_MAX_ITERATIONS,
        "max_budget_usd": team_config.DEFAULT_AGENT_MAX_BUDGET_USD,
        "system_prompt": system_prompt,
        "prompt": prompt,
    }


def audit_all_specialists() -> dict:
    """Audit all 12 specialists against TEL99 readiness, safety, memory, and evidence criteria."""
    rows = list_specialists()
    results: list[dict] = []
    for row in rows:
        role = row["role"]
        def_path = ROOT / row["definition_path"]
        md_text = def_path.read_text(encoding="utf-8") if def_path.is_file() else ""
        brief = build_subagent_brief(
            role,
            task="Verify specialist readiness.",
            mission_id="audit-12-roles",
            memory_lessons=["[procedure|verified] Audit memory recall check."],
            run_suffix="audit01",
        )
        checks = {
            "role_defined": bool(role and row["name"].startswith("tel99-")),
            "skills_assigned": bool(row["skills"]),
            "instructions_and_file": def_path.is_file() and "guard/guard.py" in md_text,
            "tools_terminal_only": row["tools"] == ["terminal"],
            "permissions_confirm_risky": row["permission_mode"] == "confirm_risky" and "LECTURE SEULE" in brief["system_prompt"],
            "receives_mission": bool(brief["agent_id"] and "Mission: audit-12-roles" in brief["prompt"]),
            "communicates_verdict": "PROVEN / UNPROVEN / UNCERTAIN" in brief["prompt"],
            "uses_memory_lessons": "Audit memory recall check." in brief["prompt"],
            "acceptance_criteria_bound": bool(row["acceptance_criteria"]) and row["acceptance_criteria"] in brief["prompt"],
            "evidence_contract_bound": bool(row["evidence_contract"]) and row["evidence_contract"] in brief["prompt"],
        }
        results.append({
            "role": role,
            "name": row["name"],
            "active": row["active"],
            "mobilization": row["mobilization"],
            "ok": all(checks.values()),
            "checks": checks,
        })
    return {
        "schema_version": 1,
        "total": len(results),
        "all_ok": len(results) == 12 and all(item["ok"] for item in results),
        "active_count": sum(1 for item in results if item["active"]),
        "reserved_count": sum(1 for item in results if not item["active"]),
        "specialists": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List all 12 TEL99 specialist roles")
    sub.add_parser("audit", help="Audit all 12 specialist roles across 10 readiness criteria")

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
    if args.cmd == "audit":
        report = audit_all_specialists()
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["all_ok"] else 2
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
