"""Tests for TEL99 zero-spend hybrid free cloud routing (Groq + OpenRouter `:free` + Ollama fallback)."""
from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.agents.automation import provider_router


class HybridFreeCloudTests(unittest.TestCase):
    def _mock_inventory(self, *, groq_ok=True, or_ok=True):
        return {
            "providers": {
                "ollama": {
                    "billing_class": provider_router.BILLING_LOCAL_FREE,
                    "available": True,
                    "quota_status": "READY",
                    "models": [
                        {
                            "id": "local/ollama-gemma4-e4b",
                            "served_model": "gemma4:e4b-tel99-8k",
                            "provider": "ollama",
                            "quality_prior": 0.78,
                            "latency_tier": "medium",
                            "confidential_ok": True,
                        }
                    ],
                },
                "groq": {
                    "billing_class": provider_router.BILLING_FREE_CLOUD_VERIFIED,
                    "available": groq_ok,
                    "quota_status": "READY" if groq_ok else "KEY_NOT_CONFIGURED",
                    "models": [
                        {
                            "id": "groq/openai/gpt-oss-120b",
                            "served_model": "openai/gpt-oss-120b",
                            "provider": "groq",
                            "quality_prior": 0.94,
                            "latency_tier": "fast",
                            "role_tier": "hard_only",
                            "effort_tier": "high",
                            "confidential_ok": False,
                        },
                        {
                            "id": "groq/openai/gpt-oss-20b",
                            "served_model": "openai/gpt-oss-20b",
                            "provider": "groq",
                            "quality_prior": 0.87,
                            "latency_tier": "fast",
                            "role_tier": "executor",
                            "effort_tier": "medium",
                            "confidential_ok": False,
                        },
                    ] if groq_ok else [],
                },
                "openrouter": {
                    "billing_class": provider_router.BILLING_FREE_CLOUD_VERIFIED,
                    "available": or_ok,
                    "quota_status": "READY" if or_ok else "KEY_NOT_CONFIGURED",
                    "models": [
                        {
                            "id": "openrouter/qwen/qwen3-coder:free",
                            "served_model": "qwen/qwen3-coder:free",
                            "provider": "openrouter",
                            "quality_prior": 0.86,
                            "latency_tier": "medium",
                            "role_tier": "executor",
                            "effort_tier": "medium",
                            "confidential_ok": False,
                        }
                    ] if or_ok else [],
                },
            }
        }

    def test_confidential_never_routes_to_cloud(self):
        inv = self._mock_inventory()
        sel = provider_router.select_executor(
            "code", difficulty="hard", confidential=True, allow_free_cloud=True, inventory=inv
        )
        self.assertTrue(sel["ok"])
        self.assertEqual(sel["chosen"]["provider"], "ollama")

    def test_hybrid_routing_easy_local_and_hard_groq(self):
        inv = self._mock_inventory()
        easy = provider_router.select_executor(
            "code", difficulty="easy", confidential=False, allow_free_cloud=True, inventory=inv
        )
        hard = provider_router.select_executor(
            "code", difficulty="hard", confidential=False, allow_free_cloud=True, inventory=inv
        )
        repair = provider_router.select_executor(
            "code", difficulty="medium", confidential=False, allow_free_cloud=True, is_repair=True, inventory=inv
        )
        self.assertEqual(easy["chosen"]["provider"], "ollama")
        self.assertEqual(hard["chosen"]["provider"], "groq")
        self.assertEqual(hard["chosen"]["served_model"], "openai/gpt-oss-120b")
        self.assertEqual(repair["chosen"]["provider"], "groq")

    def test_secret_egress_guard_blocks_tokens(self):
        ok, err = provider_router.validate_cloud_egress_safe("sys", "use ghp_123456789012345678901234", confidential=False)
        self.assertFalse(ok)
        self.assertIn("secret", err.lower())
        ok2, _ = provider_router.validate_cloud_egress_safe("sys", "implement clamp(x, 0, 1)", confidential=False)
        self.assertTrue(ok2)

    def test_allowlist_rejects_unapproved_or_paid_models(self):
        with self.assertRaises(PermissionError):
            provider_router.OpenAICompatFreeCloudAdapter(provider="groq", model="gpt-4o-paid")
        with self.assertRaises(PermissionError):
            provider_router.OpenAICompatFreeCloudAdapter(provider="openrouter", model="openai/gpt-4o")

    def test_budget_ledger_enforces_daily_limits_and_429_cooldown_and_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = provider_router.CloudBudgetLedger(
                Path(tmp) / "budgets.json",
                budgets={"groq": {"max_requests_per_day": 2, "max_tokens_per_day": 5000}},
            )
            self.assertTrue(ledger.can_call("groq", estimated_tokens=1000)[0])
            ledger.record_usage("groq", prompt_tokens=1000, completion_tokens=500)
            ledger.record_usage("groq", prompt_tokens=1000, completion_tokens=500)
            ok, reason = ledger.can_call("groq", estimated_tokens=500)
            self.assertFalse(ok)
            self.assertIn("budget", reason.lower())

            # Test HTTP 429 cooldown + automatic fallback to local Ollama
            ledger2 = provider_router.CloudBudgetLedger(Path(tmp) / "budgets2.json")
            adapter = provider_router.OpenAICompatFreeCloudAdapter(
                provider="groq",
                model="openai/gpt-oss-120b",
                confidential=False,
                fallback_ollama_model="gemma4:e4b-tel99-8k",
                budget_ledger=ledger2,
            )
            err_429 = HTTPError(
                url="https://api.groq.com/openai/v1/chat/completions",
                code=429,
                msg="Too Many Requests",
                hdrs={"Retry-After": "45"},
                fp=BytesIO(b"{}"),
            )
            with patch.object(provider_router, "load_local_provider_key", return_value="gsk_fake_test_key"), \
                 patch.object(provider_router, "urlopen", side_effect=err_429), \
                 patch.object(provider_router.OllamaNativeProvider, "complete", return_value="def f(): return 1\n"):
                out = adapter.complete(system="Return code", prompt="Write f()")
            self.assertIn("def f()", out)
            self.assertTrue(adapter.last_metadata["fallback_used"])
            self.assertEqual(adapter.last_metadata["provider_used"], "ollama")
            self.assertEqual(adapter.last_metadata["cost_usd"], 0.0)
            self.assertFalse(ledger2.can_call("groq")[0])

    def test_openrouter_probe_rejects_paid_models_and_keeps_only_zero_cost_free(self):
        fake_catalog = json.dumps({
            "data": [
                {"id": "qwen/qwen3-coder:free", "pricing": {"prompt": "0", "completion": "0"}, "context_length": 65536},
                {"id": "qwen/qwen3-paid:free", "pricing": {"prompt": "0.0001", "completion": "0.0002"}},
                {"id": "openai/gpt-4o", "pricing": {"prompt": "0", "completion": "0"}},
            ]
        }).encode("utf-8")

        class _FakeResp:
            status = 200
            def read(self, _n=-1): return fake_catalog
            def __enter__(self): return self
            def __exit__(self, *a): return False

        with tempfile.TemporaryDirectory() as tmp:
            ledger = provider_router.CloudBudgetLedger(Path(tmp) / "b.json")
            with patch.object(provider_router, "load_local_provider_key", return_value="sk-or-test"), \
                 patch.object(provider_router, "urlopen", return_value=_FakeResp()):
                res = provider_router._probe_openrouter(budget_ledger=ledger)
            self.assertTrue(res["available"])
            self.assertEqual([m["served_model"] for m in res["models"]], ["qwen/qwen3-coder:free"])


if __name__ == "__main__":
    unittest.main()
