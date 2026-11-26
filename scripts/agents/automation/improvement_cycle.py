"""Bounded Improvement Loop & Multi-Model Evaluator targeting >= 89% on Frozen 120-Mission Benchmark.

Reuses existing TEL99 modules (zero second supervisor, zero extra spend, concurrency = 1):
- benchmark_suite_100 (frozen 120 tasks: 24 train / 24 dev / 72 held_out_final across 12 roles)
- ide_coordination.local_inference_lease (via OllamaNativeProvider)
- context_engine (HybridMemoryIndex SQLite FTS5 + Skill selection + structured JSON validation)
- metacognition (estimate_task_confidence, compute_calibration_metrics, FailureLibrary, TrajectoryRecorder)
- smart_repair (structured reasoning prompt, bounded diff, anti-repeat SHA-256)
- evolution_lab (run_champion_challenger via intelligence.improvement.compare + profile rollback)
- agent_academy (versioned profile snapshots & rollback)
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

from scripts.agents.automation import (
    agent_academy,
    benchmark_suite_100,
    context_engine,
    evolution_lab,
    ide_coordination,
    metacognition,
    ollama_native,
    provider_router,
    smart_repair,
)
from scripts.agents.intelligence import improvement
from scripts.agents.intelligence.memory import Entry, MemoryStore
from scripts.agents.native.provider import ProviderError

PRIMARY_MODEL = "gemma4:e4b-tel99-8k"
FALLBACK_MODEL = "qwen3.5:9b-q4_K_M"
SKILLS_DIR = ROOT / ".agents" / "skills"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _role_instruction_hint(role: str) -> str:
    hints = {
        "development": "Handle edge cases strictly: reject bool when int/float expected (`isinstance(x, bool)`), validate bounds and types cleanly.",
        "quant": "Strictly causal math (index i uses ONLY indices <= i), reject bool/non-positive prices, round to exact requested decimals.",
        "quality": "Use `ast.parse` and `hashlib.sha256` cleanly; verify non-empty check lists and exact bool checks (`is True`/`is False`).",
        "coordination": "Deterministic sorting, Kahn's algorithm for DAG topological sort, strict lease ownership (never release foreign active lease).",
        "cloud": "Enforce loopback-only URLs, pinned @sha256 digests (64 hex chars), strict no-extra-spend billing rules, never mutate input env dict.",
        "security": "Use pathlib.Path.resolve() for containment, hmac.compare_digest for digests, regex redaction without mutating input dicts.",
        "mobile": "Use exact regex/string checks for HTML/CSS/ARIA, handle comments when balancing braces, reject bool in numeric formatters.",
        "documentation": "Preserve exact Markdown formatting, escape pipes in tables, parse ISO dates strictly (YYYY-MM-DD), return exact JSON when asked.",
        "evaluation": "Use exact math.comb/Wilson/Brier formulas, reject bool/out-of-range probabilities, return exact JSON schema when asked.",
        "market_data": "Validate OHLCV inequalities, strictly check bid < ask, aggregate timestamps via `ts // bucket_s * bucket_s`.",
        "monitoring": "Distinguish resident vs pre-load RAM thresholds, exact nearest-rank p95 (`math.ceil(0.95*n)-1`), return exact JSON when asked.",
        "release": "Enforce strict semver/40-hex SHA/ISO UTC parsing, never allow auto-merge on main/master, return exact JSON when asked.",
    }
    return hints.get(role, "Follow exact specification, validate types cleanly, output ONLY code or JSON.")


def evaluate_split(
    split: str,
    *,
    mode: str,
    primary_model: str = PRIMARY_MODEL,
    fallback_model: str | None = FALLBACK_MODEL,
    allow_free_cloud: bool = False,
    max_attempts: int = 3,
    memory_root: Path | None = None,
    artifacts_dir: Path | None = None,
    checkpoint_file: Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Evaluate a benchmark split with progressive atomic checkpointing (resumes cleanly without replay).

    Modes:
    - 'baseline' / 'A_local_only': local Ollama alone (1 attempt, minimal prompt).
    - 'B_groq_eligible': Groq free cloud on non-confidential eligible tasks with auto-Ollama fallback (minimal prompt).
    - 'upgraded' / 'C_hybrid_full': Harness + Context Engine + FTS5 RAG + Skills + Smart Repair +
      hybrid routing (local for easy, Groq/OpenRouter free or local fallback for hard/repairs).
    """
    tasks = benchmark_suite_100.get_split(split)
    if limit is not None:
        tasks = tasks[:limit]

    cloud_inventory = provider_router.probe_all_providers() if (allow_free_cloud or mode == "B_groq_eligible") else None
    is_minimal_prompt = mode in ("baseline", "A_local_only", "B_groq_eligible")
    use_cloud = bool(allow_free_cloud or mode == "B_groq_eligible")

    # Resume from existing checkpoint if present (NEVER replays completed tasks!)
    completed_by_id: dict[str, dict] = {}
    if checkpoint_file and checkpoint_file.is_file():
        try:
            prev = json.loads(checkpoint_file.read_text(encoding="utf-8"))
            if prev.get("split") == split and prev.get("mode") == mode:
                for row in prev.get("results") or []:
                    if isinstance(row, dict) and "id" in row:
                        completed_by_id[row["id"]] = row
        except (OSError, ValueError):
            pass

    traj_rec = metacognition.TrajectoryRecorder(artifacts_dir) if artifacts_dir else None
    flib = metacognition.FailureLibrary(artifacts_dir, memory_root=memory_root) if artifacts_dir else None
    mem_store = MemoryStore(memory_root) if memory_root else None
    started = time.monotonic()

    results: list[dict] = []
    for task in tasks:
        tid = task["id"]
        if tid in completed_by_id:
            results.append(completed_by_id[tid])
            continue

        mem_lessons: list[str] = []
        skills_used: list[str] = []
        if mode != "baseline":
            if memory_root is not None:
                hits = context_engine.HybridMemoryIndex(memory_root).search(
                    "tel99-bench", f"{task['role']} {task['objective']}", limit=3, verified_only=True, role=task["role"]
                )
                mem_lessons = [f"{h['title']}: {h['body']}" for h in hits]
            if SKILLS_DIR.is_dir():
                sk = context_engine.select_relevant_skills(SKILLS_DIR, f"{task['role']} {task['objective']}", limit=2)
                skills_used = [s["name"] for s in sk]

        conf_est = metacognition.estimate_task_confidence(
            estimated_lines=45,
            prior_role_success_rate=0.80 if mode != "baseline" else 0.60,
            has_verified_memory=bool(mem_lessons),
        )
        prior_hashes: list[str] = []
        attempts_log: list[dict] = []
        last_output = ""
        prev_output = ""
        last_ver: dict[str, Any] = {"ok": False, "error": "not run", "passed": [], "failed": []}

        # In baseline/A/B modes: single-shot or minimal retry; in upgraded/C: full adaptive repair + escalation
        effective_max = 1 if is_minimal_prompt else max_attempts

        for attempt in range(1, effective_max + 1):
            # Model selection: hybrid cloud (non-confidential) vs local Ollama
            cloud_adapter = None
            active_provider = "ollama"
            active_model = primary_model
            if use_cloud and cloud_inventory is not None:
                is_rep = attempt > 1
                sel = provider_router.select_executor(
                    "code",
                    difficulty="hard" if (mode == "B_groq_eligible" or task["difficulty"] == "hard" or is_rep) else task["difficulty"],
                    confidential=False,
                    allow_free_cloud=True,
                    is_repair=is_rep,
                    inventory=cloud_inventory,
                )
                chosen = sel.get("chosen") or {}
                if chosen.get("provider") in ("groq", "openrouter"):
                    active_provider = chosen["provider"]
                    active_model = chosen["served_model"]
                    cloud_adapter = provider_router.OpenAICompatFreeCloudAdapter(
                        provider=active_provider,
                        model=active_model,
                        confidential=False,
                        fallback_ollama_model=primary_model,
                    )
            if cloud_adapter is None and not is_minimal_prompt and fallback_model and attempt == effective_max and effective_max >= 3:
                active_model = fallback_model

            eng = ide_coordination.probe_local_engines()
            avail_mib = eng.get("available_memory_mib")
            if cloud_adapter is None:
                resident = active_model in ((eng.get("ollama") or {}).get("loaded_models") or [])
                profile = "patch" if is_minimal_prompt else task.get("task_profile", "module")
                budget = ollama_native.compute_adaptive_budget(
                    active_model,
                    task_profile=profile,
                    estimated_lines=45,
                    available_memory_mib=avail_mib,
                    model_is_resident=resident,
                )
                provider = ollama_native.OllamaNativeProvider(
                    model=active_model,
                    timeout=budget["timeout"],
                    max_tokens=budget["max_tokens"],
                    keep_alive="120s",
                    task_profile=budget["effective_profile"],
                    num_ctx=budget["num_ctx"],
                    num_thread=budget["num_thread"],
                )
            else:
                provider = cloud_adapter

            t0 = time.monotonic()
            if is_minimal_prompt:
                sys_p = "Return ONLY clean Python 3 stdlib code (or JSON if requested)."
                usr_p = task["objective"]
            elif attempt == 1 or active_model != primary_model:
                constraints = [
                    "Python 3.12 stdlib only (or valid JSON object ONLY if JSON requested).",
                    "No eval/exec/__import__/shell=True.",
                    _role_instruction_hint(task["role"]),
                    "Output ONLY the final code block or JSON object with zero prose.",
                ]
                sys_p = smart_repair.build_structured_reasoning_prompt(
                    role=f"tel99-{task['role']}", objective=task["objective"], constraints=constraints
                )
                usr_p = task["objective"]
                if mem_lessons:
                    usr_p += "\n\nVerified memory lessons:\n- " + "\n- ".join(mem_lessons)
                if active_model != primary_model and last_ver.get("error"):
                    usr_p += f"\n\nPrior model attempt failed with: {last_ver['error']}\nAvoid this mistake and implement cleanly."
            else:
                sys_p = "Return ONLY the complete corrected Python 3 stdlib code (or exact JSON object)."
                diff = smart_repair.compute_bounded_diff(prev_output, last_output) if prev_output else ""
                usr_p = (
                    f"Original specification:\n{task['objective']}\n\n"
                    + smart_repair.build_smart_repair_prompt(
                        previous_code=last_output,
                        exact_error=str(last_ver.get("error") or ""),
                        passed_checks=last_ver.get("passed", []),
                        failed_checks=last_ver.get("failed", []),
                        contract_constraints=[_role_instruction_hint(task["role"]), "Preserve exact function/class name and signature"],
                        prior_attempts=attempts_log,
                        memory_lessons=mem_lessons,
                        previous_diff=diff,
                    )
                )

            try:
                resp_fmt = "json" if (not is_minimal_prompt and task.get("kind") == "json") else None
                raw = provider.complete(system=sys_p, prompt=usr_p, response_format=resp_fmt)
                ver = benchmark_suite_100.verify_task_output(task, raw)
                fp = smart_repair.code_fingerprint(raw)
                repeated = smart_repair.detect_repeated_attempt(raw, prior_hashes)
            except ProviderError as exc:
                raw, fp, repeated = "", "", False
                ver = {"ok": False, "error": f"ProviderError: {exc}", "passed": [], "failed": ["infra"]}

            pmeta = getattr(provider, "last_metadata", {}) or {}
            prior_hashes.append(fp)
            attempts_log.append({
                "attempt": attempt,
                "provider": pmeta.get("provider_used", active_provider),
                "model": pmeta.get("model_used", active_model),
                "fallback_used": bool(pmeta.get("fallback_used", False)),
                "prompt_tokens": int(pmeta.get("prompt_tokens") or 0),
                "completion_tokens": int(pmeta.get("completion_tokens") or pmeta.get("eval_count") or 0),
                "available_memory_mib": avail_mib,
                "cost_usd": 0.0,
                "seconds": round(time.monotonic() - t0, 2),
                "ok": ver["ok"],
                "repeated": repeated,
                "error": ver.get("error"),
            })
            prev_output = last_output
            last_output = raw
            last_ver = ver
            if ver["ok"]:
                break

        repaired = bool(last_ver["ok"] and len(attempts_log) > 1)
        row = {
            "id": tid,
            "role": task["role"],
            "split": split,
            "difficulty": task["difficulty"],
            "ok": bool(last_ver["ok"]),
            "attempts": len(attempts_log),
            "repaired": repaired,
            "model_used": attempts_log[-1]["model"] if attempts_log else primary_model,
            "confidence": conf_est["calibrated_confidence"],
            "lessons_used": len(mem_lessons),
            "skills_used": skills_used,
            "error": last_ver.get("error"),
            "attempts_log": attempts_log,
        }
        results.append(row)
        print(json.dumps({"split": split, "mode": mode, "id": tid, "role": task["role"], "ok": row["ok"], "att": row["attempts"], "mdl": row["model_used"], "err": row["error"]}), flush=True)

        # Record trajectory & failure learning ONLY (and learn verified lessons ONLY from train/dev, NEVER from held_out_final!)
        if traj_rec is not None:
            traj_rec.record(
                project="tel99-bench",
                mission_id=f"{mode}-{tid}",
                objective=task["objective"][:400],
                model=row["model_used"],
                role=f"tel99-{task['role']}",
                tools_used=[{"tool": "ollama_native", "mode": mode}],
                decisions=[f"split={split}", f"att={row['attempts']}"],
                errors=[str(a["error"]) for a in attempts_log if a.get("error")],
                repairs=attempts_log[1:],
                tests=[{"ok": row["ok"]}],
                artifacts=[],
                verdict="SUCCESS" if row["ok"] else "FAILURE",
                duration_seconds=round(sum(a["seconds"] for a in attempts_log), 2),
            )
        if flib is not None and any(a.get("error") for a in attempts_log):
            first_err = next((str(a["error"]) for a in attempts_log if a.get("error")), "error")
            flib.record_failure(
                project="tel99-bench",
                mission_id=f"{mode}-{tid}",
                category="ENGINE_ERROR" if "ProviderError" in first_err else "VERIFICATION_ERROR",
                context_summary=f"{split}/{task['role']}/{tid}",
                cause=first_err[:240],
                cause_confirmed=row["ok"],
                evidence=f"attempts={row['attempts']} ok={row['ok']}",
                attempts=attempts_log,
                validated_solution=(f"Fixed on attempt {row['attempts']} ({row['model_used']})" if repaired else ""),
                preventive_measure=_role_instruction_hint(task["role"]),
                model=row["model_used"],
                role=f"tel99-{task['role']}",
            )
        # Strict anti-leakage: ONLY extract new verified lessons into MemoryStore during `train` split!
        if split == "train" and mem_store is not None and repaired:
            lid = f"fix-{tid}"
            if mem_store.get("tel99-bench", lid) is None:
                mem_store.record(
                    Entry(
                        id=lid,
                        project="tel99-bench",
                        kind="fix",
                        title=f"[{task['role']}] Avoid {str(attempts_log[0].get('error') or 'error')[:60]}",
                        body=f"Repaired on attempt {row['attempts']}: {_role_instruction_hint(task['role'])}",
                        tags=(task["role"], tid, "train-lesson"),
                        source=f"bench-train/{tid}",
                        author=f"tel99-{task['role']}",
                        verified=True,
                        verified_by="benchmark_suite_100",
                        confidence=0.95,
                    ),
                    actor="improvement-cycle",
                )

        if checkpoint_file is not None:
            _write_atomic(checkpoint_file, {"split": split, "mode": mode, "completed": len(results), "total": len(tasks), "results": results})

    passed = sum(1 for r in results if r["ok"])
    first_pass = sum(1 for r in results if r["ok"] and r["attempts"] == 1)
    repaired_cnt = sum(1 for r in results if r["repaired"])
    by_role = {}
    for role in benchmark_suite_100.ROLES_12:
        rr = [r for r in results if r["role"] == role]
        if rr:
            rp = sum(1 for r in rr if r["ok"])
            by_role[role] = {"passed": rp, "total": len(rr), "rate": round(rp / len(rr), 4)}
    by_diff = {}
    for d in ("easy", "medium", "hard"):
        dr = [r for r in results if r["difficulty"] == d]
        if dr:
            dp = sum(1 for r in dr if r["ok"])
            by_diff[d] = {"passed": dp, "total": len(dr), "rate": round(dp / len(dr), 4)}
    cal = metacognition.compute_calibration_metrics([{"confidence": r["confidence"], "success": r["ok"]} for r in results])
    return {
        "schema_version": 1,
        "evaluated_at": _now_iso(),
        "split": split,
        "mode": mode,
        "primary_model": primary_model,
        "fallback_model": fallback_model if mode != "baseline" else None,
        "total": len(results),
        "passed": passed,
        "success_rate": round(passed / max(1, len(results)), 4),
        "first_pass": first_pass,
        "first_pass_rate": round(first_pass / max(1, len(results)), 4),
        "repaired": repaired_cnt,
        "by_role": by_role,
        "by_difficulty": by_diff,
        "calibration": cal,
        "duration_seconds": round(time.monotonic() - started, 2),
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, default=Path.home() / "Desktop" / "TEL99_BENCHMARK_120_STATE")
    parser.add_argument("--primary-model", default=PRIMARY_MODEL)
    parser.add_argument("--fallback-model", default=FALLBACK_MODEL)
    parser.add_argument("--allow-free-cloud", action="store_true", help="Enable verified free Groq/OpenRouter hybrid routing")
    parser.add_argument("--pilot", type=int, default=0, help="Run a short A/B/C pilot on N unseen dev tasks")
    parser.add_argument("--skip-baseline-held-out", action="store_true")
    args = parser.parse_args(argv)

    work = args.work_dir.resolve()
    mem_dir = work / "memory"
    art_dir = work / "artifacts"
    work.mkdir(parents=True, exist_ok=True)

    manifest = benchmark_suite_100.benchmark_manifest()
    _write_atomic(art_dir / "benchmark_manifest_frozen.json", manifest)
    print("FROZEN_MANIFEST:", json.dumps({k: manifest[k] for k in ("total_tasks", "counts_by_split", "seals_sha256")}), flush=True)

    if args.pilot > 0:
        pilot_a = evaluate_split(
            "dev", mode="A_local_only", primary_model=args.primary_model, fallback_model=None,
            allow_free_cloud=False, max_attempts=1, memory_root=mem_dir, artifacts_dir=art_dir,
            checkpoint_file=art_dir / "ckpt_pilot_A.json", limit=args.pilot,
        )
        pilot_b = evaluate_split(
            "dev", mode="B_groq_eligible", primary_model=args.primary_model, fallback_model=None,
            allow_free_cloud=True, max_attempts=1, memory_root=mem_dir, artifacts_dir=art_dir,
            checkpoint_file=art_dir / "ckpt_pilot_B.json", limit=args.pilot,
        )
        pilot_c = evaluate_split(
            "dev", mode="C_hybrid_full", primary_model=args.primary_model, fallback_model=args.fallback_model,
            allow_free_cloud=True, max_attempts=3, memory_root=mem_dir, artifacts_dir=art_dir,
            checkpoint_file=art_dir / "ckpt_pilot_C.json", limit=args.pilot,
        )
        ide_coordination.unload_ollama_models()
        pilot_rep = {
            "pilot_tasks": args.pilot,
            "A_local_only": {k: v for k, v in pilot_a.items() if k != "results"},
            "B_groq_eligible": {k: v for k, v in pilot_b.items() if k != "results"},
            "C_hybrid_full": {k: v for k, v in pilot_c.items() if k != "results"},
        }
        _write_atomic(art_dir / "hybrid_pilot_report.json", pilot_rep)
        print("HYBRID_PILOT_SUMMARY:", json.dumps({
            "A_local": f"{pilot_a['passed']}/{pilot_a['total']} ({pilot_a['success_rate']:.2%})",
            "B_groq": f"{pilot_b['passed']}/{pilot_b['total']} ({pilot_b['success_rate']:.2%})",
            "C_hybrid": f"{pilot_c['passed']}/{pilot_c['total']} ({pilot_c['success_rate']:.2%})",
        }, indent=2), flush=True)
        return 0

    # 1. Train split (24 tasks): extract verified lessons from real failures into MemoryStore
    train_res = evaluate_split(
        "train", mode="upgraded", primary_model=args.primary_model, fallback_model=args.fallback_model,
        allow_free_cloud=args.allow_free_cloud,
        max_attempts=3, memory_root=mem_dir, artifacts_dir=art_dir, checkpoint_file=art_dir / "ckpt_train.json",
    )

    # 2. Dev split (24 tasks): Baseline vs Upgraded Champion-Challenger comparison
    dev_base = evaluate_split(
        "dev", mode="baseline", primary_model=args.primary_model, fallback_model=None,
        allow_free_cloud=False,
        max_attempts=1, memory_root=mem_dir, artifacts_dir=art_dir, checkpoint_file=art_dir / "ckpt_dev_baseline.json",
    )
    dev_up = evaluate_split(
        "dev", mode="upgraded", primary_model=args.primary_model, fallback_model=args.fallback_model,
        allow_free_cloud=args.allow_free_cloud,
        max_attempts=3, memory_root=mem_dir, artifacts_dir=art_dir, checkpoint_file=art_dir / "ckpt_dev_upgraded.json",
    )
    champ_id = "bench120-baseline-v1"
    chall_id = "bench120-upgraded-harness-rag-skills-fallback-v2"
    b_map = {r["id"]: r for r in dev_base["results"]}
    u_map = {r["id"]: r for r in dev_up["results"]}
    paired_dev = []
    for tid in b_map:
        if tid in u_map:
            b, u = b_map[tid], u_map[tid]
            paired_dev.append(improvement.Outcome(
                task_id=tid, model_id=champ_id, success=bool(b["ok"]),
                tokens=sum(int(a.get("completion_tokens") or 0) for a in b.get("attempts_log") or []),
                seconds=sum(float(a.get("seconds") or 0.0) for a in b.get("attempts_log") or []),
                evidence=f"dev/{tid}",
            ))
            paired_dev.append(improvement.Outcome(
                task_id=tid, model_id=chall_id, success=bool(u["ok"]),
                tokens=sum(int(a.get("completion_tokens") or 0) for a in u.get("attempts_log") or []),
                seconds=sum(float(a.get("seconds") or 0.0) for a in u.get("attempts_log") or []),
                evidence=f"dev/{tid}",
            ))
    cc_dev = evolution_lab.run_champion_challenger(
        champion_id=champ_id,
        challenger_id=chall_id,
        champion_profile={"mode": "baseline", "model": args.primary_model},
        challenger_profile={"mode": "upgraded", "primary": args.primary_model, "fallback": args.fallback_model, "allow_free_cloud": args.allow_free_cloud, "rag": True, "skills": True, "smart_repair": True},
        paired_outcomes=paired_dev,
        store_dir=art_dir / "profiles",
        owner_approved=False,
    )

    # 3. Frozen Held-Out Final Evaluation (72 completely unseen tasks across all 12 roles!)
    ho_base = None
    if not args.skip_baseline_held_out:
        ho_base = evaluate_split(
            "held_out_final", mode="baseline", primary_model=args.primary_model, fallback_model=None,
            allow_free_cloud=False,
            max_attempts=1, memory_root=mem_dir, artifacts_dir=art_dir, checkpoint_file=art_dir / "ckpt_heldout_baseline.json",
        )
    ho_up = evaluate_split(
        "held_out_final", mode="upgraded", primary_model=args.primary_model, fallback_model=args.fallback_model,
        allow_free_cloud=args.allow_free_cloud,
        max_attempts=3, memory_root=mem_dir, artifacts_dir=art_dir, checkpoint_file=art_dir / "ckpt_heldout_upgraded.json",
    )

    ide_coordination.unload_ollama_models()

    final_rate = ho_up["success_rate"]
    report = {
        "schema_version": 1,
        "completed_at": _now_iso(),
        "manifest": manifest,
        "target_rate": 0.89,
        "stretch_rate": 0.95,
        "target_89_achieved": final_rate >= 0.89,
        "stretch_95_achieved": final_rate >= 0.95,
        "train": {k: v for k, v in train_res.items() if k != "results"},
        "dev_baseline": {k: v for k, v in dev_base.items() if k != "results"},
        "dev_upgraded": {k: v for k, v in dev_up.items() if k != "results"},
        "champion_challenger_dev": cc_dev,
        "held_out_baseline": ({k: v for k, v in ho_base.items() if k != "results"} if ho_base else None),
        "held_out_upgraded": {k: v for k, v in ho_up.items() if k != "results"},
        "held_out_upgraded_details": ho_up["results"],
    }
    _write_atomic(art_dir / "benchmark_120_final_report.json", report)
    print("BENCHMARK_120_SUMMARY:", json.dumps({
        "train_rate": train_res["success_rate"],
        "dev_baseline": dev_base["success_rate"],
        "dev_upgraded": dev_up["success_rate"],
        "held_out_baseline": ho_base["success_rate"] if ho_base else None,
        "held_out_upgraded": f"{ho_up['passed']}/{ho_up['total']} ({ho_up['success_rate']:.2%})",
        "held_out_first_pass": f"{ho_up['first_pass']}/{ho_up['total']} ({ho_up['first_pass_rate']:.2%})",
        "target_89_achieved": report["target_89_achieved"],
        "by_role": ho_up["by_role"],
    }, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
