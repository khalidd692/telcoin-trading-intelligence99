"""Regression tests for stripped-HOME fallback (RUN4 root cause) & smart consecutive-failure circuit breaker."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agents.automation import ide_coordination
from tests import run_hour_autonomy_acceptance as hour_runner


class TestCircuitBreakerAndHomeFallback(unittest.TestCase):
    def test_default_coordination_state_root_survives_stripped_home_env(self) -> None:
        stripped = {
            k: v
            for k, v in os.environ.items()
            if k.upper() not in {"HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "TEL99_COORDINATION_STATE"}
        }
        with mock.patch.dict(os.environ, stripped, clear=True):
            with mock.patch.object(Path, "home", side_effect=RuntimeError("Could not determine home directory.")):
                resolved = ide_coordination.default_coordination_state_root()
                self.assertIsInstance(resolved, Path)
                self.assertTrue(str(resolved))

    def test_consecutive_failure_circuit_breaker_triggers_at_threshold(self) -> None:
        waves_fail = [
            {"wave": "w1", "accepted_count": 0, "total_count": 2},
            {"wave": "w2", "accepted_count": 0, "total_count": 2},
            {"wave": "w3", "accepted_count": 0, "total_count": 2},
        ]
        res = hour_runner.evaluate_consecutive_failure_breaker(waves_fail, max_consecutive_failures=3)
        self.assertTrue(res["triggered"])
        self.assertEqual(res["consecutive_zero_accepted_waves"], 3)

        waves_recover = [
            {"wave": "w1", "accepted_count": 0, "total_count": 2},
            {"wave": "w2", "accepted_count": 2, "total_count": 2},
            {"wave": "w3", "accepted_count": 0, "total_count": 2},
            {"wave": "w4", "accepted_count": 0, "total_count": 2},
        ]
        res2 = hour_runner.evaluate_consecutive_failure_breaker(waves_recover, max_consecutive_failures=3)
        self.assertFalse(res2["triggered"])
        self.assertEqual(res2["consecutive_zero_accepted_waves"], 2)


if __name__ == "__main__":
    unittest.main()
