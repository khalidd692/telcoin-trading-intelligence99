"""Emergency stop (kill-switch) for the TEL99 cloud-autonomy orchestrator.

A single, deterministic brake that halts any real mission before a conversation
is started, regardless of the configured cron, the queue, or a running mission.
It is checked *first* in ``run()`` — before the environment probe, before the
preflight, before any spend — so flipping it stops the next run immediately.

Two distinct guarantees, deliberately separated:

  * **Prevent the next launch** — :func:`local_stop` / :func:`stop_requested`
    are evaluated at the very start of a run, before any network access. Setting
    a flag makes the *next* run stop (exit 3) with no conversation and no spend.
  * **Interrupt a mission already active** — the orchestrator's ``wait_for``
    polls the local brake while a conversation runs and, when it is set, calls
    the agent-server ``/interrupt`` endpoint (see ``interrupt_conversation`` in
    the orchestrator). This only reaches a conversation the *same* run is
    driving; a conversation started by another container must be interrupted via
    the documented operator procedure (see ``docs/agents/ACTIVATION_RUNBOOK.md``).

Setting the brake is therefore necessary but not sufficient to stop a mission
that another pod is already running: the brake stops *this* run's next action,
and the durable KV flag stops the next run anywhere. The runbook states this
limit explicitly rather than promising an instant global stop.

Three independent sources are consulted; any one of them being set stops the run:

  * ``TEL99_EMERGENCY_STOP`` — an environment flag the automation config (or an
    operator) can set to ``1`` / ``true`` / ``yes`` / ``on`` (local, no network);
  * the local sentinel file ``.tel99-automation-state/EMERGENCY_STOP`` — the
    offline / on-host path (local, no network);
  * the KV key ``emergency_stop`` — durable across containers, so it survives the
    destruction of the pod that set it (network; checked after the local ones).

Why the local sources are checked before the KV one: an operator halting a run
must not depend on — or wait for — a network read. ``run()`` therefore evaluates
the local brake *before* ``load_state()`` (which reads the KV store), and only
then consults the durable KV flag.
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


def local_stop(state_dir: str | pathlib.Path) -> tuple[bool, str]:
    """Return ``(stopped, reason)`` for the local sources only. No network.

    Used first in ``run()`` so the brake is honoured before ``load_state()``
    reads the KV store over the network.
    """
    if env_stop():
        return True, f"{ENV_FLAG} is set"
    if sentinel_stop(state_dir):
        return True, f"sentinel file {SENTINEL_NAME} is present"
    return False, ""


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
    stopped, reason = local_stop(state_dir)
    if stopped:
        return stopped, reason
    if kv_get is not None and kv_stop(kv_get):
        return True, f"KV key {KV_KEY!r} is set"
    return False, ""
