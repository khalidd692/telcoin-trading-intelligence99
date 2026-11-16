#!/usr/bin/env python3
"""Verify the real automation KV store end to end (operator tool).

The cloud-autonomy plugin only runs for real when the automation injects a
durable KV store (``AUTOMATION_API_URL`` + ``AUTOMATION_KV_TOKEN``). Before
trusting it, this script proves the five properties the orchestrator and the bus
depend on, against the *actual* store — never against a mock:

  1. atomic compare-and-set   (``GET ?meta=true``, ``PUT ?nx=true``,
     ``PUT ?if_version=<n>``, ``409`` on a lost race);
  2. single-mission lock      (a second owner cannot take a held lock);
  3. deduplication            (a finished mission is not reprocessed);
  4. resume                   (an interrupted mission is re-queued intact);
  5. persistence              (the record survives a new client/connection).

Usage:

    # Against the automation's real KV (values come from the run environment):
    AUTOMATION_API_URL=... AUTOMATION_KV_TOKEN=... \
        python3 scripts/agents/automation/verify_kv.py

    # Local self-check: start a throwaway in-process KV server implementing the
    # documented contract, then run the same five checks against it.
    python3 scripts/agents/automation/verify_kv.py --local

Exit code 0 means every check passed. Any failure is printed and exits 2. The
script never writes outside the KV namespace it is given and never touches the
repository, a branch, or a conversation.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import policy  # noqa: E402

# ``orchestrator`` reads AUTOMATION_API_URL / AUTOMATION_KV_TOKEN at import time
# (module-level constants), so it must be imported *after* the environment is in
# place. It is therefore loaded lazily inside ``main``.
orch = None

try:
    from automation import bus_bridge  # noqa: E402
    from protocol.bus import Bus  # noqa: E402
    from protocol.store import KvStore  # noqa: E402
except Exception:  # noqa: BLE001
    bus_bridge = None
    Bus = None
    KvStore = None


class LocalKvServer:
    """A throwaway KV server implementing the documented contract.

    Used only with ``--local`` to self-check the harness itself. The production
    path points at the automation's real KV instead.
    """

    def __init__(self) -> None:
        self.store: dict[str, tuple] = {}
        self.lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def _send(self, code, obj=None):
                body = json.dumps(obj or {}).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                u = urlparse(self.path)
                key = u.path.rsplit("/", 1)[-1]
                q = parse_qs(u.query)
                with outer.lock:
                    if key not in outer.store:
                        return self._send(404, {"detail": "not found"})
                    value, version = outer.store[key]
                    if q.get("meta") == ["true"]:
                        return self._send(200, {"value": value, "version": version})
                    return self._send(200, {"value": value})

            def do_PUT(self):
                u = urlparse(self.path)
                key = u.path.rsplit("/", 1)[-1]
                q = parse_qs(u.query)
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length).decode()
                value = json.loads(raw) if raw else None
                with outer.lock:
                    if q.get("nx") == ["true"]:
                        if key in outer.store:
                            return self._send(409, {"detail": "exists"})
                        outer.store[key] = (value, 1)
                        return self._send(201, {"version": 1})
                    if "if_version" in q:
                        want = int(q["if_version"][0])
                        if key not in outer.store or outer.store[key][1] != want:
                            return self._send(409, {"detail": "version mismatch"})
                        outer.store[key] = (value, want + 1)
                        return self._send(200, {"version": want + 1})
                    current = outer.store.get(key, (None, 0))[1]
                    outer.store[key] = (value, current + 1)
                    return self._send(200, {"version": current + 1})

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        self.server.shutdown()


def _check(results: list, name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def verify_lock(results: list) -> None:
    """CAS + single-mission lock, exercised on the real store."""
    owner = f"verify-{int(time.time())}"
    acquired, detail = orch.acquire_lock(owner, ttl_seconds=300)
    _check(results, "lock acquire (nx / CAS)", acquired, detail)
    if acquired:
        probe = orch.kv_meta_probe(orch._LOCK_KEY)
        _check(results, "kv_meta_probe supported on a live key",
               bool(probe.get("supported")) and bool(probe.get("has_version")),
               json.dumps(probe))
        second, detail2 = orch.acquire_lock(owner + "-b", ttl_seconds=300)
        _check(results, "second owner is refused", not second, detail2)
        value, version = orch.kv_get_meta(orch._LOCK_KEY)
        _check(results, "record exposes a version",
               isinstance(value, dict) and version is not None,
               f"owner={value.get('owner') if isinstance(value, dict) else None} "
               f"version={version}")
        orch.release_lock(owner)
        third, detail3 = orch.acquire_lock(owner + "-c", ttl_seconds=300)
        _check(results, "re-acquire after release", third, detail3)
        if third:
            orch.release_lock(owner + "-c")


def verify_dedup_and_resume(results: list) -> None:
    """Deduplication and resume on the real KV-backed bus."""
    if Bus is None or bus_bridge is None or KvStore is None:
        _check(results, "bus available", False, "protocol package not importable")
        return
    base, token = os.environ.get("AUTOMATION_API_URL", ""), os.environ.get("AUTOMATION_KV_TOKEN", "")
    store = KvStore(base, token, prefix=f"tel99-verify-{int(time.time())}")
    bus = Bus(root=HERE / ".." / ".." / ".." / "bus", store=store)
    issue = {"number": 999999, "title": "verification mission", "body": "verify"}
    opened = bus_bridge.open_or_resume(
        bus, repository="khalidd692/telcoin-trading-intelligence99",
        issue=issue, work_branch="agent/mission-999999",
    )
    _check(results, "bus mission opens", opened["action"] == "opened", opened["action"])
    corr = opened["correlation_id"]

    # Resume: an interrupted (running) mission is re-queued, not lost.
    record = bus.load_mission(corr)
    record.state = "running"
    bus.save_mission(record)
    resumed = bus_bridge.open_or_resume(
        bus, repository="khalidd692/telcoin-trading-intelligence99",
        issue=issue, work_branch="agent/mission-999999",
    )
    _check(results, "interrupted mission resumes",
           resumed["action"] == "resumed", resumed["action"])

    # Dedup: a finished mission is recognised on a *fresh* bus object reading
    # the same store — proving persistence, not an in-memory shortcut.
    fresh = Bus(root=HERE / ".." / ".." / ".." / "bus", store=store)
    record = fresh.load_mission(corr)
    record.state = "done"
    fresh.save_mission(record)
    again = Bus(root=HERE / ".." / ".." / ".." / "bus", store=store)
    _check(results, "finished mission is not reprocessed",
           bus_bridge.is_already_finished(again, corr), corr)
    _check(results, "record persisted across clients",
           again.load_mission(corr) is not None, corr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the TEL99 automation KV store.")
    parser.add_argument("--local", action="store_true",
                        help="start a throwaway in-process KV server and check against it")
    args = parser.parse_args()

    server = None
    if args.local:
        server = LocalKvServer()
        os.environ["AUTOMATION_API_URL"] = server.url()
        os.environ["AUTOMATION_KV_TOKEN"] = "local-verify-token"
        print(f"local KV server on {server.url()}")

    base = os.environ.get("AUTOMATION_API_URL", "")
    token = os.environ.get("AUTOMATION_KV_TOKEN", "")
    if not (base and token):
        print("AUTOMATION_API_URL / AUTOMATION_KV_TOKEN are not set: "
              "run with --local, or provide the automation's real KV values.",
              file=sys.stderr)
        if server:
            server.stop()
        return 2

    global orch
    import orchestrator as orch  # noqa: PLC0415 - env must be set before import

    print(f"KV base: {base}")
    results: list = []
    try:
        _check(results, "kv_available", orch.kv_available(), str(orch.kv_available()))
        verify_lock(results)
        verify_dedup_and_resume(results)
    finally:
        if server:
            server.stop()

    failed = [name for name, ok, _ in results if not ok]
    print()
    if failed:
        print(f"RESULT: FAIL ({len(failed)} of {len(results)} checks failed): {failed}")
        return 2
    print(f"RESULT: PASS ({len(results)} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
