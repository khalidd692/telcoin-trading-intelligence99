"""Diagnostic-only quality guards for optional TradingView data.

These helpers do not place orders and do not alter the native exchange verdict.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Iterable


def _comparable(value: Any) -> Any:
    """Normalize finite numeric strings/numbers while preserving other values."""
    if value is None or isinstance(value, bool):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return number if math.isfinite(number) else value


def diagnose_identical_cross_venue_data(
    left_symbol: str,
    left_payload: dict[str, Any],
    right_symbol: str,
    right_payload: dict[str, Any],
    fields: Iterable[str],
    *,
    minimum_matching_fields: int = 3,
) -> dict[str, Any]:
    """Flag a suspiciously identical payload; never claim this proves corruption."""
    checked = [
        field for field in fields
        if field in left_payload and field in right_payload
        and left_payload[field] is not None and right_payload[field] is not None
    ]
    matches = [
        field for field in checked
        if _comparable(left_payload[field]) == _comparable(right_payload[field])
    ]
    different_symbols = left_symbol.strip().upper() != right_symbol.strip().upper()
    suspect = (
        different_symbols
        and len(matches) >= minimum_matching_fields
        and len(checked) >= minimum_matching_fields
        and len(matches) == len(checked)
    )
    return {
        "status": "SUSPECT_IDENTIQUE" if suspect else "NON_SIGNALÉ",
        "left_symbol": left_symbol,
        "right_symbol": right_symbol,
        "checked_fields": checked,
        "matching_fields": matches,
        "note": (
            "Alerte diagnostique seulement : des valeurs identiques ne prouvent pas "
            "une corruption. Vérifier l'instrument, la source et le cache."
            if suspect else
            "Aucune identité complète suspecte détectée sur les champs comparables."
        ),
    }


def validate_order_book(
    bids: Any,
    asks: Any,
    *,
    observed_age_seconds: float | None = None,
    max_age_seconds: float = 120.0,
) -> dict[str, Any]:
    """Validate basic L2 shape, best prices, crossed books, and optional age."""
    def levels_valid(levels: Any) -> bool:
        if not isinstance(levels, list) or not levels:
            return False
        for level in levels:
            if not isinstance(level, (list, tuple)) or len(level) < 2:
                return False
            try:
                price, quantity = float(level[0]), float(level[1])
            except (TypeError, ValueError):
                return False
            if not math.isfinite(price) or not math.isfinite(quantity) or price <= 0 or quantity <= 0:
                return False
        return True

    problems: list[str] = []
    if not levels_valid(bids):
        problems.append("BIDS_EMPTY_OR_INVALID")
    if not levels_valid(asks):
        problems.append("ASKS_EMPTY_OR_INVALID")

    if not problems:
        bid_prices = [float(level[0]) for level in bids]
        ask_prices = [float(level[0]) for level in asks]
        if bid_prices[0] >= ask_prices[0]:
            problems.append("BOOK_CROSSED_OR_LOCKED")
        if any(bid_prices[i] < bid_prices[i + 1] for i in range(len(bid_prices) - 1)):
            problems.append("BIDS_NOT_DESCENDING")
        if any(ask_prices[i] > ask_prices[i + 1] for i in range(len(ask_prices) - 1)):
            problems.append("ASKS_NOT_ASCENDING")

    if observed_age_seconds is not None:
        try:
            age = float(observed_age_seconds)
        except (TypeError, ValueError):
            age = math.inf
        if not math.isfinite(age) or age < 0:
            problems.append("BOOK_AGE_INVALID_OR_FUTURE")
        elif age > max_age_seconds:
            problems.append("BOOK_STALE")

    return {
        "status": "VERIFIED" if not problems else "NON_VÉRIFIÉ",
        "problems": problems,
        "best_bid": float(bids[0][0]) if levels_valid(bids) else None,
        "best_ask": float(asks[0][0]) if levels_valid(asks) else None,
    }


def validate_timestamp(
    timestamp: str | datetime,
    *,
    now: datetime | None = None,
    max_age_seconds: float = 1200.0,
    future_tolerance_seconds: float = 5.0,
) -> dict[str, Any]:
    """Check an ISO timestamp for parseability, staleness, and excessive futurity."""
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00")) if isinstance(timestamp, str) else timestamp
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return {"status": "NON_VÉRIFIÉ", "age_seconds": None, "reason": "TIMESTAMP_INVALID"}

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    age = (current.astimezone(timezone.utc) - parsed).total_seconds()
    if age < -future_tolerance_seconds:
        return {"status": "NON_VÉRIFIÉ", "age_seconds": age, "reason": "TIMESTAMP_IN_FUTURE"}
    if age > max_age_seconds:
        return {"status": "NON_VÉRIFIÉ", "age_seconds": age, "reason": "DATA_STALE"}
    return {"status": "VERIFIED", "age_seconds": age, "reason": None}


def preserve_native_verdict(native_status: str, tradingview_quality: str) -> dict[str, str]:
    """Optional TradingView data cannot upgrade or replace the native verdict."""
    allowed = {"VERIFIED"}
    if tradingview_quality not in allowed:
        return {
            "status": native_status,
            "tradingview": tradingview_quality,
            "effect": "IGNORÉ_PAR_DÉFAUT",
        }
    return {
        "status": native_status,
        "tradingview": tradingview_quality,
        "effect": "CONTRÔLE_CROISÉ_SEULEMENT",
    }
