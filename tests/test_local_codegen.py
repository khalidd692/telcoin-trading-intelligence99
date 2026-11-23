import hashlib
import io
import json
import subprocess
import sys
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
            {"max_attempts": True},
            {"max_attempts": 3},
        ):
            invalid = mission(**change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_contract(invalid, seal([invalid]))
        with self.assertRaises(ValueError):
            validate_contract(mission(test="assert False"), seal([approved]))
        retry = mission(max_attempts=2)
        self.assertTrue(validate_contract(retry, seal([retry])))
        with self.assertRaises(ValueError):
            validate_contract(retry, seal([approved]))

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
            patch.object(local_codegen, "_behavior", side_effect=[(True, None), (False, 1), (True, None)])
        ):
            runtime = Runtime(Path(directory), executor=lambda _: result)
            runtime.run_queue([approved], seal([approved]))
            self.assertEqual(runtime.state(approved)["status"], "REJECTED")
            self.assertNotIn("feedback", runtime.state(approved)["verification"])
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

    def test_worker_passes_only_structured_feedback_to_the_model(self):
        approved = mission(test="\n" * 6 + "assert False, 'private diagnostic'  # case: bad-input", max_attempts=2)
        base = "def increment(value):\n    return value\n"
        reply = "def increment(value):\n    return value + 1"
        request = {"mission": approved, "feedback": {"kind": "candidate-test", "line": 7}}
        stdin = io.TextIOWrapper(io.BytesIO(json.dumps(request).encode()), encoding="utf-8")
        with patch.object(local_codegen.sandbox, "require_local_image"), (
            patch.object(local_codegen, "_source", return_value=base)
        ), patch.object(local_codegen, "OpenAICompatibleProvider") as provider, (
            patch("sys.stdin", stdin)
        ), patch("sys.stdout", new_callable=io.StringIO) as output:
            complete = provider.return_value.complete
            complete.return_value = reply
            self.assertEqual(local_codegen.main(), 0)
            receipt = json.loads(output.getvalue())
            self.assertEqual(receipt["artifact"], reply)
            prompt = complete.call_args.kwargs["prompt"]
            self.assertIn("line 7", prompt)
            self.assertIn("bad-input", prompt)
            self.assertNotIn("private diagnostic", prompt)
            with self.assertRaises(ValueError):
                local_codegen.execute(approved, feedback={"kind": "candidate-test", "line": "runtime text"})
            self.assertEqual(complete.call_count, 1)

    def test_empty_model_completion_is_explained_and_retryable(self):
        approved = mission(max_attempts=2)
        base = "def increment(value):\n    return value\n"
        stdin = io.TextIOWrapper(io.BytesIO(json.dumps(approved).encode()), encoding="utf-8")
        with patch.object(local_codegen.sandbox, "require_local_image"), (
            patch.object(local_codegen, "_source", return_value=base)
        ), patch.object(local_codegen, "OpenAICompatibleProvider") as provider, (
            patch("sys.stdin", stdin)
        ), patch("sys.stdout", new_callable=io.StringIO) as output:
            provider.return_value.complete.return_value = "  \n"
            exit_code = local_codegen.main()
            report = json.loads(output.getvalue())
        self.assertEqual(exit_code, 4)
        self.assertEqual(report.get("feedback"), {"kind": "empty-completion"})

    def test_retry_diagnostic_captures_only_assertion_line(self):
        approved = mission(test="pass\nassert False, 'test-only detail'", max_attempts=2)
        reply = "def increment(value):\n    return value + 1"
        receipt = {"artifact": reply, "sha256": hashlib.sha256(reply.encode()).hexdigest(),
                   "specialist_id": approved["specialist"], "provider": "loopback-code",
                   "model": approved["model"]}
        base = "def increment(value):\n    return value\n"

        def run_trusted_test(_image, _path, _timeout, *, runner):
            return subprocess.run([sys.executable, "-I", "-B", "-c", runner],
                                  capture_output=True, timeout=5, check=False)

        with tempfile.TemporaryDirectory() as directory, (
            patch.object(local_codegen, "_source", return_value=base)
        ), patch.object(local_codegen.sandbox, "require_local_image"), (
            patch.object(local_codegen.sandbox, "_run_container", side_effect=run_trusted_test)
        ):
            report = local_codegen.verify(approved, receipt, Path(directory))
        self.assertFalse(report["ok"])
        self.assertEqual(report.get("feedback"), {"kind": "candidate-test", "line": 2})
        self.assertNotIn("test-only detail", json.dumps(report))

    def test_invalid_candidate_has_feedback_before_docker_verification(self):
        approved = mission(max_attempts=2)
        reply = "def increment(value):\n    return ("
        receipt = {"artifact": reply, "sha256": hashlib.sha256(reply.encode()).hexdigest(),
                   "specialist_id": approved["specialist"], "provider": "loopback-code",
                   "model": approved["model"]}
        base = "def increment(value):\n    return value\n"
        with tempfile.TemporaryDirectory() as directory, (
            patch.object(local_codegen, "_source", return_value=base)
        ), patch.object(local_codegen.sandbox, "require_local_image") as docker:
            report = local_codegen.verify(approved, receipt, Path(directory))
        self.assertFalse(report["ok"])
        self.assertEqual(report.get("feedback"), {"kind": "candidate-diff"})
        docker.assert_not_called()
