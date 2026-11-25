"""Unified local autonomous chain runner for TEL99 (reuses existing supervisor, CAS leases & launchers).

Chain: PREFLIGHT -> ENGINE COORDINATION -> RAM CONTROL -> AI RADAR -> ACADEMY (12 AGENTS)
       -> GENERALIZATION -> ENDURANCE -> FINAL REPORT.

Designed to run completely detached from Antigravity IDE / Gemini / Codex with zero cloud spend.
Never merges into main, never signs owner approvals, never executes trading orders.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agents.automation import ide_coordination, provider_router

DEFAULT_REPORT_DIR = Path.home() / "Desktop" / "TEL99_LOCAL_CHAIN_STATE"
AI_RADAR_DIR = Path.home() / "Desktop" / "AI_RADAR"
GENERALIZATION_DIR = Path.home() / "Desktop" / "TEL99_GENERALIZATION_CHECK"
LORA_DIR = Path.home() / "Desktop" / "TEL99-LORA"
ENDURANCE_DIR = Path.home() / "Desktop" / "TEL99_ENDURANCE_20261125_RUN2"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _check_pause_or_stop(state_dir: Path) -> str | None:
    if (state_dir / "stop.request").exists():
        return "STOPPED_BY_OPERATOR"
    while (state_dir / "pause.request").exists():
        if (state_dir / "stop.request").exists():
            return "STOPPED_BY_OPERATOR"
        time.sleep(2.0)
    return None


def _run_subprocess(cmd: list[str], *, cwd: Path, timeout: int, log_path: Path) -> dict:
    t0 = time.monotonic()
    env = provider_router.scrubbed_env()
    env["PYTHONUTF8"] = "1"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n=== [{_now_iso()}] RUN: {' '.join(cmd)} ===\n")
        fh.flush()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                env=env,
                stdout=fh,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
            rc = proc.returncode
            err = None
        except subprocess.TimeoutExpired:
            rc = 124
            err = f"timeout after {timeout}s"
    return {
        "exit_code": rc,
        "ok": rc == 0,
        "duration_seconds": round(time.monotonic() - t0, 2),
        "log": str(log_path),
        "error": err,
    }


def collect_results_summary(report_dir: Path = DEFAULT_REPORT_DIR) -> dict:
    """Read-only summary of all local TEL99 campaign artifacts."""
    def _load(p: Path):
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    ai_radar = _load(AI_RADAR_DIR / "artifacts" / "agent_campaign_report.json")
    passports = _load(AI_RADAR_DIR / "artifacts" / "agent_passports.json")
    academy = _load(AI_RADAR_DIR / "artifacts" / "academy_12_agents_report.json")
    gen = _load(GENERALIZATION_DIR / "artifacts" / "generalization_report.json")
    lora = _load(LORA_DIR / "ablation_ae_report.json")
    endurance = _load(ENDURANCE_DIR / "hour_campaign_report.json")
    chain = _load(report_dir / "local_chain_report.json")
    engines = ide_coordination.probe_local_engines()

    return {
        "checked_at": _now_iso(),
        "engines": engines,
        "local_chain": {
            "status": (chain or {}).get("status"),
            "steps": {k: v.get("status") for k, v in ((chain or {}).get("steps") or {}).items()},
        },
        "ai_radar": {
            "accepted": (ai_radar or {}).get("accepted_count"),
            "total": len((ai_radar or {}).get("runtime_statuses") or {}),
            "statuses": (ai_radar or {}).get("runtime_statuses"),
        },
        "academy_12_agents": {
            "evaluated_agents": (passports or {}).get("evaluated_agents"),
            "total_agents": (passports or {}).get("total_agents"),
            "levels": {
                p["identity"]["name"]: p["proven_level"]
                for p in ((passports or {}).get("passports") or [])
            },
            "upgraded_success_rate": ((academy or {}).get("upgraded") or {}).get("success_rate"),
            "baseline_success_rate": ((academy or {}).get("baseline") or {}).get("success_rate"),
        },
        "generalization": {
            "all_accepted": (gen or {}).get("all_accepted"),
            "missions": (gen or {}).get("missions"),
        },
        "tel99_lora_ablation": (lora or {}).get("summary"),
        "endurance": {
            "status": (endurance or {}).get("status"),
            "duration_minutes": (endurance or {}).get("duration_minutes"),
            "missions_accepted": (endurance or {}).get("missions_accepted"),
            "missions_total": (endurance or {}).get("missions_total"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--steps",
        default="preflight,ai_radar,academy,generalization,endurance",
        help="Comma-separated steps to run",
    )
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--endurance-minutes", type=float, default=60.0)
    parser.add_argument("--wait-for-pid", type=int, action="append", default=[], help="Wait for existing PIDs to exit cleanly before starting chain")
    parser.add_argument("--results", action="store_true", help="Print read-only consolidated results summary")
    args = parser.parse_args(argv)

    if args.results:
        print(json.dumps(collect_results_summary(args.report_dir), indent=2, ensure_ascii=False))
        return 0

    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "local_chain_report.json"
    steps_requested = [s.strip() for s in args.steps.split(",") if s.strip()]

    report = {
        "schema_version": 1,
        "started_at": _now_iso(),
        "status": "WAITING_DEPENDENCIES" if args.wait_for_pid else "RUNNING",
        "pid": os.getpid(),
        "waiting_for_pids": list(args.wait_for_pid),
        "steps_requested": steps_requested,
        "steps": {},
    }
    _write_atomic(report_path, report)

    # Automatic dependency-driven wait (never interrupts active campaigns; launches next stage immediately on exit)
    for dep_pid in args.wait_for_pid:
        while ide_coordination.is_pid_alive(dep_pid):
            if _check_pause_or_stop(report_dir):
                report["status"] = "STOPPED_BY_OPERATOR"
                report["finished_at"] = _now_iso()
                _write_atomic(report_path, report)
                return 0
            time.sleep(3.0)
    report["status"] = "RUNNING"
    report["dependencies_cleared_at"] = _now_iso()
    _write_atomic(report_path, report)

    py = sys.executable

    def _record_step(name: str, res: dict) -> None:
        report["steps"][name] = {
            **res,
            "status": "PROVEN" if res.get("ok") else "FAILED",
            "finished_at": _now_iso(),
        }
        _write_atomic(report_path, report)

    for step in steps_requested:
        sig = _check_pause_or_stop(report_dir)
        if sig:
            report["status"] = sig
            report["finished_at"] = _now_iso()
            _write_atomic(report_path, report)
            return 0

        if step == "preflight":
            reclaimed = ide_coordination.reclaim_orphan_leases(resource_id=None)
            eng = ide_coordination.probe_local_engines()
            if eng["llama_server"]["alive"] and not eng["llama_server"]["processing"]:
                ide_coordination.stop_idle_llama_server()
                eng = ide_coordination.probe_local_engines()
            ok = bool(eng["ollama"]["reachable"] and (eng["available_memory_mib"] or 0) >= ide_coordination.PRELOAD_MIN_FREE_MIB)
            _record_step("preflight", {"ok": ok, "reclaimed_orphans": len(reclaimed), "engines": eng})
            if not ok:
                report["status"] = "BLOCKED_PREFLIGHT"
                report["finished_at"] = _now_iso()
                _write_atomic(report_path, report)
                return 2
        elif step == "ai_radar":
            # Safely requeue radar-server if previously rejected before tuple-unpack/hybrid upgrade (never touches ACCEPTED)
            _run_subprocess(
                [
                    py, "-B", "-c",
                    (
                        "import sys, time; sys.path.insert(0, 'scripts/agents/automation'); "
                        "from pathlib import Path; from scripts.agents.automation.local_codex import exclusive; "
                        "from scripts.agents.protocol.store import FileStore; "
                        "camp = Path(r'C:\\Users\\sabri\\Desktop\\AI_RADAR\\state\\campaign-ai-radar'); "
                        "exec_lock = exclusive(camp / 'runtime.lock')\n"
                        "with exec_lock:\n"
                        "    st = FileStore(camp / 'ledger')\n"
                        "    for mid in ('radar-server', 'radar-ui-html', 'radar-ui-css', 'radar-ui-render', 'radar-ui-app', 'radar-doc'):\n"
                        "        old = st.read(f'kilo-local/{mid}')\n"
                        "        if old and old.get('status') in ('REJECTED', 'BLOCKED'):\n"
                        "            hist = list(old.get('infra_recovery_history') or [])\n"
                        "            hist.append({'recovered_at': time.time(), 'previous_status': old['status'], 'recovery_reason': 'auto_chain_hybrid_resume'})\n"
                        "            upd = {**old, 'status': 'ACK', 'execution_status': 'NOT_STARTED', 'at': time.time(), 'infra_recovery_history': hist}\n"
                        "            upd.pop('result', None); upd.pop('verification', None)\n"
                        "            st.put_cas(f'kilo-local/{mid}', upd, old)\n"
                    ),
                ],
                cwd=ROOT,
                timeout=30,
                log_path=report_dir / "ai_radar.log",
            )
            script = AI_RADAR_DIR / "run_ai_radar_campaign.py"
            res = _run_subprocess([py, "-B", str(script)], cwd=AI_RADAR_DIR, timeout=2400, log_path=report_dir / "ai_radar.log")
            _record_step("ai_radar", res)
        elif step == "academy":
            script = AI_RADAR_DIR / "run_academy_eval.py"
            res = _run_subprocess([py, "-B", str(script)], cwd=AI_RADAR_DIR, timeout=3000, log_path=report_dir / "academy.log")
            _record_step("academy", res)
        elif step == "generalization":
            script = GENERALIZATION_DIR / "run_generalization_check.py"
            res = _run_subprocess([py, "-B", str(script)], cwd=GENERALIZATION_DIR, timeout=1200, log_path=report_dir / "generalization.log")
            _record_step("generalization", res)
        elif step == "lora":
            script = LORA_DIR / "run_ablation_ae.py"
            res = _run_subprocess([py, "-B", str(script)], cwd=LORA_DIR, timeout=3600, log_path=report_dir / "lora_ablation.log")
            _record_step("lora", res)
        elif step == "bench120":
            res = _run_subprocess(
                [py, "-B", "-m", "scripts.agents.automation.improvement_cycle"],
                cwd=ROOT,
                timeout=7200,
                log_path=report_dir / "bench120.log",
            )
            _record_step("bench120", res)
        elif step == "transfer":
            res = _run_subprocess(
                [py, "-B", "-m", "scripts.agents.automation.cloud_to_local_transfer"],
                cwd=ROOT,
                timeout=3600,
                log_path=report_dir / "cloud_to_local_transfer.log",
            )
            _record_step("transfer", res)
        elif step == "lora_corpus":
            res = _run_subprocess(
                [
                    py, "-B", "-c",
                    (
                        "import json; from pathlib import Path; "
                        "from scripts.agents.automation import benchmark_suite_100, lora_corpus_builder; "
                        "ho = {t['id'] for t in benchmark_suite_100.get_split('held_out_final')}; "
                        "audit = lora_corpus_builder.audit_lora_artifacts(r'C:\\Users\\sabri\\Desktop\\TEL99-LORA'); "
                        "tfiles = [Path(r'C:\\Users\\sabri\\Desktop\\AI_RADAR\\artifacts\\trajectories.jsonl'), "
                        "Path(r'C:\\Users\\sabri\\Desktop\\TEL99_GENERALIZATION_CHECK\\artifacts\\trajectories.jsonl'), "
                        "Path(r'C:\\Users\\sabri\\Desktop\\TEL99_BENCHMARK_120_STATE\\artifacts\\trajectories.jsonl')]; "
                        "corp = lora_corpus_builder.build_verified_trajectory_corpus(tfiles, r'C:\\Users\\sabri\\Desktop\\TEL99-LORA\\verified_sft_corpus_v2.jsonl', excluded_task_ids=ho); "
                        "out = {'audit': audit, 'corpus': corp}; "
                        "Path(r'C:\\Users\\sabri\\Desktop\\TEL99-LORA\\lora_forensic_and_corpus_report.json').write_text(json.dumps(out, indent=2, ensure_ascii=False)+'\\n', encoding='utf-8'); "
                        "print(json.dumps(corp, indent=2))"
                    ),
                ],
                cwd=ROOT,
                timeout=120,
                log_path=report_dir / "lora_corpus.log",
            )
            _record_step("lora_corpus", res)
        elif step == "endurance":
            end_run3 = Path.home() / "Desktop" / "TEL99_ENDURANCE_20261125_RUN3"
            script = ROOT / "tests" / "run_hour_autonomy_acceptance.py"
            res = _run_subprocess(
                [
                    py, "-B", str(script),
                    "--min-minutes", str(args.endurance_minutes),
                    "--state-root", str(end_run3 / "hour_campaign"),
                    "--report", str(end_run3 / "hour_campaign_report.json"),
                ],
                cwd=ROOT,
                timeout=int(args.endurance_minutes * 60 + 900),
                log_path=report_dir / "endurance.log",
            )
            _record_step("endurance", res)
        else:
            _record_step(step, {"ok": False, "error": f"unknown step {step!r}"})

    ide_coordination.unload_ollama_models()
    all_ok = all(v.get("ok") for v in report["steps"].values())
    report["status"] = "COMPLETED" if all_ok else "COMPLETED_WITH_FAILURES"
    report["finished_at"] = _now_iso()
    report["summary"] = collect_results_summary(report_dir)
    _write_atomic(report_path, report)
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
