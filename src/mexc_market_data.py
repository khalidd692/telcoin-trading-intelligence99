"""Read-only MEXC Spot market snapshot with fail-closed validation.

No credentials or trading endpoints are used. Public market-data endpoints only.
"""
from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

BASE = "https://api.mexc.com"
SYMBOL = "TELUSDT"
TIMEOUT_SECONDS = 10
MAX_TRADE_AGE_SECONDS = 60
MAX_LAST_TRADE_DIVERGENCE_PCT = 1.0
MAX_SPREAD_PCT = 0.50
USER_AGENT = "telcoin-trading-intelligence/0.2 (read-only public market data)"


class MarketDataError(RuntimeError):
    """Raised when required public market data cannot be validated."""


def utc_iso(epoch_ms: int | float) -> str:
    return datetime.fromtimestamp(float(epoch_ms) / 1000, timezone.utc).isoformat()


def _get_json(path: str, *, now_ms: int | None = None) -> tuple[Any, int]:
    url = f"{BASE}{path}"
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json",
        "Cache-Control": "no-cache",
    })
    received_ms = int(time.time() * 1000) if now_ms is None else now_ms
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            received_ms = int(time.time() * 1000) if now_ms is None else now_ms
            if response.status != 200:
                raise MarketDataError(f"HTTP {response.status} from {path}")
            raw = response.read(1_000_000)
        payload = json.loads(raw.decode("utf-8"))
    except MarketDataError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MarketDataError(f"request/parse failure for {path}: {type(exc).__name__}") from exc
    return payload, received_ms


def _positive(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise MarketDataError(f"invalid {label}") from exc
    if not math.isfinite(result) or result <= 0:
        raise MarketDataError(f"invalid {label}")
    return result


def _levels(value: Any, label: str) -> list[dict[str, float]]:
    if not isinstance(value, list) or not value:
        raise MarketDataError(f"missing {label} depth")
    result = []
    for row in value[:5]:
        if not isinstance(row, list) or len(row) < 2:
            raise MarketDataError(f"invalid {label} depth row")
        price = _positive(row[0], f"{label} depth price")
        try:
            quantity = float(row[1])
        except (TypeError, ValueError) as exc:
            raise MarketDataError(f"invalid {label} depth quantity") from exc
        if not math.isfinite(quantity) or quantity <= 0:
            raise MarketDataError(f"invalid {label} depth quantity")
        result.append({"price": price, "quantity": quantity})
    return result


def collect_snapshot(*, max_trade_age_seconds: int = MAX_TRADE_AGE_SECONDS) -> dict[str, Any]:
    """Fetch public MEXC ticker, bookTicker, depth, last trade, server time and closed candles."""
    received_start = int(time.time() * 1000)
    server_payload, _ = _get_json("/api/v3/time")
    if not isinstance(server_payload, dict) or not isinstance(server_payload.get("serverTime"), (int, float)):
        raise MarketDataError("invalid MEXC server time response")
    server_ms = int(server_payload["serverTime"])
    received_at = datetime.now(timezone.utc).isoformat()

    price_payload, _ = _get_json(f"/api/v3/ticker/price?symbol={SYMBOL}")
    if not isinstance(price_payload, dict) or price_payload.get("symbol") != SYMBOL:
        raise MarketDataError("invalid ticker/price symbol or schema")
    last = _positive(price_payload.get("price"), "last price")

    book_payload, _ = _get_json(f"/api/v3/ticker/bookTicker?symbol={SYMBOL}")
    if not isinstance(book_payload, dict) or book_payload.get("symbol") != SYMBOL:
        raise MarketDataError("invalid bookTicker symbol or schema")
    bid = _positive(book_payload.get("bidPrice"), "best bid")
    bid_qty = _positive(book_payload.get("bidQty"), "best bid quantity")
    ask = _positive(book_payload.get("askPrice"), "best ask")
    ask_qty = _positive(book_payload.get("askQty"), "best ask quantity")
    if bid >= ask:
        raise MarketDataError("crossed/locked book: bid >= ask")
    spread_pct = (ask - bid) / ((ask + bid) / 2) * 100

    depth_payload, _ = _get_json(f"/api/v3/depth?symbol={SYMBOL}&limit=5")
    if not isinstance(depth_payload, dict):
        raise MarketDataError("invalid depth response schema")
    bids = _levels(depth_payload.get("bids"), "bid")
    asks = _levels(depth_payload.get("asks"), "ask")
    if bids[0]["price"] >= asks[0]["price"]:
        raise MarketDataError("crossed/locked depth: best bid >= best ask")
    if abs(bids[0]["price"] - bid) / bid * 100 > 0.01 or abs(asks[0]["price"] - ask) / ask * 100 > 0.01:
        raise MarketDataError("bookTicker and depth best levels disagree")

    trades_payload, _ = _get_json(f"/api/v3/trades?symbol={SYMBOL}&limit=1")
    if not isinstance(trades_payload, list) or not trades_payload or not isinstance(trades_payload[0], dict):
        raise MarketDataError("missing last trade timestamp")
    trade = trades_payload[0]
    trade_price = _positive(trade.get("price"), "last trade price")
    trade_ms = trade.get("time")
    if not isinstance(trade_ms, (int, float)) or trade_ms <= 0:
        raise MarketDataError("missing/invalid last trade timestamp")
    trade_ms = int(trade_ms)
    age_seconds = (server_ms - trade_ms) / 1000
    if age_seconds < -2:
        raise MarketDataError("last trade timestamp is ahead of MEXC server time")
    if age_seconds > max_trade_age_seconds:
        raise MarketDataError(f"last trade stale ({age_seconds:.1f}s)")
    divergence_pct = abs(last - trade_price) / ((last + trade_price) / 2) * 100
    if divergence_pct > MAX_LAST_TRADE_DIVERGENCE_PCT:
        raise MarketDataError(f"ticker/last-trade divergence too high ({divergence_pct:.4f}%)")
    if spread_pct > MAX_SPREAD_PCT:
        raise MarketDataError(f"spread too wide ({spread_pct:.4f}%)")

    klines_payload, _ = _get_json(f"/api/v3/klines?symbol={SYMBOL}&interval=15m&limit=5")
    if not isinstance(klines_payload, list) or len(klines_payload) < 2:
        raise MarketDataError("not enough MEXC 15m candles")
    candles = []
    for row in klines_payload:
        if not isinstance(row, list) or len(row) < 6:
            raise MarketDataError("invalid candle schema")
        try:
            open_ms = int(row[0])
            o, h, low, close, volume = (float(row[i]) for i in (1, 2, 3, 4, 5))
        except (TypeError, ValueError, IndexError) as exc:
            raise MarketDataError("malformed candle") from exc
        if not all(math.isfinite(x) for x in (o, h, low, close, volume)):
            raise MarketDataError("non-finite OHLCV")
        if min(o, h, low, close) <= 0 or volume < 0 or h < max(o, close, low) or low > min(o, close):
            raise MarketDataError("incoherent OHLCV candle")
        candles.append({"open_time": utc_iso(open_ms), "open_time_ms": open_ms,
                        "open": o, "high": h, "low": low, "close": close, "volume": volume})
    candles.sort(key=lambda candle: candle["open_time_ms"])
    if any(candles[i]["open_time_ms"] >= candles[i + 1]["open_time_ms"] for i in range(len(candles) - 1)):
        raise MarketDataError("duplicate candle timestamps")
    now_ms = server_ms
    closed = [c for c in candles if c["open_time_ms"] + 900_000 <= now_ms]
    if not closed:
        raise MarketDataError("no closed 15m candle available")

    if int(time.time() * 1000) - received_start > 20_000:
        raise MarketDataError("market snapshot collection took over 20 seconds")

    return {
        "symbol": SYMBOL,
        "source": "MEXC Spot public REST",
        "received_at_utc": received_at,
        "server_time_utc": utc_iso(server_ms),
        "last_trade_at_utc": utc_iso(trade_ms),
        "last_trade_age_seconds": round(age_seconds, 3),
        "last_price": last,
        "last_trade_price": trade_price,
        "ticker_trade_divergence_pct": round(divergence_pct, 6),
        "best_bid": {"price": bid, "quantity": bid_qty},
        "best_ask": {"price": ask, "quantity": ask_qty},
        "spread_pct": round(spread_pct, 6),
        "depth": {"bids": bids, "asks": asks},
        "latest_closed_15m_candle": closed[-1],
        "recent_closed_15m_candles": closed,
        "validation": {
            "price_positive": True, "bid_below_ask": True,
            "spread_within_limit": True, "last_trade_fresh": True,
            "ticker_matches_last_trade": True, "depth_matches_book_ticker": True,
        },
    }
