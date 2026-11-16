#!/usr/bin/env python3
"""Reproducible non-regression test for TEL99 signal coherence.

This test runs on an **isolated fixture** (``tests/fixtures/tel99_signal_coherence.json``)
derived from a real, dated public snapshot, so it never depends on the live site
being reachable and never invents a price. It pins the contract that the issue
#84 mission asked to verify:

  * a *market signal* must never be presented as a *confirmed buy*;
  * the fail-closed rule must trigger on stale, undated, missing or incoherent
    data (verdict ``DONNEES_INSUFFISANTES``), not on a technical signal alone;
  * the project isolation of the shared memory must hold (``tel99`` never reads
    another project's private entries).

Stdlib only (CI has no requirements.txt).
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "agents"))

from terminal import signal_coherence as sc  # noqa: E402
from intelligence import memory  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "tel99_signal_coherence.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class SignalCoherenceTests(unittest.TestCase):
    """The real snapshot is fresh but authorises no buy."""

    def setUp(self):
        self.snapshot = load_fixture()
        # Freeze "now" at the snapshot's captured_at so freshness is exact and
        # the test is deterministic (no dependence on the wall clock).
        self.now = sc._parse_utc(self.snapshot["captured_at"])

    def test_fixture_is_dated_and_hashed(self):
        self.assertIsNotNone(sc._parse_utc(self.snapshot["captured_at"]))
        self.assertEqual(len(self.snapshot["source_sha256"]), 64)

    def test_snapshot_is_fresh_at_capture_time(self):
        fresh = sc.freshness(self.snapshot, now=self.now)
        self.assertTrue(fresh["fresh"])
        self.assertLessEqual(fresh["age_minutes"], 15.0)
        self.assertTrue(all(f["fresh"] for f in fresh["per_frame"].values()))

    def test_market_confirmation_is_not_a_confirmed_buy(self):
        facts = sc.classify(self.snapshot)
        self.assertTrue(facts["market_confirmation"])
        self.assertFalse(facts["risk_checked_buy"])
        self.assertFalse(facts["confirmed_buy"])
        self.assertFalse(facts["real_orders"])
        self.assertFalse(facts["paper_orders"])

    def test_plan_is_inadmissible_and_below_the_rr_floor(self):
        facts = sc.classify(self.snapshot)
        self.assertFalse(facts["plan_admissible"])
        self.assertIsNotNone(facts["min_rr"])
        self.assertLess(facts["rr_gross"], facts["min_rr"])
        self.assertLess(facts["rr_net"], facts["min_rr"])

    def test_no_incoherence_in_the_real_snapshot(self):
        self.assertEqual(sc.incoherences(self.snapshot), [])

    def test_verdict_is_caution_not_a_buy(self):
        result = sc.verdict(self.snapshot, now=self.now)
        self.assertEqual(result["verdict"], sc.VERDICT_CAUTION)
        self.assertFalse(result["confirmed_buy"])
        self.assertFalse(result["fail_closed"])

    # -- fail-closed behaviour on degraded data --------------------------------
    def test_stale_snapshot_is_refused(self):
        stale_now = self.now + _dt.timedelta(minutes=16)
        result = sc.verdict(self.snapshot, now=stale_now)
        self.assertEqual(result["verdict"], sc.VERDICT_INSUFFICIENT)
        self.assertTrue(result["fail_closed"])

    def test_undated_snapshot_is_refused(self):
        broken = dict(self.snapshot)
        broken["captured_at"] = ""
        result = sc.verdict(broken, now=self.now)
        self.assertEqual(result["verdict"], sc.VERDICT_INSUFFICIENT)

    def test_missing_min_rr_is_refused(self):
        broken = json.loads(json.dumps(self.snapshot))
        broken["safety"].pop("min_rr", None)
        gate = sc.fail_closed(broken, now=self.now)
        self.assertTrue(gate["refused"])

    def test_incoherent_snapshot_is_flagged(self):
        # A snapshot that claims execution allowed on a technical confirmation
        # only (no risk check) must be reported as a contradiction.
        broken = json.loads(json.dumps(self.snapshot))
        broken["decision"]["execution_allowed"] = True
        self.assertIn("execution_allowed on a technical confirmation only",
                      sc.incoherences(broken))

    def test_confirmed_buy_requires_every_condition(self):
        good = json.loads(json.dumps(self.snapshot))
        good["radar"]["event"]["risk_checked_buy"] = True
        good["decision"]["execution_allowed"] = True
        good["decision"]["plan"]["admissible"] = True
        good["decision"]["plan"]["rr_gross"] = 2.0
        good["decision"]["plan"]["rr_net"] = 1.8
        facts = sc.classify(good)
        self.assertTrue(facts["confirmed_buy"])
        self.assertEqual(sc.incoherences(good), [])


class MemoryIsolationTests(unittest.TestCase):
    """A second project must not read TEL99's private knowledge."""

    def test_other_project_cannot_read_tel99_entries(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            store = memory.MemoryStore(tmp)
            store.record(memory.Entry(id="tel-secret", project="tel99",
                                      kind="fact", title="tel99 private",
                                      body=""))
            store.record(memory.Entry(id="shared", project=memory.COMMON_PROJECT,
                                      kind="procedure", title="shared rule",
                                      body=""))
            other = {e.id for e in store.all_entries("another-project")}
            self.assertNotIn("tel-secret", other)
            self.assertIn("shared", other)


if __name__ == "__main__":
    unittest.main()
