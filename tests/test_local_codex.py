import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

AUTOMATION = Path(__file__).resolve().parents[1] / "scripts" / "agents" / "automation"
sys.path.insert(0, str(AUTOMATION))
import local_codex as runner
import local_coordination as coordination


@unittest.skipUnless(sys.platform == "win32", "Windows supervisor")
class LocalCodexTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.supervisor = runner.Supervisor(self.root, "codex.exe", demo=True)
        self.first, self.second = runner.demo_missions()

    def test_restart_holds_interrupted_and_skips_accepted(self):
        self.supervisor.checkpoint(self.first, "ACCEPTED", commit="recorded")
        self.supervisor.checkpoint(self.second, "RUNNING")
        independent = dict(self.second, id="DEMO-03", dependencies=[])
        restarted = runner.Supervisor(self.root, "codex.exe", demo=True)
        with patch.object(restarted, "execute") as execute:
            restarted.run([self.first, self.second, independent])
            execute.assert_called_once_with(independent)
        self.assertEqual(restarted.state(self.first)["commit"], "recorded")
        self.assertEqual(restarted.state(self.second)["status"], "INTERRUPTED")

    def test_a_real_second_process_cannot_acquire_the_lock(self):
        lock = self.root / "supervisor.lock"
        script = (
            "import sys; from pathlib import Path; "
            "sys.path.insert(0, sys.argv[1]); from local_codex import exclusive; "
            "lock = exclusive(Path(sys.argv[2])); lock.__enter__(); print('ACQUIRED')"
        )
        argv = [sys.executable, "-B", "-c", script, str(AUTOMATION), str(lock)]
        with runner.exclusive(lock):
            child = subprocess.run(argv, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(child.returncode, 0)
            self.assertNotIn("ACQUIRED", child.stdout)
        child = subprocess.run(argv, capture_output=True, text=True, timeout=15)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertIn("ACQUIRED", child.stdout)

    def test_quota_is_journaled_before_start_and_stops_the_batch(self):
        with patch.object(self.supervisor, "execute", side_effect=runner.QuotaBlocked("limite")) as execute:
            self.supervisor.run([self.first, self.second])
            execute.assert_called_once_with(self.first)
        self.assertEqual(self.supervisor.state(self.first)["status"], "WAITING_QUOTA")
        self.assertEqual(self.supervisor.state(self.second), {})

    def test_corrupt_checkpoint_does_not_restart_a_mission(self):
        self.supervisor.checkpoint(self.first, "RUNNING")
        path = self.root / "ledger" / "codex-local" / "DEMO-01.json"
        path.write_text("{", encoding="utf-8")
        with self.assertRaises(runner.Blocked):
            self.supervisor.state(self.first)

    def test_worker_exit_checkpoint_resumes_verification_without_a_model_call(self):
        self.supervisor.checkpoint(
            self.first, "WORKER_EXITED", base="base", branch="branch",
            approval=runner.digest(json.dumps(self.first, sort_keys=True)),
        )
        with patch.object(self.supervisor, "execute") as execute:
            with patch.object(self.supervisor, "finalize") as finalize:
                self.supervisor.run([self.first])
                finalize.assert_called_once_with(self.first, "base", "branch")
                execute.assert_not_called()

    def test_invalid_approval_does_not_stop_an_independent_mission(self):
        independent = dict(self.second, id="DEMO-03", dependencies=[])
        with patch.object(self.supervisor, "execute") as execute:
            self.supervisor.run([self.first, self.second, independent], {"DEMO-01": "contenu édité"})
            execute.assert_called_once_with(independent)
        rows = [json.loads(line) for line in (self.root / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["status"] for row in rows], ["AWAITING_HUMAN", "WAITING_DEPENDENCY"])

    def test_issues_are_checked_for_assignment_and_content(self):
        issue = {
            "state": "open", "labels": [{"name": "codex-local/mission"}], "body": "approved",
            "user": {"login": "khalidd692"}, "assignees": [{"login": "codex"}],
        }
        approval = {
            "assignee": "codex", "issue_sha256": runner.digest(issue["body"]),
            "expires_at": "2100-01-01T00:00:00Z",
        }
        self.assertIsNone(runner.validate_issue(issue, approval))
        self.assertIsNotNone(runner.validate_issue(dict(issue, body="changed"), approval))
        self.assertIsNotNone(runner.validate_issue(dict(issue, assignees=[]), approval))
        self.assertIsNotNone(runner.validate_issue(dict(issue, pull_request={"url": "example"}), approval))

    def test_credits_and_unknown_or_exhausted_quota_fail_closed(self):
        credits = {"hasCredits": False, "unlimited": False}
        self.assertEqual(runner.allowance({"credits": credits, "primary": {"usedPercent": 42}}), [42])
        for snapshot in (
            {"credits": credits},
            {"credits": credits, "primary": {"usedPercent": 90}},
            {"credits": dict(credits, hasCredits=True), "primary": {"usedPercent": 1}},
            {"primary": {"usedPercent": 1}},
        ):
            with self.subTest(snapshot=snapshot), self.assertRaises(runner.QuotaBlocked):
                runner.allowance(snapshot)

    def test_github_run_without_shared_config_does_not_launch(self):
        live = runner.Supervisor(self.root, "codex.exe")
        task = dict(self.first, issue=123)
        with patch.object(coordination, "kv_env", return_value=("", "")):
            with patch.object(live, "execute") as execute:
                live.run([task])
                execute.assert_not_called()
        self.assertEqual(live.state(task)["status"], "WAITING_COORDINATION")

    def test_shared_lease_holds_ambiguous_work_and_rejects_replay(self):
        backend = Mock()
        records = {}

        def update(key, new, expected):
            if records.get(key) != expected:
                return False
            records[key] = new
            return True

        backend.put_cas.side_effect = update
        backend.get.side_effect = records.get
        shared = coordination.SharedCoordination.__new__(coordination.SharedCoordination)
        shared.store = backend
        cloud = coordination.orchestrator
        with patch.object(shared, "owns"), patch.object(cloud, "kv_get", return_value={"active": None}):
            with patch.object(cloud, "acquire_lock", return_value=(True, "")):
                with patch.object(cloud, "release_lock") as release:
                    with self.assertRaises(InterruptedError):
                        with shared.claim("S-05", 123, "approved") as (owner, finish):
                            raise InterruptedError
                    release.assert_not_called()
                    _, finish = shared.resume("S-05", 123, "approved", owner)
                    finish("PREPARED", "abc")
                    release.assert_called_once_with(owner)
                    with self.assertRaises(coordination.CoordinationUnavailable):
                        with shared.claim("S-05", 123, "approved"):
                            self.fail("mission replayed")
        self.assertEqual(records["codex-windows/S-05"]["commit"], "abc")

    def test_real_windows_processes_race_for_one_local_cas_record(self):
        script = (
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "from protocol.store import FileStore; "
            "print(FileStore(sys.argv[2]).put_cas('mission/claim', sys.argv[3], None))"
        )
        args = [sys.executable, "-B", "-c", script, str(AUTOMATION.parent), str(self.root)]
        children = []
        try:
            for actor in ("first", "second"):
                children.append(subprocess.Popen(
                    [*args, actor], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                ))
            outcomes = []
            for child in children:
                stdout, stderr = child.communicate(timeout=15)
                self.assertEqual(child.returncode, 0, stderr)
                outcomes.append(stdout.strip())
            self.assertCountEqual(outcomes, ["True", "False"])
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)

    def test_verified_acceptance_must_match_the_approved_sha_and_all_checks(self):
        spec = {
            "criteria": ["criterion-1", "criterion-2"], "verifiers": ["verifier"],
            "conversation_id": "conversation", "mission_digest": "digest",
            "work_branch": "work", "trusted_workflows": {}, "commit_sha": "expected",
        }
        proof = {"commit_sha": "expected"}
        checks = [{"id": "criterion-1", "exit_code": 0}, {"id": "criterion-2", "exit_code": 0}]
        for results, attestation, expected in (
            (checks, proof, proof),
            (checks[:1], proof, None),
            ([checks[0], dict(checks[1], exit_code=1)], proof, None),
            (checks, {"commit_sha": "wrong"}, None),
        ):
            with patch.object(coordination.acceptance, "verify", return_value=(results, attestation)):
                self.assertEqual(coordination.accepted_proof(
                    spec, repository=runner.REPO, mission_body="body", fetch=Mock(), comments=[],
                ), expected)


if __name__ == "__main__":
    unittest.main()
