"""Deterministic GitHub transport tests with the real supervisor and verifier."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from scripts.agents.automation.autonomy_runtime import fingerprint
from scripts.agents.automation import kilo_github_adapter as bridge
from scripts.agents.automation.kilo_executor import Executor, ProviderRateLimited
from scripts.agents.native.provider import ProviderError


ISSUE = 987
MANDATE = 7_100_000_000
OWNER = {"login": "khalidd692", "id": 275517051, "type": "User"}
PAST = "2026-01-01T00:00:00Z"


def expires():
    return (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def block(marker, payload):
    return f"```{marker}\n{json.dumps(payload)}\n```"


def comment(cid, body, user=None, issue=ISSUE):
    return {"id": cid, "body": body, "user": OWNER.copy() if user is None else user,
            "created_at": PAST, "updated_at": PAST,
            "issue_url": f"https://api.github.com/repos/{bridge.REPO}/issues/{issue}",
            "html_url": f"https://github.com/{bridge.REPO}/issues/{issue}#issuecomment-{cid}"}


def mission(mid="kilo-test-a", text="OK", **changes):
    return dict({"id": mid, "project": "synthetic", "owner": "kilo", "priority": "P0",
                 "dependencies": [], "specialist": "tel99-analyst", "synthetic_data": True,
                 "objective": f"Return exactly {text}", "expected_sha256": fingerprint_bytes(text)},
                **changes)


def fingerprint_bytes(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class GitHub:
    def __init__(self):
        self.mandate = comment(MANDATE, block("kilo-mandate/v1", {
            "repo": bridge.REPO, "issue": ISSUE, "label": "enhancement", "expires_at": expires()}))
        self.issue = {"number": ISSUE, "state": "open", "labels": [{"name": "enhancement"}]}
        self.comments = [self.mandate]
        self.posts = []
        self.lose_reply = False
        self.lose_evidence_reply = False
        self.unseen_post = False
        self.offline = False
        self.after_ack = None

    @property
    def pin(self):
        return fingerprint_bytes(self.mandate["body"])

    def approve(self, contract, **changes):
        approval = dict({"approver": OWNER["login"], "mandate_comment_id": MANDATE,
                         "expires_at": expires(), "mission_sha256": fingerprint(contract)}, **changes)
        row = comment(MANDATE + len(self.comments), block("kilo-mission/v1", {
            "mission": contract, "approval": approval}))
        self.comments.append(row)
        return row

    def fetch(self, endpoint):
        if self.offline:
            raise OSError("offline")
        prefix = f"repos/{bridge.REPO}/issues/"
        if endpoint == prefix + str(ISSUE):
            return self.issue
        if endpoint.startswith(prefix + f"{ISSUE}/comments?"):
            return self.comments
        cid = int(endpoint.removeprefix(prefix + "comments/"))
        return next((row for row in self.comments if row["id"] == cid), None)

    def post(self, body):
        event = json.loads(body.splitlines()[1])
        self.posts.append(event)
        row = comment(MANDATE + 10_000 + len(self.posts), body)
        if not self.unseen_post:
            self.comments.append(row)
        if event["phase"] == "ACK" and self.after_ack:
            self.after_ack()
        if self.lose_reply or (self.lose_evidence_reply and event["phase"] == "EVIDENCE"):
            self.lose_reply = False
            self.lose_evidence_reply = False
            raise OSError("response lost")
        return row


class FixtureProvider:
    def __init__(self, text):
        self.text = text
        self.last_completion_evidence = {"http_status": 200, "cost_usd": "0",
                                         "catalog_sha256": "a" * 64,
                                         "response_sha256": "b" * 64}

    def complete(self, **kwargs):
        return self.text


class KiloGitHubHandoffTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.gh = GitHub()
        self.calls = []
        self.pin = self.gh.pin

    def execute(self, contract):
        mid = contract["id"]
        self.assertTrue(any(e["mission_id"] == mid and e["phase"] == "ACK" for e in self.gh.posts))
        self.calls.append(mid)
        return Executor(provider=FixtureProvider(contract["objective"].removeprefix("Return exactly "))).execute(contract)

    def bridge(self, executor=None):
        runtime = bridge.Runtime(self.root, executor=executor or self.execute)
        return bridge.KiloGitHubHandoff(runtime, ISSUE, MANDATE, self.pin,
                                       fetcher=self.gh.fetch, publisher=self.gh.post)

    def test_two_tasks_in_order_and_correlated_remote_proofs(self):
        first = mission()
        a = self.gh.approve(first)
        self.gh.approve(first)
        self.gh.approve(mission("kilo-test-b", "SECOND", dependencies=[first["id"]]))
        handoff = self.bridge()
        self.assertTrue(handoff.poll())
        self.assertEqual(self.calls, ["kilo-test-a", "kilo-test-b"])
        self.assertEqual([e["phase"] for e in self.gh.posts],
                         ["ACK", "ACK", "EVIDENCE", "RESULT", "EVIDENCE", "RESULT"])
        events = [e for e in self.gh.posts if e["mission_id"] == first["id"]]
        for event in events:
            self.assertEqual(event["approval_comment_id"], a["id"])
            self.assertEqual(event["contract_sha256"], fingerprint(first))
            self.assertNotIn("artifact", event)
        self.assertEqual(events[0]["execution_status"], "NOT_STARTED")
        self.assertEqual(events[1]["artifact_sha256"], first["expected_sha256"])
        self.assertEqual(events[2]["status"], "ACCEPTED")
        self.assertTrue(self.bridge().poll())
        self.assertEqual(len(self.gh.posts), 6)
        self.assertEqual(len(self.calls), 2)

    def test_untrusted_malformed_edited_and_out_of_scope_comments(self):
        self.gh.approve(mission("spoof-login"))["user"]["id"] = 1
        self.gh.approve(mission("tampered"), mission_sha256="0" * 64)
        self.gh.approve(mission("expired"), expires_at=PAST)
        self.gh.approve(mission("wrong-scope", owner="hermes"))
        self.gh.approve(mission("extra-command", command="unsafe"))
        self.gh.approve(mission("wrong-issue"))["issue_url"] += "0"
        self.gh.approve(mission("edited"))["updated_at"] = expires()
        self.gh.approve(mission("quoted"))["body"] = "A discussion\n" + self.gh.comments[-1]["body"]
        self.gh.comments.append(comment(MANDATE + 99, block("kilo-mission/v1", [])))
        self.gh.approve(mission("conflicting-id"))
        self.gh.approve(mission("conflicting-id", "CHANGED"))
        self.assertTrue(self.bridge().poll())
        self.assertEqual(self.calls, [])
        self.assertEqual(self.gh.posts, [])

    def test_bad_mandate_pin_or_missing_issue_label_closes_queue(self):
        self.gh.approve(mission())
        handoff = self.bridge()
        self.gh.mandate["body"] += "\nChanged"
        self.assertFalse(handoff.poll())
        self.gh.mandate["body"] = self.gh.mandate["body"].removesuffix("\nChanged")
        self.gh.issue["labels"] = []
        self.assertFalse(handoff.poll())
        self.assertEqual(self.calls, [])
        self.assertEqual(self.gh.posts, [])

    def test_lost_ack_recovers_by_read_without_repost_or_early_execution(self):
        self.gh.approve(mission())
        self.gh.lose_reply = True
        first = self.bridge()
        first.poll()
        self.assertEqual(first.runtime.state(mission())["status"], "ACK")
        self.assertEqual(self.calls, [])
        self.assertTrue(self.bridge().poll())
        self.assertEqual(self.calls, ["kilo-test-a"])
        self.assertEqual([p["phase"] for p in self.gh.posts], ["ACK", "EVIDENCE", "RESULT"])

    def test_ambiguous_unseen_post_does_not_retry_and_fake_ack_cannot_unlock(self):
        self.gh.approve(mission())
        self.gh.lose_reply = True
        self.gh.unseen_post = True
        self.bridge().poll()
        fake = block("kilo-relay-event/v1", self.gh.posts[0])
        self.gh.comments.append(comment(MANDATE + 99, fake, user={"login": "intruder", "id": 1}))
        self.bridge().poll()
        self.assertEqual(len(self.gh.posts), 1)
        self.assertEqual(self.calls, [])

    def test_lost_evidence_reply_delays_accepted_result_until_reconciled(self):
        self.gh.approve(mission())
        self.gh.lose_evidence_reply = True
        self.assertFalse(self.bridge().poll())
        self.assertEqual([p["phase"] for p in self.gh.posts], ["ACK", "EVIDENCE"])
        self.assertTrue(self.bridge().poll())
        self.assertEqual([p["phase"] for p in self.gh.posts], ["ACK", "EVIDENCE", "RESULT"])
        self.assertEqual(self.gh.posts[-1]["status"], "ACCEPTED")
        self.assertIn("#issuecomment-", self.gh.posts[-1]["evidence_url"])
        self.assertEqual(self.calls, ["kilo-test-a"])

    def test_approval_removed_after_ack_blocks_effect(self):
        row = self.gh.approve(mission())
        self.gh.after_ack = lambda: self.gh.comments.remove(row)
        self.bridge().poll()
        self.assertEqual(self.calls, [])
        self.assertNotIn("ACCEPTED", [p["status"] for p in self.gh.posts])

    def test_offline_then_restart_fetches_without_replay(self):
        self.gh.approve(mission())
        self.gh.offline = True
        self.assertFalse(self.bridge().poll())
        self.gh.offline = False
        self.assertTrue(self.bridge().poll())
        self.assertTrue(self.bridge().poll())
        self.assertEqual(self.calls, ["kilo-test-a"])

    def test_verifier_rejects_wrong_artifact_and_dependency_does_not_run(self):
        contract = mission(expected_sha256=fingerprint_bytes("WRONG"))
        self.gh.approve(contract)
        self.gh.approve(mission("kilo-test-b", dependencies=[contract["id"]]))
        self.bridge().poll()
        self.assertEqual(self.calls, ["kilo-test-a"])
        self.assertEqual(self.gh.posts[-1]["phase"], "RESULT")
        self.assertEqual(self.gh.posts[-1]["status"], "REJECTED")

    def test_running_checkpoint_reconciles_without_replay(self):
        row = self.gh.approve(mission())
        adapter = self.bridge()
        adapter.runtime.executor = lambda m: (_ for _ in ()).throw(SystemExit(77))
        with self.assertRaises(SystemExit):
            adapter.poll()
        self.gh.comments.remove(row)
        self.bridge().poll()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.gh.posts[-1]["status"], "AWAITING_HUMAN")

    def test_stop_after_ack_prevents_worker(self):
        self.gh.approve(mission())
        self.gh.after_ack = lambda: (self.root / "stop.request").touch()
        self.bridge().poll()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.gh.posts[0]["phase"], "ACK")

    def test_quota_halts_following_independent_contract(self):
        self.gh.approve(mission())
        self.gh.approve(mission("kilo-test-b"))
        def rate_limited(contract):
            self.calls.append(contract["id"])
            raise bridge.QuotaBlocked()
        self.bridge(executor=rate_limited).poll()
        self.assertEqual(self.calls, ["kilo-test-a"])
        self.assertEqual(self.gh.posts[-1]["reason"], "BLOCKED_PROVIDER_RATE_LIMIT")

    def test_http_429_has_a_distinct_worker_result_without_retry(self):
        provider = Mock()
        provider.complete.side_effect = ProviderError("provider HTTP 429")
        with self.assertRaises(ProviderRateLimited):
            Executor(provider=provider).execute(mission())
        provider.complete.assert_called_once()

    def test_expired_deadline_after_ack_prevents_worker(self):
        self.gh.approve(mission())
        handoff = self.bridge()
        self.gh.after_ack = lambda: setattr(handoff.runtime, "deadline", 0.0)
        handoff.poll()
        self.assertEqual(self.calls, [])
        self.assertEqual(handoff.runtime.state(mission())["status"], "AWAITING_HUMAN")

    def test_inconsistent_verifier_output_cannot_be_accepted(self):
        self.gh.approve(mission())
        handoff = self.bridge()
        handoff.runtime.verifier = lambda m, r: {"ok": True, "checks": [{"ok": False}]}
        handoff.poll()
        self.assertEqual(self.gh.posts[-1]["status"], "REJECTED")

    def test_remote_ack_does_not_authorize_reexecution_in_fresh_state(self):
        self.gh.approve(mission())
        self.bridge().poll()
        self.root = self.root / "fresh"
        self.assertFalse(self.bridge().poll())
        self.assertEqual(self.calls, ["kilo-test-a"])
        self.assertEqual(len(self.gh.posts), 3)
