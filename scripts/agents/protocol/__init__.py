"""TEL99 agent interchange protocol and integration bus.

Public API:
    from protocol import Envelope, Actor, validate
    from protocol.bus import Bus

Everything is stdlib-only, deterministic and read-only with respect to the
repository history: no order, no merge, no deployment, no paid service.
"""

from __future__ import annotations

from .envelope import (Actor, Envelope, PROTOCOL_NAME, PROTOCOL_VERSION,
                       is_terminal, new_id, utcnow_iso, validate, validate_file)

__all__ = [
    "Actor", "Envelope", "validate", "validate_file", "is_terminal",
    "new_id", "utcnow_iso", "PROTOCOL_NAME", "PROTOCOL_VERSION",
]
