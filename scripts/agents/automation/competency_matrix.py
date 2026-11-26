"""TEL99 12-Agent x 12-Domain Generalist & Multidisciplinary Competency Matrix.

Reuses existing TEL99 modules (zero new supervisor, bounded budgets, zero held-out contamination):
- `specialist_dispatch.list_specialists()` for the 12 official roles.
- `MemoryStore` + `context_engine.HybridMemoryIndex` for cross-agent verified knowledge sharing
  under the shared namespace `tel99-shared-core` (compact, bounded for local 8k context).
- `mentor_curriculum.build_two_layer_generalist_context()` so ANY agent can tackle ANY of the 12
  domains without context overload.
- `benchmark_unseen_v3` for strictly unseen primary + cross-domain evaluation (0 cloud in local eval).
- Never fabricates metrics: unevaluated cells stay `PENDING` until executed and verified.
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
    benchmark_unseen_v3,
    ide_coordination,
    improvement_cycle,
    local_deterministic_tools,
    mentor_curriculum,
    ollama_native,
    smart_repair,
)
from scripts.agents.intelligence.memory import COMMON_PROJECT, Entry, MemoryStore

WORK_DIR = Path.home() / "Desktop" / "TEL99_BENCHMARK_120_STATE"
ART_DIR = WORK_DIR / "artifacts"
MEM_DIR = WORK_DIR / "memory"
SKILLS_DIR = ROOT / ".agents" / "skills"
LOCAL_MODEL = "gemma4:e4b-tel99-8k"
ROLES_12 = benchmark_unseen_v3.ROLES_12


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_atomic(path: Path, payload: dict) -> None:
    local_deterministic_tools.write_json_atomic_locked(path, payload)


def sync_cross_agent_shared_knowledge(memory_dir: Path = MEM_DIR) -> dict[str, Any]:
    """Promote verified role procedures into native MemoryStore `common` pool so ALL 12 agents share proven knowledge."""
    ms = MemoryStore(memory_dir)
    promoted = 0
    raw_entries = (ms._load("tel99-bench") or {}).get("entries") or []
    src_entries = [Entry.from_dict(d) for d in raw_entries if d.get("verified") is True]
    for entry in src_entries:
        shared_id = f"shared-{entry.id}"
        if ms.get(COMMON_PROJECT, shared_id) is None:
            ms.record(
                Entry(
                    id=shared_id,
                    project=COMMON_PROJECT,
                    kind=entry.kind,
                    title=entry.title[:100],
                    body=entry.body[:220],
                    tags=tuple(sorted(set(entry.tags) | {"shared-core", "cross-agent"})),
                    source=entry.source,
                    author=entry.author,
                    verified=True,
                    verified_by=entry.verified_by or "benchmark_suite_100",
                    confidence=entry.confidence,
                ),
                actor="cross-agent-knowledge-sync",
            )
            promoted += 1
    total_shared = sum(
        1 for d in ((ms._load(COMMON_PROJECT) or {}).get("entries") or []) if d.get("verified") is True
    )
    return {
        "promoted_new": promoted,
        "total_shared_verified_entries": total_shared,
        "namespace": COMMON_PROJECT,
    }


def plan_cross_domain_rotations(*, rotations_per_agent: int = 2) -> list[dict[str, Any]]:
    """Deterministically assign each of the 12 agents to unseen tasks in OTHER domains (cross-training)."""
    if rotations_per_agent < 1 or rotations_per_agent > 11:
        raise ValueError("rotations_per_agent must be in [1, 11]")
    all_v3 = benchmark_unseen_v3.get_tasks()
    by_domain: dict[str, list[dict]] = {r: [t for t in all_v3 if t["role"] == r] for r in ROLES_12}

    assignments: list[dict[str, Any]] = []
    # Pick diverse offsets (e.g., +1, +4, +7) so every agent covers distinct non-native domains
    offsets = [1, 4, 7, 2, 5, 8, 3, 6, 9, 10, 11][:rotations_per_agent]
    for idx, agent_role in enumerate(ROLES_12):
        for k, off in enumerate(offsets):
            target_domain = ROLES_12[(idx + off) % len(ROLES_12)]
            # Pick a medium/hard task from target_domain (rotated by k to maximize task diversity)
            domain_tasks = by_domain[target_domain]
            task = domain_tasks[(k + 2) % len(domain_tasks)]
            assignments.append({
                "probe_id": f"xdom-{agent_role}-on-{target_domain}-{task['id']}",
                "agent_role": agent_role,
                "target_domain": target_domain,
                "task_id": task["id"],
                "difficulty": task["difficulty"],
                "critical_security": bool(task.get("critical_security")),
                "task": task,
            })
    return assignments


def build_competency_matrix(
    *,
    primary_results: list[dict[str, Any]] | None = None,
    cross_domain_results: list[dict[str, Any]] | None = None,
    hybrid_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble the honest 12-agent x 12-domain competency matrix strictly from verified runs."""
    specs = {s["role"]: s["name"] for s in specialist_dispatch.list_specialists()}
    # Initialize 12x12 empty cells (never fabricate! Unevaluated cells stay strictly PENDING.)
    cells: dict[str, dict[str, dict[str, Any]]] = {
        agent: {
            dom: {
                "passed": 0,
                "total": 0,
                "rate": None,
                "status": "PENDING",
                "proven_level": 0,
                "cloud_calls": 0,
                "local_without_cloud_ok": None,
                "mission_ids": [],
                "errors": [],
                "skills_used": [],
                "total_seconds": 0.0,
            }
            for dom in ROLES_12
        }
        for agent in ROLES_12
    }

    def _accumulate(cell: dict[str, Any], row: dict[str, Any], target_domain: str) -> None:
        cell["total"] += 1
        if row.get("ok"):
            cell["passed"] += 1
        elif row.get("error"):
            err_s = str(row["error"])[:180]
            if err_s not in cell["errors"] and len(cell["errors"]) < 5:
                cell["errors"].append(err_s)
        cell["cloud_calls"] += int(row.get("cloud_calls") or 0)
        cell["total_seconds"] = round(cell["total_seconds"] + float(row.get("seconds") or 0.0), 2)
        mid = row.get("task_id") or row.get("id")
        if mid and mid not in cell["mission_ids"]:
            cell["mission_ids"].append(mid)
        sk = f"tel99-role-{target_domain.replace('_', '-')}"
        if sk not in cell["skills_used"]:
            cell["skills_used"].append(sk)

    # Populate diagonal (primary specialty, 100% local)
    for row in (primary_results or []):
        role = row.get("role")
        if role in cells:
            _accumulate(cells[role][role], row, role)

    # Populate off-diagonal (cross-domain generalist, 100% local)
    for row in (cross_domain_results or []):
        ag = row.get("agent_role")
        dom = row.get("target_domain")
        if ag in cells and dom in cells[ag]:
            _accumulate(cells[ag][dom], row, dom)

    # Finalize cell rates & per-agent aggregates
    agent_summaries: dict[str, dict[str, Any]] = {}
    cells_evaluated = 0
    cross_cells_evaluated = 0
    for ag in ROLES_12:
        p_pass = p_tot = x_pass = x_tot = 0
        eval_domains = 0
        gaps: list[str] = []
        for dom in ROLES_12:
            c = cells[ag][dom]
            if c["total"] > 0:
                cells_evaluated += 1
                if ag != dom:
                    cross_cells_evaluated += 1
                c["rate"] = round(c["passed"] / c["total"], 4)
                c["status"] = "PROVEN" if c["rate"] >= 0.80 else "NEEDS_TRAINING"
                c["local_without_cloud_ok"] = bool(c["cloud_calls"] == 0 and c["rate"] >= 0.80)
                if c["rate"] >= 0.90 and c["total"] >= 3:
                    c["proven_level"] = 3
                elif c["rate"] >= 0.80:
                    c["proven_level"] = 2
                elif c["passed"] > 0:
                    c["proven_level"] = 1
                else:
                    c["proven_level"] = 0
                eval_domains += 1
                if c["rate"] < 0.85:
                    gaps.append(dom)
                if ag == dom:
                    p_pass += c["passed"]
                    p_tot += c["total"]
                else:
                    x_pass += c["passed"]
                    x_tot += c["total"]
        agent_summaries[ag] = {
            "agent_name": specs.get(ag, f"tel99-{ag}"),
            "primary_passed": p_pass,
            "primary_total": p_tot,
            "primary_rate": round(p_pass / p_tot, 4) if p_tot else None,
            "cross_domain_passed": x_pass,
            "cross_domain_total": x_tot,
            "cross_domain_rate": round(x_pass / x_tot, 4) if x_tot else None,
            "overall_local_rate": round((p_pass + x_pass) / (p_tot + x_tot), 4) if (p_tot + x_tot) else None,
            "domains_evaluated": eval_domains,
            "domains_total": 12,
            "gap_domains": sorted(gaps),
        }

    # Global aggregates
    all_p_pass = sum(s["primary_passed"] for s in agent_summaries.values())
    all_p_tot = sum(s["primary_total"] for s in agent_summaries.values())
    all_x_pass = sum(s["cross_domain_passed"] for s in agent_summaries.values())
    all_x_tot = sum(s["cross_domain_total"] for s in agent_summaries.values())

    hyb_pass = sum(1 for r in (hybrid_results or []) if r.get("ok"))
    hyb_tot = len(hybrid_results or [])

    return {
        "schema_version": 1,
        "generated_at": _now_iso(),
        "dimensions": "12_agents_x_12_domains",
        "global_metrics": {
            "local_primary_expertise_rate": round(all_p_pass / all_p_tot, 4) if all_p_tot else None,
            "local_primary_passed": f"{all_p_pass}/{all_p_tot}",
            "local_cross_domain_generalist_rate": round(all_x_pass / all_x_tot, 4) if all_x_tot else None,
            "local_cross_domain_passed": f"{all_x_pass}/{all_x_tot}",
            "local_combined_generalist_rate": round((all_p_pass + all_x_pass) / (all_p_tot + all_x_tot), 4) if (all_p_tot + all_x_tot) else None,
            "hybrid_rate": round(hyb_pass / hyb_tot, 4) if hyb_tot else None,
            "hybrid_passed": f"{hyb_pass}/{hyb_tot}",
            "cloud_calls_in_local_matrix": sum(
                cells[ag][dom]["cloud_calls"] for ag in ROLES_12 for dom in ROLES_12
            ),
            "cells_evaluated": cells_evaluated,
            "cells_total": 144,
            "coverage_rate": round(cells_evaluated / 144.0, 4),
            "cross_domain_cells_evaluated": cross_cells_evaluated,
            "cross_domain_cells_total": 132,
            "full_144_covered": cells_evaluated == 144,
        },
        "agents": agent_summaries,
        "matrix_12x12": cells,
    }


def _reconcile_v3_report() -> dict[str, Any]:
    """Reconcile unseen_v3_report.json from separate phase checkpoints before reading."""
    try:
        from scripts.agents.automation import run_unseen_v3_eval
        return run_unseen_v3_eval.rebuild_unseen_v3_report_from_checkpoints(art_dir=ART_DIR)
    except Exception:
        v3_path = ART_DIR / "unseen_v3_report.json"
        return json.loads(v3_path.read_text(encoding="utf-8")) if v3_path.is_file() else {}


def run_local_cross_domain_eval(
    *,
    rotations_per_agent: int = 2,
    batch_size: int = 0,
    ckpt_path: Path = ART_DIR / "ckpt_v3_cross_domain_local.json",
) -> dict[str, Any]:
    """Execute bounded, resumable 100% LOCAL (0 cloud) cross-domain generalist probes for all 12 agents."""
    sync_info = sync_cross_agent_shared_knowledge(MEM_DIR)
    assignments = plan_cross_domain_rotations(rotations_per_agent=rotations_per_agent)

    done: dict[str, dict] = {}
    if ckpt_path.is_file():
        try:
            for r in json.loads(ckpt_path.read_text(encoding="utf-8")).get("results") or []:
                done[r["probe_id"]] = r
        except (OSError, ValueError):
            pass

    results: list[dict] = []
    executed_this_batch = 0
    t_all = time.monotonic()

    for item in assignments:
        pid = item["probe_id"]
        if pid in done:
            results.append(done[pid])
            continue
        if batch_size > 0 and executed_this_batch >= batch_size:
            continue

        task = item["task"]
        ctx = mentor_curriculum.build_two_layer_generalist_context(
            agent_role=item["agent_role"],
            target_domain=item["target_domain"],
            skills_dir=SKILLS_DIR,
            memory_dir=MEM_DIR,
            objective=task["objective"],
        )

        attempts_log: list[dict] = []
        prior_hashes: list[str] = []
        last_out = ""
        prev_out = ""
        last_ver: dict[str, Any] = {"ok": False, "error": "not run", "passed": [], "failed": []}

        for att in range(1, 4):
            eng = ide_coordination.probe_local_engines()
            resident = LOCAL_MODEL in ((eng.get("ollama") or {}).get("loaded_models") or [])
            budget = ollama_native.compute_adaptive_budget(
                LOCAL_MODEL,
                task_profile="module",
                estimated_lines=55,
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
            t0 = time.monotonic()
            if att == 1:
                sys_p = smart_repair.build_structured_reasoning_prompt(
                    role=f"tel99-{item['agent_role']} (cross-domain -> {item['target_domain']})",
                    objective=task["objective"],
                    constraints=[
                        "Python 3.12 stdlib only (or exact JSON object ONLY if JSON requested).",
                        "No eval/exec/__import__/shell=True.",
                        improvement_cycle._role_instruction_hint(item["target_domain"]),
                        "ZERO docstrings, ZERO comments, ZERO if __name__=='__main__' example blocks (<= 30 lines).",
                    ],
                )
                usr_p = f"{task['objective']}\n\n{ctx['context_text']}"
            else:
                sys_p = (
                    "Return ONLY the complete corrected Python 3.12 stdlib code (<= 30 lines, ZERO docstrings, "
                    "ZERO comments, ZERO example blocks) or exact JSON object."
                )
                diff = smart_repair.compute_bounded_diff(prev_out, last_out) if prev_out else ""
                usr_p = (
                    f"Original specification:\n{task['objective']}\n\n"
                    + smart_repair.build_smart_repair_prompt(
                        previous_code=last_out,
                        exact_error=str(last_ver.get("error") or ""),
                        passed_checks=last_ver.get("passed", []),
                        failed_checks=last_ver.get("failed", []),
                        contract_constraints=[
                            improvement_cycle._role_instruction_hint(item["target_domain"]),
                            "ZERO docstrings, ZERO comments, ZERO example blocks (<= 30 lines).",
                        ],
                        prior_attempts=attempts_log,
                        memory_lessons=[],
                        previous_diff=diff,
                    )
                )
            try:
                rf = "json" if task.get("kind") == "json" else None
                raw = provider.complete(system=sys_p, prompt=usr_p, response_format=rf)
                if task.get("kind") == "json":
                    raw = local_deterministic_tools.extract_clean_json(raw)
                else:
                    raw = local_deterministic_tools.strip_trailing_example_blocks(ollama_native.extract_code_block(raw))
                sec_pre = local_deterministic_tools.deterministic_security_gate(raw, kind=task.get("kind", "python"))
                if not sec_pre["ok"]:
                    ver = {"ok": False, "error": "; ".join(sec_pre["issues"]), "passed": [], "failed": ["security_precheck"]}
                else:
                    ver = benchmark_unseen_v3.verify_unseen_output(task, sec_pre["cleaned"])
            except Exception as exc:
                raw = ""
                ver = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:160]}", "passed": [], "failed": ["infra"]}

            fp = smart_repair.code_fingerprint(raw)
            repeated = smart_repair.detect_repeated_attempt(raw, prior_hashes)
            prior_hashes.append(fp)
            if repeated and not ver["ok"]:
                ver["error"] = f"REPEATED_ATTEMPT: {ver.get('error')}"
            attempts_log.append({
                "attempt": att,
                "seconds": round(time.monotonic() - t0, 2),
                "ok": bool(ver["ok"]),
                "repeated": repeated,
                "code_sha256": fp,
                "error": ver.get("error"),
            })
            prev_out = last_out
            last_out = raw
            last_ver = ver
            if ver["ok"]:
                break

        row = {
            "probe_id": pid,
            "agent_role": item["agent_role"],
            "target_domain": item["target_domain"],
            "task_id": item["task_id"],
            "difficulty": item["difficulty"],
            "critical_security": item["critical_security"],
            "ok": bool(last_ver["ok"]),
            "attempts": len(attempts_log),
            "repaired": bool(last_ver["ok"] and len(attempts_log) > 1),
            "cloud_calls": 0,
            "context_chars": ctx["context_chars"],
            "seconds": round(sum(a["seconds"] for a in attempts_log), 2),
            "error": last_ver.get("error"),
        }
        done[pid] = row
        results.append(row)
        executed_this_batch += 1
        _write_atomic(ckpt_path, {"completed": len(done), "total": len(assignments), "results": list(done.values())})
        print(json.dumps({"xdom_local": f"{len(done)}/{len(assignments)}", "agent": row["agent_role"], "domain": row["target_domain"], "ok": row["ok"], "att": row["attempts"], "s": row["seconds"], "err": row["error"]}), flush=True)

    if executed_this_batch > 0:
        ide_coordination.unload_ollama_models([LOCAL_MODEL])

    # Reconcile V3 checkpoints before building complete 12x12 matrix
    v3 = _reconcile_v3_report()
    all_x_rows = list(done.values())
    matrix = build_competency_matrix(
        primary_results=v3.get("details_local_after") or [],
        cross_domain_results=all_x_rows,
        hybrid_results=v3.get("details_hybrid_after") or [],
    )
    matrix["shared_knowledge_sync"] = sync_info
    matrix["cross_domain_duration_seconds"] = round(time.monotonic() - t_all, 2)
    matrix["batch_executed_now"] = executed_this_batch
    matrix["rotations_requested"] = rotations_per_agent
    matrix["cross_domain_results"] = all_x_rows
    _write_atomic(ART_DIR / "competency_matrix_12x12.json", matrix)
    print("COMPETENCY_MATRIX_12x12_SUMMARY:", json.dumps(matrix["global_metrics"], indent=2), flush=True)
    return matrix


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rotations", type=int, default=2, help="Cross-domain probes per agent (2=24 probes, 11=full 132 off-diagonal)")
    ap.add_argument("--batch-size", type=int, default=0, help="Max new probes to run in this invocation (0=all remaining)")
    ap.add_argument("--sync-only", action="store_true", help="Only sync cross-agent shared knowledge & rebuild matrix from existing reports")
    args = ap.parse_args(argv)
    if args.sync_only:
        sync_info = sync_cross_agent_shared_knowledge(MEM_DIR)
        v3 = _reconcile_v3_report()
        x_path = ART_DIR / "ckpt_v3_cross_domain_local.json"
        x_rows = (json.loads(x_path.read_text(encoding="utf-8")).get("results") or []) if x_path.is_file() else []
        mat = build_competency_matrix(
            primary_results=v3.get("details_local_after") or [],
            cross_domain_results=x_rows,
            hybrid_results=v3.get("details_hybrid_after") or [],
        )
        mat["shared_knowledge_sync"] = sync_info
        _write_atomic(ART_DIR / "competency_matrix_12x12.json", mat)
        print(json.dumps({"sync": sync_info, "global_metrics": mat["global_metrics"]}, indent=2))
        return 0
    run_local_cross_domain_eval(rotations_per_agent=args.rotations, batch_size=args.batch_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
