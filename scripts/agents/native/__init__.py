"""TEL99 native mission package.

Re-exports the deterministic verdict kernel. ``provider`` is intentionally not
re-exported here: it is delivered separately (Codex 3 / PR #105) and imported
on demand by the runner, keeping this package importable without the provider.
"""

from __future__ import annotations

from . import mission  # noqa: F401

__all__ = ["mission"]
