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
    "body": "Afficher l'age des donnees Kraken.",
    "state": "open",
    "labels": [{"name": "tel99-mission"}],
    "created_at": "2026-11-15T00:00:00Z",
}


class FakeCloud:
    """An in-memory stand-in for the KV store, GitHub and the agent server."""

    def __init__(self, *, conversation_final="finished", issues=None):
        self.kv: dict = {}
        self.issues = issues if issues is not None else [dict(ISSUE)]
        self.conversation_final = conversation_final
        self.started_conversations = []
        self.state_writes = 0

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
        # agent server
        if url.endswith("/api/conversations") and method == "GET":
            return 200, []
        if url.endswith("/api/conversations") and method == "POST":
            self.started_conversations.append(payload)
            return 201, {"id": "cid-test-1"}
        if "/api/conversations/" in url and method == "GET":
            return 200, {"execution_status": self.conversation_final}
        if url.endswith("/interrupt"):
            return 200, {}
        return 404, "unhandled"

    def _kv(self, method, url, payload):
        key = url.split("/v1/kv/", 1)[1].split("?", 1)[0]
        nx = "nx=true" in url
        if method == "GET":
            if "?prefix=" in url:
                prefix = url.split("?prefix=", 1)[1]
                return 200, {"keys": [k for k in self.kv if k.startswith(prefix)]}
            if key in self.kv:
                return 200, {"value": self.kv[key]}
            return 404, "missing"
        if method == "PUT":
            if nx and key in self.kv:
                return 409, "exists"
            self.kv[key] = payload
            self.state_writes += 1
            return 200, {}
        if method == "DELETE":
            self.kv.pop(key, None)
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
            return self.cloud.kv.get(key)

        def fake_kv_set(key, value):
            self.cloud.kv[key] = value

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

    def tearDown(self):
        orchestrator._request = self._orig_request
        orchestrator.kv_get = self._orig_kv_get
        orchestrator.kv_set = self._orig_kv_set
        store_mod.KvStore._request = self._orig_store_request
        orchestrator._KV_BASE, orchestrator._KV_TOKEN = self._orig_kv
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
        self.assertNotIn("active_mission_lock", self.cloud.kv)

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


if __name__ == "__main__":
    unittest.main()
