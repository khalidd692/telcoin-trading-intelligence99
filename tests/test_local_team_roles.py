"""Integration checks for the deterministic roles in the sealed code team."""

import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.agents.automation import local_team
from scripts.agents.automation.autonomy_runtime import Runtime, seal
from tests.test_local_codegen import local_codegen, mission
from tests.test_multiagent_pilot import advice

BASE = "def increment(value):\n    return value\n\nSENTINEL = 7\n"
FIXED = "def increment(value):\n    return value + 1\n"
DOCKER_IMAGE = os.environ.get("TEL99_ROLE_TEST_DOCKER_IMAGE")


def team_mission():
    return mission(team=local_team.TEAM.copy(), model="qwen2.5-coder:7b", port=11434)


def worker_receipt(approved, artifact=FIXED):
    return {
        "artifact": artifact,
        "sha256": hashlib.sha256(artifact.encode()).hexdigest(),
        "specialist_id": "tel99-dev",
        "provider": local_codegen.PROVIDER,
        "model": approved["model"],
        "agent_trace": local_team.trace(advice(), developer_model=approved["model"], artifact=artifact),
    }


class DeterministicTeamRolesTests(unittest.TestCase):
    def test_worker_emits_the_execution_plan_for_the_sealed_team_only(self):
        with (patch.object(local_codegen, "_source", return_value=BASE),
              patch.object(local_codegen.sandbox, "require_local_image"),
              patch.object(local_team, "OllamaNativeProvider") as analyst,
              patch.object(local_codegen, "OllamaNativeProvider") as developer):
            analyst.return_value.complete.return_value = advice()["analysis"]
            developer.return_value.complete.return_value = FIXED
            approved = team_mission()
            result = local_codegen.execute(approved)
            single = local_codegen.execute({k: v for k, v in approved.items() if k != "team"})
        plan = result.get("coordination_role", {})
        self.assertEqual((plan.get("role"), plan.get("engine"), plan.get("ok")),
                         ("tel99-coordination", "deterministic", True))
        self.assertEqual([step["role"] for step in plan["steps"]],
                         ["tel99-analyst", "tel99-dev", "tel99-verifier"])
        self.assertEqual([step["engine"] for step in plan["steps"]],
                         ["ollama", "ollama", "docker"])
        self.assertEqual(plan["steps"][1]["model"], "qwen2.5-coder:7b")
        self.assertNotIn(approved["objective"], str(plan))
        self.assertNotIn("coordination_role", single)
        self.assertIn(advice()["analysis"], developer.return_value.complete.call_args_list[0].kwargs["prompt"])

    def test_verifier_rejects_a_worker_plan_from_a_different_approved_objective(self):
        approved = team_mission()
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(local_codegen, "_source", return_value=BASE),
              patch.object(local_codegen.sandbox, "require_local_image") as docker,
              patch.object(local_team, "OllamaNativeProvider") as analyst,
              patch.object(local_codegen, "OllamaNativeProvider") as developer,
              patch.object(local_codegen, "_behavior", side_effect=[(False, 1), (True, None)])):
            analyst.return_value.complete.return_value = advice()["analysis"]
            developer.return_value.complete.return_value = FIXED
            result = local_codegen.execute(approved)
            docker.reset_mock()
            changed = {**approved, "objective": "Increment a different kind of input."}
            report = local_codegen.verify(changed, result, Path(directory))
        self.assertFalse(report["ok"])
        self.assertEqual(report["coordination_role"]["code"], "plan-mismatch")
        docker.assert_not_called()

    def test_security_role_blocks_candidate_with_new_third_party_import_before_docker(self):
        approved = team_mission()
        structural_fix = "def increment(value):\n    from example_external_package import helper\n    return value + 1\n"
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(local_codegen, "_source", return_value=BASE),
              patch.object(local_codegen.sandbox, "require_local_image") as docker,
              patch.object(local_codegen, "_behavior", side_effect=[(False, 1), (True, None)])):
            proof = local_codegen.verify(
                approved, worker_receipt(approved, structural_fix), Path(directory)
            )
            self.assertFalse((Path(directory) / "verified-code").exists())
        self.assertFalse(proof["ok"])
        self.assertEqual(proof["security_role"]["role"], "tel99-security")
        self.assertEqual(proof["security_role"]["engine"], "deterministic")
        self.assertEqual(proof["security_role"]["code"], "new-non-stdlib-import")
        self.assertFalse(proof["security_role"]["ok"])
        self.assertNotIn("example_external_package", str(proof))
        self.assertNotIn("verification_role", proof)
        docker.assert_not_called()

    def test_security_role_rejects_unrelated_source_changes_in_verification(self):
        approved = team_mission()
        wrong_diff = BASE.replace("return value", "return value + 1").replace("SENTINEL = 7", "SENTINEL = 8")
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(local_codegen, "_source", return_value=BASE),
              patch.object(local_codegen, "replace_function", return_value=wrong_diff),
              patch.object(local_codegen.sandbox, "require_local_image") as docker,
              patch.object(local_codegen, "_behavior", side_effect=[(False, 1), (True, None)])):
            proof = local_codegen.verify(approved, worker_receipt(approved), Path(directory))
        self.assertFalse(proof["ok"])
        self.assertEqual(proof["security_role"]["code"], "outside-approved-function")
        docker.assert_not_called()

    def test_version_one_worker_receipt_still_uses_docker_and_security_without_claiming_a_plan(self):
        approved = team_mission()
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(local_codegen, "_source", return_value=BASE),
              patch.object(local_codegen.sandbox, "require_local_image"),
              patch.object(local_codegen, "_behavior", side_effect=[(False, 1), (True, None)])):
            proof = local_codegen.verify(approved, worker_receipt(approved), Path(directory))
            materialized = Path(directory, "verified-code", approved["id"], approved["path"])
            self.assertIn("return value + 1", materialized.read_text(encoding="utf-8"))
        self.assertTrue(proof["ok"])
        self.assertNotIn("coordination_role", proof)
        self.assertTrue(proof["security_role"]["ok"])
        self.assertEqual(proof["verification_role"]["role"], "tel99-verifier")

    def test_sealed_worker_and_verifier_agree_on_the_plan_and_scope(self):
        approved = team_mission()
        artifact = "def increment(value):\n    import math\n    return math.floor(value) + 1\n"
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(local_codegen, "_source", return_value=BASE),
              patch.object(local_codegen.sandbox, "require_local_image"),
              patch.object(local_team, "OllamaNativeProvider") as analyst,
              patch.object(local_codegen, "OllamaNativeProvider") as developer,
              patch.object(local_codegen, "_behavior", side_effect=[(False, 1), (True, None)])):
            analyst.return_value.complete.return_value = advice()["analysis"]
            developer.return_value.complete.return_value = artifact
            result = local_codegen.execute(approved)
            proof = local_codegen.verify(approved, result, Path(directory))
        self.assertTrue(proof["ok"])
        self.assertEqual(proof["coordination_role"], result["coordination_role"])
        self.assertEqual(proof["security_role"]["code"], "scope-verified")
        self.assertEqual(proof["security_role"]["candidate_sha256"], proof["candidate_sha256"])

    @unittest.skipUnless(DOCKER_IMAGE, "set TEL99_ROLE_TEST_DOCKER_IMAGE to a local pinned Python image")
    def test_runtime_persists_role_receipts_after_real_docker_verification(self):
        approved = {
            **team_mission(),
            "id": "tel99-coordination-security-check",
            "test": "import runpy\nassert runpy.run_path('/work/program.py')['increment'](41) == 42",
            "sandbox_image": DOCKER_IMAGE,
        }
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(local_codegen, "_source", return_value=BASE),
              patch.object(local_team, "OllamaNativeProvider") as analyst,
              patch.object(local_codegen, "OllamaNativeProvider") as developer):
            analyst.return_value.complete.return_value = advice()["analysis"]
            developer.return_value.complete.return_value = FIXED
            runtime = Runtime(Path(directory), executor=local_codegen.execute)
            runtime.run_queue([approved], seal([approved]))
            state = Runtime(Path(directory)).state(approved)
        self.assertEqual(state["status"], "ACCEPTED", state.get("reason"))
        proof = state["verification"]
        self.assertEqual(proof["coordination_role"], state["result"]["coordination_role"])
        self.assertTrue(proof["security_role"]["ok"])
        self.assertEqual(proof["verification_role"]["role"], "tel99-verifier")
        self.assertEqual([(check["ok"], check.get("exit_code")) for check in proof["checks"]],
                         [(True, None), (True, None), (True, 1), (True, 0)])


if __name__ == "__main__":
    unittest.main()
