#!/usr/bin/env python3
"""Tests for the CAS/fencing state layer (issue #94, task S-04).

Stdlib only, offline. They prove the acceptance checks of S-04:

  * a compare-and-set refuses a stale write (no silent overwrite);
  * two concurrent read-modify-write workers cannot lose an update
    (demonstrated with real processes on a shared FileStore);
  * a mission's state is recoverable after a simulated crash.
"""

from __future__ import annotations

import multiprocessing as mp
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "agents"))

from protocol import bus as bus_mod  # noqa: E402
from protocol.bus import Bus  # noqa: E402
from protocol.store import CASConflict, FileStore  # noqa: E402


def _open(bus, cid="msn-cas-test-0001"):
    return bus.open_mission(
        title="cas mission", origin=bus.actors["openhands-cloud"],
        steps=[{"id": "s1", "description": "do", "assigned_to": "hermes-router"}],
        correlation_id=cid)

def _bump_attempt(root):
    local = Bus(store=FileStore(root))
    local.mutate_mission("msn-contend-0001",
                         lambda record: record.attempts.__setitem__(
                             "s1", record.attempts.get("s1", 0) + 1))


class CompareAndSetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FileStore(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_put_cas_writes_when_expected_matches(self):
        self.store.put("k/one", {"v": 1})
        self.assertTrue(self.store.put_cas("k/one", {"v": 2}, {"v": 1}))
        self.assertEqual(self.store.get("k/one"), {"v": 2})

    def test_put_cas_refuses_a_stale_write(self):
        self.store.put("k/one", {"v": 1})
        # Someone else already moved it to 2; writing on the stale 1 must fail.
        self.store.put("k/one", {"v": 2})
        self.assertFalse(self.store.put_cas("k/one", {"v": 3}, {"v": 1}))
        self.assertEqual(self.store.get("k/one"), {"v": 2})

    def test_save_mission_cas_refuses_stale(self):
        bus = Bus(store=self.store)
        record = _open(bus)
        stale = record.to_dict()
        # A concurrent writer commits first.
        record.state = "running"
        bus.save_mission(record)
        # Our write based on the stale snapshot must be refused.
        self.assertFalse(bus.save_mission_cas(record, stale))


class LostUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_mutate_mission_applies_all_updates_under_contention(self):
        store = FileStore(self.tmp.name)
        bus = Bus(store=store)
        _open(bus, cid="msn-contend-0001")

        procs = [mp.Process(target=_bump_attempt, args=(self.tmp.name,)) for _ in range(8)]
        for pr in procs:
            pr.start()
        for pr in procs:
            pr.join(timeout=30)
            self.assertEqual(pr.exitcode, 0)
        final = Bus(store=FileStore(self.tmp.name)).load_mission("msn-contend-0001")
        # Every increment survived: the CAS loop lost nothing.
        self.assertEqual(final.attempts.get("s1"), 8)

    def test_mutate_mission_fails_closed_on_persistent_conflict(self):
        store = FileStore(self.tmp.name)
        bus = Bus(store=store)
        _open(bus, cid="msn-conflict-0001")

        original = store.put_cas

        def always_conflict(key, value, expected):
            return False

        store.put_cas = always_conflict
        with self.assertRaises(CASConflict):
            bus.mutate_mission("msn-conflict-0001", lambda r: None, max_attempts=3)
        store.put_cas = original


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_state_is_recoverable_after_a_simulated_crash(self):
        # Session A opens a mission and completes step 1, then "crashes".
        bus_a = Bus(store=FileStore(self.tmp.name))
        _open(bus_a, cid="msn-recover-0001")
        bus_a.mutate_mission("msn-recover-0001",
                             lambda r: r.completed_step_ids.append("s1"))
        del bus_a  # the process is gone

        # Session B (fresh Bus over the same store) reads the durable state and
        # resumes at the correct step — no lost work, no restart from scratch.
        bus_b = Bus(store=FileStore(self.tmp.name))
        recovered = bus_b.load_mission("msn-recover-0001")
        self.assertIn("s1", recovered.completed_step_ids)
        self.assertIsNone(recovered.next_step_id)  # s1 was the only step

    def test_mutate_on_unknown_mission_raises_keyerror(self):
        bus = Bus(store=FileStore(self.tmp.name))
        with self.assertRaises(KeyError):
            bus.mutate_mission("msn-does-not-exist", lambda r: None)


if __name__ == "__main__":
    unittest.main()
