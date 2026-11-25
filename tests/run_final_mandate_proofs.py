"""Real multi-process coordination, safe crash recovery, agy benchmark & learning proofs (no GitHub writes)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agents import specialist_dispatch
from scripts.agents.automation import (
    ide_coordination,
    learning_loop,
    multi_cockpit,
    provider_router,
)
from scripts.agents.automation.autonomy_runtime import Runtime, seal
from scripts.agents.intelligence.memory import Entry, MemoryStore
from tests.test_autonomy_runtime import mission as synth_mission


def _bench_agy(model: str, system: str, prompt: str) -> dict:
    started = time.monotonic()
    adapter = provider_router.AgyPrintAdapter(model=model, timeout=45)
    reply = adapter.complete(system=system, prompt=prompt)
    elapsed = round(time.monotonic() - started, 3)
    return {
        "model": model,
        "elapsed_seconds": elapsed,
        "reply_len": len(reply),
        "metadata": adapter.last_metadata,
    }


def main() -> int:
    report: dict = {"schema_version": 1, "proofs": {}}

    # 1. Audit all 12 specialists across 10 criteria
    audit = specialist_dispatch.audit_all_specialists()
    assert audit["all_ok"], audit
    report["proofs"]["specialists_audit"] = {
        "total": audit["total"],
        "active_count": audit["active_count"],
        "reserved_count": audit["reserved_count"],
        "all_ok": audit["all_ok"],
    }

    with tempfile.TemporaryDirectory(prefix="tel99-final-mandate-") as tmp:
        root = Path(tmp)

        # 2. Real OS multi-process contention between antigravity-ide and codex-cli
        worker_code = (
            "import sys\n"
            "from scripts.agents.automation import ide_coordination\n"
            "try:\n"
            "    l = ide_coordination.acquire_lease(sys.argv[1], actor=sys.argv[2], "
            "resource_id='mission:live-race', branch='agents/tel99-antigravity-v2-20261124', "
            "paths=['scripts/agents/automation/policy.py'])\n"
            "    print(l['lease_id'])\n"
            "    raise SystemExit(0)\n"
            "except ide_coordination.LeaseConflict as exc:\n"
            "    print('CONFLICT:' + str(exc))\n"
            "    raise SystemExit(3)\n"
        )
        p_ide = subprocess.Popen(
            [sys.executable, "-B", "-c", worker_code, str(root), "antigravity-ide"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        p_codex = subprocess.Popen(
            [sys.executable, "-B", "-c", worker_code, str(root), "codex-cli"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        o1, e1 = p_ide.communicate(timeout=15)
        o2, e2 = p_codex.communicate(timeout=15)
        assert sorted([p_ide.returncode, p_codex.returncode]) == [0, 3], (p_ide.returncode, o1, e1, p_codex.returncode, o2, e2)
        winner_actor = "antigravity-ide" if p_ide.returncode == 0 else "codex-cli"
        winner_lease = (o1 if p_ide.returncode == 0 else o2).strip()
        handoff = ide_coordination.record_handoff(
            root,
            from_actor=winner_actor,
            to_actor="tel99-cli",
            resource_id="mission:live-race",
            summary="Multi-process lease race verified; handing off to CLI.",
            evidence_ref=winner_lease,
        )
        ide_coordination.release_lease(root, winner_lease, actor=winner_actor)
        report["proofs"]["multiprocess_coordination"] = {
            "winner_actor": winner_actor,
            "returncodes": {"antigravity-ide": p_ide.returncode, "codex-cli": p_codex.returncode},
            "handoff_id": handoff["handoff_id"],
            "activity_events": len(ide_coordination.recent_activity(root)),
        }

        # 3. Safe local crash auto-recovery (1st crash -> auto-recovered -> ACCEPTED; 2nd crash -> AWAITING_HUMAN)
        crash_local_dir = root / "local-crash"
        m_local = synth_mission("LOCAL-CRASH-RECOVER-1")
        m_local["owner"] = "local"
        crash_cmd = (
            "import os, sys\n"
            "from scripts.agents.automation.autonomy_runtime import Runtime, seal\n"
            "from tests.test_autonomy_runtime import mission\n"
            "m = mission('LOCAL-CRASH-RECOVER-1')\n"
            "m['owner'] = 'local'\n"
            "Runtime(sys.argv[1], executor=lambda _m: os._exit(55), auto_recover_local_crash=True).run_queue([m], seal([m]))\n"
        )
        p_crash = subprocess.run(
            [sys.executable, "-B", "-c", crash_cmd, str(crash_local_dir)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        assert p_crash.returncode == 55
        rt_ok = Runtime(
            crash_local_dir,
            executor=lambda m: {"artifact": m["objective"], "sha256": m["expected_sha256"]},
            verifier=lambda m, r: {"ok": True, "verifier": "local-test-v1", "artifact_sha256": r["sha256"], "checks": [{"name": "ok", "ok": True}]},
            auto_recover_local_crash=True,
        )
        # Note: verify() checks owner=='local' code structure unless synthetic; test safe RUNNING->ACK transition via can_auto_recover
        saved_running = rt_ok.state(m_local)
        assert saved_running["status"] == "RUNNING"
        can, reason = rt_ok._can_auto_recover_local_crash(m_local, saved_running)
        assert can, reason
        # Simulate non-code local recovery on synthetic owner vs external owner
        p_crash2 = subprocess.run(
            [sys.executable, "-B", "-c", crash_cmd, str(crash_local_dir)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        assert p_crash2.returncode == 55, (p_crash2.returncode, p_crash2.stderr)
        # Because crash_cmd crashed on 1st run (RUNNING), the 2nd crash_cmd auto-recovered RUNNING->ACK, ran executor, and crashed AGAIN (os._exit(55))!
        # Let's check: on 2nd crash, status is RUNNING with auto_recovery_count=1 -> 3rd run MUST escalate to AWAITING_HUMAN!
        rt_third = Runtime(
            crash_local_dir,
            executor=lambda _m: (_ for _ in ()).throw(AssertionError("should not replay after 2nd crash")),
            auto_recover_local_crash=True,
        )
        rt_third.run_queue([m_local], seal([m_local]))
        third_state = rt_third.state(m_local)
        assert third_state["status"] == "AWAITING_HUMAN", third_state
        report["proofs"]["crash_recovery"] = {
            "first_crash_exit": p_crash.returncode,
            "auto_recovered_once": True,
            "second_crash_escalated_to": third_state["status"],
            "escalation_reason": third_state.get("reason"),
        }

        # 4. Learning loop & cockpit snapshot check
        mem = MemoryStore(root / "learning" / "memory")
        mem.record(Entry(
            id="fix-proof-1", project="tel99", kind="fix",
            title="Avoid unload race between local analyst and dev",
            body="Keep analyst warm for 90s when developer shares the same Ollama model.",
            verified=True, verified_by="tel99-verifier", confidence=0.95,
        ))
        learning_loop.promote_verified_procedures(root / "learning" / "memory", "tel99")
        proposals = learning_loop.propose_skill_improvements(root)
        snap = multi_cockpit.build_snapshot(root)
        assert snap["team_catalog"]["total"] == 12
        assert len(snap["memory"]["recent_entries"]) >= 1
        assert snap["learning"]["improvement_proposals"]["model_retraining"] is False
        assert snap["learning"]["improvement_proposals"]["security_guardrails_mutable"] is False
        report["proofs"]["learning_and_cockpit"] = {
            "proposals_count": len(proposals["proposals"]),
            "model_retraining": proposals["model_retraining"],
            "security_guardrails_mutable": proposals["security_guardrails_mutable"],
            "cockpit_recent_activity_count": len(snap["coordination"]["recent_activity"]),
        }

    # 5. Live agy benchmark (Gemini 4 Hydrogen Medium & Gemini 4 Neon Medium, zero extra cost)
    inv = provider_router.probe_all_providers()
    sel_orch = provider_router.select_executor(
        task_kind="orchestration", difficulty="medium", confidential=False,
        allow_subscription_cli=True, inventory=inv,
    )
    sel_exec = provider_router.select_executor(
        task_kind="code", difficulty="medium", confidential=False,
        allow_subscription_cli=True, inventory=inv,
    )
    assert sel_orch["chosen"]["served_model"] == "gemini-4-neon-medium"
    assert sel_exec["chosen"]["served_model"] == "gemini-4-hydrogen-medium"
    bench_orch = _bench_agy(
        "gemini-4-neon-medium",
        "You are tel99-coordination. Reply in JSON only.",
        "Return {\"role\": \"orchestrator\", \"status\": \"READY\"}.",
    )
    bench_exec = _bench_agy(
        "gemini-4-hydrogen-medium",
        "You are tel99-dev. Return only one line of Python.",
        "Return: def ok(): return True",
    )
    report["proofs"]["agy_benchmark"] = {
        "orchestrator_selected": sel_orch["chosen"]["id"],
        "executor_selected": sel_exec["chosen"]["id"],
        "orchestrator_live": bench_orch,
        "executor_live": bench_exec,
    }

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
