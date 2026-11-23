"""Offline checks for owner-approved GitHub local code missions and draft gates."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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
EXPIRY = "2099-12-31T23:59:59Z"
NEW_BASE_REF = "agents/tel99-code-base-recipe-20261123"
NEW_BASE_SHA = "a" * 40


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
    def __init__(self, *, base=bridge.BASE_REF, base_sha=bridge.BASE_SHA):
        source = json.loads(SOURCE.read_bytes())["missions"]
        a = next(m for m in source if m["function"] == "kv_env").copy()
        b = next(m for m in source if m["function"] == "load_tasks").copy()
        a.update(id="tel99-pilot-code-a", team=local_team.TEAM.copy(),
                 model="qwen2.5-coder:7b", port=11434, base_sha=base_sha)
        b.update(id="tel99-pilot-code-b", team=local_team.TEAM.copy(),
                 model="qwen2.5-coder:7b", port=11434, base_sha=base_sha,
                 dependencies=[a["id"]])
        self.missions = (a, b)
        self.scope = {
            "repo": bridge.REPO, "issue": CONTROL, "label": bridge.CODE_LABEL,
            "expires_at": EXPIRY, "base": base, "base_sha": base_sha,
            "contracts": {m["id"]: fingerprint(m) for m in self.missions},
        }
        self.mandate = comment(MANDATE_ID, CONTROL, block(bridge.MANDATE, self.scope), TIMES[0])
        self.pin = hashlib.sha256(self.mandate["body"].encode()).hexdigest()
        self.controller = {"number": CONTROL, "state": "open", "user": OWNER.copy()}
        self.remote_base_sha = base_sha
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
        if path == f"git/ref/heads/{self.scope['base']}":
            return {"object": {"sha": self.remote_base_sha, "type": "commit"}}
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

    def handoff(self, runtime=None, **options):
        return bridge.LocalCodeCampaign(
            runtime, CONTROL, MANDATE_ID, self.pin,
            fetcher=self.fetch, publisher=self.post, **options,
        )


class LocalCodeGitHubTests(unittest.TestCase):
    def setUp(self):
        self.gh = LocalFixture()

    def test_owner_signed_two_issue_preflight(self):
        approved = self.gh.handoff().preflight()
        self.assertEqual({a["issue"] for a in approved}, {FIRST, SECOND})
        self.assertEqual({a["id"] for a in approved},
                         {m["id"] for m in self.gh.missions})

    def test_new_campaign_base_requires_matching_explicit_pin_and_github_ref(self):
        fixture = LocalFixture(base=NEW_BASE_REF, base_sha=NEW_BASE_SHA)
        with self.assertRaises(ValueError):
            fixture.handoff().preflight()
        with self.assertRaises(ValueError):
            fixture.handoff(base_ref=NEW_BASE_REF)
        with self.assertRaises(ValueError):
            fixture.handoff(base_ref="main", base_sha=NEW_BASE_SHA)
        with self.assertRaises(ValueError):
            fixture.handoff(base_ref=NEW_BASE_REF, base_sha="refs/heads/main")
        campaign = fixture.handoff(base_ref=NEW_BASE_REF, base_sha=NEW_BASE_SHA)
        self.assertEqual(len(campaign.preflight()), 2)
        fixture.remote_base_sha = "b" * 40
        with self.assertRaises(ValueError):
            campaign.preflight()

    def test_ledger_pins_the_new_campaign_base_across_restarts(self):
        fixture = LocalFixture(base=NEW_BASE_REF, base_sha=NEW_BASE_SHA)
        with tempfile.TemporaryDirectory() as temp:
            options = {"base_ref": NEW_BASE_REF, "base_sha": NEW_BASE_SHA}
            fixture.handoff(Runtime(temp), **options)
            config = Runtime(temp).store.get(bridge.CONFIG_KEY)
            self.assertEqual((config["base_ref"], config["base_sha"]),
                             (NEW_BASE_REF, NEW_BASE_SHA))
            fixture.handoff(Runtime(temp), **options)
            with self.assertRaises(ValueError):
                fixture.handoff(Runtime(temp), base_ref=NEW_BASE_REF, base_sha="b" * 40)
            with self.assertRaises(ValueError):
                fixture.handoff(Runtime(temp))

    def test_controller_issue_must_be_owner_authored(self):
        self.gh.controller["user"]["id"] = 876
        with self.assertRaises(ValueError):
            self.gh.handoff().preflight()

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
            {"port": 8080}, {"model": "qwen2.5-coder-7b-instruct"},
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

    def test_restart_between_local_claim_and_inbox_ack(self):
        first = self.gh.missions[0]
        calls = []

        def executor(mission):
            self.assertEqual([event["phase"] for event in self.gh.events], ["ACK"])
            calls.append(mission["id"])
            return {"artifact": "unverified"}

        with tempfile.TemporaryDirectory() as folder:
            runtime = Runtime(folder, executor=executor, verifier=lambda *_: {"unavailable": True})
            handler = self.gh.handoff(runtime)
            with patch.object(runtime.inbox, "receive", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    handler.poll()
            self.assertIsNotNone(runtime.store.get(f"kilo-claims/{first['id']}"))
            self.assertEqual(self.gh.events, [])
            restart = Runtime(folder, executor=executor, verifier=lambda *_: {"unavailable": True})
            self.gh.handoff(restart).poll()
            self.assertEqual(calls, [first["id"]])

    def test_restart_after_inbox_ack_before_worker(self):
        first = self.gh.missions[0]
        calls = []
        with tempfile.TemporaryDirectory() as folder:
            runtime = Runtime(folder)
            handler = self.gh.handoff(runtime)
            save = runtime.save

            def stop_before_ack(mission, status, **details):
                if status == "ACK":
                    raise KeyboardInterrupt
                return save(mission, status, **details)

            with patch.object(runtime, "save", side_effect=stop_before_ack):
                with self.assertRaises(KeyboardInterrupt):
                    handler.poll()
            self.assertTrue(runtime.inbox.seen(first["id"]))
            self.assertEqual(self.gh.events, [])
            restart = Runtime(folder, executor=lambda mission: calls.append(mission["id"]),
                              verifier=lambda *_: {"unavailable": True})
            self.gh.handoff(restart).poll()
            self.assertEqual(calls, [first["id"]])
            self.assertEqual([event["phase"] for event in self.gh.events], ["ACK", "RESULT"])

    def test_interrupted_worker_remains_uncertain_and_never_unblocks_dependency(self):
        first, second = self.gh.missions
        with tempfile.TemporaryDirectory() as folder:
            calls = []

            def interrupted(mission):
                calls.append(mission["id"])
                raise KeyboardInterrupt

            handler = self.gh.handoff(Runtime(folder, executor=interrupted))
            with self.assertRaises(KeyboardInterrupt):
                handler.poll()
            self.assertEqual(handler.runtime.state(first)["status"], "RUNNING")
            restart = self.gh.handoff(Runtime(folder, executor=interrupted))
            restart.poll()
            self.assertEqual(calls, [first["id"]])
            self.assertEqual(restart.runtime.state(first)["status"], "AWAITING_HUMAN")
            self.assertEqual(restart.runtime.state(second), {})

    def test_lost_ack_response_is_reconciled_before_launch(self):
        first = self.gh.missions[0]
        calls = []
        with tempfile.TemporaryDirectory() as folder:
            def new_runtime():
                return Runtime(folder, executor=lambda mission: calls.append(mission["id"]),
                               verifier=lambda *_: {"unavailable": True})
            handler = self.gh.handoff(new_runtime())
            post = self.gh.post

            def lost_ack(issue, body):
                post(issue, body)
                raise OSError("response interrupted after recording ACK")

            handler.post = lost_ack
            self.assertFalse(handler.poll())
            self.assertEqual(calls, [])
            self.assertEqual(handler.runtime.state(first)["status"], "ACK")
            self.gh.handoff(new_runtime()).poll()
            self.assertEqual(calls, [first["id"]])
            self.assertEqual([event["phase"] for event in self.gh.events], ["ACK", "RESULT"])

    def test_accepted_checkpoint_resumes_publication_without_repeating_verification(self):
        from tests.test_local_code_pr_publisher import fixture

        first, second = self.gh.missions
        url = f"https://github.com/{bridge.REPO}/pull/805"
        calls = []
        checked = []
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as proofs:
            _, proof, _, _, _ = fixture(Path(proofs))

            def execute(mission):
                calls.append(mission["id"])
                return proof["result"] if mission == first else {}

            def verify(mission, result):
                checked.append(mission["id"])
                return proof["verification"] if mission == first else {"unavailable": True}

            handler = self.gh.handoff(Runtime(folder, executor=execute, verifier=verify))
            original_sync = handler.sync_results

            def interrupt_after_verification():
                if handler.runtime.state(first).get("status") == "ACCEPTED":
                    raise KeyboardInterrupt
                original_sync()

            with patch.object(handler, "sync_results", side_effect=interrupt_after_verification):
                with self.assertRaises(KeyboardInterrupt):
                    handler.poll()
            accepted = handler.runtime.state(first)
            self.assertEqual(accepted["status"], "ACCEPTED")
            self.assertEqual([(r["issue"], r["phase"]) for r in self.gh.events], [(FIRST, "ACK")])
            restart = Runtime(folder, executor=execute, verifier=verify)
            self.gh.handoff(restart, pr_publisher=lambda *args, **kwargs: url).poll()
            self.assertEqual(restart.state(first), accepted)
            self.assertEqual(calls, [first["id"], second["id"]])
            self.assertEqual(checked, calls)
            self.assertEqual([(r["issue"], r["phase"]) for r in self.gh.events[:4]],
                             [(FIRST, "ACK"), (FIRST, "EVIDENCE"),
                              (FIRST, "RESULT"), (SECOND, "ACK")])

    def test_exhausted_repairs_publish_failure_without_a_draft(self):
        from tests.test_local_code_pr_publisher import fixture

        first, second = self.gh.missions
        attempts = []
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as proofs:
            _, proof, _, _, _ = fixture(Path(proofs))
            verification = proof["verification"]
            verification.update(ok=False, feedback={"kind": "candidate-test"})
            verification["checks"][-1].update(ok=False, exit_code=1)

            def execute(mission):
                attempts.append(mission["id"])
                return proof["result"]

            handler = self.gh.handoff(
                Runtime(folder, executor=execute, verifier=lambda *_: verification),
                pr_publisher=lambda *args, **kwargs: self.fail("rejected code cannot create a draft"),
            )
            handler.poll()
            self.assertEqual(attempts, [first["id"], first["id"]])
            self.assertEqual(handler.runtime.state(first)["status"], "BLOCKED")
            self.assertEqual(handler.runtime.state(second), {})
            self.assertEqual([(r["issue"], r["phase"]) for r in self.gh.events],
                             [(FIRST, "ACK"), (FIRST, "EVIDENCE"), (FIRST, "RESULT")])
            self.assertEqual(self.gh.events[-1]["status"], "BLOCKED")

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
