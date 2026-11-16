#!/usr/bin/env python3
"""Storage backends for the TEL99 agent bus.

The bus must survive the destruction of a cloud container. Locally it writes
files; in OpenHands Cloud it must write to the automation **KV store**, which is
the only durable store already available to a plugin-script run (see the
OpenHands automation contract: local files are lost when a run ends on a cloud
pod, the KV store is not).

Two backends implement the same tiny interface:

  * :class:`FileStore` — ``<root>/<kind>/<name>.json``; used locally and by tests.
  * :class:`KvStore` — ``<base>/v1/kv/<key>``; used when the automation run
    injects ``AUTOMATION_KV_TOKEN`` / ``AUTOMATION_API_URL``.

:func:`default_store` picks the KV store when it is available and falls back to
files otherwise, so the same code runs in both places. Neither backend ever
raises on a missing key: a missing key is ``None``, which is how the bus tells
"never seen" from "seen and empty".
"""

from __future__ import annotations

import json
import os
import pathlib
import urllib.error
import urllib.request

DEFAULT_ROOT = pathlib.Path("bus")


class StoreError(RuntimeError):
    """Raised when a durable write cannot be confirmed."""


class FileStore:
    """A directory-backed store. Keys are ``<kind>/<name>`` (no extension)."""

    backend = "file"

    def __init__(self, root: str | pathlib.Path) -> None:
        self.root = pathlib.Path(root)

    def _path(self, key: str) -> pathlib.Path:
        return self.root / f"{key}.json"

    def get(self, key: str):
        path = self._path(key)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def put(self, key: str, value) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        tmp.replace(path)

    def keys(self, prefix: str = "") -> list[str]:
        base = self.root / prefix if prefix else self.root
        if not base.is_dir():
            return []
        out = []
        for path in sorted(base.rglob("*.json")):
            out.append(str(path.relative_to(self.root)).removesuffix(".json"))
        return out

    def durable(self) -> bool:
        """File storage is durable only on a host, not across a cloud pod."""
        return False


class KvStore:
    """The automation KV store. Durable across container destruction."""

    backend = "kv"

    def __init__(self, base: str, token: str, prefix: str = "tel99-bus") -> None:
        self.base = base.rstrip("/")
        self.token = token
        self.prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}"

    def _request(self, method: str, url: str, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode()
                return resp.status, (json.loads(body) if body else None)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode(errors="ignore")

    def get(self, key: str):
        status, body = self._request("GET", f"{self.base}/v1/kv/{self._key(key)}")
        if status == 200 and isinstance(body, dict):
            return body.get("value")
        return None

    def put(self, key: str, value) -> None:
        status, _ = self._request("PUT", f"{self.base}/v1/kv/{self._key(key)}", value)
        if status not in (200, 201, 204):
            raise StoreError(f"KV write failed for {key!r}: HTTP {status}")

    def keys(self, prefix: str = "") -> list[str]:
        status, body = self._request(
            "GET", f"{self.base}/v1/kv?prefix={self._key(prefix)}"
        )
        if status != 200:
            return []
        if isinstance(body, dict):
            raw = body.get("keys", [])
        elif isinstance(body, list):
            raw = body
        else:
            raw = []
        out = []
        for item in raw:
            key = item.get("key") if isinstance(item, dict) else item
            if isinstance(key, str) and key.startswith(f"{self.prefix}/"):
                out.append(key[len(self.prefix) + 1:])
        return sorted(out)

    def durable(self) -> bool:
        return True


def kv_env() -> tuple[str, str]:
    """Return ``(base, token)`` for the KV store, or ``("", "")``."""
    base = os.environ.get("AUTOMATION_API_URL", "").rstrip("/")
    token = os.environ.get("AUTOMATION_KV_TOKEN", "")
    return base, token


def default_store(root: str | pathlib.Path | None = None):
    """KV store when the run provides one, else the local file store."""
    base, token = kv_env()
    if base and token:
        return KvStore(base, token)
    return FileStore(root or DEFAULT_ROOT)


def store_report(store) -> dict:
    return {
        "backend": store.backend,
        "durable_across_container": store.durable(),
        "root": str(getattr(store, "root", "")) or getattr(store, "base", ""),
    }
