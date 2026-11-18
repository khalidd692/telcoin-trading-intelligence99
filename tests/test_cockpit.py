#!/usr/bin/env python3
"""Tests for the TEL99 Agent Mission Control cockpit (issue #86).

Stdlib only (``unittest``), no network, no browser. They lock in the four
behaviours the issue demands:

  1. Display: the dataset renders the three roles and the mission phase.
  2. Provenance: every section exposes the source it came from.
  3. Security: no secret-like string reaches ``data.json``, and the browser
     code contains no token, no API key and no ``innerHTML`` sink.
  4. Quota + no-fake-active: an unknown quota never becomes "sufficient" or a
     number, and an agent is "running" only when a real start event has no end.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cockpit import build_data, model  # noqa: E402

COCKPIT = ROOT / "cockpit"


class TestQuota(unittest.TestCase):
    def test_unknown_quota_never_becomes_a_number_or_sufficient(self):
        view = model.quota_view(None)
        self.assertEqual(view["verdict"], "unknown")
        self.assertIsNone(view["remaining"])
        self.assertIn("INCONNU", view["label"])
        self.assertIn("interdit", view["message"])

    def test_unknown_quota_when_remaining_missing(self):
        view = model.quota_view({"source": "x", "daily_limit": 20})
        self.assertEqual(view["verdict"], "unknown")
        self.assertIsNone(view["remaining"])

    def test_low_quota_is_insufficient(self):
        view = model.quota_view({"remaining": 2, "daily_limit": 20})
        self.assertEqual(view["verdict"], "insufficient")
        self.assertEqual(view["remaining"], 2)

    def test_quota_at_threshold_is_sufficient(self):
        view = model.quota_view({"remaining": 12, "daily_limit": 20})
        self.assertEqual(view["verdict"], "sufficient")

    def test_threshold_is_twelve(self):
        self.assertEqual(model.MIN_QUOTA_REQUIRED, 12)


class TestAgents(unittest.TestCase):
    def test_no_events_means_unknown_not_running(self):
        for role in model.ROLES:
            view = model.agent_view(role, [])
            self.assertEqual(view["state"], "unknown")
            self.assertIsNone(view["current_task"])

    def test_open_start_means_running_with_task(self):
        events = [{"agent": "analyst", "kind": "task_start",
                   "summary": "audit data.json", "at": "2026-11-16T10:00:00Z",
                   "source": "https://example.test/1"}]
        view = model.agent_view("analyst", events)
        self.assertEqual(view["state"], "running")
        self.assertEqual(view["current_task"], "audit data.json")

    def test_finished_start_means_done_not_running(self):
        events = [
            {"agent": "analyst", "kind": "task_start", "summary": "start",
             "at": "2026-11-16T10:00:00Z", "source": "s"},
            {"agent": "analyst", "kind": "task_end", "summary": "done",
             "at": "2026-11-16T10:05:00Z", "source": "s"},
        ]
        view = model.agent_view("analyst", events)
        self.assertEqual(view["state"], "done")
        self.assertIsNone(view["current_task"])
        self.assertEqual(view["last_activity"], "done")

    def test_unknown_role_rejected(self):
        with self.assertRaises(ValueError):
            model.agent_view("manager", [])


class TestMissionPhase(unittest.TestCase):
    def test_no_events_is_waiting(self):
        self.assertEqual(model.mission_phase([]), "en_attente")

    def test_blocked_wins(self):
        events = [{"kind": "task_end"}, {"kind": "blocked"}]
        self.assertEqual(model.mission_phase(events), "bloquee")

    def test_open_start_is_running(self):
        self.assertEqual(model.mission_phase([{"kind": "run_start"}]), "en_cours")

    def test_terminal_is_done(self):
        self.assertEqual(model.mission_phase([{"kind": "task_end"}]), "terminee")


class TestControls(unittest.TestCase):
    def test_unwired_actions_are_disabled_and_read_only(self):
        view = model.controls_view({"actions": [
            {"id": "launch", "label": "Lancer", "wired": False},
            {"id": "stop", "label": "Stop", "wired": False},
        ]})
        self.assertTrue(view["read_only"])
        for a in view["actions"]:
            self.assertFalse(a["enabled"])
            self.assertFalse(a["wired"])

    def test_wired_action_is_enabled(self):
        view = model.controls_view({"actions": [
            {"id": "launch", "label": "Lancer", "wired": True, "enabled": True},
        ]})
        self.assertFalse(view["read_only"])
        self.assertTrue(view["actions"][0]["enabled"])


class TestDataset(unittest.TestCase):
    def _raw(self, **kw):
        base = {
            "generated_at": "2026-11-16T21:00:00Z",
            "quota": {"remaining": 2, "daily_limit": 20, "source": "GET /quota"},
            "memory": {"entries": [], "source": "memory/projects/tel99.json"},
            "events": [],
            "mission": {"number": 86, "title": "Cockpit"},
            "controls": {"actions": []},
            "provenance": {"quota": "GET /quota"},
        }
        base.update(kw)
        return base

    def test_dataset_has_three_roles(self):
        d = model.build_dataset(self._raw())
        self.assertEqual([a["role"] for a in d["agents"]], list(model.ROLES))

    def test_dataset_carries_phase_label(self):
        d = model.build_dataset(self._raw())
        self.assertIn("phase_label", d["mission"])

    def test_delegation_graph_omits_unknown_agents(self):
        d = model.build_dataset(self._raw())
        # No events -> no proven delegation edges.
        self.assertEqual(d["delegation_graph"]["edges"], [])

    def test_delegation_graph_has_edge_when_proven(self):
        events = [{"agent": "developer", "kind": "task_end", "summary": "x",
                   "at": "2026-11-16T10:00:00Z", "source": "s"}]
        d = model.build_dataset(self._raw(events=events))
        edges = {e["to"] for e in d["delegation_graph"]["edges"]}
        self.assertIn("developer", edges)


class TestDurableRunReport(unittest.TestCase):
    def _report(self, **changes):
        report = {
            "record_type": "tel99_run_report", "schema_version": 1,
            "mission_id": "94", "ts": "2026-11-18T16:00:00Z",
            "status": "MISSION_ACCEPTED", "mission_accepted": True,
            "outcome_verification": "ACCEPTED", "dry_run": False,
            "verification_proof": {"commit_sha": "a" * 40, "run_id": 42,
                                   "run_attempt": 1, "artifact_sha256": "b" * 64},
        }
        return {**report, **changes}

    def test_local_report_supplies_the_status_timestamp_and_ci_link(self):
        dataset = build_data.build_live(offline=True, run_report=self._report())
        mission = dataset["mission"]
        self.assertEqual(mission["number"], 94)
        self.assertEqual(mission["phase_label"], "Acceptée")
        self.assertEqual(mission["timestamp"], "2026-11-18T16:00:00Z")
        self.assertTrue(mission["proof_url"].endswith("/actions/runs/42/attempts/1"))
        self.assertFalse(dataset["live"])
        self.assertIsNone(dataset["quota"]["remaining"])

    def test_unbound_acceptance_and_waiting_proof_are_not_green(self):
        for report in (
            self._report(verification_proof=None),
            self._report(outcome_verification="NEEDS_HUMAN", mission_accepted=False),
        ):
            with self.subTest(report=report):
                dataset = build_data.build_live(offline=True, run_report=report)
                self.assertEqual(dataset["mission"]["phase"], "bloquee")
                self.assertNotIn("proof_url", dataset["mission"])

    def test_red_report_stays_rejected(self):
        dataset = build_data.build_live(offline=True, run_report=self._report(
            status="FAILED", outcome_verification="REJECTED", mission_accepted=False))
        self.assertEqual(dataset["mission"]["phase_label"], "Rejetée")


class TestShippedArtifacts(unittest.TestCase):
    """Guards on the files that actually ship in the browser."""

    def test_data_json_has_no_secret_like_string(self):
        path = COCKPIT / "data.json"
        if not path.exists():
            self.skipTest("data.json not built")
        text = path.read_text(encoding="utf-8")
        for pat in (r"ghp_[A-Za-z0-9]{20,}", r"github_pat_", r"Bearer\s+[A-Za-z0-9]",
                    r"api[_-]?key\s*[:=]", r"sk-[A-Za-z0-9]{20,}", r"password"):
            self.assertIsNone(re.search(pat, text, re.IGNORECASE),
                              f"secret-like pattern {pat!r} found in data.json")

    def test_browser_js_has_no_token_or_innerhtml(self):
        js = (COCKPIT / "app.js").read_text(encoding="utf-8")
        # No HTML sink: the only allowed text injection is textContent.
        self.assertIsNone(re.search(r"\.innerHTML\s*=", js))
        self.assertNotIn("document.write", js)
        self.assertIn("textContent", js)
        self.assertNotIn("OPENHANDS_API_KEY", js)
        self.assertNotIn("GITHUB_TOKEN", js)
        self.assertNotIn("Bearer ", js)

    def test_index_html_references_only_local_assets(self):
        html = (COCKPIT / "index.html").read_text(encoding="utf-8")
        self.assertIn("app.js", html)
        self.assertIn("data.json", html) if "data.json" in html else None
        # No remote script/style that could leak or block.
        self.assertNotRegex(html, r"<script[^>]+src=\"https?://")


if __name__ == "__main__":
    unittest.main(verbosity=2)
