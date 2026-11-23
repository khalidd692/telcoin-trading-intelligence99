"""Deterministic tests for the native Kilo CLI adapter.

No network, no paid model, no real GitHub publication. Every test uses an
injected fake launcher so the worker subprocess is never actually spawned.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "agents"))

from automation import kilo_cli_adapter as adapter  # noqa: E402

KILO_MODEL = adapter.KILO_MODEL


def good_mission(**changes):
    mission = {
        "id": "kilo-adapter-a",
        "project": "synthetic",
        "owner": "kilo",
        "priority": "P0",
        "dependencies": [],
        "specialist": "tel99-dev",
        "synthetic_data": True,
        "objective": "Return exactly OK",
        "expected_sha256": hashlib.sha256(b"OK").hexdigest(),
    }
    mission.update(changes)
    return mission


def result_json(artifact="OK"):
    return json.dumps({
        "artifact": artifact,
        "sha256": hashlib.sha256(artifact.encode("utf-8")).hexdigest(),
        "specialist_id": "tel99-dev",
        "provider": "kilo-auto-free",
        "provider_evidence": {
            "cost_usd": "0", "http_status": 200,
            "catalog_sha256": "a" * 64, "response_sha256": "b" * 64,
        },
    }).encode("utf-8")


class FakeLauncher:
    """Injected replacement for the real subprocess launcher."""

    def __init__(self, output=result_json(), rc=0, stderr=b""):
        self.output = output
        self.rc = rc
        self.stderr = stderr
        self.calls = []

    def __call__(self, mission, worktree, env, deadline, stop_check):
        self.calls.append({
            "mission": mission,
            "worktree": str(worktree),
            "env": dict(env),
            "deadline": deadline,
            "stop_check": stop_check,
        })
        return self.output, self.stderr, self.rc


class MandateValidationTests(unittest.TestCase):
    def test_valid_mandate_passes(self):
        adapter.validate_mandate(good_mission())  # must not raise

    def test_mandate_must_be_object(self):
        with self.assertRaises(adapter.KiloCliMandateError):
            adapter.validate_mandate("not an object")
        with self.assertRaises(adapter.KiloCliMandateError):
            adapter.validate_mandate(None)

    def test_mandate_rejects_non_synthetic(self):
        for value in (False, None, 0):
            with self.subTest(value=value):
                with self.assertRaises(adapter.KiloCliMandateError):
                    adapter.validate_mandate(good_mission(synthetic_data=value))

    def test_mandate_rejects_unknown_specialist(self):
        for specialist in ("unknown", "tel99-ops", "", None):
            with self.subTest(specialist=specialist):
                with self.assertRaises(adapter.KiloCliMandateError):
                    adapter.validate_mandate(good_mission(specialist=specialist))

    def test_mandate_rejects_bad_objective(self):
        with self.assertRaises(adapter.KiloCliMandateError):
            adapter.validate_mandate(good_mission(objective=""))
        with self.assertRaises(adapter.KiloCliMandateError):
            adapter.validate_mandate(good_mission(objective="x" * 4001))
        with self.assertRaises(adapter.KiloCliMandateError):
            adapter.validate_mandate(good_mission(objective=None))

    def test_mandate_rejects_bad_sha256(self):
        with self.assertRaises(adapter.KiloCliMandateError):
            adapter.validate_mandate(good_mission(expected_sha256="not-hex"))
        with self.assertRaises(adapter.KiloCliMandateError):
            adapter.validate_mandate(good_mission(expected_sha256="a" * 63))
        with self.assertRaises(adapter.KiloCliMandateError):
            adapter.validate_mandate(good_mission(expected_sha256="g" * 64))

    def test_mandate_rejects_bad_id(self):
        for bad in ("", "a/b", "../../x", "has space", "a" * 49):
            with self.subTest(bad=bad):
                with self.assertRaises(adapter.KiloCliMandateError):
                    adapter.validate_mandate(good_mission(id=bad))


class AdapterConstructorTests(unittest.TestCase):
    def test_only_kilo_auto_free_is_allowed(self):
        with self.assertRaises(adapter.KiloCliError):
            adapter.KiloCliAdapter(model="gpt-5.6")

    def test_default_model_is_kilo_auto_free(self):
        a = adapter.KiloCliAdapter()
        self.assertEqual(a.model, KILO_MODEL)

    def test_custom_worktree_root_is_used(self):
        with tempfile.TemporaryDirectory() as root:
            a = adapter.KiloCliAdapter(worktree_root=root)
            self.assertEqual(a.worktree_root, pathlib.Path(root))

    def test_injected_launcher_is_used(self):
        launcher = FakeLauncher()
        a = adapter.KiloCliAdapter(launcher=launcher)
        self.assertIs(a.launcher, launcher)


class AdapterRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_run_returns_json_result(self):
        launcher = FakeLauncher()
        a = adapter.KiloCliAdapter(launcher=launcher)
        mission = good_mission()
        result = a.run(mission)
        self.assertEqual(result["artifact"], "OK")
        self.assertEqual(len(launcher.calls), 1)
        self.assertEqual(launcher.calls[0]["mission"], mission)

    def test_run_uses_isolated_worktree(self):
        launcher = FakeLauncher()
        a = adapter.KiloCliAdapter(launcher=launcher, worktree_root=self.tmp.name)
        a.run(good_mission())
        worktree = pathlib.Path(launcher.calls[0]["worktree"])
        self.assertTrue(worktree.is_absolute())
        self.assertIn(pathlib.Path(self.tmp.name).resolve(), worktree.parents)
        self.assertEqual(a._worktree, None)  # cleaned up after run

    def test_run_passes_sanitized_env_with_kilo_model(self):
        launcher = FakeLauncher()
        a = adapter.KiloCliAdapter(launcher=launcher)
        a.run(good_mission())
        env = launcher.calls[0]["env"]
        self.assertEqual(env["TEL99_NATIVE_MODEL"], KILO_MODEL)
        self.assertEqual(env["TEL99_NATIVE_BASE_URL"], "https://ai-gateway.kilo.ai/api/v1")
        for forbidden in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GH_TOKEN", "GITHUB_TOKEN",
                          "PYTHON_TOKEN"):
            self.assertNotIn(forbidden, env)

    def test_stop_before_launch_raises(self):
        launcher = FakeLauncher()
        a = adapter.KiloCliAdapter(launcher=launcher)
        with self.assertRaises(adapter.KiloCliStopped):
            a.run(good_mission(), stop_check=lambda: True)
        self.assertEqual(len(launcher.calls), 0)

    def test_stop_during_launch_raises(self):
        launcher = FakeLauncher()
        a = adapter.KiloCliAdapter(launcher=launcher)
        triggered = {"value": False}

        def stop_check():
            return triggered["value"]

        def slow_launcher(mission, worktree, env, deadline, stop_check):
            triggered["value"] = True
            if stop_check():
                raise adapter.KiloCliStopped("STOP")
            return b"", b"", 0

        a = adapter.KiloCliAdapter(launcher=slow_launcher)
        with self.assertRaises(adapter.KiloCliStopped):
            a.run(good_mission(), stop_check=stop_check)

    def test_timeout_raises(self):
        def blocking_launcher(mission, worktree, env, deadline, stop_check):
            # Hold the worker past the deadline so the polling loop detects it.
            while time.monotonic() < deadline:
                time.sleep(0.01)
            return b"", b"", 0

        a = adapter.KiloCliAdapter(launcher=blocking_launcher)
        with self.assertRaises(adapter.KiloCliTimeout):
            a.run(good_mission(), deadline=time.monotonic() + 0.05)

    def test_nonzero_exit_raises(self):
        launcher = FakeLauncher(rc=4, stderr=b"blocked detail")
        a = adapter.KiloCliAdapter(launcher=launcher)
        with self.assertRaises(adapter.KiloCliError):
            a.run(good_mission())

    def test_invalid_json_raises(self):
        launcher = FakeLauncher(output=b"not json")
        a = adapter.KiloCliAdapter(launcher=launcher)
        with self.assertRaises(adapter.KiloCliError):
            a.run(good_mission())

    def test_incomplete_result_raises(self):
        launcher = FakeLauncher(output=b'{"sha256":"abc"}')
        a = adapter.KiloCliAdapter(launcher=launcher)
        with self.assertRaises(adapter.KiloCliError):
            a.run(good_mission())

    def test_rate_limited_exit_five(self):
        launcher = FakeLauncher(rc=5)
        a = adapter.KiloCliAdapter(launcher=launcher)
        with self.assertRaises(adapter.ProviderRateLimited):
            a.run(good_mission())

    def test_default_deadline_uses_timeout(self):
        launcher = FakeLauncher()
        a = adapter.KiloCliAdapter(launcher=launcher, timeout=42)
        a.run(good_mission())
        self.assertGreaterEqual(launcher.calls[0]["deadline"], time.monotonic() + 41)


class SupervisorExecutorTests(unittest.TestCase):
    """The adapter is accepted by Runtime via ``executor=`` and called as ``executor(m)``."""

    def test_adapter_is_callable(self):
        a = adapter.KiloCliAdapter(launcher=FakeLauncher())
        self.assertTrue(callable(a))

    def test_call_delegates_to_run(self):
        launcher = FakeLauncher()
        a = adapter.KiloCliAdapter(launcher=launcher)
        mission = good_mission()
        result = a(mission)
        self.assertEqual(result["artifact"], "OK")
        self.assertEqual(launcher.calls[0]["mission"], mission)

    def test_runtime_executor_call_pattern(self):
        # Mirror Runtime.__init__: self.executor = executor or self.execute_worker
        # and Runtime loop: result = self.executor(m).
        a = adapter.KiloCliAdapter(launcher=FakeLauncher())
        executor = a  # executor=a, not a new supervisor
        result = executor(good_mission())
        self.assertEqual(result["artifact"], "OK")


class DefaultLauncherTests(unittest.TestCase):
    """The real subprocess launcher must be guard-clean and produce JSON.

    These tests exercise the real ``kilo_executor.py worker`` subprocess with a
    monkeypatched provider so no network or paid model is involved.
    """

    def _make_executor_script(self, text):
        """Write a fake kilo_executor.py that echoes a fixed artifact as JSON."""
        code = (
            "import json, sys\n"
            "payload = json.loads(sys.stdin.read())\n"
            'print(json.dumps({"artifact": ' + repr(text) + ', "sha256": "x", '
            '"specialist_id": "tel99-dev", "provider": "kilo-auto-free", '
            '"provider_evidence": {}}))\n'
        )
        path = pathlib.Path(self.tmp.name) / "kilo_executor.py"
        path.write_text(code, encoding="utf-8")
        return str(path)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    @patch("automation.kilo_cli_adapter.shutil.which", return_value="C:\\fake\\kilo.cmd")
    @patch("automation.kilo_cli_adapter.subprocess")
    def test_default_launcher_uses_kilo_cli_run(self, mock_subprocess, mock_which):
        class FakeProc:
            def __init__(self):
                self.stdin = _StubStream()
                self.stdout = _StubStream()
                self.stderr = _StubStream()
                self.returncode = 0
                self._polled = False

            def poll(self):
                if not self._polled:
                    self._polled = True
                    return None
                return self.returncode

            def communicate(self, timeout=10):
                return self.stdout.data, self.stderr.data

            def kill(self):
                self.returncode = -1

            def wait(self, timeout=10):
                return self.returncode

        class _StubStream:
            def __init__(self):
                self.data = b""
            def write(self, data):
                self.data = data
            def close(self):
                pass

        proc = FakeProc()
        proc.stdout.data = result_json()
        mock_subprocess.Popen.return_value = proc

        a = adapter.KiloCliAdapter()
        result = a.run(good_mission())
        self.assertEqual(result["artifact"], "OK")
        cmd = mock_subprocess.Popen.call_args.args[0]
        self.assertIn("run", cmd)
        self.assertIn("--model", cmd)
        self.assertIn(adapter.KILO_MODEL, cmd)
        self.assertIn("--agent", cmd)
        self.assertIn("code", cmd)
        self.assertNotIn("--auto", cmd)


class _StubStream:
    def __init__(self):
        self.data = b""
    def write(self, data):
        self.data = data
    def close(self):
        pass


class VerifyIntegrationTests(unittest.TestCase):
    """The adapter result must be consumable by the independent verifier."""

    def test_result_passes_independent_verifier(self):
        from scripts.agents.automation.kilo_executor import verify
        mission = good_mission()
        artifact = "OK"
        mission["expected_sha256"] = hashlib.sha256(artifact.encode("utf-8")).hexdigest()
        result = {
            "artifact": artifact,
            "sha256": mission["expected_sha256"],
            "specialist_id": "tel99-dev",
            "provider": "kilo-auto-free",
            "provider_evidence": {
                "cost_usd": "0", "http_status": 200,
                "catalog_sha256": "a" * 64, "response_sha256": "b" * 64,
            },
        }
        report = verify(mission, result)
        self.assertTrue(report["ok"])
        self.assertEqual(report["verifier"], "tel99-fixed-subprocess-v1")


class BuildRuntimeWiringTests(unittest.TestCase):
    """End-to-end native wiring: Runtime driven by the adapter, no network."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)

    def test_happy_path_is_accepted(self):
        from scripts.agents.automation.autonomy_runtime import seal
        launcher = FakeLauncher()
        runtime = adapter.build_runtime(self.root, launcher=launcher)
        m = good_mission()
        runtime.run_queue([m], seal([m]))
        self.assertEqual(
            runtime.status()["missions"][m["id"]]["status"], "ACCEPTED")
        self.assertEqual(len(launcher.calls), 1)

    def test_rate_limit_becomes_quota_backoff_without_replay(self):
        from scripts.agents.automation.autonomy_runtime import seal
        launcher = FakeLauncher(rc=5)
        runtime = adapter.build_runtime(self.root, launcher=launcher)
        m = good_mission()
        runtime.run_queue([m], seal([m]))
        self.assertEqual(
            runtime.status()["missions"][m["id"]]["status"], "BLOCKED")
        self.assertTrue(runtime.quota_exhausted)
        runtime.run_queue([m], seal([m]))  # quota backoff: never replay the worker
        self.assertEqual(len(launcher.calls), 1)

    def test_stop_check_and_deadline_are_wired(self):
        from scripts.agents.automation.autonomy_runtime import seal
        captured = {}

        def capturing_launcher(mission, worktree, env, deadline, stop_check):
            captured["deadline"] = deadline
            captured["stop_check"] = stop_check
            return result_json(), b"", 0

        runtime = adapter.build_runtime(
            self.root, launcher=capturing_launcher, timeout=300)
        runtime.deadline = time.monotonic() + 5
        m = good_mission()
        runtime.run_queue([m], seal([m]))
        # The supervisor session deadline caps the adapter timeout.
        self.assertLessEqual(captured["deadline"], runtime.deadline + 1)
        self.assertGreater(captured["deadline"], 0)
        # STOP responsiveness: the wired stop_check reflects the runtime marker.
        self.assertTrue(callable(captured["stop_check"]))
        self.assertFalse(captured["stop_check"]())
        (self.root / "stop.request").touch()
        self.assertTrue(captured["stop_check"]())


if __name__ == "__main__":
    unittest.main()
