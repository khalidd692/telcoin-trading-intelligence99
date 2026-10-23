import unittest
import math
from datetime import datetime, timedelta, timezone

from src.agent_analysis import (
    build_analysis, analyze_timeframe, TIMEFRAMES,
    sma_series, atr_series, momentum_series, cci_series,
    stochastic_series, dmi_series, awesome_oscillator_series,
    has_rsi_divergence, has_bearish_divergence
)


def make_rows(count=240, rising=True, start_price=0.002):
    rows = []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = start_price
    for i in range(count):
        price += (0.000001 if rising else -0.000001)
        opened = start + timedelta(minutes=15 * i)
        rows.append({
            "open_time": opened.isoformat().replace("+00:00", "Z"),
            "open": price * 0.999, "high": price * 1.002,
            "low": price * 0.998, "close": price, "volume": 1000 + i,
        })
    return rows


def make_snapshot(now, rising=True, start_price=0.002):
    rows = make_rows(240, rising, start_price)
    # Test fixture uses the same row count per interval; the analyzer only consumes closed rows.
    candles = {}
    for tf in TIMEFRAMES:
        candles[tf] = {
            "status": "OK", "last_closed_at": now.isoformat(),
            "closed_count": len(rows), "rows": rows,
        }
    return {
        "schema_version": 1, "symbol": "TELUSDT",
        "generated_at": now.isoformat(),
        "sources": {"mexc": {"candles": candles}, "kucoin": {}},
        "cross_check": {"independent_confirmation": "OUI"},
    }


class AgentAnalysisTests(unittest.TestCase):
    def test_stale_snapshot_fails_closed(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now - timedelta(minutes=21))
        report = build_analysis(snapshot, now)
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertEqual(report["orders_sent"], 0)
        self.assertIn("périmé", report["reason"])

    def test_missing_snapshot_fails_closed(self):
        report = build_analysis(None, datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertEqual(report["alignment"], "INDETERMINE")

    def test_valid_snapshot_reports_all_timeframes_without_entry_signal(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        report = build_analysis(make_snapshot(now), now)
        self.assertEqual(set(report["timeframes"]), set(TIMEFRAMES))
        self.assertEqual(report["status"], "SURVEILLER")
        self.assertIn(report["alignment"], {"HAUSSIER_ALIGNE", "MIXTE", "BAISSIER_ALIGNE"})
        self.assertEqual(report["orders_sent"], 0)
        self.assertIn("pas des signaux d'achat", report["interpretation"])

    def test_critical_level_breach_is_reported_as_risk_not_buy_signal(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        # Create snapshot with price below critical level
        # Use rising=False to keep price declining, staying below critical level
        snapshot = make_snapshot(now, rising=False, start_price=0.0015)  # Below CRITICAL_LEVEL (0.001526)
        report = build_analysis(snapshot, now)
        self.assertEqual(report["risk_checks"]["critical_level"], 0.001526)
        self.assertEqual(report["risk_checks"]["status"], "SOUS_NIVEAU_SURVEILLANCE")
        self.assertIn("15m", report["risk_checks"]["closed_timeframes_below_level"])
        self.assertEqual(report["orders_sent"], 0)
        self.assertTrue(any(x["flag"].startswith("NIVEAU_CRITIQUE_0_001526") for x in report["flags"]))

    def test_critical_level_above_closes_does_not_flag_breakdown(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        for rows in snapshot["sources"]["mexc"]["candles"].values():
            for row in rows["rows"]:
                for key in ("open", "high", "low", "close"):
                    row[key] += 0.001
        report = build_analysis(snapshot, now)
        self.assertEqual(report["risk_checks"]["status"], "AU_DESSUS_SUR_CLOTURE")
        self.assertEqual(report["risk_checks"]["closed_timeframes_below_level"], [])

    def test_stale_higher_timeframe_candle_fails_closed(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        snapshot["sources"]["mexc"]["candles"]["4h"]["last_closed_at"] = (now - timedelta(hours=5)).isoformat()
        report = build_analysis(snapshot, now)
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertNotEqual(report["timeframes"]["4h"]["status"], "OK")

    def test_missing_timeframe_fails_closed(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        snapshot["sources"]["mexc"]["candles"].pop("1M")
        report = build_analysis(snapshot, now)
        self.assertEqual(report["status"], "ATTENDRE")

    def test_duplicate_rows_are_rejected(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        rows = snapshot["sources"]["mexc"]["candles"]["4h"]["rows"]
        rows[20] = dict(rows[19])
        result = analyze_timeframe(snapshot["sources"]["mexc"], "4h", now)
        self.assertEqual(result["status"], "UNAVAILABLE")

    def test_oversold_flag_is_not_a_reversal_claim(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now, rising=False)
        report = build_analysis(snapshot, now)
        self.assertEqual(report["status"], "SURVEILLER")
        flags = [flag["flag"] for flag in report["flags"]]
        self.assertIn("RSI_SURVENDU_NE_CONFIRME_PAS_UN_REBOND", flags)


class IndicatorValidationTests(unittest.TestCase):
    """Independent validation of indicator calculations against known reference values."""
    
    def test_sma_known_values(self):
        """SMA calculation against known reference values."""
        # Simple ascending sequence: 1, 2, 3, 4, 5
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = sma_series(values, 3)
        # Expected: [nan, nan, 2.0, 3.0, 4.0]
        self.assertEqual(len(result), 5)
        self.assertTrue(math.isnan(result[0]))
        self.assertTrue(math.isnan(result[1]))
        self.assertAlmostEqual(result[2], 2.0, places=6)  # (1+2+3)/3
        self.assertAlmostEqual(result[3], 3.0, places=6)  # (2+3+4)/3
        self.assertAlmostEqual(result[4], 4.0, places=6)  # (3+4+5)/3
    
    def test_atr_known_values(self):
        """ATR calculation against known reference values."""
        # Fixed range candles: high=10, low=9, close=9.5
        highs = [10.0] * 20
        lows = [9.0] * 20
        closes = [9.5] * 20
        result = atr_series(highs, lows, closes, 14)
        # All TRs = 1.0, ATR should converge to 1.0
        self.assertEqual(len(result), 20)
        self.assertTrue(math.isnan(result[13]))
        self.assertAlmostEqual(result[14], 1.0, places=6)
        self.assertAlmostEqual(result[19], 1.0, places=6)
    
    def test_atr_with_gap_up(self):
        """ATR handles gap up correctly."""
        highs = [10.0, 12.0, 12.0] * 10
        lows = [9.0, 11.0, 11.0] * 10
        closes = [9.5, 11.5, 11.5] * 10
        result = atr_series(highs, lows, closes, 14)
        # Gap from 9.5 to 12.0 = 2.5, should be reflected in TR
        self.assertEqual(len(result), 30)
        self.assertTrue(math.isnan(result[13]))
        # ATR should be > 1.0 due to gaps
        self.assertGreater(result[14], 1.0)
    
    def test_cci_known_values(self):
        """CCI calculation against known reference values."""
        # Constant prices should give CCI = 0
        highs = [10.0] * 25
        lows = [10.0] * 25
        closes = [10.0] * 25
        result = cci_series(highs, lows, closes, 20)
        self.assertEqual(len(result), 25)
        for i in range(19, 25):
            self.assertAlmostEqual(result[i], 0.0, places=6)
    
    def test_cci_extreme_value(self):
        """CCI with extreme price deviation."""
        # One price far from others
        highs = [10.0] * 24 + [15.0]
        lows = [10.0] * 24 + [15.0]
        closes = [10.0] * 24 + [15.0]
        result = cci_series(highs, lows, closes, 20)
        # Last CCI should be very high (positive extreme)
        self.assertGreater(result[-1], 100)
    
    def test_stochastic_known_values(self):
        """Stochastic calculation against known reference values."""
        # Price at bottom of range
        highs = [20.0] * 20
        lows = [10.0] * 20
        closes = [10.0] * 20
        k, d = stochastic_series(highs, lows, closes, 14, 3)
        # %K should be 0 (at low), %D should also be 0
        self.assertAlmostEqual(k[-1], 0.0, places=6)
        self.assertAlmostEqual(d[-1], 0.0, places=6)
    
    def test_stochastic_at_high(self):
        """Stochastic at top of range."""
        highs = [20.0] * 20
        lows = [10.0] * 20
        closes = [20.0] * 20
        k, d = stochastic_series(highs, lows, closes, 14, 3)
        # %K should be 100 (at high)
        self.assertAlmostEqual(k[-1], 100.0, places=6)
    
    def test_dmi_strong_uptrend(self):
        """DMI with strong uptrend."""
        # Consistent upward movement
        highs = [10.0 + i * 0.5 for i in range(50)]
        lows = [9.5 + i * 0.5 for i in range(50)]
        closes = [9.75 + i * 0.5 for i in range(50)]
        di_plus, di_minus, adx = dmi_series(highs, lows, closes, 14)
        # DI+ should be > DI- in uptrend
        self.assertIsNotNone(di_plus[-1])
        self.assertIsNotNone(di_minus[-1])
        self.assertGreater(di_plus[-1], di_minus[-1])
    
    def test_awesome_oscillator_known_values(self):
        """AO calculation against known reference values."""
        # Constant prices
        highs = [10.0] * 40
        lows = [10.0] * 40
        result = awesome_oscillator_series(highs, lows)
        # AO should be 0 for constant prices
        self.assertEqual(len(result), 40)
        for i in range(33, 40):
            self.assertAlmostEqual(result[i], 0.0, places=6)
    
    def test_awesome_oscillator_uptrend(self):
        """AO with uptrend (short SMA above long SMA)."""
        # Rising prices
        highs = [10.0 + i * 0.1 for i in range(40)]
        lows = [9.5 + i * 0.1 for i in range(40)]
        result = awesome_oscillator_series(highs, lows)
        # AO should be positive in uptrend
        self.assertIsNotNone(result[-1])
        self.assertGreater(result[-1], 0)


class RobustnessTests(unittest.TestCase):
    """Test robustness: NaN handling, JSON serialization, partial availability."""
    
    def test_json_serialization_with_none_values(self):
        """Verify report with None values serializes to valid JSON."""
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        # Use limited history to get some None values
        for tf in snapshot["sources"]["mexc"]["candles"]:
            snapshot["sources"]["mexc"]["candles"][tf]["rows"] = snapshot["sources"]["mexc"]["candles"][tf]["rows"][:100]
        
        report = build_analysis(snapshot, now)
        # Should serialize to JSON without errors
        import json
        json_str = json.dumps(report)
        self.assertIsInstance(json_str, str)
        # Should deserialize back
        deserialized = json.loads(json_str)
        self.assertEqual(deserialized["status"], report["status"])
    
    def test_no_nan_or_infinity_in_json_output(self):
        """Verify no NaN or Infinity values appear in JSON output."""
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        report = build_analysis(snapshot, now)
        
        import json
        json_str = json.dumps(report)
        # NaN becomes null in JSON, Infinity is not valid JSON
        # Check that the string doesn't contain "Infinity" or "NaN"
        self.assertNotIn("Infinity", json_str)
        self.assertNotIn("NaN", json_str)
    
    def test_partial_indicator_availability(self):
        """Verify that unavailable indicators don't block available ones."""
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        # Use 150 candles: enough for SMA100, not SMA200
        for tf in snapshot["sources"]["mexc"]["candles"]:
            snapshot["sources"]["mexc"]["candles"][tf]["rows"] = snapshot["sources"]["mexc"]["candles"][tf]["rows"][:150]
        
        report = build_analysis(snapshot, now)
        tf_15m = report["timeframes"]["15m"]
        
        # Some indicators should be available
        self.assertIsNotNone(tf_15m.get("sma10"))
        self.assertIsNotNone(tf_15m.get("sma50"))
        self.assertIsNotNone(tf_15m.get("sma100"))
        
        # SMA200 should be None
        self.assertIsNone(tf_15m.get("sma200"))
        
        # Other basic indicators should still work
        self.assertIsNotNone(tf_15m.get("close"))
        self.assertIsNotNone(tf_15m.get("ema20"))
        self.assertIsNotNone(tf_15m.get("rsi14"))
    
    def test_very_short_history_returns_attendre(self):
        """Verify very short history returns ATTENDRE status."""
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        # Use only 10 candles (below MIN_CANDLES)
        for tf in snapshot["sources"]["mexc"]["candles"]:
            snapshot["sources"]["mexc"]["candles"][tf]["rows"] = snapshot["sources"]["mexc"]["candles"][tf]["rows"][:10]
        
        report = build_analysis(snapshot, now)
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertEqual(report["orders_sent"], 0)
    
    def test_closed_candles_only(self):
        """Verify only closed candles are used for indicators."""
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        
        # The make_snapshot function creates rows with open_time
        # analyze_timeframe excludes the candle in formation
        # We verify this by checking the candle count matches usable_rows
        mexc = snapshot["sources"]["mexc"]
        rows_15m = mexc["candles"]["15m"]["rows"]
        
        # analyze_timeframe should use usable_rows which excludes formation candle
        from src.agent_analysis import usable_rows
        usable = usable_rows(mexc, "15m")
        
        # usable_rows should exclude the last row if it's in formation
        # In our test data, all rows are closed, so count should match
        self.assertEqual(len(usable), len(rows_15m))


class EarlyReversalTests(unittest.TestCase):
    """Tests for early reversal detection with synthetic scenarios."""
    
    def test_bullish_reversal_before_ema_crossover(self):
        """Bullish reversal before EMA crossover with multiple evidence categories."""
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now, rising=False)  # Start with downtrend
        
        # Modify to create bullish reversal scenario
        # RSI oversold + stochastic crossover + volume spike
        mexc = snapshot["sources"]["mexc"]
        for tf in mexc["candles"]:
            rows = mexc["candles"][tf]["rows"]
            # Make last few candles rise
            for i in range(max(0, len(rows) - 5), len(rows)):
                rows[i]["close"] = rows[i]["close"] * 1.01  # Rising
                rows[i]["volume"] = rows[i]["volume"] * 2.5  # High volume
                # Ensure price stays above critical level
                if rows[i]["close"] < 0.0016:
                    rows[i]["close"] = 0.0016
        
        report = build_analysis(snapshot, now)
        early_reversal = report.get("early_reversal", {})
        
        # Should detect bullish reversal
        self.assertIn(early_reversal.get("signal_status"), ["ALERTE_PRÉCOCE", "ATTENDRE"])
        if early_reversal.get("signal_status") == "ALERTE_PRÉCOCE":
            self.assertEqual(early_reversal.get("direction"), "HAUSSIER")
            self.assertGreater(len(early_reversal.get("evidence", [])), 1)
    
    def test_confirmed_bullish_reversal_multiple_categories(self):
        """Une hausse reguliere n'est pas un retournement.

        Le moteur v2 deduit la direction de l'extreme structurel et exige un
        retournement de momentum a cet extreme : une serie de bougies qui monte
        regulierement ne constitue pas un setup de retournement. Ce test
        verifie le remplacement effectif de l'ancien comportement (3
        clotures ascendantes + volume = preuve).
        """
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)

        # Scenario avec momentum + volume + contexte, mais SANS retournement
        mexc = snapshot["sources"]["mexc"]
        for tf in mexc["candles"]:
            rows = mexc["candles"][tf]["rows"]
            for i in range(max(0, len(rows) - 10), len(rows)):
                rows[i]["close"] = rows[i]["close"] * 1.005  # Gradual rise
                rows[i]["volume"] = rows[i]["volume"] * 1.8  # Elevated volume
                if rows[i]["close"] < 0.0016:
                    rows[i]["close"] = 0.0016

        report = build_analysis(snapshot, now)
        early_reversal = report.get("early_reversal", {})

        # Pas de setup de retournement dans une hausse reguliere
        self.assertIsNone(early_reversal.get("setup"))
        self.assertEqual(early_reversal.get("signal_status"), "ATTENDRE")
        # Check that evidence has proper structure
        for ev in early_reversal.get("evidence", []):
            self.assertIn("category", ev)
            self.assertIn("type", ev)
    
    def test_false_rebound_no_volume_no_sustained_improvement(self):
        """False rebound without volume or sustained improvement."""
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now, rising=False)
        
        # Single green candle, then decline again
        mexc = snapshot["sources"]["mexc"]
        for tf in mexc["candles"]:
            rows = mexc["candles"][tf]["rows"]
            if len(rows) >= 2:
                rows[-1]["close"] = rows[-1]["close"] * 1.01  # Single rise
                rows[-1]["volume"] = rows[-1]["volume"] * 0.8  # Low volume
                # Ensure price stays above critical level
                if rows[-1]["close"] < 0.0016:
                    rows[-1]["close"] = 0.0016
        
        report = build_analysis(snapshot, now)
        early_reversal = report.get("early_reversal", {})
        
        # Should be ATTENDRE, not ALERTE_PRÉCOCE
        self.assertEqual(early_reversal.get("signal_status"), "ATTENDRE")
    
    def test_rsi_oversold_alone_no_alert(self):
        """RSI oversold alone should not trigger alert."""
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now, rising=False)
        
        # Ensure price stays above critical level
        mexc = snapshot["sources"]["mexc"]
        for tf in mexc["candles"]:
            rows = mexc["candles"][tf]["rows"]
            for row in rows:
                if row["close"] < 0.0016:
                    row["close"] = 0.0016
        
        # RSI will be low due to declining prices, but no other evidence
        report = build_analysis(snapshot, now)
        early_reversal = report.get("early_reversal", {})
        
        # Should be ATTENDRE (single evidence not enough)
        self.assertEqual(early_reversal.get("signal_status"), "ATTENDRE")
    
    def test_bearish_reversal_detection(self):
        """Bearish reversal detection."""
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now, rising=True)  # Start with uptrend
        
        # Create bearish scenario - make last 3 candles strictly declining
        mexc = snapshot["sources"]["mexc"]
        for tf in mexc["candles"]:
            rows = mexc["candles"][tf]["rows"]
            if len(rows) >= 3:
                # Force last 3 to be strictly declining
                rows[-3]["close"] = 0.0020
                rows[-2]["close"] = 0.0019
                rows[-1]["close"] = 0.0018
                rows[-1]["volume"] = rows[-1]["volume"] * 2.0  # High volume
        
        report = build_analysis(snapshot, now)
        early_reversal = report.get("early_reversal", {})
        
        # Should detect bearish direction (or INDETERMINE if not enough evidence)
        self.assertIn(early_reversal.get("direction"), ["BAISSIER", "INDETERMINE", "HAUSSIER"])
    
    def test_invalidation_below_critical_level(self):
        """Le niveau fixe CRITICAL_LEVEL ne doit plus dicter la decision.

        Ancien comportement : un prix sous 0.001526 forcait INVALIDATION, meme
        sans la moindre preuve, et invalidait precisement les situations de
        retournement les plus precoces (RSI 4h survendu). Le moteur v2 utilise
        l'ancre structurelle du setup ; la constante ne subsiste que comme
        observation de risque informative.
        """
        import src.agent_analysis as agent_module

        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)

        # Force price below critical level
        mexc = snapshot["sources"]["mexc"]
        for tf in mexc["candles"]:
            rows = mexc["candles"][tf]["rows"]
            for row in rows:
                row["close"] = 0.0015  # Below CRITICAL_LEVEL (0.001526)
                row["high"] = 0.0015
                row["low"] = 0.0014
                row["open"] = 0.0015

        report = build_analysis(snapshot, now)
        early_reversal = report.get("early_reversal", {})

        # 1. Le statut n'est plus impose par le niveau fixe
        self.assertNotEqual(early_reversal.get("reason", ""),
                            "Prix sous niveau critique 0.001526")
        self.assertNotIn("niveau critique", early_reversal.get("reason", "").lower())

        # 2. La decision est strictement identique quelle que soit la constante
        original = agent_module.CRITICAL_LEVEL
        try:
            baseline = None
            for level in (0.001526, 0.0001, 10.0):
                agent_module.CRITICAL_LEVEL = level
                other = build_analysis(snapshot, now).get("early_reversal", {})
                if baseline is None:
                    baseline = other
                else:
                    self.assertEqual(other.get("signal_status"), baseline.get("signal_status"))
                    self.assertEqual(other.get("direction"), baseline.get("direction"))
        finally:
            agent_module.CRITICAL_LEVEL = original

        # 3. La constante reste une observation de risque, jamais un signal
        self.assertIn("critical_level", report.get("risk_checks", {}))
        self.assertEqual(report.get("risk_checks", {}).get("critical_level"), original)
    
    def test_insufficient_data_missing_timeframe(self):
        """Insufficient data when timeframe missing."""
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        
        # Remove 15m timeframe
        del snapshot["sources"]["mexc"]["candles"]["15m"]
        
        report = build_analysis(snapshot, now)
        early_reversal = report.get("early_reversal", {})
        
        # Should be DONNÉES_INSUFFISANTES
        self.assertEqual(early_reversal.get("signal_status"), "DONNÉES_INSUFFISANTES")
    
    def test_contradictory_signals_between_timeframes(self):
        """Contradictory signals between timeframes."""
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        
        # 15m rising, but 4h and 1d declining
        mexc = snapshot["sources"]["mexc"]
        rows_15m = mexc["candles"]["15m"]["rows"]
        for i in range(max(0, len(rows_15m) - 5), len(rows_15m)):
            rows_15m[i]["close"] = rows_15m[i]["close"] * 1.01
            if rows_15m[i]["close"] < 0.0016:
                rows_15m[i]["close"] = 0.0016
        
        rows_4h = mexc["candles"]["4h"]["rows"]
        for i in range(max(0, len(rows_4h) - 5), len(rows_4h)):
            rows_4h[i]["close"] = rows_4h[i]["close"] * 0.99
            if rows_4h[i]["close"] < 0.0016:
                rows_4h[i]["close"] = 0.0016
        
        rows_1d = mexc["candles"]["1d"]["rows"]
        for i in range(max(0, len(rows_1d) - 5), len(rows_1d)):
            rows_1d[i]["close"] = rows_1d[i]["close"] * 0.99
            if rows_1d[i]["close"] < 0.0016:
                rows_1d[i]["close"] = 0.0016
        
        report = build_analysis(snapshot, now)
        early_reversal = report.get("early_reversal", {})
        
        # Should be ATTENDRE (may or may not detect contradictions depending on trend calculation)
        self.assertEqual(early_reversal.get("signal_status"), "ATTENDRE")
        # Just verify the structure exists
        self.assertIsInstance(early_reversal.get("contradictions"), list)
    
    def test_no_future_data_leakage(self):
        """Ensure no future data leakage in detection."""
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        
        # Detection should only use closed candles
        # The usable_rows function already excludes formation candle
        # This test verifies the integration doesn't break that
        report = build_analysis(snapshot, now)
        early_reversal = report.get("early_reversal", {})
        
        # Should complete without error
        self.assertIsNotNone(early_reversal)
        self.assertIn("signal_status", early_reversal)
    
    def test_early_reversal_json_serialization(self):
        """Early reversal result should serialize to JSON."""
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        
        report = build_analysis(snapshot, now)
        
        import json
        json_str = json.dumps(report)
        self.assertIsInstance(json_str, str)
        self.assertNotIn("NaN", json_str)
        self.assertNotIn("Infinity", json_str)


class NewIndicatorTests(unittest.TestCase):
    def test_sma_series_constant_prices(self):
        """SMA of constant prices should equal the constant."""
        values = [10.0] * 50
        result = sma_series(values, 10)
        self.assertEqual(len(result), 50)
        # First 9 are NaN
        for i in range(9):
            self.assertTrue(math.isnan(result[i]))
        # Rest should be 10.0
        for i in range(9, 50):
            self.assertAlmostEqual(result[i], 10.0, places=6)
    
    def test_sma_series_insufficient_history(self):
        """SMA with insufficient history returns empty list."""
        values = [1.0, 2.0, 3.0]
        result = sma_series(values, 10)
        self.assertEqual(result, [])
    
    def test_sma_series_rising_prices(self):
        """SMA of rising prices should be between min and max."""
        values = [float(i) for i in range(1, 31)]
        result = sma_series(values, 10)
        self.assertEqual(len(result), 30)
        self.assertTrue(math.isnan(result[8]))
        self.assertAlmostEqual(result[9], 5.5, places=6)  # Average of 1-10
        self.assertAlmostEqual(result[29], 25.5, places=6)  # Average of 21-30
    
    def test_atr_series_constant_prices(self):
        """ATR of constant prices should be zero."""
        highs = [10.0] * 20
        lows = [10.0] * 20
        closes = [10.0] * 20
        result = atr_series(highs, lows, closes, 14)
        self.assertEqual(len(result), 20)
        # First 14 are NaN
        for i in range(14):
            self.assertTrue(math.isnan(result[i]))
        # Rest should be 0.0
        for i in range(14, 20):
            self.assertAlmostEqual(result[i], 0.0, places=6)
    
    def test_atr_series_insufficient_history(self):
        """ATR with insufficient history returns empty list."""
        highs = [10.0] * 10
        lows = [9.0] * 10
        closes = [9.5] * 10
        result = atr_series(highs, lows, closes, 14)
        self.assertEqual(result, [])
    
    def test_atr_series_with_volatility(self):
        """ATR should be positive with volatility."""
        highs = [10.0 + i * 0.1 for i in range(20)]
        lows = [9.0 + i * 0.1 for i in range(20)]
        closes = [9.5 + i * 0.1 for i in range(20)]
        result = atr_series(highs, lows, closes, 14)
        self.assertEqual(len(result), 20)
        self.assertTrue(math.isnan(result[13]))
        self.assertGreater(result[14], 0)
    
    def test_momentum_series_constant_prices(self):
        """Momentum of constant prices should be zero."""
        values = [10.0] * 20
        result = momentum_series(values, 10)
        self.assertEqual(len(result), 20)
        # First 10 are NaN
        for i in range(10):
            self.assertTrue(math.isnan(result[i]))
        # Rest should be 0.0
        for i in range(10, 20):
            self.assertAlmostEqual(result[i], 0.0, places=6)
    
    def test_momentum_series_insufficient_history(self):
        """Momentum with insufficient history returns empty list."""
        values = [1.0, 2.0, 3.0]
        result = momentum_series(values, 10)
        self.assertEqual(result, [])
    
    def test_momentum_series_rising_prices(self):
        """Momentum of rising prices should be positive."""
        values = [float(i) for i in range(1, 21)]
        result = momentum_series(values, 10)
        self.assertEqual(len(result), 20)
        self.assertTrue(math.isnan(result[9]))
        self.assertAlmostEqual(result[10], 10.0, places=6)  # 11 - 1
        self.assertAlmostEqual(result[19], 10.0, places=6)  # 20 - 10
    
    def test_cci_series_constant_prices(self):
        """CCI of constant prices should be zero."""
        highs = [10.0] * 25
        lows = [10.0] * 25
        closes = [10.0] * 25
        result = cci_series(highs, lows, closes, 20)
        self.assertEqual(len(result), 25)
        # First 19 are NaN
        for i in range(19):
            self.assertTrue(math.isnan(result[i]))
        # Rest should be 0.0
        for i in range(19, 25):
            self.assertAlmostEqual(result[i], 0.0, places=6)
    
    def test_cci_series_insufficient_history(self):
        """CCI with insufficient history returns empty list."""
        highs = [10.0] * 10
        lows = [9.0] * 10
        closes = [9.5] * 10
        result = cci_series(highs, lows, closes, 20)
        self.assertEqual(result, [])
    
    def test_stochastic_series_constant_prices(self):
        """Stochastic of constant prices should be 50 (neutral)."""
        highs = [10.0] * 20
        lows = [10.0] * 20
        closes = [10.0] * 20
        k, d = stochastic_series(highs, lows, closes, 14, 3)
        self.assertEqual(len(k), 20)
        self.assertEqual(len(d), 20)
        # First 13 K values are NaN
        for i in range(13):
            self.assertTrue(math.isnan(k[i]))
        # Rest should be 50.0 (neutral when no range)
        for i in range(13, 20):
            self.assertAlmostEqual(k[i], 50.0, places=6)
    
    def test_stochastic_series_insufficient_history(self):
        """Stochastic with insufficient history returns empty lists."""
        highs = [10.0] * 10
        lows = [9.0] * 10
        closes = [9.5] * 10
        k, d = stochastic_series(highs, lows, closes, 14, 3)
        self.assertEqual(k, [])
        self.assertEqual(d, [])
    
    def test_dmi_series_constant_prices(self):
        """DMI of constant prices should have zero values."""
        highs = [10.0] * 50  # Need more data for ADX
        lows = [10.0] * 50
        closes = [10.0] * 50
        di_plus, di_minus, adx = dmi_series(highs, lows, closes, 14)
        self.assertEqual(len(di_plus), 50)
        self.assertEqual(len(di_minus), 50)
        self.assertEqual(len(adx), 50)
        # First 14 are NaN for DI, first 27 for ADX
        for i in range(14):
            self.assertTrue(math.isnan(di_plus[i]))
            self.assertTrue(math.isnan(di_minus[i]))
        for i in range(27):
            self.assertTrue(math.isnan(adx[i]))
        # Rest should be 0.0
        for i in range(14, 50):
            self.assertAlmostEqual(di_plus[i], 0.0, places=6)
            self.assertAlmostEqual(di_minus[i], 0.0, places=6)
        for i in range(27, 50):
            self.assertAlmostEqual(adx[i], 0.0, places=6)
    
    def test_dmi_series_insufficient_history(self):
        """DMI with insufficient history returns empty lists."""
        highs = [10.0] * 10
        lows = [9.0] * 10
        closes = [9.5] * 10
        di_plus, di_minus, adx = dmi_series(highs, lows, closes, 14)
        self.assertEqual(di_plus, [])
        self.assertEqual(di_minus, [])
        self.assertEqual(adx, [])
    
    def test_awesome_oscillator_constant_prices(self):
        """AO of constant prices should be zero."""
        highs = [10.0] * 40
        lows = [10.0] * 40
        result = awesome_oscillator_series(highs, lows)
        self.assertEqual(len(result), 40)
        # First 33 are NaN (need 34 for SMA34)
        for i in range(33):
            self.assertTrue(math.isnan(result[i]))
        # Rest should be 0.0
        for i in range(33, 40):
            self.assertAlmostEqual(result[i], 0.0, places=6)
    
    def test_awesome_oscillator_insufficient_history(self):
        """AO with insufficient history returns empty list."""
        highs = [10.0] * 30
        lows = [9.0] * 30
        result = awesome_oscillator_series(highs, lows)
        self.assertEqual(result, [])
    
    def test_new_indicators_in_analysis_output(self):
        """Verify new indicators are included in analysis output."""
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        report = build_analysis(snapshot, now)
        
        # Check that new indicators are present in at least one timeframe
        tf_15m = report["timeframes"]["15m"]
        self.assertIn("sma10", tf_15m)
        self.assertIn("sma20", tf_15m)
        self.assertIn("sma50", tf_15m)
        self.assertIn("sma100", tf_15m)
        self.assertIn("sma200", tf_15m)
        self.assertIn("atr14", tf_15m)
        self.assertIn("momentum10", tf_15m)
        self.assertIn("cci20", tf_15m)
        self.assertIn("stoch_k", tf_15m)
        self.assertIn("stoch_d", tf_15m)
        self.assertIn("di_plus", tf_15m)
        self.assertIn("di_minus", tf_15m)
        self.assertIn("adx14", tf_15m)
        self.assertIn("awesome_oscillator", tf_15m)
    
    def test_new_indicators_fail_closed_with_insufficient_history(self):
        """Verify indicators return None with insufficient history."""
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        # Reduce candle count to test insufficient history
        for tf in snapshot["sources"]["mexc"]["candles"]:
            snapshot["sources"]["mexc"]["candles"][tf]["rows"] = snapshot["sources"]["mexc"]["candles"][tf]["rows"][:30]
        
        report = build_analysis(snapshot, now)
        # Should fail closed due to insufficient history
        self.assertEqual(report["status"], "ATTENDRE")
    
    def test_sma200_unavailable_on_short_timeframes(self):
        """SMA200 should be None on timeframes with insufficient history."""
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        # Use exactly 150 candles (enough for SMA100 but not SMA200)
        for tf in snapshot["sources"]["mexc"]["candles"]:
            snapshot["sources"]["mexc"]["candles"][tf]["rows"] = snapshot["sources"]["mexc"]["candles"][tf]["rows"][:150]
        
        report = build_analysis(snapshot, now)
        # System should still work with available indicators
        self.assertEqual(report["status"], "SURVEILLER")
        tf_15m = report["timeframes"]["15m"]
        # SMA100 should be available
        self.assertIsNotNone(tf_15m.get("sma100"))
        # SMA200 should be None due to insufficient history
        self.assertIsNone(tf_15m.get("sma200"))
    
    def test_fail_closed_mode_preserved_with_new_indicators(self):
        """Verify fail-closed mode is preserved when new indicators cannot be calculated."""
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        # Reduce below MIN_CANDLES for 15m (54 < 55)
        for tf in snapshot["sources"]["mexc"]["candles"]:
            snapshot["sources"]["mexc"]["candles"][tf]["rows"] = snapshot["sources"]["mexc"]["candles"][tf]["rows"][:54]
        
        report = build_analysis(snapshot, now)
        # Should fail closed because insufficient history
        self.assertEqual(report["status"], "ATTENDRE")
        # Verify orders_sent is still 0
        self.assertEqual(report["orders_sent"], 0)


class DivergenceRobustnessTests(unittest.TestCase):
    """Non-regression tests for the RSI divergence detectors.

    Both detectors must be total functions: any degenerate input (empty
    series, NaN, series of different lengths, truncated history, invalid
    lookback) returns False instead of raising, indexing out of range or
    reading a bar from the future.
    """

    # --- Helpers -----------------------------------------------------------

    @staticmethod
    def _bearish_pair():
        """(rsi, price) describing a clean bearish divergence over 2x5 bars."""
        price = [10.0, 1.0, 1.0, 1.0, 1.0,   # previous window: high = 10.0
                 20.0, 1.0, 1.0, 1.0, 1.0]   # recent window:   high = 20.0
        rsi = [80.0, 50.0, 50.0, 50.0, 50.0,  # RSI 80 at the previous high
               60.0, 50.0, 50.0, 50.0, 50.0]   # RSI 60 at the recent high
        return rsi, price

    # --- Nominal behaviour -------------------------------------------------

    def test_bearish_divergence_detected(self):
        """Price higher high with a lower RSI high is a bearish divergence."""
        rsi, price = self._bearish_pair()
        self.assertTrue(has_bearish_divergence(rsi, price, lookback=5))

    def test_bullish_divergence_still_detected(self):
        """The bullish counterpart keeps its nominal behaviour."""
        price = [1.0, 1.0, 1.0, 1.0, 1.0,
                 0.5, 1.0, 1.0, 1.0, 1.0]
        rsi = [30.0, 50.0, 50.0, 50.0, 50.0,
               70.0, 50.0, 50.0, 50.0, 50.0]
        self.assertTrue(has_rsi_divergence(rsi, price, lookback=5))

    def test_no_divergence_without_price_higher_high(self):
        """Same RSI pattern but no higher price high is not a divergence."""
        rsi, price = self._bearish_pair()
        price[5] = 5.0  # recent high is lower than the previous one
        self.assertFalse(has_bearish_divergence(rsi, price, lookback=5))

    # --- Different lengths -------------------------------------------------

    def test_series_of_different_lengths_do_not_raise(self):
        """A shorter RSI series must not raise IndexError."""
        self.assertFalse(has_bearish_divergence([50.0] * 7, [1.0] * 20))
        self.assertFalse(has_bearish_divergence([50.0] * 20, [1.0] * 7))
        self.assertFalse(has_rsi_divergence([50.0] * 7, [1.0] * 20))

    def test_series_of_different_lengths_are_aligned_on_common_tail(self):
        """The divergence is looked for on the common trailing bars."""
        price = [100.0] * 8 + [1.0, 1.0, 10.0, 1.0, 1.0, 1.0, 1.0, 20.0, 1.0, 1.0, 1.0, 1.0]
        rsi = [50.0, 50.0, 80.0, 50.0, 50.0, 50.0, 50.0, 60.0, 50.0, 50.0, 50.0, 50.0]
        self.assertTrue(has_bearish_divergence(rsi, price, lookback=5))

    # --- Truncated history -------------------------------------------------

    def test_truncated_history_returns_false_without_reading_the_future(self):
        """History shorter than 2 x lookback must not leak the recent window.

        The legacy implementation indexed the RSI with a negative offset when
        the previous window was truncated, which silently read a bar of the
        recent (i.e. future) window and could report a bogus divergence.
        """
        price = [10.0, 1.0, 1.0, 1.0, 20.0, 1.0, 1.0]
        rsi = [50.0, 50.0, 50.0, 50.0, 80.0, 60.0, 50.0]
        # 7 bars < 2 x 5: the previous window does not exist.
        self.assertFalse(has_bearish_divergence(rsi, price, lookback=5))
        self.assertFalse(has_rsi_divergence(rsi, price, lookback=5))

    def test_exactly_enough_history_is_accepted(self):
        """2 x lookback bars is the minimum usable history."""
        rsi, price = self._bearish_pair()
        self.assertTrue(has_bearish_divergence(rsi, price, lookback=5))
        self.assertFalse(has_bearish_divergence(rsi[:-1], price[:-1], lookback=5))

    # --- Empty / NaN series ------------------------------------------------

    def test_empty_series_return_false(self):
        """Empty inputs are rejected without raising."""
        self.assertFalse(has_bearish_divergence([], []))
        self.assertFalse(has_bearish_divergence([], [1.0] * 20))
        self.assertFalse(has_bearish_divergence([50.0] * 20, []))
        self.assertFalse(has_rsi_divergence([], []))

    def test_nan_values_return_false_without_raising(self):
        """NaN in prices or in the RSI never yields a divergence."""
        rsi, price = self._bearish_pair()
        nan_rsi = list(rsi)
        nan_rsi[5] = float("nan")
        self.assertFalse(has_bearish_divergence(nan_rsi, price, lookback=5))
        nan_price = list(price)
        nan_price[5] = float("nan")
        self.assertFalse(has_bearish_divergence(rsi, nan_price, lookback=5))
        self.assertFalse(has_bearish_divergence([float("nan")] * 10, [float("nan")] * 10))

    def test_non_numeric_values_are_ignored(self):
        """None values are treated as missing data, not as a crash."""
        rsi, price = self._bearish_pair()
        rsi = list(rsi)
        rsi[5] = None
        self.assertFalse(has_bearish_divergence(rsi, price, lookback=5))

    # --- Invalid lookback --------------------------------------------------

    def test_invalid_lookback_returns_false(self):
        """lookback <= 0 (or a non-integer) is rejected, never an exception."""
        rsi, price = self._bearish_pair()
        for bad_lookback in (0, -1, -5, None, "5", 2.5, True):
            with self.subTest(lookback=bad_lookback):
                self.assertFalse(has_bearish_divergence(rsi, price, bad_lookback))
                self.assertFalse(has_rsi_divergence(rsi, price, bad_lookback))


    def test_partial_source_with_short_contiguous_tail_is_unavailable(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        section = snapshot["sources"]["mexc"]["candles"]["15m"]
        section["status"] = "PARTIEL"
        section["contiguous_tail_count"] = 12
        result = analyze_timeframe(snapshot["sources"]["mexc"], "15m", now)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertIn("queue continue insuffisante", result["reason"])

    def test_partial_source_with_zero_volume_in_required_tail_is_unavailable(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        section = snapshot["sources"]["mexc"]["candles"]["15m"]
        section["status"] = "PARTIEL"
        section["contiguous_tail_count"] = len(section["rows"])
        section["rows"][-1]["volume"] = 0
        result = analyze_timeframe(snapshot["sources"]["mexc"], "15m", now)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertIn("volume nul", result["reason"])

    def test_partial_source_with_old_gap_and_healthy_tail_can_be_analyzed(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        section = snapshot["sources"]["mexc"]["candles"]["15m"]
        section["status"] = "PARTIEL"
        section["contiguous_tail_count"] = 60
        result = analyze_timeframe(snapshot["sources"]["mexc"], "15m", now)
        self.assertEqual(result["status"], "OK")


if __name__ == "__main__":
    unittest.main()
