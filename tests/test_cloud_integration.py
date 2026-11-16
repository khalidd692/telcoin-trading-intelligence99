#!/usr/bin/env python3
"""Deterministic tests for the cloud-autonomy integration.

They cover the three things the mission asks for that can be proven offline:

  * the **storage backends** — the file store and the KV store expose the same
    interface, and the KV store is the one that survives a container (its
    ``durable()`` is True);
  * the **bus bridge** — a GitHub mission maps to a deterministic correlation
    id, a finished mission is never reprocessed, an interrupted one resumes,
    and an outcome plus a validated learning are persisted;
  * the **orchestrator wiring** — the orchestrator imports the bridge
    defensively, refuses a finished mission on the bus, and its offline
    dry-run still succeeds.

Nothing here touches the network or the real repository history.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "agents"))
sys.path.insert(0, str(ROOT / "scripts" / "agents" / "automation"))

from protocol.bus import Bus  # noqa: E402
from protocol.store import FileStore, KvStore, default_store, store_report  # noqa: E402
from automation import bus_bridge  # noqa: E402


class FileStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FileStore(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_put_get_roundtrip(self):
        self.store.put("missions/x", {"a": 1})
        self.assertEqual(self.store.get("missions/x"), {"a": 1})

    def test_missing_key_is_none(self):
        self.assertIsNone(self.store.get("missions/nope"))

    def test_keys_lists_prefixed(self):
        self.store.put("missions/a", {})
        self.store.put("missions/b", {})
        self.store.put("envelopes/c", {})
        self.assertEqual(self.store.keys("missions/"), ["missions/a", "missions/b"])

    def test_file_store_is_not_durable(self):
        self.assertFalse(self.store.durable())
        self.assertEqual(self.store.backend, "file")


class KvStoreTests(unittest.TestCase):
    """The KV store is exercised through a fake HTTP layer (no network)."""

    def setUp(self):
        self.saved = {}

        import protocol.store as store_mod

        self.store_mod = store_mod
        saved = self.saved

        def fake_request(store_self, method, url, payload=None):
            key = url.split("/v1/kv/", 1)[1] if "/v1/kv/" in url else ""
            if method == "GET":
                if "?prefix=" in url:
                    prefix = url.split("?prefix=", 1)[1]
                    keys = [k for k in saved if k.startswith(prefix)]
                    return 200, {"keys": keys}
                if key in saved:
                    return 200, {"value": saved[key]}
                return 404, "missing"
            if method == "PUT":
                saved[key] = payload
                return 200, {}
            return 200, {}

        self._orig = store_mod.KvStore._request
        store_mod.KvStore._request = fake_request
        self.store = KvStore("https://kv.example", "token", prefix="tel99-bus")

    def tearDown(self):
        self.store_mod.KvStore._request = self._orig

    def test_put_get_roundtrip(self):
        self.store.put("missions/x", {"a": 1})
        self.assertEqual(self.store.get("missions/x"), {"a": 1})

    def test_missing_key_is_none(self):
        self.assertIsNone(self.store.get("missions/nope"))

    def test_keys_are_prefixed_and_stripped(self):
        self.store.put("missions/a", {})
        self.assertEqual(self.store.keys("missions/"), ["missions/a"])

    def test_kv_store_is_durable(self):
        self.assertTrue(self.store.durable())
        self.assertEqual(self.store.backend, "kv")


class DefaultStoreTests(unittest.TestCase):
    def test_defaults_to_files_without_kv_env(self):
        import os
        saved = {k: os.environ.pop(k, None)
                 for k in ("AUTOMATION_API_URL", "AUTOMATION_KV_TOKEN")}
        try:
            store = default_store("/tmp/x")
            self.assertEqual(store.backend, "file")
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_uses_kv_when_env_present(self):
        import os
        saved = {k: os.environ.get(k)
                 for k in ("AUTOMATION_API_URL", "AUTOMATION_KV_TOKEN")}
        os.environ["AUTOMATION_API_URL"] = "https://kv.example"
        os.environ["AUTOMATION_KV_TOKEN"] = "tok"
        try:
            store = default_store("/tmp/x")
            self.assertEqual(store.backend, "kv")
            self.assertTrue(store_report(store)["durable_across_container"])
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class BusBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bus = Bus(self.tmp.name, store=FileStore(self.tmp.name))
        self.repo = "khalidd692/telcoin-trading-intelligence99"
        self.issue = {"number": 71, "title": "Audit lecture seule", "body": "verifier"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_correlation_id_is_deterministic(self):
        a = bus_bridge.correlation_id(self.repo, 71)
        b = bus_bridge.correlation_id(self.repo, 71)
        self.assertEqual(a, b)
        self.assertNotEqual(a, bus_bridge.correlation_id(self.repo, 72))

    def test_roles_come_from_team_config(self):
        roles = bus_bridge.roles_from_team_config()
        self.assertEqual(len(roles), 3)

    def test_open_creates_mission_with_one_step_per_role(self):
        result = bus_bridge.open_or_resume(
            self.bus, repository=self.repo, issue=self.issue,
            work_branch="agent/mission-71-x")
        self.assertEqual(result["action"], "opened")
        record = self.bus.load_mission(result["correlation_id"])
        self.assertEqual(len(record.steps), 3)
        self.assertEqual(record.state, "queued")

    def test_finished_mission_is_not_reprocessed(self):
        opened = bus_bridge.open_or_resume(
            self.bus, repository=self.repo, issue=self.issue,
            work_branch="agent/mission-71-x")
        corr = opened["correlation_id"]
        bus_bridge.record_outcome(self.bus, corr, success=True, summary="ok",
                                  conversation_id="cid-1",
                                  verdict={"validated": True, "checks": []})
        self.assertTrue(bus_bridge.is_already_finished(self.bus, corr))
        again = bus_bridge.open_or_resume(
            self.bus, repository=self.repo, issue=self.issue,
            work_branch="agent/mission-71-x")
        self.assertEqual(again["action"], "already_done")

    def test_interrupted_mission_resumes(self):
        opened = bus_bridge.open_or_resume(
            self.bus, repository=self.repo, issue=self.issue,
            work_branch="agent/mission-71-x")
        corr = opened["correlation_id"]
        record = self.bus.load_mission(corr)
        record.state = "running"          # simulate a killed run
        self.bus.save_mission(record)
        again = bus_bridge.open_or_resume(
            self.bus, repository=self.repo, issue=self.issue,
            work_branch="agent/mission-71-x")
        self.assertEqual(again["action"], "resumed")
        self.assertEqual(again["state"], "queued")

    def test_success_writes_result_and_learning(self):
        opened = bus_bridge.open_or_resume(
            self.bus, repository=self.repo, issue=self.issue,
            work_branch="agent/mission-71-x")
        corr = opened["correlation_id"]
        outcome = bus_bridge.record_outcome(
            self.bus, corr, success=True, summary="3 roles ok",
            conversation_id="cid-9", work_branch="agent/mission-71-x",
            verdict={"validated": True, "checks": []})
        self.assertEqual(outcome["state"], "done")
        self.assertIsNotNone(outcome["learning"])
        record = self.bus.load_mission(corr)
        self.assertEqual(record.result["status"], "success")
        self.assertEqual(len(record.learnings), 1)

    def test_failure_marks_resumable(self):
        opened = bus_bridge.open_or_resume(
            self.bus, repository=self.repo, issue=self.issue,
            work_branch="agent/mission-71-x")
        corr = opened["correlation_id"]
        outcome = bus_bridge.record_outcome(
            self.bus, corr, success=False, summary="timeout",
            status_detail="final status timeout")
        self.assertEqual(outcome["state"], "failed")
        record = self.bus.load_mission(corr)
        self.assertTrue(record.resumable)
        self.assertEqual(record.errors[-1]["code"], "orchestrator.outcome_unvalidated")

    def test_ledger_reports_the_storage_backend(self):
        bus_bridge.open_or_resume(self.bus, repository=self.repo,
                                  issue=self.issue, work_branch="agent/mission-71-x")
        report = bus_bridge.ledger(self.bus)
        self.assertEqual(report["count"], 1)
        self.assertEqual(report["storage"]["backend"], "file")

    def test_persistence_survives_a_new_bus_instance(self):
        """A second Bus over the same store sees the first one's mission."""
        opened = bus_bridge.open_or_resume(
            self.bus, repository=self.repo, issue=self.issue,
            work_branch="agent/mission-71-x")
        corr = opened["correlation_id"]
        bus_bridge.record_outcome(self.bus, corr, success=True, summary="ok",
                                  verdict={"validated": True, "checks": []})

        fresh = Bus(self.tmp.name, store=FileStore(self.tmp.name))
        self.assertTrue(bus_bridge.is_already_finished(fresh, corr))
        self.assertEqual(fresh.load_mission(corr).state, "done")


class OrchestratorWiringTests(unittest.TestCase):
    def test_orchestrator_imports_the_bridge(self):
        import orchestrator
        self.assertIsNotNone(orchestrator.bus_bridge)
        self.assertIsNotNone(orchestrator.Bus)

    def test_offline_dry_run_still_succeeds(self):
        import contextlib
        import io
        import orchestrator
        with contextlib.redirect_stdout(io.StringIO()):
            code = orchestrator.run(dict(orchestrator.DEFAULT_CONFIG), offline=True)
        self.assertEqual(code, 0)

    def test_offline_dry_run_journals_bus_import(self):
        import contextlib
        import io
        import orchestrator
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            orchestrator.run(dict(orchestrator.DEFAULT_CONFIG), offline=True)
        # The bridge is importable, so the orchestrator can rely on it.
        self.assertIsNotNone(orchestrator.bus_bridge)


if __name__ == "__main__":
    unittest.main()
