import json
from pathlib import Path
import tempfile
import unittest

from scripts.agents import project_kit
from tests.test_agent_capabilities import contract


def manifest(project="atlas-lab", repository="example/atlas"):
    return {"schema_version": 1, "project": project, "repository": repository,
            "roles": ["quant", "development", "quality"],
            "skills": ["plan-verification"],
            "approved_models": ["openhands/deepseek-v4.1-flash"]}


class ProjectKitTests(unittest.TestCase):
    def test_two_kits_plan_the_same_id_with_separate_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atlas = project_kit.install(root / "atlas", manifest())
            boreal = project_kit.install(root / "boreal", manifest("boreal-lab", "example/boreal"))
            first = project_kit.prepare(atlas, contract())
            second = project_kit.prepare(boreal, contract("boreal-lab"))
            self.assertEqual(first["status"], "PLANNED")
            self.assertEqual(second["status"], "PLANNED")
            self.assertNotEqual(first["contract_sha256"], second["contract_sha256"])
            self.assertNotEqual(atlas.memory, boreal.memory)
            self.assertEqual(list(atlas.state.iterdir()), [])

    def test_refuses_foreign_contract_or_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kit = project_kit.install(root / "atlas", manifest())
            with self.assertRaisesRegex(ValueError, "project"):
                project_kit.prepare(kit, contract("other-lab"))
            payload = contract()
            payload["steps"][0]["role"] = "security"
            with self.assertRaisesRegex(ValueError, "role"):
                project_kit.prepare(kit, payload)
            unsafe = {**manifest(), "api_token": "secret"}
            with self.assertRaises(ValueError):
                project_kit.install(root / "unsafe", unsafe)
            self.assertFalse((root / "unsafe").exists())

    def test_refuses_reinstall_and_symlink_to_other_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kit = project_kit.install(root / "atlas", manifest())
            original = (kit.root / "project.json").read_bytes()
            with self.assertRaises(FileExistsError):
                project_kit.install(kit.root, manifest("boreal-lab"))
            self.assertEqual((kit.root / "project.json").read_bytes(), original)
            kit.memory.rmdir()
            external = root / "external"
            external.mkdir()
            try:
                kit.memory.symlink_to(external, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(ValueError, "memory"):
                project_kit.load(kit.root)
