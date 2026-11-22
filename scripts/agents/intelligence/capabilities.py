"""Prepare a bounded, offline mission using the existing roles, router and bus schema."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from . import catalog, router
from ..team_config import role_catalog
from ..native.mission import MissionError, valid_mission_id, validate_project
from ..protocol.envelope import Actor, Envelope

SKILL_ROOT = Path(__file__).resolve().parents[3] / ".agents" / "skills"
PLAN_SKILL = "plan-verification"
SKILL_ROLES = frozenset({"coordination", "quality", "evaluation"})
TASK_KINDS = {"quant": "analysis", "development": "code", "quality": "review"}


def roles():
    return [{"role": role, "profile": spec.name, "active": spec.active,
             "permission_mode": spec.permission_mode, "tools": list(spec.tools),
             "skills": [PLAN_SKILL] if role in SKILL_ROLES else []}
            for role, spec in role_catalog().items()]


def _fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or (
            value.keys() - set(required) - set(optional)):
        raise ValueError("invalid contract fields")


def _positive(value, *, minimum=1, maximum=1_000_000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("invalid numeric budget or estimate")


def _plan_verification(contract):
    try:
        request = json.dumps(contract, ensure_ascii=True, allow_nan=False)
        if len(request) > 65536:
            raise ValueError("verification contract exceeds 64 KiB")
        result = subprocess.run(
            [sys.executable, "-IB", str(SKILL_ROOT / PLAN_SKILL / "scripts" / "plan_checks.py")],
            input=request, capture_output=True, encoding="utf-8", timeout=10, check=False,
        )
        report = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ValueError("verification planner unavailable or invalid") from exc
    if not isinstance(report, dict):
        raise ValueError("verification planner returned invalid output")
    if result.returncode == 2 and report.get("status") == "invalid":
        raise ValueError(report.get("reason", "invalid verification contract"))
    if (result.returncode, report.get("status")) not in {(0, "planned"), (0, "blocked")}:
        raise ValueError("verification planner returned inconsistent status")
    return report


def plan(contract):
    """Validate a JSON mission and return correlated handoffs without dispatching."""
    _fields(contract, ("project", "mission_id", "approved_models", "budget", "steps"),
            ("verification", "confidential"))
    try:
        validate_project(contract["project"])
    except MissionError as exc:
        raise ValueError("invalid project identifier") from exc
    if not isinstance(contract["mission_id"], str) or not valid_mission_id(contract["mission_id"]):
        raise ValueError("invalid mission id")
    confidential = contract.get("confidential", False)
    if type(confidential) is not bool:
        raise ValueError("confidential must be boolean")
    allowed = contract["approved_models"]
    if (not isinstance(allowed, list) or not allowed
            or any(not isinstance(mid, str) or catalog.by_id(mid) is None for mid in allowed)
            or len(set(allowed)) != len(allowed)):
        raise ValueError("approved_models must list known catalogue IDs")

    budget = contract["budget"]
    _fields(budget, ("max_calls", "quota_remaining", "reserve", "max_seconds", "max_context_tokens"))
    for field, value in budget.items():
        if field != "quota_remaining" or value is not None:
            _positive(value, minimum=0 if field in {"quota_remaining", "reserve"} else 1)

    specs = role_catalog()
    steps = contract["steps"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= len(specs):
        raise ValueError("invalid number of role steps")
    skill_steps = []
    sequence = []
    for step in steps:
        _fields(step, ("role", "estimated_tokens", "estimated_seconds"), ("skills",))
        role = step["role"]
        if not isinstance(role, str) or role not in specs:
            raise ValueError("unknown role")
        if role in sequence:
            raise ValueError("role must occur only once in a mission plan")
        sequence.append(role)
        _positive(step["estimated_tokens"])
        _positive(step["estimated_seconds"])
        skills = step.get("skills", [])
        if skills != []:
            if skills != [PLAN_SKILL] or role not in SKILL_ROLES:
                raise ValueError("skill not allowed for role")
            skill_steps.append(role)
    if len(skill_steps) > 1 or bool(skill_steps) != ("verification" in contract):
        raise ValueError("one role must own the verification skill and its contract")

    estimates = {"model_calls": len(steps), "seconds": sum(s["estimated_seconds"] for s in steps),
                 "context_tokens": sum(s["estimated_tokens"] for s in steps)}
    report = {"status": "BLOCKED", "provider_status": "PROVIDER_PENDING", "provider_calls": 0,
              "mode": "offline_plan", "estimates": estimates, "steps": [], "codes": []}
    codes = report["codes"]
    if budget["quota_remaining"] is None:
        codes.append("QUOTA_UNKNOWN")
    elif estimates["model_calls"] > budget["quota_remaining"] - budget["reserve"]:
        codes.append("QUOTA_RESERVE")
    for metric, cap, code in (
        ("model_calls", "max_calls", "CALL_BUDGET"),
        ("seconds", "max_seconds", "TIME_BUDGET"),
        ("context_tokens", "max_context_tokens", "CONTEXT_BUDGET"),
    ):
        if estimates[metric] > budget[cap]:
            codes.append(code)
    if codes:
        return report

    decisions = [router.route(
        router.TaskProfile(kind=TASK_KINDS.get(step["role"], "general"),
                           needs_tools=bool(specs[step["role"]].tools), confidential=confidential,
                           estimated_tokens=step["estimated_tokens"]),
        dry_run=True, approved_models=frozenset(allowed), allow_local=False,
    ) for step in steps]
    if not all(decision.ok for decision in decisions):
        report["routing"] = [d.to_dict() for d in decisions]
        codes.append("MODEL_UNAVAILABLE")
        return report
    if skill_steps:
        report["verification"] = _plan_verification(contract["verification"])
        if report["verification"]["status"] != "planned":
            codes.append("VERIFICATION_UNAVAILABLE")
            return report

    raw = json.dumps(contract, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    correlation = f"plan-{digest}"
    origin = Actor("unknown", "offline-planner")
    parent = None
    for index, (step, decision) in enumerate(zip(steps, decisions), 1):
        profile = specs[step["role"]]
        target = Actor("unknown", profile.name)
        message = Envelope.create(
            origin=origin, kind="sub_mission", mission_id=contract["mission_id"],
            target=target, correlation_id=correlation, parent_envelope_id=parent,
            envelope_id=f"{correlation}-{index}", title=step["role"],
            description="Read-only role preparation", read_only=True,
            budget={"max_iterations": 1, "max_budget_usd": 0,
                    "max_runtime_seconds": step["estimated_seconds"], "free_only": True},
            tags=["offline-plan", contract["project"]],
        )
        report["steps"].append({
            "role": step["role"], "role_active": profile.active, "skills": step.get("skills", []),
            "estimated_tokens": step["estimated_tokens"], "routing": decision.to_dict(),
            "handoff": message.to_dict(),
        })
        parent, origin = message.envelope_id, target
    report.update(status="PLANNED", project=contract["project"], contract_sha256=digest)
    return report
