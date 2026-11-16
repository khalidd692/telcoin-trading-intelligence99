"""Emergency stop (kill-switch) for the TEL99 cloud-autonomy orchestrator.

A single, deterministic brake that halts any real mission before a conversation
is started, regardless of the configured cron, the queue, or a running mission.
It is checked *first* in ``run()`` — before the environment probe, before the
preflight, before any spend — so flipping it stops the next run immediately.

Three independent sources are consulted; any one of them being set stops the run:

  * ``TEL99_EMERGENCY_STOP`` — an environment flag the automation config (or an
    operator) can set to ``1`` / ``true`` / ``yes`` / ``on``;
  * the KV key ``emergency_stop`` — durable across containers, so it survives the
    destruction of the pod that set it (the cloud path);
  * the local sentinel file ``.tel99-automation-state/EMERGENCY_STOP`` — the
    offline / on-host path.

Why fail-open on a *read* error but fail-closed on a *set* flag: an unreadable
KV must not wedge the queue forever (the local sentinel and the env flag still
work), but a flag that *is* present always stops the run. This mirrors the
project's rule that an unknown value is never treated as "safe to spend" only
where a spend is at stake; here the brake is additive, so an unreadable remote
source degrades to the two local sources instead of blocking every future run.
"""

from __future__ import annotations

import os
import pathlib

# Environment flag names, checked case-insensitively by value.
ENV_FLAG = "TEL99_EMERGENCY_STOP"

# Durable KV key. The orchestrator passes its own ``kv_get`` reader so this
# module has no dependency on the KV implementation.
KV_KEY = "emergency_stop"

# Local sentinel file name, relative to the automation state directory.
SENTINEL_NAME = "EMERGENCY_STOP"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in _TRUTHY


def env_stop() -> bool:
    """True when the environment flag requests an emergency stop."""
    return _truthy(os.environ.get(ENV_FLAG))


def sentinel_stop(state_dir: str | pathlib.Path) -> bool:
    """True when the local sentinel file exists."""
    try:
        return (pathlib.Path(state_dir) / SENTINEL_NAME).exists()
    except OSError:
        return False


def kv_stop(kv_get) -> bool:
    """True when the durable KV flag is set. ``kv_get`` may raise; treat as no."""
    try:
        record = kv_get(KV_KEY)
    except Exception:  # noqa: BLE001 - an unreadable remote brake is not a brake
        return False
    if isinstance(record, dict):
        return _truthy(record.get("stopped")) or _truthy(record.get("active"))
    return _truthy(record)


def stop_requested(state_dir: str | pathlib.Path, kv_get) -> tuple[bool, str]:
    """Return ``(stopped, reason)`` for the first source that is set.

    ``kv_get`` is the orchestrator's KV reader (``None`` when the KV store is
    unavailable). The check order is local-first so a stop is recognised even
    when the durable store is unreachable.
    """
    if env_stop():
        return True, f"{ENV_FLAG} is set"
    if sentinel_stop(state_dir):
        return True, f"sentinel file {SENTINEL_NAME} is present"
    if kv_get is not None and kv_stop(kv_get):
        return True, f"KV key {KV_KEY!r} is set"
    return False, ""
