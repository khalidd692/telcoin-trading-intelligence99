import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from urllib.parse import parse_qs, urlsplit

from scripts.agents.automation.autonomy_runtime import FileStore, fingerprint
from scripts.agents.automation.kilo_acceptance_pr import publish_verified_pr


REPO = "khalidd692/telcoin-trading-intelligence99"
API = f"repos/{REPO}"
BASE = "codex/kilo-cloud-handoff-20261120"
BASE_SHA = "a903ebc45c0217ca7e0df527388f21b449cd3215"
CONTROL_ISSUE = 123
ISSUE = 501
PROOF = f"https://github.com/{REPO}/issues/{ISSUE}#issuecomment-9001"
PR_URL = f"https://github.com/{REPO}/pull/902"
OWNER = {"login": "khalidd692", "id": 275517051, "type": "User"}
NAMES = ("synthetic-contract", "artifact-sha256", "specialist-identity", "zero-cost-evidence")
ARTIFACT = "Résultat synthétique\u00a0!\n"
ARTIFACT_SHA = hashlib.sha256(ARTIFACT.encode()).hexdigest()
BASE_TREE = "1" * 40
EVIDENCE_TREE = "2" * 40
COMMIT = "3" * 40


class GitHubFixture:
    def __init__(self, proof, *, pull_number=902):
        self.refs = {f"refs/heads/{BASE}": BASE_SHA}
        self.proof = proof
        self.pull = None
        self.pull_number = pull_number
        self.writes = []
        self.blob = None
        self.tree = None
        self.lost_ref_response = False
        self.lost_pr_response = False
        self.drop_pr_before_creation = False
        self.force_wrong_diff = False
        self.advance_head_after_first_read = False

    def __call__(self, resource, *, method="GET", payload=None):
        url = urlsplit(resource)
        path = url.path.removeprefix(f"{API}/")
        if url.path == path:
            raise AssertionError(f"unexpected repository endpoint {resource}")
        if method == "GET":
            if path == "issues/comments/9001":
                return deepcopy(self.proof)
            if path.startswith("git/matching-refs/heads/"):
                prefix = path.removeprefix("git/matching-refs/")
                matched = [{"ref": ref, "object": {"type": "commit", "sha": sha}}
                           for ref, sha in self.refs.items() if ref.removeprefix("refs/").startswith(prefix)]
                if self.advance_head_after_first_read and prefix.startswith("heads/codex/tel99-acceptance/") and matched:
                    self.refs[matched[0]["ref"]] = "f" * 40
                    self.advance_head_after_first_read = False
                return matched
            if path == f"git/commits/{BASE_SHA}":
                return {"sha": BASE_SHA, "tree": {"sha": BASE_TREE}}
            if path == f"compare/{BASE_SHA}...{COMMIT}" and self.tree:
                change = self.tree["tree"][0]
                filename = ".github/workflows/extra.yml" if self.force_wrong_diff else change["path"]
                return {"status": "ahead", "ahead_by": 1, "behind_by": 0, "total_commits": 1,
                        "commits": [{"sha": COMMIT}],
                        "files": [{"filename": filename, "status": "added", "sha": change["sha"]}]}
            if path == "pulls":
                query = parse_qs(url.query)
                if query.get("state") != ["all"]:
                    raise AssertionError("closed PRs must be included in reconciliation")
                head = self.pull["head"]["ref"] if self.pull else None
                return [deepcopy(self.pull)] if query.get("head") == [f"khalidd692:{head}"] else []
        if method == "POST":
            self.writes.append((path, deepcopy(payload)))
            if path == "git/blobs":
                self.blob = payload["content"].encode("utf-8")
                return {"sha": hashlib.sha1(f"blob {len(self.blob)}\0".encode() + self.blob).hexdigest()}
            if path == "git/trees":
                self.tree = payload
                return {"sha": EVIDENCE_TREE}
            if path == "git/commits":
                return {"sha": COMMIT}
            if path == "git/refs":
                if payload["ref"] in self.refs:
                    raise AssertionError("existing refs must never be updated")
                self.refs[payload["ref"]] = payload["sha"]
                if self.lost_ref_response:
                    raise OSError("lost create-ref response")
                return {"ref": payload["ref"], "object": {"type": "commit", "sha": payload["sha"]}}
            if path == "pulls":
                if self.drop_pr_before_creation:
                    raise OSError("POST outcome unknown")
                if self.pull:
                    raise AssertionError("existing PRs must never be duplicated")
                self.pull = {"number": self.pull_number,
                             "html_url": f"https://github.com/{REPO}/pull/{self.pull_number}",
                             "draft": payload["draft"],
                             "state": "open", "user": OWNER, "title": payload["title"],
                             "body": payload["body"], "base": {"ref": payload["base"], "sha": BASE_SHA,
                             "repo": {"full_name": REPO}}, "head": {"ref": payload["head"],
                             "sha": self.refs[f"refs/heads/{payload['head']}"], "repo": {"full_name": REPO}}}
                if self.lost_pr_response:
                    raise OSError("lost create-PR response")
                return deepcopy(self.pull)
        raise AssertionError(f"unexpected GitHub call {method} {resource}")


class AcceptancePullRequestTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = FileStore(directory.name)
        self.mission = {"id": "mission-A", "project": "synthetic", "synthetic_data": True,
                        "owner": "kilo", "objective": "Never copy this objective into the PR",
                        "expected_sha256": ARTIFACT_SHA, "specialist": "tel99-analyst", "dependencies": []}
        contract = fingerprint(self.mission)
        self.state = {"id": "mission-A", "project": "synthetic", "status": "ACCEPTED",
                      "execution_status": "COMPLETED", "contract_sha256": contract,
                      "result": {"artifact": ARTIFACT, "sha256": ARTIFACT_SHA,
                                 "specialist_id": "tel99-analyst", "provider": "kilo-auto-free",
                                 "provider_evidence": {"cost_usd": "0", "http_status": 200,
                                                       "catalog_sha256": "a" * 64, "response_sha256": "b" * 64}},
                      "verification": {"verifier": "tel99-fixed-subprocess-v1", "ok": True,
                                       "artifact_sha256": ARTIFACT_SHA,
                                       "checks": [{"name": name, "ok": True} for name in NAMES]},
                      "verdict": {"validated": True}}
        self.store.put("kilo-local/mission-A", self.state)
        self.store.put("kilo-github/approvals/mission-A", {
            "comment_id": 9000, "contract_sha256": contract, "mission": self.mission,
            "issue": ISSUE, "base": BASE, "base_sha": BASE_SHA,
        })
        self.store.put("kilo-github/config", {"repo": REPO, "issue": CONTROL_ISSUE, "campaign": True,
                                             "mandate_id": 8999, "mandate_sha256": "c" * 64})
        event = {"event": "kilo-relay-event/v1", "phase": "EVIDENCE", "issue": ISSUE,
                 "status": "ACCEPTED", "execution_status": "COMPLETED", "scope": "synthetic-text",
                 "mission_id": "mission-A", "approval_comment_id": 9000, "mandate_comment_id": 8999,
                 "mandate_sha256": "c" * 64, "contract_sha256": contract, "artifact_sha256": ARTIFACT_SHA,
                 "verification_sha256": fingerprint(self.state["verification"]), "checks": self.state["verification"]["checks"],
                 "verifier": "tel99-fixed-subprocess-v1", "specialist": "tel99-analyst",
                 "cost_usd": "0", "catalog_sha256": "a" * 64, "response_sha256": "b" * 64}
        proof = {"id": 9001, "html_url": PROOF, "issue_url": f"https://api.github.com/{API}/issues/{ISSUE}",
                 "user": OWNER, "created_at": "2026-11-21T12:00:00Z", "updated_at": "2026-11-21T12:00:00Z",
                 "body": f"```kilo-relay-event/v1\n{json.dumps(event)}\n```"}
        self.github = GitHubFixture(proof)

    def publish(self, *, repo=REPO, issue=ISSUE, base=BASE, base_sha=BASE_SHA, proof=PROOF):
        return publish_verified_pr(repo, issue, base, base_sha, self.state, proof,
                                   api=self.github, store=self.store)

    def test_publishes_only_one_verified_text_blob_to_an_isolated_draft(self):
        self.assertEqual(self.publish(), PR_URL)
        self.assertEqual(self.github.blob, ARTIFACT.encode("utf-8"))
        self.assertEqual(self.github.tree["base_tree"], BASE_TREE)
        change, = self.github.tree["tree"]
        self.assertRegex(change["path"], r"^docs/agents/autonomy-evidence/acceptance/501-mission-A-[0-9a-f]+\.txt$")
        self.assertEqual((change["mode"], change["type"]), ("100644", "blob"))
        self.assertTrue(self.github.pull["draft"])
        self.assertEqual(self.github.pull["base"]["ref"], BASE)
        self.assertRegex(self.github.pull["head"]["ref"], r"^codex/tel99-acceptance/501-mission-A-[0-9a-f]+$")
        for expected in (f"Refs #{ISSUE}", PROOF, ARTIFACT_SHA, *NAMES):
            self.assertIn(expected, self.github.pull["body"])
        self.assertNotIn(self.mission["objective"], self.github.pull["body"])

    def test_reads_back_lost_ref_and_pr_responses_without_reposting(self):
        self.github.lost_ref_response = self.github.lost_pr_response = True
        self.assertEqual(self.publish(), PR_URL)
        self.assertEqual(self.publish(), PR_URL)
        self.assertEqual([endpoint for endpoint, _ in self.github.writes].count("git/refs"), 1)
        self.assertEqual([endpoint for endpoint, _ in self.github.writes].count("pulls"), 1)

    def test_unknown_pr_outcome_is_not_sent_again_without_read_evidence(self):
        self.github.drop_pr_before_creation = True
        self.assertIsNone(self.publish())
        self.github.drop_pr_before_creation = False
        self.assertIsNone(self.publish())
        self.assertEqual([endpoint for endpoint, _ in self.github.writes].count("pulls"), 1)

    def test_restart_finds_closed_draft_without_reposting(self):
        self.assertEqual(self.publish(), PR_URL)
        self.github.pull["state"] = "closed"
        self.assertEqual(self.publish(), PR_URL)
        self.assertEqual([endpoint for endpoint, _ in self.github.writes].count("pulls"), 1)

    def test_existing_ref_with_unexpected_head_is_rejected_without_writes(self):
        contract_prefix = self.state["contract_sha256"][:12]
        branch = f"refs/heads/codex/tel99-acceptance/{ISSUE}-mission-A-{contract_prefix}"
        self.github.refs[branch] = "f" * 40
        self.assertIsNone(self.publish())
        self.assertEqual(self.github.writes, [])

    def test_ref_changed_after_creation_is_never_published_as_a_draft(self):
        self.github.advance_head_after_first_read = True
        self.assertIsNone(self.publish())
        self.assertNotIn("pulls", [endpoint for endpoint, _ in self.github.writes])

    def test_existing_pr_for_same_head_and_wrong_base_is_rejected(self):
        self.assertEqual(self.publish(), PR_URL)
        self.github.pull["base"]["ref"] = "main"
        self.github.writes.clear()
        self.assertIsNone(self.publish())
        self.assertEqual(self.github.writes, [])

    def test_refuses_unexpected_diff_before_creating_a_ref_or_pr(self):
        self.github.force_wrong_diff = True
        self.assertIsNone(self.publish())
        self.assertEqual([path for path, _ in self.github.writes], ["git/blobs", "git/trees", "git/commits"])

    def test_refuses_an_advanced_base_before_taking_any_remote_write(self):
        self.github.refs[f"refs/heads/{BASE}"] = "9" * 40
        self.assertIsNone(self.publish())
        self.assertEqual(self.github.writes, [])

    def test_refuses_wrong_repository_base_pin_and_issue_proof_without_writes(self):
        inputs = ({"repo": "another/repo"}, {"base": "main"}, {"base_sha": "f" * 40},
                  {"proof": PROOF.replace(f"issues/{ISSUE}", "issues/777")},
                  {"proof": PROOF.replace("https://github.com", "https://example.test")})
        for arguments in inputs:
            with self.subTest(arguments=arguments):
                self.assertIsNone(self.publish(**arguments))
        self.assertEqual(self.github.writes, [])

    def test_refuses_a_mission_binding_for_another_issue_or_base(self):
        key = "kilo-github/approvals/mission-A"
        binding = self.store.get(key)
        for field, change in (("issue", CONTROL_ISSUE), ("base", "main"), ("base_sha", "9" * 40)):
            with self.subTest(field=field):
                self.store.put(key, {**binding, field: change})
                self.assertIsNone(self.publish())
        self.assertEqual(self.github.writes, [])

    def test_refuses_mismatched_artifact_or_cost_even_in_the_durable_checkpoint(self):
        original = deepcopy(self.state)
        for section, field, change in (("result", "artifact", "different"),
                                       ("verification", "verifier", "self-approved")):
            with self.subTest(field=field):
                self.state = deepcopy(original)
                self.state[section][field] = change
                self.store.put("kilo-local/mission-A", self.state)
                self.assertIsNone(self.publish())
        self.state = deepcopy(original)
        self.state["result"]["provider_evidence"]["cost_usd"] = None
        self.store.put("kilo-local/mission-A", self.state)
        self.assertIsNone(self.publish())
        self.assertEqual(self.github.writes, [])

    def test_refuses_untrusted_or_edited_evidence(self):
        original = deepcopy(self.github.proof)
        for field, change in (("user", {"login": OWNER["login"], "id": 7, "type": "User"}),
                              ("updated_at", "2026-11-21T12:01:00Z"),
                              ("body", original["body"].replace(ARTIFACT_SHA, "9" * 64))):
            with self.subTest(field=field):
                self.github.proof = {**original, field: change}
                self.assertIsNone(self.publish())
        self.assertEqual(self.github.writes, [])


if __name__ == "__main__":
    unittest.main()
