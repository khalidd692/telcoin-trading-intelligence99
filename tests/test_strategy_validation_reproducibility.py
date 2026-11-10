"""Regression: replay reports must not depend on wall-clock execution time."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

from scripts.strategy_backtest import history_quality as Q


class ValidationReproducibilityTests(unittest.TestCase):
    def test_manifest_cutoff_is_stable(self):
        source = "data/KRAKEN_TELUSD_4h_2026-01-22_2026-11-08.csv"
        cutoff = Q.utc_timestamp(Q.manifest()[source]["closed_before"])
        first = Q.load_history(source, as_of=cutoff).report
        second = Q.load_history(source, as_of=cutoff).report
        self.assertEqual(first, second)
        self.assertEqual(first["as_of_utc"], cutoff.isoformat())

    def test_two_replays_produce_identical_json(self):
        output = Q.ROOT / "results/strategy_validation/results.json"
        original = output.read_bytes() if output.exists() else None
        try:
            reports = []
            for _ in range(2):
                subprocess.run(
                    [sys.executable, "-m", "scripts.strategy_backtest.run_validation"],
                    cwd=Q.ROOT, check=True, capture_output=True, text=True,
                )
                reports.append(output.read_bytes())
            self.assertEqual(reports[0], reports[1])
            self.assertEqual(
                json.loads(reports[0])["validated_data"]["as_of_utc"],
                Q.utc_timestamp(Q.manifest()[
                    "data/KRAKEN_TELUSD_4h_2026-01-22_2026-11-08.csv"
                ]["closed_before"]).isoformat(),
            )
        finally:
            if original is None:
                output.unlink(missing_ok=True)
            else:
                output.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
