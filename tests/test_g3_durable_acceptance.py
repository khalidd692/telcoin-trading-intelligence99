import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/agents/automation"))
import local_coordination as coordination
import local_codex as supervisor


class FencedBackend(coordination.UpstashCoordination):
    def __init__(self, claim):
        self.guard = Lock()
        self.lease = None
        self.claim_record = claim
        self.writes = 0

    def acquire(self, owner):
        with self.guard:
            if self.lease is not None:
                return False
            self.lease = owner
            return True

    def release(self, owner):
        with self.guard:
            if self.lease == owner:
                self.lease = None

    def read(self, key):
        return self.claim_record

    def shared_state(self):
        return {"active": None}

    def update(self, key, new, expected, *, owner):
        with self.guard:
            if owner != self.lease or self.claim_record != expected:
                return False
            self.claim_record = new
            self.writes += 1
            return True


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.task = "CODEX110-WINDOWS-NATIVE-SHORTPATH"
        self.approval, self.commit = "a" * 64, "c" * 40
        self.claim = {"id": self.task, "issue": 114, "approval": self.approval,
                      "owner": "codex-windows-" + "b" * 32, "status": "PREPARED", "commit": self.commit}
        self.proof = {"status": "VERIFIED_EXTERNAL", "mission_id": self.task,
                      "commit_sha": self.commit, "run_id": 17}
        self.backend = FencedBackend(self.claim)

    def promote(self, load=None):
        return self.backend.promote_prepared(
            self.task, 114, self.approval, self.commit, load or (lambda _: self.proof),
        )

    def test_concurrent_replay_emits_one_durable_transition(self):
        def attempt(_):
            try:
                return self.promote()
            except coordination.CoordinationUnavailable:
                return None

        with ThreadPoolExecutor(max_workers=6) as workers:
            records = list(workers.map(attempt, range(12)))
        self.assertTrue(any(record and record["status"] == "ACCEPTED" for record in records))
        self.assertEqual(self.backend.writes, 1)
        self.assertEqual(self.promote()["evidence"], self.proof)
        self.assertEqual(self.backend.writes, 1)

    def test_red_missing_and_wrong_claim_leave_prepared_untouched(self):
        for evidence in (None, {**self.proof, "status": "REJECTED"}, {**self.proof, "commit_sha": "d" * 40}):
            with self.subTest(evidence=evidence), self.assertRaises(coordination.CoordinationUnavailable):
                self.promote(lambda _: evidence)
        self.backend.claim_record = {**self.claim, "approval": "f" * 64}
        verify = Mock()
        with self.assertRaises(coordination.CoordinationUnavailable):
            self.promote(verify)
        verify.assert_not_called()
        self.assertEqual(self.backend.writes, 0)

    def test_expired_fence_cannot_commit(self):
        def verify(_):
            self.backend.lease = "other-owner"
            return self.proof

        with self.assertRaises(coordination.CoordinationUnavailable):
            self.promote(verify)
        self.assertEqual(self.backend.lease, "other-owner")
        self.assertEqual(self.backend.claim_record, self.claim)

    def test_lost_ack_after_write_can_resume_without_second_write(self):
        original = self.backend.update

        def lost_response(*args, **kwargs):
            self.assertTrue(original(*args, **kwargs))
            raise coordination.CoordinationUnavailable("lost acknowledgement")

        self.backend.update = lost_response
        with self.assertRaises(coordination.CoordinationUnavailable):
            self.promote()
        self.backend.update = original
        self.assertEqual(self.promote()["status"], "ACCEPTED")
        self.assertEqual(self.backend.writes, 1)


class SupervisorAcceptanceTests(unittest.TestCase):
    def test_projects_accepted_after_durable_cas_and_retries_failed_projection(self):
        policy = coordination.g3_policy()
        mission = {"id": policy["mission_id"], "issue": 114, "kind": "native"}
        approval = supervisor.digest(json.dumps(mission, sort_keys=True))
        prepared = {"id": mission["id"], "issue": 114, "status": "PREPARED", "native": True,
                    "commit": policy["commit_sha"], "branch": policy["work_branch"],
                    "base": policy["base_sha"], "artifact_digests": policy["artifact_digests"]}
        backend = FencedBackend({"id": mission["id"], "issue": 114, "status": "PREPARED",
                                 "owner": "codex-windows-" + "b" * 32, "approval": approval,
                                 "commit": policy["commit_sha"]})
        runner = Mock()
        runner.state.return_value = prepared
        runner.store.get.return_value = {"issue": 114, "approval": approval, "state": "ACK"}
        runner.checkpoint.side_effect = [OSError("interrupted"), None]
        proof = {"status": "VERIFIED_EXTERNAL", "commit_sha": policy["commit_sha"],
                 "mission_id": mission["id"], "run_id": 5}
        with (patch.object(supervisor, "coordination_backend", return_value=backend),
              patch.object(supervisor, "fetch_approved_issue", return_value=None) as approved,
              patch.object(supervisor, "issue_comments", return_value=[]),
              patch.object(supervisor, "accepted_proof", return_value=proof)):
            with self.assertRaises(OSError):
                supervisor.reconcile_g3_114(runner, [mission], {})
            self.assertEqual(backend.claim_record["status"], "ACCEPTED")
            self.assertTrue(supervisor.reconcile_g3_114(runner, [mission], {mission["id"]: "expired"}))
            runner.state.return_value = {**prepared, "status": "ACCEPTED", "acceptance": proof}
            self.assertTrue(supervisor.reconcile_g3_114(runner, [mission], {}))
            backend.claim_record.update(status="PREPARED")
            del backend.claim_record["evidence"]
            with self.assertRaises(coordination.CoordinationUnavailable):
                supervisor.reconcile_g3_114(runner, [mission], {})
            approved.assert_called_once_with(mission)
        self.assertEqual(runner.checkpoint.call_args.args, (mission, "ACCEPTED"))
        self.assertEqual(runner.checkpoint.call_count, 2)
        self.assertEqual(backend.writes, 1)

    def test_dependency_requires_exact_durable_acceptance_even_after_external_proof(self):
        policy = coordination.g3_policy()
        task = policy["mission_id"]
        issue = {"title": "fixture", "body": "approved fixture"}
        descriptor = {key: policy[key] for key in ("issue", "mission_id", "commit_sha")}
        descriptor.update(verification_mode="g3-bot-v1", issue_sha256=supervisor.digest(issue["body"]),
                          mission_digest=supervisor.mission_digest(supervisor.mission_content(issue)))
        mission = {"dependencies": [task], "dependency_evidence": {task: descriptor}}
        proof = {"status": "VERIFIED_EXTERNAL"}
        backend = FencedBackend({"id": task, "issue": 114, "status": "PREPARED", "commit": policy["commit_sha"]})
        with (patch.object(supervisor, "coordination_backend", return_value=backend),
              patch.object(supervisor, "fetch_acceptance_resource", return_value=issue),
              patch.object(supervisor, "issue_comments", return_value=[]),
              patch.object(supervisor, "accepted_proof", return_value=proof)):
            self.assertEqual(supervisor.dependency_evidence([mission]), {})
            backend.claim_record.update(status="ACCEPTED", evidence=proof)
            self.assertEqual(supervisor.dependency_evidence([mission]), {task: proof})
            descriptor.pop("verification_mode")
            self.assertEqual(supervisor.dependency_evidence([mission]), {})


if __name__ == "__main__":
    unittest.main()
