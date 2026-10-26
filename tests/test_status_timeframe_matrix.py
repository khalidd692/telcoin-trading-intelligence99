"""Tests de régression pour scripts/backtest/status_timeframe_matrix.py.

Vérifie que chaque timeframe affiche ses propres horizons réellement mesurés,
et non ceux d'une autre unité de temps (défaut A3 corrigé).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.backtest.harness import horizons_in_bars  # noqa: E402
from scripts.backtest.protocol import HORIZON_PRESENTATION_INDICES  # noqa: E402

# Libellés attendus (en heures) pour les horizons d'indices 1 et 2 de chaque TF.
# Valeurs réelles de horizons_in_bars :
#   15m -> [8, 24, 96, 288]  -> indices 1,2 = 24 barres (6h), 96 barres (24h)
#   1h  -> [2, 6, 24, 72]    -> indices 1,2 = 6 barres (6h), 24 barres (24h)
#   4h  -> [6, 18, 42, 180]  -> indices 1,2 = 18 barres (72h), 42 barres (168h)
#   1d  -> [2, 5, 10, 20]    -> indices 1,2 = 5 barres (120h), 10 barres (240h)
EXPECTED_LABELS = {
    "15m": ("6h", "24h"),
    "1h": ("6h", "24h"),
    "4h": ("72h", "168h"),
    "1d": ("120h", "240h"),
}
EXPECTED_BARS = {
    "15m": (24, 96),
    "1h": (6, 24),
    "4h": (18, 42),
    "1d": (5, 10),
}
TF_SECONDS = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


def _label(bars: int, tf: str) -> str:
    return "{}h".format(int(round(bars * TF_SECONDS[tf] / 3600)))


def test_horizon_presentation_indices_are_1_and_2():
    assert HORIZON_PRESENTATION_INDICES == (1, 2)


def test_each_timeframe_has_its_own_horizons():
    """Chaque TF utilise ses propres horizons, pas ceux d'une autre UT."""
    for tf, (label_a, label_b) in EXPECTED_LABELS.items():
        available = horizons_in_bars(tf)
        assert len(available) >= 4, f"{tf} a moins de 4 horizons disponibles"
        h_a = available[HORIZON_PRESENTATION_INDICES[0]]
        h_b = available[HORIZON_PRESENTATION_INDICES[1]]
        assert _label(h_a, tf) == label_a, (
            f"{tf} : horizon A attendu {label_a}, obtenu {_label(h_a, tf)}")
        assert _label(h_b, tf) == label_b, (
            f"{tf} : horizon B attendu {label_b}, obtenu {_label(h_b, tf)}")


def test_expected_bar_counts():
    """Vérifie les nombres de barres des horizons retenus."""
    for tf, (bars_a, bars_b) in EXPECTED_BARS.items():
        available = horizons_in_bars(tf)
        h_a = available[HORIZON_PRESENTATION_INDICES[0]]
        h_b = available[HORIZON_PRESENTATION_INDICES[1]]
        assert h_a == bars_a, f"{tf} : horizon A = {h_a} barres, attendu {bars_a}"
        assert h_b == bars_b, f"{tf} : horizon B = {h_b} barres, attendu {bars_b}"


def test_1d_horizons_are_not_24h_72h():
    """Le cas journalier : ses horizons ne sont pas 24h/72h (ceux de la 15m)."""
    available = horizons_in_bars("1d")
    h_a = available[HORIZON_PRESENTATION_INDICES[0]]
    h_b = available[HORIZON_PRESENTATION_INDICES[1]]
    assert _label(h_a, "1d") != "24h", "1d affiche 24h au lieu de 120h"
    assert _label(h_b, "1d") != "72h", "1d affiche 72h au lieu de 240h"
    assert _label(h_a, "1d") == "120h"
    assert _label(h_b, "1d") == "240h"


def test_4h_horizons_are_not_24h_72h():
    """Le cas 4h : ses horizons ne sont pas 24h/72h (ceux de la 15m)."""
    available = horizons_in_bars("4h")
    h_a = available[HORIZON_PRESENTATION_INDICES[0]]
    h_b = available[HORIZON_PRESENTATION_INDICES[1]]
    assert _label(h_a, "4h") == "72h"
    assert _label(h_b, "4h") == "168h"


def test_1h_and_15m_share_labels_but_differ_in_bars():
    """1h et 15m ont les mêmes libellés (6h/24h) mais des barres différentes."""
    a_15m = horizons_in_bars("15m")[HORIZON_PRESENTATION_INDICES[0]]
    a_1h = horizons_in_bars("1h")[HORIZON_PRESENTATION_INDICES[0]]
    assert a_15m == 24
    assert a_1h == 6
    assert _label(a_15m, "15m") == _label(a_1h, "1h") == "6h"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))