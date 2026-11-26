"""Offline regression tests for per-model Groq quotas. No provider calls."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from scripts.agents.automation import provider_router as pr


class GroqModelQuotaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "ledger.json"
        self.ledger = pr.CloudBudgetLedger(self.path)
        self.a = self.ledger.scope_for_model("groq", "openai/gpt-oss-120b")
        self.b = self.ledger.scope_for_model("groq", "openai/gpt-oss-20b")

    def test_owner_reserve_and_independent_models(self):
        self.assertTrue(self.ledger.reserve_budget(self.a, estimated_tokens=160_000)[0])
        self.assertFalse(self.ledger.reserve_budget(self.a, estimated_tokens=1)[0])
        self.assertTrue(self.ledger.reserve_budget(self.a, estimated_tokens=40_000, purpose="interactive")[0])
        self.assertFalse(self.ledger.reserve_budget(self.a, estimated_tokens=1, purpose="interactive")[0])
        self.assertTrue(self.ledger.reserve_budget(self.b, estimated_tokens=1000)[0])
        state = self.ledger.status("groq")
        self.assertEqual(state["max_tokens_per_day"], 600_000)
        self.assertEqual(state["tokens_today"], 201_000)
        self.assertEqual(state["remaining_tokens_budget"], 399_000)
        self.assertFalse(self.ledger.reserve_budget("groq", estimated_tokens=1)[0])

    def test_reconciliation_preserves_owner_usage(self):
        ok, _, reservation = self.ledger.reserve_budget(self.a, estimated_tokens=1000)
        self.assertTrue(ok)
        self.ledger.reconcile_usage(self.a, reservation, prompt_tokens=400, completion_tokens=100)
        ok, _, owner = self.ledger.reserve_budget(self.a, estimated_tokens=1000, purpose="interactive")
        self.assertTrue(ok)
        self.ledger.reconcile_usage(self.a, owner, prompt_tokens=200, completion_tokens=100)
        s = self.ledger.status(self.a)
        self.assertEqual(s["tokens_today"], 800)
        self.assertEqual(s["background_tokens_today"], 500)
        self.assertEqual(s["background_requests_today"], 1)

    def test_legacy_same_day_is_blocked_then_natural_rollover(self):
        self.path.write_text(json.dumps({"schema_version": 1, "providers": {"groq": {
            "date_utc": "2026-11-25", "requests_today": 412, "tokens_today": 449639,
            "cooldown_until_ts": 0, "rate_limit_hits": 198, "last_headers": {}
        }}}), encoding="utf-8")
        with patch.object(pr.CloudBudgetLedger, "_today_utc", return_value="2026-11-25"):
            self.assertTrue(self.ledger.status("groq")["legacy_unattributed"])
            self.assertEqual(self.ledger.status("groq")["tokens_today"], 449639)
            self.assertFalse(self.ledger.reserve_budget(self.a, estimated_tokens=1000)[0])
            self.assertFalse(self.ledger.can_call("groq")[0])
        with patch.object(pr.CloudBudgetLedger, "_today_utc", return_value="2026-11-26"):
            self.assertTrue(self.ledger.reserve_budget(self.a, estimated_tokens=1000)[0])

    def test_rate_limit_is_model_specific(self):
        self.ledger.record_rate_limit(self.a, retry_after_s=60, now=1000)
        self.assertFalse(self.ledger.can_call(self.a, now=1001)[0])
        self.assertTrue(self.ledger.can_call(self.b, now=1001)[0])

    def test_atomic_background_reserve(self):
        def reserve(_):
            return self.ledger.reserve_budget(self.a, estimated_tokens=40_000)[0]
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(reserve, range(10)))
        self.assertEqual(sum(outcomes), 4)

    def test_cross_midnight_reconciliation(self):
        with patch.object(pr.CloudBudgetLedger, "_today_utc", return_value="2026-11-25"):
            ok, _, old = self.ledger.reserve_budget(self.a, estimated_tokens=1000)
            self.assertTrue(ok)
        with patch.object(pr.CloudBudgetLedger, "_today_utc", return_value="2026-11-26"):
            self.ledger.reserve_budget(self.a, estimated_tokens=500)
            self.ledger.reconcile_usage(self.a, old, prompt_tokens=200, completion_tokens=100)
            self.assertEqual(self.ledger.status(self.a)["tokens_today"], 800)

    def test_unknown_model_denied_and_corruption_fail_closed(self):
        with self.assertRaises(PermissionError):
            self.ledger.scope_for_model("groq", "allam-2-7b")
        self.path.write_text("{bad", encoding="utf-8")
        self.assertFalse(self.ledger.reserve_budget(self.a)[0])
        self.assertFalse(self.ledger.can_call("groq")[0])

    def test_adapter_confidential_gate_never_calls_cloud(self):
        adapter = pr.OpenAICompatFreeCloudAdapter(
            provider="groq", model="openai/gpt-oss-120b", confidential=True,
            budget_ledger=self.ledger, fallback_ollama_model=None,
            budget_purpose="interactive",
        )
        with patch.object(pr, "urlopen") as network:
            with self.assertRaises(pr.ProviderError):
                adapter.complete(system="test", prompt="test")
            network.assert_not_called()
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
