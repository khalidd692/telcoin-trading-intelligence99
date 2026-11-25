"""Tests for unified cross-engine CAS coordination, RAM guards, orphan reclaim, and infra-error resume."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.agents.automation import (
    autonomy_runtime,
    ide_coordination,
    ollama_native,
    recovery_tool,
)
from scripts.agents.protocol.store import FileStore


class CrossEngineCoordinationTests(unittest.TestCase):
    def test_ollama_blocked_when_llama_server_holds_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # llama-server acquires host-wide local inference lease
            with ide_coordination.local_inference_lease(
                "llama-server",
                state_root=root,
                model="gemma-4-E4B-it-Q8_0.gguf",
                wait_timeout=0.2,
                probe_engines=False,
            ) as llama_ctx:
                self.assertEqual(llama_ctx["actor"], "engine:llama-server")
                # Ollama MUST NOT start inference while llama-server holds the lease
                provider = ollama_native.OllamaNativeProvider(
                    model="gemma4:e4b-tel99-8k",
                    timeout=30,
                    max_tokens=512,
                    coordination_state_root=root,
                    use_coordination_lease=True,
                    lease_wait_timeout=0.15,
                )
                with self.assertRaises(ollama_native.ResourceUnavailableError) as ctx:
                    provider.complete(system="sys", prompt="hi")
                self.assertIn("busy", str(ctx.exception).lower())

            # After llama-server releases, Ollama can acquire cleanly
            with ide_coordination.local_inference_lease(
                "ollama",
                state_root=root,
                model="gemma4:e4b-tel99-8k",
                wait_timeout=0.2,
                probe_engines=False,
            ) as ol_ctx:
                self.assertEqual(ol_ctx["actor"], "engine:ollama")

    def test_llama_server_blocked_when_ollama_holds_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with ide_coordination.local_inference_lease(
                "ollama",
                state_root=root,
                model="gemma4:e4b-tel99-8k",
                wait_timeout=0.2,
                probe_engines=False,
            ):
                with self.assertRaises(ide_coordination.ResourceBusyError):
                    with ide_coordination.local_inference_lease(
                        "llama-server",
                        state_root=root,
                        model="gemma-4-E4B-it-Q8_0.gguf",
                        wait_timeout=0.15,
                        poll_interval=0.05,
                        probe_engines=False,
                    ):
                        pass

    def test_orphan_dead_pid_lease_reclaimed_automatically(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Simulate a crashed process holding the inference lease with a dead PID
            stale = ide_coordination.acquire_lease(
                root,
                actor="engine:llama-server",
                resource_id=ide_coordination.LOCAL_INFERENCE_RESOURCE,
                ttl_seconds=600,
                pid=99999991,
                note="simulated-crash",
            )
            with patch.object(ide_coordination, "is_pid_alive", side_effect=lambda pid: pid == os.getpid()):
                with ide_coordination.local_inference_lease(
                    "ollama",
                    state_root=root,
                    model="gemma4:e4b-tel99-8k",
                    wait_timeout=0.5,
                    probe_engines=False,
                ) as ctx:
                    self.assertNotEqual(ctx["lease"]["lease_id"], stale["lease_id"])
            events = ide_coordination.recent_activity(root, limit=10)
            self.assertTrue(any(e.get("kind") == "orphan_lease_reclaimed" for e in events))

    def test_preload_vs_resident_ram_thresholds_distinct(self):
        # At 1500 MiB free: cold pre-load flags insufficient_ram & clamps; already-resident stays module & ok
        cold = ollama_native.compute_adaptive_budget(
            "gemma4:e4b-tel99-8k",
            task_profile="module",
            estimated_lines=65,
            available_memory_mib=1500,
            model_is_resident=False,
        )
        warm = ollama_native.compute_adaptive_budget(
            "gemma4:e4b-tel99-8k",
            task_profile="module",
            estimated_lines=65,
            available_memory_mib=1500,
            model_is_resident=True,
        )
        self.assertTrue(cold["insufficient_ram"])
        self.assertEqual(cold["effective_profile"], "patch")
        self.assertFalse(warm["insufficient_ram"])
        self.assertEqual(warm["effective_profile"], "module")
        self.assertEqual(warm["ram_state"], "resident_ok")
        self.assertGreaterEqual(warm["num_thread"], 2)

    def test_requeue_infra_failed_mission_and_simulated_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            camp = Path(tmp) / "campaign-demo"
            ledger = camp / "ledger"
            ledger.mkdir(parents=True)
            store = FileStore(ledger)
            # 1. ACCEPTED mission must never be requeued
            store.put_cas("kilo-local/m-ok", {"id": "m-ok", "status": "ACCEPTED", "reason": None}, None)
            r_ok = recovery_tool.requeue_infra_failed_mission(camp, "m-ok")
            self.assertFalse(r_ok["ok"])
            self.assertEqual(store.read("kilo-local/m-ok")["status"], "ACCEPTED")

            # 2. Genuine verification/model error must NOT be requeued as infra error
            store.put_cas(
                "kilo-local/m-logic",
                {"id": "m-logic", "status": "REJECTED", "reason": "independent verification rejected", "error": "AssertionError: wrong sum"},
                None,
            )
            r_logic = recovery_tool.requeue_infra_failed_mission(camp, "m-logic")
            self.assertFalse(r_logic["ok"])
            self.assertEqual(r_logic["failure_category"], "VERIFICATION_ERROR")

            # 3. Genuine ProviderError/timeout IS safely requeued with history preserved
            store.put_cas(
                "kilo-local/m-ram",
                {"id": "m-ram", "status": "BLOCKED", "reason": "ProviderError", "error": "Ollama request timed out"},
                None,
            )
            r_ram = recovery_tool.requeue_infra_failed_mission(camp, "m-ram")
            self.assertTrue(r_ram["ok"])
            self.assertEqual(r_ram["new_status"], "ACK")
            rec = store.read("kilo-local/m-ram")
            self.assertEqual(rec["status"], "ACK")
            self.assertEqual(rec["infra_recovery_count"], 1)
            self.assertEqual(len(rec["infra_recovery_history"]), 1)

            # 4. Simulated interrupted RUNNING crash auto-recovers via Runtime without replaying ACCEPTED
            rt_dir = Path(tmp) / "resume-test"
            m1 = {
                "id": "m-step-1", "owner": "project-file", "project": "demo-res", "specialist": "tel99-dev",
                "priority": "P1", "dependencies": [], "objective": "Step 1",
                "workspace_root": str(Path(tmp)), "allowed_paths": ["a.py"], "target_file": "a.py",
            }
            m2 = {
                "id": "m-step-2", "owner": "project-file", "project": "demo-res", "specialist": "tel99-dev",
                "priority": "P2", "dependencies": ["m-step-1"], "objective": "Step 2",
                "workspace_root": str(Path(tmp)), "allowed_paths": ["b.py"], "target_file": "b.py",
            }
            calls: list[str] = []

            def exec_first(m):
                calls.append(m["id"])
                if m["id"] == "m-step-2":
                    raise RuntimeError("simulated power drop / ProviderError")
                return {"artifact": "x=1\n", "sha256": __import__("hashlib").sha256(b"x=1\n").hexdigest()}

            def ver(m, res):
                return {
                    "ok": True, "verifier": "test-v1", "project": m["project"],
                    "target_file": m["target_file"], "artifact_sha256": res["sha256"],
                    "checks": [{"name": "ok", "ok": True}],
                }

            rt1 = autonomy_runtime.Runtime(rt_dir, executor=exec_first, verifier=ver)
            rt1.run_queue([m1, m2], autonomy_runtime.seal([m1, m2]))
            self.assertEqual(rt1.state(m1)["status"], "ACCEPTED")
            self.assertEqual(rt1.state(m2)["status"], "BLOCKED")

            # Mark m2 error as ProviderError to simulate infra timeout and requeue
            st2 = FileStore(rt_dir / "ledger")
            old2 = st2.read("kilo-local/m-step-2")
            st2.put_cas("kilo-local/m-step-2", {**old2, "reason": "ProviderError"}, old2)
            req = recovery_tool.requeue_infra_failed_mission(rt_dir, "m-step-2")
            self.assertTrue(req["ok"])

            calls.clear()

            def exec_second(m):
                calls.append(m["id"])
                return {"artifact": "y=2\n", "sha256": __import__("hashlib").sha256(b"y=2\n").hexdigest()}

            rt2 = autonomy_runtime.Runtime(rt_dir, executor=exec_second, verifier=ver)
            rt2.run_queue([m1, m2], autonomy_runtime.seal([m1, m2]))
            self.assertEqual(calls, ["m-step-2"])  # m-step-1 ACCEPTED was NOT replayed!
            self.assertEqual(rt2.state(m2)["status"], "ACCEPTED")


if __name__ == "__main__":
    unittest.main()
