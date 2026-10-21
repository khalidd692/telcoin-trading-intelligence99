"""Conservative, read-only multi-timeframe TEL analysis.

This is a deterministic analysis layer, not an autonomous trading agent:
it never places orders and never turns oversold conditions into a buy signal.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from collector.tel_collector import compute_snapshot_fingerprint

TIMEFRAMES = ("15m", "1h", "4h", "1d", "1w", "1M")
MAX_SNAPSHOT_AGE_SECONDS = 20 * 60
CRITICAL_LEVEL = 0.001526
MIN_CANDLES = {"15m": 55, "1h": 55, "4h": 55, "1d": 55, "1w": 55, "1M": 15}
# Duration of each timeframe, used to decide whether a candle is closed.
# 1M is handled separately because a calendar month has a variable length.
TIMEFRAME_SECONDS = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800, "1M": None}


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def candle_close_time(open_time: datetime, timeframe: str) -> datetime | None:
    """Return the close time of a candle opened at `open_time` for `timeframe`.

    The rule is purely temporal and verifiable: a fixed duration for every
    timeframe except 1M, which uses the end of the calendar month.
    """
    seconds = TIMEFRAME_SECONDS.get(timeframe)
    if seconds is not None:
        return open_time + timedelta(seconds=seconds)
    if timeframe == "1M":
        year = open_time.year + (1 if open_time.month == 12 else 0)
        month = 1 if open_time.month == 12 else open_time.month + 1
        return datetime(year, month, 1, tzinfo=timezone.utc)
    return None


def is_candle_closed(open_time: datetime, timeframe: str, now: datetime) -> bool:
    """True when the candle is closed at `now` (its close time is in the past).

    A candle whose close time is in the future is still forming and must never
    contribute to an indicator, a signal or an evidence item.
    """
    close_time = candle_close_time(open_time, timeframe)
    if close_time is None:
        return False
    return close_time <= now


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def ema_series(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    alpha = 2.0 / (period + 1)
    current = mean(values[:period])
    result = [float("nan")] * (period - 1) + [current]
    for value in values[period:]:
        current = alpha * value + (1 - alpha) * current
        result.append(current)
    return result


def rsi_series(values: list[float], period: int = 14) -> list[float]:
    result = [float("nan")] * len(values)
    if len(values) <= period:
        return result
    for end in range(period, len(values)):
        changes = [values[i] - values[i - 1] for i in range(end - period + 1, end + 1)]
        gains = mean([max(change, 0.0) for change in changes])
        losses = mean([max(-change, 0.0) for change in changes])
        result[end] = 100.0 if losses == 0 and gains > 0 else (
            50.0 if losses == 0 else 100.0 - 100.0 / (1.0 + gains / losses)
        )
    return result


def macd_histogram(values: list[float]) -> list[float]:
    fast, slow = ema_series(values, 12), ema_series(values, 26)
    if not fast or not slow:
        return []
    macd = [float("nan") if not (math.isfinite(a) and math.isfinite(b)) else a - b for a, b in zip(fast, slow)]
    valid_start = next((i for i, value in enumerate(macd) if math.isfinite(value)), len(macd))
    valid_macd = macd[valid_start:]
    signal = ema_series(valid_macd, 9)
    result = [float("nan")] * valid_start
    result.extend([
        (m - s) if math.isfinite(m) and math.isfinite(s) else float("nan")
        for m, s in zip(valid_macd, signal)
    ])
    return result


def sma_series(values: list[float], period: int) -> list[float]:
    """Simple Moving Average with NaN for insufficient history."""
    if len(values) < period:
        return []
    result = [float("nan")] * (period - 1)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1:i + 1]
        result.append(mean(window))
    return result


def atr_series(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    """Average True Range using Wilder's smoothing."""
    if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
        return []
    true_ranges = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
        true_ranges.append(tr)
    # First ATR is simple average of first period TRs
    atr = mean(true_ranges[:period])
    result = [float("nan")] * period + [atr]
    # Wilder's smoothing for subsequent values
    for tr in true_ranges[period:]:
        atr = (atr * (period - 1) + tr) / period
        result.append(atr)
    return result


def momentum_series(values: list[float], period: int = 10) -> list[float]:
    """Momentum oscillator (current price - price N periods ago)."""
    if len(values) < period:
        return []
    result = [float("nan")] * period
    for i in range(period, len(values)):
        result.append(values[i] - values[i - period])
    return result


def cci_series(highs: list[float], lows: list[float], closes: list[float], period: int = 20) -> list[float]:
    """Commodity Channel Index."""
    if len(highs) < period or len(lows) < period or len(closes) < period:
        return []
    result = [float("nan")] * (period - 1)
    for i in range(period - 1, len(highs)):
        typical_prices = [(highs[j] + lows[j] + closes[j]) / 3 for j in range(i - period + 1, i + 1)]
        sma_tp = mean(typical_prices)
        mean_deviation = mean([abs(tp - sma_tp) for tp in typical_prices])
        if mean_deviation == 0:
            result.append(0.0)
        else:
            cci = (typical_prices[-1] - sma_tp) / (0.015 * mean_deviation)
            result.append(cci)
    return result


def stochastic_series(highs: list[float], lows: list[float], closes: list[float], 
                      k_period: int = 14, d_period: int = 3) -> tuple[list[float], list[float]]:
    """Stochastic oscillator %K and %D."""
    if len(highs) < k_period or len(lows) < k_period or len(closes) < k_period:
        return [], []
    k_values = [float("nan")] * (k_period - 1)
    for i in range(k_period - 1, len(highs)):
        window_high = max(highs[i - k_period + 1:i + 1])
        window_low = min(lows[i - k_period + 1:i + 1])
        if window_high == window_low:
            k_values.append(50.0)  # Neutral when no range
        else:
            k_fast = 100 * (closes[i] - window_low) / (window_high - window_low)
            k_values.append(k_fast)
    # %D is SMA of %K
    d_values = sma_series(k_values, d_period)
    return k_values, d_values


def dmi_series(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> tuple[list[float], list[float], list[float]]:
    """DMI+ and DMI- using Wilder's smoothing."""
    if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
        return [], [], []
    plus_dm = []
    minus_dm = []
    tr = []
    for i in range(1, len(highs)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        if up > down and up > 0:
            plus_dm.append(up)
        else:
            plus_dm.append(0.0)
        if down > up and down > 0:
            minus_dm.append(down)
        else:
            minus_dm.append(0.0)
        tr_val = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
        tr.append(tr_val)
    # Smooth using Wilder's method
    def wilder_smooth(values: list[float], period: int) -> list[float]:
        if not values:
            return []
        smoothed = [mean(values[:period])]
        for v in values[period:]:
            smoothed.append((smoothed[-1] * (period - 1) + v) / period)
        return smoothed
    smoothed_tr = wilder_smooth(tr, period)
    smoothed_plus_dm = wilder_smooth(plus_dm, period)
    smoothed_minus_dm = wilder_smooth(minus_dm, period)
    # Calculate DI+ and DI-
    di_plus = []
    di_minus = []
    for tr_val, pdm, mdm in zip(smoothed_tr, smoothed_plus_dm, smoothed_minus_dm):
        if tr_val == 0:
            di_plus.append(0.0)
            di_minus.append(0.0)
        else:
            di_plus.append(100 * pdm / tr_val)
            di_minus.append(100 * mdm / tr_val)
    # Calculate DX and ADX
    dx = []
    for dp, dm in zip(di_plus, di_minus):
        if dp + dm == 0:
            dx.append(0.0)
        else:
            dx.append(100 * abs(dp - dm) / (dp + dm))
    adx = wilder_smooth(dx, period)
    # Pad with NaN to align with original data length
    # di_plus and di_minus have len(smoothed_tr) values
    # adx has len(dx) values after smoothing
    # We need all to have len(highs)
    nan_prefix_di = [float("nan")] * period
    # ADX needs additional period for DX smoothing
    adx_start = period * 2 - 1
    nan_prefix_adx = [float("nan")] * adx_start
    # Ensure lengths match
    result_di_plus = nan_prefix_di + di_plus + [float("nan")] * (len(highs) - len(nan_prefix_di) - len(di_plus))
    result_di_minus = nan_prefix_di + di_minus + [float("nan")] * (len(highs) - len(nan_prefix_di) - len(di_minus))
    result_adx = nan_prefix_adx + adx + [float("nan")] * (len(highs) - len(nan_prefix_adx) - len(adx))
    return result_di_plus, result_di_minus, result_adx


def awesome_oscillator_series(highs: list[float], lows: list[float]) -> list[float]:
    """Awesome Oscillator (SMA 5 of median price - SMA 34 of median price)."""
    if len(highs) < 34 or len(lows) < 34:
        return []
    median_prices = [(h + l) / 2 for h, l in zip(highs, lows)]
    sma5 = sma_series(median_prices, 5)
    sma34 = sma_series(median_prices, 34)
    if not sma5 or not sma34:
        return []
    # Align arrays - both have different NaN prefixes
    start_idx = max(next((i for i, v in enumerate(sma5) if math.isfinite(v)), len(sma5)),
                    next((i for i, v in enumerate(sma34) if math.isfinite(v)), len(sma34)))
    result = [float("nan")] * start_idx
    for i in range(start_idx, len(median_prices)):
        if i < len(sma5) and i < len(sma34) and math.isfinite(sma5[i]) and math.isfinite(sma34[i]):
            result.append(sma5[i] - sma34[i])
        else:
            result.append(float("nan"))
    return result


# ============================================================================
# EARLY REVERSAL DETECTION FUNCTIONS
# ============================================================================

def _is_finite(value: Any) -> bool:
    """True only for finite real numbers.

    None, NaN, +/-inf and non-numeric values are rejected without raising.
    """
    try:
        return math.isfinite(value)
    except (TypeError, ValueError):
        return False


def _extreme_with_rsi(price_window: list[float], rsi_window: list[float], bullish: bool) -> tuple[float, float] | None:
    """Return (price extreme, RSI at that extreme) for a price window.

    The most recent occurrence of the extreme wins, so duplicated prices are
    resolved on the latest bar instead of the first one. Occurrences whose RSI
    is not finite (NaN/inf) are skipped explicitly: a missing RSI never yields
    a comparison and never produces a divergence.
    """
    candidates = [(offset, price) for offset, price in enumerate(price_window) if _is_finite(price)]
    if not candidates:
        return None
    target = min(price for _, price in candidates) if bullish else max(price for _, price in candidates)
    for offset, price in reversed(candidates):
        if price != target:
            continue
        rsi_value = rsi_window[offset]
        if not _is_finite(rsi_value):
            continue
        return price, rsi_value
    return None


def _align_divergence_series(rsi_series: list[float], price_series: list[float]) -> tuple[list[float], list[float]]:
    """Align the RSI and price series on their common trailing part.

    The last element of each series describes the same (most recent) bar, so
    the common tail is the only region where an RSI value and a price may be
    compared. Series of different lengths are therefore truncated to their
    common end instead of being indexed blindly: this removes any risk of
    IndexError and keeps the RSI/price pairing valid.
    """
    if not rsi_series or not price_series:
        return [], []
    common = min(len(rsi_series), len(price_series))
    return list(rsi_series[-common:]), list(price_series[-common:])


def _divergence_windows(rsi_series: list[float], price_series: list[float], lookback: int) -> tuple[list[float], list[float], list[float], list[float]] | None:
    """Split the series into (recent, previous) price/RSI windows.

    Returns None when the parameters or the history are too short to build
    both windows safely.
    """
    if isinstance(lookback, bool) or not isinstance(lookback, (int, float)):
        return None
    try:
        lookback = int(lookback)
    except (TypeError, ValueError, OverflowError):
        return None
    if lookback < 1:
        return None
    aligned_rsi, aligned_price = _align_divergence_series(rsi_series, price_series)
    n = len(aligned_price)
    # Both the recent and the previous window must be complete: a truncated
    # previous window would shift the RSI lookup into a negative index and read
    # bars that belong to the recent window (i.e. look into the future).
    if n < 2 * lookback:
        return None
    return (
        aligned_price[-lookback:], aligned_rsi[-lookback:],
        aligned_price[-2 * lookback:-lookback], aligned_rsi[-2 * lookback:-lookback],
    )


def has_rsi_divergence(rsi_series: list[float], price_series: list[float], lookback: int = 5) -> bool:
    """Detect bullish divergence: price makes lower low but RSI makes higher low."""
    windows = _divergence_windows(rsi_series, price_series, lookback)
    if windows is None:
        return False
    recent_price, recent_rsi, prev_price, prev_rsi = windows
    recent = _extreme_with_rsi(recent_price, recent_rsi, bullish=True)
    previous = _extreme_with_rsi(prev_price, prev_rsi, bullish=True)
    if recent is None or previous is None:
        return False
    recent_price_low, recent_rsi_at_low = recent
    prev_price_low, prev_rsi_at_low = previous
    # Bullish divergence: price lower, RSI higher
    return recent_price_low < prev_price_low and recent_rsi_at_low > prev_rsi_at_low


def has_bearish_divergence(rsi_series: list[float], price_series: list[float], lookback: int = 5) -> bool:
    """Detect bearish divergence: price makes higher high but RSI makes lower high.

    The RSI and price series are aligned on their common trailing part, and a
    divergence is only reported when both the recent and the previous window
    are complete. Degenerate inputs (empty series, NaN, truncated history,
    invalid lookback) return False instead of raising or reading future bars.
    """
    windows = _divergence_windows(rsi_series, price_series, lookback)
    if windows is None:
        return False
    recent_price, recent_rsi, prev_price, prev_rsi = windows
    recent = _extreme_with_rsi(recent_price, recent_rsi, bullish=False)
    previous = _extreme_with_rsi(prev_price, prev_rsi, bullish=False)
    if recent is None or previous is None:
        return False
    recent_price_high, recent_rsi_at_high = recent
    prev_price_high, prev_rsi_at_high = previous
    # Bearish divergence: price higher, RSI lower
    return recent_price_high > prev_price_high and recent_rsi_at_high < prev_rsi_at_high


def has_hammer_pattern(high: float, low: float, open_price: float, close: float) -> bool:
    """Detect hammer candle (long lower wick, small body at top)."""
    body = abs(close - open_price)
    lower_wick = min(open_price, close) - low
    upper_wick = high - max(open_price, close)
    total_range = high - low
    if total_range == 0:
        return False
    # Hammer: lower wick at least 2x body, upper wick small, body in upper third
    return (lower_wick >= 2 * body and 
            upper_wick <= body and 
            lower_wick / total_range >= 0.6)


def has_engulfing_bullish(prev_high: float, prev_low: float, prev_open: float, prev_close: float,
                          curr_high: float, curr_low: float, curr_open: float, curr_close: float) -> bool:
    """Detect bullish engulfing pattern."""
    prev_body_bearish = prev_close < prev_open
    curr_body_bullish = curr_close > curr_open
    return (prev_body_bearish and 
            curr_body_bullish and 
            curr_open <= prev_close and 
            curr_close >= prev_open)


def is_momentum_improving(momentum_series: list[float], lookback: int = 3) -> bool:
    """Check if momentum is consistently improving (rising)."""
    if len(momentum_series) < lookback + 1:
        return False
    recent = [v for v in momentum_series[-lookback:] if math.isfinite(v)]
    return len(recent) >= 2 and all(a < b for a, b in zip(recent, recent[1:]))


def is_macd_improving(macd_hist_series: list[float], lookback: int = 3) -> bool:
    """Check if MACD histogram is improving (rising, even if negative)."""
    if len(macd_hist_series) < lookback + 1:
        return False
    recent = [v for v in macd_hist_series[-lookback:] if math.isfinite(v)]
    return len(recent) >= 2 and all(a < b for a, b in zip(recent, recent[1:]))


def has_level_rejection(high: float, low: float, open_price: float, close: float, level: float, tolerance: float = 0.001) -> bool:
    """Check if price rejected a level (long wick near level)."""
    # Price touched level but closed away from it
    touched_level = low <= level * (1 + tolerance) and high >= level * (1 - tolerance)
    if not touched_level:
        return False
    # Wick at least 50% of body
    body = abs(close - open_price)
    lower_wick = min(open_price, close) - low
    return lower_wick >= 0.5 * body


def is_downtrend_ending(closes: list[float], lookback: int = 5) -> bool:
    """Check if a downtrend is ending (series of declines followed by rise)."""
    if len(closes) < lookback + 2:
        return False
    # Check for at least 3 declines then a rise
    declines = sum(1 for i in range(len(closes) - lookback, len(closes) - 1) if closes[i] < closes[i - 1])
    last_rise = closes[-1] > closes[-2]
    return declines >= 3 and last_rise


def is_uptrend_ending(closes: list[float], lookback: int = 5) -> bool:
    """Check if an uptrend is ending (series of rises followed by decline)."""
    if len(closes) < lookback + 2:
        return False
    rises = sum(1 for i in range(len(closes) - lookback, len(closes) - 1) if closes[i] > closes[i - 1])
    last_decline = closes[-1] < closes[-2]
    return rises >= 3 and last_decline


# ============================================================================
# EARLY REVERSAL ENGINE (v2)
# ============================================================================
#
# The engine is a pure function of the data available at the current bar. It
# reconstructs, from the recent history, the state of the most recent reversal
# "setup", so that three situations can be distinguished:
#
#   ALERTE_PRÉCOCE : a reversal setup exists and is still waiting for
#                     confirmation (the move has generally not started yet).
#   CONFIRMATION    : the setup is still valid AND independent evidence says
#                     the reversal has started.
#   INVALIDATION    : the level that anchored the setup has been broken, so the
#                     scenario it described no longer holds.
#   ATTENDRE        : no setup, ambiguous setup, or not enough evidence.
#
# Design rules (all causal, deterministic, no fixed price level anywhere):
#   * the direction comes from the structural extreme that anchors the setup,
#     never from a run of consecutive candles;
#   * a setup is created at a structural extreme where momentum turns;
#   * an alert needs at least one INDEPENDENT family of evidence
#     (structure / volume / context) besides the momentum turn of the setup;
#   * an alignment with the higher timeframes is NOT reversal evidence: a
#     trend that already goes the same way says nothing about a reversal. It
#     is reported as an observation only;
#   * the invalidation level is the setup's own anchor (plus an ATR tolerance),
#     never a hardcoded price.
#
# The setup is reconstructed by scanning the recent bars backwards, so the
# engine never needs any state carried between calls: it is replayable on
# history and produces exactly the same answer for the same inputs.

REVERSAL_PARAMS: dict[str, Any] = {
    "extreme_window": 20,          # bars searched for the structural extreme
    "turn_bars": 3,                # bars used to confirm a momentum turn
    "setup_window": 16,            # bars during which a setup stays relevant
    "volume_climax_ratio": 1.5,    # volume at the extreme / median of the previous bars
    "volume_lookback": 20,
    "break_tolerance_atr": 0.25,   # ATR tolerance allowed before invalidation
    "min_turn_atr": 0.05,          # amplitude minimale d'un retournement, en fraction de l'ATR
    "min_rsi_turn": 2.0,           # amplitude minimale d'un retournement de RSI, en points
    "objective_swing_window": 100, # bars used for the swing objective
    "rsi_oversold": 30.0,
    "rsi_overbought": 70.0,
    "adx_weak": 20.0,
    "momentum_period": 10,
    "regime_band": 0.05,          # |variation 1d 30 j| < 5 % => regime neutre
}

# Families of evidence. Two pieces of evidence belonging to the same family are
# correlated and must never be counted as two independent proofs.
EVIDENCE_FAMILIES = ("structure", "momentum", "volume", "context")


def _series_value(series: Any, index: int) -> float | None:
    """Finite value at `index`, or None when the index is out of range or the
    value is missing / NaN / infinite."""
    if not series or index < 0 or index >= len(series):
        return None
    value = series[index]
    return value if _is_finite(value) else None


def _extreme_index(values: list[float], index: int, window: int, find_low: bool) -> tuple[int, float] | None:
    """Index and value of the lowest (or highest) value of the window ending at
    `index`. Strictly backward-looking."""
    start = max(0, index - window + 1)
    if index - start < 2:
        return None
    best: tuple[int, float] | None = None
    for j in range(start, index + 1):
        value = _series_value(values, j)
        if value is None:
            continue
        if best is None or (value < best[1] if find_low else value > best[1]):
            best = (j, value)
    return best


def _momentum_turns(rsi_series: list[float], macd_series: list[float], closes: list[float],
                    index: int, bullish: bool, params: dict[str, Any],
                    atr: float | None = None) -> list[dict[str, Any]]:
    """Momentum turns detectable at `index` (uses bars <= index only).

    All three readings belong to the same family ("momentum"): they are
    correlated and must be counted once.

    A turn must be MATERIAL. On a flat or perfectly linear price series the
    MACD histogram converges to zero and its residual variations are pure
    floating point noise (1e-21 on a 0.0017 price); reading them as a turn
    would create alerts out of nothing. The amplitude of the turn is therefore
    required to exceed a fraction of the ATR (and the RSI rise a minimum
    number of points).
    """
    bars = params["turn_bars"]
    period = params["momentum_period"]
    if index - bars < 0:
        return []
    turns: list[dict[str, Any]] = []
    min_turn = params["min_turn_atr"] * (atr if atr and atr > 0 else 0.0)
    min_rsi = params["min_rsi_turn"]

    def window(series: list[float]) -> list[float] | None:
        """bars+1 values ending at `index` (the helpers need lookback+1 points)."""
        values = []
        for j in range(index - bars, index + 1):
            value = _series_value(series, j)
            if value is None:
                return None
            values.append(value)
        return values

    hist = window(macd_series)
    if hist is not None:
        signed_hist = hist if bullish else [-v for v in hist]
        amplitude = signed_hist[-1] - signed_hist[0]
        if is_macd_improving(signed_hist, bars) and (min_turn <= 0 or amplitude >= min_turn):
            turns.append({"category": "momentum", "type": "macd_histogram_turn",
                          "amplitude": round(amplitude, 12)})

    momentum = []
    complete = True
    for j in range(index - bars, index + 1):
        current = _series_value(closes, j)
        base = _series_value(closes, j - period)
        if current is None or base is None:
            complete = False
            break
        momentum.append(current - base)
    if complete:
        signed_momentum = momentum if bullish else [-v for v in momentum]
        amplitude = signed_momentum[-1] - signed_momentum[0]
        if is_momentum_improving(signed_momentum, bars) and (min_turn <= 0 or amplitude >= min_turn):
            turns.append({"category": "momentum", "type": "momentum_turn",
                          "amplitude": round(amplitude, 12)})

    rsi_values = window(rsi_series)
    if rsi_values is not None:
        signed_rsi = rsi_values if bullish else [-v for v in rsi_values]
        amplitude = signed_rsi[-1] - signed_rsi[0]
        if is_momentum_improving(signed_rsi, bars) and amplitude >= min_rsi:
            turns.append({"category": "momentum", "type": "rsi_turn",
                          "amplitude": round(amplitude, 3)})

    return turns


def _setup_at(closes: list[float], highs: list[float] | None, lows: list[float] | None,
              rsi_series: list[float], macd_series: list[float], index: int,
              direction: str, params: dict[str, Any], atr: float | None = None) -> dict[str, Any] | None:
    """A reversal setup created at `index`, or None.

    A setup requires BOTH a structural extreme (the bar is the extreme of its
    window) and a material momentum turn detectable on that very bar.
    """
    bullish = direction == "HAUSSIER"
    values = lows if (bullish and lows) else (highs if (not bullish and highs) else closes)
    extreme = _extreme_index(values, index, params["extreme_window"], bullish)
    if extreme is None or extreme[0] != index:
        return None
    turns = _momentum_turns(rsi_series, macd_series, closes, index, bullish, params, atr)
    if not turns:
        return None
    return {"index": index, "direction": direction, "anchor": extreme[1], "turns": turns}


def _structure_evidence(closes: list[float], highs: list[float] | None, lows: list[float] | None,
                        opens: list[float] | None, rsi_series: list[float], index: int,
                        direction: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Structure evidence at the setup bar: divergence and candle figures.

    The candle figures are only evaluated when the raw OHLC is available and
    aligned with the price series; otherwise they are simply absent (and the
    caller reports it in missing_data).
    """
    bullish = direction == "HAUSSIER"
    out: list[dict[str, Any]] = []
    lookback = 5
    if index - 2 * lookback + 1 >= 0:
        rsi_window = rsi_series[index - 2 * lookback + 1:index + 1]
        price_window = closes[index - 2 * lookback + 1:index + 1]
        if len(rsi_window) == len(price_window) == 2 * lookback:
            if bullish and has_rsi_divergence(rsi_window, price_window, lookback):
                out.append({"category": "structure", "type": "bullish_rsi_divergence"})
            elif not bullish and has_bearish_divergence(rsi_window, price_window, lookback):
                out.append({"category": "structure", "type": "bearish_rsi_divergence"})

    if not (highs and lows and opens and index < len(highs) and index < len(lows) and index < len(opens)):
        return out
    high, low, open_price = highs[index], lows[index], opens[index]
    close_price = closes[index]
    if bullish and has_hammer_pattern(high, low, open_price, close_price):
        out.append({"category": "structure", "type": "hammer_pattern"})
    if not bullish and has_hammer_pattern(high, low, open_price, close_price):
        out.append({"category": "structure", "type": "hanging_man_pattern"})
    if index >= 1:
        if bullish and has_engulfing_bullish(highs[index - 1], lows[index - 1], opens[index - 1], closes[index - 1],
                                             high, low, open_price, close_price):
            out.append({"category": "structure", "type": "bullish_engulfing"})
        elif not bullish and has_engulfing_bullish(highs[index - 1], lows[index - 1], opens[index - 1], closes[index - 1],
                                                   high, low, open_price, close_price):
            out.append({"category": "structure", "type": "bearish_engulfing"})
        # rejection of the previous structural level
        level_window = max(1, params["extreme_window"])
        start = max(0, index - 2 * level_window)
        stop = max(start + 1, index - level_window)
        if stop > start:
            if bullish:
                level = min(v for v in lows[start:stop] if _is_finite(v))
                if has_level_rejection(high, low, open_price, close_price, level):
                    out.append({"category": "structure", "type": "support_rejection", "level": level})
            else:
                level = max(v for v in highs[start:stop] if _is_finite(v))
                if has_level_rejection(high, low, open_price, close_price, level):
                    out.append({"category": "structure", "type": "resistance_rejection", "level": level})
    return out


def _volume_evidence(volumes: list[float] | None, index: int, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Volume capitulation at the extreme bar (an exhaustion of the move)."""
    if not volumes or index < 1:
        return []
    current = _series_value(volumes, index)
    if current is None:
        return []
    lookback = params["volume_lookback"]
    start = max(0, index - lookback)
    history = [v for v in volumes[start:index] if _is_finite(v)]
    if len(history) < 5:
        return []
    reference = statistics.median(history)
    if reference <= 0:
        return []
    ratio = current / reference
    if ratio >= params["volume_climax_ratio"]:
        return [{"category": "volume", "type": "volume_climax", "ratio": round(ratio, 3)}]
    return []


def _context_evidence(timeframes: dict[str, Any], direction: str,
                       params: dict[str, Any]) -> list[dict[str, Any]]:
    """Higher timeframe conditions that make a reversal plausible.

    Only states that argue FOR a reversal are used here. A higher timeframe
    that already trends the same way is reported separately as an observation
    and never counted as reversal evidence.
    """
    bullish = direction == "HAUSSIER"
    out: list[dict[str, Any]] = []
    for timeframe, key in (("4h", "higher_timeframe"), ("1h", "intermediate_timeframe"),
                           ("1d", "higher_timeframe"), ("1w", "higher_timeframe")):
        state = timeframes.get(timeframe)
        if not isinstance(state, dict) or state.get("status") not in ("OK", "PARTIEL"):
            continue
        rsi_value = state.get("rsi14")
        if isinstance(rsi_value, (int, float)) and math.isfinite(rsi_value):
            if bullish and rsi_value < params["rsi_oversold"]:
                out.append({"category": "context", "type": f"{key}_oversold", "timeframe": timeframe,
                            "value": round(rsi_value, 2)})
            elif not bullish and rsi_value > params["rsi_overbought"]:
                out.append({"category": "context", "type": f"{key}_overbought", "timeframe": timeframe,
                            "value": round(rsi_value, 2)})
    state_4h = timeframes.get("4h")
    if isinstance(state_4h, dict) and state_4h.get("status") == "OK":
        adx_value = state_4h.get("adx14")
        if isinstance(adx_value, (int, float)) and math.isfinite(adx_value) and adx_value < params["adx_weak"]:
            out.append({"category": "context", "type": "weak_higher_timeframe_trend", "timeframe": "4h",
                        "adx": round(adx_value, 2)})
    return out


def _trend_observations(timeframes: dict[str, Any], direction: str) -> list[dict[str, Any]]:
    """Trend alignment is reported as an observation only: a higher timeframe
    that already goes the same way is not evidence of a reversal."""
    bullish = direction == "HAUSSIER"
    out: list[dict[str, Any]] = []
    for timeframe in ("1h", "4h", "1d", "1w", "1M"):
        state = timeframes.get(timeframe)
        if not isinstance(state, dict) or state.get("status") not in ("OK", "PARTIEL"):
            continue
        trend = state.get("trend")
        if trend == "INDETERMINE":
            continue
        if bullish and trend == "HAUSSIER":
            out.append({"type": "higher_timeframe_trend_same_direction", "timeframe": timeframe, "trend": trend})
        elif not bullish and trend == "BAISSIER":
            out.append({"type": "higher_timeframe_trend_same_direction", "timeframe": timeframe, "trend": trend})
        elif bullish and trend == "BAISSIER":
            out.append({"type": "higher_timeframe_trend_opposite", "timeframe": timeframe, "trend": trend})
        elif not bullish and trend == "HAUSSIER":
            out.append({"type": "higher_timeframe_trend_opposite", "timeframe": timeframe, "trend": trend})
    return out


def _confirmation_evidence(closes: list[float], highs: list[float] | None, lows: list[float] | None,
                           macd_series: list[float], index: int, setup_index: int,
                           direction: str, timeframes: dict[str, Any]) -> list[dict[str, Any]]:
    """Evidence that the reversal has actually started. Requires index > setup_index."""
    if index <= setup_index:
        return []
    bullish = direction == "HAUSSIER"
    out: list[dict[str, Any]] = []

    if highs and lows:
        # La jambe opposee au setup est constituee des barres STRICTEMENT
        # comprises entre le setup et la barre courante : la cassure est le
        # franchissement de cette jambe par la cloture courante.
        if bullish:
            leg = [v for v in highs[setup_index + 1:index] if _is_finite(v)]
            if leg and closes[index] > max(leg):
                out.append({"category": "structure", "type": "structure_break"})
        else:
            leg = [v for v in lows[setup_index + 1:index] if _is_finite(v)]
            if leg and closes[index] < min(leg):
                out.append({"category": "structure", "type": "structure_break"})

    if index - 2 >= 0:
        window = [_series_value(macd_series, j) for j in range(index - 2, index + 1)]
        if all(v is not None for v in window):
            if bullish and all(v > 0 for v in window):
                out.append({"category": "momentum", "type": "momentum_sustained"})
            elif not bullish and all(v < 0 for v in window):
                out.append({"category": "momentum", "type": "momentum_sustained"})

    state_1h = timeframes.get("1h")
    if isinstance(state_1h, dict) and state_1h.get("status") == "OK":
        macd_1h = state_1h.get("macd_histogram")
        previous_1h = state_1h.get("macd_histogram_previous")
        if (isinstance(macd_1h, (int, float)) and isinstance(previous_1h, (int, float))
                and math.isfinite(macd_1h) and math.isfinite(previous_1h)):
            if bullish and macd_1h > previous_1h:
                out.append({"category": "context", "type": "intermediate_timeframe_turn", "timeframe": "1h"})
            elif not bullish and macd_1h < previous_1h:
                out.append({"category": "context", "type": "intermediate_timeframe_turn", "timeframe": "1h"})
    return out


def _structure_levels(closes: list[float], highs: list[float] | None, lows: list[float] | None,
                      atr: float | None, direction: str, params: dict[str, Any]) -> dict[str, Any]:
    """Structural objectives: short term and swing. Informative only.

    A level is a location, not a prediction. Distances are expressed in ATR so
    they can be compared across regimes. These objectives never influence the
    detection itself.
    """
    close_price = closes[-1]
    result: dict[str, Any] = {}
    near_window = params["extreme_window"]
    swing_window = params["objective_swing_window"]

    def describe(level: float | None, kind: str, bullish: bool) -> dict[str, Any] | None:
        if level is None:
            return None
        distance = (level - close_price) if bullish else (close_price - level)
        entry = {"level": round(level, 12),
                 "distance_pct": round(100 * distance / close_price, 3) if close_price else None}
        if atr:
            entry["distance_atr"] = round(distance / atr, 2)
        entry["kind"] = kind
        return entry

    if direction in ("HAUSSIER", "BAISSIER"):
        bullish = direction == "HAUSSIER"
        source = (highs if bullish else lows) or closes
        near = [v for v in source[-near_window:] if _is_finite(v)]
        swing = [v for v in source[-swing_window:] if _is_finite(v)]
        near_level = max(near) if (bullish and near) else (min(near) if near else None)
        swing_level = max(swing) if (bullish and swing) else (min(swing) if swing else None)
        result["short_term"] = describe(near_level, "opposing structural level (recent window)", bullish)
        result["swing"] = describe(swing_level, "opposing structural level (swing window)", bullish)
    else:
        # Sans direction connue, on publie les deux cotes : ce sont des
        # localisations, pas des predictions.
        high_candidates = [v for v in (highs[-near_window:] if highs else []) if _is_finite(v)]
        low_candidates = [v for v in (lows[-near_window:] if lows else []) if _is_finite(v)]
        result["resistance"] = describe(max(high_candidates) if high_candidates else None,
                                        "resistance (recent window)", True)
        result["support"] = describe(min(low_candidates) if low_candidates else None,
                                      "support (recent window)", False)
        result["short_term"] = result["resistance"]
        result["swing"] = result["support"]
    result["note"] = ("Niveaux structurels informatifs : une localisation, pas une prediction. "
                       "Aucun objectif n'entre dans la decision du detecteur.")
    return result


def _market_regime(timeframes: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Qualifie le regime de marche a partir de l'unite 1 JOURNIERE.

    Un retournement pris contre une tendance longue n'est pas exploitable : c'est
    le mode d'echec mesure (esperance negative dans les regimes en tendance, y
    compris dans les deux sens). La mesure utilisee est la variation relative
    sur 30 bougies journalieres cloturees.

    Le seuil est celui valide hors echantillon (voir OOS_PROTOCOL.md et
    oos_rule_validation.json) ; il n'a pas ete regle sur les resultats.
    """
    state = timeframes.get("1d")
    value = None
    if isinstance(state, dict) and state.get("status") in ("OK", "PARTIEL"):
        candidate = state.get("change_30")
        if isinstance(candidate, (int, float)) and math.isfinite(candidate):
            value = float(candidate)
    if value is None:
        return {"state": "INDETERMINE", "value": None, "window_bars": 30,
                "note": "regime inconnu : historique journalier insuffisant"}
    band = params["regime_band"]
    if abs(value) < band:
        state_label = "NEUTRE"
    else:
        state_label = "TENDANCE_HAUSSIERE" if value > 0 else "TENDANCE_BAISSIERE"
    return {"state": state_label, "value": round(value, 6), "window_bars": 30,
            "band": band,
            "note": ("variation relative sur 30 bougies journalieres cloturees")}


def detect_early_reversal(timeframes: dict[str, Any],
                          rsi_series_15m: list[float] = None,
                          price_series_15m: list[float] = None,
                          macd_hist_15m: list[float] = None,
                          ohlc_15m: list[tuple] = None) -> dict[str, Any]:
    """Detect early reversal signals across timeframes.

    Returns a dict with:
      - signal_status: ALERTE_PRÉCOCE | CONFIRMATION | INVALIDATION | ATTENDRE | DONNÉES_INSUFFISANTES
      - direction: HAUSSIER | BAISSIER | INDETERMINE
      - evidence: list of evidence items (each with a "category" = family)
      - contradictions: list of conflicting signals
      - missing_data: list of missing inputs
      - contributing_timeframes: timeframes that took part
      - reason: explanation of the status
      - confidence: convergence score 0-100 (NOT a probability, NOT calibrated)
      - families: independent families of evidence that were satisfied
      - setup: description of the reversal setup (or None)
      - objectives: informative structural levels
    """
    evidence: list[dict[str, Any]] = []
    contradictions: list[dict[str, Any]] = []
    missing_data: list[str] = []
    observations: list[dict[str, Any]] = []
    families: set[str] = set()
    contributing: list[str] = []
    params = REVERSAL_PARAMS

    tf_15m = timeframes.get("15m", {})
    tf_1h = timeframes.get("1h", {})
    tf_4h = timeframes.get("4h", {})
    tf_1d = timeframes.get("1d", {})

    def insufficient(reason: str, extra: list[str] | None = None) -> dict[str, Any]:
        return {
            "signal_status": "DONNÉES_INSUFFISANTES",
            "direction": "INDETERMINE",
            "evidence": [],
            "contradictions": [],
            "missing_data": extra or [],
            "contributing_timeframes": [],
            "reason": reason,
            "confidence": 0,
            "confidence_note": "score de convergence (0-100), pas une probabilite",
            "families": [],
            "setup": None,
            "objectives": None,
        }

    if tf_15m.get("status") != "OK":
        return insufficient("Timeframe 15m non disponible", ["15m timeframe unavailable"])

    closes = list(price_series_15m or [])
    rsi_series = list(rsi_series_15m or [])
    macd_series = list(macd_hist_15m or [])
    count = len(closes)
    if count < params["extreme_window"] + params["turn_bars"]:
        return insufficient("Historique 15m insuffisant pour un setup structurel",
                            ["historique 15m insuffisant"])
    if len(rsi_series) != count or len(macd_series) != count:
        missing_data.append("series_15m_desalignees")

    opens = highs = lows = volumes = None
    if ohlc_15m and len(ohlc_15m) == count:
        opens = [bar[0] for bar in ohlc_15m]
        highs = [bar[1] for bar in ohlc_15m]
        lows = [bar[2] for bar in ohlc_15m]
        volumes = [bar[4] for bar in ohlc_15m] if len(ohlc_15m[0]) > 4 else None
    else:
        missing_data.append("ohlc_15m_indisponible")

    atr = tf_15m.get("atr14")
    if not (isinstance(atr, (int, float)) and math.isfinite(atr) and atr > 0):
        atr = None
        missing_data.append("atr14")

    contributing.append("15m")
    for timeframe in ("1h", "4h", "1d", "1w", "1M"):
        state = timeframes.get(timeframe)
        if isinstance(state, dict) and state.get("status") in ("OK", "PARTIEL"):
            contributing.append(timeframe)

    index = count - 1

    # --- recherche du setup le plus recent ---------------------------------
    setup = None
    ambiguous = False
    for candidate in range(index, max(-1, index - params["setup_window"]), -1):
        found = []
        for direction in ("HAUSSIER", "BAISSIER"):
            built = _setup_at(closes, highs, lows, rsi_series, macd_series, candidate, direction, params, atr)
            if built:
                found.append(built)
        if len(found) > 1:
            ambiguous = True
            continue
        if found:
            setup = found[0]
            break

    if setup is None:
        status = "ATTENDRE"
        direction = "INDETERMINE"
        reason = "Aucun setup de retournement structurel detecte"
        confidence = 0
        setup_payload = None
        objectives = _structure_levels(closes, highs, lows, atr, direction, params)
    else:
        direction = setup["direction"]
        setup_index = setup["index"]
        anchor = setup["anchor"]
        setup_payload = {"direction": direction, "anchor": round(anchor, 12),
                         "age_bars": index - setup_index,
                         "note": ("age_bars : nombre de bougies entre la creation du setup "
                                  "et la barre courante. L'index du setup est relatif a la "
                                  "fenetre analysee et n'est donc pas publie.")}

        for turn in setup["turns"]:
            evidence.append({**turn, "timeframe": "15m", "setup_index": setup_index})
        families.add("momentum")

        structure = _structure_evidence(closes, highs, lows, opens, rsi_series, setup_index, direction, params)
        for item in structure:
            evidence.append({**item, "timeframe": "15m", "setup_index": setup_index})
        if structure:
            families.add("structure")

        volume = _volume_evidence(volumes, setup_index, params)
        for item in volume:
            evidence.append({**item, "timeframe": "15m", "setup_index": setup_index})
        if volume:
            families.add("volume")

        context = _context_evidence(timeframes, direction, params)
        for item in context:
            evidence.append(item)
        if context:
            families.add("context")

        observations = _trend_observations(timeframes, direction)
        for item in observations:
            if item["type"] == "higher_timeframe_trend_opposite":
                contradictions.append({"type": "higher_timeframe_trend_opposite",
                                       "timeframe": item["timeframe"]})

        independent = families - {"momentum"}
        objectives = _structure_levels(closes, highs, lows, atr, direction, params)

        tolerance = params["break_tolerance_atr"] * (atr or 0.0)
        if direction == "HAUSSIER":
            invalidated = closes[index] < anchor - tolerance
        else:
            invalidated = closes[index] > anchor + tolerance

        confirmation = _confirmation_evidence(closes, highs, lows, macd_series, index, setup_index,
                                              direction, timeframes) if not invalidated else []
        for item in confirmation:
            evidence.append({**item, "setup_index": setup_index})

        if ambiguous:
            contradictions.append({"type": "setup_ambigu_direction"})
        if not independent:
            status = "ATTENDRE"
            reason = "Setup isole, aucune famille de preuves independante"
            confidence = 0
        elif invalidated:
            status = "INVALIDATION"
            reason = ("Ancre structurelle du setup rompue "
                      f"({anchor:.6f}, tolerance {tolerance:.6f})")
            confidence = min(100, 20 + 15 * len(independent))
        elif confirmation:
            status = "CONFIRMATION"
            reason = (f"Setup {direction.lower()} confirme par "
                      f"{', '.join(sorted({item['type'] for item in confirmation}))}")
            confidence = min(100, 20 + 15 * len(independent) + 15)
        else:
            status = "ALERTE_PRÉCOCE"
            reason = (f"Setup de retournement {direction.lower()} a l'extreme, "
                      f"{len(independent)} famille(s) independante(s), non confirme")
            confidence = min(100, 20 + 15 * len(independent))

    if contradictions:
        confidence = max(0, confidence - 10 * len(contradictions))

    # ------------------------------------------------- regime et exploitabilite
    # Un retournement n'est exploitable que si (a) il est CONFIRME (plusieurs
    # elements independants le confortent) et (b) le marche n'est pas en
    # tendance longue : mesure sur la variation 1j 30 bougies. Les deux
    # conditions sont issues de la validation hors echantillon
    # (oos_rule_validation.json) ; aucune n'a ete reglee sur les resultats.
    regime = _market_regime(timeframes, params)
    exploitable = False
    exploitable_reason = "Aucun signal de retournement confirme a ce stade"
    if status == "CONFIRMATION":
        if regime["state"] == "NEUTRE":
            exploitable = True
            exploitable_reason = ("Retournement confirme et regime 1 jour neutre : "
                                   "criteres de la regle de recherche")
        elif regime["state"].startswith("TENDANCE"):
            exploitable = False
            exploitable_reason = ("Retournement confirme mais regime en tendance "
                                   "(variation 1j 30 j hors zone neutre) : "
                                   "contre-tendance non exploitable")
        else:
            exploitable = False
            exploitable_reason = "Regime de marche indetermine : exploitabilite non etablie"

    return {
        "signal_status": status,
        "direction": direction,
        "evidence": evidence,
        "contradictions": contradictions,
        "missing_data": missing_data,
        "contributing_timeframes": contributing,
        "reason": reason,
        "confidence": confidence,
        "confidence_note": ("score de convergence des familles de preuves (0-100) ; "
                            "ce n'est pas une probabilite et n'a pas ete calibre"),
        "families": sorted(families),
        "setup": setup_payload,
        "objectives": objectives,
        "observations": observations,
        "regime": regime,
        "exploitable": exploitable,
        "exploitable_reason": exploitable_reason,
    }


def usable_rows(source: dict[str, Any], timeframe: str) -> list[dict[str, Any]]:
    candles = source.get("candles")
    section = candles.get(timeframe) if isinstance(candles, dict) else None
    if not isinstance(section, dict) or section.get("status") == "UNAVAILABLE":
        return []
    rows = section.get("rows")
    if not isinstance(rows, list):
        return []
    valid = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        values = [row.get(k) for k in ("open", "high", "low", "close", "volume")]
        try:
            opened, high, low, close, volume = [float(v) for v in values]
        except (TypeError, ValueError):
            continue
        if not all(math.isfinite(v) for v in (opened, high, low, close, volume)):
            continue
        if min(opened, high, low, close) <= 0 or volume < 0 or high < max(opened, close, low) or low > min(opened, close):
            continue
        valid.append({**row, "open": opened, "high": high, "low": low, "close": close, "volume": volume})
    valid.sort(key=lambda row: row.get("open_time", ""))
    # Reject duplicate candle opens rather than silently treating them as extra evidence.
    if any(valid[i].get("open_time") == valid[i + 1].get("open_time") for i in range(len(valid) - 1)):
        return []
    return valid


def analyze_timeframe(source: dict[str, Any], timeframe: str, now: datetime) -> dict[str, Any]:
    section = source.get("candles", {}).get(timeframe, {}) if isinstance(source.get("candles"), dict) else {}
    rows = usable_rows(source, timeframe)
    if len(rows) < MIN_CANDLES[timeframe]:
        return {
            "status": "UNAVAILABLE", "reason": f"historique insuffisant ou incohérent ({len(rows)} bougies valides)",
            "candle_count": len(rows), "trend": "INDETERMINE",
        }
    last_close_at = parse_time(section.get("last_closed_at"))
    if last_close_at is None:
        last_open = parse_time(rows[-1].get("open_time"))
        # Do not infer a candle close time when the collector's explicit timestamp is absent.
        return {"status": "UNAVAILABLE", "reason": "horodatage de clôture absent/invalide",
                "candle_count": len(rows), "trend": "INDETERMINE"}
    age_seconds = (now - last_close_at).total_seconds()
    if age_seconds < -60:
        return {"status": "UNAVAILABLE", "reason": "horodatage futur incohérent",
                "candle_count": len(rows), "trend": "INDETERMINE"}
    closes = [row["close"] for row in rows]
    highs = [row["high"] for row in rows]
    lows = [row["low"] for row in rows]
    volumes = [row["volume"] for row in rows]
    
    # Calculate all indicators
    ema20 = ema_series(closes, 20)
    ema50 = ema_series(closes, 50)
    rsi14 = rsi_series(closes, 14)
    hist = macd_histogram(closes)
    
    # New indicators
    sma10 = sma_series(closes, 10)
    sma20 = sma_series(closes, 20)
    sma50 = sma_series(closes, 50)
    sma100 = sma_series(closes, 100)
    sma200 = sma_series(closes, 200)
    atr = atr_series(highs, lows, closes, 14)
    momentum = momentum_series(closes, 10)
    cci = cci_series(highs, lows, closes, 20)
    stoch_k, stoch_d = stochastic_series(highs, lows, closes, 14, 3)
    di_plus, di_minus, adx = dmi_series(highs, lows, closes, 14)
    ao = awesome_oscillator_series(highs, lows)
    
    if not ema20 or not math.isfinite(rsi14[-1]):
        return {"status": "UNAVAILABLE", "reason": "indicateurs minimaux non calculables",
                "candle_count": len(rows), "trend": "INDETERMINE"}
    close = closes[-1]
    e20, rsi_now = ema20[-1], rsi14[-1]
    e50 = ema50[-1] if ema50 and math.isfinite(ema50[-1]) else None
    hist_now = hist[-1] if hist and math.isfinite(hist[-1]) else None
    hist_prev = hist[-2] if len(hist) > 1 and math.isfinite(hist[-2]) else None
    
    # Helper to get last finite value or None
    def last_finite_or_none(series):
        if not series:
            return None
        for v in reversed(series):
            if math.isfinite(v):
                return v
        return None
    
    # Extract latest values with None for unavailable
    s10 = last_finite_or_none(sma10)
    s20 = last_finite_or_none(sma20)
    s50 = last_finite_or_none(sma50)
    s100 = last_finite_or_none(sma100)
    s200 = last_finite_or_none(sma200)
    atr_val = last_finite_or_none(atr)
    mom_val = last_finite_or_none(momentum)
    cci_val = last_finite_or_none(cci)
    stoch_k_val = last_finite_or_none(stoch_k)
    stoch_d_val = last_finite_or_none(stoch_d)
    di_plus_val = last_finite_or_none(di_plus)
    di_minus_val = last_finite_or_none(di_minus)
    adx_val = last_finite_or_none(adx)
    ao_val = last_finite_or_none(ao)
    
    if e50 is not None and close > e20 > e50 and hist_now is not None and hist_now > 0:
        trend = "HAUSSIER"
    elif e50 is not None and close < e20 < e50 and hist_now is not None and hist_now < 0:
        trend = "BAISSIER"
    else:
        trend = "MIXTE" if e50 is not None else "INDETERMINE"

    # Variation relative sur 30 bougies : sert a qualifier le regime de marche
    # (neutre / en tendance) sur l'unite de temps superieure. Calculee sur les
    # bougies CLOTUREES uniquement.
    change_30 = None
    if len(closes) >= 31 and closes[-31] > 0:
        change_30 = close / closes[-31] - 1.0
    avg_volume = mean(volumes[-20:])
    volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else None
    recent_rsi = [v for v in rsi14[-4:] if math.isfinite(v)]
    rsi_rising = len(recent_rsi) >= 3 and all(a < b for a, b in zip(recent_rsi, recent_rsi[1:]))
    close_rising = len(closes) >= 3 and closes[-1] > closes[-2] > closes[-3]
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
    candle_status = section.get("status", "UNKNOWN")
    timeframe_seconds = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800, "1M": 31 * 86400}[timeframe]
    # The snapshot can be fresh while one timeframe silently contains an old candle.
    # Keep the stricter 15m limit; higher intervals get one interval plus the snapshot grace.
    max_candle_age = MAX_SNAPSHOT_AGE_SECONDS if timeframe == "15m" else timeframe_seconds + MAX_SNAPSHOT_AGE_SECONDS
    fresh = -60 <= age_seconds <= max_candle_age
    monthly_history_partial = timeframe == "1M" and (e50 is None or hist_now is None)
    valid_source_status = candle_status in ("OK", "PARTIEL")
    result_status = "PARTIEL" if fresh and valid_source_status and monthly_history_partial else (
        "OK" if fresh and valid_source_status else "ATTENTION"
    )
    reason = "historique mensuel trop court pour EMA50/MACD complet" if monthly_history_partial else (
        None if fresh else "dernière bougie clôturée trop ancienne"
    )
    return {
        "status": result_status,
        "reason": reason,
        "candle_status": candle_status, "candle_count": len(rows),
        "last_closed_at": last_close_at.isoformat(), "candle_age_seconds": round(age_seconds),
        "close": close, 
        "ema20": e20, "ema50": e50, 
        "sma10": s10, "sma20": s20, "sma50": s50, "sma100": s100, "sma200": s200,
        "rsi14": rsi_now,
        "macd_histogram": hist_now, "macd_histogram_previous": hist_prev,
        "atr14": atr_val,
        "momentum10": mom_val,
        "cci20": cci_val,
        "stoch_k": stoch_k_val, "stoch_d": stoch_d_val,
        "di_plus": di_plus_val, "di_minus": di_minus_val, "adx14": adx_val,
        "awesome_oscillator": ao_val,
        "volume_last": volumes[-1], "volume_mean20": avg_volume, "volume_ratio_20": volume_ratio,
        "trend": trend, "flags": flags, "change_30": change_30,
    }


def unavailable_report(reason: str, generated_at: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1, "symbol": "TELUSDT", "mode": "READ_ONLY_ANALYSIS",
        "generated_at": datetime.now(timezone.utc).isoformat(), "source_generated_at": generated_at,
        "status": "ATTENDRE", "collection_status": "FALLBACK", "reason": reason, "timeframes": {},
        "alignment": "INDETERMINE",
        "interpretation": "Données absentes, périmées ou incohérentes : aucune conclusion d'entrée.",
        "orders_sent": 0,
    }


def build_analysis(snapshot: Any, expected_collection_id: str | None = None, now: datetime | None = None) -> dict[str, Any]:
    if isinstance(expected_collection_id, datetime):
        now = expected_collection_id
        expected_collection_id = None
    now = now or datetime.now(timezone.utc)
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1 or snapshot.get("symbol") != "TELUSDT":
        return unavailable_report("snapshot absent, schéma invalide ou symbole inattendu")

    snapshot_collection_id = snapshot.get("collection_id")
    if expected_collection_id is not None:
        if snapshot_collection_id is None:
            return unavailable_report("collection_id absent dans le snapshot (provenance non vérifiable)")
        if snapshot_collection_id != expected_collection_id:
            return unavailable_report(f"collection_id incohérent: snapshot={snapshot_collection_id}, attendu={expected_collection_id}")

    snapshot_id = snapshot.get("snapshot_id")
    if snapshot_id is not None:
        if not isinstance(snapshot_id, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", snapshot_id):
            return unavailable_report(f"snapshot_id invalide ou mal formé ({snapshot_id})")
        try:
            actual_hash = compute_snapshot_fingerprint(snapshot.get("sources"), snapshot.get("cross_check"))
        except ValueError as exc:
            return unavailable_report(f"snapshot_id invalide: source incomplète ou mal formée ({exc})")
        if actual_hash != snapshot_id:
            return unavailable_report(f"snapshot_id incohérent: attendu={actual_hash}, reçu={snapshot_id}")

    generated = parse_time(snapshot.get("generated_at"))
    if generated is None:
        return unavailable_report("horodatage de snapshot absent/invalide", snapshot.get("generated_at"))
    age = (now - generated).total_seconds()
    if age < -60 or age > MAX_SNAPSHOT_AGE_SECONDS:
        return unavailable_report(f"snapshot périmé ou horloge incohérente (âge {round(age)} s)", snapshot.get("generated_at"))
    sources = snapshot.get("sources")
    if not isinstance(sources, dict) or not isinstance(sources.get("mexc"), dict):
        return unavailable_report("source MEXC multi-unités de temps absente", snapshot.get("generated_at"))
    mexc = sources["mexc"]
    cross = snapshot.get("cross_check") if isinstance(snapshot.get("cross_check"), dict) else {}
    timeframes = {tf: analyze_timeframe(mexc, tf, now) for tf in TIMEFRAMES}
    
    # Early reversal detection (observation mode only)
    # Extract series for 15m timeframe
    rows_15m = usable_rows(mexc, "15m")
    rsi_series_15m = rsi_series([row["close"] for row in rows_15m], 14) if len(rows_15m) >= 15 else []
    price_series_15m = [row["close"] for row in rows_15m]
    macd_hist_15m = macd_histogram(price_series_15m) if len(price_series_15m) >= 27 else []
    
    # Les figures de bougies ont besoin de l'OHLC brut, aligne sur les memes
    # index que price_series_15m (une bougie par element).
    ohlc_15m = [(row["open"], row["high"], row["low"], row["close"], row["volume"])
                for row in rows_15m]
    early_reversal = detect_early_reversal(
        timeframes,
        rsi_series_15m=rsi_series_15m,
        price_series_15m=price_series_15m,
        macd_hist_15m=macd_hist_15m,
        ohlc_15m=ohlc_15m
    )
    required_timeframes = ("15m", "1h", "4h", "1d", "1w")
    missing_required = [tf for tf in required_timeframes if timeframes[tf].get("status") != "OK"]
    monthly_unavailable = timeframes["1M"].get("status") not in ("OK", "PARTIEL")
    if missing_required or monthly_unavailable:
        status = "ATTENDRE"
        reasons = [f"{tf}: {timeframes[tf].get('reason') or timeframes[tf].get('candle_status') or timeframes[tf].get('status')}"
                   for tf in required_timeframes if timeframes[tf].get("status") != "OK"]
        if monthly_unavailable:
            reasons.append(f"1M: {timeframes['1M'].get('reason') or timeframes['1M'].get('status')}")
        reason = "Unités de temps requises non validées: " + "; ".join(reasons)
    else:
        status, reason = "SURVEILLER", None
    long_trends = [timeframes[tf]["trend"] for tf in ("4h", "1d", "1w") if timeframes[tf]["status"] == "OK"]
    if timeframes["1M"]["status"] == "OK":
        long_trends.append(timeframes["1M"]["trend"])
    if len(long_trends) < 3:
        alignment = "INDETERMINE"
    elif all(trend == "HAUSSIER" for trend in long_trends):
        alignment = "HAUSSIER_ALIGNE"
    elif all(trend == "BAISSIER" for trend in long_trends):
        alignment = "BAISSIER_ALIGNE"
    else:
        alignment = "MIXTE"
    flags = []
    for tf in ("15m", "1h", "4h", "1d", "1w", "1M"):
        for flag in timeframes[tf].get("flags", []):
            flags.append({"timeframe": tf, "flag": flag})
    critical_timeframes = ("15m", "1h", "4h")
    below_critical = [tf for tf in critical_timeframes
                      if timeframes[tf].get("status") == "OK"
                      and isinstance(timeframes[tf].get("close"), (int, float))
                      and timeframes[tf]["close"] < CRITICAL_LEVEL]
    critical_status = "SOUS_NIVEAU_SURVEILLANCE" if below_critical else "AU_DESSUS_SUR_CLOTURE"
    if below_critical:
        flags.append({
            "timeframe": "GLOBAL",
            "flag": "NIVEAU_CRITIQUE_0_001526_CLOTURE_SOUS_NIVEAU_" + "_".join(below_critical),
        })
    result = {
        "schema_version": 1, "symbol": "TELUSDT", "mode": "READ_ONLY_ANALYSIS",
        "generated_at": now.isoformat(), "source_generated_at": generated.isoformat(),
        "snapshot_age_seconds": round(age), "status": status, "collection_status": "VALID", "reason": reason,
        "cross_check": {
            "independent_confirmation": cross.get("independent_confirmation", "NON ÉTABLIE"),
            "venue_data_diagnostic": cross.get("venue_data_diagnostic"),
            "divergence_bps": cross.get("divergence_bps"),
        },
        "timeframes": timeframes, "alignment": alignment, "flags": flags,
        "risk_checks": {
            "critical_level": CRITICAL_LEVEL,
            "status": critical_status,
            "closed_timeframes_below_level": below_critical,
            "interpretation": "Risque de rupture à réévaluer; ce contrôle n’est jamais un signal d’achat."
        },
        "interpretation": (
            "Analyse multi-unités de temps. Les drapeaux sont des observations, pas des signaux d'achat. "
            "Un RSI survendu ne confirme pas un retournement. SURVEILLER ne signifie pas ENTRER."
            if status == "SURVEILLER" else
            "Fail-closed : au moins une unité de temps ou la fraîcheur des données n'est pas validée. ATTENDRE."
        ),
        "orders_sent": 0,
        "early_reversal": early_reversal,  # Observation mode only
    }
    if expected_collection_id is not None:
        result["collection_id"] = expected_collection_id
    if snapshot_id is not None:
        result["snapshot_id"] = snapshot_id
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="site/tel_snapshot.json")
    parser.add_argument("--output", default="site/agent_analysis.json")
    parser.add_argument("--collection-id", default=None, help="Collection ID for provenance verification (UUID)")
    args = parser.parse_args()
    snapshot = None
    try:
        snapshot = json.loads(Path(args.input).read_text(encoding="utf-8"))
        report = build_analysis(snapshot, args.collection_id)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        report = unavailable_report(f"lecture du snapshot impossible ({type(exc).__name__})")
    # Include collection_id in report for dashboard verification
    if args.collection_id:
        report["collection_id"] = args.collection_id
    # Also include snapshot_id from snapshot if available
    if isinstance(snapshot, dict) and snapshot.get("snapshot_id"):
        report["snapshot_id"] = snapshot.get("snapshot_id")
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Analyse TEL multi-timeframes: {report['status']} | alignement={report.get('alignment')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
