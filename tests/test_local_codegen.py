import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.agents.automation.autonomy_runtime import Runtime, local_codegen, seal, validate_contract


def mission(**changes):
    return {
        "id": "local-code-a",
        "owner": "local",
        "project": "tel99",
        "specialist": "tel99-dev",
        "priority": "P0",
        "dependencies": [],
        "objective": "Increment the value by one.",
        "base_sha": "1" * 40,
        "path": "demo/counter.py",
        "function": "increment",
        "test": "assert True",
        "sandbox_image": "python@sha256:" + "2" * 64,
        "model": "local-test-model",
        "port": 18089,
        **changes,
    }


class LocalCodeTests(unittest.TestCase):
    def test_contract_checks_owner_scope_and_pin(self):
        approved = mission()
        self.assertTrue(validate_contract(approved, seal([approved])))
        for change in (
            {"path": "../counter.py"},
            {"function": "module.increment"},
            {"sandbox_image": "python:latest"},
            {"port": "443"},
            {"model": "kilo-auto/free"},
            {"specialist": "tel99-analyst"},
        ):
            invalid = mission(**change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_contract(invalid, seal([invalid]))
        with self.assertRaises(ValueError):
            validate_contract(mission(test="assert False"), seal([approved]))

    def test_model_output_is_confined_to_the_approved_function(self):
        base = "import os\n\ndef increment(value):\n    return value\n\nSENTINEL = 7\n"
        self.assertEqual(
            local_codegen.replace_function(base, "increment",
                                           "```python\ndef increment(value):\n    return value + 1\n```\nThe updated function."),
            base.replace("return value", "return value + 1"),
        )
        for reply in (
            "import os\ndef increment(value):\n    return value + 1",
            "def increment(value, other):\n    return value + other",
            "def decrement(value):\n    return value - 1",
            "```python\ndef increment(value):\n    return value + 1\n```\n```python\npass\n```",
        ):
            with self.subTest(reply=reply), self.assertRaises(ValueError):
                local_codegen.replace_function(base, "increment", reply)

    def test_verification_requires_a_failing_base_and_passing_candidate(self):
        approved = mission()
        reply = "def increment(value):\n    return value + 1"
        result = {
            "artifact": reply,
            "sha256": hashlib.sha256(reply.encode()).hexdigest(),
            "specialist_id": approved["specialist"],
            "provider": "loopback-code",
            "model": approved["model"],
        }
        base = b"def increment(value):\n    return value\n"
        with tempfile.TemporaryDirectory() as directory, (
            patch.object(local_codegen, "git_committed_blob", return_value=base)
        ), patch.object(local_codegen.sandbox, "require_local_image"), (
            patch.object(local_codegen, "_behavior", side_effect=[True, True, False, True])
        ):
            runtime = Runtime(Path(directory), executor=lambda _: result)
            runtime.run_queue([approved], seal([approved]))
            self.assertEqual(runtime.state(approved)["status"], "REJECTED")
            self.assertFalse((runtime.root / "verified-code").exists())

            second = mission(id="local-code-b")
            runtime.run_queue([second], seal([second]))
            self.assertEqual(runtime.state(second)["status"], "ACCEPTED")
            artifact = runtime.root / "verified-code" / second["id"] / approved["path"]
            self.assertIn("return value + 1", artifact.read_text(encoding="utf-8"))
            self.assertEqual(runtime.state(second)["verification"]["base_sha"], approved["base_sha"])

    def test_replacement_counts_physical_python_lines(self):
        base = 'LABEL = "a\u2028b"\n\ndef increment(value):\n    return value\n'
        reply = "def increment(value):\n    return value + 1"
        self.assertEqual(local_codegen.replace_function(base, "increment", reply),
                         base.replace("return value", "return value + 1"))
