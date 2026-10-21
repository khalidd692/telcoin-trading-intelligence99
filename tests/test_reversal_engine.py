"""
Tests unitaires du moteur de retournement v2 (src/agent_analysis.py).

Couverture demandee :
  - transitions ALERTE_PRÉCOCE -> CONFIRMATION -> INVALIDATION ;
  - independance de la decision vis-a-vis du niveau fixe CRITICAL_LEVEL ;
  - absence de fuite temporelle ;
  - bougies clôturees et donnees incompletes ;
  - figures de bougies ;
  - cas limites, donnees manquantes et contradictions ;
  - reproductibilite.

Stdlib uniquement (contrainte CI : aucun requirements.txt).
"""

import math
import unittest

import src.agent_analysis as agent
from src.agent_analysis import (
    REVERSAL_PARAMS,
    detect_early_reversal,
    has_hammer_pattern,
)


def make_state(status="OK", rsi=None, macd=None, macd_prev=None, atr=None,
               trend="MIXTE", candle_count=120, adx=None):
    return {
        "status": status, "reason": None, "candle_count": candle_count,
        "last_closed_at": "2026-10-20T00:00:00+00:00", "candle_age_seconds": 0,
        "close": 0.002, "ema20": 0.002, "ema50": 0.002,
        "sma10": 0.002, "sma20": 0.002, "sma50": 0.002, "sma100": 0.002, "sma200": None,
        "rsi14": rsi, "macd_histogram": macd, "macd_histogram_previous": macd_prev,
        "atr14": atr, "momentum10": None, "cci20": None,
        "stoch_k": None, "stoch_d": None,
        "di_plus": None, "di_minus": None, "adx14": adx, "awesome_oscillator": None,
        "volume_last": 1000, "volume_mean20": 1000, "volume_ratio_20": 1.0,
        "trend": trend, "flags": [],
    }


def timeframes(**overrides):
    base = {
        "15m": make_state(rsi=40.0, macd=0.00001, macd_prev=0.000005, atr=0.00002),
        "1h": make_state(rsi=45.0, macd=0.00001, macd_prev=0.00002, atr=0.00005),
        "4h": make_state(rsi=28.0, macd=-0.0001, macd_prev=-0.0002, atr=0.0002, adx=15.0),
        "1d": make_state(rsi=30.0, macd=-0.0002, macd_prev=-0.0003, atr=0.0005, adx=18.0),
        "1w": make_state(rsi=35.0, macd=0.0, macd_prev=0.0, atr=0.002, adx=12.0),
        "1M": make_state(status="PARTIEL", rsi=40.0, atr=0.004, trend="INDETERMINE"),
    }
    base.update(overrides)
    return base


def build_series(closes, highs=None, lows=None, opens=None, volumes=None,
                 rsi=None, macd=None):
    """Assemble des series coherentes et alignees (une entree par bougie)."""
    count = len(closes)
    highs = list(highs) if highs else [c * 1.002 for c in closes]
    lows = list(lows) if lows else [c * 0.998 for c in closes]
    opens = list(opens) if opens else list(closes)
    volumes = list(volumes) if volumes else [1000.0] * count
    if rsi is None:
        rsi = [50.0] * count
    if macd is None:
        macd = [0.0] * count
    ohlc = [(opens[i], highs[i], lows[i], closes[i], volumes[i]) for i in range(count)]
    return {"closes": closes, "rsi": rsi, "macd": macd, "ohlc": ohlc}


def declining_then_low(count=40, start=0.0020, step=0.00001):
    """Serie en baisse, la derniere bougie fait le plus bas."""
    closes = [start - step * i for i in range(count)]
    return closes


def rising_macd(count=40, last_rising=3):
    """Histogramme MACD en baisse puis en hausse sur les dernieres barres."""
    macd = [-0.0001 * (count - i) for i in range(count)]
    for k in range(last_rising):
        macd[count - last_rising + k] = 0.00001 * (k + 1)
    return macd


def call(series, tf=None, up_to=None):
    closes = series["closes"][:up_to] if up_to else series["closes"]
    rsi = series["rsi"][:up_to] if up_to else series["rsi"]
    macd = series["macd"][:up_to] if up_to else series["macd"]
    ohlc = series["ohlc"][:up_to] if up_to else series["ohlc"]
    return detect_early_reversal(
        tf or timeframes(),
        rsi_series_15m=rsi, price_series_15m=closes, macd_hist_15m=macd, ohlc_15m=ohlc)


class TestSetupDetection(unittest.TestCase):
    def test_bullish_setup_at_structural_low(self):
        closes = declining_then_low(40)
        series = build_series(closes, macd=rising_macd(40),
                              volumes=[1000.0] * 39 + [3000.0])
        result = call(series)
        self.assertEqual(result["signal_status"], "ALERTE_PRÉCOCE")
        self.assertEqual(result["direction"], "HAUSSIER")
        self.assertIsNotNone(result["setup"])
        self.assertIn("momentum", result["families"])
        self.assertIn("volume", result["families"])

    def test_setup_without_independent_family_is_attendre(self):
        """Un setup seul (momentum) ne suffit pas : il faut une famille independante."""
        closes = declining_then_low(40)
        series = build_series(closes, macd=rising_macd(40), volumes=[1000.0] * 40)
        # aucun climax de volume, pas de divergence, contexte 4h non survendu
        tf = timeframes()
        tf["4h"] = make_state(rsi=55.0, macd=0.1, macd_prev=0.05, atr=0.0002, adx=35.0)
        tf["1d"] = make_state(rsi=55.0, macd=0.2, macd_prev=0.1, atr=0.0005, adx=30.0)
        tf["1h"] = make_state(rsi=50.0, macd=0.0, macd_prev=0.0, atr=0.00005)
        tf["1w"] = make_state(rsi=50.0, macd=0.0, macd_prev=0.0, atr=0.002, adx=25.0)
        result = call(series, tf)
        self.assertEqual(result["signal_status"], "ATTENDRE")
        self.assertIn("momentum", result["families"])
        self.assertNotIn("structure", result["families"])

    def test_steady_rise_is_not_a_reversal_setup(self):
        """Une hausse reguliere n'est pas un retournement : la direction vient
        de l'extreme structurel, pas d'une serie de bougies."""
        closes = [0.0020 + 0.00001 * i for i in range(40)]
        macd = [0.0001 * i for i in range(40)]
        series = build_series(closes, macd=macd)
        result = call(series)
        self.assertEqual(result["signal_status"], "ATTENDRE")
        self.assertIsNone(result["setup"])

    def test_direction_comes_from_the_extreme_not_from_three_candles(self):
        """Trois bougies ascendantes ne suffisent pas a definir une direction
        haussiere de retournement."""
        closes = declining_then_low(40)
        closes[-1] = closes[-2] * 1.002   # deux clotures en hausse
        closes[-2] = closes[-3] * 1.002
        series = build_series(closes, macd=rising_macd(40),
                              volumes=[1000.0] * 39 + [3000.0])
        result = call(series)
        # le setup haussier existe au plus bas, la direction suit l'extreme
        self.assertIn(result["direction"], ("HAUSSIER", "BAISSIER", "INDETERMINE"))
        if result["setup"] is not None:
            self.assertEqual(result["direction"], result["setup"]["direction"])


class TestStatusTransitions(unittest.TestCase):
    def test_alert_then_confirmation(self):
        """ALERTE_PRÉCOCE puis CONFIRMATION quand la structure se casse."""
        closes = declining_then_low(41)
        # barre 38 : le plus bas (setup avec retournement de momentum)
        # barre 39 : rebond ; barre 40 : cloture au-dessus du plus haut de la jambe
        closes[39] = closes[38] * 1.004
        closes[40] = closes[39] * 1.004
        macd = rising_macd(41)
        macd[39] = -0.0002
        macd[40] = -0.0002
        volumes = [1000.0] * 38 + [3000.0, 1200.0, 1200.0]
        series = build_series(closes, macd=macd, volumes=volumes)

        alert = call(series, up_to=39)
        self.assertEqual(alert["signal_status"], "ALERTE_PRÉCOCE")
        self.assertEqual(alert["direction"], "HAUSSIER")

        confirmed = call(series, up_to=41)
        self.assertEqual(confirmed["signal_status"], "CONFIRMATION")
        types = [e["type"] for e in confirmed["evidence"]]
        self.assertIn("structure_break", types)

    def test_invalidation_when_the_anchor_is_broken(self):
        """INVALIDATION quand l'ancre structurelle du setup est cassee."""
        closes = declining_then_low(39)
        closes[38] = closes[37] * 0.99     # cassure sous l'ancre
        macd = rising_macd(39)
        macd[38] = -0.0003                  # pas de retournement : pas de nouveau setup
        volumes = [1000.0] * 37 + [3000.0, 1500.0]
        series = build_series(closes, macd=macd, volumes=volumes)
        result = call(series)
        self.assertEqual(result["signal_status"], "INVALIDATION")
        self.assertIn("ancre", result["reason"].lower())

    def test_invalidation_takes_precedence_over_confirmation(self):
        closes = declining_then_low(40)
        closes[38] = closes[37] * 0.99
        closes[39] = closes[37] * 0.985
        macd = rising_macd(40)
        macd[38] = -0.0003
        macd[39] = -0.0004
        volumes = [1000.0] * 37 + [3000.0, 1500.0, 1500.0]
        series = build_series(closes, macd=macd, volumes=volumes)
        result = call(series)
        self.assertEqual(result["signal_status"], "INVALIDATION")

    def test_setup_expires_and_status_returns_to_attendre(self):
        """Un setup trop ancien ne reste plus pertinent."""
        closes = declining_then_low(60)
        macd = rising_macd(60)
        volumes = [1000.0] * 59 + [3000.0]
        series = build_series(closes, macd=macd, volumes=volumes)
        # le setup est a la barre 59 ; on ajoute 30 barres sans nouveau setup
        more = [closes[-1] - 0.00001 * (i + 1) for i in range(30)]
        long_series = build_series(closes + more,
                                   macd=macd + [-0.0002] * 30,
                                   volumes=volumes + [1000.0] * 30)
        result = call(long_series)
        self.assertEqual(result["signal_status"], "ATTENDRE")


class TestCriticalLevelIndependence(unittest.TestCase):
    """Le niveau fixe ne doit plus influencer la decision."""

    def _scenario(self):
        closes = declining_then_low(40)
        return build_series(closes, macd=rising_macd(40),
                            volumes=[1000.0] * 39 + [3000.0])

    def test_decision_is_independent_from_critical_level(self):
        series = self._scenario()
        reference = None
        original = agent.CRITICAL_LEVEL
        try:
            for level in (0.001526, 0.000001, 0.5, 12.0, 1e-12):
                agent.CRITICAL_LEVEL = level
                result = call(series)
                if reference is None:
                    reference = result
                else:
                    self.assertEqual(result["signal_status"], reference["signal_status"])
                    self.assertEqual(result["direction"], reference["direction"])
                    self.assertEqual([e["type"] for e in result["evidence"]],
                                     [e["type"] for e in reference["evidence"]])
        finally:
            agent.CRITICAL_LEVEL = original

    def test_critical_level_is_not_read_by_the_detector(self):
        """Aucune reference a CRITICAL_LEVEL dans le corps du detecteur."""
        import inspect
        source = inspect.getsource(detect_early_reversal)
        self.assertNotIn("CRITICAL_LEVEL", source)
        for name in ("_setup_at", "_structure_evidence", "_confirmation_evidence",
                     "_context_evidence", "_volume_evidence", "_structure_levels"):
            self.assertNotIn("CRITICAL_LEVEL", inspect.getsource(getattr(agent, name)))


class TestCausality(unittest.TestCase):
    def test_future_bars_do_not_change_the_decision(self):
        """Perturber les barres posterieures ne doit rien changer a la decision
        prise sur les seules barres disponibles."""
        closes = declining_then_low(40)
        macd = rising_macd(40)
        volumes = [1000.0] * 39 + [3000.0]
        series = build_series(closes, macd=macd, volumes=volumes)
        reference = call(series, up_to=40)

        perturbed_closes = list(closes)
        perturbed_closes[40:] = [0.05, 0.06]
        perturbed_macd = list(macd) + [0.9, 0.9]
        perturbed = build_series(perturbed_closes, macd=perturbed_macd,
                                 volumes=volumes + [9999.0, 9999.0])
        after = call(perturbed, up_to=40)

        self.assertEqual(reference["signal_status"], after["signal_status"])
        self.assertEqual(reference["direction"], after["direction"])
        self.assertEqual([e["type"] for e in reference["evidence"]],
                         [e["type"] for e in after["evidence"]])

    def test_decision_only_uses_bars_up_to_the_current_one(self):
        """Le setup reference ne peut pas etre posterieur a la barre courante."""
        closes = declining_then_low(40)
        series = build_series(closes, macd=rising_macd(40),
                              volumes=[1000.0] * 39 + [3000.0])
        result = call(series)
        if result["setup"]:
            # l'index du setup est relatif a la fenetre analysee : seule l'age
            # (nombre de bougies depuis la creation) est publie
            self.assertNotIn("index", result["setup"])
            self.assertGreaterEqual(result["setup"]["age_bars"], 0)
            self.assertLessEqual(result["setup"]["age_bars"], len(closes) - 1)


class TestRegimeAndExploitabilite(unittest.TestCase):
    """Le regime de marche et la determination d'exploitabilite."""

    def _state(self, **kwargs):
        base = make_state(rsi=40.0, macd=0.00001, macd_prev=0.000005, atr=0.00002)
        base.update(kwargs)
        return base

    def _timeframes(self, change_30=None):
        return {
            "15m": self._state(),
            "1h": self._state(rsi=45.0),
            "4h": self._state(rsi=28.0, adx=15.0),
            "1d": self._state(rsi=30.0, change_30=change_30),
            "1w": self._state(rsi=35.0, adx=12.0),
            "1M": make_state(status="PARTIEL", rsi=40.0, atr=0.004, trend="INDETERMINE"),
        }

    def test_regime_neutre_quand_la_variation_1d_est_faible(self):
        closes = declining_then_low(40)
        series = build_series(closes, macd=rising_macd(40),
                              volumes=[1000.0] * 39 + [3000.0])
        result = call(series, self._timeframes(change_30=0.02))
        self.assertEqual(result["regime"]["state"], "NEUTRE")
        self.assertEqual(result["regime"]["window_bars"], 30)

    def test_regime_tendance_detecte(self):
        closes = declining_then_low(40)
        series = build_series(closes, macd=rising_macd(40),
                              volumes=[1000.0] * 39 + [3000.0])
        result = call(series, self._timeframes(change_30=-0.25))
        self.assertEqual(result["regime"]["state"], "TENDANCE_BAISSIERE")

    def test_regime_indetermine_sans_historique_journalier(self):
        closes = declining_then_low(40)
        series = build_series(closes, macd=rising_macd(40),
                              volumes=[1000.0] * 39 + [3000.0])
        result = call(series, self._timeframes(change_30=None))
        self.assertEqual(result["regime"]["state"], "INDETERMINE")

    def test_exploitable_exige_confirmation_et_regime_neutre(self):
        closes = declining_then_low(40)
        series = build_series(closes, macd=rising_macd(40),
                              volumes=[1000.0] * 39 + [3000.0])
        result = call(series, self._timeframes(change_30=0.02))
        # le scenario est une ALERTE (non confirmee) : jamais exploitable
        self.assertEqual(result["signal_status"], "ALERTE_PRÉCOCE")
        self.assertFalse(result["exploitable"])
        self.assertIn("confirme", result["exploitable_reason"].lower())

    def test_exploitable_faux_en_regime_de_tendance(self):
        """Meme avec une confirmation, un regime en tendance n'est pas exploitable."""
        closes = declining_then_low(41)
        # barre 38 : plus bas avec retournement ; barre 39 : cassure de structure
        closes[39] = closes[38] * 1.01
        closes[40] = closes[39] * 1.01
        macd = rising_macd(41)
        macd[39] = -0.0002
        macd[40] = -0.0002
        series = build_series(closes, macd=macd, volumes=[1000.0] * 38 + [3000.0, 1200.0, 1200.0])
        result = call(series, self._timeframes(change_30=-0.30))
        self.assertEqual(result["signal_status"], "CONFIRMATION")
        self.assertEqual(result["regime"]["state"], "TENDANCE_BAISSIERE")
        self.assertFalse(result["exploitable"])
        self.assertIn("tendance", result["exploitable_reason"].lower())


class TestCandleFigures(unittest.TestCase):
    def test_hammer_pattern_is_detected_and_reported(self):
        """Un marteau a l'extreme doit produire une preuve de structure."""
        closes = declining_then_low(40)
        highs = [c * 1.002 for c in closes]
        lows = [c * 0.998 for c in closes]
        opens = list(closes)
        # derniere bougie : corps petit en haut, longue meche basse
        closes[-1] = 0.001600
        opens[-1] = 0.001601
        highs[-1] = 0.001602
        lows[-1] = 0.001500
        series = build_series(closes, highs=highs, lows=lows, opens=opens,
                              macd=rising_macd(40), volumes=[1000.0] * 39 + [3000.0])
        self.assertTrue(has_hammer_pattern(highs[-1], lows[-1], opens[-1], closes[-1]))
        result = call(series)
        types = [e["type"] for e in result["evidence"]]
        self.assertIn("hammer_pattern", types)
        self.assertIn("structure", result["families"])

    def test_bullish_engulfing_is_reported(self):
        closes = declining_then_low(40)
        highs = [c * 1.002 for c in closes]
        lows = [c * 0.998 for c in closes]
        opens = list(closes)
        # avant-derniere bougie baissiere, derniere bougie englobante haussiere
        # qui fait aussi le plus bas de la fenetre (donc l'ancre du setup)
        closes[38] = 0.001900
        opens[38] = 0.001950
        highs[38] = 0.001960
        lows[38] = 0.001880
        closes[39] = 0.001960
        opens[39] = 0.001500          # gap sous le plus bas : <= close precedente
        highs[39] = 0.001970
        lows[39] = 0.001495           # plus bas que la veille
        macd = rising_macd(40)
        series = build_series(closes, highs=highs, lows=lows, opens=opens, macd=macd,
                              volumes=[1000.0] * 39 + [3000.0])
        result = call(series)
        self.assertEqual(result["direction"], "HAUSSIER")
        types = [e["type"] for e in result["evidence"]]
        self.assertIn("bullish_engulfing", types)

    def test_figures_are_absent_when_ohlc_is_unavailable(self):
        """Sans OHLC, le moteur degrade proprement et le signale."""
        closes = declining_then_low(40)
        series = build_series(closes, macd=rising_macd(40),
                              volumes=[1000.0] * 39 + [3000.0])
        result = detect_early_reversal(
            timeframes(),
            rsi_series_15m=series["rsi"], price_series_15m=series["closes"],
            macd_hist_15m=series["macd"], ohlc_15m=None)
        self.assertIn("ohlc_15m_indisponible", result["missing_data"])
        types = [e["type"] for e in result["evidence"]]
        self.assertNotIn("hammer_pattern", types)


class TestMissingDataAndEdgeCases(unittest.TestCase):
    def test_missing_15m_gives_insufficient_data(self):
        tf = timeframes()
        tf["15m"] = make_state(status="UNAVAILABLE")
        result = detect_early_reversal(tf, rsi_series_15m=[50.0] * 40,
                                       price_series_15m=[0.002] * 40,
                                       macd_hist_15m=[0.0] * 40)
        self.assertEqual(result["signal_status"], "DONNÉES_INSUFFISANTES")
        self.assertEqual(result["confidence"], 0)

    def test_short_history_gives_insufficient_data(self):
        result = detect_early_reversal(timeframes(), rsi_series_15m=[50.0] * 5,
                                       price_series_15m=[0.002] * 5,
                                       macd_hist_15m=[0.0] * 5)
        self.assertEqual(result["signal_status"], "DONNÉES_INSUFFISANTES")

    def test_empty_series_does_not_raise(self):
        result = detect_early_reversal(timeframes(), rsi_series_15m=[],
                                       price_series_15m=[], macd_hist_15m=[])
        self.assertEqual(result["signal_status"], "DONNÉES_INSUFFISANTES")

    def test_nan_values_are_tolerated(self):
        closes = declining_then_low(40)
        macd = rising_macd(40)
        macd[10] = float("nan")
        series = build_series(closes, macd=macd, volumes=[1000.0] * 39 + [3000.0])
        result = call(series)
        self.assertIn(result["signal_status"],
                      ("ALERTE_PRÉCOCE", "CONFIRMATION", "INVALIDATION", "ATTENDRE"))

    def test_misaligned_series_are_reported(self):
        closes = declining_then_low(40)
        series = build_series(closes, macd=rising_macd(40))
        result = detect_early_reversal(
            timeframes(),
            rsi_series_15m=series["rsi"][:10], price_series_15m=series["closes"],
            macd_hist_15m=series["macd"], ohlc_15m=series["ohlc"])
        self.assertIn("series_15m_desalignees", result["missing_data"])

    def test_contradiction_with_opposite_higher_timeframe_trend(self):
        closes = declining_then_low(40)
        series = build_series(closes, macd=rising_macd(40),
                              volumes=[1000.0] * 39 + [3000.0])
        tf = timeframes()
        tf["1w"] = make_state(rsi=70.0, macd=0.1, macd_prev=0.05, atr=0.002, adx=40.0, trend="BAISSIER")
        tf["1d"] = make_state(rsi=65.0, macd=0.2, macd_prev=0.1, atr=0.0005, adx=35.0, trend="BAISSIER")
        result = call(series, tf)
        types = [c["type"] for c in result["contradictions"]]
        self.assertIn("higher_timeframe_trend_opposite", types)

    def test_trend_alignment_is_an_observation_not_evidence(self):
        """Une tendance superieure alignee ne doit pas compter comme preuve."""
        closes = declining_then_low(40)
        series = build_series(closes, macd=rising_macd(40),
                              volumes=[1000.0] * 39 + [3000.0])
        tf = timeframes()
        for key in ("4h", "1d", "1w"):
            tf[key] = make_state(rsi=55.0, macd=0.1, macd_prev=0.05, atr=0.0002,
                                 adx=35.0, trend="HAUSSIER")
        result = call(series, tf)
        types = [e["type"] for e in result["evidence"]]
        self.assertNotIn("higher_timeframe_alignment", types)
        observations = [o["type"] for o in result["observations"]]
        self.assertIn("higher_timeframe_trend_same_direction", observations)


class TestOutputs(unittest.TestCase):
    def test_objectives_are_informative_only(self):
        closes = declining_then_low(40)
        series = build_series(closes, macd=rising_macd(40),
                              volumes=[1000.0] * 39 + [3000.0])
        result = call(series)
        objectives = result["objectives"]
        self.assertIsNotNone(objectives)
        self.assertIn("short_term", objectives)
        self.assertIn("swing", objectives)
        self.assertIn("pas une prediction", objectives["note"].lower())

    def test_confidence_is_labelled_as_not_a_probability(self):
        closes = declining_then_low(40)
        series = build_series(closes, macd=rising_macd(40),
                              volumes=[1000.0] * 39 + [3000.0])
        result = call(series)
        self.assertIn("probabilite", result["confidence_note"].lower())
        self.assertGreaterEqual(result["confidence"], 0)
        self.assertLessEqual(result["confidence"], 100)

    def test_reproducibility(self):
        closes = declining_then_low(40)
        series = build_series(closes, macd=rising_macd(40),
                              volumes=[1000.0] * 39 + [3000.0])
        first = call(series)
        second = call(series)
        self.assertEqual(first, second)

    def test_parameters_are_exposed_and_frozen(self):
        self.assertIn("extreme_window", REVERSAL_PARAMS)
        self.assertIn("setup_window", REVERSAL_PARAMS)
        self.assertIn("break_tolerance_atr", REVERSAL_PARAMS)
        self.assertEqual(REVERSAL_PARAMS["extreme_window"], 20)
        self.assertEqual(REVERSAL_PARAMS["setup_window"], 16)

    def test_every_evidence_has_a_known_family(self):
        closes = declining_then_low(40)
        series = build_series(closes, macd=rising_macd(40),
                              volumes=[1000.0] * 39 + [3000.0])
        result = call(series)
        for item in result["evidence"]:
            self.assertIn(item["category"], ("structure", "momentum", "volume", "context"))
            self.assertIn("type", item)


if __name__ == "__main__":
    unittest.main()
