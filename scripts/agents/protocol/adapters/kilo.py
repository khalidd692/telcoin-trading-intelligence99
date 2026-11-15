#!/usr/bin/env python3
"""Kilo adapter — DECLARED BUT NOT CONNECTED.

The mission brief names "Kilo Code Auto Free" as the independent-validation and
testing environment. A verification of this repository found **no Kilo
component**: no ``kilo`` file or directory, no ``hermes-tel99/router``, and the
existing pilot document states explicitly that there is "no Kilo or Hermes
file". There is therefore no in-process interface to wrap and no verified remote
transport to call.

This adapter is honest about that: it declares ``connected = False``, it can only
exchange envelopes through the **file bus** (a directory an operator or a future
Kilo runner reads and writes), and it refuses to pretend a mission was delivered
to Kilo when nothing received it.

The value it provides today:

  * a **stable contract** Kilo can implement later (the envelope schema);
  * a **conformance test** Kilo's implementation must pass;
  * a **clear, machine-readable "not connected" signal** so the bus never routes
    a live mission to a dead endpoint.
"""

from __future__ import annotations

import json
import pathlib

from ..envelope import Actor, Envelope

# Where a future Kilo runner would pick up and drop envelopes. The bus writes
# here; nothing consumes it until Kilo is actually connected.
DEFAULT_INBOX = pathlib.Path("bus/inbox/kilo")
DEFAULT_OUTBOX = pathlib.Path("bus/outbox/kilo")


def actor() -> Actor:
    return Actor(
        environment="kilo",
        id="kilo-code-auto-free",
        capabilities=("independent_validation", "test_execution"),
        connected=False,
    )


def is_connected() -> bool:
    """Always false today: no Kilo transport exists in this repository."""
    return False


def connection_report() -> dict:
    """A machine-readable statement of what is and is not connected."""
    return {
        "environment": "kilo",
        "connected": False,
        "reason": "no Kilo component found in the repository (verified)",
        "transport": "file bus only (inbox/outbox), no live endpoint",
        "inbox": str(DEFAULT_INBOX),
        "outbox": str(DEFAULT_OUTBOX),
        "what_would_connect_it": (
            "a Kilo runner that reads bus/inbox/kilo/*.json and writes "
            "bus/outbox/kilo/*.json, passing tests/test_agent_protocol.py's "
            "KiloConformanceTests"
        ),
    }


def enqueue(envelope: Envelope, *, inbox: pathlib.Path | None = None) -> pathlib.Path:
    """Drop an envelope for Kilo in the file bus (does not deliver it live)."""
    target_dir = pathlib.Path(inbox or DEFAULT_INBOX)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{envelope.envelope_id}.json"
    path.write_text(envelope.to_json(), encoding="utf-8")
    return path


def collect(*, outbox: pathlib.Path | None = None) -> list[dict]:
    """Read whatever a Kilo runner left in the outbox (empty today)."""
    source = pathlib.Path(outbox or DEFAULT_OUTBOX)
    if not source.is_dir():
        return []
    envelopes = []
    for path in sorted(source.glob("*.json")):
        try:
            envelopes.append(json.loads(path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return envelopes


def conformance_checks(envelope_dict: dict) -> list[str]:
    """The checks a real Kilo implementation must pass to be considered connected.

    Returns the list of problems (empty means conformant). This is what turns
    "Kilo is connected" from a claim into a test.
    """
    from ..envelope import validate

    problems = validate(envelope_dict)
    origin = envelope_dict.get("origin", {})
    if origin.get("environment") != "kilo":
        problems.append("a Kilo envelope must have origin.environment == 'kilo'")
    if envelope_dict.get("kind") not in ("result", "evidence", "error",
                                         "learning", "heartbeat"):
        problems.append("a Kilo reply must be a result, evidence, error, "
                        "learning or heartbeat envelope")
    if envelope_dict.get("kind") == "result" and not envelope_dict.get("result"):
        problems.append("a Kilo result envelope must carry a result block")
    return problems
