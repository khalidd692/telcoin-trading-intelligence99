"""Offline regressions from independent runtime review; no provider calls."""
import tempfile
import time
import unittest
from pathlib import Path

from scripts.agents.automation.autonomy_runtime import Runtime, seal
from tests.test_autonomy_runtime import mission, result


class AutonomyReviewRegressions(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.calls = []
        self.runtime = Runtime(self.root, executor=self.execute)

    def execute(self, contract):
        self.calls.append(contract['id'])
        return result()

    def test_changed_prerequisite_cannot_release_dependent_listed_first(self):
        original = mission()
        self.runtime.run_queue([original], seal([original]))
        self.assertEqual(self.runtime.state(original)['status'], 'ACCEPTED')
        self.calls.clear()
        changed = mission(objective='Return changed prerequisite')
        dependent = mission('demo-dependent', dependencies=[original['id']])
        self.runtime.run_queue([dependent, changed], seal([dependent, changed]))
        self.assertNotIn(dependent['id'], self.calls)
        self.assertNotEqual(self.runtime.state(dependent).get('status'), 'ACCEPTED')

    def test_fresh_status_reports_persistent_stop(self):
        (self.root / 'stop.request').touch()
        self.assertEqual(Runtime(self.root).status()['state'], 'STOP_REQUESTED')

    def test_corrupt_checkpoint_is_blocked_not_busy(self):
        contract = mission()
        checkpoint = self.runtime.store._path('kilo-local/' + contract['id'])
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text('{corrupt', encoding='utf-8')
        self.runtime.run_queue([contract], seal([contract]))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.runtime.status()['state'], 'BLOCKED')

    def test_expired_run_budget_does_not_claim_or_execute(self):
        contract = mission()
        self.runtime.deadline = time.monotonic() - 1
        self.runtime.run_queue([contract], seal([contract]))
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.runtime.store.get('kilo-claims/' + contract['id']))

    def test_expired_budget_after_first_task_does_not_start_second(self):
        first = mission()
        second = mission('demo-next')
        self.runtime.deadline = time.monotonic() + 60

        def exhaust_budget(contract):
            self.calls.append(contract['id'])
            self.runtime.deadline = time.monotonic() - 1
            return result()

        self.runtime.executor = exhaust_budget
        self.runtime.run_queue([first, second], seal([first, second]))
        self.assertEqual(self.calls, [first['id']])
        self.assertIsNone(self.runtime.store.get('kilo-claims/' + second['id']))


if __name__ == '__main__':
    unittest.main()
