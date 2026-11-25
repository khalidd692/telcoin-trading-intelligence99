"""Offline tests for isolated, quota-attributed V4 recovery."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.agents.automation import run_unseen_v4_eval as ev

QUOTA = "ProviderError: groq unavailable (daily free token budget exhausted) and no local fallback configured"

class V4QuotaRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.art = Path(self.tmp.name)
        self.tasks = ev.benchmark_unseen_v4.get_tasks(per_role_limit=5)
        self.rows = [{"id": t["id"], "ok": True} for t in self.tasks]
        self.rows[0].update(ok=False, error=QUOTA)
        self.rows[1].update(ok=False, error="semantic verification failure")
        self.original = {"phase": "hybrid_after_hardening", "completed": len(self.tasks),
                         "total": len(self.tasks), "results": self.rows}
        self.source = self.art / "ckpt_v4_hybrid_after.json"
        self.source.write_text(json.dumps(self.original), encoding="utf-8")
        (self.art / "unseen_v4_manifest_frozen.json").write_text(
            json.dumps(ev.benchmark_unseen_v4.unseen_v4_manifest()), encoding="utf-8")

    def test_select_only_quota_failures(self):
        self.assertEqual(ev.select_quota_recovery_rows(self.original, self.tasks), [self.rows[0]])

    def test_invalid_source_rejected(self):
        self.original["completed"] -= 1
        with self.assertRaises(ValueError):
            ev.select_quota_recovery_rows(self.original, self.tasks)

    def test_dry_run_no_calls_no_writes(self):
        with patch.object(ev, "evaluate_hybrid_phase") as run:
            report = ev.recover_quota_errors(art_dir=self.art)
        run.assert_not_called()
        self.assertEqual(report["status"], "DRY_RUN")
        self.assertEqual(report["eligible_quota_errors"], 1)
        self.assertFalse((self.art / "v4_quota_recovery").exists())

    def test_separate_recovery_preserves_original_and_prior_failures(self):
        original_bytes = self.source.read_bytes()
        result = {"status": "COMPLETE", "passed": 1, "total": 1, "results": [{"id": self.rows[0]["id"], "ok": True}]}
        with patch.object(ev.provider_router.CloudBudgetLedger, "can_call", return_value=(True, "ok")), patch.object(ev, "evaluate_hybrid_phase", return_value=result) as run:
            report = ev.recover_quota_errors(art_dir=self.art, execute=True)
        self.assertEqual(self.source.read_bytes(), original_bytes)
        self.assertEqual(report["combined_passed_after_targeted_retry"], len(self.tasks)-1)
        self.assertFalse(report["independent_unseen_validation"])
        self.assertEqual([x["id"] for x in run.call_args.args[0]], [self.rows[0]["id"]])
        self.assertTrue(run.call_args.kwargs["pause_on_infra"])
        self.assertTrue((self.art / "v4_quota_recovery" / "report.json").is_file())

    def test_exhausted_budget_never_calls_models(self):
        with patch.object(ev.provider_router.CloudBudgetLedger, "can_call", return_value=(False, "quota")), patch.object(ev, "evaluate_hybrid_phase") as run:
            report = ev.recover_quota_errors(art_dir=self.art, execute=True)
        self.assertEqual(report["status"], "WAITING_QUOTA")
        run.assert_not_called()

    def test_changed_source_refused(self):
        with patch.object(ev.provider_router.CloudBudgetLedger, "can_call", return_value=(False, "quota")):
            ev.recover_quota_errors(art_dir=self.art, execute=True)
            self.source.write_text(json.dumps(self.original, indent=2), encoding="utf-8")
            with self.assertRaises(ValueError):
                ev.recover_quota_errors(art_dir=self.art, execute=True)

if __name__ == "__main__":
    unittest.main()
