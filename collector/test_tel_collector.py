"""Offline logic tests; they do not prove exchange connectivity."""
import json, os, unittest
from unittest.mock import patch
from collector import tel_collector as tc

class CollectorTests(unittest.TestCase):
    def test_spread(self):
        s=tc.spread(1.0,1.02)
        self.assertAlmostEqual(s["pct_mid"],(0.02/1.01)*100)
        self.assertIsNone(tc.spread(None,1.0)["mid"])

    def test_buy_cost_walks_asks_and_marks_fees_excluded(self):
        r=tc.buy_cost([[1.0,100],[2.0,100]],150)
        self.assertTrue(r["complete"])
        self.assertAlmostEqual(r["qty_tel"],125)
        self.assertAlmostEqual(r["avg_price"],1.2)
        self.assertEqual(r["fees"],"EXCLUDED_NOT_VERIFIED")

    def test_partial_depth_is_not_reported_complete(self):
        r=tc.buy_cost([[1.0,10]],300)
        self.assertFalse(r["complete"])
        self.assertEqual(r["filled_usdt"],10)

    def test_tiny_partial_fill_is_not_hidden_by_an_absolute_tolerance(self):
        for partial, target in ((1e-8, 2e-8), (1e-13, 2e-13)):
            buy=tc.buy_cost([[1.0,partial]],target)
            self.assertFalse(buy["complete"])
            self.assertAlmostEqual(buy["filled_usdt"],partial)
            sell=tc.sell_proceeds([[1.0,partial]],target)
            self.assertFalse(sell["complete"])
            self.assertAlmostEqual(sell["filled_qty_tel"],partial)

    def test_relative_tolerance_covers_full_partial_and_tiny_buy_and_sell(self):
        cases=(
            ("full",50.0,50.0,True),
            ("partial",50.0,25.0,False),
            ("tiny-full",2e-8,2e-8,True),
            ("tiny-partial",2e-8,1e-8,False),
            ("infinitesimal-full",2e-13,2e-13,True),
            ("infinitesimal-partial",2e-13,1e-13,False),
        )
        for label,target,available,expected in cases:
            with self.subTest(label=label,side="buy"):
                self.assertEqual(tc.buy_cost([[1.0,available]],target)["complete"],expected)
            with self.subTest(label=label,side="sell"):
                self.assertEqual(tc.sell_proceeds([[1.0,available]],target)["complete"],expected)

    def test_recent_mexc_trade_order_is_sorted_by_timestamp(self):
        class C:
            venue="mexc"; symbol="TELUSDT"
            def __init__(self): self.log=[]
            def get(self,path,params=None):
                if path=="/api/v3/ticker/bookTicker": return {"bidPrice":"1","bidQty":"2","askPrice":"1.1","askQty":"3"}
                if path=="/api/v3/depth": return {"lastUpdateId":2,"bids":[["1","2"]],"asks":[["1.1","3"]]}
                if path=="/api/v3/trades": return [{"time":1000,"price":"1","qty":"1"},{"time":3000,"price":"1.1","qty":"1"}]
                if path=="/api/v3/time": return {"serverTime":4000}
        r=tc.fast(C())
        self.assertEqual(r["trades"][0]["time_ms"],3000)

    def test_missing_book_timestamp_never_claims_verified(self):
        obs=[{"book_age_ms":None,"book_hash":"same","book_sequence":5,"newest_trade_age_ms":1000},
             {"book_age_ms":None,"book_hash":"same","book_sequence":5,"newest_trade_age_ms":1000}]
        v=tc.verdict(obs,10,900)
        self.assertEqual(v["book"]["verdict"],"NON VÉRIFIÉ")

    def test_changed_book_without_timestamp_is_partial(self):
        obs=[{"book_age_ms":None,"book_hash":"a","book_sequence":5,"newest_trade_age_ms":1000},
             {"book_age_ms":None,"book_hash":"b","book_sequence":6,"newest_trade_age_ms":1000}]
        self.assertEqual(tc.verdict(obs,10,900)["book"]["verdict"],"PARTIEL")

    def test_stale_trade_not_verified(self):
        obs=[{"book_age_ms":None,"book_hash":"a","book_sequence":None,"newest_trade_age_ms":3600000}]
        self.assertEqual(tc.verdict(obs,10,900)["trades"]["verdict"],"NON VÉRIFIÉ")

    def test_kucoin_server_timestamp_is_unwrapped_integer(self):
        class C:
            venue = "kucoin"
            def get(self, path):
                self.path = path
                return 1792257123456
        c = C()
        self.assertEqual(tc.server_time(c), 1792257123456)
        self.assertEqual(c.path, "/api/v1/timestamp")

    def test_month_end(self):
        from datetime import datetime, timezone
        start=int(datetime(2026,9,1,tzinfo=timezone.utc).timestamp()*1000)
        end=int(datetime(2026,10,1,tzinfo=timezone.utc).timestamp()*1000)
        self.assertEqual(tc.month_end_ms(start),end)


    def test_book_verdict_uses_only_last_pass_timestamp(self):
        obs=[
            {"book_age_ms":1000,"book_hash":"a","book_sequence":1,"newest_trade_age_ms":1000},
            {"book_age_ms":None,"book_hash":"b","book_sequence":2,"newest_trade_age_ms":1000},
        ]
        self.assertEqual(tc.verdict(obs,10,900)["book"]["verdict"],"PARTIEL")

    def test_empty_or_one_sided_book_is_anomaly_not_crossed(self):
        self.assertIn("CARNET_VIDE", tc.book_anomalies([], [], None))
        one_sided=tc.book_anomalies([[1.0,2.0]], [], None)
        self.assertIn("CARNET_INCOMPLET", one_sided)
        self.assertNotIn("CARNET_CROISE", one_sided)

    def test_crossed_depth_book_detected_even_without_l1(self):
        anomalies=tc.book_anomalies([[1.1,2.0]], [[1.0,2.0]], None)
        self.assertIn("CARNET_CROISE", anomalies)
        self.assertIn("L1_ABSENT", anomalies)

    def test_quality_guard_detects_unsorted_order_book(self):
        quality = tc.validate_order_book([[1.0, 2.0], [1.1, 3.0]], [[1.2, 2.0], [1.3, 3.0]])
        self.assertEqual(quality["status"], "NON_VÉRIFIÉ")
        self.assertIn("BIDS_NOT_DESCENDING", quality["problems"])

    def test_quality_guard_does_not_call_identical_venue_values_corruption(self):
        diagnostic = tc.diagnose_identical_cross_venue_data(
            "MEXC:TELUSDT", {"mid": 1.0, "bid": 0.99, "ask": 1.01},
            "KUCOIN:TEL-USDT", {"mid": 1.0, "bid": 0.99, "ask": 1.01},
            ["mid", "bid", "ask"],
        )
        self.assertEqual(diagnostic["status"], "SUSPECT_IDENTIQUE")
        self.assertIn("ne prouvent pas", diagnostic["note"])


class RoundTripDiagnosticsTests(unittest.TestCase):
    def test_amounts_are_parametric_with_sensible_defaults(self):
        self.assertEqual(tc.normalize_amounts(None), [50.0, 100.0, 300.0, 500.0, 1000.0])
        self.assertEqual(tc.normalize_amounts("75, 250.5, 75"), [75.0, 250.5])
        with self.assertRaises(ValueError):
            tc.normalize_amounts("0,-5,abc")

    def test_round_trip_separates_spread_from_buy_and_sell_slippage(self):
        result = tc.round_trip_scenarios(
            [[0.99, 100], [0.89, 100]],
            [[1.0, 100], [1.1, 100]],
            [150],
        )
        scenario = result["scenarios"][0]
        self.assertEqual(scenario["execution_status"], "COMPLET")
        self.assertAlmostEqual(result["initial_spread"]["pct_mid"], (0.01 / 0.995) * 100)
        self.assertAlmostEqual(scenario["buy"]["slippage_vs_best_ask_pct"], 3.125)
        self.assertAlmostEqual(scenario["sell"]["slippage_vs_best_bid_pct"], (1 - 0.95875 / 0.99) * 100)
        self.assertAlmostEqual(scenario["round_trip"]["cost_pct"], (150 - 139.4545454545) / 150 * 100)
        self.assertFalse(scenario["round_trip"]["fees_verified"])
        self.assertIsNone(scenario["round_trip"]["fees_usdt"])

    def test_small_amount_is_complete_and_large_amount_is_not_extrapolated(self):
        result = tc.round_trip_scenarios([[1.0, 10]], [[1.01, 10]], [1, 1000])
        small, large = result["scenarios"]
        self.assertEqual(small["execution_status"], "COMPLET")
        self.assertTrue(small["depth_sufficient"])
        self.assertEqual(large["execution_status"], "PROFONDEUR_ACHAT_INSUFFISANTE")
        self.assertFalse(large["depth_sufficient"])
        self.assertIsNone(large["round_trip"])

    def test_one_sided_book_and_sell_depth_are_fail_closed(self):
        no_asks = tc.round_trip_scenarios([[1.0, 100]], [], [50])["scenarios"][0]
        self.assertEqual(no_asks["execution_status"], "PROFONDEUR_ACHAT_INSUFFISANTE")
        self.assertIsNone(no_asks["round_trip"])

        thin_bids = tc.round_trip_scenarios([[1.0, 1]], [[1.0, 1000]], [50])["scenarios"][0]
        self.assertEqual(thin_bids["execution_status"], "PROFONDEUR_VENTE_INSUFFISANTE")
        self.assertIsNone(thin_bids["round_trip"])

    def test_unverified_fees_are_never_applied(self):
        result = tc.round_trip_scenarios(
            [[1.0, 100]], [[1.01, 100]], [50], fees={"verified": False, "pct": 0.57}
        )
        scenario = result["scenarios"][0]
        self.assertFalse(result["fees"]["verified"])
        self.assertEqual(result["fees"]["provided_pct"], 0.57)
        self.assertIsNone(scenario["round_trip"]["fees_usdt"])
        self.assertIsNone(scenario["round_trip"]["net_cost_pct"])
        self.assertIn("non vérifiés", result["fees"]["note"])

    @staticmethod
    def _fee_claim(pct=0.1):
        return {"verified": True, "pct": pct, "value": None, "provenance": {
            "source": "exchange_fee_schedule",
            "source_url": "https://example.test/fees",
            "retrieved_at": "2026-10-23T00:00:00Z",
            "evidence_sha256": "a" * 64,
            "algorithm": "HMAC-SHA256",
            "key_id": "test-key-v1",
        }}

    def test_verified_fees_require_a_valid_hmac_provenance(self):
        key = "test-fees-secret"
        signed = tc.sign_fees_provenance(self._fee_claim(), key=key)
        with patch.dict(os.environ, {tc.FEES_PROVENANCE_ENV: key}):
            result = tc.round_trip_scenarios(
                [[1.0, 100]], [[1.01, 100]], [50], fees=signed
            )
        scenario = result["scenarios"][0]
        self.assertTrue(result["fees"]["verified"])
        self.assertEqual(result["fees"]["provenance_status"], "VERIFIED")
        self.assertIsNotNone(scenario["round_trip"]["fees_usdt"])
        self.assertGreater(scenario["round_trip"]["net_cost_pct"], scenario["round_trip"]["cost_pct"])

    def test_verified_fees_without_provenance_are_rejected(self):
        with patch.dict(os.environ, {tc.FEES_PROVENANCE_ENV: "test-fees-secret"}):
            result = tc.round_trip_scenarios(
                [[1.0, 100]], [[1.01, 100]], [50], fees={"verified": True, "pct": 0.1}
            )
        self.assertFalse(result["fees"]["verified"])
        self.assertEqual(result["fees"]["provenance_status"], "MISSING_PROVENANCE")
        self.assertIsNone(result["scenarios"][0]["round_trip"]["fees_usdt"])

    def test_verified_fees_with_incomplete_provenance_are_rejected(self):
        key = "test-fees-secret"
        claim = self._fee_claim()
        claim["provenance"].pop("source_url")
        signed = tc.sign_fees_provenance(claim, key=key)
        with patch.dict(os.environ, {tc.FEES_PROVENANCE_ENV: key}):
            result = tc.round_trip_scenarios(
                [[1.0, 100]], [[1.01, 100]], [50], fees=signed
            )
        self.assertFalse(result["fees"]["verified"])
        self.assertEqual(result["fees"]["provenance_status"], "INVALID_PROVENANCE")
        self.assertIsNone(result["scenarios"][0]["round_trip"]["fees_usdt"])

    def test_verified_fees_with_a_bad_signature_are_rejected(self):
        key = "test-fees-secret"
        signed = tc.sign_fees_provenance(self._fee_claim(), key=key)
        signed["provenance"]["signature"] = "0" * 64
        with patch.dict(os.environ, {tc.FEES_PROVENANCE_ENV: key}):
            result = tc.round_trip_scenarios(
                [[1.0, 100]], [[1.01, 100]], [50], fees=signed
            )
        self.assertFalse(result["fees"]["verified"])
        self.assertEqual(result["fees"]["provenance_status"], "INVALID_SIGNATURE")
        self.assertIsNone(result["scenarios"][0]["round_trip"]["fees_usdt"])

    def test_normalized_verified_fees_still_reverify(self):
        key = "test-fees-secret"
        signed = tc.sign_fees_provenance(self._fee_claim(), key=key)
        with patch.dict(os.environ, {tc.FEES_PROVENANCE_ENV: key}):
            normalized = tc.normalize_fees(signed)
            status = tc.verify_fees_provenance(normalized)
        self.assertTrue(normalized["verified"])
        self.assertEqual(normalized["pct_per_side"], 0.1)
        self.assertEqual(status, "VERIFIED")

    def test_verified_fees_with_modified_metadata_after_signing_are_rejected(self):
        key = "test-fees-secret"
        signed = tc.sign_fees_provenance(self._fee_claim(), key=key)
        signed["provenance"]["source_url"] = "https://evil.example/fees"
        with patch.dict(os.environ, {tc.FEES_PROVENANCE_ENV: key}):
            result = tc.round_trip_scenarios(
                [[1.0, 100]], [[1.01, 100]], [50], fees=signed
            )
        self.assertFalse(result["fees"]["verified"])
        self.assertEqual(result["fees"]["provenance_status"], "INVALID_SIGNATURE")
        self.assertIsNone(result["scenarios"][0]["round_trip"]["fees_usdt"])

    def test_verified_fees_with_conflicting_pct_fields_are_rejected(self):
        key = "test-fees-secret"
        signed = tc.sign_fees_provenance(self._fee_claim(), key=key)
        signed["pct_per_side"] = 0.01
        with patch.dict(os.environ, {tc.FEES_PROVENANCE_ENV: key}):
            result = tc.round_trip_scenarios(
                [[1.0, 100]], [[1.01, 100]], [50], fees=signed
            )
        self.assertFalse(result["fees"]["verified"])
        self.assertEqual(result["fees"]["provenance_status"], "INVALID_PCT")
        self.assertIsNone(result["scenarios"][0]["round_trip"]["fees_usdt"])

    def test_verified_fees_with_modified_pct_after_signing_are_rejected(self):
        key = "test-fees-secret"
        signed = tc.sign_fees_provenance(self._fee_claim(), key=key)
        signed["pct"] = 0.01
        with patch.dict(os.environ, {tc.FEES_PROVENANCE_ENV: key}):
            result = tc.round_trip_scenarios(
                [[1.0, 100]], [[1.01, 100]], [50], fees=signed
            )
        self.assertFalse(result["fees"]["verified"])
        self.assertEqual(result["fees"]["provenance_status"], "INVALID_SIGNATURE")
        self.assertIsNone(result["scenarios"][0]["round_trip"]["fees_usdt"])

    def test_verified_fees_require_the_trusted_key(self):
        signed = tc.sign_fees_provenance(self._fee_claim(), key="test-fees-secret")
        with patch.dict(os.environ, {tc.FEES_PROVENANCE_ENV: ""}):
            result = tc.round_trip_scenarios(
                [[1.0, 100]], [[1.01, 100]], [50], fees=signed
            )
        self.assertFalse(result["fees"]["verified"])
        self.assertEqual(result["fees"]["provenance_status"], "KEY_UNAVAILABLE")
        self.assertIsNone(result["scenarios"][0]["round_trip"]["fees_usdt"])

    def test_stale_or_untimestamped_books_produce_no_scenarios(self):
        stale = tc.liquidity_cost_report(
            [[1.0, 100]], [[1.01, 100]], [50], calculated_at_ms=30_000,
            book_source_time_ms=1_000, max_book_age_ms=10_000, book_verdict="VÉRIFIÉ",
        )
        self.assertFalse(stale["usable"])
        self.assertEqual(stale["reason"], "STALE_DATA")
        self.assertEqual(stale["scenarios"], [])

        unknown = tc.liquidity_cost_report(
            [[1.0, 100]], [[1.01, 100]], [50], calculated_at_ms=30_000,
            book_source_time_ms=None, max_book_age_ms=10_000, book_verdict="VÉRIFIÉ",
        )
        self.assertFalse(unknown["usable"])
        self.assertEqual(unknown["reason"], "AGE_DU_CARNET_INCONNU")
        self.assertEqual(unknown["scenarios"], [])

    def test_fresh_book_produces_scenarios_and_freshness(self):
        fresh = tc.liquidity_cost_report(
            [[1.0, 100]], [[1.01, 100]], [50, 300], calculated_at_ms=20_000,
            book_source_time_ms=19_500, max_book_age_ms=10_000, book_verdict="VÉRIFIÉ",
        )
        self.assertTrue(fresh["usable"])
        self.assertTrue(fresh["book"]["fresh"])
        self.assertEqual(len(fresh["scenarios"]), 2)
        self.assertFalse(fresh["fees"]["verified"])
        self.assertIn("coût réel", fresh["fees"]["note"])

    def test_publication_age_is_reported_without_inventing_freshness(self):
        report = tc.liquidity_cost_report(
            [[1.0, 100]], [[1.01, 100]], [50], calculated_at_ms=2_000,
            book_source_time_ms=1_000, max_book_age_ms=10_000, book_verdict="VÉRIFIÉ",
        )
        tc.annotate_liquidity_publication({"mexc": {"liquidity_cost": report}}, 20_000, 10_000)
        self.assertEqual(report["book"]["age_at_publication_ms"], 19_000)
        self.assertFalse(report["book"]["fresh_at_publication"])
        self.assertTrue(report["usable"], "la mesure reste valide à l'heure de calcul")
        self.assertFalse(report["usable_at_publication"])
        self.assertEqual(len(report["scenarios"]), 1)
        self.assertIn("périmé", report["publication_warning"])

    def test_publication_annotation_preserves_a_more_specific_failure(self):
        report = tc.liquidity_cost_report(
            [], [], [50], calculated_at_ms=2_000,
            book_source_time_ms=None, max_book_age_ms=10_000, book_verdict="NON VÉRIFIÉ",
        )
        self.assertEqual(report["reason"], "CARNET_VIDE")
        tc.annotate_liquidity_publication({"mexc": {"liquidity_cost": report}}, 20_000, 10_000)
        self.assertFalse(report["usable"])
        self.assertEqual(report["reason"], "CARNET_VIDE")
        self.assertIn("inconnu", report["publication_warning"])

    def test_spread_passes_and_percentiles_are_diagnostic_only(self):
        runs = [
            {"local_mid_ms": 1_000, "best": {"bid": 0.99, "ask": 1.01}},
            {"local_mid_ms": 4_000, "best": {"bid": 0.98, "ask": 1.02}},
            {"local_mid_ms": 7_000, "best": {"bid": 0.97, "ask": 1.03}},
        ]
        stats = tc.spread_passes(runs)
        self.assertEqual(stats["count"], 3)
        self.assertEqual(stats["valid_count"], 3)
        self.assertAlmostEqual(stats["median_pct"], tc.spread(0.98, 1.02)["pct_mid"])
        self.assertAlmostEqual(stats["min_pct"], tc.spread(0.99, 1.01)["pct_mid"])
        self.assertAlmostEqual(stats["max_pct"], tc.spread(0.97, 1.03)["pct_mid"])
        self.assertAlmostEqual(tc.percentile_rank([1, 2, 3, 4], 2.5), 50.0)

    def test_empty_book_is_explicitly_unusable(self):
        report = tc.liquidity_cost_report(
            [], [], [50], calculated_at_ms=2_000, book_source_time_ms=1_000,
            max_book_age_ms=10_000, book_verdict="VÉRIFIÉ",
        )
        self.assertFalse(report["usable"])
        self.assertEqual(report["reason"], "CARNET_VIDE")
        self.assertEqual(report["scenarios"], [])

    def _transport_source_report(self, run, log, max_book_age=10):
        class C:
            venue = "mexc"
        c = C()
        c.log = log
        with patch.object(tc, "fast", return_value=run), patch.object(tc, "candles", return_value={}):
            return tc.source_report(c, 300, 1, 0, max_book_age, 900, amounts=[50])

    @staticmethod
    def _empty_run(now):
        return {"server_time_ms": now, "local_mid_ms": now, "best": None,
                "bids": [], "asks": [], "sequence": None, "book_time_ms": None, "trades": []}

    def test_mexc_dns_resolution_is_explicit_and_fail_closed(self):
        now = tc.now_ms()
        report = self._transport_source_report(self._empty_run(now), [
            {"source": "mexc", "endpoint": "/api/v3/depth", "http_status": None,
             "error": "DNS_RESOLUTION", "error_detail": "getaddrinfo failed"},
        ])
        liquidity = report["liquidity_cost"]
        self.assertEqual(liquidity["reason"], "DNS_RESOLUTION")
        self.assertEqual(liquidity["transport_reason"], "DNS_RESOLUTION")
        self.assertFalse(liquidity["usable"])
        self.assertEqual(liquidity["scenarios"], [])
        self.assertIn("DNS", liquidity["reason_detail"])

    def test_mexc_http_error_is_explicit_and_fail_closed(self):
        now = tc.now_ms()
        report = self._transport_source_report(self._empty_run(now), [
            {"source": "mexc", "endpoint": "/api/v3/depth", "http_status": 503,
             "error": "HTTP_503"},
        ])
        liquidity = report["liquidity_cost"]
        self.assertEqual(liquidity["reason"], "HTTP_ERROR")
        self.assertEqual(liquidity["transport_reason"], "HTTP_ERROR")
        self.assertFalse(liquidity["usable"])
        self.assertEqual(liquidity["scenarios"], [])
        self.assertIn("HTTP", liquidity["reason_detail"])

    def test_mexc_network_timeout_is_not_misreported_as_empty_or_http(self):
        now = tc.now_ms()
        report = self._transport_source_report(self._empty_run(now), [
            {"source": "mexc", "endpoint": "/api/v3/depth", "http_status": None,
             "error": "TIMEOUT"},
        ])
        liquidity = report["liquidity_cost"]
        self.assertEqual(liquidity["reason"], "NETWORK_ERROR")
        self.assertEqual(liquidity["transport_reason"], "NETWORK_ERROR")
        self.assertFalse(liquidity["usable"])
        self.assertEqual(liquidity["scenarios"], [])

    def test_mexc_successful_empty_book_is_carnet_vide(self):
        now = tc.now_ms()
        report = self._transport_source_report(self._empty_run(now), [
            {"source": "mexc", "endpoint": "/api/v3/depth", "http_status": 200,
             "error": None},
        ])
        liquidity = report["liquidity_cost"]
        self.assertEqual(liquidity["reason"], "CARNET_VIDE")
        self.assertIsNone(liquidity["transport_reason"])
        self.assertFalse(liquidity["usable"])
        self.assertEqual(liquidity["scenarios"], [])

    def test_mexc_stale_book_is_stale_data(self):
        now = tc.now_ms()
        run = {"server_time_ms": now, "local_mid_ms": now,
               "best": {"bid": 1.0, "ask": 1.01, "last": 1.005},
               "bids": [[1.0, 1000]], "asks": [[1.01, 1000]],
               "sequence": 7, "book_time_ms": now - 20_000, "trades": []}
        report = self._transport_source_report(run, [
            {"source": "mexc", "endpoint": "/api/v3/depth", "http_status": 200,
             "error": None},
        ])
        liquidity = report["liquidity_cost"]
        self.assertEqual(liquidity["reason"], "STALE_DATA")
        self.assertIsNone(liquidity["transport_reason"])
        self.assertFalse(liquidity["usable"])
        self.assertEqual(liquidity["scenarios"], [])
        self.assertGreater(liquidity["book"]["age_at_calculation_ms"], 10_000)

    def test_source_report_keeps_legacy_buy_cost_and_adds_scenarios(self):
        now = tc.now_ms()
        run = {
            "server_time_ms": now,
            "local_mid_ms": now,
            "best": {"bid": 1.0, "ask": 1.01, "last": 1.005},
            "bids": [[1.0, 1000]], "asks": [[1.01, 1000]],
            "sequence": 7, "book_time_ms": now - 500, "trades": [],
        }

        class C:
            venue = "mexc"

        with patch.object(tc, "fast", return_value=run), patch.object(tc, "candles", return_value={}):
            report = tc.source_report(C(), 300, 1, 0, 10, 900, amounts=[50, 300])
        self.assertEqual(report["buy_cost_300_usdt"]["target_usdt"], 300)
        self.assertEqual(report["spread"]["pct_mid"], tc.spread(1.0, 1.01)["pct_mid"])
        self.assertEqual(report["spread_passes"]["count"], 1)
        self.assertTrue(report["liquidity_cost"]["usable"])
        self.assertFalse(report["liquidity_cost"]["fees"]["verified"])
        self.assertIsNone(report["liquidity_cost"]["scenarios"][0]["round_trip"]["fees_usdt"])
        self.assertEqual([s["amount_usdt"] for s in report["liquidity_cost"]["scenarios"]], [50.0, 300.0])


if __name__=="__main__": unittest.main(verbosity=2)
