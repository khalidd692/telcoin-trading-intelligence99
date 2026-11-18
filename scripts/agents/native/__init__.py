"""TEL99 native mission runner (issue #86 / owner directive on sovereignty).

A minimal, stdlib-only way for *our own project* to launch a bounded agent
mission with an interchangeable model provider -- with no dependency on Hermes
Desktop, Kilo Agent Manager or OpenHands Cloud at runtime.

The package reuses the existing intelligence layer (router, memory, catalog),
the protocol store and the free-model allowlist; it re-implements none of them.

  * :mod:`native.provider` -- the interchangeable provider contract + adapters.
  * :mod:`native.mission`  -- the bounded kernel and deterministic verdicts.
  * :mod:`native.cli`      -- the native entry point (``python -m ...``).

Nothing here places an order, merges a branch, deploys, installs a package or
writes a secret. A real run is fail-closed on an unknown or low quota.
"""

from __future__ import annotations

from . import mission, provider  # noqa: F401

__all__ = ["provider", "mission"]
