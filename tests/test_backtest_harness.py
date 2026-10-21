"""
Tests de régression du harnais de backtest (scripts/backtest/).

Aucun accès réseau : les tests s'exécutent sur la fixture
tests/fixtures/tel_history_sample.json, ce qui les rend utilisables en CI.

Références :
  R1  aucune fuite temporelle (perturbation de l'avenir)
  R2  équivalence préfixe / historique complet pour les indicateurs
  R3  alignement réel des unités de temps (close_time <= t)
  R4  déduplication par événement
  R5  reproductibilité
  R6  test d'atteignabilité (base rate) et fenêtre non discriminante
  R7  complétude des statuts de sortie
  R8  cas dégénéré (aucun signal)
  R9  intégrité de l'archive
  R10 fixture utilisable sans réseau
  R11 fidélité du chemin rapide vis-à-vis du code de production
"""

import json
import math
import random
import unittest
from pathlib import Path

from scripts.backtest import engine, history_store as store
from scripts.backtest.harness import (
    PROTOCOL,
    Bundle,
    call_detector,
    detection_state,
    fast_timeframe_state,
    horizons_in_bars,
    production_timeframe_state,
)
from src.agent_analysis import (
    atr_series,
    cci_series,
    dmi_series,
    ema_series,
    macd_histogram,
    momentum_series,
    rsi_series,
    sma_series,
    stochastic_series,
)

FIXTURE = Path(__file__).parent / "fixtures" / "tel_history_sample.json"
_CACHE = {}


def fixture_timeframes():
    if "data" not in _CACHE:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        _CACHE["data"] = payload["timeframes"]
    return _CACHE["data"]


def rows_for(timeframe):
    return fixture_timeframes()[timeframe]


def bundle_for(timeframe):
    key = f"bundle:{timeframe}"
    if key not in _CACHE:
        _CACHE[key] = Bundle(timeframe, rows_for(timeframe))
    return _CACHE[key]


def perturb_future(rows, index, seed=1234):
    """Perturbe toutes les bougies postérieures à index (hors valeurs aberrantes)."""
    rng = random.Random(seed)
    perturbed = [dict(row) for row in rows]
    for row in perturbed[index + 1:]:
        factor = rng.uniform(0.4, 2.5)
        for field in ("o", "h", "l", "c"):
            row[field] = round(row[field] * factor, 12)
    return perturbed


class TestNoFutureLeak(unittest.TestCase):
    """R1 : l'état et la détection à l'instant t ne doivent dépendre que du passé."""

    def test_r1_etat_identique_apres_perturbation_du_futur(self):
        rows = rows_for("15m")
        bundle = bundle_for("15m")
        index = 250
        now = store.close_time_ms(rows[index], "15m")
        before = fast_timeframe_state(bundle, index, now)
        perturbed = Bundle("15m", perturb_future(rows, index))
        after = fast_timeframe_state(perturbed, index, now)
        self.assertEqual(before, after)

    def test_r1_detection_identique_apres_perturbation_du_futur(self):
        rows = rows_for("15m")
        bundle = bundle_for("15m")
        index = 250
        now = store.close_time_ms(rows[index], "15m")
        state = fast_timeframe_state(bundle, index, now)
        series = detection_state(bundle, index)
        before = call_detector({"15m": state}, series)
        perturbed = Bundle("15m", perturb_future(rows, index))
        state_after = fast_timeframe_state(perturbed, index, now)
        series_after = detection_state(perturbed, index)
        after = call_detector({"15m": state_after}, series_after)
        self.assertEqual(before["signal_status"], after["signal_status"])
        self.assertEqual(before["direction"], after["direction"])
        self.assertEqual(before["evidence"], after["evidence"])

    def test_r1_seuil_quantile_insensible_a_la_perturbation_du_futur(self):
        # On utilise 1h : le quantile causal exige h_max bougies d'antecedence,
        # ce qui n'est pas atteignable sur la courte fenetre 15m de la fixture.
        rows = rows_for("1h")
        bundle = bundle_for("1h")
        index = 250
        perturbed = Bundle("1h", perturb_future(rows, index))
        checked = 0
        for horizon in horizons_in_bars("1h"):
            if bundle.q90[horizon][index] is None:
                continue
            checked += 1
            self.assertEqual(bundle.q90[horizon][index], perturbed.q90[horizon][index])
        self.assertGreater(checked, 0, "le quantile causal doit etre defini a cet index")

    def test_r3_alignement_multi_unites_de_temps(self):
        rows = rows_for("15m")
        index = 250
        now = store.close_time_ms(rows[index], "15m")
        for timeframe in ("15m", "1h", "4h", "1d"):
            bundle = bundle_for(timeframe)
            index_tf = engine.TimeframeIndex(bundle).index_at(now)
            self.assertIsNotNone(index_tf)
            close_time = store.close_time_ms(bundle.rows[index_tf], timeframe)
            self.assertLessEqual(close_time, now, "aucune bougie future ne doit etre utilisee")
            if index_tf + 1 < len(bundle.rows):
                next_close = store.close_time_ms(bundle.rows[index_tf + 1], timeframe)
                self.assertGreater(next_close, now)

    def test_r3_une_bougie_en_formation_nest_jamais_utilisee(self):
        rows = rows_for("1h")
        bundle = bundle_for("1h")
        now = store.close_time_ms(rows[100], "1h")
        state = fast_timeframe_state(bundle, 100, now)
        used = bundle.rows[100]
        self.assertEqual(state["close"], used["c"])
        self.assertLessEqual(store.close_time_ms(used, "1h"), now)


class TestCausaliteDesIndicateurs(unittest.TestCase):
    """R2 : un indicateur calculé sur l'historique complet doit coïncider avec
    celui calculé sur le préfixe, sinon le pré-calcul serait une fuite."""

    @staticmethod
    def _value_at(series, index):
        """Valeur de la série à l'index `index` (aligné sur la bougie), ou None."""
        if index >= len(series):
            return None
        value = series[index]
        if value is None or not math.isfinite(value):
            return None
        return value

    def test_r2_equivalence_prefixe_complet(self):
        rows = rows_for("15m")
        closes = [r["c"] for r in rows]
        highs = [r["h"] for r in rows]
        lows = [r["l"] for r in rows]
        for index in (150, 220, 290):
            prefix_c = closes[:index + 1]
            prefix_h = highs[:index + 1]
            prefix_l = lows[:index + 1]
            checks = [
                ("ema20", ema_series(closes, 20), ema_series(prefix_c, 20)),
                ("ema50", ema_series(closes, 50), ema_series(prefix_c, 50)),
                ("rsi14", rsi_series(closes, 14), rsi_series(prefix_c, 14)),
                ("sma50", sma_series(closes, 50), sma_series(prefix_c, 50)),
                ("sma100", sma_series(closes, 100), sma_series(prefix_c, 100)),
                ("momentum", momentum_series(closes, 10), momentum_series(prefix_c, 10)),
                ("atr", atr_series(highs, lows, closes, 14), atr_series(prefix_h, prefix_l, prefix_c, 14)),
                ("cci", cci_series(highs, lows, closes, 20), cci_series(prefix_h, prefix_l, prefix_c, 20)),
            ]
            for name, full, prefix in checks:
                expected = self._value_at(full, index)
                actual = self._value_at(prefix, len(prefix) - 1)
                self.assertIsNotNone(expected, f"{name} sans valeur a l'index {index}")
                self.assertAlmostEqual(expected, actual, places=9,
                                       msg=f"{name} differe entre prefixe et historique complet (index {index})")

    def test_r2_macd_alignement_index_bougie(self):
        rows = rows_for("15m")
        closes = [r["c"] for r in rows]
        full = macd_histogram(closes)
        for index in (150, 220, 280):
            prefix = macd_histogram(closes[:index + 1])
            self.assertAlmostEqual(full[index], prefix[-1], places=12,
                                   msg="macd_histogram n'est pas aligne sur la bougie")

    def test_r2_dmi_alignement_index_bougie(self):
        rows = rows_for("15m")
        closes = [r["c"] for r in rows]
        highs = [r["h"] for r in rows]
        lows = [r["l"] for r in rows]
        full_di, full_dm, full_adx = dmi_series(highs, lows, closes, 14)
        for index in (200, 280):
            prefix_di, prefix_dm, prefix_adx = dmi_series(highs[:index + 1], lows[:index + 1],
                                                           closes[:index + 1], 14)
            self.assertAlmostEqual(full_di[index], prefix_di[-1], places=9)
            self.assertAlmostEqual(full_dm[index], prefix_dm[-1], places=9)
            self.assertAlmostEqual(full_adx[index], prefix_adx[-1], places=9)

    def test_r2_stochastic_alignement_index_bougie(self):
        rows = rows_for("15m")
        closes = [r["c"] for r in rows]
        highs = [r["h"] for r in rows]
        lows = [r["l"] for r in rows]
        full_k, full_d = stochastic_series(highs, lows, closes, 14, 3)
        index = 250
        prefix_k, prefix_d = stochastic_series(highs[:index + 1], lows[:index + 1], closes[:index + 1], 14, 3)
        self.assertAlmostEqual(full_k[index], prefix_k[-1], places=9)
        self.assertAlmostEqual(full_d[index], prefix_d[-1], places=9)


class TestFideliteHarnais(unittest.TestCase):
    """R11 : le chemin rapide doit reproduire exactement le code de production."""

    def test_r11_etat_rapide_identique_a_analyze_timeframe(self):
        for timeframe in ("15m", "1h", "4h"):
            bundle = bundle_for(timeframe)
            for index in (120, 200, 280):
                if index >= len(bundle.rows):
                    continue
                now = store.close_time_ms(bundle.rows[index], timeframe)
                fast = fast_timeframe_state(bundle, index, now)
                production = production_timeframe_state(bundle, index, now)
                for key in sorted(set(fast) | set(production)):
                    self.assertEqual(fast.get(key), production.get(key),
                                     msg=f"{timeframe}[{index}].{key} diverge du code de production")

    def test_r11_detection_rapide_identique_a_la_production(self):
        bundle = bundle_for("15m")
        index = 250
        now = store.close_time_ms(bundle.rows[index], "15m")
        fast_state = fast_timeframe_state(bundle, index, now)
        production_state = production_timeframe_state(bundle, index, now)
        fast = call_detector({"15m": fast_state}, detection_state(bundle, index))
        production = call_detector({"15m": production_state}, detection_state(bundle, index))
        self.assertEqual(fast, production)


class TestMetriques(unittest.TestCase):
    """R4, R6, R7, R8."""

    def _signals(self):
        base = 1_700_000_000_000
        return [
            {"index": 10, "time_ms": base, "status": "ALERTE_PRÉCOCE", "direction": "HAUSSIER",
             "confidence": 60, "evidence": ["a"], "contradictions": [], "reason": "", "price": 1.0},
            {"index": 12, "time_ms": base + 20 * 60_000, "status": "ALERTE_PRÉCOCE", "direction": "HAUSSIER",
             "confidence": 60, "evidence": ["a"], "contradictions": [], "reason": "", "price": 1.0},
            {"index": 14, "time_ms": base + 40 * 60_000, "status": "ALERTE_PRÉCOCE", "direction": "HAUSSIER",
             "confidence": 60, "evidence": ["a"], "contradictions": [], "reason": "", "price": 1.0},
            {"index": 20, "time_ms": base + 200 * 60_000, "status": "ALERTE_PRÉCOCE", "direction": "BAISSIER",
             "confidence": 60, "evidence": ["b"], "contradictions": [], "reason": "", "price": 1.0},
            {"index": 30, "time_ms": base + 400 * 60_000, "status": "INVALIDATION",
             "direction": "HAUSSIER", "confidence": 90, "evidence": [], "contradictions": [], "reason": "", "price": 1.0},
        ]

    def test_r4_deduplication_par_evenement(self):
        episodes = engine.group_episodes(self._signals())
        # chaque statut est regroupe independamment :
        # 3 ALERTE_PRÉCOCE proches -> 1 episode ; l'INVALIDATION forme son propre
        # episode ; la rafale baissiere forme le sien.
        self.assertEqual(len(episodes), 3, "3 alertes rapprochees doivent former 1 episode")
        alert_episodes = [e for e in episodes if e["status"] == "ALERTE_PRÉCOCE"]
        # 3 alertes a 20 min d'intervalle -> 1 episode ; la 4e alerte, a 200 min,
        # est hors fenetre de deduplication -> son propre episode
        self.assertEqual(len(alert_episodes), 2)
        self.assertEqual(alert_episodes[0]["member_count"], 3)
        self.assertEqual(alert_episodes[0]["index"], 10)
        self.assertEqual(alert_episodes[1]["index"], 20)
        invalidations = [e for e in episodes if e["status"] == "INVALIDATION"]
        self.assertEqual(len(invalidations), 1)
        bearish = [e for e in episodes if e["direction"] == "BAISSIER"]
        self.assertEqual(len(bearish), 1)
        self.assertEqual(bearish[0]["index"], 20)

    def test_r4_les_invalidations_ne_sont_pas_des_episodes_dalerte(self):
        episodes = engine.group_episodes(self._signals())
        alert_episodes = [e for e in episodes if e["status"] == "ALERTE_PRÉCOCE"]
        self.assertTrue(all(e["direction"] in ("HAUSSIER", "BAISSIER") for e in alert_episodes))
        # l'invalidation est un episode distinct, mesure a part
        self.assertTrue(any(e["status"] == "INVALIDATION" for e in episodes))

    def test_r7_statut_de_sortie_complet(self):
        bundle = bundle_for("15m")
        episodes = engine.group_episodes(self._signals())
        for episode in episodes:
            result = engine.evaluate_episode(bundle, episode, "quantile")
            self.assertIn(result["outcome"], ("SIGNIFICANT", "NON_SIGNIFICANT", "NON_EVALUABLE"))
            self.assertEqual(result["evaluable"], result["available"] >= PROTOCOL["min_horizons_hit"])

    def test_r8_cas_degenere_aucun_signal(self):
        episodes = engine.group_episodes([])
        self.assertEqual(episodes, [])
        bundle = bundle_for("15m")
        null = engine.null_test(bundle, [], [], "quantile")
        self.assertIsNone(null["observed_hit_rate"])
        self.assertFalse(null["significant"])

    def test_r6_base_rate_et_vigilance_de_discrimination(self):
        bundle = bundle_for("1h")
        indices = list(range(150, len(bundle.rows) - max(horizons_in_bars("1h"))))
        base = engine.base_rate(bundle, indices, "quantile")
        self.assertIn("discriminant", base)
        self.assertGreater(base["base_rate"], 0.0)
        self.assertLess(base["base_rate"], 1.0)
        self.assertEqual(base["discriminant"],
                         PROTOCOL["base_rate_min"] <= base["base_rate"] <= PROTOCOL["base_rate_max"])

    def test_r6_fenetre_non_discriminante_signalee(self):
        bundle = bundle_for("15m")
        base = engine.base_rate(bundle, [], "quantile")
        self.assertEqual(base["base_rate"], 0.0)
        self.assertFalse(base["discriminant"], "une fenetre sans barre evaluable n'est pas discriminante")

    def test_criteres_publies_ensemble(self):
        """Le protocole doit garder les DEUX criteres (v1 sigma, v2 quantile)."""
        self.assertIn("sigma_multiplier", PROTOCOL)
        self.assertIn("quantile", PROTOCOL)
        self.assertIn("revision_note", PROTOCOL)


class TestReproductibilite(unittest.TestCase):
    """R5."""

    def test_r5_determinisme_de_la_detection(self):
        bundles = {tf: bundle_for(tf) for tf in ("15m", "1h", "4h", "1d")}
        indexes = {tf: engine.TimeframeIndex(bundles[tf]) for tf in bundles}
        first, counts_a = engine.collect_signals(bundles, indexes, "15m")
        second, counts_b = engine.collect_signals(bundles, indexes, "15m")
        self.assertEqual(counts_a, counts_b)
        self.assertEqual(first, second)


class TestArchive(unittest.TestCase):
    """R9, R10."""

    def test_r10_fixture_presente_et_exploitable_sans_reseau(self):
        self.assertTrue(FIXTURE.exists(), "la fixture CI doit etre versionnee")
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(payload["kind"], "tel_history_sample")
        for timeframe in ("15m", "1h", "4h", "1d", "1w", "1M"):
            self.assertIn(timeframe, payload["timeframes"])
            self.assertGreater(len(payload["timeframes"][timeframe]), 60)

    def test_r9_integrite_de_l_archive(self):
        for timeframe, rows in fixture_timeframes().items():
            times = [row["t"] for row in rows]
            self.assertEqual(len(times), len(set(times)), f"{timeframe} : doublons")
            self.assertEqual(times, sorted(times), f"{timeframe} : ordre non croissant")
            period = store.PERIOD_SECONDS.get(timeframe)
            if period:
                for index in range(1, len(times)):
                    step = (times[index] - times[index - 1]) / 1000
                    self.assertEqual(step, period, f"{timeframe} : trou a l'index {index}")
            for row in rows:
                self.assertGreater(min(row["o"], row["h"], row["l"], row["c"]), 0)
                self.assertGreaterEqual(row["h"], max(row["o"], row["c"]))
                self.assertLessEqual(row["l"], min(row["o"], row["c"]))
                self.assertGreaterEqual(row["v"], 0)

    def test_r9_bougie_en_formation_exclue_du_cache(self):
        """Le cache ne doit contenir que des bougies clôturées."""
        import time as _time
        now_ms = int(_time.time() * 1000)
        for timeframe, rows in fixture_timeframes().items():
            for row in rows[-3:]:
                self.assertLessEqual(store.close_time_ms(row, timeframe), now_ms)


if __name__ == "__main__":
    unittest.main()
