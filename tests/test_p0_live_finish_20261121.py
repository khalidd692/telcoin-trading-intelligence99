"""Tests for the read-only, no-worker historical recipe inspector."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import tempfile
from contextlib import closing
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "agents" / "automation" / "p0_live_finish_20261121.py"
spec = importlib.util.spec_from_file_location("p0_history_audit", SCRIPT)
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)

HISTORICAL_SESSIONS = {
    audit_module.MISSION_A: "local-3139741921003cb68e6b35387e61ef623a8c1517b56431e4cdb6f7de17e29e62",
    audit_module.MISSION_B: "local-5e538a446c010b0cac78b968f64f1d7280fbc2baa58670c325e242e6884e9c86",
}


class HistoricalReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)

    def checkpoint(self, mid, status, model="meituan/longcat-2.5:free", cost=0.0,
                   verified=True, evidence=True, session=None):
        session = session or HISTORICAL_SESSIONS.get(mid, "local-" + "a" * 64)
        ckpt = self.state / "ledger" / "kilo-local" / (mid + ".json")
        ckpt.parent.mkdir(parents=True, exist_ok=True)
        value = {"id": mid, "status": status,
                 "contract_sha256": audit_module.EXPECTED_CONTRACTS[mid],
                 "verification": {
                     "ok": verified, "verifier": "hermes-fixed-subprocess-v1",
                     "checks": [{"name": name, "ok": verified}
                                for name in sorted(audit_module.REQUIRED_CHECKS)]},
                 "verdict": {"validated": verified},
                 "result": {"artifact": "OK", "sha256": hashlib.sha256(b"OK").hexdigest(),
                            "specialist_id": audit_module.EXPECTED_ROLES[mid],
                            "model": model, "session_id": session,
                            "provider_evidence": {
                                "model": model, "billing_provider": "nous",
                                "estimated_cost_usd": cost, "actual_cost_usd": cost,
                                "session_id": session,
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

    def test_checkpoint_fingerprint_mismatch_not_reported_as_accepted(self):
        self.setup_ab()
        path = self.state / "ledger" / "kilo-local" / (audit_module.MISSION_A + ".json")
        row = json.loads(path.read_text(encoding="utf-8"))
        row["contract_sha256"] = "f" * 64
        path.write_text(json.dumps(row), encoding="utf-8")
        result = audit_module.audit(self.state)
        self.assertFalse(result["ab_existing_acceptance_verified_from_local_checkpoints"])

    def test_second_checkpoint_cannot_reuse_first_session(self):
        self.setup_ab()
        self.checkpoint(audit_module.MISSION_B, "ACCEPTED",
                        session=HISTORICAL_SESSIONS[audit_module.MISSION_A])
        report = audit_module.audit(self.state)
        self.assertFalse(report["ab_existing_acceptance_verified_from_local_checkpoints"])

    def test_conflicting_duplicate_checkpoint_fields_fail_closed(self):
        self.setup_ab()
        path = self.state / "ledger" / "kilo-local" / (audit_module.MISSION_A + ".json")
        raw = path.read_text(encoding="utf-8")
        path.write_text('{"status":"REJECTED",' + raw[1:], encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate checkpoint key"):
            audit_module.audit(self.state)

    def test_c_cannot_be_reported_accepted_from_the_wrong_state(self):
        self.setup_ab()
        self.checkpoint(audit_module.MISSION_C, "ACCEPTED", model=audit_module.QWEN_MODEL)
        report = audit_module.audit(self.state)
        self.assertEqual(report["c_historical_status"], "ACCEPTED")
        self.assertTrue(report["c_wrong_state_scope"])
        self.assertFalse(report["c_currently_accepted"])

    def test_qwen_billing_db_matches_exact_session_but_c_remains_rejected(self):
        self.setup_ab()
        self.checkpoint(audit_module.MISSION_C, "REJECTED", model=audit_module.QWEN_MODEL)
        db = self.state / "Éléments # historiques" / "state.db"
        db.parent.mkdir()
        with closing(sqlite3.connect(db)) as con, con:
            con.execute("CREATE TABLE session_model_usage (session_id TEXT, model TEXT, "
                        "billing_provider TEXT, estimated_cost_usd REAL, "
                        "actual_cost_usd REAL, cost_status TEXT, last_seen INTEGER)")
            con.execute("INSERT INTO session_model_usage VALUES (?, ?, ?, ?, ?, ?, ?)",
                        ("local-" + "a"*64, audit_module.QWEN_MODEL, "nous", 0.0,
                         0.0, "confirmed", 1))
        report = audit_module.audit(self.state, billing_db=db)
        self.assertEqual(report["c_billing_db_readonly"]["status"], "VERIFIED_ZERO_IN_LOCAL_DB")
        self.assertEqual(report["c_historical_status"], "REJECTED")
        self.assertFalse(report["c_reconciliation_authorised"])

    def test_missing_billing_db_does_not_create_one(self):
        self.setup_ab()
        path = self.state / "not-created.db"
        report = audit_module.audit(self.state, billing_db=path)
        self.assertEqual(report["c_billing_db_readonly"]["status"], "NOT_VERIFIED")
        self.assertFalse(path.exists())

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
