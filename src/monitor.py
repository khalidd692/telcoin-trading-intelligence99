from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.kraken_market_data import KrakenMarketDataError, collect_snapshot as collect_kraken_snapshot

SYMBOL = "TELUSDT"
TIMEOUT_SECONDS = 10
MAX_SPREAD_PCT = 0.50
MAX_REPORT_AGE_SECONDS = 20 * 60
USER_AGENT = "telcoin-trading-intelligence/0.1 (read-only public market data)"


class DataUnavailable(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise DataUnavailable(f"HTTP status {response.status}")
            return json.loads(response.read(2_000_000).decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DataUnavailable(f"request/parse failure: {type(exc).__name__}") from exc


def number(value: Any, label: str, *, positive: bool = True) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise DataUnavailable(f"invalid {label}") from exc
    if not math.isfinite(result) or (positive and result <= 0):
        raise DataUnavailable(f"invalid {label}")
    return result


def maybe_number(value: Any) -> float | None:
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def ema(values: list[float], period: int) -> float:
    if len(values) < period:
        raise DataUnavailable(f"not enough values for EMA{period}")
    alpha = 2 / (period + 1)
    result = sum(values[:period]) / period
    for value in values[period:]:
        result = alpha * value + (1 - alpha) * result
    return result


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) < period + 1:
        raise DataUnavailable("not enough values for RSI")
    changes = [values[i] - values[i - 1] for i in range(1, len(values))][-period:]
    gain = sum(max(x, 0.0) for x in changes) / period
    loss = sum(max(-x, 0.0) for x in changes) / period
    if loss == 0:
        return 100.0 if gain > 0 else 50.0
    return 100 - 100 / (1 + gain / loss)


def fallback_report(reason: str) -> dict[str, Any]:
    """Return a schema-valid, fail-closed TEL/USD report."""
    return {
        "schema_version": 1, "generated_at": utc_now().isoformat(),
        "symbol": "TELUSD", "pair": "TEL/USD", "mode": "READ_ONLY_ALERTS", "status": "ATTENDRE",
        "sources": {
            "kraken_market": {"status": "UNAVAILABLE", "reason": reason},
            "kraken_candles": {"status": "UNAVAILABLE", "reason": reason},
            "kraken_depth": {"status": "UNAVAILABLE", "reason": reason},
            "kraken_trades": {"status": "UNAVAILABLE", "reason": reason},
        },
        "checks": [{"name": "Kraken collection pipeline", "status": "FAIL", "reason": reason}],
        "indicators": None, "error": reason,
        "interpretation": "Rapport de secours. Fail-closed : ATTENDRE.",
        "disclaimer": "Read-only monitoring. No orders. No profitability claims.",
    }


def build_report() -> dict[str, Any]:
    """Build a Kraken TEL/USD report. No automatic currency-mixed fallback."""
    report: dict[str, Any] = {
        "schema_version": 1, "generated_at": utc_now().isoformat(),
        "symbol": "TELUSD", "pair": "TEL/USD", "quote_currency": "USD",
        "mode": "READ_ONLY_ALERTS", "status": "ATTENDRE",
        "sources": {}, "checks": [], "indicators": None,
        "disclaimer": "No orders are placed. TEL/USD is not interchangeable with TEL/USDT.",
    }
    try:
        snapshot = collect_kraken_snapshot()
        report["sources"]["kraken_market"] = {
            "status": "OK", "source": snapshot["source"], "pair": snapshot["symbol"],
            "pair_key": snapshot["pair_key"], "observed_at": snapshot["observed_at_utc"],
            "server_time": snapshot["server_time_utc"], "last": snapshot["last"],
            "bid": snapshot["bid"], "ask": snapshot["ask"], "spread_pct": snapshot["spread_pct"],
            "ticker_timestamp": snapshot["ticker_timestamp"],
            "ticker_freshness_verified": snapshot["ticker_freshness_verified"],
            "ticker_freshness_note": snapshot["ticker_freshness_note"],
            "depth_timestamp_note": snapshot["depth_timestamp_note"],
            "collection_duration_seconds": snapshot["collection_duration_seconds"],
        }
        report["sources"]["kraken_depth"] = {
            "status": "OK", "depth": snapshot["depth"],
            "freshness_verified": snapshot["validation"]["depth_fresh"],
            "observed_at": snapshot["observed_at_utc"],
        }
        report["sources"]["kraken_trades"] = {
            "status": "OK", **snapshot["trade"], "observed_at": snapshot["observed_at_utc"],
            "freshness_verified": snapshot["validation"]["trade_fresh"],
        }
        candles = snapshot["recent_closed_15m_candles"]
        closes = [c["close"] for c in candles]
        candle_close_epoch = candles[-1]["open_time_epoch"] + 900
        server_epoch = datetime.fromisoformat(snapshot["server_time_utc"]).timestamp()
        age = max(0, int(server_epoch - candle_close_epoch))
        if age > MAX_REPORT_AGE_SECONDS:
            raise DataUnavailable(f"latest closed Kraken candle stale ({age}s)")
        true_ranges = [
            max(candles[i]["high"] - candles[i]["low"],
                abs(candles[i]["high"] - candles[i-1]["close"]),
                abs(candles[i]["low"] - candles[i-1]["close"]))
            for i in range(1, len(candles))
        ]
        if len(candles) < 55 or len(true_ranges) < 14:
            raise DataUnavailable("not enough closed Kraken candles for EMA50/RSI14/ATR14")
        atr = sum(true_ranges[-14:]) / 14
        report["indicators"] = {
            "timeframe": "15m",
            "last_closed_candle_at": candles[-1]["open_time"],
            "candle_age_seconds": age, "close": closes[-1],
            "ema12": ema(closes, 12), "ema26": ema(closes, 26), "ema50": ema(closes, 50),
            "rsi14": rsi(closes), "atr14": atr, "atr_pct": atr / closes[-1] * 100,
            "volume_last_closed": candles[-1]["volume"],
            "volume_mean20": sum(c["volume"] for c in candles[-20:]) / 20,
            "close_series": [
                {"time": datetime.fromtimestamp(c["open_time_epoch"] + 900, timezone.utc).isoformat(), "close": c["close"]}
                for c in candles[-48:]
            ],
        }
        report["sources"]["kraken_candles"] = {
            "status": "OK", "timeframe": "15m", "closed_candles_used": len(candles),
            "latest_closed_at": candles[-1]["open_time"],
        }
        report["checks"].extend([
            {"name": "Kraken TEL/USD exact pair", "status": "PASS"},
            {"name": "Kraken ticker positive and bid below ask", "status": "PASS"},
            {"name": "Kraken spread", "status": "PASS", "value_pct": round(snapshot["spread_pct"], 4), "limit_pct": MAX_SPREAD_PCT},
            {"name": "Kraken timestamped depth freshness and ticker consistency", "status": "PASS"},
            {"name": "Kraken latest trade freshness and ticker consistency", "status": "PASS"},
            {"name": "Kraken closed 15m candles", "status": "PASS", "closed_candles_used": len(candles)},
        ])
        report["status"] = "SURVEILLER" if all(c["status"] == "PASS" for c in report["checks"]) else "ATTENDRE"
        report["interpretation"] = (
            "Kraken TEL/USD public data passed current checks. SURVEILLER is not an entry instruction."
            if report["status"] == "SURVEILLER"
            else "At least one required data-quality check failed. Fail-closed: ATTENDRE."
        )
    except (DataUnavailable, KrakenMarketDataError) as exc:
        report["status"] = "ATTENDRE"
        report["error"] = str(exc)
        report["checks"].append({"name": "Kraken data quality", "status": "FAIL", "reason": str(exc)})
        report["interpretation"] = "Required Kraken data unavailable or incoherent. Fail-closed: ATTENDRE."
        for key in ("kraken_market", "kraken_depth", "kraken_trades", "kraken_candles"):
            report["sources"].setdefault(key, {"status": "UNAVAILABLE", "reason": str(exc)})
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="report.json")
    args = parser.parse_args()
    try:
        report = build_report()
    except Exception as exc:  # Keep a usable fail-closed artifact for unexpected errors too.
        report = fallback_report(f"unexpected collector error: {type(exc).__name__}")
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    # ATTENDRE is a valid report, but a critical data-quality failure must fail the workflow.
    return 0 if report.get("status") == "SURVEILLER" else 1


if __name__ == "__main__":
    sys.exit(main())

