"""Tests for the read-only, no-worker historical recipe inspector."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "agents" / "automation" / "p0_live_finish_20261121.py"
spec = importlib.util.spec_from_file_location("p0_history_audit", SCRIPT)
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


class HistoricalReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)

    def checkpoint(self, mid, status, model="meituan/longcat-2.5:free", cost=0.0,
                   verified=True, evidence=True):
        ckpt = self.state / "ledger" / "kilo-local" / (mid + ".json")
        ckpt.parent.mkdir(parents=True, exist_ok=True)
        value = {"id": mid, "status": status, "contract_sha256": "f" * 64,
                 "verification": {"ok": verified, "checks": [{"ok": verified}] * 5},
                 "result": {"artifact": "OK", "sha256": hashlib.sha256(b"OK").hexdigest(),
                            "model": model, "session_id": "local-" + "a"*64,
                            "provider_evidence": {
                                "model": model, "billing_provider": "nous",
                                "estimated_cost_usd": cost, "actual_cost_usd": cost,
                                "session_id": "local-" + "a"*64,
                                "api_call_count": 1} if evidence else {}}}
        ckpt.write_text(json.dumps(value), encoding="utf-8")

    def setup_ab(self):
        for mid in (audit_module.MISSION_A, audit_module.MISSION_B):
            self.checkpoint(mid, "ACCEPTED")

    def test_a_b_accepted_and_rejected_c_never_promoted(self):
        self.setup_ab()
        self.checkpoint(audit_module.MISSION_C, "REJECTED", model=audit_module.QWEN_MODEL)
        before = {p: p.read_bytes() for p in self.state.rglob("*.json")}
        report = audit_module.audit(self.state)
        after = {p: p.read_bytes() for p in self.state.rglob("*.json")}
        self.assertEqual(before, after)
        self.assertTrue(report["ab_existing_acceptance_verified_from_local_checkpoints"])
        self.assertEqual(report["c_historical_status"], "REJECTED")
        self.assertFalse(report["c_currently_accepted"])
        self.assertFalse(report["c_reconciliation_authorised"])
        self.assertFalse(report["live_replay_without_duplicate_calls_proven"])
        self.assertFalse(report["local_worker_invoked"])
        self.assertFalse(report["github_posts_made"])

    def test_missing_c_is_not_silently_started(self):
        self.setup_ab()
        report = audit_module.audit(self.state)
        self.assertEqual(report["c_historical_status"], "MISSING")
        self.assertFalse(report["c_wrong_state_scope"])
        self.assertFalse(report["local_worker_invoked"])

    def test_unknown_c_cost_never_claimed_zero(self):
        self.setup_ab()
        self.checkpoint(audit_module.MISSION_C, "REJECTED", model=audit_module.QWEN_MODEL,
                        evidence=False)
        result = audit_module.audit(self.state)
        self.assertFalse(result["missions"][audit_module.MISSION_C]["provider_cost_evidence_present_and_zero"])
        self.assertIsNone(result["missions"][audit_module.MISSION_C]["actual_cost_usd"])

    def test_malformed_checkpoint_fails_closed(self):
        self.setup_ab()
        ck = self.state / "ledger" / "kilo-local" / (audit_module.MISSION_C + ".json")
        ck.write_text('{"id":"WRONG","status":"ACCEPTED"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "identity"):
            audit_module.audit(self.state)

    def test_no_state_does_not_create_directories(self):
        path = self.state / "missing"
        with self.assertRaisesRegex(ValueError, "state directory not found"):
            audit_module.audit(path)
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
