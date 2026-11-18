#!/usr/bin/env python3
"""Tests for the TEL99 native mission runner (issue #86).

Stdlib only, no network, no LLM, no real key: the runner is deterministic by
design, so the tests assert exact, reproducible behaviour. They cover the
interchangeable-provider contract, the bounded kernel and -- most importantly --
the safety invariants the owner asked for:

  * the model's self-report NEVER decides the verdict (negative fixture);
  * quota is fail-closed (unknown or below reserve => STOP, no provider call);
  * a mission never runs twice (idempotency);
  * unsafe mission ids / artifact names are rejected (no path traversal);
  * a provider never leaks a secret and never uses a paid model;
  * every command the kernel shells out to is guard-clean.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "agents"))

from native import mission, provider  # noqa: E402
from guard import guard  # noqa: E402

MATH_OK = ("```mathutils.py\n"
           "def add(a, b):\n    return a + b\n\n"
           "def double(x):\n    return add(x, x)\n```")
MATH_BAD = ("```mathutils.py\n"
            "def add(a, b):\n    return a + b\n\n"
            "def double(x):\n    return x\n```\nVERDICT: PASS")


def _engine(tmp: str, responses, **kwargs) -> mission.MissionEngine:
    root = pathlib.Path(tmp)
    return mission.MissionEngine(
        provider=provider.ScriptedProvider(responses, name="scripted"),
        store_root=root / "state",
        workspace_root=root / "state" / "artifacts",
        memory_root=root / "memory",
        quota_remaining=kwargs.pop("quota_remaining", 18),
        **kwargs,
    )


class ProviderContractTests(unittest.TestCase):
    def test_scripted_provider_is_deterministic_and_counts_calls(self):
        p = provider.ScriptedProvider(["a", "b"])
        self.assertEqual(p.complete(system="s", prompt="p"), "a")
        self.assertEqual(p.complete(system="s", prompt="p"), "b")
        self.assertEqual(p.calls, 2)
        with self.assertRaises(provider.ProviderError):
            p.complete(system="s", prompt="p")

    def test_paid_model_is_refused(self):
        with self.assertRaises(provider.ProviderConfigError):
            provider.OpenAICompatibleProvider(
                model="gpt-5.6", base_url="https://example.test/v1",
                api_key="x")

    def test_non_local_endpoint_requires_a_key(self):
        with self.assertRaises(provider.ProviderConfigError):
            provider.OpenAICompatibleProvider(
                model="openhands/deepseek-v4.1-flash",
                base_url="https://example.test/v1")

    def test_local_endpoint_allows_no_key(self):
        p = provider.OpenAICompatibleProvider(
            model="openhands/deepseek-v4.1-flash",
            base_url="http://localhost:1234/v1")
        self.assertEqual(p.model, "openhands/deepseek-v4.1-flash")

    def test_bad_scheme_is_refused(self):
        with self.assertRaises(provider.ProviderConfigError):
            provider.OpenAICompatibleProvider(
                model="openhands/deepseek-v4.1-flash",
                base_url="file:///etc/passwd", api_key="x")

    def test_free_allowlist_comes_from_team_config(self):
        self.assertIn("openhands/deepseek-v4.1-flash", provider.free_model_ids())

    def test_get_provider_unknown_name_fails_closed(self):
        with self.assertRaises(provider.ProviderConfigError):
            provider.get_provider("does-not-exist")

    def test_provider_error_never_leaks_the_key(self):
        # A provider that raises must surface only a type name, never details.
        p = provider.OpenAICompatibleProvider(
            model="openhands/deepseek-v4.1-flash",
            base_url="http://127.0.0.1:1/v1", api_key="SECRET-KEY")
        with self.assertRaises(provider.ProviderError) as ctx:
            p.complete(system="s", prompt="p")
        self.assertNotIn("SECRET-KEY", str(ctx.exception))


class VerdictTests(unittest.TestCase):
    def test_no_checks_is_needs_human(self):
        self.assertEqual(mission.decide_verdict([]), mission.NEEDS_HUMAN)

    def test_all_checks_pass_is_pass(self):
        self.assertEqual(
            mission.decide_verdict([{"ok": True}, {"ok": True}]), mission.PASS)

    def test_any_failing_check_is_fail(self):
        self.assertEqual(
            mission.decide_verdict([{"ok": True}, {"ok": False}]), mission.FAIL)


class KernelTests(unittest.TestCase):
    def test_happy_path_writes_artifact_and_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_OK])
            spec = mission.MissionSpec(
                mission_id="m-good", prompt="write mathutils", artifacts=["mathutils.py"],
                checks=[mission.Check("compile",
                                      ["python3", "-m", "py_compile", "mathutils.py"])],
            )
            result = engine.run(spec)
            self.assertEqual(result.verdict, mission.PASS)
            self.assertIn("mathutils.py", result.artifacts)
            self.assertEqual(result.provider_calls, 1)
            art = pathlib.Path(tmp) / "state" / "artifacts" / "m-good" / "mathutils.py"
            self.assertTrue(art.is_file())
            journal = art.parent / "journal.json"
            self.assertTrue(journal.is_file())

    def test_negative_fixture_model_claims_pass_but_check_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_BAD])
            spec = mission.MissionSpec(
                mission_id="m-bad", prompt="write mathutils", artifacts=["mathutils.py"],
                checks=[mission.Check(
                    "behaviour",
                    ["python3", "-c",
                     "import mathutils; assert mathutils.double(21) == 42"])],
            )
            result = engine.run(spec)
            self.assertEqual(result.verdict, mission.FAIL)
            # The model's text claimed PASS; the kernel ignored it.
            self.assertTrue(result.checks[0]["ok"] is False)

    def test_idempotency_no_double_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_OK])
            spec = mission.MissionSpec(
                mission_id="m-once", prompt="write", artifacts=["mathutils.py"],
                checks=[mission.Check("compile",
                                      ["python3", "-m", "py_compile", "mathutils.py"])],
            )
            first = engine.run(spec)
            second = engine.run(spec)
            self.assertFalse(first.reused)
            self.assertTrue(second.reused)
            self.assertEqual(second.provider_calls, 0)

    def test_refused_run_leaks_no_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_OK], quota_remaining=5)
            with self.assertRaises(mission.MissionError):
                engine.run(mission.MissionSpec(mission_id="m-leak", prompt="x"))
            claims = pathlib.Path(tmp) / "state" / "claims"
            self.assertEqual(list(claims.glob("*")) if claims.is_dir() else [], [])

    def test_quota_unknown_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_OK], quota_remaining=None)
            spec = mission.MissionSpec(mission_id="m-q", prompt="x")
            with self.assertRaises(mission.MissionError):
                engine.run(spec)

    def test_quota_below_reserve_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_OK], quota_remaining=11)
            spec = mission.MissionSpec(mission_id="m-q2", prompt="x")
            with self.assertRaises(mission.MissionError):
                engine.run(spec)

    def test_quota_at_reserve_proceeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_OK], quota_remaining=12)
            spec = mission.MissionSpec(mission_id="m-q3", prompt="x")
            self.assertEqual(engine.run(spec).verdict, mission.NEEDS_HUMAN)

    def test_dry_run_never_calls_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_OK], dry_run=True)
            spec = mission.MissionSpec(mission_id="m-dry", prompt="x")
            result = engine.run(spec)
            self.assertEqual(result.provider_calls, 0)
            self.assertEqual(result.verdict, mission.NEEDS_HUMAN)
            self.assertEqual(engine.provider.calls, 0)

    def test_unsafe_mission_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_OK])
            for bad in ("../../etc/passwd", "/abs", "a/b", "", "UPPER", "a" * 65):
                with self.subTest(bad=bad):
                    with self.assertRaises(mission.MissionError):
                        engine.run(mission.MissionSpec(mission_id=bad, prompt="x"))

    def test_unsafe_artifact_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_OK])
            spec = mission.MissionSpec(
                mission_id="m-ok", prompt="x", artifacts=["../escape.py"])
            with self.assertRaises(mission.MissionError):
                engine.run(spec)

    def test_provider_error_yields_fail_not_crash(self):
        class Boom:
            name = "boom"

            def complete(self, *, system, prompt):
                raise provider.ProviderError("provider HTTP 500")

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            engine = mission.MissionEngine(
                provider=Boom(), store_root=root / "s",
                workspace_root=root / "s" / "artifacts", memory_root=root / "m",
                quota_remaining=18)
            result = engine.run(mission.MissionSpec(mission_id="m-err", prompt="x"))
            self.assertEqual(result.verdict, mission.FAIL)
            self.assertIn("provider error", result.reasons[0])

    def test_journal_never_contains_a_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_OK])
            spec = mission.MissionSpec(mission_id="m-sec", prompt="x")
            engine.run(spec)
            journal = pathlib.Path(tmp) / "state" / "artifacts" / "m-sec" / "journal.json"
            blob = journal.read_text(encoding="utf-8")
            for forbidden in ("api_key", "Authorization", "Bearer", "SECRET"):
                self.assertNotIn(forbidden, blob)


class ConcurrencyTests(unittest.TestCase):
    def test_concurrent_run_of_same_id_spends_one_call(self):
        """A real run-level race: while A is inside the provider call, B's run
        of the same mission_id must be refused and spend zero calls.

        This exercises the real ordering (claim after preconditions, before the
        provider) -- not just a direct ``_claim`` call.
        """
        import threading

        started = threading.Event()
        release = threading.Event()

        class SlowProvider:
            name = "slow"

            def __init__(self):
                self.calls = 0

            def complete(self, *, system, prompt):
                self.calls += 1
                started.set()
                release.wait(timeout=5)
                return MATH_OK

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            shared = root / "state"
            slow = SlowProvider()
            a = mission.MissionEngine(
                provider=slow, store_root=shared,
                workspace_root=shared / "artifacts", memory_root=root / "memory",
                quota_remaining=18)
            b = mission.MissionEngine(
                provider=provider.ScriptedProvider([MATH_OK]),
                store_root=shared, workspace_root=shared / "artifacts",
                memory_root=root / "memory", quota_remaining=18)
            spec = mission.MissionSpec(mission_id="m-race", prompt="x")
            result_holder = {}

            def run_a():
                result_holder["a"] = a.run(spec)

            thread = threading.Thread(target=run_a)
            thread.start()
            self.assertTrue(started.wait(timeout=5), "A never reached the provider")
            with self.assertRaises(mission.MissionError):
                b.run(spec)  # must be refused while A holds the claim
            release.set()
            thread.join(timeout=5)
            self.assertEqual(slow.calls, 1)
            self.assertEqual(b.provider.calls, 0)
            self.assertEqual(result_holder["a"].provider_calls, 1)

    def test_claim_is_released_when_the_run_aborts(self):
        """An aborted run must not wedge the mission id permanently."""
        class Abort:
            name = "abort"

            def complete(self, *, system, prompt):
                raise KeyboardInterrupt("simulated abort")

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            eng = mission.MissionEngine(
                provider=Abort(), store_root=root / "s",
                workspace_root=root / "s" / "a", memory_root=root / "m",
                quota_remaining=18)
            spec = mission.MissionSpec(mission_id="m-abort", prompt="x")
            with self.assertRaises(KeyboardInterrupt):
                eng.run(spec)
            claims = root / "s" / "claims"
            self.assertEqual(list(claims.glob("*")) if claims.is_dir() else [], [])
            # A retry with a working provider must be possible.
            eng2 = mission.MissionEngine(
                provider=provider.ScriptedProvider(["no artifacts"]),
                store_root=root / "s", workspace_root=root / "s" / "a",
                memory_root=root / "m", quota_remaining=18)
            self.assertEqual(eng2.run(spec).verdict, mission.NEEDS_HUMAN)


class MemoryTests(unittest.TestCase):
    def test_recall_from_a_fresh_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_OK])
            spec = mission.MissionSpec(mission_id="m-mem", prompt="x")
            engine.run(spec)
            fresh = mission.memory.MemoryStore(pathlib.Path(tmp) / "memory")
            ids = [e.id for e in fresh.search("tel99", "m-mem")]
            self.assertIn("mission-m-mem", ids)

    def test_memory_is_project_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_OK])
            engine.run(mission.MissionSpec(mission_id="m-iso", prompt="x"))
            fresh = mission.memory.MemoryStore(pathlib.Path(tmp) / "memory")
            self.assertEqual(fresh.search("other-project", "m-iso"), [])


class GuardCleanTests(unittest.TestCase):
    """Every command the kernel shells out to must be allowed by the guard."""

    def test_kernel_check_commands_are_guard_clean(self):
        commands = [
            ["python3", "-m", "py_compile", "mathutils.py"],
            ["python3", "-c", "import mathutils; assert mathutils.double(21) == 42"],
        ]
        for command in commands:
            with self.subTest(command=command):
                event = {"tool_name": "terminal",
                         "tool_input": {"command": " ".join(command)}}
                code, _ = guard.decide(event)
                self.assertEqual(code, 0)


class HttpContractTests(unittest.TestCase):
    """Prove the *real* HTTP adapter works end-to-end against a local stub.

    A tiny stdlib HTTP server speaks the OpenAI-compatible protocol on
    localhost. The SAME kernel that runs the ScriptedProvider runs unchanged
    with :class:`OpenAICompatibleProvider` -- which is the whole point of the
    interchangeable-provider contract. No external network, no real model, no
    key.
    """

    @classmethod
    def setUpClass(cls):
        import http.server
        import threading

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence the test log
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(length)
                body = json.dumps({"choices": [
                    {"message": {"content": MATH_OK}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        cls.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_real_http_adapter_runs_the_same_kernel(self):
        p = provider.OpenAICompatibleProvider(
            model="openhands/deepseek-v4.1-flash",
            base_url=f"http://127.0.0.1:{self.port}/v1")
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            engine = mission.MissionEngine(
                provider=p, store_root=root / "s",
                workspace_root=root / "s" / "artifacts", memory_root=root / "m",
                quota_remaining=18)
            spec = mission.MissionSpec(
                mission_id="http-mission", prompt="write mathutils",
                artifacts=["mathutils.py"],
                checks=[mission.Check(
                    "behaviour",
                    ["python3", "-c",
                     "import mathutils; assert mathutils.double(21) == 42"])],
            )
            result = engine.run(spec)
            self.assertEqual(result.verdict, mission.PASS)
            self.assertEqual(result.chosen_model, "openhands/deepseek-v4.1-flash")
            self.assertEqual(result.provider_calls, 1)
            self.assertTrue(
                (root / "s" / "artifacts" / "http-mission" / "mathutils.py").is_file())

    def test_real_http_adapter_refuses_a_paid_model(self):
        with self.assertRaises(provider.ProviderConfigError):
            provider.OpenAICompatibleProvider(
                model="gpt-5.6", base_url=f"http://127.0.0.1:{self.port}/v1")


class CliTests(unittest.TestCase):
    """The native entry point must fail closed and stay deterministic."""

    def _run(self, argv):
        import contextlib
        import io
        from native import cli
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(argv)
        return code, out.getvalue()

    def test_demo_is_deterministic_pass(self):
        code, out = self._run(["demo"])
        self.assertEqual(code, 0)
        self.assertIn("DEMO: PASS", out)
        self.assertIn('"negative_fixture_verdict": "FAIL"', out)

    def test_dry_run_needs_no_provider_and_spends_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self._run(
                ["--state", tmp, "--memory", tmp, "--quota", "18", "--dry-run",
                 "run", "--mission-id", "cli-dry", "--mission", "x"])
            self.assertEqual(code, 0)
            self.assertIn('"provider_calls": 0', out)

    def test_real_run_without_provider_env_refuses(self):
        import os
        saved = {k: os.environ.pop(k, None)
                 for k in ("TEL99_NATIVE_MODEL", "TEL99_NATIVE_BASE_URL",
                           "TEL99_NATIVE_API_KEY")}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                code, _ = self._run(
                    ["--state", tmp, "--memory", tmp, "--quota", "18",
                     "run", "--mission-id", "cli-real", "--mission", "x"])
                self.assertEqual(code, 2)
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_real_run_below_reserve_refuses_before_provider(self):
        import os
        os.environ["TEL99_NATIVE_MODEL"] = "openhands/deepseek-v4.1-flash"
        os.environ["TEL99_NATIVE_BASE_URL"] = "http://localhost:1/v1"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                code, _ = self._run(
                    ["--state", tmp, "--memory", tmp, "--quota", "5",
                     "run", "--mission-id", "cli-low", "--mission", "x"])
                self.assertEqual(code, 2)
        finally:
            os.environ.pop("TEL99_NATIVE_MODEL", None)
            os.environ.pop("TEL99_NATIVE_BASE_URL", None)


if __name__ == "__main__":
    unittest.main()
