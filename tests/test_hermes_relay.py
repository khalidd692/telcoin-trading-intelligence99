"""Offline tests for the Hermes failover relay adapter (GitHub -> #124 engine).

Covers authenticated admission, executor contract/quota/cost gates, the fixed
independent verifier, engine resume semantics with owner=hermes, and
idempotent GitHub publication. No network, no model call, no paid provider.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from scripts.agents.automation.autonomy_runtime import Runtime, seal, fingerprint
from scripts.agents.automation import github_mission_source as gms
from scripts.agents.automation import hermes_github_adapter as hga
from scripts.agents.automation.github_mission_source import (
    parse_approvals, fetch_mandate, EVENT_MARKER,
)
from scripts.agents.automation.hermes_executor import (
    HermesExecutor, ExecutorUnavailable, FREE_MODELS,
)
from scripts.agents.automation import hermes_verifier
from scripts.agents.automation.hermes_github_adapter import build_runtime, event_body

MANDATE = 7024804657
SESSION = "local-" + "a" * 64


def mission(i="HERMES-RELAY-TEST-A", **kw):
    m = dict(id=i, project="synthetic", owner="hermes", priority="P0",
             dependencies=[], specialist="tel99-analyst", synthetic_data=True,
             objective="Return exactly OK",
             expected_sha256=hashlib.sha256(b"OK").hexdigest())
    m.update(kw)
    return m


def ok_result(m=None):
    m = m or mission()
    return {"artifact": "OK", "sha256": hashlib.sha256(b"OK").hexdigest(),
            "specialist_id": m["specialist"], "provider": "hermes-nous-free",
            "model": FREE_MODELS[0], "session_id": SESSION,
            "provider_evidence": {
                "model": FREE_MODELS[0], "billing_provider": "nous",
                "estimated_cost_usd": 0.0, "actual_cost_usd": 0.0,
                "cost_status": "unknown", "input_tokens": 10, "output_tokens": 2,
                "api_call_count": 1, "exit_code": 0, "session_id": SESSION}}


def approval_comment(m, login="khalidd692", cid=1, expires_in=3600,
                     mandate=MANDATE, tamper=False):
    fp = fingerprint(m)
    if tamper:
        m = dict(m, objective="modified after approval")
    expires = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {"mission": m, "approval": {
        "approver": login, "mandate_comment_id": mandate,
        "expires_at": expires, "mission_sha256": fp}}
    body = ("Approbation synthétique.\n```hermes-mission/v1\n"
            + json.dumps(payload, ensure_ascii=True) + "\n```")
    return {"id": cid, "user": {"login": login}, "body": body}


class SourceTests(unittest.TestCase):
    def parse(self, comments, **kw):
        return parse_approvals(comments, mandate_comment_id=MANDATE, **kw)

    def test_valid_owner_approval_admitted(self):
        m = mission()
        data = self.parse([approval_comment(m)])
        self.assertEqual(data["missions"], [m])
        self.assertEqual(data["approvals"][m["id"]], fingerprint(m))
        self.assertEqual(data["sources"][m["id"]], 1)

    def test_non_owner_ignored(self):
        self.assertEqual(self.parse([approval_comment(mission(), login="intruder")])["missions"], [])

    def test_event_marker_ignored(self):
        c = approval_comment(mission())
        c["body"] = "```" + EVENT_MARKER + "\n{}\n```\n" + c["body"]
        self.assertEqual(self.parse([c])["missions"], [])

    def test_expired_ignored(self):
        self.assertEqual(self.parse([approval_comment(mission(), expires_in=-10)])["missions"], [])

    def test_wrong_mandate_ignored(self):
        self.assertEqual(self.parse([approval_comment(mission(), mandate=1)])["missions"], [])

    def test_tampered_fingerprint_ignored(self):
        self.assertEqual(self.parse([approval_comment(mission(), tamper=True)])["missions"], [])

    def test_kilo_owner_not_admitted_here(self):
        self.assertEqual(self.parse([approval_comment(mission(owner="kilo"))])["missions"], [])

    def test_duplicate_id_once(self):
        m = mission()
        data = self.parse([approval_comment(m, cid=1), approval_comment(m, cid=2)])
        self.assertEqual(len(data["missions"]), 1)

    def test_invalid_json_ignored(self):
        c = {"id": 9, "user": {"login": "khalidd692"},
             "body": "```hermes-mission/v1\n{not json}\n```"}
        self.assertEqual(self.parse([c])["missions"], [])

    def test_cap_20(self):
        comments = [approval_comment(mission(f"HERMES-RELAY-T-{i:02d}"), cid=i) for i in range(25)]
        self.assertEqual(len(self.parse(comments)["missions"]), 20)

    def test_mandate_not_owner_raises(self):
        with self.assertRaises(ValueError):
            fetch_mandate("r/x", 67, MANDATE,
                          fetcher=lambda ep: {"user": {"login": "intruder"}})

    def test_source_fail_closed_via_poll(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Runtime(Path(tmp), executor=lambda m: ok_result(m))
            def offline():
                raise OSError("github down")
            self.assertFalse(r.poll(offline))
            self.assertEqual(r.status()["state"], "BLOCKED")


FAKE_OK = (
    "import sys\n"
    "print('OK')\n"
    f"print('session_id: {SESSION}', file=sys.stderr)\n"
)
FAKE_429 = (
    "import os, sys\n"
    "open(os.environ['FAKE_COUNTER'], 'a').write('x')\n"
    "print('HTTP 429 Too Many Requests: fair-share limit', file=sys.stderr)\n"
    "sys.exit(1)\n"
)
FAKE_NO_SESSION = "print('OK')\n"


def usage_stub(home, session_id):
    return dict(ok_result()["provider_evidence"])


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ok = self.root / "fake_ok.py"
        self.ok.write_text(FAKE_OK)
        self.rate = self.root / "fake_429.py"
        self.rate.write_text(FAKE_429)
        self.no_session = self.root / "fake_no_session.py"
        self.no_session.write_text(FAKE_NO_SESSION)

    def exe(self, script, **kw):
        return HermesExecutor(root=self.root, cli_command=[sys.executable, str(script)],
                              usage_reader=usage_stub, **kw)

    def test_success_evidence(self):
        res = self.exe(self.ok).execute(mission())
        self.assertEqual(res["artifact"], "OK")
        self.assertEqual(res["sha256"], hashlib.sha256(b"OK").hexdigest())
        self.assertEqual(res["session_id"], SESSION)
        self.assertEqual(res["provider_evidence"]["estimated_cost_usd"], 0.0)
        self.assertEqual(res["provider_evidence"]["exit_code"], 0)

    def test_contract_gate(self):
        with self.assertRaises(ExecutorUnavailable):
            self.exe(self.ok).execute(mission(synthetic_data=False))

    def test_model_allowlist_gate(self):
        with self.assertRaises(ExecutorUnavailable):
            self.exe(self.ok, model="paid/model").execute(mission())

    def test_429_cooldown_no_retry_loop(self):
        counter = self.root / "calls.txt"
        os.environ["FAKE_COUNTER"] = str(counter)
        try:
            exe = self.exe(self.rate)
            with self.assertRaisesRegex(ExecutorUnavailable, "BLOCKED_PROVIDER_RATE_LIMIT"):
                exe.execute(mission())
            self.assertTrue(exe.cooldown_path.exists())
            with self.assertRaisesRegex(ExecutorUnavailable, "BLOCKED_PROVIDER_COOLDOWN"):
                exe.execute(mission())
            self.assertEqual(counter.read_text(), "x")  # exactly one real attempt
        finally:
            os.environ.pop("FAKE_COUNTER", None)

    def test_nonzero_cost_refused(self):
        def paid(home, sid):
            row = usage_stub(home, sid)
            row["estimated_cost_usd"] = 0.5
            return row
        exe = HermesExecutor(root=self.root, cli_command=[sys.executable, str(self.ok)],
                             usage_reader=paid)
        with self.assertRaisesRegex(ExecutorUnavailable, "COST_UNKNOWN_OR_NONZERO_REFUSED"):
            exe.execute(mission())

    def test_missing_session_refused(self):
        with self.assertRaisesRegex(ExecutorUnavailable, "HERMES_SESSION_ID_MISSING"):
            self.exe(self.no_session).execute(mission())

    def test_missing_cost_evidence_refused(self):
        exe = HermesExecutor(root=self.root, cli_command=[sys.executable, str(self.ok)],
                             usage_reader=lambda h, s: None)
        with self.assertRaisesRegex(ExecutorUnavailable, "HERMES_COST_EVIDENCE_UNAVAILABLE"):
            exe.execute(mission())


class VerifierTests(unittest.TestCase):
    def test_ok(self):
        report = hermes_verifier.verify(mission(), ok_result())
        self.assertTrue(report["ok"])
        self.assertEqual(report["verifier"], "hermes-fixed-subprocess-v1")
        self.assertTrue(all(c["ok"] for c in report["checks"]))

    def test_sha_mismatch(self):
        res = ok_result()
        res["artifact"] = "NOT OK"
        self.assertFalse(hermes_verifier.verify(mission(), res)["ok"])

    def test_cost_nonzero(self):
        res = ok_result()
        res["provider_evidence"]["estimated_cost_usd"] = 0.01
        self.assertFalse(hermes_verifier.verify(mission(), res)["ok"])

    def test_bad_session(self):
        res = ok_result()
        res["session_id"] = "forged"
        self.assertFalse(hermes_verifier.verify(mission(), res)["ok"])


class RuntimeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.calls = []

    def execute(self, m):
        self.calls.append(m["id"])
        return ok_result(m)

    def runtime(self):
        return Runtime(self.root, executor=self.execute, verifier=hermes_verifier.verify)

    def test_hermes_owner_chain_memory_restart(self):
        a = mission()
        b = mission("HERMES-RELAY-TEST-B", dependencies=[a["id"]], specialist="tel99-dev")
        r = self.runtime()
        r.run_queue([a, b], seal([a, b]))
        self.assertEqual(self.calls, [a["id"], b["id"]])
        self.assertEqual(r.state(a)["status"], "ACCEPTED")
        self.assertEqual(r.state(b)["status"], "ACCEPTED")
        self.assertTrue(any((self.root / "memory").rglob("*.json")))
        newer = self.runtime()
        newer.run_queue([a, b], seal([a, b]))
        self.assertEqual(len(self.calls), 2)  # no duplicate execution after restart

    def test_running_crash_never_replays(self):
        a = mission()
        r = self.runtime()
        r.claim(a)
        r.save(a, "RUNNING")
        r.run_queue([a], seal([a]))
        self.assertEqual(self.calls, [])
        self.assertEqual(r.state(a)["status"], "AWAITING_HUMAN")

    def test_worker_exited_resume_verifies_without_new_call(self):
        a = mission()
        r = self.runtime()
        r.claim(a)
        r.save(a, "WORKER_EXITED", result=ok_result(a))
        r.run_queue([a], seal([a]))
        self.assertEqual(self.calls, [])
        self.assertEqual(r.state(a)["status"], "ACCEPTED")


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.published = []

    def fake_publisher(self, body):
        self.published.append(body)
        return f"https://github.com/fake#{len(self.published)}"

    def test_ack_and_terminal_dedupe_restart(self):
        r, pub = build_runtime(self.root, issue=94, publisher=self.fake_publisher)
        a = mission()
        r.claim(a)
        ack = r.inbox.receive({"request_id": a["id"]})
        self.assertTrue(ack["accepted"])
        self.assertEqual(len(self.published), 1)
        self.assertIn("ACK", self.published[0])
        r.save(a, "ACCEPTED", result=ok_result(a))
        pub.sync()
        self.assertEqual(len(self.published), 2)
        self.assertIn("ACCEPTED", self.published[1])
        # restart: durable CAS dedupe -> no new publication
        r2, pub2 = build_runtime(self.root, issue=94, publisher=self.fake_publisher)
        r2.inbox.receive({"request_id": a["id"]})
        pub2.sync()
        self.assertEqual(len(self.published), 2)
        self.assertTrue((self.root / "relay-events.jsonl").exists())
        for body in self.published:
            self.assertIn(EVENT_MARKER, body)
            self.assertIn("récepteur Hermes", body)  # legacy receiver skip marker

    def test_publish_outage_retries_later(self):
        state = {"down": True}
        def flaky(body):
            if state["down"]:
                raise OSError("github down")
            return self.fake_publisher(body)
        r, pub = build_runtime(self.root, issue=94, publisher=flaky)
        a = mission()
        r.claim(a)
        r.inbox.receive({"request_id": a["id"]})
        r.save(a, "ACCEPTED", result=ok_result(a))
        pub.sync()
        self.assertEqual(self.published, [])  # nothing recorded while down
        state["down"] = False
        pub.sync()
        self.assertEqual(len(self.published), 2)  # ACK + ACCEPTED retried
        pub.sync()
        self.assertEqual(len(self.published), 2)  # then deduped

    def test_build_runtime_executor_is_callable(self):
        r, _ = build_runtime(self.root, issue=94, publisher=self.fake_publisher)
        self.assertTrue(callable(r.executor))  # regression: instance vs bound method
        self.assertTrue(callable(r.verifier))

    def test_no_publish_mode_still_journals(self):
        r, pub = build_runtime(self.root, issue=94, publisher=self.fake_publisher, publish=False)
        a = mission()
        r.claim(a)
        r.inbox.receive({"request_id": a["id"]})
        r.save(a, "ACCEPTED", result=ok_result(a))
        pub.sync()
        self.assertEqual(self.published, [])
        self.assertTrue((self.root / "relay-events.jsonl").exists())


class ReviewHardeningTests(unittest.TestCase):
    """Réserves F3/F4/F5 de la revue indépendante SUPPORT (sa-0-4cb76064)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.published = []

    def fake_publisher(self, body):
        self.published.append(body)
        return f"https://github.com/fake#{len(self.published)}"

    def test_f5_executor_rejects_bad_id_direct_call(self):
        exe = HermesExecutor(root=self.root, cli_command=[sys.executable, "unused"],
                             usage_reader=usage_stub)
        with self.assertRaisesRegex(ExecutorUnavailable, "Invalid mission id"):
            exe.execute(mission(i="../escape"))

    def test_f3_scan_recovers_existing_event_without_repost(self):
        r, _ = build_runtime(self.root, issue=94, publisher=self.fake_publisher,
                             scan=lambda: {("HERMES-RELAY-TEST-A", "ACK"): "https://github.com/existing#1"})
        a = mission()
        r.claim(a)
        r.inbox.receive({"request_id": a["id"]})
        self.assertEqual(self.published, [])  # no duplicate POST
        rec = r.store.get("hermes-relay-published/HERMES-RELAY-TEST-A/ACK")
        self.assertIsNotNone(rec)
        self.assertTrue(rec["recovered"])
        self.assertEqual(rec["url"], "https://github.com/existing#1")

    def test_f3_scan_unavailable_defers_publication(self):
        state = {"down": True}
        r, pub = build_runtime(self.root, issue=94, publisher=self.fake_publisher,
                               scan=lambda: None if state["down"] else {})
        a = mission()
        r.claim(a)
        r.inbox.receive({"request_id": a["id"]})
        r.save(a, "ACCEPTED", result=ok_result(a))
        pub.sync()
        self.assertEqual(self.published, [])  # never blind-post while scan is down
        state["down"] = False
        pub.sync()
        self.assertEqual(len(self.published), 2)

    def test_f3_existing_events_parses_and_fail_closed(self):
        body = event_body("M1", "ACK", {"contract_sha256": "x"}, issue=94)
        comments = [{"id": 1, "body": body, "html_url": "u1"}, {"id": 2, "body": "no block"}]
        found = hga.existing_events("x/y", 94, fetcher=lambda ep: comments)
        self.assertIsNotNone(found)
        self.assertEqual(found[("M1", "ACK")], "u1")
        def boom(ep):
            raise OSError("down")
        self.assertIsNone(hga.existing_events("x/y", 94, fetcher=boom))

    def test_f4_journal_no_duplicate_lines_after_restart(self):
        r, pub = build_runtime(self.root, issue=94, publisher=self.fake_publisher)
        a = mission()
        r.claim(a)
        r.save(a, "ACCEPTED", result=ok_result(a))
        pub.sync()
        r2, pub2 = build_runtime(self.root, issue=94, publisher=self.fake_publisher)
        pub2.sync()
        lines = (self.root / "relay-events.jsonl").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)


class TimeoutFailClosedTests(unittest.TestCase):
    """Review indépendante F1/F2 : tout timeout gh doit rester fail-closed."""

    def test_fetcher_timeout_maps_to_oserror(self):
        with mock.patch.object(gms.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("gh", 60)):
            with self.assertRaises(OSError):
                gms.default_fetcher("repos/x/y/issues/1/comments")

    def test_publish_timeout_maps_to_oserror(self):
        with mock.patch.object(hga.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("gh", 60)):
            with self.assertRaises(OSError):
                hga.publish_comment("x/y", 94, "body")

    def test_poll_timeout_fail_closed_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Runtime(Path(tmp), executor=lambda m: ok_result(m))
            with mock.patch.object(gms.subprocess, "run",
                                   side_effect=subprocess.TimeoutExpired("gh", 60)):
                self.assertFalse(r.poll(lambda: gms.github_source("x/y", 94, 67, MANDATE)))
            self.assertEqual(r.status()["state"], "BLOCKED")


class Phase2Tests(unittest.TestCase):
    """GO phase 2 : pagination >300, coût strictement nul, frontière d'approbation."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_pagination_beyond_300_admits_late_mission(self):
        m = mission("HERMES-RELAY-LATE-320")
        comments = [{"id": i, "user": {"login": "khalidd692"}, "body": f"noise {i}"}
                    for i in range(350)]
        comments[320] = approval_comment(m, cid=320)
        def fetcher(ep):
            page = int(ep.rsplit("page=", 1)[1])
            return comments[(page - 1) * 100:page * 100]
        traversed = gms.fetch_comments("x/y", 94, fetcher=fetcher)
        self.assertEqual(len(traversed), 350)
        data = gms.parse_approvals(traversed, mandate_comment_id=MANDATE)
        self.assertEqual([x["id"] for x in data["missions"]], [m["id"]])

    def test_pagination_cap_fail_closed(self):
        def fetcher(ep):
            return [{"id": 1, "user": {"login": "khalidd692"}, "body": "x"}] * 100
        with self.assertRaises(ValueError):
            gms.fetch_comments("x/y", 94, fetcher=fetcher)

    def test_existing_events_sees_late_pages(self):
        body = event_body("M-LATE", "ACCEPTED", {"contract_sha256": "z"}, issue=94)
        comments = [{"id": i, "body": "noise"} for i in range(310)]
        comments[305] = {"id": 305, "body": body, "html_url": "u-late"}
        def fetcher(ep):
            page = int(ep.rsplit("page=", 1)[1])
            return comments[(page - 1) * 100:page * 100]
        found = hga.existing_events("x/y", 94, fetcher=fetcher)
        self.assertIsNotNone(found)
        self.assertEqual(found[("M-LATE", "ACCEPTED")], "u-late")

    def test_executor_unknown_actual_cost_refused(self):
        fake = self.root / "fake_ok.py"
        fake.write_text(FAKE_OK)
        def unknown(home, sid):
            row = usage_stub(home, sid)
            row["actual_cost_usd"] = None  # coût réel INCONNU != preuve de zéro
            return row
        exe = HermesExecutor(root=self.root, cli_command=[sys.executable, str(fake)],
                             usage_reader=unknown)
        with self.assertRaisesRegex(ExecutorUnavailable, "COST_UNKNOWN_OR_NONZERO_REFUSED"):
            exe.execute(mission())

    def test_verifier_unknown_actual_cost_not_ok(self):
        res = ok_result()
        res["provider_evidence"]["actual_cost_usd"] = None
        self.assertFalse(hermes_verifier.verify(mission(), res)["ok"])

    def _with_origin(self, comment, origin):
        payload = json.loads(gms.BLOCK_RE.search(comment["body"]).group(1))
        payload["approval"]["origin"] = origin
        comment["body"] = ("```hermes-mission/v1\n"
                           + json.dumps(payload, ensure_ascii=True) + "\n```")
        return comment

    def test_owner_direct_requires_local_artifact(self):
        m = mission("HERMES-RELAY-OD")
        c = self._with_origin(approval_comment(m), "owner-direct")
        self.assertEqual(gms.parse_approvals([c], mandate_comment_id=MANDATE)["missions"], [])
        bad = lambda mid: {"approved_by": "khalidd692", "channel": "owner-local",
                           "mission_sha256": "0" * 64}
        self.assertEqual(gms.parse_approvals([c], mandate_comment_id=MANDATE,
                                             owner_approval_reader=bad)["missions"], [])
        good = lambda mid: {"approved_by": "khalidd692", "channel": "owner-local",
                            "mission_sha256": fingerprint(m)}
        data = gms.parse_approvals([c], mandate_comment_id=MANDATE,
                                   owner_approval_reader=good)
        self.assertEqual([x["id"] for x in data["missions"]], [m["id"]])

    def test_invalid_origin_ignored(self):
        c = self._with_origin(approval_comment(mission()), "self-granted")
        self.assertEqual(gms.parse_approvals([c], mandate_comment_id=MANDATE)["missions"], [])

    def test_delegated_origin_explicit_ok(self):
        c = self._with_origin(approval_comment(mission()), "delegated-mandate")
        self.assertEqual(len(gms.parse_approvals([c], mandate_comment_id=MANDATE)["missions"]), 1)

    def test_proposal_never_admitted(self):
        body = hga.build_proposal_body([{"id": "I-02", "title": "memoire"}])
        c = {"id": 1, "user": {"login": "khalidd692"}, "body": body}
        self.assertIn("PROPOSED", body)
        self.assertEqual(gms.parse_approvals([c], mandate_comment_id=MANDATE)["missions"], [])

    def test_session_executed_counts_only_fresh(self):
        now = time.time()
        states = [{"id": "OLD", "status": "ACCEPTED", "at": now - 100},
                  {"id": "NEW", "status": "ACCEPTED", "at": now + 1},
                  {"id": "ACKED", "status": "ACK", "at": now + 1},
                  {"id": "RUN", "status": "RUNNING", "at": now + 1}]
        self.assertEqual(hga.session_executed(states, now), {"NEW", "RUN"})

    def test_poll_max_tasks_passthrough(self):
        calls = []
        r = Runtime(self.root, executor=lambda m: (calls.append(m["id"]), ok_result(m))[1])
        a = mission("HERMES-RELAY-MT-A")
        b = mission("HERMES-RELAY-MT-B")
        r.poll(lambda: {"missions": [a, b], "approvals": seal([a, b])}, max_tasks=1)
        self.assertEqual(calls, [a["id"]])
        self.assertEqual(list(r.status()["missions"]), [a["id"]])

    def test_owner_approval_reader_read_only_and_bounded(self):
        reader = hga.owner_approval_reader_for(self.root)
        self.assertIsNone(reader("ABSENT"))
        self.assertIsNone(reader("../escape"))
        d = self.root / "owner-approvals"
        d.mkdir()
        (d / "HERMES-RELAY-X.json").write_text(json.dumps(
            {"approved_by": "khalidd692", "channel": "owner-local", "mission_sha256": "a" * 64}))
        self.assertEqual(reader("HERMES-RELAY-X")["channel"], "owner-local")


if __name__ == "__main__":
    unittest.main()
