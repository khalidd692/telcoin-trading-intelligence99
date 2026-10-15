"""Read-only Kraken Spot TEL/USD snapshot using public REST market-data endpoints only.

No API keys, private/account endpoints, or trading endpoints are used. Each public request is spaced to respect Kraken rate guidance.
Ticker and order-book timestamps are treated separately: Kraken's Ticker response
has no quote timestamp, so it is cross-checked against timestamped public trades
and timestamped depth levels before the snapshot can be accepted.
"""
from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

BASE = "https://api.kraken.com/0/public"
EXPECTED_WSNAME = "TEL/USD"
EXPECTED_ALTNAME = "TELUSD"
TIMEOUT_SECONDS = 10
MAX_SPREAD_PCT = 0.50  # Keep existing monitor limit; do not raise without approval.
MAX_MARKET_DATA_AGE_SECONDS = 60
MAX_COLLECTION_SECONDS = 20
REQUEST_SPACING_SECONDS = 1.05
USER_AGENT = "telcoin-trading-intelligence/0.3 (read-only public market data)"


class KrakenMarketDataError(RuntimeError):
    """Raised when required public Kraken market data cannot be validated."""


def _utc(epoch: float | int) -> str:
    return datetime.fromtimestamp(float(epoch), timezone.utc).isoformat()


def _positive(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise KrakenMarketDataError(f"invalid {label}") from exc
    if not math.isfinite(number) or number <= 0:
        raise KrakenMarketDataError(f"invalid {label}")
    return number


def _get_json(path: str, params: dict[str, str] | None = None) -> tuple[dict[str, Any], int, int]:
    query = "?" + urllib.parse.urlencode(params) if params else ""
    url = f"{BASE}/{path}{query}"
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Cache-Control": "no-cache",
    })
    started = time.monotonic()
    status = 0
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", 200)
            raw = response.read(1_000_000)
        if status != 200:
            raise KrakenMarketDataError(f"HTTP {status} from {path}")
        payload = json.loads(raw.decode("utf-8"))
    except KrakenMarketDataError:
        raise
    except urllib.error.HTTPError as exc:
        raise KrakenMarketDataError(f"HTTP {exc.code} from {path}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KrakenMarketDataError(f"request/parse failure for {path}: {type(exc).__name__}") from exc
    elapsed_ms = int((time.monotonic() - started) * 1000)
    if not isinstance(payload, dict):
        raise KrakenMarketDataError(f"invalid JSON object from {path}")
    errors = payload.get("error")
    if not isinstance(errors, list) or errors:
        detail = ", ".join(str(item) for item in errors) if isinstance(errors, list) else "missing error array"
        raise KrakenMarketDataError(f"Kraken API error for {path}: {detail}")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise KrakenMarketDataError(f"missing result object from {path}")
    return result, elapsed_ms, status


def _resolve_pair(asset_pairs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if not isinstance(asset_pairs, dict):
        raise KrakenMarketDataError("invalid AssetPairs result")
    matches = []
    for key, metadata in asset_pairs.items():
        if not isinstance(metadata, dict):
            continue
        wsname = str(metadata.get("wsname", "")).upper()
        altname = str(metadata.get("altname", "")).upper()
        if wsname == EXPECTED_WSNAME or altname == EXPECTED_ALTNAME or str(key).upper() == EXPECTED_ALTNAME:
            matches.append((key, metadata))
    if len(matches) != 1:
        raise KrakenMarketDataError(f"TEL/USD pair missing or ambiguous in AssetPairs (matches={len(matches)})")
    key, metadata = matches[0]
    if str(metadata.get("wsname", "")).upper() != EXPECTED_WSNAME:
        raise KrakenMarketDataError("resolved Kraken pair is not exactly TEL/USD")
    if str(metadata.get("status", "online")).lower() != "online":
        raise KrakenMarketDataError("Kraken TEL/USD pair is not online")
    return key, metadata


def _single_result(result: dict[str, Any], label: str) -> dict[str, Any]:
    values = [v for v in result.values() if isinstance(v, dict)]
    if len(values) != 1:
        raise KrakenMarketDataError(f"unexpected {label} result shape")
    return values[0]


def _levels(raw: Any, side: str, server_time: float) -> list[dict[str, float]]:
    if not isinstance(raw, list) or not raw:
        raise KrakenMarketDataError(f"missing {side} depth")
    levels: list[dict[str, float]] = []
    for row in raw[:10]:
        if not isinstance(row, list) or len(row) < 3:
            raise KrakenMarketDataError(f"invalid {side} depth row or missing timestamp")
        price = _positive(row[0], f"{side} depth price")
        quantity = _positive(row[1], f"{side} depth quantity")
        try:
            timestamp = float(row[2])
        except (TypeError, ValueError) as exc:
            raise KrakenMarketDataError(f"invalid {side} depth timestamp") from exc
        if not math.isfinite(timestamp) or timestamp <= 0:
            raise KrakenMarketDataError(f"invalid {side} depth timestamp")
        age = server_time - timestamp
        # Kraken's L2 timestamp is associated with that price level, not the whole HTTP snapshot.
        # Old levels can remain valid; reject only implausible future timestamps. The fresh
        # HTTP snapshot and timestamped recent trades establish current market context.
        if age < -2:
            raise KrakenMarketDataError(f"{side} depth timestamp is in the future ({age:.3f}s)")
        levels.append({"price": price, "quantity": quantity, "timestamp": timestamp,
                       "level_age_seconds": round(age, 3)})
    return levels


def collect_snapshot() -> dict[str, Any]:
    """Fetch and validate public Kraken TEL/USD ticker, depth, trades, and closed 15m candles."""
    started = time.monotonic()
    http_statuses: dict[str, int] = {}
    asset_pairs, _, status = _get_json("AssetPairs")
    http_statuses["AssetPairs"] = status
    pair_key, pair_metadata = _resolve_pair(asset_pairs)

    # Kraken public rate limits are respected with spacing between requests.
    time.sleep(REQUEST_SPACING_SECONDS)
    server_result, _, status = _get_json("Time")
    http_statuses["Time"] = status
    try:
        server_time = float(server_result["unixtime"])
    except (KeyError, TypeError, ValueError) as exc:
        raise KrakenMarketDataError("missing/invalid Kraken server time") from exc
    if not math.isfinite(server_time) or server_time <= 0:
        raise KrakenMarketDataError("invalid Kraken server time")

    time.sleep(REQUEST_SPACING_SECONDS)
    ticker_result, _, status = _get_json("Ticker", {"pair": pair_key})
    http_statuses["Ticker"] = status
    ticker = _single_result(ticker_result, "Ticker")
    if not all(key in ticker for key in ("a", "b", "c")):
        raise KrakenMarketDataError("incomplete Kraken ticker")
    ask = _positive(ticker["a"][0] if isinstance(ticker["a"], list) and ticker["a"] else None, "ticker ask")
    bid = _positive(ticker["b"][0] if isinstance(ticker["b"], list) and ticker["b"] else None, "ticker bid")
    last = _positive(ticker["c"][0] if isinstance(ticker["c"], list) and ticker["c"] else None, "ticker last")
    if bid >= ask:
        raise KrakenMarketDataError("invalid/locked Kraken ticker: bid >= ask")
    spread_pct = (ask - bid) / ((ask + bid) / 2) * 100
    if spread_pct > MAX_SPREAD_PCT:
        raise KrakenMarketDataError(f"spread too wide ({spread_pct:.4f}%)")

    time.sleep(REQUEST_SPACING_SECONDS)
    depth_result, _, status = _get_json("Depth", {"pair": pair_key, "count": "10"})
    http_statuses["Depth"] = status
    depth = _single_result(depth_result, "Depth")
    bids = _levels(depth.get("bids"), "bid", server_time)
    asks = _levels(depth.get("asks"), "ask", server_time)
    if bids[0]["price"] >= asks[0]["price"]:
        raise KrakenMarketDataError("crossed/locked Kraken depth: bid >= ask")
    if abs(bids[0]["price"] - bid) / bid * 100 > 0.01 or abs(asks[0]["price"] - ask) / ask * 100 > 0.01:
        raise KrakenMarketDataError("Kraken ticker and depth best levels disagree")

    time.sleep(REQUEST_SPACING_SECONDS)
    trades_result, _, status = _get_json("Trades", {"pair": pair_key})
    http_statuses["Trades"] = status
    trades = [v for k, v in trades_result.items() if k != "last" and isinstance(v, list)]
    if len(trades) != 1 or not trades[0]:
        raise KrakenMarketDataError("missing/malformed Kraken recent trades")
    trade_rows = trades[0]
    parsed_trades = []
    for row in trade_rows:
        if not isinstance(row, list) or len(row) < 3:
            raise KrakenMarketDataError("malformed Kraken trade row")
        try:
            row_time = float(row[2])
        except (TypeError, ValueError) as exc:
            raise KrakenMarketDataError("missing/invalid Kraken trade timestamp") from exc
        if not math.isfinite(row_time) or row_time <= 0:
            raise KrakenMarketDataError("invalid Kraken trade timestamp")
        parsed_trades.append((row_time, row))
    # Kraken REST returns recent trades oldest-to-newest; choose the maximum timestamp,
    # not the first row, which may be hours old on an illiquid pair.
    trade_time, trade = max(parsed_trades, key=lambda item: item[0])
    trade_price = _positive(trade[0], "last trade price")
    trade_qty = _positive(trade[1], "last trade quantity")
    trade_age = server_time - trade_time
    if trade_age < -2 or trade_age > MAX_MARKET_DATA_AGE_SECONDS:
        raise KrakenMarketDataError(f"Kraken last trade stale or in future ({trade_age:.3f}s)")
    divergence_pct = abs(last - trade_price) / ((last + trade_price) / 2) * 100
    if divergence_pct > 1.0:
        raise KrakenMarketDataError(f"ticker/last-trade divergence too high ({divergence_pct:.4f}%)")

    time.sleep(REQUEST_SPACING_SECONDS)
    ohlc_result, _, status = _get_json("OHLC", {"pair": pair_key, "interval": "15"})
    http_statuses["OHLC"] = status
    candle_arrays = [v for k, v in ohlc_result.items() if k != "last" and isinstance(v, list)]
    if len(candle_arrays) != 1 or len(candle_arrays[0]) < 2:
        raise KrakenMarketDataError("not enough Kraken OHLC candles")
    raw_candles = candle_arrays[0]
    candles = []
    for row in raw_candles:
        if not isinstance(row, list) or len(row) < 8:
            raise KrakenMarketDataError("invalid Kraken OHLC row")
        try:
            open_time = int(row[0])
            o, high, low, close, volume = (float(row[i]) for i in (1, 2, 3, 4, 6))
            count = int(row[7])
        except (TypeError, ValueError, IndexError) as exc:
            raise KrakenMarketDataError("malformed Kraken OHLC row") from exc
        if not all(math.isfinite(v) for v in (o, high, low, close, volume)):
            raise KrakenMarketDataError("non-finite Kraken OHLCV")
        if min(o, high, low, close) <= 0 or volume < 0 or count < 0 or high < max(o, close, low) or low > min(o, close):
            raise KrakenMarketDataError("incoherent Kraken OHLCV candle")
        candles.append({"open_time": _utc(open_time), "open_time_epoch": open_time,
                        "open": o, "high": high, "low": low, "close": close,
                        "volume": volume, "trade_count": count})
    candles.sort(key=lambda c: c["open_time_epoch"])
    if any(candles[i]["open_time_epoch"] >= candles[i + 1]["open_time_epoch"] for i in range(len(candles) - 1)):
        raise KrakenMarketDataError("duplicate Kraken candle timestamps")
    closed = [c for c in candles if c["open_time_epoch"] + 900 <= server_time]
    if not closed:
        raise KrakenMarketDataError("no closed Kraken 15m candle available")

    elapsed = time.monotonic() - started
    if elapsed > MAX_COLLECTION_SECONDS:
        raise KrakenMarketDataError(f"Kraken collection too slow ({elapsed:.2f}s)")

    observed_at = datetime.now(timezone.utc).isoformat()
    return {
        "source": "Kraken Spot public REST",
        "http_statuses": http_statuses,
        "symbol": "TEL/USD",
        "pair_key": pair_key,
        "pair_status": pair_metadata.get("status"),
        "quote_currency": "USD",
        "observed_at_utc": observed_at,
        "server_time_utc": _utc(server_time),
        "ticker_timestamp": None,
        "ticker_freshness_verified": False,
        "ticker_freshness_note": "Kraken Ticker REST response has no quote timestamp; values are cross-checked against fresh timestamped trades and the just-retrieved L2 snapshot.",
        "depth_timestamp_note": "L2 level timestamps describe price-level events, not HTTP snapshot age; the snapshot is observed at collection time.",
        "last": last,
        "bid": bid,
        "ask": ask,
        "spread_pct": spread_pct,
        "trade": {"price": trade_price, "quantity": trade_qty, "timestamp_utc": _utc(trade_time),
                  "age_seconds": round(trade_age, 3)},
        "depth": {"bids": bids, "asks": asks},
        "latest_closed_15m_candle": closed[-1],
        "recent_closed_15m_candles": closed,
        "validation": {
            "exact_pair": True, "positive_prices": True, "bid_below_ask": True,
            "spread_within_limit": True, "depth_fresh": True, "trade_fresh": True,
            "ticker_depth_consistent": True, "ticker_trade_consistent": True,
            "closed_candle_available": True,
        },
        "collection_duration_seconds": round(elapsed, 3),
    }
