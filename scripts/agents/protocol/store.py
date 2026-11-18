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

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

try:
    import msvcrt
except ImportError:  # POSIX
    msvcrt = None

DEFAULT_ROOT = pathlib.Path("bus")


class StoreError(RuntimeError):
    """Raised when a durable write cannot be confirmed."""


class CASConflict(RuntimeError):
    """Raised when a compare-and-set finds the stored value changed.

    This is the *lost-update* signal: the caller read version *V*, another
    writer committed first, so our conditional write did not apply. The caller
    re-reads and retries; nothing is silently overwritten.
    """


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

    def put_cas(self, key: str, value, expected) -> bool:
        """Write ``value`` only if the stored value equals ``expected``.

        Atomic within one host: an advisory file lock serialises concurrent
        conditional writers to the same key, and the actual file write stays
        atomic (temp file + rename). Two processes performing a read-modify-
        write on the same key therefore cannot lose an update — the second one
        sees the first one's committed value and is told the CAS failed.

        Returns ``True`` when written, ``False`` on a compare-and-set conflict.
        """
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_suffix(".lock")
        with lock_path.open("a+b") as lock:
            if fcntl is not None:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            elif msvcrt is not None:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                raise StoreError("file compare-and-set requires an OS file lock")
            try:
                current = self.get(key)
                if current != expected:
                    return False
                tmp = path.with_suffix(".tmp")
                tmp.write_text(
                    json.dumps(value, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
                tmp.replace(path)
                return True
            finally:
                if fcntl is not None:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                else:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)

    def durable(self) -> bool:
        """File storage is durable only on a host, not across a cloud pod."""
        return False


class KvStore:
    """The automation KV store. Durable across container destruction.

    The cloud KV routes ``/v1/kv/{key}`` on a single path segment: a key that
    contains ``/`` is answered with a routing 404, not a stored value. Internal
    keys keep ``/`` (``missions/<id>``) so the file store and the bus are
    unchanged; on the wire it is mapped to ``.``, which envelope and mission ids
    never contain.
    """

    backend = "kv"
    _SEP = "."

    def __init__(self, base: str, token: str, prefix: str = "tel99-bus") -> None:
        self.base = base.rstrip("/")
        self.token = token
        self.prefix = prefix

    def _wire(self, key: str) -> str:
        return f"{self.prefix}{self._SEP}{key}".replace("/", self._SEP)

    def _unwire(self, wire: str) -> str:
        rest = wire[len(self.prefix) + len(self._SEP):]
        return rest.replace(self._SEP, "/", 1)

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
        status, body = self._request("GET", f"{self.base}/v1/kv/{self._wire(key)}")
        if status == 200 and isinstance(body, dict):
            return body.get("value")
        return None

    def put(self, key: str, value) -> None:
        status, _ = self._request("PUT", f"{self.base}/v1/kv/{self._wire(key)}", value)
        if status not in (200, 201, 204):
            raise StoreError(f"KV write failed for {key!r}: HTTP {status}")

    def keys(self, prefix: str = "") -> list[str]:
        # The cloud KV ignores ``?prefix=``; filter on the client so the result
        # matches the file store's contract exactly.
        status, body = self._request("GET", f"{self.base}/v1/kv")
        if status != 200:
            return []
        if isinstance(body, dict):
            raw = body.get("keys", [])
        elif isinstance(body, list):
            raw = body
        else:
            raw = []
        head = f"{self.prefix}{self._SEP}"
        out = []
        for item in raw:
            key = item.get("key") if isinstance(item, dict) else item
            if isinstance(key, str) and key.startswith(head):
                internal = self._unwire(key)
                if internal.startswith(prefix):
                    out.append(internal)
        return sorted(out)

    def put_cas(self, key: str, value, expected) -> bool:
        """Conditional write using the KV record version (``if_version``).

        The cloud KV exposes the record version via ``?meta=true`` and accepts a
        conditional write with ``?if_version=<version>`` (HTTP 409 on mismatch),
        the same mechanism the cloud orchestrator's lock uses. We read the
        version, verify the current value still equals ``expected``, then write
        conditionally; a 409 means another writer won and the CAS is refused
        (no lost update). Returns ``True`` when written, ``False`` on conflict.

        A backend that does not expose a version cannot do an atomic CAS, so it
        raises :class:`StoreError` and the caller fails closed.
        """
        wire = self._wire(key)
        status, body = self._request("GET", f"{self.base}/v1/kv/{wire}?meta=true")
        if status == 404:
            current, version = None, None
        elif status == 200 and isinstance(body, dict) and "value" in body:
            current, version = body.get("value"), body.get("version")
            if version is None:
                raise StoreError(
                    f"KV backend exposes no record version for {key!r}: "
                    "cannot perform an atomic compare-and-set")
        else:
            raise StoreError(f"KV metadata read failed for {key!r}: HTTP {status}")

        if current != expected:
            return False

        condition = "nx=true" if version is None else f"if_version={version}"
        status, _ = self._request("PUT", f"{self.base}/v1/kv/{wire}?{condition}", value)
        if status in (200, 201, 204):
            return True
        if status == 409:
            return False
        raise StoreError(f"KV conditional write failed for {key!r}: HTTP {status}")

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
