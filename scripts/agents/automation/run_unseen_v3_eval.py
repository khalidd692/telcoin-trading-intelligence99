"""Identical-Conditions Evaluator for Brand-New Frozen Benchmark Unseen V3 (60 Missions, 12 Roles).

Runs strictly separated, atomic-checkpointed evaluations:
  1. `local_before` : 100% LOCAL Gemma 4 (0 cloud calls), baseline naive prompt (1 attempt).
  2. `local_after`  : 100% LOCAL Gemma 4 (0 cloud calls), 12 specialized role Skills + verified
                      train-only RAG + deterministic local tools + bounded 3-attempt Smart Repair.
  3. `hybrid_after` : Hybrid 3-mentor Groq ($0.00) + 12 specialized role Skills + deterministic tools
                      + bounded 3-attempt Smart Repair (target >= 95%, 100% critical security).

Computes paired Champion-Challenger sign test (local_before vs local_after), per-specialist scores
(target > 85%), and mandatory critical security gate (100%).
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
    benchmark_unseen_v3,
    context_engine,
    evolution_lab,
    ide_coordination,
    improvement_cycle,
    local_deterministic_tools,
    mentor_curriculum,
    ollama_native,
    provider_router,
    smart_repair,
)
from scripts.agents.intelligence import improvement

WORK_DIR = Path.home() / "Desktop" / "TEL99_BENCHMARK_120_STATE"
ART_DIR = WORK_DIR / "artifacts"
MEM_DIR = WORK_DIR / "memory"
SKILLS_DIR = ROOT / ".agents" / "skills"
LOCAL_MODEL = "gemma4:e4b-tel99-8k"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_atomic(path: Path, payload: dict) -> None:
    local_deterministic_tools.write_json_atomic_locked(path, payload)


def _call_groq_safe(model: str, *, system: str, prompt: str, response_format: str | None = None) -> tuple[str, dict]:
    ledger = provider_router.CloudBudgetLedger()
    ad = provider_router.OpenAICompatFreeCloudAdapter(
        provider="groq",
        model=model,
        timeout=60,
        max_tokens=1400,
        confidential=False,
        fallback_ollama_model=None,
        budget_ledger=ledger,
    )
    for retry in range(6):
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
            msg = str(exc).lower()
            if ("429" in msg or "cooldown" in msg) and retry < 5:
                st2 = ledger.status("groq")
                time.sleep(min(90.0, max(15.0, st2["cooldown_remaining_s"] + 2.0)))
                continue
            raise
    raise RuntimeError("Groq 429 retries exhausted")


def _summarize_phase(name: str, tasks: list[dict], results: list[dict], *, cloud_calls: int, duration_s: float) -> dict[str, Any]:
    task_map = {t["id"]: t for t in tasks}
    passed = sum(1 for r in results if r["ok"])
    fp = sum(1 for r in results if r["ok"] and r["attempts"] == 1)
    by_role = {}
    for role in benchmark_unseen_v3.ROLES_12:
        rr = [r for r in results if r["role"] == role]
        by_role[role] = {
            "passed": sum(1 for r in rr if r["ok"]),
            "total": len(rr),
            "rate": round(sum(1 for r in rr if r["ok"]) / max(1, len(rr)), 4),
        }
    sec_rows = [r for r in results if task_map[r["id"]].get("critical_security")]
    sec_passed = sum(1 for r in sec_rows if r["ok"])
    return {
        "phase": name,
        "cloud_calls": cloud_calls,
        "passed": passed,
        "total": len(results),
        "success_rate": round(passed / max(1, len(results)), 4),
        "first_pass": fp,
        "first_pass_rate": round(fp / max(1, len(results)), 4),
        "repaired": sum(1 for r in results if r.get("repaired")),
        "critical_security_passed": sec_passed,
        "critical_security_total": len(sec_rows),
        "critical_security_100pct": sec_passed == len(sec_rows) and len(sec_rows) > 0,
        "roles_above_85pct": sum(1 for v in by_role.values() if v["rate"] >= 0.85),
        "by_role": by_role,
        "duration_seconds": round(duration_s, 2),
        "results": results,
    }


def evaluate_local_phase(tasks: list[dict], *, upgraded: bool, ckpt_path: Path) -> dict[str, Any]:
    """Evaluate Unseen V3 strictly 100% LOCAL (ZERO cloud calls)."""
    phase_name = "local_after_transfer" if upgraded else "local_before_baseline"
    done: dict[str, dict] = {}
    if ckpt_path.is_file():
        try:
            for r in json.loads(ckpt_path.read_text(encoding="utf-8")).get("results") or []:
                done[r["id"]] = r
        except (OSError, ValueError):
            pass

    results: list[dict] = []
    t_all = time.monotonic()

    for task in tasks:
        tid = task["id"]
        if tid in done:
            results.append(done[tid])
            continue

        lessons: list[str] = []
        role_skill_card = ""
        if upgraded:
            hits = context_engine.HybridMemoryIndex(MEM_DIR).search(
                "tel99-bench", f"{task['role']} {task['objective']}", limit=2, verified_only=True, role=task["role"]
            )
            lessons = [f"{h['title']}: {h['body']}" for h in hits]
            role_skill_card = mentor_curriculum.load_role_skill_card(task["role"], skills_dir=SKILLS_DIR, max_chars=750)

        max_att = 3 if upgraded else 1
        attempts_log: list[dict] = []
        prior_hashes: list[str] = []
        last_out = ""
        prev_out = ""
        last_ver: dict[str, Any] = {"ok": False, "error": "not run", "passed": [], "failed": []}

        for att in range(1, max_att + 1):
            eng = ide_coordination.probe_local_engines()
            resident = LOCAL_MODEL in ((eng.get("ollama") or {}).get("loaded_models") or [])
            budget = ollama_native.compute_adaptive_budget(
                LOCAL_MODEL,
                task_profile="module" if upgraded else "patch",
                estimated_lines=55 if upgraded else 40,
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
            if not upgraded:
                sys_p = "Return ONLY clean Python 3 stdlib code (or JSON if requested)."
                usr_p = task["objective"]
            elif att == 1:
                sys_p = smart_repair.build_structured_reasoning_prompt(
                    role=f"tel99-{task['role']}",
                    objective=task["objective"],
                    constraints=[
                        "Python 3.12 stdlib only (or exact JSON object ONLY if JSON requested).",
                        "No eval/exec/__import__/shell=True.",
                        improvement_cycle._role_instruction_hint(task["role"]),
                        "ZERO docstrings, ZERO comments, ZERO if __name__=='__main__' example blocks (<= 30 lines total).",
                    ],
                )
                usr_p = task["objective"]
                if role_skill_card:
                    usr_p += f"\n\nSpecialized Skill (tel99-role-{task['role'].replace('_', '-')}):\n{role_skill_card}"
                if lessons:
                    usr_p += "\n\nVerified mentor lessons:\n- " + "\n- ".join(lessons[:2])
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
                            improvement_cycle._role_instruction_hint(task["role"]),
                            "ZERO docstrings, ZERO comments, ZERO example blocks (<= 30 lines).",
                        ],
                        prior_attempts=attempts_log,
                        memory_lessons=lessons[:2],
                        previous_diff=diff,
                    )
                )
            try:
                rf = "json" if (upgraded and task.get("kind") == "json") else None
                raw = provider.complete(system=sys_p, prompt=usr_p, response_format=rf)
                if upgraded:
                    if task.get("kind") == "json":
                        raw = local_deterministic_tools.extract_clean_json(raw)
                    else:
                        raw = local_deterministic_tools.strip_trailing_example_blocks(ollama_native.extract_code_block(raw))
                    sec_pre = local_deterministic_tools.deterministic_security_gate(raw, kind=task.get("kind", "python"))
                    if not sec_pre["ok"]:
                        ver = {"ok": False, "error": "; ".join(sec_pre["issues"]), "passed": [], "failed": ["security_precheck"]}
                    else:
                        ver = benchmark_unseen_v3.verify_unseen_output(task, sec_pre["cleaned"])
                else:
                    ver = benchmark_unseen_v3.verify_unseen_output(task, raw)
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
            "id": tid,
            "role": task["role"],
            "difficulty": task["difficulty"],
            "critical_security": bool(task.get("critical_security")),
            "ok": bool(last_ver["ok"]),
            "attempts": len(attempts_log),
            "repaired": bool(last_ver["ok"] and len(attempts_log) > 1),
            "cloud_calls": 0,
            "seconds": round(sum(a["seconds"] for a in attempts_log), 2),
            "error": last_ver.get("error"),
        }
        results.append(row)
        _write_atomic(ckpt_path, {"phase": phase_name, "completed": len(results), "total": len(tasks), "results": results})
        print(json.dumps({"v3": phase_name, "n": f"{len(results)}/{len(tasks)}", "id": tid, "role": task["role"], "ok": row["ok"], "att": row["attempts"], "s": row["seconds"], "err": row["error"]}), flush=True)

    ide_coordination.unload_ollama_models([LOCAL_MODEL])
    return _summarize_phase(phase_name, tasks, results, cloud_calls=0, duration_s=time.monotonic() - t_all)


def evaluate_hybrid_phase(tasks: list[dict], *, ckpt_path: Path) -> dict[str, Any]:
    """Evaluate Unseen V3 with Hybrid 3-Mentor Groq + 12 Specialized Skills + Deterministic Tools ($0.00)."""
    done: dict[str, dict] = {}
    if ckpt_path.is_file():
        try:
            for r in json.loads(ckpt_path.read_text(encoding="utf-8")).get("results") or []:
                done[r["id"]] = r
        except (OSError, ValueError):
            pass

    results: list[dict] = []
    t_all = time.monotonic()
    total_cloud_calls = 0

    for task in tasks:
        tid = task["id"]
        if tid in done:
            results.append(done[tid])
            total_cloud_calls += int(done[tid].get("cloud_calls") or 0)
            continue

        hits = context_engine.HybridMemoryIndex(MEM_DIR).search(
            "tel99-bench", f"{task['role']} {task['objective']}", limit=2, verified_only=True, role=task["role"]
        )
        lessons = [f"{h['title']}: {h['body']}" for h in hits]
        role_skill_card = mentor_curriculum.load_role_skill_card(task["role"], skills_dir=SKILLS_DIR, max_chars=750)

        chain = (
            ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
            if task["difficulty"] == "hard"
            else ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"]
        )
        attempts_log: list[dict] = []
        last_out = ""
        prev_out = ""
        last_ver: dict[str, Any] = {"ok": False, "error": "not run", "passed": [], "failed": []}

        for att in range(1, 4):
            mdl = chain[att - 1]
            t0 = time.monotonic()
            if att == 1:
                sys_p = smart_repair.build_structured_reasoning_prompt(
                    role=f"tel99-{task['role']}",
                    objective=task["objective"],
                    constraints=[
                        "Python 3.12 stdlib only (or exact JSON object ONLY if JSON requested).",
                        "No eval/exec/__import__/shell=True.",
                        improvement_cycle._role_instruction_hint(task["role"]),
                        "ZERO docstrings, ZERO comments, ZERO example blocks; output ONLY code or JSON.",
                    ],
                )
                usr_p = task["objective"]
                if role_skill_card:
                    usr_p += f"\n\nSpecialized Skill:\n{role_skill_card}"
                if lessons:
                    usr_p += "\n\nVerified mentor lessons:\n- " + "\n- ".join(lessons[:2])
            else:
                sys_p = "Return ONLY complete corrected Python 3.12 stdlib code (or exact JSON object) with ZERO prose/docstrings."
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
                            "Preserve exact signature, return keys, types, and edge-case ValueErrors.",
                        ],
                        prior_attempts=attempts_log,
                        memory_lessons=lessons[:2],
                        previous_diff=diff,
                    )
                )
            try:
                rf = "json" if task.get("kind") == "json" else None
                raw, _meta = _call_groq_safe(mdl, system=sys_p, prompt=usr_p, response_format=rf)
                total_cloud_calls += 1
                if task.get("kind") == "json":
                    raw = local_deterministic_tools.extract_clean_json(raw)
                else:
                    raw = local_deterministic_tools.strip_trailing_example_blocks(ollama_native.extract_code_block(raw))
                ver = benchmark_unseen_v3.verify_unseen_output(task, raw)
            except Exception as exc:
                raw = ""
                ver = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:160]}", "passed": [], "failed": ["infra"]}

            attempts_log.append({"attempt": att, "model": mdl, "seconds": round(time.monotonic() - t0, 2), "ok": bool(ver["ok"]), "error": ver.get("error")})
            prev_out = last_out
            last_out = raw
            last_ver = ver
            if ver["ok"]:
                break

        row = {
            "id": tid,
            "role": task["role"],
            "difficulty": task["difficulty"],
            "critical_security": bool(task.get("critical_security")),
            "ok": bool(last_ver["ok"]),
            "attempts": len(attempts_log),
            "repaired": bool(last_ver["ok"] and len(attempts_log) > 1),
            "model_used": attempts_log[-1]["model"],
            "cloud_calls": len(attempts_log),
            "seconds": round(sum(a["seconds"] for a in attempts_log), 2),
            "cost_usd": 0.0,
            "error": last_ver.get("error"),
        }
        results.append(row)
        _write_atomic(ckpt_path, {"phase": "hybrid_after_transfer", "completed": len(results), "total": len(tasks), "results": results})
        print(json.dumps({"v3": "hybrid_after", "n": f"{len(results)}/{len(tasks)}", "id": tid, "role": task["role"], "ok": row["ok"], "att": row["attempts"], "mdl": row["model_used"], "err": row["error"]}), flush=True)

    return _summarize_phase("hybrid_after_transfer", tasks, results, cloud_calls=total_cloud_calls, duration_s=time.monotonic() - t_all)


def _attach_paired_comparison(report: dict[str, Any], *, art_dir: Path) -> None:
    """Compute Champion-Challenger paired sign test & security promotion gate when both local phases exist."""
    if not (report.get("details_local_before") and report.get("details_local_after")):
        return
    b_map = {r["id"]: r for r in report["details_local_before"]}
    a_map = {r["id"]: r for r in report["details_local_after"]}
    paired = []
    for tid in b_map:
        if tid in a_map:
            paired.append(improvement.Outcome(task_id=tid, model_id="v3-local-before", success=b_map[tid]["ok"], tokens=0, seconds=b_map[tid]["seconds"], evidence=f"v3/{tid}"))
            paired.append(improvement.Outcome(task_id=tid, model_id="v3-local-after", success=a_map[tid]["ok"], tokens=0, seconds=a_map[tid]["seconds"], evidence=f"v3/{tid}"))
    if paired:
        report["champion_challenger_local"] = evolution_lab.run_champion_challenger(
            champion_id="v3-local-before",
            challenger_id="v3-local-after",
            champion_profile={"mode": "local_before", "cloud_calls": 0},
            challenger_profile={"mode": "local_after_12_role_skills_rag_tools_repair", "cloud_calls": 0},
            paired_outcomes=paired,
            store_dir=art_dir / "profiles_v3",
            owner_approved=False,
        )
        if report.get("local_before") and report.get("local_after"):
            report["delta_local_success_rate"] = round(
                report["local_after"]["success_rate"] - report["local_before"]["success_rate"], 4
            )
            report["promotion_blocked_security"] = not bool(report["local_after"].get("critical_security_100pct"))


def rebuild_unseen_v3_report_from_checkpoints(*, art_dir: Path = ART_DIR, per_role: int = 5) -> dict[str, Any]:
    """Deterministically reconcile `unseen_v3_report.json` from separate phase checkpoints under a file lock.

    Prevents concurrent phase runs (local_before/local_after/hybrid_after) from ever clobbering each other.
    """
    manifest = benchmark_unseen_v3.unseen_v3_manifest()
    tasks = benchmark_unseen_v3.get_tasks(per_role_limit=per_role)
    task_ids = {t["id"] for t in tasks}
    report_path = art_dir / "unseen_v3_report.json"

    def _load_ckpt(fname: str) -> list[dict[str, Any]]:
        p = art_dir / fname
        if not p.is_file():
            return []
        try:
            rows = json.loads(p.read_text(encoding="utf-8")).get("results") or []
            return [r for r in rows if isinstance(r, dict) and r.get("id") in task_ids]
        except (OSError, ValueError):
            return []

    lb_rows = _load_ckpt("ckpt_v3_local_before.json")
    la_rows = _load_ckpt("ckpt_v3_local_after.json")
    hy_rows = _load_ckpt("ckpt_v3_hybrid_after.json")

    def _merge(current: dict[str, Any]) -> dict[str, Any]:
        rep = dict(current)
        rep["schema_version"] = 1
        rep["evaluation_type"] = "INDEPENDENT_UNSEEN_V3_FROZEN_VALIDATION"
        rep["manifest"] = manifest
        rep["updated_at"] = _now_iso()

        if lb_rows and len(lb_rows) >= len(rep.get("details_local_before") or []):
            dur = sum(float(r.get("seconds") or 0.0) for r in lb_rows)
            s = _summarize_phase("local_before_baseline", tasks, lb_rows, cloud_calls=0, duration_s=dur)
            rep["local_before"] = {k: v for k, v in s.items() if k != "results"}
            rep["details_local_before"] = lb_rows
        if la_rows and len(la_rows) >= len(rep.get("details_local_after") or []):
            dur = sum(float(r.get("seconds") or 0.0) for r in la_rows)
            s = _summarize_phase("local_after_transfer", tasks, la_rows, cloud_calls=0, duration_s=dur)
            rep["local_after"] = {k: v for k, v in s.items() if k != "results"}
            rep["details_local_after"] = la_rows
        if hy_rows and len(hy_rows) >= len(rep.get("details_hybrid_after") or []):
            dur = sum(float(r.get("seconds") or 0.0) for r in hy_rows)
            cc = sum(int(r.get("cloud_calls") or 0) for r in hy_rows)
            s = _summarize_phase("hybrid_after_transfer", tasks, hy_rows, cloud_calls=cc, duration_s=dur)
            rep["hybrid_after"] = {k: v for k, v in s.items() if k != "results"}
            rep["details_hybrid_after"] = hy_rows

        _attach_paired_comparison(rep, art_dir=art_dir)
        return rep

    return local_deterministic_tools.locked_json_update(report_path, _merge)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", choices=["local_before", "local_after", "hybrid_after", "all"], default="all")
    ap.add_argument("--per-role", type=int, default=5, help="Tasks per role (default 5 => 60 total)")
    ap.add_argument("--rebuild-report", action="store_true", help="Reconcile unseen_v3_report.json from checkpoints under file lock")
    args = ap.parse_args(argv)

    manifest = benchmark_unseen_v3.unseen_v3_manifest()
    _write_atomic(ART_DIR / "unseen_v3_manifest_frozen.json", manifest)
    tasks = benchmark_unseen_v3.get_tasks(per_role_limit=args.per_role)

    if args.rebuild_report:
        report = rebuild_unseen_v3_report_from_checkpoints(art_dir=ART_DIR, per_role=args.per_role)
        print("UNSEEN_V3_REBUILT:", json.dumps({
            "seal_sha256": manifest["seal_sha256"],
            "local_before": report.get("local_before"),
            "local_after": report.get("local_after"),
            "hybrid_after": report.get("hybrid_after"),
            "delta_local_success_rate": report.get("delta_local_success_rate"),
            "promotion_blocked_security": report.get("promotion_blocked_security"),
        }, indent=2, ensure_ascii=False), flush=True)
        return 0

    report_path = ART_DIR / "unseen_v3_report.json"

    def _merge_phase(key: str, details_key: str, res: dict[str, Any]) -> dict[str, Any]:
        def _upd(cur: dict[str, Any]) -> dict[str, Any]:
            rep = dict(cur)
            rep["schema_version"] = 1
            rep["evaluation_type"] = "INDEPENDENT_UNSEEN_V3_FROZEN_VALIDATION"
            rep["manifest"] = manifest
            rep["updated_at"] = _now_iso()
            rep[key] = {k: v for k, v in res.items() if k != "results"}
            rep[details_key] = res["results"]
            _attach_paired_comparison(rep, art_dir=ART_DIR)
            return rep
        return local_deterministic_tools.locked_json_update(report_path, _upd)

    report: dict[str, Any] = {}
    if args.phase in ("local_before", "all"):
        res = evaluate_local_phase(tasks, upgraded=False, ckpt_path=ART_DIR / "ckpt_v3_local_before.json")
        report = _merge_phase("local_before", "details_local_before", res)

    if args.phase in ("local_after", "all"):
        res = evaluate_local_phase(tasks, upgraded=True, ckpt_path=ART_DIR / "ckpt_v3_local_after.json")
        report = _merge_phase("local_after", "details_local_after", res)

    if args.phase in ("hybrid_after", "all"):
        res = evaluate_hybrid_phase(tasks, ckpt_path=ART_DIR / "ckpt_v3_hybrid_after.json")
        report = _merge_phase("hybrid_after", "details_hybrid_after", res)

    print("UNSEEN_V3_SUMMARY:", json.dumps({
        "seal_sha256": manifest["seal_sha256"],
        "local_before": report.get("local_before"),
        "local_after": report.get("local_after"),
        "hybrid_after": report.get("hybrid_after"),
        "delta_local_success_rate": report.get("delta_local_success_rate"),
    }, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
