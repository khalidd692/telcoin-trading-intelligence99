"""Offline tests for the Hermes failover relay adapter (GitHub -> #124 engine).

Covers authenticated admission, executor contract/quota/cost gates, the fixed
independent verifier, engine resume semantics with owner=hermes, and
idempotent GitHub publication. No network, no model call, no paid provider.
"""
import hashlib
import io
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
MANDATE_SHA = hashlib.sha256(b"GO synthetique").hexdigest()
OWNER = {"login": "khalidd692", "id": 275517051, "type": "User"}
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


class PreflightTests(unittest.TestCase):
    """Read-only preflight must not create state, call a model or publish."""

    def test_utf8_mandate_hash_and_admissions_without_runtime(self):
        with tempfile.TemporaryDirectory() as root:
            m = mission()
            mandate = {"user": {"login": "khalidd692"}, "body": "GO propriétaire: été ✅"}
            expected_sha = hashlib.sha256(mandate["body"].encode("utf-8")).hexdigest()
            with mock.patch(f"{hga.github_source.__module__}.default_fetcher", side_effect=[
                    mandate, [approval_comment(m)]]) as fetch, \
                 mock.patch.object(hga, "build_runtime",
                                   side_effect=AssertionError("preflight must not start runtime")), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as output:
                result = hga.main(["preflight", "--state", root, "--issue", "94",
                                   "--mandate-comment", str(MANDATE)])
            self.assertEqual(result, 0)
            data = json.loads(output.getvalue())
            self.assertEqual(data["preflight"], "OK")
            self.assertEqual(data["mandate_sha256"], expected_sha)
            self.assertEqual(data["missions"][0]["id"], m["id"])
            self.assertEqual(data["missions"][0]["contract_sha256"], seal([m])[m["id"]])
            self.assertEqual(fetch.call_count, 2)
            self.assertTrue(fetch.call_args_list[0].args[0].endswith(f"/issues/comments/{MANDATE}"))
            self.assertFalse(Path(root, "ledger").exists())

    def test_pinned_mandate_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            mandate = {"user": {"login": "khalidd692"}, "body": "modified"}
            with mock.patch(f"{hga.github_source.__module__}.default_fetcher", return_value=mandate) as fetch, \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as output:
                code = hga.main(["preflight", "--state", root, "--issue", "94",
                                 "--mandate-comment", str(MANDATE),
                                 "--mandate-sha256", "0" * 64])
            self.assertEqual(code, 2)
            fetch.assert_called_once()
            self.assertIn("does not match", output.getvalue())
            self.assertFalse(Path(root, "ledger").exists())

    def test_github_failure_reports_exact_error(self):
        with tempfile.TemporaryDirectory() as root:
            with mock.patch(f"{hga.github_source.__module__}.default_fetcher",
                                   side_effect=OSError("github unavailable")), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as output:
                code = hga.main(["preflight", "--state", root, "--issue", "94",
                                 "--mandate-comment", str(MANDATE)])
            self.assertEqual(code, 2)
            report = json.loads(output.getvalue())
            self.assertEqual(report["preflight"], "BLOCKED")
            self.assertEqual(report["error"], "OSError")
            self.assertIn("github unavailable", report["detail"])

    def test_empty_queue_reports_no_admissions(self):
        mandate = {"user": {"login": "khalidd692"}, "body": "GO"}
        with tempfile.TemporaryDirectory() as root, \
             mock.patch(f"{hga.github_source.__module__}.default_fetcher", side_effect=[mandate, []]), \
             mock.patch.object(hga, "build_runtime", side_effect=AssertionError("unexpected runtime")), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            code = hga.main(["preflight", "--state", root, "--issue", "94",
                             "--mandate-comment", str(MANDATE)])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.getvalue())["preflight"], "NO_ADMISSIONS")
            self.assertEqual(list(Path(root).iterdir()), [])


class SourceTests(unittest.TestCase):
    def test_historical_rejected_c_cannot_be_admitted_again(self):
        c = mission("HERMES-QWEN4-20261121-C")
        self.assertEqual(self.parse([approval_comment(c)])["missions"], [])

    def test_mandate_cannot_be_used_from_a_different_issue(self):
        comment = {"id": MANDATE, "body": "GO", "user": {"login": "khalidd692"},
                   "issue_url": "https://api.github.com/repos/x/y/issues/999"}
        with self.assertRaisesRegex(ValueError, "mandate issue"):
            fetch_mandate("x/y", 67, MANDATE, fetcher=lambda _: comment)

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

    def test_qwen_is_preferred_but_longcat_remains_available(self):
        self.assertEqual(FREE_MODELS[0], "qwen/qwen4-max:free")
        self.assertIn("meituan/longcat-2.5:free", FREE_MODELS)
        self.assertIn("upstage/solar-mini4:free", FREE_MODELS)
        self.assertEqual(self.exe(self.ok).model, FREE_MODELS[0])

    def test_qwen_unknown_actual_cost_is_blocked(self):
        def unknown_cost(home, session):
            row = usage_stub(home, session)
            row["actual_cost_usd"] = None
            return row
        exe = HermesExecutor(root=self.root, cli_command=[sys.executable, str(self.ok)],
                             usage_reader=unknown_cost)
        with self.assertRaisesRegex(ExecutorUnavailable, "COST_UNKNOWN_OR_NONZERO_REFUSED"):
            exe.execute(mission())

    def test_qwen_session_model_mismatch_is_blocked(self):
        def incorrect_model(home, session):
            row = usage_stub(home, session)
            row["model"] = "meituan/longcat-2.5:free"
            return row
        exe = HermesExecutor(root=self.root, cli_command=[sys.executable, str(self.ok)],
                             usage_reader=incorrect_model)
        with self.assertRaisesRegex(ExecutorUnavailable, "HERMES_MODEL_IDENTITY_MISMATCH"):
            exe.execute(mission())

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

    def test_429_blocks_other_models_on_same_provider_after_restart(self):
        counter = self.root / "calls.txt"
        with mock.patch.dict(os.environ, {"FAKE_COUNTER": str(counter)}):
            with self.assertRaisesRegex(ExecutorUnavailable, "BLOCKED_PROVIDER_RATE_LIMIT"):
                self.exe(self.rate).execute(mission())
            with self.assertRaisesRegex(ExecutorUnavailable, "BLOCKED_PROVIDER_COOLDOWN"):
                self.exe(self.rate, model=FREE_MODELS[1]).execute(mission("FRESH-MODEL"))
        self.assertEqual(counter.read_text(), "x")

    def test_legacy_model_cooldown_blocks_another_model(self):
        executor = self.exe(self.ok, model=FREE_MODELS[1])
        executor.cooldown_path.write_text(json.dumps({FREE_MODELS[0]: time.time() + 300}),
                                          encoding="utf-8")
        with self.assertRaisesRegex(ExecutorUnavailable, "BLOCKED_PROVIDER_COOLDOWN"):
            executor.execute(mission())

    def test_invalid_cooldown_state_blocks_worker(self):
        executor = self.exe(self.ok)
        for content in ("{", "[]", '{"provider:nous":NaN}', '{"provider:nous":true}'):
            with self.subTest(content=content):
                executor.cooldown_path.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(ExecutorUnavailable, "COOLDOWN_STATE_UNAVAILABLE"):
                    executor.execute(mission())

    def test_model_quota_ends_session_before_claiming_next_mission(self):
        a, b = mission("NEW-MISSION-A"), mission("NEW-MISSION-B")
        counter = self.root / "calls.txt"
        payload = {"missions": [a, b], "approvals": seal([a, b]), "sources": {}}
        with mock.patch.dict(os.environ, {"FAKE_COUNTER": str(counter)}), \
             mock.patch.object(hga, "github_source", return_value=payload) as source, \
             mock.patch.object(hga, "HermesExecutor", return_value=self.exe(self.rate)):
            code = hga.main(["run", "--state", str(self.root), "--issue", "94",
                             "--mandate-comment", str(MANDATE), "--mandate-sha256", MANDATE_SHA,
                             "--no-publish", "--seconds", "1"])
        r = Runtime(self.root)
        self.assertEqual(code, 2)
        self.assertEqual(r.state(a)["reason"], "BLOCKED_PROVIDER_RATE_LIMIT")
        self.assertEqual(r.state(b), {})
        self.assertEqual(counter.read_text(), "x")
        self.assertEqual(source.call_count, 1)

    def test_stop_rechecked_immediately_before_starting_worker(self):
        a = mission()
        executor = self.exe(self.ok, stop_requested=lambda: (
            self.root / f"{a['id']}.hermes.err").exists())
        with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("worker started")), \
             self.assertRaisesRegex(ExecutorUnavailable, "HERMES_WORKER_STOPPED_OR_TIMEOUT"):
            executor.execute(a)

    def test_historical_c_cannot_enter_direct_executor(self):
        with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("worker started")), \
             self.assertRaisesRegex(ExecutorUnavailable, "historical mission C"):
            self.exe(self.ok).execute(mission("HERMES-QWEN4-20261121-C"))

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
    def test_zero_cost_must_be_a_number(self):
        res = ok_result()
        res["provider_evidence"]["actual_cost_usd"] = False
        self.assertFalse(hermes_verifier.verify(mission(), res)["ok"])

    def test_incomplete_subprocess_success_is_rejected(self):
        completed = subprocess.CompletedProcess([], 0, '{"ok":true,"checks":[{"ok":true}]}', "")
        with mock.patch.object(subprocess, "run", return_value=completed):
            self.assertFalse(hermes_verifier.verify(mission(), ok_result())["ok"])

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
    def test_stop_after_ack_blocks_worker_and_later_publication(self):
        a = mission()
        r, publisher = build_runtime(
            self.root, issue=94, publisher=self.fake_publisher,
        )
        def post_and_stop(body):
            (self.root / "stop.request").touch()
            return self.fake_publisher(body)

        publisher.publisher = post_and_stop
        r.executor = mock.Mock(side_effect=AssertionError("worker must stay stopped"))
        r.run_queue([a], seal([a]))
        publisher.sync()
        r.executor.assert_not_called()
        self.assertEqual(len(self.published), 1)
        self.assertTrue(r.stopped())

    def test_lost_ack_response_pauses_worker_until_reconciled_without_reposting(self):
        a = mission()
        receipts, attempts, calls = {}, [], []

        def post(body):
            event = json.loads(hga.EVENT_BLOCK_RE.search(body)[1])
            attempts.append(event["status"])
            receipts[(a["id"], event["status"])] = {
                "url": "https://github.com/fixture",
                "contract_sha256": fingerprint(a),
            }
            raise OSError("response lost")

        r, _ = build_runtime(self.root, issue=94, publisher=post, scan=lambda: dict(receipts))
        r.executor = lambda m: calls.append(m["id"]) or ok_result(m)
        r.run_queue([a], seal([a]))
        self.assertEqual(r.state(a)["status"], "ACK")
        self.assertEqual(calls, [])
        r.run_queue([a], seal([a]))
        self.assertEqual(r.state(a)["status"], "ACCEPTED")
        self.assertEqual(calls, [a["id"]])
        self.assertEqual(attempts, ["ACK"])

    def test_stop_after_publication_intent_prevents_post(self):
        a = mission()
        r, publisher = build_runtime(self.root, issue=94, publisher=self.fake_publisher)
        original_cas = r.store.put_cas

        def request_stop(key, value, previous):
            result = original_cas(key, value, previous)
            if key.startswith("hermes-relay-published/") and isinstance(value, dict) and value.get("pending"):
                (self.root / "stop.request").touch()
            return result

        r.store.put_cas = request_stop
        r.run_queue([a], seal([a]))
        self.assertEqual(self.published, [])

    def test_ambiguous_ack_without_receipt_blocks_without_reposting(self):
        a = mission()
        attempts = []

        def post(body):
            attempts.append(body)
            raise OSError("unknown outcome")

        r, _ = build_runtime(self.root, issue=94, publisher=post, scan=lambda: {})
        r.executor = mock.Mock(side_effect=AssertionError("worker started"))
        for _ in range(2):
            r.run_queue([a], seal([a]))
        self.assertEqual(len(attempts), 1)
        self.assertEqual(r.state(a)["status"], "ACK")
        with mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            hga.main(["status", "--state", str(self.root)])
        report = json.loads(output.getvalue())
        self.assertEqual(report.get("pending_publications"),
                         [f"hermes-relay-published/{a['id']}/ACK"])

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
        self.assertTrue(pub.ack(a["id"]))
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
        r, pub = build_runtime(self.root, issue=94, publisher=flaky,
                               scan=lambda: None if state["down"] else {})
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
        a = mission()
        r, pub = build_runtime(self.root, issue=94, publisher=self.fake_publisher,
                             scan=lambda: {(a["id"], "ACK"): {
                                 "url": "https://github.com/existing#1",
                                 "contract_sha256": fingerprint(a)}})
        r.claim(a)
        r.inbox.receive({"request_id": a["id"]})
        self.assertTrue(pub.ack(a["id"]))
        self.assertEqual(self.published, [])  # no duplicate POST
        rec = r.store.get(f"hermes-relay-published/{a['id']}/ACK")
        self.assertIsNotNone(rec)
        self.assertTrue(rec["recovered"])
        self.assertEqual(rec["url"], "https://github.com/existing#1")

    def test_f3_scan_same_id_different_contract_is_not_swallowed(self):
        # Réserve #126-4: a same-id event carrying a DIFFERENT contract is a new
        # approval, not a crash recovery -> it must be published, not recorded.
        a = mission()
        r, pub = build_runtime(self.root, issue=94, publisher=self.fake_publisher,
                             scan=lambda: {(a["id"], "ACK"): {
                                 "url": "https://github.com/existing#1",
                                 "contract_sha256": "0" * 64}})
        r.claim(a)
        r.inbox.receive({"request_id": a["id"]})
        self.assertTrue(pub.ack(a["id"]))
        self.assertEqual(len(self.published), 1)  # new approval published, not swallowed
        rec = r.store.get(f"hermes-relay-published/{a['id']}/ACK")
        self.assertIsNotNone(rec)
        self.assertNotIn("recovered", rec)  # recorded as a fresh publication
        self.assertEqual(rec["url"], "https://github.com/fake#1")  # fresh POST, pas l'URL recoverée

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
        original = {"id": 1, "body": body,
                    "user": {"login": "khalidd692", "id": 275517051, "type": "User"},
                    "issue_url": "https://api.github.com/repos/x/y/issues/94",
                    "created_at": "2026-11-22T12:00:00Z", "updated_at": "2026-11-22T12:00:00Z",
                    "html_url": "https://github.com/x/y/issues/94#issuecomment-1"}
        fake = {**original, "user": {"login": "someone-else", "id": 1}}
        self.assertEqual(hga.existing_events("x/y", 94, fetcher=lambda ep: [fake]), {})
        found = hga.existing_events("x/y", 94, fetcher=lambda ep: [original, fake])
        self.assertEqual(found[("M1", "ACK")],
                         {"url": original["html_url"], "contract_sha256": "x"})
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
        with mock.patch.object(subprocess, "run",
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
        url = "https://github.com/x/y/issues/94#issuecomment-305"
        comments[305] = {"id": 305, "body": body, "html_url": url,
                         "issue_url": "https://api.github.com/repos/x/y/issues/94",
                         "created_at": "2026-11-22T12:00:00Z", "updated_at": "2026-11-22T12:00:00Z",
                         "user": {"login": "khalidd692", "id": 275517051, "type": "User"}}
        def fetcher(ep):
            page = int(ep.rsplit("page=", 1)[1])
            return comments[(page - 1) * 100:page * 100]
        found = hga.existing_events("x/y", 94, fetcher=fetcher)
        self.assertIsNotNone(found)
        self.assertEqual(found[("M-LATE", "ACCEPTED")],
                         {"url": url, "contract_sha256": "z"})

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


class ReviewR1R2Tests(unittest.TestCase):
    """Réserves R1/R2 de la revue indépendante phase 2 (sa-0-75c69b25)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_poll_budget_helper(self):
        term = [{"id": f"T{i}", "status": "ACCEPTED"} for i in range(3)]
        self.assertEqual(hga.poll_budget(term, 5), 8)
        self.assertEqual(hga.poll_budget(term, 20), 20)  # engine registry cap
        self.assertEqual(hga.poll_budget([], 1), 1)
        self.assertEqual(hga.poll_budget([{"id": "R", "status": "RUNNING"}], 1), 1)

    def test_main_wiring_hard_intra_poll_cap(self):
        a = mission("HERMES-RELAY-R1-A")
        b = mission("HERMES-RELAY-R1-B")
        payload = {"missions": [a, b], "approvals": seal([a, b]), "sources": {}}
        class StubExec:
            def __init__(self, **kw):
                pass
            def execute(self, m):
                return ok_result(m)
        with mock.patch.object(hga, "github_source", return_value=payload), \
             mock.patch.object(hga, "HermesExecutor", StubExec):
            code = hga.main(["run", "--state", str(self.root), "--issue", "94",
                             "--mandate-comment", str(MANDATE), "--mandate-sha256", MANDATE_SHA, "--once",
                             "--max-tasks", "1", "--no-publish", "--seconds", "60"])
        self.assertEqual(code, 0)
        states = list((self.root / "ledger" / "kilo-local").glob("*.json"))
        self.assertEqual(len(states), 1)  # hard cap intra-poll: 1 seule exécution

    def test_later_poll_uses_only_remaining_session_budget(self):
        a, b, c = [mission(f"NEW-MISSION-{letter}") for letter in "ABC"]
        payloads = [{"missions": admitted, "approvals": seal(admitted), "sources": {}}
                    for admitted in ([a], [a, b, c])]
        executor = mock.Mock()
        executor.execute.side_effect = ok_result
        clock = mock.Mock(wraps=time)
        polling_time = time.monotonic()
        clock.monotonic.side_effect = lambda: polling_time

        def skip_poll_interval(_):
            nonlocal polling_time
            polling_time += 10

        clock.sleep.side_effect = skip_poll_interval
        with mock.patch.object(hga, "time", clock), \
             mock.patch.object(hga, "github_source", side_effect=payloads), \
             mock.patch.object(hga, "HermesExecutor", return_value=executor):
            code = hga.main(["run", "--state", str(self.root), "--issue", "94",
                             "--mandate-comment", str(MANDATE), "--mandate-sha256", MANDATE_SHA,
                             "--max-tasks", "2", "--no-publish", "--seconds", "60"])
        r = Runtime(self.root)
        self.assertEqual(code, 0)
        self.assertEqual(r.state(a)["status"], "ACCEPTED")
        self.assertEqual(r.state(b)["status"], "ACCEPTED")
        self.assertEqual(r.state(c), {})

    def test_unadmitted_terminal_checkpoint_cannot_expand_worker_budget(self):
        a, b = mission("NEW-MISSION-A"), mission("NEW-MISSION-B")
        stale = mission("ARCHIVED-SYNTHETIC")
        r = Runtime(self.root)
        r.save(stale, "ACCEPTED", result=ok_result(stale))
        payload = {"missions": [a, b], "approvals": seal([a, b]), "sources": {}}
        executor = mock.Mock()
        executor.execute.side_effect = ok_result
        with mock.patch.object(hga, "github_source", return_value=payload), \
             mock.patch.object(hga, "HermesExecutor", return_value=executor):
            hga.main(["run", "--state", str(self.root), "--issue", "94",
                      "--mandate-comment", str(MANDATE), "--mandate-sha256", MANDATE_SHA,
                      "--max-tasks", "1", "--once", "--no-publish"])
        self.assertEqual(r.state(a)["status"], "ACCEPTED")
        self.assertIn(r.state(b).get("execution_status"), (None, "NOT_STARTED"))

    def test_propose_dedup_via_main(self):
        bl = self.root / "backlog.json"
        bl.write_text(json.dumps({"tasks": [
            {"id": "I-02", "owner": "hermes", "initial_state": "todo", "title": "memoire"}]}))
        published = []
        with mock.patch.object(hga, "gh_json", return_value=OWNER), \
             mock.patch.object(hga, "publish_comment",
                               side_effect=lambda repo, issue, body, **kw: published.append(body) or "u1"):
            code1 = hga.main(["propose", "--state", str(self.root), "--issue", "94",
                              "--backlog", str(bl), "--task", "I-02"])
            code2 = hga.main(["propose", "--state", str(self.root), "--issue", "94",
                              "--backlog", str(bl), "--task", "I-02"])
        self.assertEqual((code1, code2), (0, 0))
        self.assertEqual(len(published), 1)  # dédup CAS: pas de seconde publication

    def test_propose_obeys_stop_before_any_github_call(self):
        (self.root / "stop.request").touch()
        with mock.patch.object(hga, "gh_json", side_effect=AssertionError("GitHub read")), \
             mock.patch.object(hga, "publish_comment", side_effect=AssertionError("GitHub write")):
            code = hga.main(["propose", "--state", str(self.root), "--issue", "94"])
        self.assertEqual(code, 2)

    def test_live_run_requires_a_content_pin_even_without_publication(self):
        for pin in ([], ["--mandate-sha256", "invalid"]):
            with self.subTest(pin=pin):
                with mock.patch.object(hga, "github_source", side_effect=AssertionError("GitHub read")), \
                     mock.patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit) as error:
                    hga.main(["run", "--state", str(self.root), "--issue", "94",
                              "--mandate-comment", str(MANDATE), "--no-publish", "--once", *pin])
                self.assertEqual(error.exception.code, 2)

    def test_publishing_run_requires_the_pinned_owner_before_admission(self):
        with mock.patch.object(hga, "gh_json", return_value={**OWNER, "id": 1}), \
             mock.patch.object(hga, "github_source", side_effect=AssertionError("GitHub admission")):
            code = hga.main(["run", "--state", str(self.root), "--issue", "94",
                             "--mandate-comment", str(MANDATE), "--mandate-sha256", MANDATE_SHA,
                             "--once"])
        self.assertEqual(code, 2)

    def test_github_rate_limit_rejects_ack_and_stops_before_next_claim(self):
        a, b = mission("NEW-MISSION-A"), mission("NEW-MISSION-B")
        payload = {"missions": [a, b], "approvals": seal([a, b]), "sources": {}}
        calls = []

        def github(endpoint, *, body, timeout):
            if endpoint == "user":
                return OWNER
            calls.append("POST" if body is not None else "GET")
            if body is not None:
                raise hga.GitHubRateLimited("GitHub API rate limit reached")
            return []

        with mock.patch.object(hga, "gh_json", side_effect=github), \
             mock.patch.object(hga, "github_source", return_value=payload):
            code = hga.main(["run", "--state", str(self.root), "--issue", "94",
                             "--mandate-comment", str(MANDATE), "--mandate-sha256", MANDATE_SHA,
                             "--once"])
        r = Runtime(self.root)
        self.assertEqual(code, 2)
        self.assertEqual(calls, ["GET", "POST"])
        self.assertEqual(r.state(a)["status"], "ACK")
        self.assertEqual(r.state(b), {})
        self.assertIsNone(r.store.get(f"hermes-relay-published/{a['id']}/ACK"))
        self.assertEqual(r.status()["last_observed"]["BLOCKER"], "BLOCKED_GITHUB_RATE_LIMIT")

    def test_explicit_resume_posts_ack_when_stop_prevented_dispatch(self):
        a = mission()
        payload = {"missions": [a], "approvals": seal([a]), "sources": {}}
        arguments = ["run", "--state", str(self.root), "--issue", "94", "--once",
                     "--mandate-comment", str(MANDATE), "--mandate-sha256", MANDATE_SHA]
        marker = self.root / "stop.request"
        executor = mock.Mock()
        executor.execute.side_effect = ok_result
        attempts = []
        actual_publish = hga.publish_comment

        def stop_before_dispatch(*args, **kwargs):
            marker.touch()
            return actual_publish(*args, **kwargs)

        def github(endpoint, *, body, timeout):
            if endpoint == "user":
                return OWNER
            if body is None:
                return []
            attempts.append(json.loads(hga.EVENT_BLOCK_RE.search(body)[1])["status"])
            cid = len(attempts)
            return {"id": cid, "user": OWNER, "created_at": "now", "updated_at": "now",
                    "issue_url": f"https://api.github.com/repos/{hga.REPO}/issues/94",
                    "html_url": f"https://github.com/{hga.REPO}/issues/94#issuecomment-{cid}"}

        with mock.patch.object(hga, "gh_json", side_effect=github), \
             mock.patch.object(hga, "github_source", return_value=payload), \
             mock.patch.object(hga, "HermesExecutor", return_value=executor):
            with mock.patch.object(hga, "publish_comment", side_effect=stop_before_dispatch):
                self.assertEqual(hga.main(arguments), 2)
            self.assertEqual(attempts, [])
            self.assertEqual(Runtime(self.root).state(a)["status"], "ACK")
            marker.unlink()
            self.assertEqual(hga.main(arguments), 0)
        self.assertEqual(attempts, ["ACK", "ACCEPTED"])
        self.assertEqual(Runtime(self.root).state(a)["status"], "ACCEPTED")


class ReliabilityReviewTests(unittest.TestCase):
    """Sept corrections de fiabilité (#126-1 .. #126-7), audit lecture seule."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.published = []

    def fake_publisher(self, body):
        self.published.append(body)
        return f"https://github.com/fake#{len(self.published)}"

    def test_duplicate_json_key_rejected(self):
        m = mission("HERMES-RELAY-DUP")
        fp = fingerprint(m)
        expires = (datetime.now(timezone.utc) + timedelta(seconds=3600)) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        approval = json.dumps({"approver": "khalidd692", "mandate_comment_id": MANDATE,
                               "expires_at": expires, "mission_sha256": fp})
        # duplicate une clé NON couverte par l'empreinte (expires_at, même valeur) :
        # l'ancien code l'admettait (dernier verdict), le nouveau le rejette.
        doubled = approval.replace('"expires_at": "' + expires + '"',
                                   '"expires_at": "' + expires + '", "expires_at": "' + expires + '"', 1)
        self.assertIn('"expires_at"', doubled)
        body = ("```hermes-mission/v1\n" + '{"mission": ' + json.dumps(m)
                + ', "approval": ' + doubled + "}\n```")
        c = {"id": 1, "user": {"login": "khalidd692"}, "body": body}
        self.assertEqual(parse_approvals([c], mandate_comment_id=MANDATE)["missions"], [])

    def test_mandate_content_pinned_by_sha256(self):
        comment = {"id": MANDATE, "user": {"login": "khalidd692"}, "body": "GO synthetique"}
        sha = hashlib.sha256(b"GO synthetique").hexdigest()
        self.assertEqual(fetch_mandate("x/y", 67, MANDATE, fetcher=lambda ep: comment,
                                      mandate_sha256=sha)["body"], "GO synthetique")
        with self.assertRaises(ValueError):
            fetch_mandate("x/y", 67, MANDATE, fetcher=lambda ep: comment,
                          mandate_sha256="0" * 64)
        # sans épingle: comportement historique (auteur seul) conservé
        self.assertEqual(fetch_mandate("x/y", 67, MANDATE,
                                       fetcher=lambda ep: comment)["body"], "GO synthetique")

    def test_gh_calls_pin_utf8_encoding(self):
        completed = subprocess.CompletedProcess([], 0, '{"body":"déjà vérifié"}'.encode("utf-8"), b"")
        with mock.patch.object(gms.subprocess, "run", return_value=completed) as run:
            row = gms.default_fetcher("repos/x/y/issues/1/comments")
        self.assertEqual(row["body"], "déjà vérifié")
        self.assertIn("github.com", run.call_args.args[0])
        with mock.patch.object(subprocess, "run", return_value=completed) as run:
            hga.publish_comment("x/y", 1, "résultat vérifié")
        self.assertEqual(json.loads(run.call_args.kwargs["input"].decode("utf-8")),
                         {"body": "résultat vérifié"})

    def test_journal_appends_before_cas_mark(self):
        published = []
        r, pub = build_runtime(self.root, issue=94,
                               publisher=lambda body: published.append(body) or "u")
        a = mission()
        r.claim(a)
        r.save(a, "ACCEPTED", result=ok_result(a))
        real = r.store.put_cas

        def exploding(key, value, old):
            if key.startswith("hermes-relay-journal/"):
                raise OSError("crash entre append et mark")
            return real(key, value, old)

        r.store.put_cas = exploding
        with self.assertRaises(OSError):
            pub.sync()
        lines = (self.root / "relay-events.jsonl").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)  # la transition n'est pas perdue

    def test_main_loop_unexpected_error_fail_closed(self):
        with mock.patch.object(hga, "github_source", side_effect=TypeError("boom")):
            code = hga.main(["run", "--state", str(self.root), "--issue", "94",
                             "--mandate-comment", str(MANDATE), "--mandate-sha256", MANDATE_SHA, "--once",
                             "--no-publish", "--seconds", "60"])
        self.assertEqual(code, 2)
        # heartbeat refera STOPPED à la sortie ; le BLOCKER reste prouvé et
        # aucune mission n'a été exécutée (fail-closed, pas de boucle).
        report = Runtime(self.root).status()
        self.assertEqual(report["missions"], {})
        self.assertEqual(report["last_observed"].get("BLOCKER"), "TypeError")

    def test_main_wires_mandate_sha256_into_source(self):
        seen = {}
        def fake_source(*a, **kw):
            seen.update(kw)
            return {"missions": [], "approvals": {}, "sources": {}}
        with mock.patch.object(hga, "github_source", side_effect=fake_source):
            code = hga.main(["run", "--state", str(self.root), "--issue", "94",
                             "--mandate-comment", str(MANDATE), "--mandate-sha256", "a" * 64,
                             "--once", "--no-publish", "--seconds", "60"])
        self.assertEqual(code, 0)
        self.assertEqual(seen.get("mandate_sha256"), "a" * 64)

    def test_existing_events_ignores_non_dict_comments(self):
        found = hga.existing_events("x/y", 94, fetcher=lambda ep: ["not-a-dict", 7, None])
        self.assertEqual(found, {})

    def test_contractless_recovered_event_is_published_fail_closed(self):
        # Réserve #126-4: sans empreinte sur l'événement existant, la
        # correspondance n'est pas prouvée -> on publie plutôt que avaler.
        a = mission()
        r, pub = build_runtime(self.root, issue=94, publisher=self.fake_publisher,
                             scan=lambda: {(a["id"], "ACK"): {
                                 "url": "https://github.com/existing#1",
                                 "contract_sha256": None}})
        r.claim(a)
        r.inbox.receive({"request_id": a["id"]})
        self.assertTrue(pub.ack(a["id"]))
        self.assertEqual(len(self.published), 1)

    def test_main_loop_attribute_error_fail_closed(self):
        with mock.patch.object(hga, "github_source", side_effect=AttributeError("boom")):
            code = hga.main(["run", "--state", str(self.root), "--issue", "94",
                             "--mandate-comment", str(MANDATE), "--mandate-sha256", MANDATE_SHA, "--once",
                             "--no-publish", "--seconds", "60"])
        self.assertEqual(code, 2)
        report = Runtime(self.root).status()
        self.assertEqual(report["missions"], {})
        self.assertEqual(report["last_observed"].get("BLOCKER"), "AttributeError")

    def test_propose_publish_failure_returns_error(self):
        bl = self.root / "backlog.json"
        bl.write_text(json.dumps({"tasks": [
            {"id": "I-02", "owner": "hermes", "initial_state": "todo"}]}))
        with mock.patch.object(hga, "gh_json", return_value=OWNER), \
             mock.patch.object(hga, "publish_comment", side_effect=OSError("down")):
            code = hga.main(["propose", "--state", str(self.root), "--issue", "94",
                             "--backlog", str(bl), "--task", "I-02"])
        self.assertEqual(code, 1)

    def test_propose_concurrent_single_publication(self):
        import threading
        bl = self.root / "backlog.json"
        bl.write_text(json.dumps({"tasks": [
            {"id": "I-02", "owner": "hermes", "initial_state": "todo"}]}))
        published = []

        def slow_publish(repo, issue, body, **kw):
            published.append(body)
            time.sleep(0.05)
            return "u"

        codes = []

        def go():
            codes.append(hga.main(["propose", "--state", str(self.root), "--issue", "94",
                                   "--backlog", str(bl), "--task", "I-02"]))

        # Un SEUL patch posé dans le thread principal : patch.object n'est pas
        # thread-safe et un patch posé/retiré par deux threads fuit et casse les
        # tests suivants (publish_comment remplacé par un Mock résiduel).
        with mock.patch.object(hga, "gh_json", return_value=OWNER), \
             mock.patch.object(hga, "publish_comment", side_effect=slow_publish):
            t1, t2 = threading.Thread(target=go), threading.Thread(target=go)
            t1.start(); t2.start(); t1.join(); t2.join()
        self.assertEqual(sorted(codes), [0, 0])
        self.assertEqual(len(published), 1)  # verrou + CAS : une seule publication


class TwoMissionRecipeTests(unittest.TestCase):
    """Recette #123 : deux missions synthétiques distinctes A puis B, enchaînées."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.published = []

    def fake_publisher(self, body):
        self.published.append(body)
        return f"https://github.com/fake#{len(self.published)}"

    def _run(self, stub):
        a = mission("HERMES-RECIPE-A", specialist="tel99-analyst")
        b = mission("HERMES-RECIPE-B", dependencies=[a["id"]], specialist="tel99-dev")
        comments = [approval_comment(a, cid=11), approval_comment(b, cid=12)]
        mandate = {"id": MANDATE, "user": {"login": "khalidd692"}, "body": "GO synthetique"}

        def fetcher(endpoint):
            if endpoint.endswith(f"/comments/{MANDATE}"):
                return mandate
            return comments if endpoint.endswith("page=1") else []

        real_source = gms.github_source

        def source():
            return real_source("x/y", 94, 67, MANDATE, fetcher=fetcher)

        with mock.patch.object(hga, "gh_json", return_value=OWNER), \
             mock.patch.object(hga, "github_source", side_effect=lambda *a, **k: source()), \
             mock.patch.object(hga, "existing_events", return_value={}), \
             mock.patch.object(hga, "HermesExecutor", lambda **kw: stub), \
             mock.patch.object(hga, "publish_comment",
                               side_effect=lambda repo, issue, body, **kw: self.fake_publisher(body)):
            code = hga.main(["run", "--state", str(self.root), "--issue", "94",
                             "--mandate-issue", "67", "--mandate-comment", str(MANDATE),
                             "--mandate-sha256", MANDATE_SHA, "--once", "--seconds", "60"])
        return code, a, b

    def test_recipe_a_then_b_end_to_end_and_idempotent(self):
        class StubExec:
            def __init__(self):
                self.calls = []

            def execute(self, m):
                self.calls.append(m["id"])
                return ok_result(m)

        stub = StubExec()
        code, a, b = self._run(stub)
        self.assertEqual(code, 0)
        self.assertEqual(stub.calls, [a["id"], b["id"]])  # A avant B (dépendance CAS)
        r = Runtime(self.root)
        self.assertEqual(r.state(a)["status"], "ACCEPTED")
        self.assertEqual(r.state(b)["status"], "ACCEPTED")
        self.assertEqual(len(self.published), 4)  # ACK A, ACK B, ACCEPTED A, ACCEPTED B
        idx = {}
        for i, body in enumerate(self.published):
            for mid in (a["id"], b["id"]):
                for status in ("ACK", "ACCEPTED"):
                    if f'"mission_id": "{mid}"' in body and f'"status": "{status}"' in body:
                        idx[(mid, status)] = i
        self.assertLess(idx[(a["id"], "ACK")], idx[(b["id"], "ACK")])
        self.assertLess(idx[(a["id"], "ACCEPTED")], idx[(b["id"], "ACCEPTED")])
        memory_files = list((self.root / "memory").rglob("*.json"))
        self.assertEqual(len(memory_files), 1)  # un document par projet
        entries = json.loads(memory_files[0].read_text(encoding="utf-8"))["entries"]
        self.assertEqual({e["id"] for e in entries}, {a["id"], b["id"]})

        # second run on the same durable state: idempotent, zero duplicate
        code2, _, _ = self._run(stub)
        self.assertEqual(code2, 0)
        self.assertEqual(stub.calls, [a["id"], b["id"]])
        self.assertEqual(len(self.published), 4)


if __name__ == "__main__":
    unittest.main()
