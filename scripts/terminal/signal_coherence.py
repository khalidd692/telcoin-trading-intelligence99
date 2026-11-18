#!/usr/bin/env python3
"""Independent coherence check for a published TEL99 signal snapshot.

This module answers one narrow, verifiable question about a snapshot such as the
public ``data.json`` of the TEL99 terminal:

    does the snapshot ever present a *market signal* as a *confirmed buy*, and
    does it fail closed when the data is stale, undated, missing or incoherent?

It is deliberately read-only, deterministic and stdlib-only: it consumes a
plain dict, calls no network, writes nothing, and never produces an order. It is
the reusable core behind ``tests/test_signal_coherence.py`` and can be applied
to any snapshot with the documented shape (a small, isolated fixture is used in
the test so the check does not depend on the live site being reachable).

The four distinct objects of the TEL99 vocabulary are kept separate, never
conflated:

  * ``market_early_alert`` — an early technical condition is forming;
  * ``market_confirmation`` — the technical pattern is validated on a close;
  * ``market_invalidation`` — the pattern is broken;
  * ``risk_checked_buy`` — every execution cost is verified and the plan is
    admissible. Only this one may ever be called a "confirmed buy".

A technical confirmation is **not** a confirmed buy: it says nothing about
fees, spread, liquidity or the net risk/reward.
"""

from __future__ import annotations

import datetime as _dt

# Distinct decision objects (never merge these labels).
MARKET_EARLY_ALERT = "market_early_alert"
MARKET_CONFIRMATION = "market_confirmation"
MARKET_INVALIDATION = "market_invalidation"
RISK_CHECKED_BUY = "risk_checked_buy"

# Default freshness ceiling for the fail-closed rule (minutes).
DEFAULT_MAX_AGE_MINUTES = 15.0

# Verdicts a human/agent may act on.
VERDICT_WAIT = "ATTENDRE"
VERDICT_CAUTION = "PRUDENCE"
VERDICT_INSUFFICIENT = "DONNEES_INSUFFISANTES"


def _parse_utc(value) -> _dt.datetime | None:
    """Parse an ISO-8601 timestamp (with ``Z`` or ``+00:00``) to aware UTC."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone(_dt.timezone.utc)


def _as_epoch(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def freshness(snapshot: dict, now: _dt.datetime | None = None,
              max_age_minutes: float = DEFAULT_MAX_AGE_MINUTES) -> dict:
    """Return the age (minutes) of the snapshot and of each timeframe's close.

    ``age_minutes`` is measured from ``captured_at`` (the moment the data was
    produced) to ``now`` — this is the real staleness of the *snapshot*. The
    per-timeframe gap is measured from the last closed candle, which is
    mechanically older for coarse frames and is reported for transparency.
    """
    now = now or _dt.datetime.now(_dt.timezone.utc)
    captured = _parse_utc(snapshot.get("captured_at"))
    result: dict = {
        "captured_at": snapshot.get("captured_at"),
        "now": now.isoformat().replace("+00:00", "Z"),
        "max_age_minutes": max_age_minutes,
        "age_minutes": None,
        "fresh": False,
        "per_frame": {},
        "reasons": [],
    }
    if captured is None:
        result["reasons"].append("captured_at missing or unparsable")
        return result
    age = (now - captured).total_seconds() / 60.0
    result["age_minutes"] = age
    result["fresh"] = age <= max_age_minutes
    if not result["fresh"]:
        result["reasons"].append(
            f"snapshot is {age:.2f} min old (> {max_age_minutes} min)")

    frames = snapshot.get("frames") or {}
    if not frames:
        result["reasons"].append("no frames present")
    for name, frame in frames.items():
        quality = (frame or {}).get("quality") or {}
        last_close = _as_epoch(quality.get("last_close"))
        gap = None
        if last_close is not None:
            close_dt = _dt.datetime.fromtimestamp(last_close, _dt.timezone.utc)
            gap = (captured - close_dt).total_seconds() / 60.0
        result["per_frame"][name] = {
            "gap_minutes": gap,
            "fresh": quality.get("fresh"),
            "coverage_pct": quality.get("coverage_pct"),
        }
    return result


def classify(snapshot: dict) -> dict:
    """Classify the snapshot into the TEL99 objects, keeping them distinct.

    Returns a dict with the raw facts and a boolean per object. ``confirmed_buy``
    is true **only** when ``risk_checked_buy`` is true and the plan is
    admissible; a technical ``confirmed`` flag alone never sets it.
    """
    decision = snapshot.get("decision") or {}
    plan = decision.get("plan") or {}
    event = ((snapshot.get("radar") or {}).get("event")) or {}
    safety = snapshot.get("safety") or {}

    event_type = str(event.get("type") or "").upper()
    early = event_type == "EARLY_ALERT" or event_type == "EARLY"
    confirmed = bool(event.get("confirmed")) and (
        event_type == "CONFIRMATION" or "CONFIRMATION" in str(event.get("decision") or "").upper())
    invalidation = event_type == "INVALIDATION" or "INVALIDATION" in str(
        event.get("decision") or "").upper()

    risk_checked_buy = bool(event.get("risk_checked_buy"))
    admissible = bool(plan.get("admissible"))
    execution_allowed = bool(decision.get("execution_allowed"))
    min_rr = safety.get("min_rr")
    rr_gross = plan.get("rr_gross")
    rr_net = plan.get("rr_net")

    # A confirmed buy requires ALL of: the risk-checked flag, an admissible
    # plan, execution allowed, and a gross AND net RR above the floor.
    rr_ok = True
    if isinstance(min_rr, (int, float)):
        if isinstance(rr_gross, (int, float)):
            rr_ok = rr_ok and rr_gross >= min_rr
        else:
            rr_ok = False
        if isinstance(rr_net, (int, float)):
            rr_ok = rr_ok and rr_net >= min_rr
        else:
            rr_ok = False
    else:
        rr_ok = False  # a missing floor is itself a fail-closed condition

    confirmed_buy = (risk_checked_buy and admissible and execution_allowed
                     and rr_ok)

    return {
        "market_early_alert": early,
        "market_confirmation": confirmed,
        "market_invalidation": invalidation,
        "risk_checked_buy": risk_checked_buy,
        "confirmed_buy": confirmed_buy,
        "execution_allowed": execution_allowed,
        "plan_admissible": admissible,
        "rr_gross": rr_gross,
        "rr_net": rr_net,
        "min_rr": min_rr,
        "real_orders": bool(safety.get("real_orders")),
        "paper_orders": bool(safety.get("paper_orders")),
        "status": decision.get("status"),
    }


def incoherences(snapshot: dict) -> list[str]:
    """Return concrete contradictions between the objects, if any.

    A contradiction is a snapshot that presents a confirmed buy without the
    risk check, or that claims execution while the plan is inadmissible or the
    safety flags forbid orders.
    """
    facts = classify(snapshot)
    problems: list[str] = []
    if facts["confirmed_buy"] and not facts["risk_checked_buy"]:
        problems.append("confirmed buy without risk_checked_buy")
    if facts["confirmed_buy"] and not facts["plan_admissible"]:
        problems.append("confirmed buy with an inadmissible plan")
    if facts["execution_allowed"] and not facts["plan_admissible"]:
        problems.append("execution_allowed while the plan is inadmissible")
    if facts["execution_allowed"] and facts["market_confirmation"] \
            and not facts["risk_checked_buy"]:
        problems.append("execution_allowed on a technical confirmation only")
    if (facts["real_orders"] or facts["paper_orders"]) and not facts["confirmed_buy"]:
        problems.append("orders enabled without a confirmed buy")
    return problems


def fail_closed(snapshot: dict, now: _dt.datetime | None = None,
                max_age_minutes: float = DEFAULT_MAX_AGE_MINUTES) -> dict:
    """Decide whether the snapshot must be refused on data-quality grounds.

    The rule is fail-closed: missing, undated, stale (> ``max_age_minutes``) or
    incoherent data means "do not act", regardless of the technical signal.
    """
    fresh = freshness(snapshot, now=now, max_age_minutes=max_age_minutes)
    problems = list(fresh["reasons"]) + incoherences(snapshot)
    facts = classify(snapshot)
    if not facts["min_rr"]:
        problems.append("min_rr missing: net risk/reward cannot be checked")
    return {
        "refused": bool(problems),
        "reasons": problems,
        "freshness": fresh,
    }


def verdict(snapshot: dict, now: _dt.datetime | None = None,
            max_age_minutes: float = DEFAULT_MAX_AGE_MINUTES) -> dict:
    """The single exploitable result: a label plus the facts behind it.

    * ``DONNEES_INSUFFISANTES`` — data is stale, undated, missing or incoherent;
    * ``ATTENDRE`` — data is fresh but nothing authorises a buy;
    * ``PRUDENCE`` — data is fresh, a technical confirmation exists, but no
      confirmed buy (which is still not an order authorisation).
    """
    gate = fail_closed(snapshot, now=now, max_age_minutes=max_age_minutes)
    facts = classify(snapshot)
    if gate["refused"]:
        label = VERDICT_INSUFFICIENT
    elif facts["confirmed_buy"]:
        label = VERDICT_WAIT  # still never an order: costs are the operator's
    elif facts["market_confirmation"]:
        label = VERDICT_CAUTION
    else:
        label = VERDICT_WAIT
    return {
        "verdict": label,
        "confirmed_buy": facts["confirmed_buy"],
        "market_confirmation": facts["market_confirmation"],
        "risk_checked_buy": facts["risk_checked_buy"],
        "fail_closed": gate["refused"],
        "reasons": gate["reasons"],
        "facts": facts,
    }
