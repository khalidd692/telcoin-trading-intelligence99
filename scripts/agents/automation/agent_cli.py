"""TEL99 Direct 12-Agent Operator CLI (REUSE-FIRST, zero new supervisor, zero paid spend).

Lets the owner invoke any of the 12 TEL99 agents directly from one PowerShell command on any project:
- Reuses `specialist_dispatch` (12 official roles + dynamic routing).
- Reuses `mentor_curriculum.build_two_layer_generalist_context` (shared generalist core + target Skill + verified memory).
- Reuses `local_deterministic_tools.deterministic_security_gate` (100% deterministic security check).
- Reuses `ollama_native.OllamaNativeProvider` (concurrence=1 CAS lease) and optional free Groq mentors (`--hybrid`, $0.00).
- Supports `--team`, `--status`, `--task "..." [--role ...] [--hybrid] [--confidential] [--project ...] [--dry-run]`.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agents import specialist_dispatch
from scripts.agents.automation import (
    ide_coordination,
    local_deterministic_tools,
    mentor_curriculum,
    ollama_native,
    provider_router,
    run_full_local_chain,
    smart_repair,
)

LOCAL_MODEL = "gemma4:e4b-tel99-8k"
SKILLS_DIR = ROOT / ".agents" / "skills"
DEFAULT_MEM_DIR = Path.home() / "Desktop" / "TEL99_BENCHMARK_120_STATE" / "memory"
PASSPORTS_PATH = Path.home() / "Desktop" / "AI_RADAR" / "artifacts" / "agent_passports.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_team_overview() -> dict[str, Any]:
    """Return structured status of all 12 official TEL99 agents with verified passport levels."""
    specs = specialist_dispatch.list_specialists()
    passports_by_role: dict[str, dict[str, Any]] = {}
    if PASSPORTS_PATH.is_file():
        try:
            pdata = json.loads(PASSPORTS_PATH.read_text(encoding="utf-8"))
            for row in pdata.get("passports") or []:
                passports_by_role[row["identity"]["role"]] = row
        except (OSError, ValueError):
            pass

    agents: list[dict[str, Any]] = []
    for sp in specs:
        role = sp["role"]
        p = passports_by_role.get(role) or {}
        metrics = p.get("metrics") or {}
        skill_name = f"tel99-role-{role.replace('_', '-')}"
        agents.append({
            "role": role,
            "name": sp["name"],
            "specialty": sp.get("specialty", "code"),
            "proven_level": p.get("proven_level", 0),
            "proven_level_label": p.get("proven_level_label", "Niveau 0 — Non évalué"),
            "success_rate": metrics.get("success_rate"),
            "tasks_evaluated": metrics.get("tasks_evaluated", 0),
            "skill_ready": (SKILLS_DIR / skill_name / "SKILL.md").is_file(),
        })
    return {
        "schema_version": 1,
        "checked_at": _now_iso(),
        "total_agents": len(agents),
        "default_local_model": LOCAL_MODEL,
        "agents": agents,
    }


def resolve_role_for_task(task_text: str, explicit_role: str | None = None) -> tuple[str, str]:
    """Select the best specialist role among the 12 TEL99 agents (or honor explicit role)."""
    if explicit_role:
        spec = specialist_dispatch.resolve_specialist(explicit_role)
        return spec.role, spec.name
    picks = specialist_dispatch.select_specialists(task_text, include_verifier=False, max_specialists=1)
    if picks:
        return picks[0]["role"], picks[0]["name"]
    return "development", "tel99-dev"


def build_agent_request(
    *,
    task_text: str,
    role: str | None = None,
    domain: str | None = None,
    memory_dir: Path = DEFAULT_MEM_DIR,
    project_dir: Path | None = None,
) -> dict[str, Any]:
    """Assemble bounded 2-layer generalist + domain Skill + memory prompt for any of the 12 agents."""
    chosen_role, agent_name = resolve_role_for_task(task_text, role)
    target_domain = domain or chosen_role
    ctx = mentor_curriculum.build_two_layer_generalist_context(
        agent_role=chosen_role,
        target_domain=target_domain,
        skills_dir=SKILLS_DIR,
        memory_dir=memory_dir if memory_dir.is_dir() else None,
        objective=task_text,
    )
    sys_prompt = smart_repair.build_structured_reasoning_prompt(
        role=f"{agent_name} ({chosen_role} -> {target_domain})",
        objective=task_text,
        constraints=[
            "Strict security: zero eval/exec/os.system/shell=True/0.0.0.0/secret leaks.",
            "Validate types cleanly (check isinstance(x, bool) before int/float).",
            "Be concise, verifiable, and honest about limits.",
        ],
    )
    proj_note = f"\nTarget project workspace: {project_dir}" if project_dir else ""
    user_prompt = f"{task_text}{proj_note}\n\n{ctx['context_text']}"
    return {
        "agent_name": agent_name,
        "role": chosen_role,
        "target_domain": target_domain,
        "cross_domain": ctx["cross_domain_transfer"],
        "context_chars": ctx["context_chars"],
        "lessons_count": ctx["lessons_count"],
        "system_prompt": sys_prompt,
        "user_prompt": user_prompt,
    }


def run_agent_task(
    *,
    task_text: str,
    role: str | None = None,
    domain: str | None = None,
    hybrid: bool = False,
    confidential: bool = False,
    project_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run a task on any of the 12 TEL99 agents with deterministic security & zero-spend enforcement."""
    inj = local_deterministic_tools.detect_prompt_injection(task_text)
    if not inj["safe"]:
        return {
            "ok": False,
            "blocked_reason": "prompt_injection_detected",
            "matches": inj["matches"],
            "cloud_calls": 0,
        }

    req = build_agent_request(task_text=task_text, role=role, domain=domain, project_dir=project_dir)
    route_policy = local_deterministic_tools.check_cloud_escalation_policy(
        confidential=confidential,
        allow_cloud=hybrid,
        prompt_text=f"{req['system_prompt']}\n{req['user_prompt']}",
    )
    use_cloud = bool(hybrid and route_policy["allowed"])

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "agent_name": req["agent_name"],
            "role": req["role"],
            "target_domain": req["target_domain"],
            "cross_domain": req["cross_domain"],
            "planned_provider": "groq" if use_cloud else "ollama",
            "planned_model": "openai/gpt-oss-120b" if use_cloud else LOCAL_MODEL,
            "cloud_policy_reason": route_policy["reason"],
            "context_chars": req["context_chars"],
            "lessons_count": req["lessons_count"],
            "cloud_calls": 0,
        }

    t0 = time.monotonic()
    cloud_calls = 0
    if use_cloud:
        mentor = "qwen/qwen3.8-27b" if req["target_domain"] in ("development", "mobile", "market_data") else "openai/gpt-oss-120b"
        ad = provider_router.OpenAICompatFreeCloudAdapter(
            provider="groq",
            model=mentor,
            timeout=60,
            max_tokens=1400,
            confidential=False,
            fallback_ollama_model=LOCAL_MODEL,
        )
        reply = ad.complete(system=req["system_prompt"], prompt=req["user_prompt"])
        provider_used = str(ad.last_metadata.get("provider_used") or "groq")
        model_used = str(ad.last_metadata.get("model_used") or mentor)
        if provider_used == "groq":
            cloud_calls = 1
    else:
        eng = ide_coordination.probe_local_engines()
        resident = LOCAL_MODEL in ((eng.get("ollama") or {}).get("loaded_models") or [])
        budget = ollama_native.compute_adaptive_budget(
            LOCAL_MODEL,
            task_profile="module",
            estimated_lines=60,
            available_memory_mib=eng.get("available_memory_mib"),
            model_is_resident=resident,
        )
        provider = ollama_native.OllamaNativeProvider(
            model=LOCAL_MODEL,
            timeout=budget["timeout"],
            max_tokens=budget["max_tokens"],
            keep_alive="120s",
            task_profile=budget["effective_profile"],
            num_ctx=budget["num_ctx"],
            num_thread=budget["num_thread"],
        )
        reply = provider.complete(system=req["system_prompt"], prompt=req["user_prompt"])
        provider_used = "ollama"
        model_used = LOCAL_MODEL

    sec_check = local_deterministic_tools.detect_secret_leak(reply)
    return {
        "ok": bool(sec_check["safe"]),
        "agent_name": req["agent_name"],
        "role": req["role"],
        "target_domain": req["target_domain"],
        "cross_domain": req["cross_domain"],
        "provider_used": provider_used,
        "model_used": model_used,
        "cloud_calls": cloud_calls,
        "cost_usd": 0.0,
        "duration_seconds": round(time.monotonic() - t0, 2),
        "secret_leak_safe": sec_check["safe"],
        "response": reply if sec_check["safe"] else "[BLOCKED: secret pattern detected in output]",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--team", action="store_true", help="List all 12 TEL99 agents and verified levels")
    ap.add_argument("--status", action="store_true", help="Show consolidated system, chain, and AI Radar status")
    ap.add_argument("--task", type=str, default="", help="Execute a task with the best (or specified) TEL99 agent")
    ap.add_argument("--role", type=str, default=None, help="Explicit agent role (development, quant, security, ...)")
    ap.add_argument("--domain", type=str, default=None, help="Optional target domain for cross-domain generalist mode")
    ap.add_argument("--hybrid", action="store_true", help="Allow free Groq mentor escalation ($0.00, non-confidential only)")
    ap.add_argument("--confidential", action="store_true", help="Force 100% local Ollama execution (blocks cloud)")
    ap.add_argument("--project", type=Path, default=None, help="Optional target project directory")
    ap.add_argument("--dry-run", action="store_true", help="Preview routing, Skill/context selection, and security policy without calling LLM")
    args = ap.parse_args(argv)

    if args.team:
        print(json.dumps(get_team_overview(), indent=2, ensure_ascii=False))
        return 0
    if args.status:
        out = {
            "team": get_team_overview(),
            "results": run_full_local_chain.collect_results_summary(),
            "ai_radar_url": "http://127.0.0.1:8780/",
            "cockpit_url": "http://127.0.0.1:8765/",
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    if args.task.strip():
        res = run_agent_task(
            task_text=args.task.strip(),
            role=args.role,
            domain=args.domain,
            hybrid=args.hybrid,
            confidential=args.confidential,
            project_dir=args.project,
            dry_run=args.dry_run,
        )
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res.get("ok") else 2

    print(json.dumps(get_team_overview(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
