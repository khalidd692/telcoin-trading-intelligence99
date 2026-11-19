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
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

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

    def test_included_model_override_is_only_for_loopback(self):
        for endpoint in ("https://example.test/v1", "https://127.0.0.1@example.test/v1"):
            with self.subTest(endpoint=endpoint), self.assertRaises(provider.ProviderConfigError):
                provider.OpenAICompatibleProvider(
                    model="gpt-6.2-sol", base_url=endpoint, api_key="fixture",
                    included_local_model="gpt-6.2-sol")

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


class KiloGatewayTests(unittest.TestCase):
    endpoint = "https://ai-gateway.kilo.ai/api/v1"
    model = "kilo-auto/free"

    def _provider(self, **overrides):
        config = {"base_url": self.endpoint, "model": self.model, "synthetic_data": True}
        return provider.OpenAICompatibleProvider(**(config | overrides))

    def _catalog(self, **overrides):
        return {"data": [{"id": self.model, "isFree": True, "mayTrainOnYourPrompts": True,
                          "pricing": {"prompt": "0", "completion": "0", "request": "0"}}
                         | overrides]}

    def _http_response(self, payload):
        response = MagicMock()
        http = response.__enter__.return_value
        http.status = 200
        http.read.return_value = json.dumps(payload).encode()
        return response

    def _completion(self, usage):
        return {"model": "example/synthetic:free", "usage": usage,
                "choices": [{"message": {"content": MATH_OK}}]}

    def test_requires_synthetic_opt_in_exact_endpoint_and_no_credentials(self):
        self.assertTrue(self._provider().requires_explicit_quota)
        self.assertIn(self.model, provider.free_model_ids())
        self.assertNotIn(self.model, provider.cfg.FREE_MODEL_IDS)
        for overrides in (
            {"synthetic_data": False}, {"api_key": "fixture"},
            {"base_url": "http://127.0.0.1/v1", "included_local_model": self.model},
            {"base_url": "https://ai-gateway.kilo.ai.evil.test/api/v1"},
            {"base_url": self.endpoint.replace(".ai/", ".ai:8443/")},
            {"base_url": self.endpoint + "/alternate"},
            {"model": "openhands/deepseek-v4.1-flash", "api_key": "fixture"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(provider.ProviderConfigError):
                self._provider(**overrides)

    def test_catalog_refusals_send_no_prompt(self):
        for catalog in (
            self._catalog(isFree=False), self._catalog(mayTrainOnYourPrompts=None),
            self._catalog(pricing={"prompt": 0}),
            self._catalog(pricing={"prompt": 0, "completion": 0, "request": "0.001"}),
            {"data": []}, {"data": self._catalog()["data"] * 2},
        ):
            with self.subTest(catalog=catalog):
                configured = self._provider()
                with patch.object(configured._opener, "open", return_value=self._http_response(catalog)) as http:
                    with self.assertRaises(provider.ProviderError):
                        configured.complete(system="s", prompt="synthetic fixture")
                self.assertEqual(http.call_count, 1)
                req = http.call_args.args[0]
                self.assertEqual(req.get_method(), "GET")
                self.assertIsNone(req.data)

    def test_zero_cost_completion_records_only_selected_http_metadata(self):
        configured = self._provider()
        completion = self._completion({"cost": 0})
        with patch.object(configured._opener, "open", side_effect=[
            self._http_response(self._catalog()), self._http_response(completion),
        ]) as http:
            with tempfile.TemporaryDirectory() as tmp:
                engine = _engine(tmp, [])
                engine.provider = configured
                spec = mission.MissionSpec("kilo-fixture", "synthetic fixture", ["mathutils.py"],
                                           [mission.Check("fixture", [sys.executable, "-c", "pass"])])
                result = engine.run(spec)
                self.assertEqual(result.verdict, mission.PASS)
                evidence = engine.record_for(spec)["attempts"][0]["provider_evidence"]
        get, post = [call.args[0] for call in http.call_args_list]
        self.assertEqual((get.full_url, post.full_url),
                         (self.endpoint + "/models", self.endpoint + "/chat/completions"))
        self.assertEqual((get.get_method(), post.get_method()), ("GET", "POST"))
        self.assertFalse(get.has_header("Authorization") or post.has_header("Authorization"))
        self.assertEqual(json.loads(post.data)["model"], self.model)
        self.assertEqual(evidence["http_status"], 200)
        self.assertEqual(evidence["response_model"], completion["model"])
        self.assertEqual(evidence["cost_usd"], "0")
        self.assertTrue(evidence["may_train_on_prompts"])
        self.assertNotIn("synthetic fixture", json.dumps(evidence))

    def test_missing_or_nonzero_cost_rejects_completion(self):
        for usage in ({}, {"cost": False}, {"cost": "1e-500"}):
            with self.subTest(usage=usage):
                configured = self._provider()
                with patch.object(configured._opener, "open", side_effect=[
                    self._http_response(self._catalog()), self._http_response(self._completion(usage)),
                ]):
                    with self.assertRaises(provider.ProviderError):
                        configured.complete(system="s", prompt="synthetic fixture")

    def test_http_refusals_do_not_retry_or_fall_back(self):
        from urllib.error import HTTPError

        for status in (302, 401, 402, 403, 429):
            with self.subTest(status=status):
                configured = self._provider()
                refusal = HTTPError(self.endpoint, status, "fixture", None, None)
                with patch.object(configured._opener, "open", side_effect=[
                    self._http_response(self._catalog()), refusal,
                ]) as http:
                    with self.assertRaisesRegex(provider.ProviderError, f"HTTP {status}"):
                        configured.complete(system="s", prompt="synthetic fixture")
                self.assertEqual(http.call_count, 2)
                self.assertIsNone(configured.last_completion_evidence)

    def test_cli_requires_opt_in_and_explicit_budget_before_any_network(self):
        import contextlib
        import io
        from native import cli

        env = {"TEL99_NATIVE_MODEL": self.model, "TEL99_NATIVE_BASE_URL": self.endpoint}
        argv = ["run", "--mission-id", "kilo-fixture", "--mission", "synthetic fixture"]
        with patch.dict(os.environ, env, clear=True), \
                patch.object(cli, "read_quota") as fallback_quota, \
                patch("urllib.request.OpenerDirector.open") as http, \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(cli.main(["--quota", "12", *argv]), 2)
            self.assertIn("explicit synthetic data", errors.getvalue())
            self.assertEqual(cli.main([*argv, "--synthetic-data"]), 2)
            self.assertIn("quota unknown", errors.getvalue())
        fallback_quota.assert_not_called()
        http.assert_not_called()


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
                                      [sys.executable, "-m", "py_compile", "mathutils.py"])],
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
                    [sys.executable, "-c",
                     "import mathutils; assert mathutils.double(21) == 42"])],
            )
            result = engine.run(spec)
            self.assertEqual(result.verdict, mission.FAIL)
            # The model's text claimed PASS; the kernel ignored it.
            self.assertTrue(result.checks[0]["ok"] is False)

    def test_engine_repairs_a_red_check_within_a_bounded_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_BAD, MATH_OK])
            spec = mission.MissionSpec(
                mission_id="repair", prompt="make double", artifacts=["mathutils.py"],
                max_repairs=1, checks=[mission.Check(
                    "behaviour", [sys.executable, "-c",
                                  "import mathutils; assert mathutils.double(21) == 42"])])
            result = engine.run(spec)
            self.assertEqual(result.verdict, mission.PASS)
            self.assertEqual(result.provider_calls, 2)
            self.assertEqual([attempt["verdict"] for attempt in result.attempts],
                             [mission.FAIL, mission.PASS])

    def test_incomplete_artifact_set_never_passes_even_with_a_green_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_OK] * 4)
            spec = mission.MissionSpec(
                mission_id="missing", prompt="two files",
                artifacts=["mathutils.py", "README.md"],
                checks=[mission.Check("green", [sys.executable, "-c", "pass"])])
            result = engine.run(spec)
            self.assertEqual(result.verdict, mission.FAIL)
            self.assertIn("README.md", result.attempts[-1]["missing_artifacts"])

    def test_zero_repairs_does_not_retry_missing_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_OK, MATH_OK])
            result = engine.run(mission.MissionSpec(
                "no-repair", "two files", artifacts=["mathutils.py", "README.md"], max_repairs=0))
            self.assertEqual(result.verdict, mission.FAIL)
            self.assertEqual(result.provider_calls, 1)

    def test_artifact_journal_recovers_if_the_mission_index_write_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_OK])
            spec = mission.MissionSpec("recover", "write", artifacts=["mathutils.py"],
                                       checks=[mission.Check("green", [sys.executable, "-c", "pass"])])
            with patch.object(engine.store, "put", side_effect=OSError("index unavailable")):
                with self.assertRaises(OSError):
                    engine.run(spec)
            restored = engine.run(spec)
            self.assertTrue(restored.reused)
            self.assertEqual(restored.verdict, mission.PASS)
            self.assertEqual(engine.provider.calls, 1)

    def test_repair_preserves_the_quota_floor(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_BAD, MATH_OK], quota_remaining=12)
            spec = mission.MissionSpec(
                mission_id="repair-quota", prompt="make double", artifacts=["mathutils.py"],
                max_repairs=1, checks=[mission.Check(
                    "behaviour", [sys.executable, "-c",
                                  "import mathutils; assert mathutils.double(21) == 42"])])
            result = engine.run(spec)
            self.assertEqual(result.verdict, mission.FAIL)
            self.assertEqual(result.provider_calls, 1)

    def test_idempotency_no_double_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_OK])
            spec = mission.MissionSpec(
                mission_id="m-once", prompt="write", artifacts=["mathutils.py"],
                checks=[mission.Check("compile",
                                      [sys.executable, "-m", "py_compile", "mathutils.py"])],
            )
            first = engine.run(spec)
            second = engine.run(spec)
            self.assertFalse(first.reused)
            self.assertTrue(second.reused)
            self.assertEqual(second.provider_calls, 0)

    def test_same_mission_id_is_isolated_across_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _engine(tmp, [MATH_OK, MATH_BAD])
            check = mission.Check("behaviour", [
                sys.executable, "-c", "import mathutils; assert mathutils.double(21) == 42",
            ])
            common = {"mission_id": "shared-id", "prompt": "write",
                      "artifacts": ["mathutils.py"], "checks": [check]}
            first = engine.run(mission.MissionSpec(project="tel99", **common))
            second = engine.run(mission.MissionSpec(project="project-b", **common))

            self.assertEqual(first.verdict, mission.PASS)
            self.assertEqual(second.verdict, mission.FAIL)
            self.assertFalse(second.reused)
            self.assertEqual(second.provider_calls, 1)
            self.assertEqual(engine.recall("shared-id", project="tel99")[0]["project"], "tel99")
            self.assertEqual(engine.recall("shared-id", project="project-b")[0]["project"],
                             "project-b")
            artifacts = pathlib.Path(tmp) / "state" / "artifacts"
            self.assertIn("return add(x, x)",
                          (artifacts / "shared-id" / "mathutils.py").read_text())
            self.assertIn("return x",
                          (artifacts / "_projects" / "project-b" / "shared-id"
                           / "mathutils.py").read_text())

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
            for bad in ("../../etc/passwd", "/abs", "a/b", "", "UPPER", "a" * 65,
                        "con", "lpt1.txt", "trailing.", "newline\n"):
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
                    [sys.executable, "-c",
                     "import mathutils; assert mathutils.double(21) == 42"])],
            )
            result = engine.run(spec)
            self.assertEqual(result.verdict, mission.PASS)
            self.assertEqual(result.chosen_model, "openhands/deepseek-v4.1-flash")
            self.assertEqual(result.provider_calls, 1)
            self.assertTrue(
                (root / "s" / "artifacts" / "http-mission" / "mathutils.py").is_file())

    def test_approved_loopback_model_uses_the_same_http_contract(self):
        p = provider.OpenAICompatibleProvider(
            model="gpt-6.2-sol", included_local_model="gpt-6.2-sol",
            base_url=f"http://127.0.0.1:{self.port}/v1")
        self.assertTrue(p.requires_explicit_quota)
        self.assertEqual(p.complete(system="fixture", prompt="fake HTTP contract only"), MATH_OK)

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

    def test_cached_failure_remains_a_cli_failure(self):
        bad_file = "```mathutils.py\ndef incomplete(\n```"
        scripted = provider.ScriptedProvider([bad_file])
        with tempfile.TemporaryDirectory() as tmp:
            args = ["--state", tmp, "--memory", tmp, "--quota", "18",
                    "run", "--mission-id", "cli-bad", "--mission", "write",
                    "--artifact", "mathutils.py"]
            with patch.object(provider, "provider_from_env", return_value=scripted):
                self.assertEqual(self._run(args)[0], 3)
                code, out = self._run(args)

        self.assertEqual(code, 3)
        self.assertIn('"reused": true', out)
        self.assertIn('"provider_calls": 0', out)

    def test_cli_project_controls_mission_and_recall(self):
        scripted = provider.ScriptedProvider([MATH_OK])
        with tempfile.TemporaryDirectory() as tmp:
            roots = ["--state", tmp, "--memory", tmp]
            with patch.object(provider, "provider_from_env", return_value=scripted):
                code, _ = self._run(roots + [
                    "--quota", "18", "run", "--project", "project-b",
                    "--mission-id", "cli-scoped", "--mission", "write",
                    "--artifact", "mathutils.py",
                ])
            self.assertEqual(code, 0)
            _, default = self._run(roots + ["recall", "--query", "cli-scoped"])
            _, scoped = self._run(roots + [
                "recall", "--project", "project-b", "--query", "cli-scoped",
            ])

        self.assertEqual(json.loads(default), [])
        self.assertEqual(json.loads(scoped)[0]["project"], "project-b")

    def test_private_memory_round_trip_across_separate_cli_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source, fresh, backup = root / "source", root / "fresh", root / "snapshot.json"
            memory = mission.memory.MemoryStore(source)
            memory.record(mission.memory.Entry(
                id="verified-fact", project="project-b", kind="fact", title="Unique fact",
                body="A synthetic fact for restoration", verified=True, verified_by="audit"))
            memory.record(mission.memory.Entry(
                id="different-fact", project="tel99", kind="fact", title="Other project",
                body="Independently scoped fixture"))
            command = [sys.executable, "-m", "scripts.agents.native.cli"]

            def call(*args):
                return subprocess.run([*command, *map(str, args)], cwd=ROOT,
                                      capture_output=True, text=True, check=False, timeout=15)

            exported = call("--memory", source, "export-memory", "--project", "project-b",
                            "--file", backup)
            self.assertEqual(exported.returncode, 0, exported.stderr)
            if os.name == "posix":
                self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
            data = json.loads(backup.read_text())
            self.assertEqual([e["id"] for e in data["entries"]], ["verified-fact"])
            wrong = call("--memory", fresh, "restore-memory", "--project", "tel99",
                         "--file", backup)
            self.assertEqual(wrong.returncode, 2)
            restored = call("--memory", fresh, "restore-memory", "--project", "project-b",
                            "--file", backup)
            self.assertEqual(restored.returncode, 0, restored.stderr)
            recall = call("--memory", fresh, "recall", "--project", "project-b",
                          "--query", "unique")
            self.assertEqual(recall.returncode, 0, recall.stderr)
            fact = json.loads(recall.stdout)[0]
            self.assertEqual(fact["verified_by"], "audit")
            self.assertEqual(mission.memory.MemoryStore(fresh).history("project-b"),
                             memory.history("project-b"))
            self.assertEqual(call("--memory", fresh, "restore-memory", "--project",
                                  "project-b", "--file", backup).returncode, 2)
            self.assertEqual(call("--memory", source, "export-memory", "--project",
                                  "project-b", "--file", backup).returncode, 2)
            self.assertEqual(json.loads(backup.read_text()), data)

    def test_native_cli_runs_a_declared_script_in_a_pinned_sandbox(self):
        from native import cli
        image = "python@sha256:" + "1" * 64
        source = "```script.py\nprint('fixture result')\n```"
        scripted = provider.ScriptedProvider([source])
        completed = subprocess.CompletedProcess([], 0, b"fixture result\n")
        with tempfile.TemporaryDirectory() as tmp:
            args = ["--state", tmp, "--memory", tmp, "--quota", "18",
                    "run", "--mission-id", "script-test", "--mission", "write",
                    "--artifact", "script.py", "--sandbox-image", image,
                    "--sandbox-script", "script.py", "--expected-stdout", "fixture result"]
            with patch.object(provider, "provider_from_env", return_value=scripted), \
                    patch.object(cli.sandbox, "_run_container", return_value=completed) as launch:
                code, out = self._run(args)

        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["checks"][-1]["name"], "sandboxed-script")
        self.assertEqual(launch.call_args.args[0], image)

    def test_cached_syntax_only_run_cannot_satisfy_a_sandbox_check(self):
        image = "python@sha256:" + "1" * 64
        scripted = provider.ScriptedProvider([MATH_OK])
        with tempfile.TemporaryDirectory() as tmp:
            args = ["--state", tmp, "--memory", tmp, "--quota", "18",
                    "run", "--mission-id", "syntax-first", "--mission", "write",
                    "--artifact", "mathutils.py"]
            with patch.object(provider, "provider_from_env", return_value=scripted):
                self.assertEqual(self._run(args)[0], 0)
                code, _ = self._run(args + [
                    "--sandbox-image", image, "--sandbox-script", "mathutils.py",
                    "--expected-stdout", "value",
                ])

        self.assertEqual(code, 2)
        self.assertEqual(scripted.calls, 1)

    @unittest.skipUnless(os.environ.get("TEL99_TEST_SANDBOX_IMAGE"),
                         "requires a local Docker image pinned by digest")
    def test_native_sandbox_accepts_only_the_observed_output(self):
        image = os.environ["TEL99_TEST_SANDBOX_IMAGE"]
        fixture = """```probe.py
import os
import socket
assert "TEL99_PRIVATE_FIXTURE" not in os.environ
assert {name for _, name in socket.if_nameindex()} == {"lo"}
assert not os.access("/work/program.py", os.W_OK)
print("isolated")
```"""
        with tempfile.TemporaryDirectory() as root, patch.dict(
                os.environ, {"TEL99_PRIVATE_FIXTURE": "synthetic"}):
            for mission_id, expected, verdict in (
                ("probe-good", "isolated", 0), ("probe-incorrect", "other", 3),
            ):
                with self.subTest(mission_id=mission_id), patch.object(
                        provider, "provider_from_env",
                        return_value=provider.ScriptedProvider([fixture])):
                    code, output = self._run([
                        "--state", root, "--memory", root, "--quota", "18",
                        "run", "--mission-id", mission_id, "--mission", "fixture",
                        "--artifact", "probe.py", "--sandbox-image", image,
                        "--sandbox-script", "probe.py", "--expected-stdout", expected,
                    ])
                    self.assertEqual(code, verdict, output)

    @unittest.skipUnless(os.environ.get("TEL99_TEST_SANDBOX_IMAGE"),
                         "requires a local Docker image pinned by digest")
    def test_task_app_mission_repairs_a_real_failed_acceptance_case(self):
        source = (ROOT / "tests/fixtures/native_tasks_candidate.py").read_text()
        broken = source.replace('task["done"] = True', 'task["done"] = False')

        def response(program):
            return ("```tasks.py\n" + program + "\n```\n"
                    "````README.md\nUse python tasks.py --db tasks.json list.\n"
                    "```text\n add TITLE; edit ID TITLE; complete ID; delete ID\n```\n````")

        scripted = provider.ScriptedProvider([response(broken), response(source)])
        with tempfile.TemporaryDirectory() as root:
            args = ["--state", root, "--memory", root, "--quota", "18", "run",
                    "--project", "task-demo", "--mission-id", "task-app", "--profile", "tasks",
                    "--mission", "Crée une application de gestion de tâches.",
                    "--sandbox-image", os.environ["TEL99_TEST_SANDBOX_IMAGE"]]
            with patch.object(provider, "provider_from_env", return_value=scripted):
                code, report = self._run(args)
            self.assertEqual(code, 0, report)
            result = json.loads(report)
            self.assertEqual([attempt["verdict"] for attempt in result["attempts"]],
                             ["FAIL", "PASS"])
            self.assertEqual(scripted.calls, 2)
            program = pathlib.Path(result["artifact_directory"]) / "tasks.py"
            self.assertEqual(program.read_text().strip(), source.strip())
            self.assertTrue((program.parent / "journal.json").is_file())
            status, stored = self._run(["--state", root, "status", "--mission-id",
                                       "task-app", "--project", "task-demo"])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(stored)["provider"], "scripted")
            self.assertIsNone(json.loads(stored)["chosen_model"])
            self.assertEqual(json.loads(stored)["attempts"][0]["checks"][-1]["criterion"],
                             "complete persists the done flag")
            verify, _ = self._run(["verify-task-app", "--file", str(program),
                                   "--sandbox-image", os.environ["TEL99_TEST_SANDBOX_IMAGE"]])
            self.assertEqual(verify, 0)

    def test_cached_pass_rejects_artifacts_edited_after_check(self):
        scripted = provider.ScriptedProvider([MATH_OK])
        with tempfile.TemporaryDirectory() as tmp:
            args = ["--state", tmp, "--memory", tmp, "--quota", "18", "run",
                    "--mission-id", "before-edit", "--mission", "write",
                    "--artifact", "mathutils.py"]
            with patch.object(provider, "provider_from_env", return_value=scripted):
                code, output = self._run(args)
                self.assertEqual(code, 0)
                artifact = pathlib.Path(json.loads(output)["artifact_directory"]) / "mathutils.py"
                artifact.write_text("modified", encoding="utf-8")
                code, _ = self._run(args)
            self.assertEqual(code, 2)
            self.assertEqual(scripted.calls, 1)

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
