"""Offline checks for owner-approved GitHub local code missions and draft gates."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.agents.automation import github_local_code_campaign as bridge
from scripts.agents.automation import local_code_pr, local_team
from scripts.agents.automation.autonomy_runtime import Runtime, fingerprint

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/agents/TEL99_QWEN_REPAIR_QUEUE_20261123.json"
OWNER = {"login": "khalidd692", "id": 275517051, "type": "User"}
CONTROL = 240
FIRST = 241
SECOND = 242
MANDATE_ID = 4001
TIMES = ("2026-11-23T18:00:00Z", "2026-11-23T18:01:00Z",
         "2026-11-23T18:02:00Z")
EXPIRY = "2026-12-31T23:59:59Z"


def block(marker, payload):
    fence = chr(96) * 3
    return fence + marker + "\n" + json.dumps(payload, sort_keys=True) + "\n" + fence


def comment(cid, issue, body, timestamp):
    return {
        "id": cid, "user": OWNER.copy(), "body": body,
        "issue_url": f"https://api.github.com/repos/{bridge.REPO}/issues/{issue}",
        "html_url": f"https://github.com/{bridge.REPO}/issues/{issue}#issuecomment-{cid}",
        "created_at": timestamp, "updated_at": timestamp,
    }


class LocalFixture:
    def __init__(self):
        source = json.loads(SOURCE.read_bytes())["missions"]
        a = next(m for m in source if m["function"] == "kv_env").copy()
        b = next(m for m in source if m["function"] == "load_tasks").copy()
        a.update(id="tel99-pilot-code-a", team=local_team.TEAM.copy(),
                 model="qwen2.5-coder:7b", port=11434)
        b.update(id="tel99-pilot-code-b", team=local_team.TEAM.copy(),
                 model="qwen2.5-coder:7b", port=11434, dependencies=[a["id"]])
        self.missions = (a, b)
        self.scope = {
            "repo": bridge.REPO, "issue": CONTROL, "label": bridge.CODE_LABEL,
            "expires_at": EXPIRY, "base": bridge.BASE_REF, "base_sha": bridge.BASE_SHA,
            "contracts": {m["id"]: fingerprint(m) for m in self.missions},
        }
        self.mandate = comment(MANDATE_ID, CONTROL, block(bridge.MANDATE, self.scope), TIMES[0])
        self.pin = hashlib.sha256(self.mandate["body"].encode()).hexdigest()
        self.controller = {"number": CONTROL, "state": "open", "user": OWNER.copy()}
        self.issues = {}
        self.comments = []
        self.events = []
        for i, mission in enumerate(self.missions):
            issue = FIRST + i
            self.issues[issue] = {
                "number": issue, "state": "open", "user": OWNER.copy(),
                "labels": [{"name": bridge.CODE_LABEL}],
                "created_at": TIMES[1], "body": f"tel99-code-campaign: {MANDATE_ID}",
            }
            approval = {
                "approver": "khalidd692", "origin": "owner-direct",
                "mandate_comment_id": MANDATE_ID, "issue": issue,
                "mission_sha256": fingerprint(mission), "expires_at": EXPIRY,
            }
            self.comments.append(comment(
                5000 + issue, issue,
                block(bridge.APPROVAL, {"mission": mission, "approval": approval}), TIMES[2],
            ))

    def fetch(self, endpoint):
        start = f"repos/{bridge.REPO}/"
        if not endpoint.startswith(start):
            raise ValueError("unexpected endpoint")
        path = endpoint[len(start):]
        if path == f"issues/{CONTROL}":
            return self.controller
        if path == f"issues/comments/{MANDATE_ID}":
            return self.mandate
        if path == f"git/ref/heads/{bridge.BASE_REF}":
            return {"object": {"sha": bridge.BASE_SHA, "type": "commit"}}
        if path.startswith("issues?"):
            return [self.controller, *self.issues.values()]
        if path.startswith("issues/comments/"):
            cid = int(path.split("/")[-1])
            return next(c for c in self.comments if c["id"] == cid)
        if path.startswith("issues/") and "/comments" in path:
            issue = int(path.split("/")[1])
            return [c for c in self.comments
                    if c["issue_url"].endswith(f"/issues/{issue}")]
        if path.startswith("issues/"):
            return self.issues[int(path.split("/")[1])]
        raise ValueError("unexpected endpoint")

    def post(self, issue, body):
        event = json.loads(body.splitlines()[1])
        self.events.append(event)
        row = comment(9000 + len(self.events), issue, body, TIMES[2])
        self.comments.append(row)
        return row

    def handoff(self, runtime=None):
        return bridge.LocalCodeCampaign(
            runtime, CONTROL, MANDATE_ID, self.pin,
            fetcher=self.fetch, publisher=self.post,
        )


class LocalCodeGitHubTests(unittest.TestCase):
    def setUp(self):
        self.gh = LocalFixture()

    def test_owner_signed_two_issue_preflight(self):
        approved = self.gh.handoff().preflight()
        self.assertEqual({a["issue"] for a in approved}, {FIRST, SECOND})
        self.assertEqual({a["id"] for a in approved},
                         {m["id"] for m in self.gh.missions})

    def test_mandate_changed_or_expired_is_refused(self):
        self.gh.mandate["body"] += "\nchanged"
        with self.assertRaisesRegex(ValueError, "changed"):
            self.gh.handoff().preflight()
        self.gh = LocalFixture()
        self.gh.scope["expires_at"] = "2026-01-01T00:00:00Z"
        self.gh.mandate["body"] = block(bridge.MANDATE, self.gh.scope)
        self.gh.pin = hashlib.sha256(self.gh.mandate["body"].encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, "expiry"):
            self.gh.handoff().preflight()

    def test_untrusted_issues_and_approvals_cannot_enter(self):
        self.gh.issues[FIRST]["user"] = {"login": "attacker", "id": 3, "type": "User"}
        self.assertEqual(len(self.gh.handoff().preflight()), 1)
        self.gh = LocalFixture()
        self.gh.comments.append({**self.gh.comments[0], "id": 7777})
        with self.assertRaisesRegex(ValueError, "multiple approval"):
            self.gh.handoff().preflight()

    def test_code_scope_and_team_are_hard_guards(self):
        handler = self.gh.handoff()
        for wrong in (
            {"owner": "kilo"}, {"project": "synthetic"},
            {"team": ["tel99-dev"]}, {"base_sha": "f" * 40},
        ):
            with self.subTest(wrong=wrong):
                self.assertFalse(handler._mission_allowed(
                    {**self.gh.missions[0], **wrong}, self.gh.scope))

    def test_ack_precedes_execution_and_does_not_replay_uncertain_work(self):
        with tempfile.TemporaryDirectory() as folder:
            calls = []
            def executor(mission):
                calls.append(mission["id"])
                return {"artifact": "unverified"}
            runtime = Runtime(Path(folder), executor=executor,
                              verifier=lambda mission, result: {"unavailable": True})
            handoff = self.gh.handoff(runtime)
            queue = handoff.source()
            runtime.run_queue(queue["missions"], queue["approvals"])
            self.assertEqual(calls, [self.gh.missions[0]["id"]])
            self.assertEqual(self.gh.events[0]["phase"], "ACK")
            self.assertEqual(self.gh.events[0]["scope"], "approved-python-function")
            self.assertEqual(runtime.state(self.gh.missions[0])["status"], "AWAITING_HUMAN")
            runtime.run_queue(queue["missions"], queue["approvals"])
            self.assertEqual(len(calls), 1)
            # Recreate the supervisor instance against the same persisted CAS
            # state: an uncertain task must NOT be silently run again.
            restart = Runtime(Path(folder), executor=executor,
                              verifier=lambda mission, result: {"unavailable": True})
            self.gh.handoff(restart)
            restart.run_queue(queue["missions"], queue["approvals"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(restart.state(self.gh.missions[0])["status"], "AWAITING_HUMAN")

    def test_local_code_publisher_rejects_unverified_state(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Runtime(Path(folder)).store
            result = local_code_pr.publish_verified_code_pr(
                bridge.REPO, FIRST, bridge.BASE_REF, bridge.BASE_SHA,
                {"id": self.gh.missions[0]["id"], "status": "REJECTED"},
                "not-a-valid-evidence-url",
                api=lambda *args, **kwargs: self.fail("No GitHub call allowed"),
                store=store, root=folder,
            )
            self.assertIsNone(result)

    def test_pr_diff_must_be_single_modified_file(self):
        path = self.gh.missions[0]["path"]
        def response(n):
            return {"status": "ahead", "ahead_by": 1, "behind_by": 0,
                    "total_commits": 1, "commits": [{"sha": "b" * 40}],
                    "files": [{"filename": path, "status": "modified", "sha": "a" * 40}
                              for _ in range(n)]}
        with self.assertRaisesRegex(ValueError, "one approved"):
            local_code_pr._verify_code_diff(lambda _: response(2),
                                            bridge.BASE_SHA, "b" * 40,
                                            path, "a" * 40)
        local_code_pr._verify_code_diff(lambda _: response(1),
                                        bridge.BASE_SHA, "b" * 40, path, "a" * 40)


if __name__ == "__main__":
    unittest.main()
