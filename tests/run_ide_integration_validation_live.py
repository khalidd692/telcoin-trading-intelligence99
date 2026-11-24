"""Isolated live end-to-end validation for Antigravity IDE integration (Ollama + Docker + CAS leases).

Runs strictly inside a temporary directory with zero GitHub writes and never
touches historical issues (#205/#206/#207) or TEL99_ANTIGRAVITY_AUTOFEED_20261124_STATE.
"""
from __future__ import annotations

import hashlib
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agents import specialist_dispatch
from scripts.agents.automation import (
    env_doctor,
    ide_coordination,
    learning_loop,
    local_codegen,
    local_model_routing,
    local_team,
    mission_planner,
    multi_cockpit,
    provider_router,
    recovery_tool,
)
from scripts.agents.automation.autonomy_runtime import Runtime, seal
from scripts.agents.intelligence.memory import MemoryStore

BASE_SHA = "934d9fd8a3fd498c6e3e69226007dd46276aa6da"
BASE_REF = "agents/tel99-code-base-autofeed-20261124"


def _wait_for_ollama_idle(timeout: float = 30.0) -> None:
    """Wait until Ollama finishes unloading resident models and free RAM >= 1024 MiB."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        models = None
        conn = HTTPConnection("127.0.0.1", 11434, timeout=2)
        try:
            conn.request("GET", "/api/ps")
            resp = conn.getresponse()
            if resp.status == 200:
                payload = json.loads(resp.read(32_768))
                models = payload.get("models") if isinstance(payload, dict) else []
        except (OSError, ValueError):
            models = None
        finally:
            conn.close()
        avail = local_model_routing.available_memory_mib()
        if models == [] and avail is not None and avail >= local_model_routing.AVAILABLE_MEMORY_RESERVE_MIB:
            return
        time.sleep(1.0)


def main() -> int:
    started = time.monotonic()
    report: dict = {"schema_version": 1, "base_sha": BASE_SHA, "proofs": {}}

    # 1. Doctor & live providers (Ollama + agy resolved)
    _wait_for_ollama_idle()
    doctor = env_doctor.diagnose(auto_feed=True, include_providers=True)
    if not doctor["ready"]:
        raise RuntimeError(f"Environment not ready: {doctor['blockers']}")
    providers_inv = provider_router.probe_all_providers()
    assert providers_inv["providers"]["ollama"]["available"] is True
    assert providers_inv["providers"]["agy"]["installed"] is True

    # 2. On-demand mobilization of 12 specialists (bounded <= 4)
    selected = specialist_dispatch.select_specialists(
        "security lease check and Python function repair verification",
        include_verifier=True,
        max_specialists=3,
    )
    assert len(selected) == 3
    assert any(not row["active"] for row in selected), "Expected at least one reserved specialist mobilized"

    with tempfile.TemporaryDirectory(prefix="tel99-ide-live-") as tmp:
        root = Path(tmp)

        # 3. CAS lease coordination proof (antigravity-ide vs codex-cli)
        lease = ide_coordination.acquire_lease(
            root,
            actor="antigravity-ide",
            resource_id="mission:val-ide-20261124-branch-protected",
            branch=BASE_REF,
            paths=["scripts/agents/automation/policy.py"],
            ttl_seconds=600,
        )
        conflict_blocked = False
        try:
            ide_coordination.acquire_lease(
                root,
                actor="codex-cli",
                resource_id="mission:concurrent-codex",
                branch=BASE_REF,
                paths=["scripts/agents/automation/policy.py"],
                ttl_seconds=600,
            )
        except ide_coordination.LeaseConflict:
            conflict_blocked = True
        assert conflict_blocked, "Expected LeaseConflict for concurrent codex-cli"

        # 4. Plan & execute fresh isolated mission via real Ollama + Docker
        goal_spec = {
            "goal": "Validate branch protection normalization cleanly",
            "base_sha": BASE_SHA,
            "base_ref": BASE_REF,
            "tasks": [
                {
                    "id": "val-ide-20261124-branch-protected",
                    "dependencies": [],
                    "path": "scripts/agents/automation/policy.py",
                    "function": "branch_is_protected",
                    "objective": (
                        "Check protected branches safely even when prefixed with 'refs/heads/' or using uppercase letters "
                        "(for example 'refs/heads/main' or 'MAIN' or 'Tel99-live-data'). Strip whitespace, remove an optional "
                        "'refs/heads/' prefix, and check case-insensitively against PROTECTED_BRANCHES and PROTECTED_PREFIXES. "
                        "Preserve the exact function signature and all module constants."
                    ),
                    "test": (
                        "import runpy\n"
                        "prot = runpy.run_path('/work/program.py')['branch_is_protected']\n"
                        "assert prot('main') is True  # case: main | expected: main is protected.\n"
                        "assert prot('refs/heads/main') is True  # case: refs-heads-main | expected: refs/heads/main is protected.\n"
                        "assert prot('MAIN') is True  # case: uppercase-main | expected: Case-insensitive main is protected.\n"
                        "assert prot('refs/heads/TEL99-live-data') is True  # case: prefixed-tel99 | expected: Prefixed tel99- branch is protected.\n"
                        "assert prot('agents/tel99-work') is False  # case: work-branch | expected: Isolated agent work branch is allowed.\n"
                    ),
                },
            ],
        }
        plan = mission_planner.plan_from_goal(
            goal_spec, state_root=root, verify_baseline=True, inventory=providers_inv,
        )
        assert plan["baseline_checks"]["val-ide-20261124-branch-protected"]["baseline_red"] is True

        camp_root = root / "campaign-290"
        shared_mem = root / "learning" / "memory"
        rt = Runtime(camp_root, shared_memory_root=shared_mem)
        missions = plan["local_registry"]["missions"]
        approvals = plan["local_registry"]["approvals"]
        rt.run_queue(missions, approvals)
        m_state = rt.state(missions[0])
        assert m_state.get("status") == "ACCEPTED", m_state
        chain_statuses = {missions[0]["id"]: m_state["status"]}

        # 5. Real auto-repair + learning memory capitalization & recall proof
        repair_mission = {
            **missions[0],
            "id": "val-ide-20261124-repair-proof",
            "max_attempts": 2,
        }
        repair_dir = root / "repair-live"
        repair_rt = Runtime(repair_dir, shared_memory_root=shared_mem)
        broken_code = (
            "def branch_is_protected(branch: str) -> bool:\n"
            "    if not isinstance(branch, str) or not branch.strip():\n"
            "        return True\n"
            "    b = branch.strip()\n"
            "    if b.startswith('refs/heads/'):\n"
            "        b = b[len('refs/heads/'):]\n"
            "    return b in PROTECTED_BRANCHES or b.startswith(PROTECTED_PREFIXES)\n"
        )
        seed_note = "Initial review: check whitespace strip and case normalization."
        seed_analysis = {
            "role": "tel99-analyst",
            "model": local_team.ANALYST_MODEL,
            "kind": "read-only-advice",
            "analysis": seed_note,
            "sha256": local_team._hash(seed_note),
        }
        broken_trace = local_team.trace(
            seed_analysis,
            developer_model=repair_mission["model"],
            artifact=broken_code,
        )
        broken_result = {
            "artifact": broken_code,
            "sha256": hashlib.sha256(broken_code.encode("utf-8")).hexdigest(),
            "specialist_id": "tel99-dev",
            "provider": local_codegen.PROVIDER,
            "model": repair_mission["model"],
            "generation_seconds": 1.0,
            "agent_trace": broken_trace,
        }
        repair_rt.claim(repair_mission)
        repair_rt.inbox.receive({"request_id": repair_mission["id"]})
        repair_rt.save(repair_mission, "WORKER_EXITED", attempt=1, result=broken_result)
        _wait_for_ollama_idle()
        repair_rt.run_queue([repair_mission], seal([repair_mission]))
        repair_state = repair_rt.state(repair_mission)
        assert repair_state["status"] == "ACCEPTED", repair_state
        assert repair_state["attempt"] == 2 and len(repair_state["attempt_history"]) == 1

        metrics = learning_loop.sync_measured_quality(root)
        mem_entries = MemoryStore(shared_mem).all_entries("tel99", include_common=False)
        recalled = learning_loop.retrieve_lessons(shared_mem, "tel99", repair_mission)
        assert any(e.kind == "fix" and e.verified for e in mem_entries)
        assert any(e.kind == "procedure" and e.verified for e in mem_entries)
        assert len(recalled) >= 1

        # 6. Brutal crash recovery without replay
        crash_dir = root / "crash-live"
        crash_script = (
            "import os, sys\n"
            "from scripts.agents.automation.autonomy_runtime import Runtime, seal\n"
            "from tests.test_autonomy_runtime import mission\n"
            "m = mission('VAL-IDE-CRASH-1')\n"
            "Runtime(sys.argv[1], executor=lambda _m: os._exit(55)).run_queue([m], seal([m]))\n"
        )
        proc = subprocess.run(
            [sys.executable, "-B", "-c", crash_script, str(crash_dir)],
            cwd=ROOT, capture_output=True, timeout=20, check=False,
        )
        assert proc.returncode == 55
        replay_calls = []
        crash_rt = Runtime(crash_dir, executor=lambda t: replay_calls.append(t["id"]))
        from tests.test_autonomy_runtime import mission as synth_mission
        cm = synth_mission("VAL-IDE-CRASH-1")
        crash_rt.run_queue([cm], seal([cm]))
        assert replay_calls == []
        assert crash_rt.state(cm)["status"] == "AWAITING_HUMAN"

        camp_crash = root / "campaign-999"
        crash_dir.replace(camp_crash)
        rec = recovery_tool.inspect_state(root)
        assert len(rec["awaiting_human"]) == 1

        # 7. Cockpit snapshot verification (while lease is active, then released)
        srv = multi_cockpit.make_server(root, port=0, allow_controls=True, include_providers=False)
        thr = threading.Thread(target=srv.serve_forever, args=(0.02,), daemon=True)
        thr.start()
        try:
            host_hdr = f"127.0.0.1:{srv.server_port}"
            conn = HTTPConnection("127.0.0.1", srv.server_port, timeout=3)
            conn.request("GET", "/api/snapshot.json", headers={"Host": host_hdr})
            snap = json.loads(conn.getresponse().read().decode("utf-8"))
            conn.close()
            assert snap["team_catalog"]["total"] == 12
            assert len(snap["coordination"]["active"]) == 1
        finally:
            srv.shutdown()
            thr.join(timeout=2)
            srv.server_close()

        rel = ide_coordination.release_lease(root, lease["lease_id"], actor="antigravity-ide")
        assert rel["released"] is True

        report["proofs"] = {
            "doctor_ready": doctor["ready"],
            "agy_installed": providers_inv["providers"]["agy"]["installed"],
            "agy_version": providers_inv["providers"]["agy"].get("version"),
            "specialists_mobilized": [row["name"] for row in selected],
            "lease_conflict_blocked_codex": conflict_blocked,
            "lease_released": rel["released"],
            "fresh_mission": {
                "chain_statuses": chain_statuses,
                "baseline_red": True,
                "status": m_state["status"],
                "checks": len((m_state.get("verification") or {}).get("checks", [])),
            },
            "repair_mission": {
                "id": repair_mission["id"],
                "status": repair_state["status"],
                "attempts": repair_state["attempt"],
                "recalled_lessons": recalled,
                "memory_entries_count": len(mem_entries),
            },
            "crash_recovery": {
                "crash_exit_code": proc.returncode,
                "replayed_workers": len(replay_calls),
                "post_crash_status": "AWAITING_HUMAN",
            },
            "measured_quality": metrics["measured_quality"],
        }

    report["duration_seconds"] = round(time.monotonic() - started, 3)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
