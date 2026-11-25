"""Live final acceptance suite for TEL99 (real Ollama, Docker, crash recovery, cockpit & router).

Runs in an isolated temporary directory outside the repository. Never alters
historical GitHub issues (#205/#206/#207) or historical state ledgers, and
performs zero GitHub writes.
"""
from __future__ import annotations

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

from scripts.agents.automation import (
    env_doctor,
    learning_loop,
    local_codegen,
    local_team,
    mission_planner,
    multi_cockpit,
    proposal_builder,
    provider_router,
    recovery_tool,
)
from scripts.agents.automation.autonomy_runtime import Runtime, seal
from scripts.agents.automation.env_doctor import DEFAULT_SANDBOX_IMAGE
from scripts.agents.intelligence.memory import MemoryStore

BASE_SHA = "934d9fd8a3fd498c6e3e69226007dd46276aa6da"
BASE_REF = "agents/tel99-code-base-autofeed-20261124"


def main() -> int:
    started = time.monotonic()
    report: dict = {"schema_version": 1, "base_sha": BASE_SHA, "proofs": {}}

    # 1. Doctor + live multi-provider probe
    doctor = env_doctor.diagnose(auto_feed=True, include_providers=True)
    if not doctor["ready"]:
        raise RuntimeError(f"Environment not ready: {doctor['blockers']}")
    providers_inv = provider_router.probe_all_providers()
    route_confidential = provider_router.select_executor(
        task_kind="code", difficulty="medium", confidential=True,
        allow_subscription_cli=True, inventory=providers_inv,
    )
    route_nonconf = provider_router.select_executor(
        task_kind="code", difficulty="medium", confidential=False,
        allow_subscription_cli=False, inventory=providers_inv,
    )
    assert route_confidential["ok"] and route_confidential["chosen"]["provider"] == "ollama"
    assert route_nonconf["ok"]
    report["proofs"]["providers_and_doctor"] = {
        "doctor_ready": doctor["ready"],
        "autofeed_controllers": doctor["checks"]["autofeed"]["controllers"],
        "providers": {
            name: {
                "billing_class": p["billing_class"],
                "quota_status": p["quota_status"],
                "available": p["available"],
                "models_count": len(p.get("models", [])),
            }
            for name, p in providers_inv["providers"].items()
        },
        "selected_confidential": route_confidential["chosen"]["id"],
        "selected_non_confidential_no_opt_in": route_nonconf["chosen"]["id"],
    }

    # 2. Goal decomposition + baseline-red Docker check + 3-mission live Ollama/Docker chain
    goal_spec = {
        "goal": "Fix three TEL99 helpers cleanly with independent Docker tests",
        "base_sha": BASE_SHA,
        "base_ref": BASE_REF,
        "controller_issue": 260,
        "mandate_comment_id": 900001,
        "expires_at": "2026-12-20T23:59:59Z",
        "tasks": [
            {
                "id": "live-m1-tool-names",
                "issue": 261,
                "dependencies": [],
                "path": "scripts/agents/automation/verify_runtime.py",
                "function": "tool_names",
                "objective": (
                    "Keep only non-empty string tool names (ignoring whitespace-only strings via .strip()) "
                    "from strings or dictionaries when reading persisted agent metadata. Ignore blank strings, "
                    "numeric dictionary names and non-list roots without changing the order of real tool names. "
                    "Preserve the existing function signature, imports and all other code."
                ),
                "test": (
                    "import runpy\n"
                    "read = runpy.run_path('/work/program.py')['tool_names']\n"
                    "assert read(['terminal', {'name':'read'}, 'git']) == ['terminal','read','git']  # case: normal-tools | expected: Valid names keep their order.\n"
                    "assert read('terminal') == []  # case: invalid-root | expected: Non-list roots give no names.\n"
                    "assert read(['  ', {'name':3}, {'name':''}, None, 'git', {'name':'read'}]) == ['git','read']  # case: malformed-names | expected: Empty and blank tool names are ignored.\n"
                ),
            },
            {
                "id": "live-m2-dedup-key",
                "issue": 262,
                "dependencies": ["live-m1-tool-names"],
                "path": "scripts/agents/automation/pilot_recipe.py",
                "function": "dedup_key",
                "objective": (
                    "Normalize runs of whitespace in mission titles when computing a deduplication key. "
                    "Titles with the same words and differing internal spaces or tabs must receive the same digest, "
                    "while differing repository names or issue numbers must still differ. "
                    "Keep the exact function signature and existing hashlib import. Modify only dedup_key."
                ),
                "test": (
                    "import runpy\n"
                    "key = runpy.run_path('/work/program.py')['dedup_key']\n"
                    "assert key('sample/repo',12,' TASK ') == key('sample/repo',12,'task')  # case: existing-normalization | expected: Boundary spaces normalized.\n"
                    "assert key('sample/repo',12,'Fix   Parser') == key('sample/repo',12,' fix parser ')  # case: internal-spaces | expected: Repeated spaces normalized.\n"
                    "assert key('sample/repo',12,'fix parser') == key('sample/repo',12,'fix\\tparser')  # case: tab-run | expected: Tabs and spaces normalize equally.\n"
                    "assert key('sample/repo',12,'fix parser') != key('sample/repo',13,'fix parser')  # case: issue-boundary | expected: Distinct issue keeps distinct key.\n"
                ),
            },
            {
                "id": "live-m3-branch-protected",
                "issue": 263,
                "dependencies": ["live-m2-dedup-key"],
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

    with tempfile.TemporaryDirectory(prefix="tel99-final-live-") as tmp:
        root = Path(tmp)
        plan = mission_planner.plan_from_goal(
            goal_spec, state_root=root, verify_baseline=True, inventory=providers_inv,
        )
        assert plan["execution_order"] == [
            "live-m1-tool-names", "live-m2-dedup-key", "live-m3-branch-protected",
        ]
        assert plan["github_proposal"] is not None
        assert plan["github_proposal"]["github_writes_performed"] == 0

        # Run the 3-mission chain with real Ollama + Docker + shared memory
        camp_root = root / "campaign-260"
        shared_mem = root / "learning" / "memory"
        rt = Runtime(camp_root, shared_memory_root=shared_mem)
        missions = plan["local_registry"]["missions"]
        approvals = plan["local_registry"]["approvals"]
        rt.run_queue(missions, approvals)
        chain_statuses = {m["id"]: rt.state(m).get("status") for m in missions}
        assert all(st == "ACCEPTED" for st in chain_statuses.values()), chain_statuses

        # 3. Real auto-repair proof: seed attempt 1 failure -> Docker rejects -> real Ollama repairs on attempt 2 -> Docker accepts
        repair_mission = {**missions[0], "id": "live-repair-proof"}
        repair_dir = root / "repair-live"
        repair_rt = Runtime(repair_dir, shared_memory_root=shared_mem)
        broken_code = (
            "def tool_names(tools) -> list[str]:\n"
            "    if isinstance(tools, list):\n"
            "        return [x for x in tools if isinstance(x, str) and x]\n"
            "    return []\n"
        )
        broken_trace = local_team.trace(
            local_team.analyze(repair_mission, "def tool_names(tools):\n    return []\n"),
            developer_model=repair_mission["model"],
            artifact=broken_code,
        )
        import hashlib
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
        repair_rt.run_queue([repair_mission], seal([repair_mission]))
        repair_state = repair_rt.state(repair_mission)
        assert repair_state["status"] == "ACCEPTED", repair_state
        assert repair_state["attempt"] == 2 and len(repair_state["attempt_history"]) == 1

        # 4. Sync learning_loop -> check measured quality + promoted procedures
        metrics = learning_loop.sync_measured_quality(root)
        mem_entries = MemoryStore(shared_mem).all_entries("tel99", include_common=False)
        procedures_doc = (root / "learning" / "learned_procedures.md").read_text(encoding="utf-8")
        assert any(e.kind == "fix" and e.verified for e in mem_entries)
        assert any(e.kind == "procedure" and e.verified for e in mem_entries)

        # 5. Real brutal crash subprocess -> safe AWAITING_HUMAN recovery without replay
        crash_dir = root / "crash-live"
        crash_script = (
            "import os, sys\n"
            "from scripts.agents.automation.autonomy_runtime import Runtime, seal\n"
            "from tests.test_autonomy_runtime import mission\n"
            "m = mission('LIVE-CRASH-1')\n"
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
        cm = synth_mission("LIVE-CRASH-1")
        crash_rt.run_queue([cm], seal([cm]))
        assert replay_calls == []
        assert crash_rt.state(cm)["status"] == "AWAITING_HUMAN"

        # Wrap crash_dir under root/campaign-999 to inspect via recovery_tool & multi_cockpit
        camp_crash = root / "campaign-999"
        crash_dir.replace(camp_crash)
        rec = recovery_tool.inspect_state(root)
        assert len(rec["awaiting_human"]) == 1

        # 6. Live loopback cockpit HTTP + STOP/clear-stop controls
        srv = multi_cockpit.make_server(root, port=0, allow_controls=True, include_providers=False)
        thr = threading.Thread(target=srv.serve_forever, args=(0.02,), daemon=True)
        thr.start()
        try:
            host_hdr = f"127.0.0.1:{srv.server_port}"
            conn = HTTPConnection("127.0.0.1", srv.server_port, timeout=3)
            conn.request("GET", "/", headers={"Host": host_hdr})
            html_resp = conn.getresponse()
            assert html_resp.status == 200
            conn.close()

            conn = HTTPConnection("127.0.0.1", srv.server_port, timeout=3)
            conn.request("GET", "/api/snapshot.json", headers={"Host": host_hdr})
            snap = json.loads(conn.getresponse().read().decode("utf-8"))
            conn.close()

            conn = HTTPConnection("127.0.0.1", srv.server_port, timeout=3)
            conn.request("POST", "/api/stop", headers={"Host": host_hdr, "X-TEL99-Token": snap["controls_token"]})
            assert conn.getresponse().status == 200
            conn.close()
            assert (root / "stop.request").exists()

            conn = HTTPConnection("127.0.0.1", srv.server_port, timeout=3)
            conn.request("POST", "/api/clear-stop", headers={"Host": host_hdr, "X-TEL99-Token": snap["controls_token"]})
            assert conn.getresponse().status == 200
            conn.close()
            assert not (root / "stop.request").exists()
        finally:
            srv.shutdown()
            thr.join(timeout=2)
            srv.server_close()

        report["proofs"]["chain_and_learning"] = {
            "baseline_checks": plan["baseline_checks"],
            "chain_statuses": chain_statuses,
            "repair_proof": {
                "status": repair_state["status"],
                "attempts": repair_state["attempt"],
                "feedback_line": repair_state["attempt_history"][0]["feedback"].get("line"),
            },
            "measured_quality": metrics["measured_quality"],
            "memory_entries_count": len(mem_entries),
            "procedures_doc_present": bool(procedures_doc.strip()),
            "proposal_draft_missions": len(plan["github_proposal"]["missions"]),
        }
        report["proofs"]["crash_and_cockpit"] = {
            "crash_exit_code": proc.returncode,
            "replayed_workers": len(replay_calls),
            "post_crash_status": "AWAITING_HUMAN",
            "cockpit_http_and_controls": "OK",
        }

    report["duration_seconds"] = round(time.monotonic() - started, 3)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
