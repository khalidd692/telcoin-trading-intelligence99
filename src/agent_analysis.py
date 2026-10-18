"""Conservative, read-only multi-timeframe TEL analysis.

This is a deterministic analysis layer, not an autonomous trading agent:
it never places orders and never turns oversold conditions into a buy signal.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TIMEFRAMES = ("15m", "1h", "4h", "1d", "1w", "1M")
MAX_SNAPSHOT_AGE_SECONDS = 20 * 60
MIN_CANDLES = {"15m": 55, "1h": 55, "4h": 55, "1d": 55, "1w": 55, "1M": 15}


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
    volumes = [row["volume"] for row in rows]
    ema20 = ema_series(closes, 20)
    ema50 = ema_series(closes, 50)
    rsi14 = rsi_series(closes, 14)
    hist = macd_histogram(closes)
    if not ema20 or not math.isfinite(rsi14[-1]):
        return {"status": "UNAVAILABLE", "reason": "indicateurs minimaux non calculables",
                "candle_count": len(rows), "trend": "INDETERMINE"}
    close = closes[-1]
    e20, rsi_now = ema20[-1], rsi14[-1]
    e50 = ema50[-1] if ema50 and math.isfinite(ema50[-1]) else None
    hist_now = hist[-1] if hist and math.isfinite(hist[-1]) else None
    hist_prev = hist[-2] if len(hist) > 1 and math.isfinite(hist[-2]) else None
    if e50 is not None and close > e20 > e50 and hist_now is not None and hist_now > 0:
        trend = "HAUSSIER"
    elif e50 is not None and close < e20 < e50 and hist_now is not None and hist_now < 0:
        trend = "BAISSIER"
    else:
        trend = "MIXTE" if e50 is not None else "INDETERMINE"
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
        "close": close, "ema20": e20, "ema50": e50, "rsi14": rsi_now,
        "macd_histogram": hist_now, "macd_histogram_previous": hist_prev,
        "volume_last": volumes[-1], "volume_mean20": avg_volume, "volume_ratio_20": volume_ratio,
        "trend": trend, "flags": flags,
    }


def unavailable_report(reason: str, generated_at: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1, "symbol": "TELUSDT", "mode": "READ_ONLY_ANALYSIS",
        "generated_at": datetime.now(timezone.utc).isoformat(), "source_generated_at": generated_at,
        "status": "ATTENDRE", "reason": reason, "timeframes": {},
        "alignment": "INDETERMINE",
        "interpretation": "Données absentes, périmées ou incohérentes : aucune conclusion d'entrée.",
        "orders_sent": 0,
    }


def build_analysis(snapshot: Any, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1 or snapshot.get("symbol") != "TELUSDT":
        return unavailable_report("snapshot absent, schéma invalide ou symbole inattendu")
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
    return {
        "schema_version": 1, "symbol": "TELUSDT", "mode": "READ_ONLY_ANALYSIS",
        "generated_at": now.isoformat(), "source_generated_at": generated.isoformat(),
        "snapshot_age_seconds": round(age), "status": status, "reason": reason,
        "cross_check": {
            "independent_confirmation": cross.get("independent_confirmation", "NON ÉTABLIE"),
            "venue_data_diagnostic": cross.get("venue_data_diagnostic"),
            "divergence_bps": cross.get("divergence_bps"),
        },
        "timeframes": timeframes, "alignment": alignment, "flags": flags,
        "interpretation": (
            "Analyse multi-unités de temps. Les drapeaux sont des observations, pas des signaux d'achat. "
            "Un RSI survendu ne confirme pas un retournement. SURVEILLER ne signifie pas ENTRER."
            if status == "SURVEILLER" else
            "Fail-closed : au moins une unité de temps ou la fraîcheur des données n'est pas validée. ATTENDRE."
        ),
        "orders_sent": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="site/tel_snapshot.json")
    parser.add_argument("--output", default="site/agent_analysis.json")
    args = parser.parse_args()
    try:
        snapshot = json.loads(Path(args.input).read_text(encoding="utf-8"))
        report = build_analysis(snapshot)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        report = unavailable_report(f"lecture du snapshot impossible ({type(exc).__name__})")
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Analyse TEL multi-timeframes: {report['status']} | alignement={report.get('alignment')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
