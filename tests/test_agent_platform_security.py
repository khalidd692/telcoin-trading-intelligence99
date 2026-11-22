import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

from scripts.agents import cockpit, platform_evidence, project_kit
from scripts.agents.native import mission, provider
from tests.test_agent_project_kit import manifest


class PlatformSecurityTests(unittest.TestCase):
    def test_cockpit_never_joins_foreign_projects_by_equal_mission_id(self):
        foreign = {"id": "shared", "project": "boreal-lab", "status": "ACCEPTED"}
        report = cockpit.snapshot(
            project="atlas-lab", repository="example/atlas",
            status={"missions": {"shared": foreign}, "github_receipts": {
                "kilo-github/outbox/shared/ACK": "https://github.com/example/atlas/issues/1#issuecomment-5"
            }},
            plan={"project": "boreal-lab", "status": "PLANNED",
                  "steps": [{"role": "quant"}], "estimates": {"model_calls": 10}},
            handoffs={"events": [{"task_id": "shared", "status": "ACCEPTED"}]},
        )
        self.assertEqual(report["missions"], [])
        self.assertEqual(report["events"], [])
        self.assertIsNone(report["budget"]["calls"])
        self.assertTrue(all(row["activity"] is None for row in report["roles"]))

    def test_read_only_proof_requires_exact_journal_and_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = project_kit.install(Path(directory) / "atlas", manifest())
            engine = mission.MissionEngine(
                provider=provider.ScriptedProvider(["```result.txt\nOK\n```"]),
                store_root=kit.state, workspace_root=kit.artifacts, memory_root=kit.memory,
                quota_remaining=20,
            )
            spec = mission.MissionSpec("proof-example", "fixture", project="atlas-lab",
                                       artifacts=["result.txt"], checks=[mission.Check(
                                           "value", [sys.executable, "-I", "-c",
                                                     "assert open('result.txt').read().strip() == 'OK'"])])
            self.assertEqual(engine.run(spec).verdict, mission.PASS)
            path = engine.artifact_directory(spec)
            journal = path / "journal.json"
            before = journal.read_bytes()
            sha = hashlib.sha256(before).hexdigest()
            self.assertEqual(platform_evidence.verify(kit, spec.mission_id, sha)["status"],
                             "VERIFIED_ARTIFACTS")
            with self.assertRaisesRegex(ValueError, "journal"):
                platform_evidence.verify(kit, spec.mission_id, "1" * 64)
            artifact = path / "result.txt"
            artifact.write_text("VERDICT: PASS")
            with self.assertRaisesRegex(ValueError, "artifact"):
                platform_evidence.verify(kit, spec.mission_id, sha)
            self.assertEqual(journal.read_bytes(), before)

    def test_duplicate_fields_never_become_browser_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text('{"state":"BLOCKED","state":"ACCEPTED"}')
            self.assertIsNone(cockpit.read_snapshot(path))
