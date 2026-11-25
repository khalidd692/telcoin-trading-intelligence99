"""Live Groq Free Hybrid Expert Shootout (dev), Mentor Lesson Mining (train),
and Frozen 72-Mission Held-Out Evaluation (Target >= 65/72 = 90.28%, stretch 95%).

Uses ONLY existing TEL99 modules (provider_router, benchmark_suite_100, context_engine,
metacognition, smart_repair, evolution_lab). Zero local RAM/CPU contention (safe to run
while local Ollama/llama-server campaigns finish). Strict zero-spend ($0.00), non-confidential
synthetic benchmark tasks only, secret-scrubbed, with dynamic TPM pacing and atomic checkpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agents.automation import (
    benchmark_suite_100,
    context_engine,
    evolution_lab,
    improvement_cycle,
    local_deterministic_tools,
    mentor_curriculum,
    metacognition,
    provider_router,
    smart_repair,
)
from scripts.agents.intelligence import improvement
from scripts.agents.intelligence.memory import Entry, MemoryStore

WORK_DIR = Path.home() / "Desktop" / "TEL99_BENCHMARK_120_STATE"
ART_DIR = WORK_DIR / "artifacts"
MEM_DIR = WORK_DIR / "memory"
SKILLS_DIR = ROOT / ".agents" / "skills"

GROQ_MODELS = (
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _call_groq_safe(
    model: str,
    *,
    system: str,
    prompt: str,
    response_format: str | None = None,
    max_tokens: int = 1536,
    max_429_retries: int = 4,
) -> tuple[str, dict]:
    """Call Groq free adapter with gentle 429 retry/pacing (never touches paid APIs or local Ollama during parallel run)."""
    ledger = provider_router.CloudBudgetLedger()
    ad = provider_router.OpenAICompatFreeCloudAdapter(
        provider="groq",
        model=model,
        timeout=60,
        max_tokens=max_tokens,
        confidential=False,
        fallback_ollama_model=None,
        budget_ledger=ledger,
    )
    for retry in range(max_429_retries + 1):
        st = ledger.status("groq")
        if st["cooldown_remaining_s"] > 0:
            time.sleep(min(90.0, st["cooldown_remaining_s"] + 2.0))
        else:
            rem_tok = int(((st.get("last_headers") or {}).get("x-ratelimit-remaining-tokens")) or 8000)
            if rem_tok < 3000:
                time.sleep(12.0)
        try:
            out = ad.complete(system=system, prompt=prompt, response_format=response_format)
            return out, dict(ad.last_metadata)
        except Exception as exc:
            msg = str(exc)
            if "429" in msg or "cooldown" in msg.lower():
                if retry < max_429_retries:
                    st2 = ledger.status("groq")
                    time.sleep(min(90.0, max(15.0, st2["cooldown_remaining_s"] + 2.0)))
                    continue
            raise
    raise RuntimeError("Groq call failed after 429 retries")


def _run_single_model_dev(model: str, tasks: list[dict], ckpt_path: Path) -> dict:
    done: dict[str, dict] = {}
    if ckpt_path.is_file():
        try:
            prev = json.loads(ckpt_path.read_text(encoding="utf-8"))
            for r in prev.get("results") or []:
                done[r["id"]] = r
        except (OSError, ValueError):
            pass

    results = []
    t_all = time.monotonic()
    for task in tasks:
        if task["id"] in done:
            results.append(done[task["id"]])
            continue
        sys_p = smart_repair.build_structured_reasoning_prompt(
            role=f"tel99-{task['role']}",
            objective=task["objective"],
            constraints=[
                "Python 3.12 stdlib only (or exact JSON object if JSON requested).",
                "No eval/exec/__import__/shell=True.",
                improvement_cycle._role_instruction_hint(task["role"]),
                "Output ONLY code block or JSON object with zero prose.",
            ],
        )
        t0 = time.monotonic()
        try:
            rf = "json" if task.get("kind") == "json" else None
            raw, meta = _call_groq_safe(model, system=sys_p, prompt=task["objective"], response_format=rf)
            ver = benchmark_suite_100.verify_task_output(task, raw)
        except Exception as exc:
            meta = {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}
            ver = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
        dt = round(time.monotonic() - t0, 2)
        row = {
            "id": task["id"],
            "role": task["role"],
            "difficulty": task["difficulty"],
            "model": model,
            "ok": bool(ver["ok"]),
            "error": ver.get("error"),
            "seconds": dt,
            "prompt_tokens": int(meta.get("prompt_tokens") or 0),
            "completion_tokens": int(meta.get("completion_tokens") or 0),
            "cost_usd": 0.0,
        }
        results.append(row)
        print(json.dumps({"phase": "dev_shootout", "model": model, "id": task["id"], "ok": row["ok"], "s": dt, "err": row["error"]}), flush=True)
        _write_atomic(ckpt_path, {"model": model, "results": results})

    passed = sum(1 for r in results if r["ok"])
    by_role = {}
    for role in benchmark_suite_100.ROLES_12:
        rr = [r for r in results if r["role"] == role]
        if rr:
            by_role[role] = round(sum(1 for r in rr if r["ok"]) / len(rr), 4)
    return {
        "model": model,
        "passed": passed,
        "total": len(results),
        "success_rate": round(passed / max(1, len(results)), 4),
        "avg_seconds": round(sum(r["seconds"] for r in results) / max(1, len(results)), 2),
        "total_tokens": sum(r["prompt_tokens"] + r["completion_tokens"] for r in results),
        "cost_usd": 0.0,
        "by_role": by_role,
        "duration_seconds": round(time.monotonic() - t_all, 2),
        "results": results,
    }


def _mine_train_mentor_lessons(best_model: str, tasks: list[dict], ckpt_path: Path) -> dict:
    """Use Groq mentor on TRAIN split ONLY to verify solutions and store verified procedural lessons in MemoryStore."""
    done: dict[str, dict] = {}
    if ckpt_path.is_file():
        try:
            prev = json.loads(ckpt_path.read_text(encoding="utf-8"))
            for r in prev.get("results") or []:
                done[r["id"]] = r
        except (OSError, ValueError):
            pass

    ms = MemoryStore(MEM_DIR)
    traj = metacognition.TrajectoryRecorder(ART_DIR)
    results = []
    lessons_stored = 0

    for task in tasks:
        if task["id"] in done:
            results.append(done[task["id"]])
            continue
        sys_p = smart_repair.build_structured_reasoning_prompt(
            role=f"tel99-{task['role']}",
            objective=task["objective"],
            constraints=[
                "Python 3.12 stdlib only (or exact JSON).",
                improvement_cycle._role_instruction_hint(task["role"]),
                "Output ONLY clean concise code or JSON.",
            ],
        )
        t0 = time.monotonic()
        try:
            rf = "json" if task.get("kind") == "json" else None
            raw, meta = _call_groq_safe(best_model, system=sys_p, prompt=task["objective"], response_format=rf)
            ver = benchmark_suite_100.verify_task_output(task, raw)
        except Exception as exc:
            raw, meta = "", {}
            ver = {"ok": False, "error": str(exc)[:160]}
        dt = round(time.monotonic() - t0, 2)
        if ver["ok"]:
            lid = f"mentor-{task['role']}-{task['id']}"
            if ms.get("tel99-bench", lid) is None:
                ms.record(
                    Entry(
                        id=lid,
                        project="tel99-bench",
                        kind="procedure",
                        title=f"Verified {task['role']} pattern ({task['id']})",
                        body=f"{improvement_cycle._role_instruction_hint(task['role'])} Verified on {task['id']} via independent AST+functional tests.",
                        tags=(task["role"], task["id"], "groq-mentor-verified", "train-only"),
                        source=f"groq-mentor/{best_model}/{task['id']}",
                        author=f"tel99-{task['role']}",
                        verified=True,
                        verified_by="benchmark_suite_100",
                        confidence=0.98,
                    ),
                    actor="groq-mentor-learning",
                )
                lessons_stored += 1
            traj.record(
                project="tel99-bench", mission_id=f"train-mentor-{task['id']}",
                objective=task["objective"][:400], model=best_model, role=f"tel99-{task['role']}",
                tools_used=[{"tool": "groq_free", "model": best_model}],
                decisions=["split=train", "verified_mentor_lesson"],
                errors=[], repairs=[], tests=[{"ok": True}], artifacts=[],
                verdict="SUCCESS", duration_seconds=dt, cost_usd=0.0,
            )
        row = {"id": task["id"], "role": task["role"], "ok": bool(ver["ok"]), "seconds": dt, "error": ver.get("error")}
        results.append(row)
        _write_atomic(ckpt_path, {"model": best_model, "results": results})
        print(json.dumps({"phase": "train_mentor", "id": task["id"], "ok": row["ok"], "s": dt}), flush=True)

    return {
        "model": best_model,
        "passed": sum(1 for r in results if r["ok"]),
        "total": len(results),
        "lessons_stored": lessons_stored,
    }


def _evaluate_frozen_held_out_hybrid(
    role_routing: dict[str, str],
    expert_model: str,
    secondary_model: str,
    tasks: list[dict],
    ckpt_path: Path,
) -> dict:
    """Evaluate all 72 completely unseen held_out_final tasks with full Harness + RAG + Skills + Smart Repair + Multi-Model Escalation."""
    done: dict[str, dict] = {}
    if ckpt_path.is_file():
        try:
            prev = json.loads(ckpt_path.read_text(encoding="utf-8"))
            for r in prev.get("results") or []:
                done[r["id"]] = r
        except (OSError, ValueError):
            pass

    traj = metacognition.TrajectoryRecorder(ART_DIR)
    flib = metacognition.FailureLibrary(ART_DIR, memory_root=None)  # NEVER contaminate memory from held_out!
    results = []
    t_all = time.monotonic()

    for task in tasks:
        tid = task["id"]
        if tid in done:
            results.append(done[tid])
            continue

        # Retrieve verified train-only lessons via SQLite FTS5 Hybrid RAG + specialized role Skill
        hits = context_engine.HybridMemoryIndex(MEM_DIR).search(
            "tel99-bench", f"{task['role']} {task['objective']}", limit=3, verified_only=True, role=task["role"]
        )
        mem_lessons = [f"{h['title']}: {h['body']}" for h in hits]
        role_skill_card = mentor_curriculum.load_role_skill_card(task["role"], skills_dir=SKILLS_DIR, max_chars=550)
        role_skill_name = f"tel99-role-{task['role'].replace('_', '-')}"
        skills_used = [role_skill_name] if role_skill_card else [
            s["name"] for s in context_engine.select_relevant_skills(SKILLS_DIR, f"{task['role']} {task['objective']}", limit=2)
        ]
        conf = metacognition.estimate_task_confidence(
            estimated_lines=45, prior_role_success_rate=0.92, has_verified_memory=bool(mem_lessons or role_skill_card)
        )

        # Empirical routing per role + 3-mentor complementarity escalation chain (max 3 attempts)
        first_model = expert_model if task["difficulty"] == "hard" else role_routing.get(task["role"], secondary_model)
        alt_model = secondary_model if first_model == expert_model else expert_model
        third_model = "qwen/qwen3.8-27b" if "qwen/qwen3.8-27b" not in (first_model, alt_model) else expert_model
        model_chain = [first_model, alt_model, third_model]

        prior_hashes: list[str] = []
        attempts_log: list[dict] = []
        last_out = ""
        prev_out = ""
        last_ver: dict[str, Any] = {"ok": False, "error": "not run", "passed": [], "failed": []}

        for attempt in range(1, 4):
            mdl = model_chain[attempt - 1]
            t0 = time.monotonic()
            if attempt == 1:
                sys_p = smart_repair.build_structured_reasoning_prompt(
                    role=f"tel99-{task['role']}",
                    objective=task["objective"],
                    constraints=[
                        "Python 3.12 stdlib only (or valid JSON object ONLY if JSON requested).",
                        "No eval/exec/__import__/shell=True.",
                        improvement_cycle._role_instruction_hint(task["role"]),
                        "ZERO docstrings, ZERO comments, ZERO example/main blocks; output ONLY the final code block or JSON object.",
                    ],
                )
                usr_p = task["objective"]
                if role_skill_card:
                    usr_p += f"\n\nSpecialized Skill ({role_skill_name}):\n{role_skill_card}"
                if mem_lessons:
                    usr_p += "\n\nVerified memory lessons:\n- " + "\n- ".join(mem_lessons[:2])
            else:
                sys_p = "Return ONLY the complete corrected Python 3.12 stdlib code (or exact JSON object) with ZERO prose/docstrings."
                diff = smart_repair.compute_bounded_diff(prev_out, last_out) if prev_out else ""
                usr_p = (
                    f"Original specification:\n{task['objective']}\n\n"
                    + smart_repair.build_smart_repair_prompt(
                        previous_code=last_out,
                        exact_error=str(last_ver.get("error") or ""),
                        passed_checks=last_ver.get("passed", []),
                        failed_checks=last_ver.get("failed", []),
                        contract_constraints=[
                            improvement_cycle._role_instruction_hint(task["role"]),
                            "Preserve exact function/class name, signature, and return types.",
                            "Re-read every edge case (bool vs int, empty inputs, bounds, exact keys, rounding).",
                        ],
                        prior_attempts=attempts_log,
                        memory_lessons=mem_lessons[:2],
                        previous_diff=diff,
                    )
                )
            try:
                rf = "json" if task.get("kind") == "json" else None
                raw, meta = _call_groq_safe(mdl, system=sys_p, prompt=usr_p, response_format=rf)
                if task.get("kind") == "json":
                    raw = local_deterministic_tools.extract_clean_json(raw)
                else:
                    raw = local_deterministic_tools.strip_trailing_example_blocks(raw)
                ver = benchmark_suite_100.verify_task_output(task, raw)
                fp = smart_repair.code_fingerprint(raw)
                rep = smart_repair.detect_repeated_attempt(raw, prior_hashes)
            except Exception as exc:
                raw, meta, fp, rep = "", {}, "", False
                ver = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:160]}", "passed": [], "failed": ["infra"]}

            prior_hashes.append(fp)
            attempts_log.append({
                "attempt": attempt,
                "model": mdl,
                "seconds": round(time.monotonic() - t0, 2),
                "prompt_tokens": int(meta.get("prompt_tokens") or 0),
                "completion_tokens": int(meta.get("completion_tokens") or 0),
                "ok": bool(ver["ok"]),
                "repeated": rep,
                "error": ver.get("error"),
            })
            prev_out = last_out
            last_out = raw
            last_ver = ver
            if ver["ok"]:
                break

        repaired = bool(last_ver["ok"] and len(attempts_log) > 1)
        row = {
            "id": tid,
            "role": task["role"],
            "difficulty": task["difficulty"],
            "ok": bool(last_ver["ok"]),
            "attempts": len(attempts_log),
            "repaired": repaired,
            "model_used": attempts_log[-1]["model"],
            "confidence": conf["calibrated_confidence"],
            "lessons_used": len(mem_lessons),
            "skills_used": skills_used,
            "total_tokens": sum(a["prompt_tokens"] + a["completion_tokens"] for a in attempts_log),
            "seconds": round(sum(a["seconds"] for a in attempts_log), 2),
            "cost_usd": 0.0,
            "error": last_ver.get("error"),
            "attempts_log": attempts_log,
        }
        results.append(row)
        _write_atomic(ckpt_path, {"completed": len(results), "total": len(tasks), "results": results})
        print(json.dumps({"phase": "held_out_final", "n": f"{len(results)}/{len(tasks)}", "id": tid, "role": task["role"], "ok": row["ok"], "att": row["attempts"], "mdl": row["model_used"], "err": row["error"]}), flush=True)

        traj.record(
            project="tel99-bench-heldout", mission_id=tid, objective=task["objective"][:400],
            model=row["model_used"], role=f"tel99-{task['role']}",
            tools_used=[{"tool": "groq_hybrid", "model": row["model_used"]}],
            decisions=[f"att={row['attempts']}", f"rag={len(mem_lessons)}"],
            errors=[str(a["error"]) for a in attempts_log if a.get("error")],
            repairs=attempts_log[1:], tests=[{"ok": row["ok"]}], artifacts=[],
            verdict="SUCCESS" if row["ok"] else "FAILURE", duration_seconds=row["seconds"], cost_usd=0.0,
        )
        if any(a.get("error") for a in attempts_log):
            flib.record_failure(
                project="tel99-bench-heldout", mission_id=tid, category="VERIFICATION_ERROR",
                context_summary=f"held_out/{task['role']}/{tid}",
                cause=str(attempts_log[0].get("error") or "")[:240],
                cause_confirmed=row["ok"], evidence=f"att={row['attempts']} ok={row['ok']}",
                attempts=attempts_log, validated_solution=("Repaired via smart_repair+escalation" if repaired else ""),
                preventive_measure="Apply role constraints", model=row["model_used"], role=f"tel99-{task['role']}",
            )

    passed = sum(1 for r in results if r["ok"])
    fp_cnt = sum(1 for r in results if r["ok"] and r["attempts"] == 1)
    rep_cnt = sum(1 for r in results if r["repaired"])
    by_role = {}
    for role in benchmark_suite_100.ROLES_12:
        rr = [r for r in results if r["role"] == role]
        by_role[role] = {
            "passed": sum(1 for r in rr if r["ok"]),
            "total": len(rr),
            "rate": round(sum(1 for r in rr if r["ok"]) / max(1, len(rr)), 4),
            "first_pass": sum(1 for r in rr if r["ok"] and r["attempts"] == 1),
        }
    by_diff = {}
    for d in ("easy", "medium", "hard"):
        dr = [r for r in results if r["difficulty"] == d]
        by_diff[d] = {"passed": sum(1 for r in dr if r["ok"]), "total": len(dr), "rate": round(sum(1 for r in dr if r["ok"]) / max(1, len(dr)), 4)}
    cal = metacognition.compute_calibration_metrics([{"confidence": r["confidence"], "success": r["ok"]} for r in results])
    return {
        "passed": passed,
        "total": len(results),
        "success_rate": round(passed / max(1, len(results)), 4),
        "first_pass": fp_cnt,
        "first_pass_rate": round(fp_cnt / max(1, len(results)), 4),
        "repaired": rep_cnt,
        "total_tokens": sum(r["total_tokens"] for r in results),
        "avg_seconds": round(sum(r["seconds"] for r in results) / max(1, len(results)), 2),
        "duration_seconds": round(time.monotonic() - t_all, 2),
        "cost_usd": 0.0,
        "by_role": by_role,
        "by_difficulty": by_diff,
        "calibration": cal,
        "target_65_of_72_achieved": passed >= 65,
        "target_95_pct_achieved": (passed / max(1, len(results))) >= 0.95,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--v2", action="store_true", help="Run fresh held-out v2 evaluation using 12 specialized Skills + 3-mentor chain (preserves v1 report)")
    args = ap.parse_args(argv)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    ART_DIR.mkdir(parents=True, exist_ok=True)
    MEM_DIR.mkdir(parents=True, exist_ok=True)

    manifest = benchmark_suite_100.benchmark_manifest()
    _write_atomic(ART_DIR / "benchmark_manifest_frozen.json", manifest)

    dev_tasks = benchmark_suite_100.get_split("dev")
    train_tasks = benchmark_suite_100.get_split("train")
    ho_tasks = benchmark_suite_100.get_split("held_out_final")

    # 1. Experimental 3-model shootout on DEV (24 tasks)
    dev_results = {}
    for mdl in GROQ_MODELS:
        slug = mdl.replace("/", "_")
        dev_results[mdl] = _run_single_model_dev(mdl, dev_tasks, ART_DIR / f"ckpt_dev_groq_{slug}.json")

    # Rank models empirically by dev success_rate, then speed
    ranked_models = sorted(
        GROQ_MODELS,
        key=lambda m: (-dev_results[m]["success_rate"], dev_results[m]["avg_seconds"]),
    )
    expert_model = ranked_models[0]
    secondary_model = ranked_models[1]
    role_routing = {}
    for role in benchmark_suite_100.ROLES_12:
        role_routing[role] = sorted(
            GROQ_MODELS,
            key=lambda m: (-dev_results[m]["by_role"].get(role, 0.0), -dev_results[m]["success_rate"], dev_results[m]["avg_seconds"]),
        )[0]

    # 2. Champion-Challenger paired comparison on DEV (best Groq vs qwen/qwen3.8-27b)
    champ_id = "groq-qwen-27b-dev"
    chall_id = f"groq-{expert_model.replace('/', '-')}-dev"
    m_base = {r["id"]: r for r in dev_results["qwen/qwen3.8-27b"]["results"]}
    m_best = {r["id"]: r for r in dev_results[expert_model]["results"]}
    paired_dev = []
    for tid in m_base:
        if tid in m_best:
            b, c = m_base[tid], m_best[tid]
            paired_dev.append(improvement.Outcome(
                task_id=tid, model_id=champ_id, success=bool(b["ok"]),
                tokens=int(b.get("prompt_tokens", 0) + b.get("completion_tokens", 0)),
                seconds=float(b.get("seconds", 0.0)), evidence=f"dev/{tid}",
            ))
            paired_dev.append(improvement.Outcome(
                task_id=tid, model_id=chall_id, success=bool(c["ok"]),
                tokens=int(c.get("prompt_tokens", 0) + c.get("completion_tokens", 0)),
                seconds=float(c.get("seconds", 0.0)), evidence=f"dev/{tid}",
            ))
    cc_dev = evolution_lab.run_champion_challenger(
        champion_id=champ_id,
        challenger_id=chall_id,
        champion_profile={"model": "qwen/qwen3.8-27b"},
        challenger_profile={"model": expert_model, "role_routing": role_routing},
        paired_outcomes=paired_dev,
        store_dir=ART_DIR / "profiles",
        owner_approved=False,
    )

    # 3. Mine verified mentor lessons from TRAIN split ONLY (24 tasks)
    train_summary = _mine_train_mentor_lessons(expert_model, train_tasks, ART_DIR / "ckpt_train_mentor.json")

    # 4. Evaluate FROZEN held_out_final (72 unseen tasks!)
    ckpt_name = "ckpt_heldout_groq_hybrid_v2.json" if args.v2 else "ckpt_heldout_groq_hybrid.json"
    rep_name = "groq_hybrid_benchmark_120_v2_report.json" if args.v2 else "groq_hybrid_benchmark_120_report.json"
    ho_summary = _evaluate_frozen_held_out_hybrid(
        role_routing, expert_model, secondary_model, ho_tasks, ART_DIR / ckpt_name
    )

    report = {
        "schema_version": 1,
        "evaluation_type": "REGRESSION_TEST_ON_V1_HELDOUT_72" if args.v2 else "FROZEN_V1_HELDOUT_72",
        "version": "v2-regression-12-skills-3-mentors" if args.v2 else "v1",
        "completed_at": _now_iso(),
        "manifest": manifest,
        "dev_3_model_shootout": {m: {k: v for k, v in d.items() if k != "results"} for m, d in dev_results.items()},
        "empirical_ranking": ranked_models,
        "empirical_role_routing": role_routing,
        "champion_challenger_dev": cc_dev,
        "train_mentor_learning": train_summary,
        "held_out_final_hybrid": {k: v for k, v in ho_summary.items() if k != "results"},
        "groq_budget_after": provider_router.CloudBudgetLedger().status("groq"),
        "held_out_final_details": ho_summary["results"],
    }
    _write_atomic(ART_DIR / rep_name, report)
    print("GROQ_HYBRID_120_FINAL:", json.dumps({
        "held_out_seal": manifest["seals_sha256"]["held_out_final"],
        "dev_shootout": {m: f"{d['passed']}/{d['total']} ({d['success_rate']:.1%}, {d['avg_seconds']}s)" for m, d in dev_results.items()},
        "train_mentor": f"{train_summary['passed']}/{train_summary['total']} (lessons={train_summary['lessons_stored']})",
        "held_out_final": f"{ho_summary['passed']}/{ho_summary['total']} ({ho_summary['success_rate']:.2%})",
        "held_out_first_pass": f"{ho_summary['first_pass']}/{ho_summary['total']} ({ho_summary['first_pass_rate']:.2%})",
        "target_65_of_72": ho_summary["target_65_of_72_achieved"],
        "target_95_pct": ho_summary["target_95_pct_achieved"],
        "by_role": ho_summary["by_role"],
        "cost_usd": 0.0,
    }, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
