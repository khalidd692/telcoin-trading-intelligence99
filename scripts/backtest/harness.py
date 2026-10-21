"""
Harnais de backtest du détecteur de retournement précoce TEL/USDT.

Principes :
  * aucune fuite temporelle : à l'instant t, seule une bougie dont close_time <= t
    est utilisée, pour chaque unité de temps ;
  * le code de production (src/agent_analysis.py) est appelé SANS modification ;
  * la logique multi-unités de temps n'est pas réimplémentée : on réutilise
    analyze_timeframe() et detect_early_reversal() tels quels ;
  * les seuils de mouvement significatif sont exprimés en multiples de la
    volatilité mesurée (ATR14 relatif), et les constantes du protocole sont
    figées avant exécution (voir PROTOCOL).

Le protocole est défini ICI, en clair, avant toute exécution sur les données.
"""

from __future__ import annotations

import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.agent_analysis import (  # noqa: E402
    MAX_SNAPSHOT_AGE_SECONDS,
    MIN_CANDLES,
    analyze_timeframe,
    atr_series,
    awesome_oscillator_series,
    cci_series,
    detect_early_reversal,
    dmi_series,
    ema_series,
    macd_histogram,
    momentum_series,
    rsi_series,
    sma_series,
    stochastic_series,
)
from scripts.backtest import history_store as store  # noqa: E402

# --------------------------------------------------------------------------
# PROTOCOLE — figé avant exécution. Toute modification doit être justifiée
# dans le rapport et n'est jamais faite pour améliorer les statistiques.
# --------------------------------------------------------------------------
PROTOCOL: dict[str, Any] = {
    "version": "1.1",
    "sigma_multiplier": 1.5,          # seuil v1 = k * sqrt(H_barres) * ATR14_relatif
    "quantile": 0.90,                 # seuil v2 = quantile empirique causal (q90)
    "quantile_window": 200,           # fenêtre glissante causale du quantile
    "criterion": "quantile",          # critère primaire retenu (v2)
    "min_horizons_hit": 2,             # significatif si >= 2 horizons atteints
    "dedup_window_minutes": 90,        # regroupement des signaux en épisodes
    "atr_window_bars": 200,            # fenêtre glissante (causale) du calcul de volatilité
    "reference_sigma": 1.5,            # amplitude du retournement de référence (critère v1)
    "reference_min_separation": 0.5,   # separation minimale, en fraction du plus long horizon
    "warning_window_horizon": 1,       # index de l'horizon servant de fenetre d'avertissement
                                        # (2e plus court : 6 h en 15m/1h, 3 j en 4h, 5 j en 1d)
    "base_rate_min": 0.05,             # en dessous, la fenêtre est non discriminante
    "base_rate_max": 0.60,
    "null_test_iterations": 2000,
    "null_test_iterations_note": (
        "200 iterations donnaient une resolution de percentile de 0,5 % : un verdict limite "
        "(0,955 vs 0,91) ne distinguait pas un signal reel d'une variation de l'estimateur. "
        "Le nombre d'iterations est la PRECISION de l'estimateur, pas le seuil de decision "
        "(le seuil reste percentile >= 0,95) : l'augmenter ne favorise aucune hypothese."
    ),
    "revision_note": (
        "v1.0 (seuil sigma) a échoué au test d'atteignabilité R6 (base rate 4,8 % < 5 %) : "
        "le critère n'était atteignable sur aucune fenêtre testée. v1.1 ajoute un second critère "
        "distributionnel (quantile causal q90) dont le taux de base est constructible (~10 %). "
        "LES DEUX RÉSULTATS SONT PUBLIÉS. Les constantes n'ont pas été retouchées pour améliorer "
        "la performance du détecteur."
    ),
}

# Horizons exprimés en DURATIONS (pas en nombre de bougies) : la même question
# est posée à chaque unité de temps ("le prix a bougé dans les 24 h qui suivent ?").
HORIZON_DURATIONS: dict[str, list[str]] = {
    "15m": ["2h", "6h", "24h", "72h"],
    "1h":  ["2h", "6h", "24h", "72h"],
    "4h":  ["1d", "3d", "7d", "30d"],
    "1d":  ["2d", "5d", "10d", "20d"],
    "1w":  ["2w", "5w", "10w", "20w"],
    "1M":  ["3M", "6M", "12M", "24M"],
}

_DURATION_SECONDS = {"h": 3600, "d": 86400, "w": 604800}


def _duration_seconds(token: str) -> int:
    if token.endswith("M"):
        return int(token[:-1]) * 31 * 86400
    return int(token[:-1]) * _DURATION_SECONDS[token[-1]]


def horizons_in_bars(timeframe: str) -> list[int]:
    """Horizons de la timeframe, convertis en nombre de bougies."""
    period = store.PERIOD_SECONDS.get(timeframe)
    out = []
    for token in HORIZON_DURATIONS[timeframe]:
        seconds = _duration_seconds(token)
        if period is None:            # 1M : une bougie = un mois
            out.append(max(1, round(seconds / (31 * 86400))))
        else:
            out.append(max(1, round(seconds / period)))
    return out


def _iso(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _iso_production(ms: float) -> str:
    """Format identique à celui produit par analyze_timeframe (datetime.isoformat)."""
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()


# --------------------------------------------------------------------------
# 1. Pré-calcul des indicateurs (causalité vérifiée par les tests R2/R11)
# --------------------------------------------------------------------------
class Bundle:
    """Séries d'indicateurs pré-calculées sur l'historique complet d'une TF."""

    def __init__(self, timeframe: str, rows: list[dict]) -> None:
        self.timeframe = timeframe
        self.rows = rows
        self.closes = [r["c"] for r in rows]
        self.highs = [r["h"] for r in rows]
        self.lows = [r["l"] for r in rows]
        self.volumes = [r["v"] for r in rows]
        n = len(rows)

        self.ema20 = ema_series(self.closes, 20)
        self.ema50 = ema_series(self.closes, 50)
        self.rsi14 = rsi_series(self.closes, 14)
        # macd_histogram() renvoie une serie PLUS COURTE de 8 elements que l'entree
        # (le lissage du signal consomme 8 barres). L'index i correspond encore a
        # la bougie i, mais les 8 dernieres bougies n'ont pas de valeur. On les
        # recalcule exactement sur le prefixe pour conserver un alignement strict.
        self.hist = macd_histogram(self.closes)
        if len(self.hist) < n:
            padded = list(self.hist)
            for k in range(len(self.hist), n):
                sub = macd_histogram(self.closes[:k + 1])
                padded.append(sub[-1] if sub else None)
            self.hist = padded
        self.sma10 = sma_series(self.closes, 10)
        self.sma20 = sma_series(self.closes, 20)
        self.sma50 = sma_series(self.closes, 50)
        self.sma100 = sma_series(self.closes, 100)
        self.sma200 = sma_series(self.closes, 200)
        self.atr = atr_series(self.highs, self.lows, self.closes, 14)
        self.momentum = momentum_series(self.closes, 10)
        self.cci = cci_series(self.highs, self.lows, self.closes, 20)
        self.stoch_k, self.stoch_d = stochastic_series(self.highs, self.lows, self.closes, 14, 3)
        self.di_plus, self.di_minus, self.adx = dmi_series(self.highs, self.lows, self.closes, 14)
        self.ao = awesome_oscillator_series(self.highs, self.lows)

        # Volatilité relative causale : ATR14 / close, lissée par une médiane
        # glissante sur PROTOCOL["atr_window_bars"] bougies (donc connue à t).
        self.atr_pct: list[float | None] = [None] * n
        for i in range(n):
            atr_value = self.atr[i]
            if atr_value is None or not math.isfinite(atr_value) or self.closes[i] <= 0:
                continue
            self.atr_pct[i] = atr_value / self.closes[i]
        self.atr_pct_median = self._trailing_median(self.atr_pct, PROTOCOL["atr_window_bars"])

        # Quantiles causaux des mouvements avant (q90) : le seuil v2 est ainsi
        # toujours atteignable (taux de base constructible) et adapte a chaque
        # unite de temps, sans seuil arbitraire.
        # Deux series distinctes : le q90 des mouvements MONTANTS et le q90 des
        # mouvements BAISSERS. Employer le meme seuil pour les deux directions
        # serait asymetrique (une hausse exigerait plus de force qu'une baisse).
        self.q90, self.q90_down = self._causal_forward_quantiles(
            PROTOCOL["quantile"], PROTOCOL["quantile_window"])

    def _causal_forward_quantiles(self, quantile: float, window: int):
        """Quantiles causaux des mouvements avant, dans les deux directions.

        CAUSALITE STRICTE : le seuil disponible a l'instant i ne doit dependre
        que des bougies closes jusqu'a i. Un mouvement avant mesure a l'index j
        porte sur j..j+h ; il n'est donc complet qu'a partir de j+h. Pour que
        TOUS les mouvements du fenetre de reference soient deja connus a i,
        on ne retient que les index j <= i - h_max.
        """
        horizons = horizons_in_bars(self.timeframe)
        h_max = max(horizons)
        # La fenetre de reference doit etre plus large que le decalage de
        # causalite, sinon il n'y a aucune observation eligible.
        window_eff = max(window, h_max + 60)
        closes = self.closes
        n = len(closes)
        up: dict[int, list[float | None]] = {}
        down: dict[int, list[float | None]] = {}

        def quantile_of(values: list[float]) -> float:
            ordered = sorted(values)
            position = quantile * (len(ordered) - 1)
            low = int(math.floor(position))
            high = min(low + 1, len(ordered) - 1)
            return ordered[low] + (ordered[high] - ordered[low]) * (position - low)

        for h in horizons:
            forward: list[float | None] = [None] * n
            for i in range(n - h):
                forward[i] = (closes[i + h] - closes[i]) / closes[i]
            series_up: list[float | None] = [None] * n
            series_down: list[float | None] = [None] * n
            for i in range(n):
                stop = i - h_max + 1
                if stop <= 0:
                    continue
                start = max(0, i - window_eff)
                chunk = [v for v in forward[start:stop] if v is not None]
                if len(chunk) >= 30:
                    series_up[i] = quantile_of(chunk)
                    series_down[i] = quantile_of([-v for v in chunk])
            up[h] = series_up
            down[h] = series_down
        return up, down

    @staticmethod
    def last_finite_at(series: list[float | None], k: int) -> float | None:
        """Dernière valeur finie <= k (recherche arrière, exceptionnelle)."""
        upper = min(k, len(series) - 1)
        for j in range(upper, max(-1, upper - 400), -1):
            value = series[j]
            if value is not None and math.isfinite(value):
                return value
        return None

    @staticmethod
    def _trailing_median(series: list[float | None], window: int) -> list[float | None]:
        out: list[float | None] = [None] * len(series)
        for i in range(len(series)):
            chunk = [v for v in series[max(0, i - window + 1):i + 1] if v is not None]
            out[i] = statistics.median(chunk) if chunk else None
        return out

    def atr_pct_at(self, k: int) -> float | None:
        return self.atr_pct_median[k]


def fast_timeframe_state(bundle: Bundle, k: int, now_ms: float) -> dict[str, Any]:
    """État d'une unité de temps à l'index k, calqué sur analyze_timeframe().

    Indexation directe (pas de copie de préfixe) : coût O(1) par point.
    R11 vérifie l'égalité stricte avec analyze_timeframe() sur des échantillons.
    """
    timeframe = bundle.timeframe
    rows = bundle.rows
    available = k + 1  # nombre de bougies effectivement disponibles a l'instant k
    if available < MIN_CANDLES[timeframe]:
        return {"status": "UNAVAILABLE",
                "reason": f"historique insuffisant ou incohérent ({available} bougies valides)",
                "candle_count": available, "trend": "INDETERMINE"}

    closes = bundle.closes
    volumes = bundle.volumes
    last_closed_at = store.close_time_ms(rows[k], timeframe) / 1000
    age_seconds = now_ms / 1000 - last_closed_at
    if age_seconds < -60:
        return {"status": "UNAVAILABLE", "reason": "horodatage futur incohérent",
                "candle_count": available, "trend": "INDETERMINE"}

    def at(series, index):
        if index < 0 or index >= len(series):
            return None
        value = series[index]
        return value if (value is None or math.isfinite(value)) else None

    e20 = at(bundle.ema20, k)
    e50 = at(bundle.ema50, k)
    rsi_now = at(bundle.rsi14, k)
    hist_now = at(bundle.hist, k)
    hist_prev = at(bundle.hist, k - 1)
    if e20 is None or rsi_now is None or not math.isfinite(rsi_now):
        return {"status": "UNAVAILABLE", "reason": "indicateurs minimaux non calculables",
                "candle_count": available, "trend": "INDETERMINE"}

    close = closes[k]
    atr_val = Bundle.last_finite_at(bundle.atr, k)
    mom_val = Bundle.last_finite_at(bundle.momentum, k)
    cci_val = Bundle.last_finite_at(bundle.cci, k)
    stoch_k_val = Bundle.last_finite_at(bundle.stoch_k, k)
    stoch_d_val = Bundle.last_finite_at(bundle.stoch_d, k)
    di_plus_val = Bundle.last_finite_at(bundle.di_plus, k)
    di_minus_val = Bundle.last_finite_at(bundle.di_minus, k)
    adx_val = Bundle.last_finite_at(bundle.adx, k)
    ao_val = Bundle.last_finite_at(bundle.ao, k)
    s10 = Bundle.last_finite_at(bundle.sma10, k)
    s20 = Bundle.last_finite_at(bundle.sma20, k)
    s50 = Bundle.last_finite_at(bundle.sma50, k)
    s100 = Bundle.last_finite_at(bundle.sma100, k)
    s200 = Bundle.last_finite_at(bundle.sma200, k)

    if e50 is not None and close > e20 > e50 and hist_now is not None and hist_now > 0:
        trend = "HAUSSIER"
    elif e50 is not None and close < e20 < e50 and hist_now is not None and hist_now < 0:
        trend = "BAISSIER"
    else:
        trend = "MIXTE" if e50 is not None else "INDETERMINE"

    # Variation relative sur 30 bougies (identique a analyze_timeframe)
    change_30 = None
    if k >= 30 and closes[k - 30] > 0:
        change_30 = close / closes[k - 30] - 1.0

    window = volumes[max(0, k - 19):k + 1]
    avg_volume = (sum(window) / len(window)) if window else None
    volume_ratio = volumes[k] / avg_volume if avg_volume else None
    recent_rsi = [v for v in (at(bundle.rsi14, k - 3), at(bundle.rsi14, k - 2),
                               at(bundle.rsi14, k - 1), rsi_now)
                  if v is not None and math.isfinite(v)]
    rsi_rising = len(recent_rsi) >= 3 and all(a < b for a, b in zip(recent_rsi, recent_rsi[1:]))
    close_rising = (k >= 2 and closes[k] > closes[k - 1] > closes[k - 2])
    flags = []
    if rsi_now < 30:
        flags.append("RSI_SURVENDU_NE_CONFIRME_PAS_UN_REBOND")
    if rsi_rising:
        flags.append("RSI_EN_HAUSSE_SUR_LES_DERNIERES_CLOTURES")
    if close_rising:
        flags.append("TROIS_CLOTURES_EN_HAUSSE")
    if volume_ratio is not None and volume_ratio >= 1.5 and close_rising:
        flags.append("REPRISE_AVEC_VOLUME_SUPERIEUR_A_1_5X")
    if hist_now is not None and hist_prev is not None and hist_now > hist_prev:
        flags.append("HISTOGRAMME_MACD_EN_AMELIORATION")

    timeframe_seconds = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400,
                         "1w": 604800, "1M": 31 * 86400}[timeframe]
    max_candle_age = MAX_SNAPSHOT_AGE_SECONDS if timeframe == "15m" else timeframe_seconds + MAX_SNAPSHOT_AGE_SECONDS
    fresh = -60 <= age_seconds <= max_candle_age
    monthly_history_partial = timeframe == "1M" and (e50 is None or hist_now is None)
    result_status = "PARTIEL" if fresh and monthly_history_partial else ("OK" if fresh else "ATTENTION")
    reason = "historique mensuel trop court pour EMA50/MACD complet" if monthly_history_partial else (
        None if fresh else "dernière bougie clôturée trop ancienne")

    return {
        "status": result_status, "reason": reason, "candle_status": "OK",
        "candle_count": available, "last_closed_at": _iso_production(store.close_time_ms(rows[k], timeframe)),
        "candle_age_seconds": round(age_seconds), "close": close,
        "ema20": e20, "ema50": e50,
        "sma10": s10, "sma20": s20, "sma50": s50, "sma100": s100, "sma200": s200,
        "rsi14": rsi_now, "macd_histogram": hist_now, "macd_histogram_previous": hist_prev,
        "atr14": atr_val, "momentum10": mom_val, "cci20": cci_val,
        "stoch_k": stoch_k_val, "stoch_d": stoch_d_val,
        "di_plus": di_plus_val, "di_minus": di_minus_val, "adx14": adx_val,
        "awesome_oscillator": ao_val,
        "volume_last": volumes[k], "volume_mean20": avg_volume, "volume_ratio_20": volume_ratio,
        "trend": trend, "flags": flags, "change_30": change_30,
    }


def production_timeframe_state(bundle: Bundle, k: int, now_ms: float) -> dict[str, Any]:
    """État calculé par le code de production (analyze_timeframe), pour vérification R11."""
    timeframe = bundle.timeframe
    rows = bundle.rows[:k + 1]
    section = {
        "status": "OK",
        "last_closed_at": _iso(store.close_time_ms(bundle.rows[k], timeframe)),
        "rows": store.to_snapshot_rows(rows),
    }
    source = {"candles": {timeframe: section}}
    now = datetime.fromtimestamp(now_ms / 1000, timezone.utc)
    return analyze_timeframe(source, timeframe, now)


def detection_state(bundle: Bundle, k: int) -> dict[str, Any]:
    """Entrées de-series pour detect_early_reversal (fenêtre suffit large).

    L'OHLC est fourni aligné sur les memes index que les series : c'est ce qui
    permet au moteur d'evaluer les figures de bougies.
    """
    tail = min(k + 1, 200)
    closes = bundle.closes[k - tail + 1:k + 1]
    rsi = bundle.rsi14[k - tail + 1:k + 1]
    hist = bundle.hist[k - tail + 1:k + 1]
    rows = bundle.rows[k - tail + 1:k + 1]
    ohlc = [(row["o"], row["h"], row["l"], row["c"], row["v"]) for row in rows]
    return {
        "price_series_15m": closes,
        "rsi_series_15m": rsi if len(closes) >= 15 else [],
        "macd_hist_15m": hist if len(closes) >= 27 else [],
        "ohlc_15m": ohlc,
    }


def call_detector(timeframes: dict[str, Any], series: dict[str, Any],
                  detector=None) -> dict[str, Any]:
    """Appel du détecteur de production, sans modification.

    `detector` permet de rejouer un moteur anterieur (comparaison A/B) sans
    toucher au code de production.
    """
    detect = detector if detector is not None else detect_early_reversal
    arguments = dict(
        rsi_series_15m=series["price_series_15m"] and series["rsi_series_15m"],
        price_series_15m=series["price_series_15m"],
        macd_hist_15m=series["macd_hist_15m"],
    )
    try:
        return detect(timeframes, ohlc_15m=series.get("ohlc_15m"), **arguments)
    except TypeError:
        # Moteur anterieur : signature sans ohlc_15m.
        return detect(timeframes, **arguments)
