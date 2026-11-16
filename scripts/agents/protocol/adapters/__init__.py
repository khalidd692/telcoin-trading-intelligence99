"""Adapters that bind each environment to the TEL99 interchange protocol.

Each adapter is a thin, honest translator: it exposes what the environment can
*actually* do and declares ``connected`` accordingly. An adapter never invents
a transport that does not exist.

  * :mod:`adapters.openhands` — real: the local agent-server and OpenHands Cloud
    API are reachable, so this adapter is ``connected``.
  * :mod:`adapters.hermes` — real within this repository: it wraps the existing
    model router, shared memory and improvement loop from
    ``scripts/agents/intelligence``.
  * :mod:`adapters.kilo` — declared but NOT connected: no Kilo component exists
    in the repository (verified), so it exchanges envelopes only through the
    file bus (inbox/outbox), and says so.
"""

from __future__ import annotations

from . import hermes, kilo, openhands  # noqa: F401

__all__ = ["openhands", "hermes", "kilo"]
