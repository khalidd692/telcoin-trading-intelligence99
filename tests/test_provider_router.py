"""Offline tests for the unified TEL99 multi-provider router."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.agents.automation import provider_router as pr


def _inventory(*, codex_quota="READY", codex_available=True, agy_available=True, ollama_available=True):
    return {
        "schema_version": 1,
        "billing_policy": "no-extra-spend",
        "providers": {
            "ollama": {
                "provider": "ollama",
                "installed": True,
                "available": ollama_available,
                "billing_class": pr.BILLING_LOCAL_FREE,
                "quota_status": "READY" if ollama_available else "UNAVAILABLE",
                "models": [
                    {
                        "id": "local/ollama-gemma4-e4b",
                        "served_model": "gemma4:e4b-tel99-8k",
                        "provider": "ollama",
                        "quality_prior": 0.55,
                        "latency_tier": "slow",
                        "supports_tools": False,
                        "context_tokens": 8192,
                        "confidential_ok": True,
                    },
                    {
                        "id": "local/ollama-qwen2.5-coder-7b",
                        "served_model": "qwen2.5-coder:7b",
                        "provider": "ollama",
                        "quality_prior": 0.40,
                        "latency_tier": "fast",
                        "supports_tools": True,
                        "context_tokens": 32000,
                        "confidential_ok": True,
                    },
                ] if ollama_available else [],
            },
            "codex": {
                "provider": "codex",
                "installed": True,
                "available": codex_available,
                "billing_class": pr.BILLING_SUBSCRIPTION_VERIFIED,
                "quota_status": codex_quota,
                "models": [
                    {
                        "id": "codex/gpt-6.2-sol",
                        "served_model": "gpt-6.2-sol",
                        "provider": "codex",
                        "quality_prior": 0.85,
                        "latency_tier": "medium",
                        "supports_tools": True,
                        "context_tokens": 128000,
                        "confidential_ok": False,
                    },
                ] if codex_available else [],
                "reason": None if codex_available else "quota reserve reached",
            },
            "agy": {
                "provider": "agy",
                "installed": True,
                "available": agy_available,
                "billing_class": pr.BILLING_SUBSCRIPTION_OPT_IN,
                "quota_status": "OPT_IN_NO_RPC_QUOTA",
                "models": [
                    {
                        "id": "agy/gemini-4-neon-high",
                        "served_model": "gemini-4-neon-high",
                        "provider": "agy",
                        "quality_prior": 0.92,
                        "latency_tier": "medium",
                        "supports_tools": True,
                        "context_tokens": 128000,
                        "confidential_ok": False,
                    },
                ] if agy_available else [],
            },
            "claude": {
                "provider": "claude",
                "installed": True,
                "available": False,
                "billing_class": pr.BILLING_UNVERIFIED,
                "quota_status": "EXCLUDED_BY_POLICY",
                "models": [],
                "reason": "billing unverified",
            },
            "gemini": {
                "provider": "gemini",
                "installed": False,
                "available": False,
                "billing_class": pr.BILLING_NOT_INSTALLED,
                "quota_status": "NOT_INSTALLED",
                "models": [],
                "reason": "gemini CLI not found",
            },
            "kilo": {
                "provider": "kilo",
                "installed": True,
                "available": False,
                "billing_class": pr.BILLING_FREE_GATEWAY,
                "quota_status": "EXCLUDED_BY_POLICY",
                "models": [],
                "reason": "synthetic only",
            },
        },
    }


class ProviderRouterTests(unittest.TestCase):
    def test_scrubbed_env_strips_all_paid_api_keys_and_tokens(self):
        dirty = {
            "PATH": "C:/Windows",
            "OPENAI_API_KEY": "sk-secret",
            "ANTHROPIC_API_KEY": "ant-secret",
            "GOOGLE_API_KEY": "g-secret",
            "GEMINI_API_KEY": "gem-secret",
            "GH_TOKEN": "ghp_secret",
            "CUSTOM_SECRET": "val",
        }
        clean = pr.scrubbed_env(dirty)
        self.assertEqual(clean, {"PATH": "C:/Windows"})

    def test_confidential_tasks_only_route_to_local_free_even_with_opt_in(self):
        inv = _inventory()
        decision = pr.select_executor(
            task_kind="code", difficulty="medium", confidential=True,
            allow_subscription_cli=True, inventory=inv,
        )
        self.assertTrue(decision["ok"])
        self.assertEqual(decision["chosen"]["provider"], "ollama")
        self.assertEqual(decision["chosen"]["billing_class"], pr.BILLING_LOCAL_FREE)
        rejected_providers = {row["provider"] for row in decision["rejected"]}
        self.assertIn("codex", rejected_providers)
        self.assertIn("agy", rejected_providers)
        self.assertIn("claude", rejected_providers)

    def test_non_confidential_failover_when_codex_hits_waiting_quota(self):
        inv = _inventory(codex_quota="WAITING_QUOTA", codex_available=False)
        # Without opt-in, agy is rejected and local ollama takes over safely.
        no_opt = pr.select_executor(
            task_kind="code", difficulty="medium", confidential=False,
            allow_subscription_cli=False, inventory=inv,
        )
        self.assertTrue(no_opt["ok"])
        self.assertEqual(no_opt["chosen"]["provider"], "ollama")

        # With explicit opt-in, agy subscription CLI is eligible for non-confidential work.
        opt_in = pr.select_executor(
            task_kind="code", difficulty="medium", confidential=False,
            allow_subscription_cli=True, inventory=inv,
        )
        self.assertTrue(opt_in["ok"])
        self.assertEqual(opt_in["chosen"]["provider"], "agy")
        self.assertEqual(opt_in["chosen"]["billing_class"], pr.BILLING_SUBSCRIPTION_OPT_IN)

    def test_measured_quality_guides_local_model_choice(self):
        inv = _inventory()
        decision = pr.select_executor(
            task_kind="code", difficulty="medium", confidential=True,
            measured_quality={
                "local/ollama-gemma4-e4b": 0.45,
                "local/ollama-qwen2.5-coder-7b": 0.95,
            },
            inventory=inv,
        )
        self.assertTrue(decision["ok"])
        self.assertEqual(decision["chosen"]["id"], "local/ollama-qwen2.5-coder-7b")

    def test_build_adapter_enforces_subscription_opt_in(self):
        agy_sel = {"provider": "agy", "served_model": "gemini-4-neon-high"}
        with self.assertRaises(PermissionError):
            pr.build_adapter(agy_sel, allow_subscription_cli=False)
        with patch("shutil.which", return_value="C:/bin/agy.exe"):
            adapter = pr.build_adapter(agy_sel, allow_subscription_cli=True)
            self.assertIsInstance(adapter, pr.AgyPrintAdapter)
        with self.assertRaises(PermissionError):
            pr.build_adapter({"provider": "claude", "served_model": "claude-opus"})

    def test_resolve_agy_cli_falls_back_to_user_gemini_bin(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = Path(tmp)
            agy_bin = fake_home / ".gemini" / "bin" / "agy.exe"
            agy_bin.parent.mkdir(parents=True)
            agy_bin.write_text("", encoding="utf-8")
            with patch("shutil.which", return_value=None), patch("pathlib.Path.home", return_value=fake_home):
                self.assertEqual(pr._resolve_agy_cli(), str(agy_bin))

    def test_agy_role_specialization_and_high_effort_gating(self):
        inv = {
            "providers": {
                "agy": {
                    "provider": "agy",
                    "installed": True,
                    "available": True,
                    "billing_class": pr.BILLING_SUBSCRIPTION_OPT_IN,
                    "quota_status": "OPT_IN_NO_RPC_QUOTA",
                    "models": [
                        {
                            "id": item["id"],
                            "served_model": item["model"],
                            "provider": "agy",
                            "role_tier": item["role_tier"],
                            "effort_tier": item["effort_tier"],
                            "quality_prior": item["quality_prior"],
                            "latency_tier": item["latency_tier"],
                            "supports_tools": True,
                            "context_tokens": 128000,
                            "confidential_ok": False,
                        }
                        for item in pr.SUBSCRIPTION_MODELS["agy"]
                    ],
                }
            }
        }
        orch = pr.select_executor(
            task_kind="orchestration", difficulty="medium", confidential=False,
            allow_subscription_cli=True, inventory=inv,
        )
        self.assertEqual(orch["chosen"]["served_model"], "gemini-4-neon-medium")
        self.assertTrue(any("difficulty=hard" in r["reason"] for r in orch["rejected"]))

        exe = pr.select_executor(
            task_kind="code", difficulty="medium", confidential=False,
            allow_subscription_cli=True, inventory=inv,
        )
        self.assertEqual(exe["chosen"]["served_model"], "gemini-4-hydrogen-medium")

        hard = pr.select_executor(
            task_kind="code", difficulty="hard", confidential=False,
            allow_subscription_cli=True, inventory=inv,
        )
        self.assertEqual(hard["chosen"]["served_model"], "gemini-4-neon-high")

    def test_agy_print_adapter_places_model_before_print_flag(self):
        with patch("shutil.which", return_value="C:/bin/agy.exe"), patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = '{"status":"SUCCESS","response":"OK","duration_seconds":1.2}'
            adapter = pr.AgyPrintAdapter("gemini-4-hydrogen-medium")
            out = adapter.complete(system="Sys", prompt="Hi")
            self.assertEqual(out, "OK")
            argv = mock_run.call_args.args[0]
            self.assertLess(argv.index("--model"), argv.index("--print"))
            self.assertEqual(adapter.last_metadata.get("status"), "SUCCESS")


if __name__ == "__main__":
    unittest.main()
