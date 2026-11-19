"""Exercise the supervisor's local handoff without model calls or live approvals."""

from contextlib import contextmanager
from collections import Counter
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/agents/automation"))
import local_codex as runner
from local_coordination import CoordinationUnavailable


class FixtureCoordinator:
    @contextmanager
    def claim(self, task, issue, approval):
        yield "fixture-owner", lambda status, commit=None: None

    def owns(self, owner):
        pass


class WindowsBusTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.supervisor = runner.Supervisor(Path(directory.name))
        self.backend = FixtureCoordinator()

    def events(self):
        store = self.supervisor.store
        return {row["envelope_id"]: row for key in store.keys("envelopes/")
                if (row := store.get(key))}

    def test_supervisor_emits_ordered_events_for_two_fixture_missions(self):
        ran = []
        missions = [{"id": f"FIXTURE-{number}", "issue": number, "kind": "native"} for number in (201, 202)]

        def execute(mission, **kwargs):
            self.assertEqual(Counter(e["tags"][0] for e in self.events().values())["ACK"], len(ran) + 1)
            ran.append(mission["id"])
            sha = "a" * 40
            kwargs["finish"]("PREPARED", sha)
            self.supervisor.checkpoint(mission, "PREPARED", commit=sha)

        with (patch.object(runner, "coordination_backend", return_value=self.backend),
              patch.object(runner, "fetch_approved_issue", return_value=None),
              patch.object(self.supervisor, "execute", side_effect=execute)):
            for mission in missions:
                self.supervisor.run_shared(mission, {})
            with self.assertRaises(CoordinationUnavailable):
                self.supervisor.run_shared(missions[0], {})
        self.assertEqual(ran, [mission["id"] for mission in missions])
        self.assertEqual(Counter(event["tags"][0] for event in self.events().values()),
                         {"REQUEST": 2, "ACK": 2, "RESULT": 2})
        proof = {"status": "VERIFIED_EXTERNAL", "commit_sha": "a" * 40, "mission_id": missions[0]["id"]}
        self.supervisor.checkpoint(missions[0], "ACCEPTED", commit="a" * 40, acceptance=proof)
        self.assertEqual(len(self.events()), 6)
        verdict = {"status": "ACCEPTED", "commit": "a" * 40, "acceptance": proof}
        self.supervisor.publish_bus_outcome(missions[0], verdict)
        self.supervisor.publish_bus_outcome(missions[0], verdict)
        events = self.events()
        self.assertEqual(len(events), 7)
        for event in events.values():
            previous = event["parent_envelope_id"]
            if previous:
                self.assertEqual(events[previous]["correlation_id"], event["correlation_id"])
        self.assertEqual(next(e for e in events.values() if "EVIDENCE" in e["tags"])["kind"], "evidence")

    def test_a_denied_ticket_is_never_acknowledged(self):
        mission = {"id": "FIXTURE-DENIED", "issue": 203, "kind": "native"}
        with (patch.object(runner, "coordination_backend", return_value=self.backend),
              patch.object(runner, "fetch_approved_issue", return_value="denied"),
              patch.object(self.supervisor, "execute") as execute):
            with self.assertRaises(runner.Blocked):
                self.supervisor.run_shared(mission, {})
            execute.assert_not_called()
        self.assertFalse(self.events())
        self.assertIsNone(self.supervisor.store.get(f"claims/{mission['id']}"))

    def test_resume_reuses_ack_without_restarting_worker(self):
        mission = {"id": "FIXTURE-RESUME", "issue": 204, "kind": "native"}
        with (patch.object(runner, "coordination_backend", return_value=self.backend),
              patch.object(runner, "fetch_approved_issue", return_value=None),
              patch.object(self.supervisor, "execute", side_effect=ConnectionError("orphaned"))):
            with self.assertRaises(ConnectionError):
                self.supervisor.run_shared(mission, {})
        with self.assertRaises(CoordinationUnavailable):
            self.supervisor.publish_bus_outcome(mission, {"status": "ACCEPTED", "commit": "a" * 40})
        approval = self.supervisor.store.get(f"claims/{mission['id']}")["approval"]
        resumed = runner.Supervisor(self.supervisor.root)
        finish = lambda status, commit=None: None
        with (patch.object(runner, "coordination_backend", return_value=self.backend),
              patch.object(self.backend, "resume", create=True,
                           return_value=({"status": "CLAIMED"}, finish)),
              patch.object(resumed, "finalize") as finalize,
              patch.object(resumed, "execute") as execute):
            resumed.run_shared(mission, {
                "status": "WORKER_EXITED", "approval": approval, "base": "a" * 40,
                "branch": "fixture", "shared_owner": "fixture-owner",
            })
        execute.assert_not_called()
        finalize.assert_called_once()
        self.assertEqual(Counter(event["tags"][0] for event in self.events().values()),
                         {"REQUEST": 1, "ACK": 1})


if __name__ == "__main__":
    unittest.main()
