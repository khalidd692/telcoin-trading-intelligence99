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
        self.started_conversations = []
        self.state_writes = 0
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
        # agent server: coordinator events (delegations + child launches)
        if url.endswith("/events") and method == "GET":
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
                return 200, events
            return 200, []
        # agent server: conversation list / single
        if url.endswith("/api/conversations") and method == "GET":
            return 200, []
        if url.endswith("/api/conversations") and method == "POST":
            self.started_conversations.append(payload)
            return 201, {"id": "cid-test-1"}
        if "/api/conversations/" in url and method == "GET":
            conv = url.split("/api/conversations/", 1)[1].split("/", 1)[0]
            if conv == "cid-test-1":
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
                    "mission_label": "tel99-mission", "max_runtime_seconds": 60})
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


if __name__ == "__main__":
    unittest.main()
