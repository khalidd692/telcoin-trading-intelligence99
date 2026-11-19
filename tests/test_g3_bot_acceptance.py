"""G3 bot proof is never trusted without independent GitHub API verification."""

import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "g3_bot_acceptance_under_test",
    ROOT / "scripts" / "agents" / "automation" / "g3_bot_acceptance.py",
)
g3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g3)
TRUST = json.loads((ROOT / "docs/agents/G3_AUTO_TRUST_114.json").read_text())
REPO = "khalidd692/telcoin-trading-intelligence99"


def make_fixture():
    policy = copy.deepcopy(TRUST)
    bytes_by_name = {
        "tasks.py": b"def main():\n    pass\n",
        "README.md": b"example\n",
    }
    policy["artifact_digests"] = {
        name: hashlib.sha256(data).hexdigest() for name, data in bytes_by_name.items()
    }
    payload = {
        "version": 1, "project_id": policy["project_id"],
        "mission_id": policy["mission_id"], "issue": policy["issue"],
        "candidate_branch": policy["work_branch"],
        "candidate_sha": policy["commit_sha"],
        "candidate_digests": policy["artifact_digests"],
        "verifier_branch": policy["verifier_branch"],
        "verifier_sha": policy["verifier_sha"],
        "check_job": g3.CHECK_JOB, "checks": policy["criteria"],
        "verdict": "PASS", "accepted": False, "run_id": 123, "run_attempt": 1,
    }
    comment = {
        "id": 42, "body": g3.MARKER + json.dumps(payload), "user": {"login": g3.BOT},
        "created_at": "2026-11-19T00:00:00Z",
        "updated_at": "2026-11-19T00:00:00Z",
    }
    maps = {
        "git/ref/heads/" + policy["work_branch"]: {
            "ref": "refs/heads/" + policy["work_branch"],
            "object": {"type": "commit", "sha": policy["commit_sha"]},
        },
        "commits/" + policy["commit_sha"]: {
            "sha": policy["commit_sha"], "parents": [{"sha": policy["base_sha"]}],
        },
        "actions/runs/123": {
            "id": 123, "run_attempt": 1, "event": "push",
            "head_sha": policy["verifier_sha"],
            "head_branch": policy["verifier_branch"],
            "head_repository": {"full_name": REPO},
            "workflow_id": policy["workflow_id"],
            "path": ".github/workflows/tel99-g3-independent-native.yml",
            "status": "completed", "conclusion": "success",
        },
        "actions/runs/123/attempts/1/jobs?per_page=100": {
            "total_count": 2,
            "jobs": [
                {"id": 501, "name": g3.CHECK_JOB, "run_id": 123,
                 "run_attempt": 1, "head_sha": policy["verifier_sha"],
                 "status": "completed", "conclusion": "success"},
                {"id": 502, "name": g3.ATTEST_JOB, "run_id": 123,
                 "run_attempt": 1, "head_sha": policy["verifier_sha"],
                 "status": "completed", "conclusion": "success"},
            ],
        },
    }
    for filename, data in bytes_by_name.items():
        path = f"docs/agents/codex-local-results/{policy['mission_id'].lower()}/{filename}"
        maps[f"contents/{path}?ref={policy['commit_sha']}"] = {
            "path": path, "type": "file", "encoding": "base64",
            "size": len(data), "content": base64.b64encode(data).decode(),
        }
    for path, digest in policy["trusted_blobs"].items():
        maps[f"contents/{path}?ref={policy['verifier_sha']}"] = {
            "path": path, "type": "file", "sha": digest,
        }
    return policy, comment, payload, maps


class ExternalProofTest(unittest.TestCase):
    def setUp(self):
        self.policy, self.comment, self.payload, self.maps = make_fixture()

    def result(self):
        return g3.verify(
            policy=self.policy, comments=[self.comment], repository=REPO,
            fetch=lambda path: self.maps[path],
        )

    def test_realized_proof_can_be_independently_checked(self):
        self.assertEqual(self.result()["status"], "VERIFIED_EXTERNAL")

    def test_no_bot_comment_means_no_proof(self):
        self.comment["body"] = "PASS"
        self.assertIsNone(self.result())

    def test_same_owner_impersonating_bot_is_rejected(self):
        self.comment["user"]["login"] = "khalidd692"
        self.assertIsNone(self.result())

    def test_comment_edited_later_is_not_an_attestation(self):
        self.comment["updated_at"] = "2026-11-19T00:01:00Z"
        self.assertIsNone(self.result())

    def test_work_branch_moves_after_proof(self):
        self.maps["git/ref/heads/" + self.policy["work_branch"]]["object"]["sha"] = "f" * 40
        self.assertIsNone(self.result())

    def test_commit_parent_mismatch(self):
        self.maps["commits/" + self.policy["commit_sha"]]["parents"] = []
        self.assertIsNone(self.result())

    def test_candidate_artifact_tampered(self):
        path = f"docs/agents/codex-local-results/{self.policy['mission_id'].lower()}/tasks.py"
        self.maps[f"contents/{path}?ref={self.policy['commit_sha']}"]["content"] = base64.b64encode(b"tamper").decode()
        self.assertIsNone(self.result())

    def test_workflow_not_exact_trusted_blob(self):
        path = ".github/workflows/tel99-g3-independent-native.yml"
        self.maps[f"contents/{path}?ref={self.policy['verifier_sha']}"]["sha"] = "f" * 40
        self.assertIsNone(self.result())

    def test_untrusted_verifier_commit_is_ignored(self):
        self.comment["body"] = self.comment["body"].replace(self.policy["verifier_sha"], "f" * 40)
        self.assertIsNone(self.result())

    def test_workflow_run_head_mismatch(self):
        self.maps["actions/runs/123"]["head_sha"] = "f" * 40
        self.assertIsNone(self.result())

    def test_workflow_run_incomplete(self):
        self.maps["actions/runs/123"]["status"] = "in_progress"
        self.assertIsNone(self.result())

    def test_check_job_red_blocks_acceptance(self):
        self.maps["actions/runs/123/attempts/1/jobs?per_page=100"]["jobs"][0]["conclusion"] = "failure"
        self.assertIsNone(self.result())

    def test_attest_job_red_blocks_acceptance(self):
        self.maps["actions/runs/123/attempts/1/jobs?per_page=100"]["jobs"][1]["conclusion"] = "failure"
        self.assertIsNone(self.result())

    def test_untrusted_workflow_id(self):
        self.maps["actions/runs/123"]["workflow_id"] = 987
        self.assertIsNone(self.result())

    def test_missing_or_duplicate_jobs(self):
        page = self.maps["actions/runs/123/attempts/1/jobs?per_page=100"]
        page["jobs"].append(copy.deepcopy(page["jobs"][0]))
        page["total_count"] = 3
        self.assertIsNone(self.result())

    def test_wrong_run_attempt(self):
        self.maps["actions/runs/123"]["run_attempt"] = 2
        self.assertIsNone(self.result())

    def test_newer_untrusted_bot_run_cannot_override_pinned_proof(self):
        newer = copy.deepcopy(self.comment)
        newer["id"] = 100
        payload = copy.deepcopy(self.payload)
        payload["verifier_sha"] = "f" * 40
        newer["body"] = g3.MARKER + json.dumps(payload)
        result = g3.verify(
            policy=self.policy, comments=[self.comment, newer], repository=REPO,
            fetch=lambda path: self.maps[path],
        )
        self.assertEqual(result["status"], "VERIFIED_EXTERNAL")

    def test_no_trust_policy_fails_closed(self):
        self.assertIsNone(g3.verify(
            policy={}, comments=[self.comment], repository=REPO,
            fetch=lambda path: self.maps[path],
        ))


if __name__ == "__main__":
    unittest.main()
