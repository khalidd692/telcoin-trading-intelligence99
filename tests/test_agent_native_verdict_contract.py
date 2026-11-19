"""Contract tests for the deterministic native mission verdict."""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "agents"))

from native.mission import decide_verdict  # noqa: E402


class NativeVerdictContractTests(unittest.TestCase):
    def test_all_successful_checks_return_pass(self):
        self.assertEqual(decide_verdict([{"ok": True}] * 3), "PASS")

    def test_failed_check_returns_fail_in_every_position(self):
        for outcomes in ((False, True, True), (True, False, True), (True, True, False)):
            with self.subTest(outcomes=outcomes):
                checks = [{"ok": outcome} for outcome in outcomes]
                self.assertEqual(decide_verdict(checks), "FAIL")

    def test_incomplete_check_returns_fail_alongside_success(self):
        checks = [{"ok": True}, {"name": "incomplete"}]
        self.assertEqual(decide_verdict(checks), "FAIL")

    def test_empty_list_returns_fail(self):
        self.assertEqual(decide_verdict([]), "FAIL")

    def test_non_dict_check_returns_fail(self):
        self.assertEqual(decide_verdict([{"ok": True}, "not-a-dict"]), "FAIL")

    def test_ok_false_returns_fail(self):
        self.assertEqual(decide_verdict([{"ok": False}]), "FAIL")
