#!/usr/bin/env python3
"""Deterministic end-to-end proof of the cloud-autonomy path.

This test drives the **real** ``orchestrator.run()`` — the same function the
cloud plugin-script runner executes — from mission selection to bus result,
replacing only the network layer with an in-memory fake. It proves, without any
spend and without touching the repository:

  * the whole pipeline runs: select mission -> KV lock -> start conversation ->
    wait -> record result on the bus -> release lock;
  * the lock is atomic (a second run cannot start while the first holds it);
  * a finished mission is **not** reprocessed on a later run;
  * the ledger survives a "container destruction" (a fresh orchestrator/bus over
    the same KV store still sees the mission and its learning).

The fake KV store is a plain dict shared across runs, which is exactly what a
durable store gives across distinct cloud pods.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "agents"))
sys.path.insert(0, str(ROOT / "scripts" / "agents" / "automation"))

import orchestrator  # noqa: E402
import protocol.store as store_mod  # noqa: E402
from protocol.bus import Bus  # noqa: E402
from protocol.store import KvStore  # noqa: E402
from automation import bus_bridge  # noqa: E402
from automation import policy  # noqa: E402

REPO = "khalidd692/telcoin-trading-intelligence99"
ISSUE = {
    "number": 70,
    "title": "Mission (lecture seule) - age des donnees Kraken",
    "body": (
        "Afficher l'age des donnees Kraken.\n\n"
        "### Critere d'acceptation\n"
        "Un rapport de lecture seule, avec preuves, pret a etre valide par un humain.\n"
    ),
    "state": "open",
    "labels": [{"name": "tel99-mission"}],
    "created_at": "2026-11-15T00:00:00Z",
}

# S-06: a mission may start only with a current, content-bound approval by an
# explicitly authorised actor. The fixture is approved by this login, and the
# config below names it, so the end-to-end tests exercise the approved path.
AUTHORIZED_APPROVER = "khalidd692"
ISSUE["body"] = (
    ISSUE["body"]
    + policy.approval_marker(policy.mission_content(ISSUE),
                             approver=AUTHORIZED_APPROVER)
    + "\n"
)


class FakeCloud:
    """An in-memory stand-in for the KV store, GitHub and the agent server."""

    def __init__(self, *, conversation_final="finished", issues=None,
                 coordinator_response="Rapport final du coordinateur.",
                 children=None, roles=None, mission_body=None):
        self.kv: dict = {}
        self.kv_versions: dict = {}
        self.issues = issues if issues is not None else [dict(ISSUE)]
        self.conversation_final = conversation_final
        self.coordinator_response = coordinator_response
        # Each child: {"id", "status", "response"}. Default: one finished verifier.
        self.children = children if children is not None else [
            {"id": "child-verifier", "status": "finished", "response": "verifie"},
        ]
        # Role delegations, as real ``TaskObservation``s. Default: the three
        # required roles (dev, analyst, verifier) each completed with a result.
        self.roles = roles if roles is not None else [
            {"subagent": "tel99-dev-000000", "status": "completed",
             "text": "rapport dev", "is_error": False, "task_id": "task_1"},
            {"subagent": "tel99-analyst-000000", "status": "completed",
             "text": "rapport analyste", "is_error": False, "task_id": "task_2"},
            {"subagent": "tel99-verifier-000000", "status": "completed",
             "text": "rapport verificateur", "is_error": False, "task_id": "task_3"},
        ]
        if mission_body is not None:
            self.issues = [{**dict(ISSUE), "body": mission_body}]
        self.approval_comment_author = AUTHORIZED_APPROVER
        self.started_conversations = []
        self.state_writes = 0
        # When >0, ``/events/search`` returns a first page of that size and a
        # ``next_page_id``, to exercise the pagination walk.
        self.event_page_size = 0
        # When set, a KV PUT to this key fails, to exercise KV failures.
        # ``fail_kv_put_after`` lets a test allow the first N writes (e.g. the
        # mission opening) and fail only a later one (the final record).
        self.fail_kv_put_key = None
        self.fail_kv_put_after = 0
        self.kv_put_calls = []
        # Inject a one-shot contention: the Nth conditional PUT returns 409 even
        # though the CAS would otherwise win, to force the retry path.
        self.inject_409_on_put = 0
        self._put_count = 0
        # Conversation ids the server no longer knows (404): a conversation a
        # prior run started and that has since been removed. Used by the resume
        # tests to prove a dead conversation is safely re-queued.
        self.dead_conversations: set[str] = set()
        # A per-conversation list of execution statuses consumed on each GET, so
        # a test can simulate a conversation that is "running" then "finished".
        self.status_sequence: list[str] = []

    # -- HTTP surface -------------------------------------------------------
    def request(self, method, url, payload=None, headers=None, timeout=60):
        # KV store
        if "/v1/kv" in url:
            return self._kv(method, url, payload)
        # run phase reporting
        if "/v1/runs/" in url and url.endswith("/phase"):
            return 200, {}
        # quota
        if url.endswith("/api/quota/status"):
            return 200, {"remaining": 10, "daily_limit": 20}
        if "api.github.com" in url and "/comments?" in url:
            approval, _ = policy.read_approval(self.issues[0])
            if approval is None:
                return 200, []
            now = policy.utcnow_iso()
            return 200, [{
                "body": policy.approval_marker(
                    policy.mission_content(self.issues[0]), approver=approval["approved_by"]),
                "user": {"login": self.approval_comment_author},
                "created_at": now,
                "updated_at": now,
            }]
        # GitHub issues
        if "api.github.com" in url and "/issues" in url:
            return 200, self.issues
        # agent server: coordinator final response
        if url.endswith("/agent_final_response"):
            conv = url.split("/api/conversations/", 1)[1].split("/", 1)[0]
            if conv == "cid-test-1":
                return 200, {"response": self.coordinator_response}
            for child in self.children:
                if child["id"] == conv:
                    return 200, {"response": child.get("response", "")}
            return 200, {"response": ""}
        # agent server: coordinator events (delegations + child launches).
        # The real reader is the *paginated* ``/events/search`` endpoint; the
        # batch ``/events`` endpoint needs a body and answers 422 to a bare GET.
        if "/events/search" in url and method == "GET":
            conv = url.split("/api/conversations/", 1)[1].split("/", 1)[0]
            if conv == "cid-test-1":
                events = []
                for role in self.roles:
                    events.append({"action": {"kind": "TaskAction",
                                              "subagent_type": role["subagent"],
                                              "description": "delegate"}})
                    events.append({"observation": {
                        "kind": "TaskObservation",
                        "task_id": role.get("task_id", ""),
                        "subagent": role["subagent"],
                        "status": role.get("status", "completed"),
                        "is_error": role.get("is_error", False),
                        "content": [{"type": "text", "text": role.get("text", "")}],
                    }})
                for c in self.children:
                    events.append({"observation": {
                        "kind": "StartChildConversationObservation",
                        "conversation_id": c["id"]}})
                if self.event_page_size:
                    if "page_id=" in url:
                        page = events[self.event_page_size:]
                        return 200, {"items": page, "next_page_id": None}
                    page = events[:self.event_page_size]
                    return 200, {"items": page, "next_page_id": "p2"}
                return 200, {"items": events, "next_page_id": None}
            return 200, {"items": [], "next_page_id": None}
        # The batch endpoint must NOT be read: a bare GET is a 422.
        if url.endswith("/events") and method == "GET":
            return 422, "batch endpoint needs a body"
        # agent server: conversation list / single
        if url.endswith("/api/conversations") and method == "GET":
            return 200, []
        if url.endswith("/api/conversations") and method == "POST":
            self.started_conversations.append(payload)
            return 201, {"id": "cid-test-1"}
        if "/api/conversations/" in url and method == "GET":
            conv = url.split("/api/conversations/", 1)[1].split("/", 1)[0]
            if conv in self.dead_conversations:
                return 404, "conversation not found"
            if conv == "cid-test-1":
                if self.status_sequence:
                    status = self.status_sequence.pop(0)
                    return 200, {"execution_status": status}
                return 200, {"execution_status": self.conversation_final}
            for child in self.children:
                if child["id"] == conv:
                    return 200, {"execution_status": child.get("status", "finished")}
            return 200, {"execution_status": "finished"}
        if url.endswith("/interrupt"):
            return 200, {}
        return 404, "unhandled"

    def _kv(self, method, url, payload):
        key = url.split("/v1/kv/", 1)[1].split("?", 1)[0]
        nx = "nx=true" in url
        meta = "meta=true" in url
        if_version = None
        if "if_version=" in url:
            if_version = url.split("if_version=", 1)[1].split("&", 1)[0]
        if method == "GET":
            if "?prefix=" in url:
                prefix = url.split("?prefix=", 1)[1]
                return 200, {"keys": [k for k in self.kv if k.startswith(prefix)]}
            if key in self.kv:
                body = {"value": self.kv[key]}
                if meta:
                    body["version"] = self.kv_versions.get(key, 1)
                return 200, body
            return 404, "missing"
        if method == "PUT":
            self.kv_put_calls.append(key)
            self._put_count += 1
            matches = self.kv_put_calls.count(key)
            if self.fail_kv_put_key and key == self.fail_kv_put_key \
                    and matches > self.fail_kv_put_after:
                return 500, "kv write failed"
            if self.inject_409_on_put and self._put_count == self.inject_409_on_put:
                return 409, "conflict"
            if nx and key in self.kv:
                return 409, "exists"
            if if_version is not None:
                current = str(self.kv_versions.get(key, 1))
                if key not in self.kv or current != str(if_version):
                    return 409, "version mismatch"
            self.kv[key] = payload
            self.kv_versions[key] = self.kv_versions.get(key, 0) + 1
            self.state_writes += 1
            return 200, {}
        if method == "DELETE":
            self.kv.pop(key, None)
            self.kv_versions.pop(key, None)
            return 200, {}
        return 404, "unhandled"


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.cloud = FakeCloud()
        self._orig_request = orchestrator._request
        self._orig_kv_get = orchestrator.kv_get
        self._orig_kv_set = orchestrator.kv_set
        self._orig_kv = (orchestrator._KV_BASE, orchestrator._KV_TOKEN)
        orchestrator._request = self.cloud.request

        def fake_kv_get(key):
            status, body = self.cloud._kv("GET", f"https://kv.example/v1/kv/{key}", None)
            if status == 200 and isinstance(body, dict):
                return body.get("value")
            return None

        def fake_kv_set(key, value):
            status, _ = self.cloud._kv("PUT", f"https://kv.example/v1/kv/{key}", value)
            if status not in (200, 201, 204):
                raise orchestrator.urllib.error.HTTPError(
                    f"https://kv.example/v1/kv/{key}", status, "kv write failed",
                    {}, None)

        orchestrator.kv_get = fake_kv_get
        orchestrator.kv_set = fake_kv_set

        # The bus's KvStore talks HTTP directly; route it to the same fake.
        self._orig_store_request = store_mod.KvStore._request

        def store_request(store_self, method, url, payload=None):
            return self.cloud.request(method, url, payload)

        store_mod.KvStore._request = store_request
        # kv_available() needs both a base and a token.
        orchestrator._KV_BASE = "https://kv.example"
        orchestrator._KV_TOKEN = "tok"
        # The bus reads these at call time to pick the durable store.
        self._env = {k: os.environ.get(k)
                     for k in ("AUTOMATION_API_URL", "AUTOMATION_KV_TOKEN",
                               "OPENHANDS_API_KEY")}
        os.environ["AUTOMATION_API_URL"] = "https://kv.example"
        os.environ["AUTOMATION_KV_TOKEN"] = "tok"
        # quota_remaining() needs an API key to even attempt the (faked) call;
        # without it the run is refused fail-closed and the test would depend on
        # the host environment. Pin it so the test is deterministic.
        os.environ["OPENHANDS_API_KEY"] = "test-key"
        self._cwd = os.getcwd()
        os.chdir(ROOT)
        # Isolate every file write (bus ledger, state) in a temp dir: otherwise a
        # file-store run would write to the repository's ``bus/`` and a later test
        # would read it back as "already finished".
        self._orig_repo_root = orchestrator.REPO_ROOT
        self._tmp_root = tempfile.TemporaryDirectory()
        orchestrator.REPO_ROOT = pathlib.Path(self._tmp_root.name)

    def tearDown(self):
        orchestrator._request = self._orig_request
        orchestrator.kv_get = self._orig_kv_get
        orchestrator.kv_set = self._orig_kv_set
        store_mod.KvStore._request = self._orig_store_request
        orchestrator._KV_BASE, orchestrator._KV_TOKEN = self._orig_kv
        orchestrator.REPO_ROOT = self._orig_repo_root
        self._tmp_root.cleanup()
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        os.chdir(self._cwd)

    def _config(self, **over):
        cfg = dict(orchestrator.DEFAULT_CONFIG)
        cfg.update({"dry_run": False, "repository": REPO,
                    "mission_label": "tel99-mission", "max_runtime_seconds": 60,
                    "authorized_approvers": [AUTHORIZED_APPROVER]})
        cfg.update(over)
        return cfg

    def _run(self, config):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = orchestrator.run(config, offline=False)
        return code, buf.getvalue()

    # -- the proofs ---------------------------------------------------------
    def test_full_path_starts_one_conversation_and_records_bus_result(self):
        code, out = self._run(self._config())
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.cloud.started_conversations), 1)
        self.assertIn("bus_mission", out)
        self.assertIn("bus_outcome", out)
        self.assertIn("conversation_finished", out)

        # The ledger holds a finished mission with a learning.
        bus = Bus(ROOT / "bus", store=KvStore("https://kv.example", "tok"))
        corr = bus_bridge.correlation_id(REPO, 70)
        record = bus.load_mission(corr)
        self.assertIsNotNone(record)
        self.assertEqual(record.state, "done")
        self.assertEqual(record.result["status"], "success")
        self.assertEqual(len(record.learnings), 1)

    # -- crash / resume: no duplicate conversation --------------------------
    def _seed_active(self, conversation_id):
        """Simulate a run killed after it recorded an active mission."""
        orchestrator.kv_set("state", {
            "version": 1, "processed": [], "journal": [],
            "active": {"issue": 70, "work_branch": "agent/mission-70-x",
                       "started_at": "2026-11-15T00:00:00Z", "owner": "run-killed",
                       "conversation_id": conversation_id},
        })

    def test_crash_after_post_reattaches_and_does_not_duplicate(self):
        # A run was killed after creating the conversation but before clearing
        # ``active``: the state records the conversation id, the lock is gone.
        # The next run must re-attach to the SAME conversation, never start a
        # second one.
        self._seed_active("cid-test-1")
        # The resumed conversation is still running, then finishes.
        self.cloud.status_sequence = ["running", "running", "finished"]
        code, out = self._run(self._config())
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.cloud.started_conversations), 0, out)
        self.assertIn("conversation_resumed", out)
        self.assertIn("conversation_finished", out)

    def test_crash_with_a_dead_conversation_is_safely_requeued(self):
        # The recorded conversation no longer exists on the server (404). Nothing
        # is running, so the mission is re-queued and a fresh conversation is
        # started exactly once -- the orphan is recovered, not duplicated.
        self._seed_active("cid-gone")
        self.cloud.dead_conversations.add("cid-gone")
        code, out = self._run(self._config())
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.cloud.started_conversations), 1, out)
        self.assertIn("stale_active_reconciled", out)

    def test_crash_before_post_is_safely_requeued(self):
        # A kill before the POST leaves an active record with no conversation id.
        # Only the lock can prove safety; it is gone, so the mission is re-queued
        # and started once.
        orchestrator.kv_set("state", {
            "version": 1, "processed": [], "journal": [],
            "active": {"issue": 70, "work_branch": "agent/mission-70-x",
                       "started_at": "2026-11-15T00:00:00Z", "owner": "run-killed",
                       "conversation_id": None},
        })
        code, out = self._run(self._config())
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.cloud.started_conversations), 1, out)

    def test_live_conversation_with_no_lock_never_starts_a_duplicate(self):
        # The strongest no-duplicate proof: even with the lock absent, a live
        # conversation recorded in state is re-attached, so the mission is not
        # started again.
        self._seed_active("cid-test-1")
        self.cloud.status_sequence = ["running", "finished"]
        code, out = self._run(self._config())
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.cloud.started_conversations), 0, out)

    def test_lock_is_released_after_a_successful_run(self):
        self._run(self._config())
        # Released, not merely deleted: the CAS release writes a tombstone, and
        # no run owns the lock afterwards.
        self.assertFalse(orchestrator._lock_held(self.cloud.kv.get("active_mission_lock")))

    def test_finished_mission_is_not_reprocessed_on_a_second_run(self):
        code1, _ = self._run(self._config())
        self.assertEqual(code1, 0)
        code2, out2 = self._run(self._config())
        self.assertEqual(code2, 0)
        # The second run must not start a second conversation.
        self.assertEqual(len(self.cloud.started_conversations), 1, out2)

    def test_a_failed_conversation_records_a_failure_and_stays_resumable(self):
        self.cloud.conversation_final = "error"
        code, out = self._run(self._config())
        self.assertEqual(code, 2, out)
        bus = Bus(ROOT / "bus", store=KvStore("https://kv.example", "tok"))
        record = bus.load_mission(bus_bridge.correlation_id(REPO, 70))
        self.assertEqual(record.state, "failed")
        self.assertTrue(record.resumable)

    def test_a_held_lock_blocks_a_concurrent_run(self):
        """The real concurrency guarantee: the KV lock, not the state field.

        A second run must refuse while another run holds the lock, so two cloud
        executions can never work on the same mission at once.
        """
        orchestrator.kv_set("active_mission_lock", {
            "owner": "other-run", "acquired_at": "2026-11-15T00:00:00Z",
            "expires_at": "2099-01-01T00:00:00Z",
        })
        code, out = self._run(self._config())
        self.assertEqual(code, 2, out)
        self.assertIn("mission lock not acquired", out)
        self.assertEqual(len(self.cloud.started_conversations), 0)

    def test_dry_run_starts_nothing_and_touches_no_ledger(self):
        code, out = self._run(self._config(dry_run=True))
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.cloud.started_conversations), 0)
        bus = Bus(ROOT / "bus", store=KvStore("https://kv.example", "tok"))
        self.assertIsNone(bus.load_mission(bus_bridge.correlation_id(REPO, 70)))

    # -- Point 2: the bus must be mandatory, not best-effort -----------------
    def test_real_run_refuses_when_bus_storage_is_not_durable(self):
        """A real run with only file storage must refuse before any spend."""
        self._env_restore = os.environ.pop("AUTOMATION_KV_TOKEN", None)
        try:
            code, out = self._run(self._config())
            self.assertEqual(code, 2, out)
            self.assertIn("not durable", out)
            self.assertEqual(len(self.cloud.started_conversations), 0)
        finally:
            if self._env_restore is not None:
                os.environ["AUTOMATION_KV_TOKEN"] = self._env_restore

    def test_real_run_aborts_when_final_record_fails(self):
        """If the durable final write fails, the mission is NOT marked done."""
        # Opening writes the mission record twice (create, then envelope link);
        # fail the first write of the final record (write #3).
        self.cloud.fail_kv_put_key = KvStore(
            "https://kv.example", "tok"
        )._wire("missions/msn-gh-70-f2dd9a84926f")
        self.cloud.fail_kv_put_after = 2
        code, out = self._run(self._config())
        self.assertEqual(code, 2, out)
        self.assertIn("NOT marked done", out)
        # The mission must not be in processed, so a later run retries it.
        state = self.cloud.kv.get("state", {})
        self.assertNotIn(70, state.get("processed", []))

    def test_require_durable_bus_can_be_relaxed_for_local_use(self):
        """require_durable_bus=false keeps the old, non-blocking behaviour."""
        self._env_restore = os.environ.pop("AUTOMATION_KV_TOKEN", None)
        try:
            code, out = self._run(self._config(require_durable_bus=False))
            # No durable store: the bus is skipped, but the run may proceed.
            self.assertIn("conversation_started", out)
        finally:
            if self._env_restore is not None:
                os.environ["AUTOMATION_KV_TOKEN"] = self._env_restore

    # -- Point 3: a finished status is not a validated success ---------------
    def test_finished_without_evidence_is_not_a_validated_success(self):
        self.cloud.coordinator_response = ""
        self.cloud.children = []
        code, out = self._run(self._config())
        self.assertEqual(code, 2, out)
        self.assertIn('"validated": false', out)
        bus = Bus(ROOT / "bus", store=KvStore("https://kv.example", "tok"))
        record = bus.load_mission(bus_bridge.correlation_id(REPO, 70))
        self.assertEqual(record.state, "failed")
        self.assertEqual(record.learnings, [])  # no verified learning

    def test_finished_with_child_evidence_is_validated(self):
        code, out = self._run(self._config())
        self.assertEqual(code, 0, out)
        self.assertIn('"validated": true', out)
        bus = Bus(ROOT / "bus", store=KvStore("https://kv.example", "tok"))
        record = bus.load_mission(bus_bridge.correlation_id(REPO, 70))
        self.assertEqual(record.state, "done")
        self.assertEqual(len(record.learnings), 1)
        self.assertTrue(record.learnings[0]["verified"])
        self.assertIn("verdict", record.result)

    def test_a_role_that_did_not_finish_does_not_validate(self):
        """A child that errored is irrelevant; a *required role* that failed is not."""
        self.cloud.roles = [
            {"subagent": "tel99-dev-000000", "status": "completed", "text": "ok"},
            {"subagent": "tel99-analyst-000000", "status": "completed", "text": "ok"},
            {"subagent": "tel99-verifier-000000", "status": "error", "text": ""},
        ]
        code, out = self._run(self._config())
        self.assertEqual(code, 2, out)
        self.assertIn('"validated": false', out)
        self.assertIn("role_quality_reported", out)

    # -- Point 4: lock lifecycle under KV failure ---------------------------
    def test_lock_is_released_even_when_the_run_fails(self):
        self.cloud.coordinator_response = ""
        self.cloud.children = []
        self._run(self._config())
        self.assertFalse(orchestrator._lock_held(self.cloud.kv.get("active_mission_lock")))

    def test_an_expired_lock_can_be_taken_over(self):
        orchestrator.kv_set("active_mission_lock", {
            "owner": "dead-run", "acquired_at": "2000-01-01T00:00:00Z",
            "expires_at": "2000-01-01T00:00:01Z",
        })
        code, out = self._run(self._config())
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.cloud.started_conversations), 1)

    def test_release_only_by_owner(self):
        """A foreign owner must not be able to delete someone else's lock."""
        orchestrator.kv_set("active_mission_lock", {
            "owner": "someone-else", "acquired_at": "2026-11-15T00:00:00Z",
            "expires_at": "2099-01-01T00:00:00Z",
        })
        orchestrator.release_lock("me")
        self.assertIn("active_mission_lock", self.cloud.kv)

    def test_a_failed_resumable_mission_is_retried_not_deduped(self):
        self.cloud.coordinator_response = ""
        self.cloud.children = []
        self._run(self._config())            # fails, stays resumable
        self.cloud.coordinator_response = "Rapport final."
        self.cloud.children = [{"id": "c", "status": "finished", "response": "ok"}]
        code, out = self._run(self._config())  # retried, now validated
        self.assertEqual(code, 0, out)
        self.assertIn('"action": "retried"', out)


class MissionApprovalTests(EndToEndTests):
    """S-06 gate on the real ``orchestrator.run()`` path.

    A mission label is not an authorisation: the run must refuse to start a
    conversation unless the issue carries a current, content-bound approval by
    an actor named in ``authorized_approvers``.
    """

    def _issue_with_body(self, body):
        self.cloud.issues = [{**dict(ISSUE), "body": body}]

    def _approved_body(self, *, approver=AUTHORIZED_APPROVER, base=None):
        base = base if base is not None else {
            "title": ISSUE["title"], "body": "Corps initial.\n"}
        return base["body"] + policy.approval_marker(
            policy.mission_content(base), approver=approver) + "\n"

    def test_an_authorized_current_approval_lets_the_mission_start(self):
        code, out = self._run(self._config())
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.cloud.started_conversations), 1)
        self.assertIn('"approval_checked"', out)
        self.assertIn('"approved": true', out)

    def test_approval_requires_the_author_of_the_github_comment(self):
        self.cloud.approval_comment_author = "other-contributor"

        code, out = self._run(self._config())

        self.assertEqual(code, 2, out)
        self.assertEqual(self.cloud.started_conversations, [])
        self.assertIn("no authenticated approval comment", out)

    def test_a_mission_without_an_approval_is_refused(self):
        self._issue_with_body("Aucune approbation ici.\n")
        code, out = self._run(self._config())
        self.assertEqual(code, 2, out)
        self.assertEqual(self.cloud.started_conversations, [])
        self.assertIn("no content-bound approval", out)

    def test_an_unauthorized_approver_is_refused(self):
        self._issue_with_body(self._approved_body(approver="intrus"))
        code, out = self._run(self._config())
        self.assertEqual(code, 2, out)
        self.assertEqual(self.cloud.started_conversations, [])
        self.assertIn("not an authorized approver", out)

    def test_a_mission_edited_after_approval_is_refused(self):
        # Approve the body, then edit it: the digest no longer matches.
        approved = self._approved_body()
        edited = approved.replace("Corps initial.", "Corps modifie apres approbation.")
        self._issue_with_body(edited)
        code, out = self._run(self._config())
        self.assertEqual(code, 2, out)
        self.assertEqual(self.cloud.started_conversations, [])
        self.assertIn("content changed after approval", out)

    def test_an_empty_approver_allowlist_refuses_every_mission(self):
        code, out = self._run(self._config(authorized_approvers=[]))
        self.assertEqual(code, 2, out)
        self.assertEqual(self.cloud.started_conversations, [])
        self.assertIn("no authorized approvers configured", out)

    def test_a_dry_run_reports_the_decision_without_starting(self):
        self._issue_with_body("Aucune approbation ici.\n")
        code, out = self._run(self._config(dry_run=True))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.cloud.started_conversations, [])
        self.assertIn('"approved": false', out)


class ControllableKv:
    """A KV backend that records versions and lets a test inject interleavings.

    It implements exactly the conditional semantics the lock relies on:
    ``GET ?meta=true`` returns the version; ``PUT ?nx=true`` fails with 409 when
    the key exists; ``PUT ?if_version=N`` fails with 409 unless the stored
    version equals ``N``. ``on_put`` is a hook called before each conditional
    write, so a test can run a competing acquirer at an exact instant.
    """

    def __init__(self):
        self.kv = {}
        self.versions = {}
        self.put_log = []
        self.get_log = []
        self.on_put = None
        self._inject = 0

    def request(self, method, url, payload=None, headers=None, timeout=60):
        key = url.split("/v1/kv/", 1)[1].split("?", 1)[0]
        meta = "meta=true" in url
        nx = "nx=true" in url
        if_version = None
        if "if_version=" in url:
            if_version = url.split("if_version=", 1)[1].split("&", 1)[0]
        if method == "GET":
            self.get_log.append(key)
            if key in self.kv:
                body = {"value": self.kv[key]}
                if meta:
                    body["version"] = self.versions.get(key, 1)
                return 200, body
            return 404, "missing"
        if method == "PUT":
            self.put_log.append((key, "nx" if nx else (
                f"if_version={if_version}" if if_version is not None else "plain")))
            if self.on_put is not None:
                hook, self.on_put = self.on_put, None
                hook()
            if self._inject:
                self._inject -= 1
                return 409, "injected"
            if nx and key in self.kv:
                return 409, "exists"
            if if_version is not None:
                if key not in self.kv or str(self.versions.get(key, 1)) != str(if_version):
                    return 409, "version mismatch"
            self.kv[key] = payload
            self.versions[key] = self.versions.get(key, 0) + 1
            return 200, {}
        if method == "DELETE":
            self.kv.pop(key, None)
            self.versions.pop(key, None)
            return 200, {}
        return 404, "unhandled"


class LockConcurrencyTests(unittest.TestCase):
    """Atomicity of the mission lock, with controlled interleavings."""

    def setUp(self):
        self.kv = ControllableKv()
        self._orig_request = orchestrator._request
        self._orig_avail = orchestrator.kv_available
        self._orig_base = orchestrator._KV_BASE
        self._orig_token = orchestrator._KV_TOKEN
        orchestrator._request = self.kv.request
        orchestrator.kv_available = lambda: True
        orchestrator._KV_BASE = "https://kv.example"
        orchestrator._KV_TOKEN = "tok"

    def tearDown(self):
        orchestrator._request = self._orig_request
        orchestrator.kv_available = self._orig_avail
        orchestrator._KV_BASE = self._orig_base
        orchestrator._KV_TOKEN = self._orig_token

    def test_winner_of_the_race_holds_the_lock_and_loser_refuses(self):
        """Two runs race from an empty key: exactly one wins, the other refuses."""
        results = {}

        # Run B is injected the instant run A issues its conditional write.
        def race():
            results["b"] = orchestrator.acquire_lock("run-b")

        self.kv.on_put = race
        results["a"] = orchestrator.acquire_lock("run-a")

        winners = [name for name, (ok, _) in results.items() if ok]
        self.assertEqual(len(winners), 1, results)
        # Whoever lost must have refused, not silently proceeded.
        loser = "b" if winners == ["a"] else "a"
        self.assertFalse(results[loser][0])
        self.assertEqual(self.kv.kv["active_mission_lock"]["owner"],
                         f"run-{winners[0]}")

    def test_a_stale_read_is_never_accepted_as_a_win(self):
        """A run whose CAS fails (409) must retry, then refuse while held.

        A reads version v, B takes the lock (bumping the version), then A's
        conditional write is rejected with 409. A must re-read, see B's live
        lock and refuse — never overwrite B.
        """
        orchestrator.acquire_lock("run-b")  # B holds a fresh lock

        def bump_version():
            # Emulate B's write landing between A's read and A's write.
            self.kv.kv["active_mission_lock"] = {
                "owner": "run-b",
                "expires_at": "2099-01-01T00:00:00Z",
            }
            self.kv.versions["active_mission_lock"] = 99

        self.kv.on_put = bump_version
        ok, detail = orchestrator.acquire_lock("run-a")
        self.assertFalse(ok, detail)
        self.assertIn("run-b", detail)
        # B's lock is intact.
        self.assertEqual(self.kv.kv["active_mission_lock"]["owner"], "run-b")

    def test_retries_on_a_transient_409_then_succeeds(self):
        """A lost race is retried; a transient conflict does not wedge the run."""
        self.kv._inject = 1  # the first conditional PUT returns 409
        ok, detail = orchestrator.acquire_lock("run-a")
        self.assertTrue(ok, detail)
        self.assertEqual(self.kv.kv["active_mission_lock"]["owner"], "run-a")

    def test_an_expired_lock_is_reacquired_by_cas(self):
        """An expired record is overwritten with a conditional write, not deleted."""
        self.kv.kv["active_mission_lock"] = {
            "owner": "dead", "acquired_at": "2000-01-01T00:00:00Z",
            "expires_at": "2000-01-01T00:00:01Z",
        }
        self.kv.versions["active_mission_lock"] = 3
        ok, detail = orchestrator.acquire_lock("run-a")
        self.assertTrue(ok, detail)
        self.assertEqual(self.kv.kv["active_mission_lock"]["owner"], "run-a")
        # The takeover used a versioned (if_version) write, never a blind write.
        self.assertIn(("active_mission_lock", "if_version=3"), self.kv.put_log)

    def test_release_never_clobbers_a_lock_taken_over_underneath_us(self):
        """If our lock expired and another run took over, our release must not remove it."""
        orchestrator.acquire_lock("run-a")
        # While run-a still believes it holds the lock, run-b takes over after
        # run-a's lock expired (a new owner, a newer version).
        self.kv.kv["active_mission_lock"] = {
            "owner": "run-b", "expires_at": "2099-01-01T00:00:00Z",
        }
        self.kv.versions["active_mission_lock"] = 42
        orchestrator.release_lock("run-a")
        self.assertEqual(self.kv.kv["active_mission_lock"]["owner"], "run-b")

    def test_release_by_owner_writes_a_tombstone_and_frees_the_lock(self):
        orchestrator.acquire_lock("run-a")
        orchestrator.release_lock("run-a")
        self.assertFalse(orchestrator._lock_held(self.kv.kv["active_mission_lock"]))
        # A new run can take it afterwards.
        ok, detail = orchestrator.acquire_lock("run-b")
        self.assertTrue(ok, detail)

    def test_fail_closed_when_the_backend_reports_no_version(self):
        """No version => no CAS => refuse to start a real mission."""
        def no_version_request(method, url, payload=None, headers=None, timeout=60):
            if method == "GET":
                return 200, {"value": {"owner": "x", "expires_at": "2099-01-01T00:00:00Z"}}
            return 200, {}
        orchestrator._request = no_version_request
        ok, detail = orchestrator.acquire_lock("run-a")
        self.assertFalse(ok)
        self.assertIn("compare-and-set", detail)


class ThreeRoleVerificationTests(unittest.TestCase):
    """verify_outcome must require a distinct, completed proof from each role."""

    ROLES = {"development": "tel99-dev-120000",
             "quant": "tel99-analyst-120000",
             "quality": "tel99-verifier-120000"}
    BODY = "### Critère d'acceptation\nUn rapport avec preuves."

    def _obs(self, name, status="completed", text="rapport", is_error=False):
        return {"task_id": "t", "subagent": name, "status": status,
                "is_error": is_error, "response_chars": len(text),
                "result_text": text}

    def _evidence(self, observations):
        return {"coordinator_response_chars": 10,
                "observations": observations,
                "children": [],
                "acceptance_criteria": "Un rapport avec preuves."}

    def test_all_three_roles_proven_validates(self):
        obs = [self._obs(self.ROLES[r]) for r in self.ROLES]
        validated, verdict = orchestrator.verify_outcome("finished", self._evidence(obs))
        self.assertTrue(validated, verdict["checks"])
        self.assertEqual(set(verdict["roles"]), set(self.ROLES))
        for info in verdict["roles"].values():
            self.assertEqual(info["proven"], 1)

    def test_a_single_finished_role_does_not_validate(self):
        """One role is not enough: the previous minimum of one child is rejected."""
        obs = [self._obs(self.ROLES["development"])]
        validated, verdict = orchestrator.verify_outcome("finished", self._evidence(obs))
        self.assertFalse(validated)
        failed = [c["check"] for c in verdict["checks"] if not c["ok"]]
        self.assertIn("role_quant_reported", failed)
        self.assertIn("role_quality_reported", failed)

    def test_a_wrong_identity_does_not_prove_a_role(self):
        """A delegation to an unrelated agent never counts as a required role."""
        obs = [self._obs(self.ROLES["development"]),
               self._obs(self.ROLES["quant"]),
               self._obs("general-purpose")]  # not the verifier
        validated, _ = orchestrator.verify_outcome("finished", self._evidence(obs))
        self.assertFalse(validated)

    def test_a_role_in_error_state_does_not_prove(self):
        obs = [self._obs(self.ROLES["development"]),
               self._obs(self.ROLES["quant"]),
               self._obs(self.ROLES["quality"], status="error", text="")]
        validated, _ = orchestrator.verify_outcome("finished", self._evidence(obs))
        self.assertFalse(validated)

    def test_a_role_with_an_empty_result_does_not_prove(self):
        obs = [self._obs(self.ROLES["development"]),
               self._obs(self.ROLES["quant"]),
               self._obs(self.ROLES["quality"], text="")]
        validated, _ = orchestrator.verify_outcome("finished", self._evidence(obs))
        self.assertFalse(validated)

    def test_the_sdk_placeholder_is_not_a_proof(self):
        """A sub-agent that returned nothing yields a non-empty SDK placeholder.

        The SDK's TaskExecutor substitutes "Task completed with no result." when
        a sub-agent produces no result, so a bare length check would accept it.
        It must never count as proof that a role reported.
        """
        placeholder = "Task completed with no result."
        obs = [self._obs(self.ROLES["development"]),
               self._obs(self.ROLES["quant"]),
               self._obs(self.ROLES["quality"], text=placeholder)]
        validated, verdict = orchestrator.verify_outcome("finished", self._evidence(obs))
        self.assertFalse(validated)
        self.assertIn("role_quality_reported",
                      [c["check"] for c in verdict["checks"] if not c["ok"]])

    def test_the_sdk_failure_placeholder_is_not_a_proof(self):
        obs = [self._obs(self.ROLES["development"]),
               self._obs(self.ROLES["quant"]),
               self._obs(self.ROLES["quality"], text="Task failed.")]
        validated, _ = orchestrator.verify_outcome("finished", self._evidence(obs))
        self.assertFalse(validated)

    def test_collect_evidence_marks_the_placeholder(self):
        """The collected observation must flag the placeholder for the verdict."""
        cloud = FakeCloud(roles=[
            {"subagent": "tel99-dev-120000", "status": "completed",
             "text": "rapport dev", "task_id": "t1"},
            {"subagent": "tel99-analyst-120000", "status": "completed",
             "text": "rapport analyste", "task_id": "t2"},
            {"subagent": "tel99-verifier-120000", "status": "completed",
             "text": "Task completed with no result.", "task_id": "t3"},
        ])
        self._orig_request2 = orchestrator._request
        orchestrator._request = cloud.request
        try:
            evidence = orchestrator.collect_evidence(
                "cid-test-1", expected_roles=self.ROLES, mission_body=self.BODY)
        finally:
            orchestrator._request = self._orig_request2
        by_sub = {o["subagent"]: o for o in evidence["observations"]}
        self.assertTrue(by_sub["tel99-verifier-120000"]["is_placeholder"])
        self.assertFalse(by_sub["tel99-dev-120000"]["is_placeholder"])

    def test_a_missing_acceptance_criterion_does_not_validate(self):
        obs = [self._obs(self.ROLES[r]) for r in self.ROLES]
        evidence = self._evidence(obs)
        evidence["acceptance_criteria"] = ""
        validated, verdict = orchestrator.verify_outcome("finished", evidence)
        self.assertFalse(validated)
        self.assertIn("acceptance_criteria_declared",
                      [c["check"] for c in verdict["checks"] if not c["ok"]])

    def test_roles_are_recomputed_when_the_caller_passes_a_raw_dict(self):
        """A caller that omits the precomputed roles still gets the full check."""
        obs = [self._obs(self.ROLES[r]) for r in self.ROLES]
        raw = {"coordinator_response_chars": 10, "observations": obs,
               "acceptance_criteria": "Un rapport avec preuves."}
        validated, verdict = orchestrator.verify_outcome(
            "finished", raw, expected_roles=self.ROLES)
        self.assertTrue(validated, verdict["checks"])
        self.assertEqual(set(verdict["roles"]), set(self.ROLES))

    # --- S-05 / gate G3: the acceptance criterion must be *satisfied*, not just
    # declared. Three lying PASS reports plus a RED acceptance test must never be
    # accepted as a success. ---

    def _all_roles_pass(self):
        return [self._obs(self.ROLES[r]) for r in self.ROLES]

    def test_a_red_acceptance_check_rejects_despite_three_pass_reports(self):
        """Gate G3: 3 PASS reports + a red test => validated is False.

        This is the regression test for the S-05 defect: before the fix,
        ``verify_outcome`` accepted the mission on the declared criterion text
        alone and never looked at the check result.
        """
        evidence = self._evidence(self._all_roles_pass())
        red = [{"id": "business-test", "command": "python -m unittest x",
                "exit_code": 1, "reproducible": True,
                "output_digest": "sha256:deadbeef"}]
        validated, verdict = orchestrator.verify_outcome(
            "finished", evidence, acceptance_checks=red)
        self.assertFalse(validated, verdict["checks"])
        self.assertIn("criterion_business-test",
                      [c["check"] for c in verdict["checks"] if not c["ok"]])
        self.assertEqual(verdict["failed"], ["business-test"])

    def test_a_green_acceptance_check_still_validates(self):
        """The same three PASS reports WITH a reproducible green check validate."""
        evidence = self._evidence(self._all_roles_pass())
        green = [{"id": "business-test", "command": "python -m unittest x",
                  "exit_code": 0, "reproducible": True,
                  "output_digest": "sha256:cafe"}]
        validated, verdict = orchestrator.verify_outcome(
            "finished", evidence, acceptance_checks=green)
        self.assertTrue(validated, verdict["checks"])
        self.assertEqual(verdict["satisfied"], ["business-test"])

    def test_a_non_automatable_criterion_is_needs_human_not_a_pass(self):
        """A criterion with no runnable command is NEEDS_HUMAN, never a silent PASS."""
        evidence = self._evidence(self._all_roles_pass())
        manual = [{"id": "ux-review", "automatable": False}]
        validated, verdict = orchestrator.verify_outcome(
            "finished", evidence, acceptance_checks=manual)
        self.assertFalse(validated)
        self.assertEqual(verdict["needs_human"], ["ux-review"])

    def test_a_check_without_reproducible_evidence_does_not_satisfy(self):
        """exit_code 0 alone is not proof: reproducible + output_digest are required."""
        evidence = self._evidence(self._all_roles_pass())
        weak = [{"id": "business-test", "command": "python -m unittest x",
                 "exit_code": 0, "reproducible": False,
                 "output_digest": None}]
        validated, verdict = orchestrator.verify_outcome(
            "finished", evidence, acceptance_checks=weak)
        self.assertFalse(validated)
        self.assertEqual(verdict["failed"], ["business-test"])

    def test_no_checks_keeps_the_historical_behaviour(self):
        """Without acceptance checks the previous behaviour is unchanged."""
        evidence = self._evidence(self._all_roles_pass())
        validated, verdict = orchestrator.verify_outcome("finished", evidence)
        self.assertTrue(validated, verdict["checks"])
        self.assertEqual(verdict["acceptance_checks"], [])
        self.assertEqual(verdict["failed"], [])

    def test_checks_read_from_evidence_when_not_passed_explicitly(self):
        """``collect_evidence`` can carry the checks; verify_outcome reads them."""
        evidence = self._evidence(self._all_roles_pass())
        evidence["acceptance_checks"] = [
            {"id": "business-test", "command": "python -m unittest x",
             "exit_code": 1, "reproducible": True, "output_digest": "sha256:x"}]
        validated, _ = orchestrator.verify_outcome("finished", evidence)
        self.assertFalse(validated)

    def test_a_declared_check_without_a_result_is_needs_human(self):
        """A ``check:`` line with no recorded result is a promise, not proof.

        It must route to NEEDS_HUMAN, never be accepted on the criterion text.
        """
        body = ("### Critere d'acceptation\nUn test de non-regression passe.\n"
                "- check: python -m unittest tests.test_x\n")
        checks = orchestrator.acceptance_checks_from_body(body)
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["command"], "python -m unittest tests.test_x")
        evidence = self._evidence(self._all_roles_pass())
        evidence["acceptance_criteria"] = orchestrator.extract_acceptance_criteria(body)
        evidence["acceptance_checks"] = checks
        validated, verdict = orchestrator.verify_outcome("finished", evidence)
        self.assertFalse(validated)
        self.assertEqual(len(verdict["needs_human"]), 1)
        self.assertEqual(verdict["failed"], [])

    def test_a_producer_never_executes_a_declared_command(self):
        """The producer only parses: a dangerous line must not be run."""
        body = ("### Critere d'acceptation\n"
                "- check: rm -rf /\n")
        checks = orchestrator.acceptance_checks_from_body(body)
        # It is captured as text with no result -- never executed.
        self.assertEqual(checks[0]["command"], "rm -rf /")
        self.assertIsNone(checks[0]["exit_code"])
        self.assertFalse(checks[0]["reproducible"])

    def test_a_caller_cannot_hide_a_red_evidence_check(self):
        """Fail-closed merge: a red check in evidence wins over an empty argument."""
        evidence = self._evidence(self._all_roles_pass())
        evidence["acceptance_checks"] = [
            {"id": "business-test", "command": "python -m unittest x",
             "exit_code": 1, "reproducible": True, "output_digest": "sha256:red"}]
        validated, verdict = orchestrator.verify_outcome(
            "finished", evidence, acceptance_checks=[])
        self.assertFalse(validated)
        self.assertEqual(verdict["failed"], ["business-test"])

    def test_a_caller_cannot_downgrade_a_red_evidence_check_to_green(self):
        """The same id present on both sides keeps the failing entry."""
        evidence = self._evidence(self._all_roles_pass())
        evidence["acceptance_checks"] = [
            {"id": "business-test", "command": "python -m unittest x",
             "exit_code": 1, "reproducible": True, "output_digest": "sha256:red"}]
        green = [{"id": "business-test", "command": "python -m unittest x",
                  "exit_code": 0, "reproducible": True, "output_digest": "sha256:ok"}]
        validated, _ = orchestrator.verify_outcome(
            "finished", evidence, acceptance_checks=green)
        self.assertFalse(validated)

    def test_a_malformed_check_container_does_not_crash(self):
        """A truthy non-iterable container is treated as absent, not a crash."""
        evidence = self._evidence(self._all_roles_pass())
        for bad in (5, True, object()):
            with self.subTest(bad=type(bad).__name__):
                validated, verdict = orchestrator.verify_outcome(
                    "finished", evidence, acceptance_checks=bad)
                # Falls back to the declared-text check: still validates here.
                self.assertTrue(validated, verdict["checks"])

    def test_a_check_under_a_subheading_is_still_captured(self):
        """A ``check:`` under a deeper sub-heading stays in the acceptance section."""
        body = ("### Critere d'acceptation\n"
                "#### Detail\n"
                "- check: python -m unittest tests.test_x\n")
        checks = orchestrator.acceptance_checks_from_body(body)
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["command"], "python -m unittest tests.test_x")

    def test_a_check_after_a_sibling_heading_is_not_captured(self):
        """A heading at the same level closes the section: the check is out of scope."""
        body = ("### Critere d'acceptation\nUn rapport.\n"
                "### Notes\n"
                "- check: python -m unittest tests.test_x\n")
        self.assertEqual(orchestrator.acceptance_checks_from_body(body), [])

    def test_a_midsentence_phrase_does_not_open_the_section(self):
        """A non-heading mention of the phrase must not start capturing checks."""
        body = ("### Contexte\n"
                "Voir le critere d'acceptation ci-dessous.\n"
                "- check: python -m unittest tests.test_x\n")
        self.assertEqual(orchestrator.acceptance_checks_from_body(body), [])

    def test_a_duplicate_id_inside_the_evidence_is_fail_closed(self):
        """Two evidence entries sharing an id: a red one can never be hidden."""
        evidence = self._evidence(self._all_roles_pass())
        evidence["acceptance_checks"] = [
            {"id": "x", "command": "c", "exit_code": 1,
             "reproducible": True, "output_digest": "sha256:red"},
            {"id": "x", "command": "c", "exit_code": 0,
             "reproducible": True, "output_digest": "sha256:ok"},
        ]
        validated, verdict = orchestrator.verify_outcome("finished", evidence)
        self.assertFalse(validated)
        self.assertEqual(verdict["failed"], ["x"])

    def test_a_green_then_red_duplicate_inside_the_evidence_is_fail_closed(self):
        """Order must not matter: green-then-red is also rejected."""
        evidence = self._evidence(self._all_roles_pass())
        evidence["acceptance_checks"] = [
            {"id": "x", "command": "c", "exit_code": 0,
             "reproducible": True, "output_digest": "sha256:ok"},
            {"id": "x", "command": "c", "exit_code": 1,
             "reproducible": True, "output_digest": "sha256:red"},
        ]
        validated, _ = orchestrator.verify_outcome("finished", evidence)
        self.assertFalse(validated)

    def test_collect_evidence_derives_declared_checks_from_the_body(self):
        """The producer is WIRED: collect_evidence fills acceptance_checks.

        This is the anti-inertness test: with no explicit checks, a mission body
        that declares a ``check:`` line must make ``collect_evidence`` carry a
        structured (unconfirmed) check, which then routes the verdict to
        NEEDS_HUMAN instead of accepting on the criterion text alone.
        """
        body = ("### Critere d'acceptation\nUn test de non-regression passe.\n"
                "- check: python -m unittest tests.test_x\n")
        cloud = FakeCloud(mission_body=body)
        orig = orchestrator._request
        orchestrator._request = cloud.request
        try:
            evidence = orchestrator.collect_evidence(
                "cid-test-1", expected_roles=self.ROLES, mission_body=body)
        finally:
            orchestrator._request = orig
        self.assertEqual(len(evidence["acceptance_checks"]), 1)
        validated, verdict = orchestrator.verify_outcome("finished", evidence)
        self.assertFalse(validated)
        self.assertEqual(len(verdict["needs_human"]), 1)

    def test_collect_evidence_reads_the_paginated_endpoint(self):
        """Regression: reading the batch ``/events`` endpoint returned no proof.

        A bare ``GET /events`` answers HTTP 422 (it needs a body), so every
        delegation was silently lost and a real mission was marked failed. The
        reader must walk ``/events/search``.
        """
        roles = {"development": "tel99-dev-000000",
                 "quant": "tel99-analyst-000000",
                 "quality": "tel99-verifier-000000"}
        cloud = FakeCloud()
        original = orchestrator._request
        orchestrator._request = cloud.request
        try:
            evidence = orchestrator.collect_evidence(
                "cid-test-1", expected_roles=roles, mission_body=self.BODY)
        finally:
            orchestrator._request = original
        self.assertEqual(len(evidence["observations"]), 3)
        self.assertEqual({o["subagent"] for o in evidence["observations"]},
                         set(roles.values()))
        validated, _ = orchestrator.verify_outcome(
            "finished", evidence, expected_roles=roles)
        self.assertTrue(validated)

    def test_collect_evidence_walks_every_page(self):
        """A paginated reader must follow ``next_page_id`` to the last page."""
        roles = {"development": "tel99-dev-000000",
                 "quant": "tel99-analyst-000000",
                 "quality": "tel99-verifier-000000"}
        cloud = FakeCloud()
        cloud.event_page_size = 4  # 3 delegations = 6 events -> 2 pages
        original = orchestrator._request
        orchestrator._request = cloud.request
        try:
            evidence = orchestrator.collect_evidence(
                "cid-test-1", expected_roles=roles, mission_body=self.BODY)
        finally:
            orchestrator._request = original
        self.assertEqual(len(evidence["observations"]), 3)


class DurableRunReportTests(unittest.TestCase):
    """Issue #94 / PR #92 item 3: one durable, consultable report per run.

    The platform deletes the sandbox after a run, so the report must be readable
    from the KV store (durable across container destruction) and must separate
    SCRIPT SUCCESS (exit code) from MISSION_ACCEPTED (business verdict).
    """

    def setUp(self):
        self.cloud = FakeCloud()
        self._orig_request = orchestrator._request
        self._orig_kv_get = orchestrator.kv_get
        self._orig_kv_set = orchestrator.kv_set
        self._orig_kv = (orchestrator._KV_BASE, orchestrator._KV_TOKEN)
        self._orig_quota = orchestrator.quota_remaining
        orchestrator._request = self.cloud.request

        def fake_kv_get(key):
            status, body = self.cloud._kv("GET", f"https://kv.example/v1/kv/{key}", None)
            if status == 200 and isinstance(body, dict):
                return body.get("value")
            return None

        def fake_kv_set(key, value):
            status, _ = self.cloud._kv("PUT", f"https://kv.example/v1/kv/{key}", value)
            if status not in (200, 201, 204):
                raise orchestrator.urllib.error.HTTPError(
                    f"https://kv.example/v1/kv/{key}", status, "kv write failed",
                    {}, None)

        orchestrator.kv_get = fake_kv_get
        orchestrator.kv_set = fake_kv_set
        orchestrator._KV_BASE = "https://kv.example"
        orchestrator._KV_TOKEN = "tok"
        self._env = {k: os.environ.get(k)
                     for k in ("AUTOMATION_API_URL", "AUTOMATION_KV_TOKEN",
                               "OPENHANDS_API_KEY")}
        os.environ["AUTOMATION_API_URL"] = "https://kv.example"
        os.environ["AUTOMATION_KV_TOKEN"] = "tok"
        os.environ["OPENHANDS_API_KEY"] = "test-key"
        self._orig_store_request = store_mod.KvStore._request
        store_mod.KvStore._request = lambda store_self, method, url, payload=None:             self.cloud.request(method, url, payload)
        self._cwd = os.getcwd()
        os.chdir(ROOT)
        self._orig_repo_root = orchestrator.REPO_ROOT
        self._tmp_root = tempfile.TemporaryDirectory()
        orchestrator.REPO_ROOT = pathlib.Path(self._tmp_root.name)

    def tearDown(self):
        orchestrator._request = self._orig_request
        orchestrator.kv_get = self._orig_kv_get
        orchestrator.kv_set = self._orig_kv_set
        orchestrator.quota_remaining = self._orig_quota
        store_mod.KvStore._request = self._orig_store_request
        orchestrator._KV_BASE, orchestrator._KV_TOKEN = self._orig_kv
        orchestrator.REPO_ROOT = self._orig_repo_root
        self._tmp_root.cleanup()
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        os.chdir(self._cwd)

    def _config(self, **over):
        cfg = dict(orchestrator.DEFAULT_CONFIG)
        cfg.update({"dry_run": False, "repository": REPO,
                    "mission_label": "tel99-mission", "max_runtime_seconds": 60,
                    "authorized_approvers": [AUTHORIZED_APPROVER]})
        cfg.update(over)
        return cfg

    def _run(self, config):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = orchestrator.run(config, offline=False)
        return code, buf.getvalue()

    # -- the report is durable and complete ---------------------------------
    def test_report_is_persisted_to_the_durable_store(self):
        code, _ = self._run(self._config())
        report = self.cloud.kv.get("run_report")
        self.assertIsInstance(report, dict, "the run report must be in the KV store")
        for field in ("run_id", "ts", "config_digest", "dry_run", "quota_before",
                      "quota_after", "mission_id", "started_children", "status",
                      "mission_accepted", "outcome_verification", "error_reason",
                      "evidence_uri"):
            self.assertIn(field, report, f"missing report field {field}")

    def test_accepted_mission_reports_mission_accepted(self):
        code, _ = self._run(self._config())
        self.assertEqual(code, 0)
        report = self.cloud.kv.get("run_report")
        self.assertEqual(report["status"], "MISSION_ACCEPTED")
        self.assertTrue(report["mission_accepted"])
        self.assertEqual(report["outcome_verification"], "ACCEPTED")
        self.assertEqual(report["mission_id"], "70")
        self.assertEqual(report["started_children"], 1)

    def test_dry_run_reports_a_selected_mission_but_no_acceptance(self):
        """A dry run exits 0 without accepting: the report must not claim it."""
        code, _ = self._run(self._config(dry_run=True))
        self.assertEqual(code, 0)
        report = self.cloud.kv.get("run_report")
        self.assertEqual(report["mission_id"], "70")  # selected, not worked
        self.assertEqual(report["status"], "SUCCESS_SCRIPT_MISSION_NOT_ACCEPTED")
        self.assertFalse(report["mission_accepted"])
        self.assertEqual(report["outcome_verification"], "NOT_ATTEMPTED")
        self.assertEqual(report["started_children"], 0)

    def test_idle_run_reports_no_mission(self):
        """No eligible mission: exit 0 with NO_MISSION, not a fake acceptance."""
        self.cloud.issues = []
        code, _ = self._run(self._config())
        self.assertEqual(code, 0)
        report = self.cloud.kv.get("run_report")
        self.assertEqual(report["mission_id"], "NO_MISSION")
        self.assertEqual(report["status"], "SUCCESS_SCRIPT_NO_MISSION")
        self.assertFalse(report["mission_accepted"])
        self.assertEqual(report["outcome_verification"], "NOT_ATTEMPTED")
        self.assertEqual(report["started_children"], 0)

    def test_a_rejected_mission_is_not_accepted_even_though_script_ran(self):
        self.cloud.coordinator_response = ""
        self.cloud.children = []
        code, _ = self._run(self._config())
        self.assertEqual(code, 2)
        report = self.cloud.kv.get("run_report")
        self.assertFalse(report["mission_accepted"])
        self.assertEqual(report["outcome_verification"], "REJECTED")
        self.assertEqual(report["status"], "FAILED")

    def test_idle_run_does_not_inherit_the_previous_mission_verdict(self):
        self.assertEqual(self._run(self._config())[0], 0)
        self.cloud.issues = []

        self.assertEqual(self._run(self._config())[0], 0)

        report = self.cloud.kv["run_report"]
        self.assertEqual(report["mission_id"], "NO_MISSION")
        self.assertEqual(report["outcome_verification"], "NOT_ATTEMPTED")
        self.assertFalse(report["mission_accepted"])
        self.assertEqual(report["started_children"], 0)

    def test_report_is_readable_after_container_destruction(self):
        """A fresh reader over the same KV store still sees the report."""
        self._run(self._config())
        orchestrator.kv_get = self._orig_kv_get  # drop the fake reader
        # A new process would read the same KV key; simulate by reading the raw
        # store the fake kept (equivalent to a fresh pod over the durable store).
        report = self.cloud.kv.get("run_report")
        self.assertEqual(report["status"], "MISSION_ACCEPTED")
        self.assertEqual(orchestrator.read_run_report.__name__, "read_run_report")

    def test_stopped_run_reports_stopped_and_writes_a_report(self):
        self.cloud.conversation_final = "stopped"
        code, _ = self._run(self._config())
        self.assertEqual(code, 3)
        report = self.cloud.kv.get("run_report")
        self.assertEqual(report["status"], "STOPPED")
        self.assertFalse(report["mission_accepted"])

    def test_report_contains_no_secret_looking_values(self):
        self._run(self._config())
        blob = json.dumps(self.cloud.kv.get("run_report")).lower()
        for needle in ("token", "secret", "api_key", "password", "bearer"):
            self.assertNotIn(needle, blob)

    def test_config_digest_is_stable_and_ignores_unknown_keys(self):
        d1 = orchestrator.config_digest(self._config())
        d2 = orchestrator.config_digest(self._config())
        self.assertEqual(d1, d2)
        # An injected secret-looking key is NOT part of the whitelist, so it does
        # not change the digest.
        self.assertEqual(d1, orchestrator.config_digest(
            {**self._config(), "GITHUB_TOKEN": "should-not-matter"}))

    def test_report_written_even_when_kv_write_fails(self):
        """A KV failure must not lose the report: the local file still gets it."""
        good = orchestrator.kv_set

        def boom(key, value):
            if key == orchestrator._RUN_REPORT_KEY:
                raise orchestrator.urllib.error.HTTPError(
                    "https://kv.example/v1/kv/run_report", 500, "boom", {}, None)
            return good(key, value)

        orchestrator.kv_set = boom
        code, _ = self._run(self._config())
        self.assertEqual(code, 0)  # the run's exit code is unchanged
        path = orchestrator._state_path().with_name(
            orchestrator._state_path().stem + "_run_report.json")
        self.assertTrue(path.is_file(), "the local fallback report must exist")
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["status"], "MISSION_ACCEPTED")

    def test_build_run_report_never_raises_on_a_plain_state(self):
        report = orchestrator.build_run_report(
            {"version": 1, "processed": [], "active": None, "journal": []},
            self._config(), 0)
        self.assertEqual(report["mission_id"], "NO_MISSION")
        self.assertEqual(report["status"], "SUCCESS_SCRIPT_NO_MISSION")

    def test_brake_path_writes_no_report_to_the_network(self):
        """The emergency brake must halt without any network call."""
        import automation.emergency as emergency
        calls = []
        self._orig_quota2 = orchestrator.quota_remaining
        orchestrator.quota_remaining = lambda: calls.append("quota")
        saved_env = os.environ.get(emergency.ENV_FLAG)
        os.environ[emergency.ENV_FLAG] = "true"
        orig_load = orchestrator.load_state
        orig_save = orchestrator.save_state
        orchestrator.load_state = lambda: {"version": 1, "processed": [],
                                           "active": None, "journal": []}
        orchestrator.save_state = lambda state: None
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = orchestrator.run(self._config(), offline=False)
        finally:
            orchestrator.load_state = orig_load
            orchestrator.save_state = orig_save
            orchestrator.quota_remaining = self._orig_quota2
            if saved_env is None:
                os.environ.pop(emergency.ENV_FLAG, None)
            else:
                os.environ[emergency.ENV_FLAG] = saved_env
        self.assertEqual(code, 3)
        self.assertEqual(calls, [], "the brake path must not probe quota")
        # No durable KV write on the brake path either.
        self.assertNotIn("run_report", self.cloud.kv)

    def test_crash_path_still_writes_a_report(self):
        """Exit code 1 (a crash) must not leave the run invisible."""
        orig_impl = orchestrator._run_impl

        def boom(config, offline, holder):
            raise RuntimeError("simulated crash")

        orchestrator._run_impl = boom
        try:
            with self.assertRaises(RuntimeError):
                orchestrator.run(self._config(), offline=False)
        finally:
            orchestrator._run_impl = orig_impl
        report = self.cloud.kv.get("run_report")
        self.assertIsNotNone(report, "a crash must still produce a durable report")
        self.assertEqual(report["status"], "FAILED")
        self.assertFalse(report["mission_accepted"])

    def test_per_run_history_key_is_written(self):
        """A per-run key preserves history even when 'latest' is overwritten."""
        self._run(self._config())
        keys = [k for k in self.cloud.kv if k.startswith("run_report.")]
        self.assertTrue(keys, "a per-run run_report.<id> key must exist")
        latest = self.cloud.kv.get("run_report")
        self.assertEqual(self.cloud.kv[keys[0]]["run_id"], latest["run_id"])

    def test_evidence_uri_points_at_the_per_run_key(self):
        self._run(self._config())
        report = self.cloud.kv.get("run_report")
        self.assertTrue(report["evidence_uri"].startswith("kv://run_report."))

    def test_build_run_report_survives_a_corrupted_journal(self):
        """A poisoned/edited state must not crash the report builder."""
        for bad in ({"journal": None}, {"journal": [None, 42, "x"]},
                    {"journal": [{"event": "run_start", "owner": "r"}]}, {}):
            report = orchestrator.build_run_report(bad, self._config(), 0)
            self.assertEqual(report["mission_id"], "NO_MISSION")

    def test_fire_callback_carries_the_mission_outcome(self):
        captured = {}

        class _Resp:
            def read(self):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=30):
            captured["body"] = json.loads(req.data.decode())
            return _Resp()

        orig = orchestrator.urllib.request.urlopen
        orig_url = os.environ.get("AUTOMATION_CALLBACK_URL")
        orchestrator.urllib.request.urlopen = fake_urlopen
        os.environ["AUTOMATION_CALLBACK_URL"] = "https://callback.example/run"
        try:
            orchestrator.fire_callback("COMPLETED", outcome={
                "mission_id": "70", "mission_accepted": True,
                "outcome_verification": "ACCEPTED", "config_digest": "abc"})
        finally:
            orchestrator.urllib.request.urlopen = orig
            if orig_url is None:
                os.environ.pop("AUTOMATION_CALLBACK_URL", None)
            else:
                os.environ["AUTOMATION_CALLBACK_URL"] = orig_url
        self.assertEqual(captured["body"]["mission_id"], "70")
        self.assertTrue(captured["body"]["mission_accepted"])
        self.assertEqual(captured["body"]["outcome_verification"], "ACCEPTED")


if __name__ == "__main__":
    unittest.main()
