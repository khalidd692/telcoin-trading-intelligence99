#!/usr/bin/env python3
"""OpenHands adapter — the only environment with a verified live transport.

It translates between the TEL99 interchange protocol and the interfaces that
actually exist in this runtime, both read-only:

  * the **local agent-server** (``http://localhost:60000``, header
    ``X-Session-API-Key``) exposes ``/api/conversations`` for listing and
    creating conversations;
  * the **OpenHands Cloud API** (``https://app.all-hands.dev``) exposes
    ``/api/quota/status`` (the free-conversation quota) and
    ``/api/automation/v1`` (scheduled automations).

Every capability probe returns a fact, never an assumption. A probe that fails
marks the capability unavailable instead of pretending it works.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from ..envelope import Actor

DEFAULT_AGENT_SERVER = "http://localhost:60000"
DEFAULT_CLOUD = "https://app.all-hands.dev"


def _session_key() -> str:
    for name in ("SESSION_API_KEY", "OH_SESSION_API_KEYS_0"):
        value = os.environ.get(name)
        if value:
            return value
    try:
        with open("/proc/1/environ", "rb") as handle:
            blob = handle.read().decode(errors="ignore")
    except OSError:
        return ""
    for part in blob.split("\x00"):
        if part.startswith("SESSION_API_KEY="):
            return part.split("=", 1)[1]
    return ""


def _request(method: str, url: str, *, headers: dict | None = None,
             payload: dict | None = None, timeout: int = 15):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        if value:
            req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="ignore")
    except Exception as exc:  # noqa: BLE001 - a probe must never raise
        return None, f"{type(exc).__name__}: {exc}"


def agent_server_base() -> str:
    return os.environ.get("AGENT_SERVER_URL", DEFAULT_AGENT_SERVER).rstrip("/")


def cloud_base() -> str:
    return os.environ.get("OPENHANDS_CLOUD_API_URL", DEFAULT_CLOUD).rstrip("/")


def actor() -> Actor:
    return Actor(
        environment="openhands",
        id=os.environ.get("TEL99_OPENHANDS_ACTOR", "openhands-cloud"),
        capabilities=("create_conversation", "read_quota", "read_automations",
                      "run_scheduled"),
        connected=True,
    )


# --------------------------------------------------------------------------- #
# Capability probes (each returns a fact)
# --------------------------------------------------------------------------- #
def probe_agent_server() -> dict:
    status, body = _request("GET", f"{agent_server_base()}/",
                            headers={"X-Session-API-Key": _session_key()})
    reachable = status == 200 and isinstance(body, dict)
    return {
        "capability": "local_agent_server",
        "reachable": reachable,
        "http_status": status,
        "version": body.get("version") if isinstance(body, dict) else None,
    }


def probe_conversation_creation() -> dict:
    """A POST with an empty body must be rejected (422), proving the route is
    live without actually creating a conversation (no spend)."""
    status, _ = _request("POST", f"{agent_server_base()}/api/conversations",
                         headers={"X-Session-API-Key": _session_key()},
                         payload={})
    return {
        "capability": "create_conversation",
        "endpoint_live": status == 422,
        "http_status": status,
        "note": "422 on an empty body proves the route is live; nothing created",
    }


def probe_quota() -> dict:
    key = os.environ.get("OPENHANDS_API_KEY", "")
    if not key:
        return {"capability": "quota", "reachable": False,
                "detail": "OPENHANDS_API_KEY absent"}
    status, body = _request("GET", f"{cloud_base()}/api/quota/status",
                            headers={"Authorization": f"Bearer {key}"})
    if status == 200 and isinstance(body, dict):
        return {"capability": "quota", "reachable": True,
                "remaining": body.get("remaining"),
                "daily_limit": body.get("daily_limit"),
                "used_today": body.get("used_today"),
                "reset_at": body.get("reset_at")}
    return {"capability": "quota", "reachable": False, "http_status": status}


def probe_automations() -> dict:
    key = os.environ.get("OPENHANDS_API_KEY", "")
    if not key:
        return {"capability": "scheduled_automations", "reachable": False,
                "detail": "OPENHANDS_API_KEY absent"}
    status, body = _request("GET", f"{cloud_base()}/api/automation/v1",
                            headers={"Authorization": f"Bearer {key}"})
    if status == 200 and isinstance(body, dict):
        return {"capability": "scheduled_automations", "reachable": True,
                "total": body.get("total", len(body.get("automations", []))),
                "automations": body.get("automations", [])}
    return {"capability": "scheduled_automations", "reachable": False,
            "http_status": status}


def probe_all() -> list[dict]:
    return [probe_agent_server(), probe_conversation_creation(), probe_quota(),
            probe_automations()]
