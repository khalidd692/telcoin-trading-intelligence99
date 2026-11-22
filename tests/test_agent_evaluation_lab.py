from pathlib import Path
import tempfile
import unittest

from scripts.agents import evaluation_lab


class EvaluationLabTests(unittest.TestCase):
    def test_fixture_compares_real_checks_and_repairs(self):
        report = evaluation_lab.run()
        self.assertEqual(report["provider_mode"], "scripted")
        self.assertEqual(report["external_model_calls"], 0)
        self.assertEqual(len(report["cases"]), 10)
        self.assertEqual(report["comparison"]["baseline_rate"], 0.5)
        self.assertEqual(report["comparison"]["candidate_rate"], 1.0)
        self.assertEqual(report["comparison"]["verdict"], "keep")
        self.assertEqual(report["comparison"]["paired_metrics"]["candidate"]["provider_calls"], 15)
        negative = next(case for case in report["cases"] if case["id"] == "false-verdict")
        self.assertEqual(negative["candidate"]["verdict"], "FAIL")
        self.assertTrue(negative["candidate"]["matched_expectation"])

    def test_never_overwrites_existing_report(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "report.json"
            file.write_text("existing", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                evaluation_lab.write_report(file, {"provider_mode": "scripted"})
            self.assertEqual(file.read_text(encoding="utf-8"), "existing")
