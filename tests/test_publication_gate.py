"""
Tests de la porte de publication (src/publication_gate.py).

Couvrent :
  - chaque motif de refus de la porte ;
  - la compatibilite REELLE entre le collecteur et la porte : l'instantane
    produit par le collecteur doit etre publiable. Ce test a ete ajoute apres
    un echec de production : la porte exigeait un marqueur `collection_status`
    que le collecteur n'ecrivait pas, et aucun test ne le verifiait.

Stdlib uniquement (contrainte CI : aucun requirements.txt).
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collector import tel_collector as tc
from src.publication_gate import (
    PublicationRejected,
    validate_artifacts,
    validate_paths,
)

COLLECTION_ID = "11111111-2222-3333-4444-555555555555"


def valid_sources(mid_mexc=0.0015, mid_kucoin=0.00151):
    """Blocs sources valides : le calcul de l'empreinte les accepte."""
    def block(mid):
        return {
            "status": {"book": {"verdict": "VÉRIFIÉ", "reason": None},
                       "trades": {"verdict": "VÉRIFIÉ", "reason": None}},
            "mid": mid,
            "best": {"bid": mid * 0.999, "ask": mid * 1.001, "last": mid},
            "book": {"bids": [[mid * 0.999, 1000.0]], "asks": [[mid * 1.001, 1000.0]]},
            "trades": [],
            "candles": {},
            "fees": {"verified": False, "value": None, "note": "exclus"},
        }
    return {"mexc": block(mid_mexc), "kucoin": block(mid_kucoin)}


def valid_cross_check():
    return {"mid_mexc": 0.0015, "mid_kucoin": 0.00151, "divergence_bps": 66.6,
            "identical_top_bids_alert": False, "both_books_usable": True,
            "independent_confirmation": "OUI"}


def valid_snapshot(sources=None, cross_check=None, fingerprint=None):
    sources = sources if sources is not None else valid_sources()
    cross_check = cross_check if cross_check is not None else valid_cross_check()
    if fingerprint is None:
        fingerprint = tc.compute_snapshot_fingerprint(sources, cross_check)
    return {
        "schema_version": 1, "symbol": "TELUSDT", "mode": "READ_ONLY_PUBLIC_DATA",
        "generated_at": "2026-10-21T12:00:00.000Z",
        "collection_id": COLLECTION_ID,
        "collection_status": "VALID",
        "sources": sources, "cross_check": cross_check,
        "snapshot_id": fingerprint,
        "request_log": [],
    }


def valid_report():
    return {"schema_version": 1, "symbol": "TELUSDT", "mode": "READ_ONLY_ALERTS",
            "status": "SURVEILLER", "collection_id": COLLECTION_ID,
            "collection_status": "VALID", "orders_sent": 0}


def valid_analysis():
    return {"schema_version": 1, "symbol": "TELUSDT", "mode": "READ_ONLY_ANALYSIS",
            "status": "SURVEILLER", "collection_id": COLLECTION_ID,
            "collection_status": "VALID", "orders_sent": 0,
            "early_reversal": {"signal_status": "ATTENDRE", "direction": "INDETERMINE"}}


class TestGateAccepts(unittest.TestCase):
    def test_valid_triple_is_accepted(self):
        validate_artifacts(valid_snapshot(), valid_report(), valid_analysis(), COLLECTION_ID)

    def test_valid_triple_on_disk_is_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "site").mkdir()
            (root / "site" / "tel_snapshot.json").write_text(
                json.dumps(valid_snapshot()), encoding="utf-8")
            (root / "site" / "report.json").write_text(json.dumps(valid_report()), encoding="utf-8")
            (root / "site" / "agent_analysis.json").write_text(
                json.dumps(valid_analysis()), encoding="utf-8")
            validated = validate_paths(root, COLLECTION_ID)
            self.assertEqual(validated["snapshot"]["collection_id"], COLLECTION_ID)


class TestGateRejects(unittest.TestCase):
    def _assert_rejected(self, snapshot=None, report=None, analysis=None, expected_id=COLLECTION_ID,
                         fragment=""):
        with self.assertRaises(PublicationRejected) as context:
            validate_artifacts(snapshot if snapshot is not None else valid_snapshot(),
                               report if report is not None else valid_report(),
                               analysis if analysis is not None else valid_analysis(),
                               expected_id)
        self.assertIn(fragment, str(context.exception))

    def test_missing_collection_status_is_rejected(self):
        """Le defaut exact qui a bloque la production du 21/10."""
        snapshot = valid_snapshot()
        snapshot.pop("collection_status")
        self._assert_rejected(snapshot=snapshot, fragment="collection_status")

    def test_fallback_status_is_rejected(self):
        snapshot = valid_snapshot()
        snapshot["collection_status"] = "FALLBACK"
        self._assert_rejected(snapshot=snapshot, fragment="fallback")

    def test_missing_collection_id_is_rejected(self):
        report = valid_report()
        report.pop("collection_id")
        self._assert_rejected(report=report, fragment="collection_id")

    def test_symbol_mismatch_is_rejected(self):
        analysis = valid_analysis()
        analysis["symbol"] = "BTCUSDT"
        self._assert_rejected(analysis=analysis, fragment="symbol mismatch")

    def test_different_collection_ids_are_rejected(self):
        report = valid_report()
        report["collection_id"] = "autre-id"
        self._assert_rejected(report=report, fragment="different collection_id")

    def test_missing_expected_collection_id_is_rejected(self):
        self._assert_rejected(expected_id="", fragment="COLLECTION_ID is empty")

    def test_collection_id_mismatch_with_workflow_is_rejected(self):
        self._assert_rejected(expected_id="99999999-9999-9999-9999-999999999999",
                              fragment="mismatch with workflow value")

    def test_missing_snapshot_id_is_rejected(self):
        snapshot = valid_snapshot()
        snapshot.pop("snapshot_id")
        self._assert_rejected(snapshot=snapshot, fragment="snapshot_id missing or malformed")

    def test_fingerprint_mismatch_is_rejected(self):
        snapshot = valid_snapshot()
        snapshot["snapshot_id"] = "0" * 64
        self._assert_rejected(snapshot=snapshot, fragment="does not match the deterministic fingerprint")

    def test_missing_artifact_on_disk_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "site").mkdir()
            (root / "site" / "report.json").write_text(json.dumps(valid_report()), encoding="utf-8")
            (root / "site" / "agent_analysis.json").write_text(
                json.dumps(valid_analysis()), encoding="utf-8")
            with self.assertRaises(PublicationRejected) as context:
                validate_paths(root, COLLECTION_ID)
            self.assertIn("missing or empty", str(context.exception))

    def test_empty_artifact_on_disk_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "site").mkdir()
            (root / "site" / "tel_snapshot.json").write_text("", encoding="utf-8")
            with self.assertRaises(PublicationRejected):
                validate_paths(root, COLLECTION_ID)


class TestCollectorCompatibility(unittest.TestCase):
    """L'instantane REELLEMENT produit par le collecteur doit etre publiable."""

    def _run_collector(self):
        def fake_source_report(client, notional, passes, interval, max_book_age, max_trade_age):
            mid = 0.0015 if client.venue == "mexc" else 0.00151
            return valid_sources(mid, mid * 1.007)["mexc" if client.venue == "mexc" else "kucoin"]
        with patch.object(tc, "source_report", side_effect=fake_source_report):
            return tc.run(passes=1, interval=0, notional=300, collection_id=COLLECTION_ID)

    def test_collector_snapshot_carries_a_collection_status(self):
        snapshot = self._run_collector()
        self.assertIn("collection_status", snapshot)
        self.assertIn(snapshot["collection_status"], {"VALID", "FALLBACK"})

    def test_collector_snapshot_is_publishable_when_data_is_complete(self):
        snapshot = self._run_collector()
        self.assertEqual(snapshot["collection_status"], "VALID")
        self.assertIsNotNone(snapshot.get("snapshot_id"))
        # la porte doit accepter l'instantane tel quel
        report = valid_report()
        analysis = valid_analysis()
        validate_artifacts(snapshot, report, analysis, COLLECTION_ID)

    def test_incomplete_data_yields_a_fallback_snapshot_that_cannot_be_published(self):
        def broken_source_report(client, notional, passes, interval, max_book_age, max_trade_age):
            block = valid_sources()["mexc"]
            block["mid"] = None
            return block
        with patch.object(tc, "source_report", side_effect=broken_source_report):
            snapshot = tc.run(passes=1, interval=0, notional=300, collection_id=COLLECTION_ID)
        self.assertEqual(snapshot["collection_status"], "FALLBACK")
        with self.assertRaises(PublicationRejected) as context:
            validate_artifacts(snapshot, valid_report(), valid_analysis(), COLLECTION_ID)
        self.assertIn("fallback", str(context.exception))


if __name__ == "__main__":
    unittest.main()
