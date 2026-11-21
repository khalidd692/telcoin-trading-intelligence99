"""Two-issue campaign tests with GitHub and provider fixtures."""
import json
from pathlib import Path
import tempfile
import unittest

from tests.test_kilo_acceptance_pr import GitHubFixture, PR_URL
from tests.test_kilo_github_handoff import (
    FixtureProvider, GitHub, ISSUE, MANDATE, OWNER, block, comment, expires,
    fingerprint_bytes, mission,
)
from scripts.agents.automation import kilo_github_adapter as bridge
from scripts.agents.automation.autonomy_runtime import fingerprint
from scripts.agents.automation.kilo_executor import Executor

FIRST = ISSUE + 1
SECOND = ISSUE + 2
BASE = bridge.ACCEPTANCE_BASE
BASE_SHA = bridge.ACCEPTANCE_BASE_SHA


class CampaignGitHub(GitHub):
    def __init__(self):
        super().__init__()
        self.first = mission("kilo-campaign-a")
        self.second = mission("kilo-campaign-b", "READY", specialist="tel99-dev",
                              dependencies=[self.first["id"]])
        self.mandate["body"] = block("kilo-campaign/v1", {
            "repo": bridge.REPO, "issue": ISSUE, "label": "enhancement",
            "expires_at": expires(), "base": BASE, "base_sha": BASE_SHA,
            "contracts": {m["id"]: fingerprint(m) for m in (self.first, self.second)},
        })
        self.issues = {ISSUE: self.issue}
        self.discovery_pages = None
        self.prs = []
        self.publish_blocked = False

    def add_issue(self, number, contract=None):
        issue = {
            "number": number, "state": "open", "user": OWNER.copy(),
            "created_at": "2026-01-01T00:00:01Z",
            "labels": [{"name": "enhancement"}], "body": f"kilo-campaign: {MANDATE}",
        }
        self.issues[number] = issue
        self.approve_issue(number, contract or self.first)
        return issue

    def approve_issue(self, number, contract):
        approval = {"approver": OWNER["login"], "mandate_comment_id": MANDATE,
                    "expires_at": expires(), "mission_sha256": fingerprint(contract),
                    "issue": number}
        row = comment(MANDATE + len(self.comments), block("kilo-mission/v1", {
            "mission": contract, "approval": approval}), issue=number)
        row["created_at"] = row["updated_at"] = "2026-01-01T00:00:02Z"
        self.comments.append(row)
        return row

    def fetch(self, endpoint):
        prefix = f"repos/{bridge.REPO}/issues"
        if endpoint.startswith(prefix + "?"):
            page = int(endpoint.split("page=")[-1])
            if self.discovery_pages is not None:
                return self.discovery_pages[page]
            return list(self.issues.values())
        if endpoint.startswith(prefix + "/comments/"):
            return super().fetch(endpoint)
        ends = endpoint.removeprefix(prefix + "/").split("/", 1)
        number = int(ends[0])
        if len(ends) == 1:
            return self.issues.get(number)
        return [row for row in self.comments if row["issue_url"].endswith(f"/issues/{number}")]

    def post_event_at(self, number, body):
        event = json.loads(body.splitlines()[1])
        self.posts.append(event)
        row = comment(MANDATE + 10_000 + len(self.posts), body, issue=number)
        self.comments.append(row)
        return row

    def publish_pr(self, repo, issue, base, base_sha, state, evidence_url, **kwargs):
        if self.publish_blocked:
            return None
        self.prs.append((issue, state["id"], evidence_url))
        return f"https://github.com/{repo}/pull/{issue + 100}"


class CampaignTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.gh = CampaignGitHub()
        self.calls = []

    def execute(self, contract):
        self.calls.append(contract["id"])
        text = contract["objective"].removeprefix("Return exactly ")
        return Executor(provider=FixtureProvider(text)).execute(contract)

    def handoff(self, executor=None):
        runtime = bridge.Runtime(self.root, executor=executor or self.execute)
        return bridge.KiloGitHubHandoff(
            runtime, ISSUE, MANDATE, self.gh.pin, campaign=True,
            fetcher=self.gh.fetch, publisher=self.gh.post_event_at,
            pr_publisher=self.gh.publish_pr,
        )

    def test_discovers_separate_issues_and_publishes_before_dependent_work(self):
        handoff = self.handoff()
        self.assertTrue(handoff.poll())
        self.assertEqual(self.calls, [])
        self.gh.add_issue(SECOND, self.gh.second)
        self.assertTrue(handoff.poll())
        self.assertEqual(self.calls, [])
        self.gh.add_issue(FIRST)
        self.assertTrue(handoff.poll())
        self.assertEqual(self.calls, [self.gh.first["id"], self.gh.second["id"]])
        self.assertEqual([(e["issue"], e["phase"]) for e in self.gh.posts],
                         [(i, p) for i in (FIRST, SECOND) for p in ("ACK", "EVIDENCE", "RESULT")])
        self.assertEqual([pr[0] for pr in self.gh.prs], [FIRST, SECOND])
        self.assertIn("/pull/", self.gh.posts[-1]["pull_request_url"])
        self.assertTrue(self.handoff().poll())
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(len(self.gh.posts), 6)
        self.assertEqual(len(self.gh.prs), 2)

    def test_pending_pr_pauses_dependent_worker_and_resumes_without_model_replay(self):
        self.gh.add_issue(FIRST)
        self.gh.add_issue(SECOND, self.gh.second)
        self.gh.publish_blocked = True
        self.assertFalse(self.handoff().poll())
        self.assertEqual(self.calls, [self.gh.first["id"]])
        self.assertEqual([e["phase"] for e in self.gh.posts], ["ACK", "EVIDENCE"])
        self.gh.publish_blocked = False
        self.assertTrue(self.handoff().poll())
        self.assertEqual(self.calls, [self.gh.first["id"], self.gh.second["id"]])

    def test_dependency_waits_for_actual_draft_publisher_and_receipt(self):
        self.gh.add_issue(FIRST)
        self.gh.add_issue(SECOND, self.gh.second)
        git = {FIRST: GitHubFixture(None), SECOND: GitHubFixture(None, pull_number=903)}
        active_issue = None

        def execute(contract):
            if contract == self.gh.second:
                self.assertTrue(git[FIRST].pull["draft"])
                self.assertTrue(any(event["phase"] == "RESULT" and event["issue"] == FIRST
                                    for event in self.gh.posts))
            return self.execute(contract)

        def api(endpoint, *, method="GET", payload=None):
            nonlocal active_issue
            if endpoint.startswith(f"repos/{bridge.REPO}/issues/comments/"):
                row = self.gh.fetch(endpoint)
                active_issue = int(row["issue_url"].split("/")[-1])
                return row
            return git[active_issue](endpoint, method=method, payload=payload)

        handoff = self.handoff(executor=execute)
        handoff.github = api
        handoff.pr_publisher = bridge.publish_verified_pr
        self.assertTrue(handoff.poll())
        self.assertEqual(self.calls, [self.gh.first["id"], self.gh.second["id"]])
        results = [event["pull_request_url"] for event in self.gh.posts if event["phase"] == "RESULT"]
        self.assertEqual(results, [PR_URL, f"https://github.com/{bridge.REPO}/pull/903"])
        self.assertEqual([git[i].blob for i in (FIRST, SECOND)], [b"OK", b"READY"])
        self.assertTrue(all(fixture.pull["draft"] and fixture.pull["base"]["ref"] == BASE
                            for fixture in git.values()))

    def test_excludes_forged_edited_cross_issue_old_and_unpinned_contracts(self):
        self.gh.add_issue(FIRST, mission("kilo-campaign-unpinned"))
        self.gh.add_issue(SECOND)["user"]["id"] += 1
        self.gh.add_issue(SECOND + 1)["created_at"] = self.gh.mandate["created_at"]
        self.gh.add_issue(SECOND + 2)["body"] = "Instructions libres à exécuter"
        self.gh.add_issue(SECOND + 3)["pull_request"] = {}
        candidate = self.gh.add_issue(SECOND + 4)
        row = self.gh.comments[-1]
        row["body"] = row["body"].replace(f'"issue": {candidate["number"]}', '"issue": 999')
        self.gh.add_issue(SECOND + 5)
        self.gh.comments[-1]["updated_at"] = expires()
        self.assertTrue(self.handoff().poll())
        self.assertEqual(self.calls, [])
        self.assertEqual(self.gh.posts, [])

    def test_rejects_reused_mission_identity_across_issues(self):
        self.gh.add_issue(FIRST)
        self.gh.add_issue(SECOND)
        self.assertFalse(self.handoff().poll())
        self.assertEqual(self.calls, [])
        self.assertEqual(self.gh.posts, [])

    def test_rejected_artifact_has_no_pr_and_blocks_dependency(self):
        self.gh.add_issue(FIRST)
        self.gh.add_issue(SECOND, self.gh.second)
        handoff = self.handoff(executor=lambda m: Executor(provider=FixtureProvider("WRONG")).execute(m))
        self.assertTrue(handoff.poll())
        self.assertEqual(self.gh.prs, [])
        self.assertEqual(self.gh.posts[-1]["status"], "REJECTED")
        self.assertEqual({e["issue"] for e in self.gh.posts}, {FIRST})

    def test_label_revoked_while_worker_runs_blocks_new_remote_effects(self):
        issue = self.gh.add_issue(FIRST)

        def revoke_label(contract):
            result = self.execute(contract)
            issue["labels"] = []
            return result

        handoff = self.handoff(executor=revoke_label)
        self.assertFalse(handoff.poll())
        self.assertEqual(handoff.runtime.state(self.gh.first)["status"], "ACCEPTED")
        self.assertEqual([event["phase"] for event in self.gh.posts], ["ACK"])
        self.assertEqual(self.gh.prs, [])
        issue["labels"] = [{"name": "enhancement"}]
        self.assertTrue(self.handoff().poll())
        self.assertEqual(self.calls, [self.gh.first["id"]])
        self.assertEqual([event["phase"] for event in self.gh.posts], ["ACK", "EVIDENCE", "RESULT"])

    def test_checkpointed_worker_resumes_verification_without_running_again(self):
        self.gh.add_issue(FIRST)
        self.gh.add_issue(SECOND, self.gh.second)
        original = self.handoff()

        def interrupt(*args):
            raise KeyboardInterrupt()

        original.runtime.verifier = interrupt
        with self.assertRaises(KeyboardInterrupt):
            original.poll()
        self.assertEqual(original.runtime.state(self.gh.first)["status"], "WORKER_EXITED")
        self.assertEqual(self.calls, [self.gh.first["id"]])
        self.assertTrue(self.handoff().poll())
        self.assertEqual(self.calls, [self.gh.first["id"], self.gh.second["id"]])
        self.assertEqual(len(self.gh.prs), 2)

    def test_quota_blocks_the_file_without_replay_or_publication(self):
        self.gh.add_issue(FIRST)
        self.gh.add_issue(SECOND, self.gh.second)

        def rate_limited(contract):
            self.calls.append(contract["id"])
            raise bridge.QuotaBlocked("429")

        handoff = self.handoff(executor=rate_limited)
        handoff.poll()
        self.assertTrue(handoff.runtime.quota_exhausted)
        self.assertTrue(self.handoff().poll())
        self.assertEqual(self.calls, [self.gh.first["id"]])
        self.assertEqual(self.gh.prs, [])
        self.assertEqual(self.gh.posts[-1]["reason"], "BLOCKED_PROVIDER_RATE_LIMIT")

    def test_discovery_never_executes_a_truncated_page(self):
        first = self.gh.add_issue(FIRST)
        self.gh.discovery_pages = {page: [first] * 100 for page in range(1, 4)}
        self.assertFalse(self.handoff().poll())
        self.assertEqual(self.calls, [])
        self.assertEqual(self.gh.posts, [])


if __name__ == "__main__":
    unittest.main()
