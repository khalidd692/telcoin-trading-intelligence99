"""Offline end-to-end tests for planning, procedures, isolation, recovery & cockpit controls."""
from __future__ import annotations

from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts.agents.automation import (
    github_multi_mandate_session as multi,
    learning_loop,
    mission_planner,
    multi_cockpit,
    recovery_tool,
)
from scripts.agents.intelligence.memory import Entry, MemoryStore
from scripts.agents.protocol.store import FileStore
from tests.test_github_multi_mandate_session import FakeCampaign, spec, write_manifest
from tests.test_provider_router import _inventory


class MissionPlannerAndProceduresTests(unittest.TestCase):
    def test_plan_from_goal_orders_dependencies_and_builds_sealed_registry(self):
        goal_spec = {
            "goal": "Fix two independent helpers cleanly",
            "base_sha": "934d9fd8a3fd498c6e3e69226007dd46276aa6da",
            "base_ref": "agents/tel99-code-base-autofeed-20261124",
            "controller_issue": 230,
            "mandate_comment_id": 888888,
            "expires_at": "2026-12-15T23:59:59Z",
            "tasks": [
                {
                    "id": "task-second", "issue": 232, "dependencies": ["task-first"],
                    "path": "scripts/agents/automation/pilot_recipe.py",
                    "function": "dedup_key",
                    "test": "assert False, 'red'",
                },
                {
                    "id": "task-first", "issue": 231, "dependencies": [],
                    "path": "scripts/agents/automation/verify_runtime.py",
                    "function": "tool_names",
                    "test": "assert False, 'red'",
                },
            ],
        }
        plan = mission_planner.plan_from_goal(
            goal_spec,
            verify_baseline=True,
            inventory=_inventory(),
            source_loader=lambda m: f"def {m['function']}(x):\n    return x\n",
            behavior_runner=lambda _img, _src, _test: (False, 1),
        )
        self.assertEqual(plan["execution_order"], ["task-first", "task-second"])
        self.assertEqual(len(plan["local_registry"]["missions"]), 2)
        self.assertEqual(set(plan["local_registry"]["approvals"]), {"task-first", "task-second"})
        self.assertIsNotNone(plan["github_proposal"])
        self.assertEqual(plan["github_proposal"]["github_writes_performed"], 0)
        self.assertEqual(plan["model_selection"]["chosen"]["provider"], "ollama")

    def test_promote_verified_procedures_is_idempotent_and_writes_guide(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mem = root / "learning" / "memory"
            store = MemoryStore(mem)
            store.record(Entry(
                id="fix-demo-1", project="tel99", kind="fix",
                title="Strip blank strings in tool_names",
                body="Check isinstance(item, str) and item.strip().",
                verified=True, verified_by="tel99-local-docker-code-v1", confidence=0.95,
            ))
            first = learning_loop.promote_verified_procedures(mem, "tel99")
            self.assertEqual(first, ["proc-fix-demo-1"])
            self.assertEqual(learning_loop.promote_verified_procedures(mem, "tel99"), [])
            guide = root / "learning" / "learned_procedures.md"
            self.assertTrue(guide.is_file())
            self.assertIn("Strip blank strings in tool_names", guide.read_text(encoding="utf-8"))


class IsolationCollisionAndRecoveryTests(unittest.TestCase):
    def test_isolate_blocked_lets_healthy_controller_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = write_manifest(root, [spec(205), spec(212)])
            state_dir = root / "state"
            # Pre-seed #205 with a terminal BLOCKED checkpoint (never replay!).
            ledger_205 = FileStore(state_dir / "campaign-205" / "ledger")
            ledger_205.put_cas("kilo-local/m-205", {"id": "m-205", "status": "BLOCKED"}, None)

            calls, done = [], {}

            class SeededCampaign(FakeCampaign):
                def states(self):
                    if self.info["issue"] == 205:
                        return iter([{"id": "m-205", "status": "BLOCKED"}])
                    return iter([])

            # Strict default (isolate_blocked=False) raises Blocked on #205 without touching #212.
            with self.assertRaises(multi.Blocked):
                multi.run_campaigns(
                    manifest, state_dir, seconds=1, once=True,
                    build=lambda info, r, d: SeededCampaign(info, done, calls),
                    isolate_blocked=False,
                )
            self.assertEqual(calls, [205])
            calls.clear()

            # With isolate_blocked=True, #205 is isolated without polling and #212 executes cleanly!
            summary = multi.run_campaigns(
                manifest, state_dir, seconds=1, once=True,
                build=lambda info, r, d: SeededCampaign(info, done, calls),
                isolate_blocked=True,
            )
            self.assertEqual(summary, {205: False, 212: True})
            self.assertEqual(calls, [212])

    def test_detects_cross_campaign_path_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            s1, s2 = spec(211), spec(212)
            for issue in (211, 212):
                store = FileStore(root / f"campaign-{issue}" / "ledger")
                store.put_cas("kilo-github/approvals/m1", {
                    "mission": {"id": "m1", "path": "scripts/agents/automation/verify_runtime.py"}
                }, None)
                store.put_cas("kilo-local/m1", {"id": "m1", "status": "ACK"}, None)
            collisions = multi.detect_campaign_collisions([s1, s2], root)
            self.assertIn(212, collisions)
            self.assertIn("path collision", collisions[212])

    def test_recovery_tool_inspects_and_clears_stops_without_touching_cas(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "stop.request").touch()
            camp = root / "campaign-205"
            camp.mkdir(parents=True)
            (camp / "stop.request").touch()
            ledger = FileStore(camp / "ledger")
            ledger.put_cas("kilo-local/m1", {"id": "m1", "status": "BLOCKED", "reason": "test"}, None)
            ledger.put_cas("kilo-local/m2", {"id": "m2", "status": "RUNNING"}, None)

            with patch.object(recovery_tool, "LEGACY_STOP", root / "unused-global-stop"):
                info = recovery_tool.inspect_state(root)
                self.assertTrue(info["parent_stop"])
                self.assertEqual(info["campaign_stops"], ["campaign-205"])
                self.assertEqual(len(info["blocked_missions"]), 1)
                self.assertEqual(len(info["crashed_running"]), 1)

                cleared = recovery_tool.clear_stops(root)
                self.assertEqual(len(cleared["cleared"]), 2)
                self.assertFalse((root / "stop.request").exists())
                self.assertFalse((camp / "stop.request").exists())
                # CAS checkpoints remain strictly untouched.
                self.assertEqual(ledger.get("kilo-local/m1")["status"], "BLOCKED")
                self.assertEqual(ledger.get("kilo-local/m2")["status"], "RUNNING")


class CockpitControlsTests(unittest.TestCase):
    def test_cockpit_post_controls_require_opt_in_and_csrf_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Default read-only server must reject POST /api/stop with 403.
            ro_server = multi_cockpit.make_server(root, port=0, allow_controls=False)
            ro_thread = threading.Thread(target=ro_server.serve_forever, args=(0.02,), daemon=True)
            ro_thread.start()
            try:
                conn = HTTPConnection("127.0.0.1", ro_server.server_port, timeout=3)
                conn.request("POST", "/api/stop", headers={"Host": f"127.0.0.1:{ro_server.server_port}"})
                self.assertEqual(conn.getresponse().status, 403)
                conn.close()
            finally:
                ro_server.shutdown()
                ro_thread.join(timeout=2)
                ro_server.server_close()

            # Opt-in server issues CSRF token in snapshot and honors STOP / clear-stop.
            rw_server = multi_cockpit.make_server(root, port=0, allow_controls=True)
            rw_thread = threading.Thread(target=rw_server.serve_forever, args=(0.02,), daemon=True)
            rw_thread.start()
            try:
                host_hdr = f"127.0.0.1:{rw_server.server_port}"
                conn = HTTPConnection("127.0.0.1", rw_server.server_port, timeout=3)
                conn.request("GET", "/api/snapshot.json", headers={"Host": host_hdr})
                snap = json.loads(conn.getresponse().read().decode("utf-8"))
                conn.close()
                token = snap["controls_token"]

                # Missing token -> 403
                conn = HTTPConnection("127.0.0.1", rw_server.server_port, timeout=3)
                conn.request("POST", "/api/stop", headers={"Host": host_hdr})
                self.assertEqual(conn.getresponse().status, 403)
                conn.close()

                # Valid token -> creates stop.request then clears it
                conn = HTTPConnection("127.0.0.1", rw_server.server_port, timeout=3)
                conn.request("POST", "/api/stop", headers={"Host": host_hdr, "X-TEL99-Token": token})
                self.assertEqual(conn.getresponse().status, 200)
                conn.close()
                self.assertTrue((root / "stop.request").exists())

                conn = HTTPConnection("127.0.0.1", rw_server.server_port, timeout=3)
                conn.request("POST", "/api/clear-stop", headers={"Host": host_hdr, "X-TEL99-Token": token})
                self.assertEqual(conn.getresponse().status, 200)
                conn.close()
                self.assertFalse((root / "stop.request").exists())
            finally:
                rw_server.shutdown()
                rw_thread.join(timeout=2)
                rw_server.server_close()


if __name__ == "__main__":
    unittest.main()
