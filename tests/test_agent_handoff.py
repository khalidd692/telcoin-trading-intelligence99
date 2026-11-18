#!/usr/bin/env python3
"""Tests for the TEL99 handoff engine (issue #94, zero human copy-paste).

Stdlib only, offline, deterministic. They prove the four code gaps the audit of
``main`` found missing are now implemented and *testable*:

  * automatic next-task selection (admissible set, dependency gating,
    human-reserved owners, deterministic ordering);
  * an idempotent receiver keyed on a stable request id (duplicate delivery =>
    one action, one ACK);
  * a content-bound approval (an edited mission is refused);
  * a real verdict that REJECTS a red acceptance check even when every role
    reports PASS, and returns NEEDS_HUMAN for a non-automatable criterion.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import pathlib
from threading import Barrier, Lock, local
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "agents"))

from protocol import handoff  # noqa: E402
from protocol.store import FileStore  # noqa: E402


def _deliver_in_process(root, start, results):
    start.wait(timeout=10)
    inbox = handoff.Inbox("kilo", store=FileStore(root))
    result = inbox.receive({"request_id": "req-process"}, act=lambda _: "executed")
    results.put(result["accepted"])


def _backlog():
    return {
        "schema_version": 1,
        "tasks": [
            {"id": "S-01", "priority": "P0", "owner": "owner",
             "dependencies": [], "initial_state": "awaiting_human"},
            {"id": "S-02", "priority": "P0", "owner": "openhands",
             "dependencies": [], "initial_state": "todo"},
            {"id": "S-03", "priority": "P0", "owner": "openhands",
             "dependencies": [], "initial_state": "in_review"},
            {"id": "S-06", "priority": "P0", "owner": "openhands",
             "dependencies": [], "initial_state": "todo"},
            {"id": "S-04", "priority": "P0", "owner": "openhands",
             "dependencies": ["S-03"], "initial_state": "todo"},
            {"id": "I-01", "priority": "P1", "owner": "hermes",
             "dependencies": [], "initial_state": "todo"},
            {"id": "Z-03", "priority": "P1", "owner": "hermes",
             "dependencies": ["S-06"], "initial_state": "todo"},
        ],
    }


class TaskSelectionTests(unittest.TestCase):
    def test_highest_admissible_is_selected(self):
        chosen = handoff.select_next_task(_backlog())
        # S-02 is P0, not human-reserved, dependency-free, state todo.
        self.assertEqual(chosen["id"], "S-02")

    def test_human_reserved_owner_is_never_selected(self):
        ok, reason = handoff.is_admissible(
            {"id": "S-01", "owner": "owner", "dependencies": []})
        self.assertFalse(ok)
        self.assertIn("human-reserved", reason)

    def test_task_with_unaccepted_dependency_is_not_admissible(self):
        ok, reason = handoff.is_admissible(
            {"id": "S-04", "owner": "openhands", "dependencies": ["S-03"]},
            {"S-03": "in_review"})
        self.assertFalse(ok)
        self.assertIn("dependencies not accepted", reason)

    def test_task_becomes_admissible_once_dependency_accepted(self):
        ok, _ = handoff.is_admissible(
            {"id": "S-04", "owner": "openhands", "dependencies": ["S-03"]},
            {"S-03": "accepted"})
        self.assertTrue(ok)

    def test_owner_filter_restricts_to_that_owner(self):
        chosen = handoff.select_next_task(_backlog(), owner="hermes")
        self.assertEqual(chosen["id"], "I-01")

    def test_selection_is_deterministic(self):
        first = handoff.select_next_task(_backlog())
        second = handoff.select_next_task(_backlog())
        self.assertEqual(first["id"], second["id"])

    def test_report_lists_next_task_and_per_task_reasons(self):
        report = handoff.admissibility_report(_backlog())
        self.assertEqual(report["next_task"], "S-02")
        by_id = {row["id"]: row for row in report["tasks"]}
        self.assertFalse(by_id["S-01"]["admissible"])
        self.assertTrue(by_id["S-02"]["admissible"])

    def test_none_when_nothing_is_admissible(self):
        backlog = {"tasks": [
            {"id": "X", "owner": "openhands", "dependencies": [],
             "initial_state": "accepted"}]}
        self.assertIsNone(handoff.select_next_task(backlog))


class InboxIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FileStore(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_delivery_runs_the_action_once(self):
        calls = []
        inbox = handoff.Inbox("kilo-code-auto-free", store=self.store)
        msg = {"request_id": "req-0001", "task_id": "Z-02"}
        out = inbox.receive(msg, act=lambda m: calls.append(m["task_id"]))
        self.assertTrue(out["accepted"])
        self.assertFalse(out["duplicate"])
        self.assertEqual(out["ack"]["status"], "ACK")
        self.assertEqual(calls, ["Z-02"])

    def test_duplicate_delivery_does_not_run_the_action_again(self):
        calls = []
        inbox = handoff.Inbox("kilo-code-auto-free", store=self.store)
        msg = {"request_id": "req-0002", "task_id": "Z-02"}
        inbox.receive(msg, act=lambda m: calls.append(m["task_id"]))
        again = inbox.receive(msg, act=lambda m: calls.append(m["task_id"]))
        self.assertFalse(again["accepted"])
        self.assertTrue(again["duplicate"])
        self.assertIsNone(again["action"])
        self.assertEqual(calls, ["Z-02"])  # exactly one action

    def test_two_receivers_racing_for_one_request_run_the_action_once(self):
        rendezvous = Barrier(2, timeout=5)
        serialized_put = Lock()
        per_thread = local()

        class RacingStore(FileStore):
            def get(self, key):
                value = super().get(key)
                if not getattr(per_thread, "has_read", False):
                    per_thread.has_read = True
                    rendezvous.wait()
                return value

            def put(self, key, value):
                with serialized_put:
                    super().put(key, value)

        calls = []

        def deliver():
            inbox = handoff.Inbox("kilo", store=RacingStore(self.tmp.name))
            return inbox.receive({"request_id": "req-race"}, act=lambda _: calls.append(1))

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: deliver(), range(2)))
        self.assertEqual(calls, [1])
        self.assertEqual(sorted(result["accepted"] for result in outcomes), [False, True])

    def test_file_claim_is_atomic_across_processes(self):
        ctx = multiprocessing.get_context("spawn")
        start, results = ctx.Barrier(2), ctx.Queue()
        workers = [ctx.Process(target=_deliver_in_process,
                               args=(self.tmp.name, start, results))
                   for _ in range(2)]
        try:
            for worker in workers:
                worker.start()
            accepted = [results.get(timeout=15) for _ in workers]
            self.assertEqual(sorted(accepted), [False, True])
        finally:
            for worker in workers:
                if worker.pid is not None:
                    worker.join(timeout=1)
                    if worker.is_alive():
                        worker.terminate()
                        worker.join()
            results.close()
        self.assertEqual([worker.exitcode for worker in workers], [0, 0])

    def test_lost_ack_preserves_the_claim(self):
        class LostAckStore(FileStore):
            def put_cas(self, key, value, expected):
                if value["status"] == "ACK":
                    raise OSError("connection lost")
                return super().put_cas(key, value, expected)

        calls = []
        msg = {"request_id": "req-no-ack"}
        inbox = handoff.Inbox("kilo", store=LostAckStore(self.tmp.name))
        with self.assertRaises(OSError):
            inbox.receive(msg, act=lambda _: calls.append(1))
        retry = handoff.Inbox("kilo", store=self.store).receive(
            msg, act=lambda _: calls.append(1))
        self.assertEqual(retry["status"], "claimed")
        self.assertTrue(retry["duplicate"])
        self.assertEqual(calls, [1])

    def test_seen_reports_a_recorded_request(self):
        inbox = handoff.Inbox("hermes-router", store=self.store)
        inbox.receive({"request_id": "req-0003"})
        self.assertTrue(inbox.seen("req-0003"))
        self.assertFalse(inbox.seen("req-9999"))

    def test_message_without_stable_id_is_refused(self):
        inbox = handoff.Inbox("kilo", store=self.store)
        with self.assertRaises(ValueError):
            inbox.receive({"task_id": "Z-02"})

    def test_receivers_do_not_share_state(self):
        a = handoff.Inbox("kilo", store=self.store)
        b = handoff.Inbox("hermes", store=self.store)
        a.receive({"request_id": "req-0004"})
        self.assertFalse(b.seen("req-0004"))


class ContentBoundApprovalTests(unittest.TestCase):
    def test_digest_is_stable_across_trailing_whitespace(self):
        self.assertEqual(handoff.content_digest("mission X\nstep 1\n"),
                         handoff.content_digest("mission X\nstep 1"))

    def test_approval_is_current_for_unchanged_content(self):
        content = "Fix the receiver idempotency.\nAcceptance: ACK once."
        approval = handoff.approve(content, approver="owner")
        ok, _ = handoff.approval_is_current(content, approval)
        self.assertTrue(ok)

    def test_edited_content_is_refused(self):
        approval = handoff.approve("original mission", approver="owner")
        ok, reason = handoff.approval_is_current("edited mission", approval)
        self.assertFalse(ok)
        self.assertIn("changed after approval", reason)

    def test_missing_approval_is_refused(self):
        ok, reason = handoff.approval_is_current("anything", None)
        self.assertFalse(ok)
        self.assertIn("no content-bound approval", reason)

    def test_approval_needs_an_approver(self):
        with self.assertRaises(ValueError):
            handoff.approve("content", approver="")


class VerifyMissionTests(unittest.TestCase):
    def _green_check(self, cid="tests-pass"):
        return {"id": cid, "command": "python -m unittest", "exit_code": 0,
                "output_digest": "sha256:abc", "reproducible": True}

    def test_all_roles_pass_and_green_check_is_accepted(self):
        verdict = handoff.verify_mission(
            conversation_finished=True,
            roles={"analyst": True, "developer": True, "verifier": True},
            acceptance_checks=[self._green_check()])
        self.assertEqual(verdict["verdict"], handoff.MISSION_ACCEPTED)
        self.assertTrue(verdict["validated"])

    def test_three_lying_pass_with_a_red_check_is_rejected(self):
        # Gate G3: even if every role reports PASS, a red test REJECTS.
        verdict = handoff.verify_mission(
            conversation_finished=True,
            roles={"analyst": True, "developer": True, "verifier": True},
            acceptance_checks=[{"id": "tests-pass", "command": "python -m unittest",
                                "exit_code": 1, "output_digest": "sha256:red",
                                "reproducible": True}])
        self.assertEqual(verdict["verdict"], handoff.REJECTED)
        self.assertFalse(verdict["validated"])

    def test_check_without_reproducible_proof_is_rejected(self):
        verdict = handoff.verify_mission(
            conversation_finished=True, roles={"analyst": True},
            acceptance_checks=[{"id": "claim", "command": "echo ok",
                                "exit_code": 0, "output_digest": None,
                                "reproducible": False}])
        self.assertEqual(verdict["verdict"], handoff.REJECTED)

    def test_non_automatable_criterion_is_needs_human(self):
        verdict = handoff.verify_mission(
            conversation_finished=True, roles={"analyst": True},
            acceptance_checks=[{"id": "ux-review", "automatable": False}])
        self.assertEqual(verdict["verdict"], handoff.NEEDS_HUMAN)
        self.assertIn("ux-review", verdict["needs_human"])

    def test_no_acceptance_check_is_rejected(self):
        verdict = handoff.verify_mission(
            conversation_finished=True, roles={"analyst": True},
            acceptance_checks=[])
        self.assertEqual(verdict["verdict"], handoff.REJECTED)

    def test_a_missing_role_rejects(self):
        verdict = handoff.verify_mission(
            conversation_finished=True, roles={"analyst": True, "verifier": False},
            acceptance_checks=[self._green_check()])
        self.assertEqual(verdict["verdict"], handoff.REJECTED)

    def test_unfinished_conversation_rejects(self):
        verdict = handoff.verify_mission(
            conversation_finished=False, roles={"analyst": True},
            acceptance_checks=[self._green_check()])
        self.assertEqual(verdict["verdict"], handoff.REJECTED)

    def test_accepts_an_envelope_evidence_object(self):
        from protocol.envelope import Evidence
        evidence = Evidence(kind="test", claim="tests-pass",
                            command="python -m unittest", exit_code=0,
                            output_digest="sha256:abc", reproducible=True)
        verdict = handoff.verify_mission(
            conversation_finished=True, roles={"analyst": True},
            acceptance_checks=[evidence])
        self.assertEqual(verdict["verdict"], handoff.MISSION_ACCEPTED)


class HandoffLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FileStore(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_record_handoff_persists_status_and_event(self):
        ledger = handoff.HandoffLedger(store=self.store)
        event = ledger.record_handoff(task_id="S-03", owner="openhands",
                                      status="accepted", sha="deadbeef",
                                      tests="7/7", proof="pr#99",
                                      next_task="S-04")
        self.assertEqual(event["task_id"], "S-03")
        self.assertEqual(ledger.statuses()["S-03"], "accepted")
        self.assertEqual(len(ledger.events()), 1)

    def test_ledger_drives_the_next_task_after_acceptance(self):
        # A dependency-gated task becomes selectable only once its dependency is
        # recorded accepted — the automatic handoff, no human relaying it.
        ledger = handoff.HandoffLedger(store=self.store)
        before = ledger.next_task(_backlog(), owner="openhands")
        self.assertNotEqual(before["id"], "S-04")
        ledger.record_handoff(task_id="S-03", owner="openhands",
                              status="accepted", next_task="S-04")
        after = ledger.next_task(_backlog(), owner="openhands")
        self.assertIsNotNone(after)

    def test_ledger_survives_a_new_instance_same_store(self):
        handoff.HandoffLedger(store=self.store).record_handoff(
            task_id="S-02", owner="openhands", status="in_progress")
        reopened = handoff.HandoffLedger(store=self.store)
        self.assertEqual(reopened.statuses()["S-02"], "in_progress")




class ZeroCopyPasteLoopTests(unittest.TestCase):
    """The gate G2/G6 loop: one entry -> work -> verify -> auto next task,
    with an idempotent receiver and a resume that survives a new session."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FileStore(self.tmp.name)
        self.backlog = _backlog()

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_mission_runs_and_hands_off_to_the_next_task(self):
        ledger = handoff.HandoffLedger(store=self.store)
        inbox = handoff.Inbox("openhands-cloud", store=self.store)

        # 1) The mission enters ONCE, through the receiver.
        entry = {"request_id": "mission-0001", "task_id": "S-02"}
        first = inbox.receive(entry)
        self.assertTrue(first["accepted"])

        # 2) A duplicate delivery of the same message is a no-op.
        second = inbox.receive(entry)
        self.assertTrue(second["duplicate"])

        # 3) Work is verified by evidence, not by an agent's opinion.
        verdict = handoff.verify_mission(
            conversation_finished=True,
            roles={"analyst": True, "developer": True, "verifier": True},
            acceptance_checks=[{"id": "unit", "command": "python -m unittest",
                                "exit_code": 0, "output_digest": "sha256:ok",
                                "reproducible": True}])
        self.assertEqual(verdict["verdict"], handoff.MISSION_ACCEPTED)

        # 4) The accepted handoff is recorded, and the NEXT task is auto-picked.
        ledger.record_handoff(task_id="S-02", owner="openhands",
                              status="accepted", sha="abc123",
                              tests="29/29", proof="pr#99", next_task="S-03")
        nxt = ledger.next_task(self.backlog, owner="openhands")
        self.assertIsNotNone(nxt)
        self.assertNotEqual(nxt["id"], "S-02")  # S-02 is now accepted

    def test_resume_in_a_new_session_selects_the_same_next_task(self):
        # Session A accepts the three dependency-free P0 tasks.
        session_a = handoff.HandoffLedger(store=self.store)
        for task_id in ("S-02", "S-03", "S-06"):
            session_a.record_handoff(task_id=task_id, owner="openhands",
                                     status="accepted")
        # S-04 (dependency S-03 now accepted) is the highest admissible task.
        self.assertEqual(session_a.next_task(self.backlog,
                                             owner="openhands")["id"], "S-04")

        # Session B: a brand-new ledger over the SAME store — no human relay,
        # no re-derivation of what session A did.
        session_b = handoff.HandoffLedger(store=self.store)
        chosen = session_b.next_task(self.backlog, owner="openhands")
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["id"], "S-04")

    def test_a_receiver_survives_restart_without_double_action(self):
        calls = []
        # Session A receives and acts.
        handoff.Inbox("kilo", store=self.store).receive(
            {"request_id": "req-restart"}, act=lambda m: calls.append(1))
        # Session B (new Inbox instance, same store) sees the duplicate.
        again = handoff.Inbox("kilo", store=self.store).receive(
            {"request_id": "req-restart"}, act=lambda m: calls.append(1))
        self.assertTrue(again["duplicate"])
        self.assertEqual(len(calls), 1)




class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FileStore(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_owner_match_is_case_and_space_insensitive(self):
        ok, reason = handoff.is_admissible(
            {"id": "S-01", "owner": "  Owner ", "dependencies": []})
        self.assertFalse(ok)
        self.assertIn("human-reserved", reason)

    def test_crash_mid_action_does_not_replay_on_redelivery(self):
        # The action raises the first time (a crash mid-work). The claim is
        # persisted BEFORE the action, so the redelivery must NOT re-run it.
        calls = []

        def flaky(_msg):
            calls.append(1)
            raise RuntimeError("crash mid-action")

        inbox = handoff.Inbox("kilo", store=self.store)
        with self.assertRaises(RuntimeError):
            inbox.receive({"request_id": "req-crash"}, act=flaky)
        redelivery = inbox.receive({"request_id": "req-crash"}, act=lambda m: calls.append(1))
        self.assertFalse(redelivery["accepted"])
        self.assertEqual(redelivery["status"], "failed")
        self.assertEqual(calls, [1])

    def test_bus_handoff_dir_is_gitignored(self):
        import subprocess
        root = pathlib.Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["git", "check-ignore", "-q", "bus/handoff/statuses.json"],
            cwd=root, capture_output=True)
        self.assertEqual(result.returncode, 0, "bus/handoff/ must be gitignored")


if __name__ == "__main__":
    unittest.main()
