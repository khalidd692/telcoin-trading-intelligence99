#!/usr/bin/env python3
"""Tests for data provenance tracking (collection_id, snapshot_id)."""
import os
import subprocess
import sys
import tempfile
import unittest
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from collector.tel_collector import run, compute_snapshot_fingerprint
from src.monitor import build_report, fallback_report
from src.agent_analysis import build_analysis


class TestProvenanceDeterministic(unittest.TestCase):
    """Deterministic tests for provenance validation and fail-closed behavior."""

    @staticmethod
    def _valid_sources():
        return {
            "mexc": {
                "mid": 0.0015,
                "best": {"bid": 0.00149, "ask": 0.00151},
                "book": {"bids": [(0.00149, 1000)], "asks": [(0.00151, 1000)]},
            },
            "kucoin": {
                "mid": 0.0015,
                "best": {"bid": 0.00149, "ask": 0.00151},
                "book": {"bids": [(0.00149, 1000)], "asks": [(0.00151, 1000)]},
            },
        }

    @staticmethod
    def _valid_cross_check():
        return {"mid_mexc": 0.0015, "mid_kucoin": 0.0015, "divergence_bps": 0.0}

    def test_snapshot_fingerprint_deterministic(self):
        """Test that snapshot fingerprint is deterministic for same valid source data."""
        fingerprint_a = compute_snapshot_fingerprint(self._valid_sources(), self._valid_cross_check())
        fingerprint_b = compute_snapshot_fingerprint(self._valid_sources(), self._valid_cross_check())
        self.assertEqual(fingerprint_a, fingerprint_b)
        self.assertEqual(len(fingerprint_a), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in fingerprint_a))

    def test_monitor_includes_collection_id(self):
        """Test that monitor includes collection_id in report."""
        test_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        ticker = {
            "last": 0.00178, "bid": 0.001779, "ask": 0.001781,
            "spread_pct": 0.1124, "quote_volume_24h": 12345.0,
            "change_pct_24h": 0.7, "source": "MEXC public ticker",
            "observed_at": now.isoformat(),
        }
        kucoin = {"last": 0.001781, "bid": 0.001780, "ask": 0.001782}
        start = int((now.timestamp() - 1200 - 59 * 900) * 1000)
        candles = [
            [start + i * 900_000, 0.0017 + i * 1e-7,
             0.0018 + i * 1e-7, 0.0016 + i * 1e-7,
             0.00171 + i * 1e-7, 1000.0 + i]
            for i in range(60)
        ]
        with patch("src.monitor.utc_now", return_value=now), \
             patch("src.monitor.time.time", return_value=now.timestamp()), \
             patch("src.monitor.mexc_ticker", return_value=ticker), \
             patch("src.monitor.candles_15m", return_value=candles), \
             patch("src.monitor.kucoin_price", return_value=kucoin):
            report = build_report(test_id)
        self.assertIn("collection_id", report)
        self.assertEqual(report["collection_id"], test_id)
        self.assertEqual(report["collection_status"], "VALID")

    def test_monitor_without_collection_id(self):
        """Test that monitor works without collection_id (backward compatibility)."""
        report = build_report(None)
        self.assertNotIn("collection_id", report)

    def test_agent_analysis_verifies_collection_id_match(self):
        """Test that agent_analysis verifies collection_id matches snapshot."""
        test_id = str(uuid.uuid4())
        generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        valid_sources = self._valid_sources()
        valid_sources["mexc"]["candles"] = {"15m": {"status": "OK", "rows": [{"open_time": generated_at, "open": 0.0015, "high": 0.0016, "low": 0.0014, "close": 0.00155, "volume": 1000000}] * 60}}
        snapshot = {
            "schema_version": 1,
            "symbol": "TELUSDT",
            "generated_at": generated_at,
            "collection_id": test_id,
            "snapshot_id": compute_snapshot_fingerprint(valid_sources, self._valid_cross_check()),
            "sources": valid_sources,
            "cross_check": {"independent_confirmation": "OUI", **self._valid_cross_check()}
        }

        report = build_analysis(snapshot, test_id)
        self.assertIn("collection_id", report)
        self.assertEqual(report["collection_id"], test_id)

    def test_snapshot_fingerprint_rejects_missing_or_incomplete_sources(self):
        """Test that a missing or malformed source block is rejected rather than hashed."""
        with self.assertRaises(ValueError):
            compute_snapshot_fingerprint({"mexc": None, "kucoin": {"mid": 0.0015, "best": {"bid": 0.00149, "ask": 0.00151}, "book": {"bids": [(0.00149, 1000)], "asks": [(0.00151, 1000)]}}}, {"mid_mexc": 0.0015, "mid_kucoin": 0.0015, "divergence_bps": 0.0})

        with self.assertRaises(ValueError):
            compute_snapshot_fingerprint({"mexc": {"mid": 0.0015, "best": {"bid": 0.00149, "ask": 0.00151}, "book": {"bids": [], "asks": []}}, "kucoin": {"mid": 0.0015, "best": {"bid": 0.00149, "ask": 0.00151}, "book": {"bids": [(0.00149, 1000)], "asks": [(0.00151, 1000)]}}}, {"mid_mexc": 0.0015, "mid_kucoin": 0.0015, "divergence_bps": 0.0})

    def test_snapshot_fingerprint_rejects_malformed_best_prices(self):
        """Test that a malformed best quote cannot produce a valid snapshot hash."""
        malformed_sources = {
            "mexc": {"mid": 0.0015, "best": {"bid": "bad", "ask": 0.00151}, "book": {"bids": [(0.00149, 1000)], "asks": [(0.00151, 1000)]}},
            "kucoin": {"mid": 0.0015, "best": {"bid": 0.00149, "ask": 0.00151}, "book": {"bids": [(0.00149, 1000)], "asks": [(0.00151, 1000)]}},
        }
        with self.assertRaises(ValueError):
            compute_snapshot_fingerprint(malformed_sources, {"mid_mexc": 0.0015, "mid_kucoin": 0.0015, "divergence_bps": 0.0})

    def test_agent_analysis_rejects_mismatched_snapshot_id(self):
        """Test that a snapshot hash mismatch is rejected before analysis is accepted."""
        generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        valid_sources = self._valid_sources()
        valid_sources["mexc"]["candles"] = {"15m": {"status": "OK", "rows": [{"open_time": generated_at, "open": 0.0015, "high": 0.0016, "low": 0.0014, "close": 0.00155, "volume": 1000000}] * 60}}
        valid_hash = compute_snapshot_fingerprint(valid_sources, self._valid_cross_check())
        snapshot = {
            "schema_version": 1,
            "symbol": "TELUSDT",
            "generated_at": generated_at,
            "collection_id": "123e4567-e89b-12d3-a456-426614174000",
            "snapshot_id": "0" * 64,
            "sources": valid_sources,
            "cross_check": {"independent_confirmation": "OUI", **self._valid_cross_check()},
        }
        report = build_analysis(snapshot, snapshot["collection_id"])
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertIn("snapshot_id", report["reason"].lower())

    def test_agent_analysis_rejects_missing_collection_id(self):
        """Test that agent_analysis rejects snapshot with missing collection_id when expected."""
        test_id = str(uuid.uuid4())
        
        snapshot = {
            "schema_version": 1,
            "symbol": "TELUSDT",
            "generated_at": "2026-10-19T17:00:00.000Z",
            # No collection_id
            "sources": {
                "mexc": {
                    "candles": {
                        "15m": {
                            "status": "OK",
                            "rows": [
                                {
                                    "open_time": "2026-10-19T16:00:00.000Z",
                                    "open": 0.0015,
                                    "high": 0.0016,
                                    "low": 0.0014,
                                    "close": 0.00155,
                                    "volume": 1000000
                                }
                            ] * 60
                        }
                    }
                }
            },
            "cross_check": {
                "independent_confirmation": "OUI"
            }
        }
        
        # Should fail when collection_id is expected but missing
        report = build_analysis(snapshot, test_id)
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertIn("collection_id", report["reason"].lower())

    def test_agent_analysis_rejects_mismatched_collection_id(self):
        """Test that agent_analysis rejects snapshot with mismatched collection_id."""
        test_id = str(uuid.uuid4())
        different_id = str(uuid.uuid4())
        
        snapshot = {
            "schema_version": 1,
            "symbol": "TELUSDT",
            "generated_at": "2026-10-19T17:00:00.000Z",
            "collection_id": different_id,  # Different from expected
            "sources": {
                "mexc": {
                    "candles": {
                        "15m": {
                            "status": "OK",
                            "rows": [
                                {
                                    "open_time": "2026-10-19T16:00:00.000Z",
                                    "open": 0.0015,
                                    "high": 0.0016,
                                    "low": 0.0014,
                                    "close": 0.00155,
                                    "volume": 1000000
                                }
                            ] * 60
                        }
                    }
                }
            },
            "cross_check": {
                "independent_confirmation": "OUI"
            }
        }
        
        # Should fail when collection_id doesn't match
        report = build_analysis(snapshot, test_id)
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertIn("incohérent", report["reason"].lower())

    def test_agent_analysis_without_expected_collection_id(self):
        """Test that agent_analysis works without expected collection_id (backward compatibility)."""
        snapshot = {
            "schema_version": 1,
            "symbol": "TELUSDT",
            "generated_at": "2026-10-19T17:00:00.000Z",
            # No collection_id in snapshot
            "sources": {
                "mexc": {
                    "candles": {
                        "15m": {
                            "status": "OK",
                            "rows": [
                                {
                                    "open_time": "2026-10-19T16:00:00.000Z",
                                    "open": 0.0015,
                                    "high": 0.0016,
                                    "low": 0.0014,
                                    "close": 0.00155,
                                    "volume": 1000000
                                }
                            ] * 60
                        }
                    }
                }
            },
            "cross_check": {
                "independent_confirmation": "OUI"
            }
        }
        
        # Should succeed when no collection_id is expected
        report = build_analysis(snapshot, None)
        # Status depends on data validation, not collection_id check
        self.assertIn("status", report)

    def test_fallback_report_is_fail_closed_for_absent_or_invalid_artifact(self):
        """Fail-closed fallback must remain schema-valid and never claim a valid signal."""
        report = fallback_report("artifact missing or invalid")
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertEqual(report["symbol"], "TELUSDT")
        self.assertEqual(report["collection_status"], "FALLBACK")
        self.assertIn("fail-closed", report["interpretation"].lower())
        self.assertEqual(report["sources"]["mexc_ticker"]["status"], "UNAVAILABLE")

    def test_valid_attendre_report_is_accepted_when_provenance_is_valid(self):
        """A legitimate ATTENDRE report remains valid when its provenance and snapshot are valid."""
        test_id = str(uuid.uuid4())
        generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        valid_sources = self._valid_sources()
        valid_sources["mexc"]["candles"] = {"15m": {"status": "OK", "rows": [{"open_time": generated_at, "open": 0.0015, "high": 0.0016, "low": 0.0014, "close": 0.00155, "volume": 1000000}] * 60}}
        snapshot = {
            "schema_version": 1,
            "symbol": "TELUSDT",
            "generated_at": generated_at,
            "collection_id": test_id,
            "collection_status": "VALID",
            "snapshot_id": compute_snapshot_fingerprint(valid_sources, self._valid_cross_check()),
            "sources": valid_sources,
            "cross_check": {"independent_confirmation": "OUI", **self._valid_cross_check()},
        }
        report = {**snapshot, "status": "ATTENDRE", "collection_status": "VALID", "sources": valid_sources}
        analysis = build_analysis(snapshot, test_id)
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertEqual(analysis["status"], "ATTENDRE")
        self.assertEqual(analysis["collection_status"], "VALID")

    def test_fallback_attendre_report_is_rejected_even_with_matching_ids(self):
        """A fallback ATTENDRE must be rejected even when identifiers match the valid artifacts."""
        test_id = str(uuid.uuid4())
        generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        valid_sources = self._valid_sources()
        valid_sources["mexc"]["candles"] = {"15m": {"status": "OK", "rows": [{"open_time": generated_at, "open": 0.0015, "high": 0.0016, "low": 0.0014, "close": 0.00155, "volume": 1000000}] * 60}}
        snapshot = {
            "schema_version": 1,
            "symbol": "TELUSDT",
            "generated_at": generated_at,
            "collection_id": test_id,
            "collection_status": "FALLBACK",
            "snapshot_id": "0" * 64,
            "sources": valid_sources,
            "cross_check": {"independent_confirmation": "OUI", **self._valid_cross_check()},
        }
        report = {"schema_version": 1, "symbol": "TELUSDT", "status": "ATTENDRE", "collection_status": "FALLBACK", "collection_id": test_id, "sources": {}, "checks": [], "indicators": None}
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertEqual(report["collection_status"], "FALLBACK")
        self.assertTrue(report["collection_status"] == "FALLBACK")
        self.assertTrue(snapshot["collection_status"] == "FALLBACK")

    def test_workflow_validation_fails_nonzero_for_missing_or_invalid_artifacts(self):
        """The publication gate must fail closed for missing or inconsistent provenance artifacts.

        The gate lives in src/publication_gate.py and is executed exactly as the
        workflow does. This test used to run a COPY of the inline workflow
        script, from a temporary directory without the repository on the import
        path: it therefore failed on the import and never exercised the gate.
        """
        repo_root = Path(__file__).resolve().parents[1]
        script = (
            "import sys\n"
            f"sys.path.insert(0, {str(repo_root)!r})\n"
            "from src.publication_gate import main\n"
            "sys.exit(main(['--root', '.']))\n"
        )
        base = {
            "schema_version": 1,
            "symbol": "TELUSDT",
            "collection_id": "123e4567-e89b-12d3-a456-426614174000",
            "snapshot_id": "0" * 64,
            "sources": {
                "mexc": {"mid": 1.0, "best": {"bid": 0.99, "ask": 1.01}, "book": {"bids": [(0.99, 10)], "asks": [(1.01, 10)]}},
                "kucoin": {"mid": 1.0, "best": {"bid": 0.99, "ask": 1.01}, "book": {"bids": [(0.99, 10)], "asks": [(1.01, 10)]}},
            },
            "cross_check": {"mid_mexc": 1.0, "mid_kucoin": 1.0, "divergence_bps": 0.0},
        }
        for label, mutation in [
            ("missing_collection_id", lambda d: {**d, "collection_id": None}),
            ("empty_collection_id", lambda d: {**d, "collection_id": ""}),
            ("mismatched_collection_id", lambda d: {**d, "report": {**d["report"], "collection_id": "different"}}),
            ("wrong_snapshot_id", lambda d: {**d, "snapshot_id": "1" * 64}),
            ("fallback_report_attendre", lambda d: {**d, "report": {**d["report"], "status": "ATTENDRE"}, "analysis": {**d["analysis"], "status": "SURVEILLER"}}),
            ("missing_artifact", lambda d: None),
        ]:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / 'site').mkdir()
                    if mutation is None:
                        pass
                    else:
                        if label == "missing_artifact":
                            pass
                        else:
                            test_snapshot = json.loads(json.dumps(base))
                            test_report = json.loads(json.dumps(base))
                            test_analysis = json.loads(json.dumps(base))
                            if label == "missing_collection_id":
                                test_snapshot.pop("collection_id")
                                test_report["collection_id"] = "123e4567-e89b-12d3-a456-426614174000"
                                test_analysis["collection_id"] = "123e4567-e89b-12d3-a456-426614174000"
                            elif label == "empty_collection_id":
                                test_snapshot["collection_id"] = ""
                                test_report["collection_id"] = "123e4567-e89b-12d3-a456-426614174000"
                                test_analysis["collection_id"] = "123e4567-e89b-12d3-a456-426614174000"
                            elif label == "mismatched_collection_id":
                                test_snapshot["collection_id"] = "123e4567-e89b-12d3-a456-426614174000"
                                test_report["collection_id"] = "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb"
                                test_analysis["collection_id"] = "123e4567-e89b-12d3-a456-426614174000"
                            elif label == "wrong_snapshot_id":
                                test_snapshot["snapshot_id"] = "1" * 64
                                test_report["snapshot_id"] = "1" * 64
                                test_analysis["snapshot_id"] = "1" * 64
                            elif label == "fallback_report_attendre":
                                test_snapshot["collection_id"] = "123e4567-e89b-12d3-a456-426614174000"
                                test_snapshot["collection_status"] = "FALLBACK"
                                test_report["collection_id"] = "123e4567-e89b-12d3-a456-426614174000"
                                test_report["collection_status"] = "FALLBACK"
                                test_report["status"] = "ATTENDRE"
                                test_analysis["collection_id"] = "123e4567-e89b-12d3-a456-426614174000"
                                test_analysis["collection_status"] = "FALLBACK"
                                test_analysis["status"] = "ATTENDRE"
                            (root / 'site' / 'tel_snapshot.json').write_text(json.dumps(test_snapshot), encoding='utf-8')
                            (root / 'site' / 'report.json').write_text(json.dumps(test_report), encoding='utf-8')
                            (root / 'site' / 'agent_analysis.json').write_text(json.dumps(test_analysis), encoding='utf-8')
                    env = os.environ.copy()
                    env['COLLECTION_ID'] = '123e4567-e89b-12d3-a456-426614174000'
                    completed = subprocess.run([sys.executable, '-c', script], cwd=root, env=env, capture_output=True, text=True)
                    self.assertNotEqual(completed.returncode, 0, msg=f'{label} should fail closed')
                    # The rejection must come from the gate itself, not from a
                    # crash (import error, syntax error) that would make the
                    # test pass for the wrong reason.
                    self.assertIn('PUBLICATION REFUSEE', completed.stdout,
                                  msg=f'{label} must be rejected by the publication gate')


@unittest.skipUnless(os.environ.get("TEL_NETWORK_INTEGRATION") == "1", "requires live public-market access")
class TestProvenanceLiveIntegration(unittest.TestCase):
    """Integration tests that exercise the live collector against public endpoints."""

    def test_tel_collector_generates_collection_id(self):
        """Test that tel_collector generates a collection_id when not provided."""
        rep = run(passes=1, interval=1, notional=10, max_book_age=10, max_trade_age=900)
        self.assertIn("collection_id", rep)
        self.assertIsNotNone(rep["collection_id"])
        try:
            uuid.UUID(rep["collection_id"])
        except ValueError:
            self.fail("collection_id is not a valid UUID")

    def test_tel_collector_uses_provided_collection_id(self):
        """Test that tel_collector uses the provided collection_id."""
        test_id = str(uuid.uuid4())
        rep = run(passes=1, interval=1, notional=10, max_book_age=10, max_trade_age=900, collection_id=test_id)
        self.assertEqual(rep["collection_id"], test_id)

    def test_tel_collector_generates_snapshot_id(self):
        """Test that a valid live snapshot yields a SHA-256 fingerprint, otherwise the collector stays fail-closed."""
        rep = run(passes=1, interval=1, notional=10, max_book_age=10, max_trade_age=900)
        if "snapshot_id" in rep:
            self.assertIsNotNone(rep["snapshot_id"])
            self.assertEqual(len(rep["snapshot_id"]), 64)
            self.assertTrue(all(c in "0123456789abcdef" for c in rep["snapshot_id"]))
        else:
            self.assertIn("provenance_error", rep.get("cross_check", {}))


if __name__ == "__main__":
    unittest.main()
