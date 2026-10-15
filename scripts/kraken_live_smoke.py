"""Optional live smoke test for public Kraken TEL/USD REST data; never places orders."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from src import kraken_market_data as km


def main() -> int:
    started_at = datetime.now(timezone.utc).isoformat()
    km.HTTP_REQUEST_LOG.clear()
    try:
        snapshot = km.collect_snapshot()
        evidence = {
            "test_type": "LIVE_PUBLIC_API",
            "started_at_utc": started_at,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "endpoints": [
                "/0/public/AssetPairs",
                "/0/public/Time",
                "/0/public/Ticker?pair=<resolved-TEL-USD-pair>",
                "/0/public/Depth?pair=<resolved-TEL-USD-pair>&count=10",
                "/0/public/Trades?pair=<resolved-TEL-USD-pair>",
                "/0/public/OHLC?pair=<resolved-TEL-USD-pair>&interval=15",
            ],
            "http_statuses": snapshot["http_statuses"],
            "http_requests": km.HTTP_REQUEST_LOG,
            "source": snapshot["source"],
            "pair": snapshot["symbol"],
            "pair_key": snapshot["pair_key"],
            "server_time_utc": snapshot["server_time_utc"],
            "observed_at_utc": snapshot["observed_at_utc"],
            "ticker": {
                "last": snapshot["last"], "bid": snapshot["bid"], "ask": snapshot["ask"],
                "spread_pct": round(snapshot["spread_pct"], 6),
                "timestamp_available": snapshot["ticker_timestamp"] is not None,
                "freshness_directly_verified": snapshot["ticker_freshness_verified"],
            },
            "last_trade": snapshot["trade"],
            "depth_level_counts": {
                "bids": len(snapshot["depth"]["bids"]),
                "asks": len(snapshot["depth"]["asks"]),
            },
            "latest_closed_15m_candle": snapshot["latest_closed_15m_candle"],
            "validation": snapshot["validation"],
            "collection_duration_seconds": snapshot["collection_duration_seconds"],
            "orders_sent": False,
        }
        print(json.dumps(evidence, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({
            "test_type": "LIVE_PUBLIC_API",
            "started_at_utc": started_at,
            "failed_at_utc": datetime.now(timezone.utc).isoformat(),
            "result": "UNAVAILABLE_OR_INVALID",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "http_requests": km.HTTP_REQUEST_LOG,
            "orders_sent": False,
        }, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
