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


def mexc_ticker() -> dict[str, Any]:
    data = http_json(f"https://api.mexc.com/api/v3/ticker/24hr?symbol={SYMBOL}")
    if not isinstance(data, dict) or data.get("symbol") != SYMBOL:
        raise DataUnavailable("unexpected MEXC ticker schema/symbol")
    last = number(data.get("lastPrice"), "MEXC last")
    bid = number(data.get("bidPrice"), "MEXC bid")
    ask = number(data.get("askPrice"), "MEXC ask")
    if ask < bid:
        raise DataUnavailable("MEXC ask below bid")
    return {
        "last": last, "bid": bid, "ask": ask,
        "spread_pct": (ask - bid) / ((ask + bid) / 2) * 100,
        "quote_volume_24h": maybe_number(data.get("quoteVolume")),
        "change_pct_24h": maybe_number(data.get("priceChangePercent")),
        "source": "MEXC public ticker", "observed_at": utc_now().isoformat(),
    }


def candles_15m() -> list[list[float]]:
    data = http_json(f"https://api.mexc.com/api/v3/klines?symbol={SYMBOL}&interval=15m&limit=100")
    if not isinstance(data, list) or len(data) < 55:
        raise DataUnavailable("not enough MEXC candles")
    candles = []
    for row in data:
        if not isinstance(row, list) or len(row) < 6:
            raise DataUnavailable("unexpected candle schema")
        try:
            ts = int(row[0])
            o, h, low, close, vol = (float(row[i]) for i in (1, 2, 3, 4, 5))
        except (TypeError, ValueError, IndexError) as exc:
            raise DataUnavailable("malformed candle") from exc
        if not all(math.isfinite(x) for x in (o, h, low, close, vol)):
            raise DataUnavailable("non-finite candle")
        if min(o, h, low, close) <= 0 or vol < 0 or h < max(o, close, low) or low > min(o, close):
            raise DataUnavailable("incoherent OHLCV candle")
        candles.append([ts, o, h, low, close, vol])
    candles.sort(key=lambda c: c[0])
    if any(candles[i][0] >= candles[i + 1][0] for i in range(len(candles) - 1)):
        raise DataUnavailable("duplicate candle timestamps")
    return candles[:-1]  # never use the still-forming candle


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


def kucoin_price() -> dict[str, float]:
    data = http_json("https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=TEL-USDT")
    if not isinstance(data, dict) or data.get("code") != "200000" or not isinstance(data.get("data"), dict):
        raise DataUnavailable("unexpected KuCoin response")
    d = data["data"]
    result = {
        "last": number(d.get("price"), "KuCoin last"),
        "bid": number(d.get("bestBid"), "KuCoin bid"),
        "ask": number(d.get("bestAsk"), "KuCoin ask"),
    }
    if result["ask"] < result["bid"]:
        raise DataUnavailable("KuCoin ask below bid")
    return result


def fallback_report(reason: str) -> dict[str, Any]:
    """Return a schema-valid, fail-closed report when collection cannot complete."""
    return {
        "schema_version": 1, "generated_at": utc_now().isoformat(),
        "symbol": SYMBOL, "mode": "READ_ONLY_ALERTS", "status": "ATTENDRE",
        "collection_status": "FALLBACK",
        "sources": {
            "mexc_ticker": {"status": "UNAVAILABLE", "reason": reason},
            "mexc_candles": {"status": "UNAVAILABLE", "reason": reason},
            "kucoin_level1": {"status": "UNAVAILABLE", "reason": reason},
        },
        "checks": [{"name": "Collection pipeline", "status": "FAIL", "reason": reason}],
        "indicators": None, "error": reason,
        "interpretation": "Rapport de secours. Fail-closed : ATTENDRE.",
        "disclaimer": "Read-only monitoring. No orders. No profitability claims.",
    }


def build_report(collection_id: str | None = None) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": 1, "generated_at": utc_now().isoformat(),
        "symbol": SYMBOL, "mode": "READ_ONLY_ALERTS", "status": "ATTENDRE",
        "collection_status": "VALID",
        "sources": {}, "checks": [], "indicators": None,
        "disclaimer": "No orders are placed. Monitoring is not a proven trading edge or financial advice.",
    }
    if collection_id:
        report["collection_id"] = collection_id
    try:
        ticker = mexc_ticker()
        report["sources"]["mexc_ticker"] = {"status": "OK", **ticker}
        candles = candles_15m()
        closes = [c[4] for c in candles]
        # MEXC kline timestamps mark candle OPEN time; evaluate freshness at candle CLOSE.
        latest_ts = candles[-1][0] / 1000 + 900
        age = max(0, int(time.time() - latest_ts))
        if age > MAX_REPORT_AGE_SECONDS:
            raise DataUnavailable(f"latest closed candle stale ({age}s)")
        true_ranges = [
            max(candles[i][2] - candles[i][3],
                abs(candles[i][2] - candles[i-1][4]),
                abs(candles[i][3] - candles[i-1][4]))
            for i in range(1, len(candles))
        ]
        atr = sum(true_ranges[-14:]) / 14
        report["indicators"] = {
            "timeframe": "15m",
            "last_closed_candle_at": datetime.fromtimestamp(latest_ts, timezone.utc).isoformat(),
            "candle_age_seconds": age, "close": closes[-1],
            "ema12": ema(closes, 12), "ema26": ema(closes, 26), "ema50": ema(closes, 50),
            "rsi14": rsi(closes), "atr14": atr, "atr_pct": atr / closes[-1] * 100,
            "volume_last_closed": candles[-1][5],
            "volume_mean20": sum(c[5] for c in candles[-20:]) / 20,
            "close_series": [
                {"time": datetime.fromtimestamp(c[0] / 1000 + 900, timezone.utc).isoformat(),
                 "close": c[4]} for c in candles[-48:]
            ],
        }
        report["sources"]["mexc_candles"] = {"status": "OK", "timeframe": "15m", "closed_candles_used": len(candles)}
        report["checks"].append({"name": "MEXC ticker/candles freshness and schema", "status": "PASS"})
        spread_ok = ticker["spread_pct"] <= MAX_SPREAD_PCT
        report["checks"].append({"name": "MEXC spread", "status": "PASS" if spread_ok else "FAIL",
                                 "value_pct": round(ticker["spread_pct"], 4), "limit_pct": MAX_SPREAD_PCT})
        try:
            ku = kucoin_price()
            report["sources"]["kucoin_level1"] = {"status": "OK", **ku, "observed_at": utc_now().isoformat()}
            divergence = abs(ticker["last"] - ku["last"]) / ((ticker["last"] + ku["last"]) / 2) * 100
            report["cross_exchange"] = {"last_price_divergence_pct": round(divergence, 4)}
            report["checks"].append({"name": "Cross-exchange price consistency",
                                     "status": "PASS" if divergence <= 1.0 else "FAIL",
                                     "divergence_pct": round(divergence, 4), "limit_pct": 1.0})
        except DataUnavailable as exc:
            report["sources"]["kucoin_level1"] = {"status": "UNAVAILABLE", "reason": str(exc)}
            report["checks"].append({"name": "Independent venue confirmation", "status": "FAIL",
                                     "reason": "KuCoin unavailable; fail-closed"})
        report["status"] = "SURVEILLER" if all(c["status"] == "PASS" for c in report["checks"]) else "ATTENDRE"
        report["interpretation"] = ("Feeds passed basic quality checks. SURVEILLER is not an entry instruction."
                                    if report["status"] == "SURVEILLER"
                                    else "At least one quality/confirmation check failed. Fail-closed: ATTENDRE.")
    except DataUnavailable as exc:
        report["status"] = "ATTENDRE"
        report["collection_status"] = "FALLBACK"
        report["error"] = str(exc)
        report["interpretation"] = "Required data unavailable or incoherent. Fail-closed: ATTENDRE."
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="report.json")
    parser.add_argument("--collection-id", default=None, help="Collection ID for provenance tracking (UUID)")
    args = parser.parse_args()
    try:
        report = build_report(args.collection_id)
    except Exception as exc:  # Keep a usable fail-closed artifact for unexpected errors too.
        report = fallback_report(f"unexpected collector error: {type(exc).__name__}")
        if args.collection_id:
            report["collection_id"] = args.collection_id
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    # The exit code reports whether collection produced a valid artifact, not whether
    # the market passed every quality check. A valid ATTENDRE (for example a spread
    # above the threshold) is a legitimate fail-closed decision and must not be
    # retried as if the collection itself had failed. Only a FALLBACK report means
    # that required market data is missing or incoherent.
    return 0 if report.get("collection_status") == "VALID" else 1


if __name__ == "__main__":
    sys.exit(main())

