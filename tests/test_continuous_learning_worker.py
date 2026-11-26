"""Offline unit tests for G5/G6 continuous learning & G8 bounded proactive council."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agents.automation import ide_coordination
from scripts.agents.automation.local_codex import exclusive
from scripts.agents.automation.continuous_learning_worker import ContinuousLearningWorker


class TestContinuousLearningAndProactiveG8(unittest.TestCase):
    def test_g8_concurrent_same_day_cycle_is_serialized_and_loser_does_not_overwrite_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            worker = ContinuousLearningWorker(td)
            snapshot = {
                "projects": [{"name": "TEL99", "status": "IN_PROGRESS", "missions_accepted": 1, "missions_total": 4}],
                "certification": {"endurance_latest": {"status": "FAILED"}},
                "groq_quotas": {"legacy_unattributed": False},
            }
            entered_execution = threading.Event()
            release_execution = threading.Event()
            original_execute = worker._execute_proactive_cycle_locked

            def paused_execute(**kwargs):
                entered_execution.set()
                if not release_execution.wait(timeout=5):
                    raise AssertionError("test did not release first G8 execution")
                return original_execute(**kwargs)

            worker._execute_proactive_cycle_locked = paused_execute  # type: ignore[method-assign]
            first_result: list[dict] = []
            first = threading.Thread(target=lambda: first_result.append(worker.run_proactive_cycle(
                authorized_snapshot=snapshot, daily_key="2026-11-26", probe_engines=False
            )))
            first.start()
            self.assertTrue(entered_execution.wait(timeout=5), "first cycle never acquired the lock")

            losing = worker.run_proactive_cycle(
                authorized_snapshot=snapshot, daily_key="2026-11-26", probe_engines=False
            )
            self.assertEqual(losing["status"], "DEFERRED")
            self.assertFalse(losing["state_persisted"])
            self.assertFalse(worker.proactive_state_path.exists())

            release_execution.set()
            first.join(timeout=5)
            self.assertFalse(first.is_alive())
            self.assertEqual(len(first_result), 1)
            self.assertIn(first_result[0]["status"], {"PROPOSAL", "DONE"})
            final_state = worker.load_proactive_state()
            self.assertEqual(final_state["daily_executed_keys"].count("2026-11-26"), 1)
            self.assertEqual(final_state["latest_brief"]["brief_id"], first_result[0]["brief_id"])

    def test_g8_rechecks_daily_dedup_after_waiting_for_owner_of_lock(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            worker = ContinuousLearningWorker(td)
            state = worker.load_proactive_state()
            state["daily_executed_keys"] = ["2026-11-26"]
            worker.save_proactive_state(state)
            with exclusive(worker.learning_dir / "proactive.lock"):
                result = worker.run_proactive_cycle(
                    authorized_snapshot={}, daily_key="2026-11-26", probe_engines=False
                )
            self.assertEqual(result["status"], "DEFERRED")
            self.assertEqual(result["reason"], "proactive_lock_busy")
            self.assertFalse(result["state_persisted"])
            self.assertEqual(worker.load_proactive_state()["daily_executed_keys"], ["2026-11-26"])

    def test_pause_resume_and_owner_priority_yield(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            worker = ContinuousLearningWorker(td)
            ok, reason = worker.can_run_background(probe_engines=False)
            self.assertTrue(ok, reason)

            worker.pause()
            ok, reason = worker.can_run_background(probe_engines=False)
            self.assertFalse(ok)
            self.assertEqual(reason, "paused_by_owner")

            worker.resume()
            ok, reason = worker.can_run_background(probe_engines=False)
            self.assertTrue(ok)

            ide_coordination.set_owner_interactive_priority(td, job_id="job-test-1", ttl_seconds=60)
            try:
                ok, reason = worker.can_run_background(probe_engines=False)
                self.assertFalse(ok)
                self.assertEqual(reason, "yielded_to_owner_priority")
            finally:
                ide_coordination.clear_owner_interactive_priority(td, job_id="job-test-1")

    def test_full_g6_chain_error_fix_persist_reload_distinct_task(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            worker = ContinuousLearningWorker(td)
            calls: list[str] = []

            def fake_model(role: str, prompt: str) -> str:
                calls.append(prompt)
                if "strict_positive_amount" in prompt and "Previous attempt failed" not in prompt:
                    return (
                        "```python\n"
                        "import math\n"
                        "def strict_positive_amount(value):\n"
                        "    if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:\n"
                        "        raise ValueError('invalid')\n"
                        "    return float(value)\n"
                        "```"
                    )
                if "strict_positive_amount" in prompt and "Previous attempt failed" in prompt:
                    return (
                        "```python\n"
                        "import math\n"
                        "def strict_positive_amount(value):\n"
                        "    if isinstance(value, bool) or not isinstance(value, (int, float)):\n"
                        "        raise TypeError('invalid')\n"
                        "    if not math.isfinite(value) or value <= 0:\n"
                        "        raise ValueError('invalid')\n"
                        "    return float(value)\n"
                        "```"
                    )
                if "validate_order_quantity" in prompt and "isinstance(value, bool)" in prompt:
                    return (
                        "```python\n"
                        "def validate_order_quantity(qty):\n"
                        "    if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:\n"
                        "        raise ValueError('invalid')\n"
                        "    return qty\n"
                        "```"
                    )
                return "def broken(): pass"

            res = worker.run_verified_g6_chain(model_call=fake_model, probe_engines=False)
            self.assertTrue(res["ok"])
            self.assertFalse(res["task_a_initial_passed"])
            self.assertTrue(res["task_a_repaired"])
            self.assertTrue(res["lesson_recalled_after_reload"])
            self.assertTrue(res["task_b_passed"])
            self.assertTrue(res["g6_chain_proven"])
            self.assertEqual(len(calls), 3)

            st = worker.load_state()
            self.assertTrue(st["g6_chain_proven"])
            self.assertEqual(st["verified_lessons_promoted"], 1)
            self.assertFalse(st["lora_training_enabled"])

    def test_g8_proactive_cycle_deliverable_dedup_feedback_and_no_useful_task(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            worker = ContinuousLearningWorker(td)
            snap = {
                "projects": [
                    {"name": "TEL99_BUDGET_FAMILIAL_V2", "status": "IN_PROGRESS", "missions_accepted": 4, "missions_total": 7}
                ],
                "certification": {"endurance_latest": {"status": "FAILED"}},
                "groq_quotas": {"legacy_unattributed": False},
            }

            # 1. Owner priority yields proactive cycle immediately
            ide_coordination.set_owner_interactive_priority(td, job_id="job-owner-busy", ttl_seconds=60)
            try:
                yielded = worker.run_proactive_cycle(
                    authorized_snapshot=snap, trigger="scheduled_idle", daily_key="2026-11-26", probe_engines=False
                )
                self.assertFalse(yielded["ok"])
                self.assertEqual(yielded["status"], "YIELDED_TO_OWNER")
            finally:
                ide_coordination.clear_owner_interactive_priority(td, job_id="job-owner-busy")

            # 2. Scheduled cycle produces 1 bounded verifiable deliverable & morning brief (no auto-approval)
            res1 = worker.run_proactive_cycle(
                authorized_snapshot=snap, trigger="scheduled_idle", daily_key="2026-11-26", probe_engines=False
            )
            self.assertTrue(res1["ok"])
            self.assertEqual(res1["status"], "PROPOSAL")
            self.assertTrue(res1["requires_human_approval"])
            self.assertLessEqual(len(res1["council_roles"]), 3)
            deliverable = Path(td) / res1["deliverable_rel_path"]
            self.assertTrue(deliverable.is_file())
            self.assertNotIn("C:\\Users\\", deliverable.read_text(encoding="utf-8"))

            # 3. Same-day second cycle is deduplicated cleanly without repeating work
            res_dup = worker.run_proactive_cycle(
                authorized_snapshot=snap, trigger="scheduled_idle", daily_key="2026-11-26", probe_engines=False
            )
            self.assertTrue(res_dup["ok"])
            self.assertEqual(res_dup["status"], "NO_USEFUL_TASK")
            self.assertTrue(res_dup["deduplicated"])

            # 4. Owner feedback updates domain weight & persists to MemoryStore
            fb = worker.record_brief_feedback(res1["brief_id"], "useful", note="Bon diagnostic")
            self.assertTrue(fb["ok"])
            self.assertGreater(fb["domain_weight"], 1.0)

            # 5. Next day with NO actionable signals concludes NO_USEFUL_TASK honestly
            empty_snap = {
                "projects": [{"name": "AI_RADAR", "status": "COMPLETED", "missions_accepted": 5, "missions_total": 5}],
                "certification": {"endurance_latest": {"status": "PROVEN"}},
                "groq_quotas": {"legacy_unattributed": False},
                "suppress_beyond_tel99_opportunities": True,
            }
            res_empty = worker.run_proactive_cycle(
                authorized_snapshot=empty_snap, trigger="scheduled_idle", daily_key="2026-11-27", probe_engines=False
            )
            self.assertTrue(res_empty["ok"])
            self.assertEqual(res_empty["status"], "NO_USEFUL_TASK")

            # 6. Multi-role LLM council produces DONE deliverable with 3 distinct role contributions
            role_calls: list[str] = []

            def fake_council(role: str, prompt: str) -> str:
                role_calls.append(role)
                return f"Contribution vérifiée de {role} : analyse factuelle, risques et plan réversible."

            res_done = worker.run_proactive_cycle(
                authorized_snapshot={"projects": [], "certification": {}, "groq_quotas": {}},
                trigger="windows_task_scheduler",
                daily_key="2026-11-28",
                model_call=fake_council,
                probe_engines=False,
            )
            self.assertTrue(res_done["ok"])
            self.assertEqual(res_done["status"], "DONE")
            self.assertEqual(res_done["distinct_council_calls"], 3)
            self.assertEqual(len(role_calls), 3)


if __name__ == "__main__":
    unittest.main()
