"""Offline integration & regression tests for the opt-in Google Antigravity SDK backend."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from scripts.agents.automation import (
    antigravity_sdk_backend as sdk_backend,
    env_doctor,
    local_codegen,
    local_team,
    multi_cockpit,
    provider_router,
)
from scripts.agents.native.provider import ProviderError

ROOT = Path(__file__).resolve().parents[1]


class AntigravitySDKBackendUnitTests(unittest.TestCase):
    def test_options_enforce_localhost_and_safe_compaction_threshold(self):
        with self.assertRaises(ValueError):
            sdk_backend.TEL99SDKOptions(
                compaction_token_threshold=sdk_backend.MIN_SAFE_COMPACTION_THRESHOLD - 1
            )
        with self.assertRaises(ValueError):
            sdk_backend.TEL99SDKOptions(base_url="https://generativelanguage.googleapis.com")
        opts = sdk_backend.TEL99SDKOptions(workspaces=[str(ROOT)])
        self.assertEqual(opts.compaction_token_threshold, sdk_backend.DEFAULT_COMPACTION_THRESHOLD)
        self.assertEqual(opts.tool_output_max_tokens, 600)
        self.assertFalse(opts.allow_shell)

    def test_resumed_prompt_helper_preserves_lessons_and_required_tags(self):
        prompt = sdk_backend.build_resumed_prompt_with_lessons(
            "Recall key and verify rule.",
            verified_lessons=["[fix|verified] Strip blanks before lower()."],
            required_tags=["TEL99-KEY-1234", "TAG_OK"],
        )
        self.assertIn("Verified project memory notes", prompt)
        self.assertIn("Strip blanks before lower()", prompt)
        self.assertIn("TEL99-KEY-1234, TAG_OK", prompt)

    def test_sdk_provider_falls_back_to_ollama_native_when_sdk_unavailable(self):
        provider = sdk_backend.AntigravitySDKProvider(
            model="gemma4:e4b-tel99-8k",
            fallback_to_ollama_native=True,
        )
        with patch.object(sdk_backend, "sdk_available", return_value=False), \
             patch.object(sdk_backend, "OllamaNativeProvider") as mock_native:
            mock_native.return_value.complete.return_value = "def f(x):\n    return x\n"
            mock_native.return_value.last_metadata = {"done_reason": "stop"}
            out = provider.complete(system="sys", prompt="prm")
        self.assertIn("def f(x):", out)
        self.assertTrue(provider.last_metadata["fallback_used"])
        self.assertEqual(provider.last_metadata["fallback_reason"], "sdk_not_installed")

    def test_sdk_provider_raises_when_fallback_disabled_and_sdk_missing(self):
        provider = sdk_backend.AntigravitySDKProvider(
            model="gemma4:e4b-tel99-8k",
            fallback_to_ollama_native=False,
        )
        with patch.object(sdk_backend, "sdk_available", return_value=False):
            with self.assertRaises(ProviderError):
                provider.complete(system="sys", prompt="prm")

    def test_bounded_role_pipeline_repairs_once_after_verifier_feedback(self):
        calls = []

        def analyst():
            calls.append("analyst")
            return {"analysis": "Check None and strip."}

        def developer(_analysis, feedback):
            calls.append(("dev", feedback is not None))
            return {"code": "v2" if feedback else "v1"}

        def verifier(cand):
            calls.append(("verifier", cand["code"]))
            if cand["code"] == "v1":
                return {"ok": False, "feedback": {"kind": "candidate-test", "line": 2}}
            return {"ok": True}

        res = sdk_backend.run_bounded_role_pipeline(
            analyst_fn=analyst, developer_fn=developer, verifier_fn=verifier, max_repairs=1
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["attempts"], 2)
        self.assertEqual(
            calls,
            ["analyst", ("dev", False), ("verifier", "v1"), ("dev", True), ("verifier", "v2")],
        )

    def test_provider_router_cockpit_and_doctor_expose_sdk_status_without_breaking_contracts(self):
        inv = provider_router.probe_all_providers(probes={
            "ollama": lambda: {"provider": "ollama", "available": True, "billing_class": "LOCAL_FREE", "quota_status": "READY", "models": []},
            "codex": lambda: {"provider": "codex", "available": False, "billing_class": "SUBSCRIPTION_VERIFIED", "quota_status": "WAITING_QUOTA", "models": []},
            "agy": lambda: {"provider": "agy", "available": False, "billing_class": "SUBSCRIPTION_OPT_IN", "quota_status": "UNAVAILABLE", "models": []},
            "claude": lambda: {"provider": "claude", "available": False, "billing_class": "BILLING_UNVERIFIED", "quota_status": "EXCLUDED_BY_POLICY", "models": []},
            "gemini": lambda: {"provider": "gemini", "available": False, "billing_class": "NOT_INSTALLED", "quota_status": "NOT_INSTALLED", "models": []},
            "kilo": lambda: {"provider": "kilo", "available": False, "billing_class": "FREE_GATEWAY", "quota_status": "EXCLUDED_BY_POLICY", "models": []},
        })
        self.assertIn("sdk_backend", inv)
        self.assertEqual(set(inv["providers"].keys()), {"ollama", "codex", "agy", "claude", "gemini", "kilo"})
        adapter = provider_router.build_adapter(
            {"provider": "ollama", "served_model": "gemma4:e4b-tel99-8k"},
            use_sdk_backend=True,
        )
        self.assertIsInstance(adapter, provider_router.AntigravitySDKAdapter)

        cfg = json.loads((ROOT / "scripts/agents/automation/tel99-config.json").read_text(encoding="utf-8"))
        self.assertIn("sdk_backend", cfg)
        self.assertFalse(cfg["sdk_backend"]["enabled"])
        self.assertTrue(cfg["sdk_backend"]["fallback_to_ollama_native"])

    def test_local_team_analyze_opt_in_sdk_uses_sdk_provider_and_valid_trace_remains_compatible(self):
        mission = {
            "team": list(local_team.TEAM),
            "specialist": "tel99-dev",
            "objective": "Check strip handling.",
            "port": 11434,
            "model": local_team.ANALYST_MODEL,
        }
        with patch.dict(os.environ, {"TEL99_EXECUTION_BACKEND": "antigravity_sdk"}), \
             patch.object(local_team, "AntigravitySDKProvider") as mock_sdk:
            mock_sdk.return_value.complete.return_value = "Strip blank inputs before comparing."
            analysis = local_team.analyze(mission, "def f(x):\n    return x\n")
            mock_sdk.assert_called_once()
        trace = local_team.trace(analysis, developer_model=local_team.ANALYST_MODEL, artifact="code")
        self.assertTrue(local_team.valid_trace(mission, {"sha256": local_team._hash("code"), "agent_trace": trace}))

    def test_real_sdk_config_builder_when_installed(self):
        if not sdk_backend.sdk_available():
            self.skipTest("google-antigravity SDK not installed in this Python environment")
        from google.antigravity import types

        def sample_tool() -> str:
            """Sample tool."""
            return "ok"

        opts = sdk_backend.TEL99SDKOptions(
            tools=[sample_tool],
            workspaces=[str(ROOT)],
            inline_skills=[types.InlineSkill(name="s", description="d", content="c")],
        )
        cfg = sdk_backend.build_tel99_sdk_config(opts)
        self.assertEqual(cfg.capabilities.agent_behavior, types.AgentBehavior.MINIMAL)
        self.assertFalse(cfg.capabilities.enable_subagents)
        self.assertEqual(cfg.compaction_config.token_threshold, 4500)
        names = [p.name for p in cfg.policies]
        self.assertIn("tel99_deny_shell", names)
        self.assertIn("workspace_only", names)


if __name__ == "__main__":
    unittest.main()
