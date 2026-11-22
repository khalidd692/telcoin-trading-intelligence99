import json
from pathlib import Path
import tempfile
import unittest

from scripts.agents import cockpit, platform_demo, platform_evidence, project_kit


class PlatformDemoTests(unittest.TestCase):
    def test_installed_example_runs_and_projects_its_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "example"
            outcome = platform_demo.run(root)
            kit = project_kit.load(root)
            self.assertEqual(outcome["provider_calls"], 1)
            self.assertEqual(outcome["external_model_calls"], 0)
            self.assertEqual(platform_evidence.verify(
                kit, outcome["mission_id"], outcome["journal_sha256"])["status"],
                "VERIFIED_ARTIFACTS")
            report = cockpit.snapshot(
                status=json.loads((root / "status.json").read_bytes()),
                plan=json.loads((root / "plan.json").read_bytes()),
                repository=kit.profile["repository"], project=kit.profile["project"],
            )
            self.assertEqual(report["mode"], "demo")
            self.assertEqual(report["missions"][0]["state"], "PASS")
            self.assertEqual(len(report["missions"][0]["proof"]), 64)
            self.assertIsNone(report["budget"]["quota"])
            with self.assertRaises(FileExistsError):
                platform_demo.run(root)
