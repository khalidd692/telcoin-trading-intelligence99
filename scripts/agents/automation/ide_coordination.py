"""CAS lease and handoff coordination between Antigravity IDE, TEL99 CLI, SDK, and Codex CLI.

Prevents concurrent work on the same controller, mission, or (branch, path)
across IDE subagents, PowerShell/Python CLI supervisors, SDK adapters, and Codex
sessions. Reuses ``FileStore`` CAS and ``exclusive()`` without building a second
supervisor.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from scripts.agents.automation.local_codex import Blocked, exclusive
from scripts.agents.protocol.store import CASConflict, FileStore

SDK_INTERFACE_VERSION = "tel99-coordination-v1"
LEASES_KEY = "coordination/leases"
ACTIVITY_KEY = "coordination/activity"
MAX_ACTIVITY_EVENTS = 100
ACTOR_RE = re.compile(
    r"^(antigravity-ide|antigravity-sdk|tel99-cli|codex-cli|"
    r"subagent:[A-Za-z0-9_.-]{1,48}|engine:[a-z0-9_.-]{1,32})$"
)
RESOURCE_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,96}$")
MAX_TTL_SECONDS = 7200
DEFAULT_TTL_SECONDS = 1800

LOCAL_INFERENCE_RESOURCE = "inference:local-gpu-ram"
PRELOAD_MIN_FREE_MIB = 2200
RESIDENT_MIN_FREE_MIB = 950
DEFAULT_INFERENCE_TTL_SECONDS = 600
DEFAULT_INFERENCE_WAIT_SECONDS = 180.0
ENGINE_NAME_RE = re.compile(r"^[a-z0-9_.-]{1,32}$")


class LeaseConflict(RuntimeError):
    """Raised when another actor already holds an active lease on the target scope."""


class ResourceBusyError(LeaseConflict):
    """Raised when local RAM or cross-engine inference capacity is exhausted."""

    error_category = "ENVIRONMENT_ERROR"


@contextmanager
def _lease_transaction(coord_dir: Path):
    """Allow a concurrent transaction to finish before checking its lease."""
    deadline = time.monotonic() + 1.0
    with ExitStack() as stack:
        while True:
            try:
                stack.enter_context(exclusive(coord_dir / "leases.lock"))
            except Blocked as exc:
                if time.monotonic() >= deadline:
                    raise LeaseConflict("coordination ledger is busy") from exc
                time.sleep(0.02)
            else:
                break
        yield


def _utc_iso(ts: float | None = None) -> str:
    dt = datetime.fromtimestamp(time.time() if ts is None else ts, tz=timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_actor(actor: str) -> str:
    if not isinstance(actor, str) or not ACTOR_RE.fullmatch(actor.strip()):
        raise ValueError(f"unsupported coordination actor: {actor!r}")
    return actor.strip()


def _normalize_path(path: str) -> str:
    clean = str(path or "").strip().replace("\\", "/")
    while clean.startswith("./"):
        clean = clean[2:]
    return clean.strip("/")


def _normalize_paths(paths) -> list[str]:
    if not paths:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in paths:
        norm = _normalize_path(item)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return sorted(out)


def _coord_dir(state_root: Path | str) -> Path:
    return Path(state_root).resolve() / "coordination"


def _read_raw_leases(coord_dir: Path) -> tuple[list[dict], dict | None]:
    ledger_dir = coord_dir / "ledger"
    if not ledger_dir.is_dir():
        return [], None
    store = FileStore(ledger_dir)
    record = store.read(LEASES_KEY, default=None)
    if record is None:
        return [], None
    if not isinstance(record, dict) or not isinstance(record.get("leases"), list):
        raise ValueError("corrupt coordination leases record")
    return [row for row in record["leases"] if isinstance(row, dict)], record


def _append_activity_locked(coord_dir: Path, event: dict) -> None:
    """Append a bounded coordination event inside ``leases.lock``."""
    store = FileStore(coord_dir / "ledger")
    previous = store.read(ACTIVITY_KEY, default=None)
    events = []
    if isinstance(previous, dict) and isinstance(previous.get("events"), list):
        events = [row for row in previous["events"] if isinstance(row, dict)]
    next_events = [*events, event][-MAX_ACTIVITY_EVENTS:]
    store.put_cas(ACTIVITY_KEY, {"version": 1, "events": next_events}, previous)


def recent_activity(state_root: Path | str, *, limit: int = 25) -> list[dict]:
    """Read-only inspection of recent coordination/handoff events."""
    if limit <= 0:
        return []
    cdir = _coord_dir(state_root)
    ledger_dir = cdir / "ledger"
    if not ledger_dir.is_dir():
        return []
    record = FileStore(ledger_dir).read(ACTIVITY_KEY, default=None)
    if not isinstance(record, dict) or not isinstance(record.get("events"), list):
        return []
    rows = [row for row in record["events"] if isinstance(row, dict)]
    return rows[-limit:]


def _split_leases(leases: list[dict], now: float) -> tuple[list[dict], int]:
    active: list[dict] = []
    expired = 0
    for row in leases:
        exp = row.get("expires_at")
        if type(exp) in (int, float) and exp > now:
            active.append(row)
        else:
            expired += 1
    return active, expired


def _find_conflicts(
    active: list[dict],
    *,
    actor: str,
    resource_id: str,
    branch: str,
    paths: list[str],
) -> list[str]:
    conflicts: list[str] = []
    norm_branch = str(branch or "").strip()
    path_set = set(paths)
    for row in active:
        holder = row.get("actor")
        if holder == actor:
            continue
        if resource_id and row.get("resource_id") == resource_id:
            conflicts.append(
                f"resource {resource_id!r} held by {holder} (lease {row.get('lease_id')})"
            )
            continue
        holder_branch = str(row.get("branch") or "").strip()
        holder_paths = set(row.get("paths") or [])
        if path_set and holder_paths and (not norm_branch or not holder_branch or norm_branch == holder_branch):
            overlap = sorted(path_set & holder_paths)
            if overlap:
                conflicts.append(
                    f"path conflict on ({norm_branch or holder_branch or '*'}, {overlap[0]}) "
                    f"held by {holder} (lease {row.get('lease_id')})"
                )
    return conflicts


def active_leases(state_root: Path | str, *, now: float | None = None) -> dict:
    """Read-only inspection of active, expired leases and recent coordination events."""
    ts = time.time() if now is None else float(now)
    cdir = _coord_dir(state_root)
    if not (cdir / "ledger").is_dir():
        return {
            "schema_version": 1,
            "sdk_interface_version": SDK_INTERFACE_VERSION,
            "active": [],
            "expired_count": 0,
            "actors_active": [],
            "locked_paths": [],
            "recent_activity": [],
        }
    raw, _ = _read_raw_leases(cdir)
    active, expired = _split_leases(raw, ts)
    actors = sorted({str(r.get("actor")) for r in active if r.get("actor")})
    locked_paths = sorted({
        f"{r.get('branch') or '*'}:{p}"
        for r in active
        for p in (r.get("paths") or [])
    })
    return {
        "schema_version": 1,
        "sdk_interface_version": SDK_INTERFACE_VERSION,
        "active": active,
        "expired_count": expired,
        "actors_active": actors,
        "locked_paths": locked_paths,
        "recent_activity": recent_activity(state_root, limit=15),
    }


def check_conflicts(
    state_root: Path | str,
    *,
    actor: str,
    resource_id: str = "",
    branch: str = "",
    paths=(),
    now: float | None = None,
) -> list[str]:
    """Read-only check for lease conflicts against another active actor."""
    clean_actor = _validate_actor(actor)
    ts = time.time() if now is None else float(now)
    cdir = _coord_dir(state_root)
    if not (cdir / "ledger").is_dir():
        return []
    raw, _ = _read_raw_leases(cdir)
    active, _ = _split_leases(raw, ts)
    return _find_conflicts(
        active,
        actor=clean_actor,
        resource_id=str(resource_id or "").strip(),
        branch=str(branch or "").strip(),
        paths=_normalize_paths(paths),
    )


def acquire_lease(
    state_root: Path | str,
    *,
    actor: str,
    resource_id: str,
    branch: str = "",
    paths=(),
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    pid: int | None = None,
    note: str = "",
    now: float | None = None,
) -> dict:
    """Acquire an exclusive CAS coordination lease for an actor and scope."""
    clean_actor = _validate_actor(actor)
    clean_resource = str(resource_id or "").strip()
    if not RESOURCE_RE.fullmatch(clean_resource):
        raise ValueError(f"invalid resource_id: {resource_id!r}")
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= MAX_TTL_SECONDS:
        raise ValueError(f"ttl_seconds must be within 1..{MAX_TTL_SECONDS}")
    norm_branch = str(branch or "").strip()
    norm_paths = _normalize_paths(paths)
    ts = time.time() if now is None else float(now)

    cdir = _coord_dir(state_root)
    cdir.mkdir(parents=True, exist_ok=True)
    with _lease_transaction(cdir):
        raw, previous = _read_raw_leases(cdir)
        active, _ = _split_leases(raw, ts)
        conflicts = _find_conflicts(
            active,
            actor=clean_actor,
            resource_id=clean_resource,
            branch=norm_branch,
            paths=norm_paths,
        )
        if conflicts:
            _append_activity_locked(cdir, {
                "at": _utc_iso(ts),
                "kind": "lease_conflict",
                "actor": clean_actor,
                "resource_id": clean_resource,
                "detail": "; ".join(conflicts)[:240],
            })
            raise LeaseConflict("; ".join(conflicts))

        remaining = [
            row for row in active
            if not (row.get("actor") == clean_actor and row.get("resource_id") == clean_resource)
        ]
        lease = {
            "lease_id": f"lease-{uuid4().hex[:12]}",
            "actor": clean_actor,
            "resource_id": clean_resource,
            "branch": norm_branch,
            "paths": norm_paths,
            "pid": os.getpid() if pid is None else int(pid),
            "acquired_at": ts,
            "expires_at": ts + ttl_seconds,
            "note": str(note or "")[:200],
        }
        next_record = {"version": 1, "leases": [*remaining, lease]}
        store = FileStore(cdir / "ledger")
        if not store.put_cas(LEASES_KEY, next_record, previous):
            raise CASConflict("coordination lease CAS conflict")
        _append_activity_locked(cdir, {
            "at": _utc_iso(ts),
            "kind": "lease_acquired",
            "actor": clean_actor,
            "resource_id": clean_resource,
            "lease_id": lease["lease_id"],
            "paths": norm_paths,
        })
        return lease


def release_lease(
    state_root: Path | str,
    lease_id: str,
    *,
    actor: str,
    force_expired: bool = False,
    now: float | None = None,
) -> dict:
    """Release an existing lease owned by ``actor`` (or purge if expired)."""
    clean_actor = _validate_actor(actor)
    ts = time.time() if now is None else float(now)
    cdir = _coord_dir(state_root)
    if not (cdir / "ledger").is_dir():
        return {"released": False, "reason": "no coordination ledger"}

    cdir.mkdir(parents=True, exist_ok=True)
    with _lease_transaction(cdir):
        raw, previous = _read_raw_leases(cdir)
        active, expired_before = _split_leases(raw, ts)
        target = next((row for row in active if row.get("lease_id") == lease_id), None)
        if target is None:
            if previous is not None and len(active) != len(raw):
                FileStore(cdir / "ledger").put_cas(
                    LEASES_KEY, {"version": 1, "leases": active}, previous,
                )
            return {
                "released": False,
                "reason": "lease not found or already expired",
                "expired_purged": expired_before,
            }
        if target.get("actor") != clean_actor and not force_expired:
            raise LeaseConflict(
                f"lease {lease_id} belongs to {target.get('actor')}, not {clean_actor}"
            )
        remaining = [row for row in active if row.get("lease_id") != lease_id]
        store = FileStore(cdir / "ledger")
        if not store.put_cas(LEASES_KEY, {"version": 1, "leases": remaining}, previous):
            raise CASConflict("coordination release CAS conflict")
        _append_activity_locked(cdir, {
            "at": _utc_iso(ts),
            "kind": "lease_released",
            "actor": clean_actor,
            "resource_id": target.get("resource_id", ""),
            "lease_id": lease_id,
        })
        return {"released": True, "lease_id": lease_id, "remaining": len(remaining)}


def record_handoff(
    state_root: Path | str,
    *,
    from_actor: str,
    to_actor: str,
    resource_id: str,
    summary: str,
    evidence_ref: str = "",
    branch: str = "",
    now: float | None = None,
) -> dict:
    """Record a durable CAS handoff event between two cooperating actors."""
    src = _validate_actor(from_actor)
    dst = _validate_actor(to_actor)
    clean_res = str(resource_id or "").strip()
    if not RESOURCE_RE.fullmatch(clean_res):
        raise ValueError(f"invalid resource_id: {resource_id!r}")
    clean_summary = str(summary or "").strip()
    if not clean_summary:
        raise ValueError("handoff summary is required")
    ts = time.time() if now is None else float(now)
    event = {
        "at": _utc_iso(ts),
        "kind": "handoff",
        "handoff_id": f"handoff-{uuid4().hex[:12]}",
        "from_actor": src,
        "to_actor": dst,
        "resource_id": clean_res,
        "branch": str(branch or "").strip(),
        "evidence_ref": str(evidence_ref or "")[:160],
        "summary": clean_summary[:240],
        "sdk_interface_version": SDK_INTERFACE_VERSION,
    }
    cdir = _coord_dir(state_root)
    cdir.mkdir(parents=True, exist_ok=True)
    with _lease_transaction(cdir):
        _append_activity_locked(cdir, event)
    return event


def default_coordination_state_root() -> Path:
    """Resolve the single shared TEL99 coordination state root without creating a second ledger."""
    env_dir = os.environ.get("TEL99_COORDINATION_STATE", "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    cfg_path = HERE / "tel99-config.json"
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            raw = str(cfg.get("state_dir") or "").strip()
            if raw:
                if raw.startswith(("~/", "~\\")):
                    return (Path.home() / raw[2:]).resolve()
                return Path(raw).expanduser().resolve()
        except (OSError, ValueError):
            pass
    return (Path.home() / "Desktop" / "TEL99_ANTIGRAVITY_AUTOFEED_20261124_STATE").resolve()


def is_pid_alive(pid: int | None) -> bool:
    """Return True if a local OS process with `pid` is currently running."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        import ctypes

        process_query_limited = 0x1000
        still_active = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(process_query_limited, False, pid)
        if not handle:
            # Error 5 (ACCESS_DENIED) means process exists but is elevated.
            return ctypes.get_last_error() == 5 or kernel32.GetLastError() == 5
        try:
            code = ctypes.c_ulong(0)
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == still_active)
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def reclaim_orphan_leases(
    state_root: Path | str | None = None,
    *,
    resource_id: str | None = LOCAL_INFERENCE_RESOURCE,
    now: float | None = None,
) -> list[dict]:
    """Reclaim active CAS leases whose owning PID is confirmed dead (crash recovery)."""
    root = default_coordination_state_root() if state_root is None else Path(state_root).resolve()
    cdir = _coord_dir(root)
    if not (cdir / "ledger").is_dir():
        return []
    ts = time.time() if now is None else float(now)
    reclaimed: list[dict] = []
    with _lease_transaction(cdir):
        raw, previous = _read_raw_leases(cdir)
        active, _ = _split_leases(raw, ts)
        kept: list[dict] = []
        for row in active:
            same_res = resource_id is None or row.get("resource_id") == resource_id
            pid = row.get("pid")
            if same_res and isinstance(pid, int) and pid > 0 and not is_pid_alive(pid):
                reclaimed.append(row)
            else:
                kept.append(row)
        if reclaimed or len(kept) != len(raw):
            store = FileStore(cdir / "ledger")
            if not store.put_cas(LEASES_KEY, {"version": 1, "leases": kept}, previous):
                raise CASConflict("orphan lease reclaim CAS conflict")
            for row in reclaimed:
                _append_activity_locked(cdir, {
                    "at": _utc_iso(ts),
                    "kind": "orphan_lease_reclaimed",
                    "actor": str(row.get("actor") or ""),
                    "resource_id": str(row.get("resource_id") or ""),
                    "lease_id": str(row.get("lease_id") or ""),
                    "dead_pid": row.get("pid"),
                })
    return reclaimed


def _loopback_http_json(port: int, path: str, *, method: str = "GET", payload: dict | None = None, timeout: float = 2.0) -> dict | list | None:
    from http.client import HTTPConnection, HTTPException

    conn = HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read(65_536)
        if resp.status != 200:
            return None
        return json.loads(raw.decode("utf-8", errors="replace")) if raw else {}
    except (OSError, HTTPException, ValueError):
        return None
    finally:
        conn.close()


def _find_listening_llama_pid(llama_port: int = 8080) -> int | None:
    """Locate the PID of a local llama-server listening on `llama_port` without killing anything."""
    import subprocess

    if sys.platform != "win32":
        return None
    try:
        ns = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5, check=False,
        )
        candidate_pids: set[int] = set()
        needle = f"127.0.0.1:{llama_port}"
        for line in (ns.stdout or "").splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1].endswith(f":{llama_port}") and parts[3].upper() in ("LISTENING", "LISTEN", "ECOUTE", "\ufffdCOUTE"):
                if needle in parts[1] or parts[1].startswith("0.0.0.0:"):
                    try:
                        candidate_pids.add(int(parts[4]))
                    except ValueError:
                        pass
        for pid in sorted(candidate_pids):
            tl = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5, check=False,
            )
            if "llama-server" in (tl.stdout or "").lower():
                return pid
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def probe_local_engines(
    *,
    state_root: Path | str | None = None,
    ollama_port: int = 11434,
    llama_port: int = 8080,
) -> dict:
    """Read-only inspection of all local inference engines (Ollama, llama-server), RAM, and CAS lease."""
    from scripts.agents.automation import local_model_routing

    root = default_coordination_state_root() if state_root is None else Path(state_root).resolve()
    avail_mib = local_model_routing.available_memory_mib()

    ollama_ps = _loopback_http_json(ollama_port, "/api/ps", timeout=1.5)
    ollama_loaded: list[str] = []
    ollama_size_mib = 0.0
    if isinstance(ollama_ps, dict) and isinstance(ollama_ps.get("models"), list):
        for row in ollama_ps["models"]:
            if isinstance(row, dict) and isinstance(row.get("name"), str):
                ollama_loaded.append(row["name"])
                sz = row.get("size")
                if isinstance(sz, (int, float)) and sz > 0:
                    ollama_size_mib += float(sz) / (1024 * 1024)

    llama_health = _loopback_http_json(llama_port, "/health", timeout=1.5)
    llama_alive = isinstance(llama_health, dict) and llama_health.get("status") == "ok"
    llama_processing = False
    llama_busy_slots = 0
    if llama_alive:
        slots = _loopback_http_json(llama_port, "/slots", timeout=1.5)
        slot_list = slots if isinstance(slots, list) else (slots.get("value") if isinstance(slots, dict) else [])
        if isinstance(slot_list, list):
            for s in slot_list:
                if isinstance(s, dict) and s.get("is_processing"):
                    llama_processing = True
                    llama_busy_slots += 1

    leases_info = active_leases(root)
    inf_leases = [r for r in leases_info["active"] if r.get("resource_id") == LOCAL_INFERENCE_RESOURCE]
    return {
        "schema_version": 1,
        "state_root": str(root),
        "available_memory_mib": avail_mib,
        "preload_min_free_mib": PRELOAD_MIN_FREE_MIB,
        "resident_min_free_mib": RESIDENT_MIN_FREE_MIB,
        "ollama": {
            "port": ollama_port,
            "reachable": ollama_ps is not None,
            "loaded_models": ollama_loaded,
            "resident_size_mib": round(ollama_size_mib, 1),
        },
        "llama_server": {
            "port": llama_port,
            "alive": llama_alive,
            "processing": llama_processing,
            "busy_slots": llama_busy_slots,
            "pid": _find_listening_llama_pid(llama_port) if llama_alive else None,
        },
        "active_inference_lease": inf_leases[0] if inf_leases else None,
        "active_inference_leases_count": len(inf_leases),
    }


def unload_ollama_models(
    models: list[str] | tuple[str, ...] | None = None,
    *,
    ollama_port: int = 11434,
    timeout: float = 8.0,
) -> list[str]:
    """Safely unload resident Ollama models via keep_alive=0 to reclaim host RAM."""
    if models is None:
        ps = _loopback_http_json(ollama_port, "/api/ps", timeout=1.5)
        models = [
            row["name"]
            for row in ((ps or {}).get("models") or [])
            if isinstance(row, dict) and isinstance(row.get("name"), str)
        ]
    unloaded: list[str] = []
    for name in list(models):
        res = _loopback_http_json(
            ollama_port,
            "/api/generate",
            method="POST",
            payload={"model": name, "prompt": "", "keep_alive": 0, "stream": False},
            timeout=timeout,
        )
        if res is not None:
            unloaded.append(name)
    if unloaded:
        time.sleep(0.6)
    return unloaded


def stop_idle_llama_server(
    *,
    state_root: Path | str | None = None,
    llama_port: int = 8080,
) -> dict:
    """Safely stop an idle llama-server process ONLY when no slot is busy and no CAS lease is held."""
    import subprocess

    root = default_coordination_state_root() if state_root is None else Path(state_root).resolve()
    status = probe_local_engines(state_root=root, llama_port=llama_port)
    lease = status.get("active_inference_lease")
    if lease and str(lease.get("actor") or "") in ("engine:llama-server", "engine:llama-cpp"):
        return {"stopped": False, "reason": "active CAS lease held by llama-server"}
    ls = status["llama_server"]
    if not ls["alive"]:
        return {"stopped": False, "reason": "llama-server not running"}
    if ls["processing"]:
        return {"stopped": False, "reason": "llama-server has active processing slots"}
    pid = ls.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return {"stopped": False, "reason": "unable to confirm exact llama-server PID"}
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=8, check=False)
    else:
        import signal

        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    time.sleep(1.0)
    return {"stopped": True, "pid": pid, "port": llama_port}


def _owner_priority_path(state_root: Path | str | None = None) -> Path:
    root = default_coordination_state_root() if state_root is None else Path(state_root).resolve()
    return _coord_dir(root) / "owner_interactive_priority.json"


def set_owner_interactive_priority(
    state_root: Path | str | None = None,
    *,
    job_id: str,
    ttl_seconds: int = 180,
) -> Path:
    """Signal background campaigns to yield politely between tasks for an interactive owner chat."""
    path = _owner_priority_path(state_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    payload = {
        "job_id": str(job_id),
        "pid": os.getpid(),
        "set_at": now,
        "expires_at": now + max(15, min(300, int(ttl_seconds))),
    }
    tmp = path.parent / f"{path.name}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def clear_owner_interactive_priority(
    state_root: Path | str | None = None,
    *,
    job_id: str | None = None,
) -> None:
    """Clear the owner interactive priority signal if owned by this job (or unconditionally if job_id=None)."""
    path = _owner_priority_path(state_root)
    if not path.is_file():
        return
    if job_id is not None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("job_id") not in (None, str(job_id)):
                return
        except (OSError, ValueError):
            pass
    path.unlink(missing_ok=True)


def owner_interactive_priority_active(
    state_root: Path | str | None = None,
    *,
    now: float | None = None,
) -> dict | None:
    """Return active non-expired owner interactive priority metadata, or None."""
    path = _owner_priority_path(state_root)
    if not path.is_file():
        return None
    ts = time.time() if now is None else float(now)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        exp = float(data.get("expires_at") or 0.0)
        if exp <= ts:
            path.unlink(missing_ok=True)
            return None
        return data
    except (OSError, ValueError, TypeError):
        return None


@contextmanager
def local_inference_lease(
    engine: str,
    *,
    state_root: Path | str | None = None,
    model: str = "",
    required_free_mib: int | None = None,
    wait_timeout: float = DEFAULT_INFERENCE_WAIT_SECONDS,
    ttl_seconds: int = DEFAULT_INFERENCE_TTL_SECONDS,
    poll_interval: float = 0.5,
    auto_reclaim_idle: bool = True,
    probe_engines: bool = True,
    ollama_port: int = 11434,
    llama_port: int = 8080,
    priority: str = "background",
):
    """Host-wide exclusive CAS mutex for ALL local inference engines (concurrency = 1).

    Reuses `acquire_lease`/`release_lease` on `LOCAL_INFERENCE_RESOURCE`:
    - Blocks Ollama when llama-server holds the lease, and blocks llama-server when Ollama holds it.
    - Respects interactive owner chat priority (`priority="owner"`) so background campaigns yield cleanly between tasks.
    - Reclaims confirmed dead-PID orphan leases automatically.
    - Distinguishes pre-load RAM headroom vs already-resident model RAM headroom.
    - Safely frees idle competing engines when switching between Ollama and llama-server.
    """
    clean_engine = str(engine or "").strip().lower()
    if not ENGINE_NAME_RE.fullmatch(clean_engine):
        raise ValueError(f"invalid local inference engine name: {engine!r}")
    actor = f"engine:{clean_engine}"
    root = default_coordination_state_root() if state_root is None else Path(state_root).resolve()
    deadline = time.monotonic() + max(0.0, float(wait_timeout))
    yield_deadline = time.monotonic() + 90.0
    lease: dict | None = None

    while True:
        if priority != "owner" and time.monotonic() < yield_deadline:
            pri = owner_interactive_priority_active(root)
            if pri is not None and int(pri.get("pid") or -1) != os.getpid():
                if time.monotonic() < deadline:
                    time.sleep(min(1.5, max(0.1, deadline - time.monotonic())))
                    continue
        reclaim_orphan_leases(root, resource_id=LOCAL_INFERENCE_RESOURCE)
        try:
            lease = acquire_lease(
                root,
                actor=actor,
                resource_id=LOCAL_INFERENCE_RESOURCE,
                ttl_seconds=ttl_seconds,
                note=f"{clean_engine}:{model}"[:180],
            )
            break
        except LeaseConflict as exc:
            if time.monotonic() >= deadline:
                raise ResourceBusyError(
                    f"local inference lease busy for {actor} after {wait_timeout:.1f}s: {exc}"
                ) from exc
            time.sleep(min(poll_interval, max(0.05, deadline - time.monotonic())))

    try:
        model_is_resident = False
        avail_mib: int | None = None
        threshold_mib = int(required_free_mib) if required_free_mib is not None else PRELOAD_MIN_FREE_MIB
        reclaimed_actions: list[str] = []

        if probe_engines:
            snap = probe_local_engines(state_root=root, ollama_port=ollama_port, llama_port=llama_port)
            avail_mib = snap.get("available_memory_mib")
            ollama_loaded = list((snap.get("ollama") or {}).get("loaded_models") or [])
            llama_info = snap.get("llama_server") or {}

            if clean_engine in ("ollama", "antigravity-sdk"):
                model_is_resident = bool(model and model in ollama_loaded)
                # Wait cleanly if an external llama-server is actively processing (never kill an active run!)
                while llama_info.get("alive") and llama_info.get("processing"):
                    if time.monotonic() >= deadline:
                        raise ResourceBusyError("llama-server is actively processing on port 8080")
                    time.sleep(min(max(poll_interval, 2.0), max(0.1, deadline - time.monotonic())))
                    snap = probe_local_engines(state_root=root, ollama_port=ollama_port, llama_port=llama_port)
                    avail_mib = snap.get("available_memory_mib")
                    llama_info = snap.get("llama_server") or {}
                if llama_info.get("alive") and not llama_info.get("processing") and auto_reclaim_idle:
                    stopped = stop_idle_llama_server(state_root=root, llama_port=llama_port)
                    if stopped.get("stopped"):
                        reclaimed_actions.append(f"stopped_idle_llama_server:pid={stopped.get('pid')}")
                        snap = probe_local_engines(state_root=root, ollama_port=ollama_port, llama_port=llama_port)
                        avail_mib = snap.get("available_memory_mib")
                # Unload OTHER resident Ollama models if RAM is tight before loading target model.
                other_models = [m for m in ollama_loaded if m != model]
                if other_models and auto_reclaim_idle and (avail_mib is None or avail_mib < PRELOAD_MIN_FREE_MIB):
                    unloaded = unload_ollama_models(other_models, ollama_port=ollama_port)
                    if unloaded:
                        reclaimed_actions.append(f"unloaded_ollama:{','.join(unloaded)}")
                        snap = probe_local_engines(state_root=root, ollama_port=ollama_port, llama_port=llama_port)
                        avail_mib = snap.get("available_memory_mib")
            elif clean_engine in ("llama-server", "llama-cpp"):
                model_is_resident = bool(llama_info.get("alive"))
                if ollama_loaded and auto_reclaim_idle:
                    unloaded = unload_ollama_models(ollama_loaded, ollama_port=ollama_port)
                    if unloaded:
                        reclaimed_actions.append(f"unloaded_ollama:{','.join(unloaded)}")
                        snap = probe_local_engines(state_root=root, ollama_port=ollama_port, llama_port=llama_port)
                        avail_mib = snap.get("available_memory_mib")

            if required_free_mib is None:
                threshold_mib = RESIDENT_MIN_FREE_MIB if model_is_resident else PRELOAD_MIN_FREE_MIB

            while avail_mib is not None and avail_mib < threshold_mib:
                if time.monotonic() >= deadline:
                    raise ResourceBusyError(
                        f"insufficient free RAM for {actor} ({model or 'local'}): "
                        f"{avail_mib} MiB < {threshold_mib} MiB "
                        f"({'resident' if model_is_resident else 'pre-load'} threshold)"
                    )
                time.sleep(min(max(poll_interval, 1.0), max(0.1, deadline - time.monotonic())))
                snap = probe_local_engines(state_root=root, ollama_port=ollama_port, llama_port=llama_port)
                avail_mib = snap.get("available_memory_mib")

        yield {
            "lease": lease,
            "engine": clean_engine,
            "actor": actor,
            "model": model,
            "model_is_resident": model_is_resident,
            "available_memory_mib": avail_mib,
            "ram_threshold_mib": threshold_mib,
            "reclaimed_actions": reclaimed_actions,
        }
    finally:
        if lease is not None:
            try:
                release_lease(root, lease["lease_id"], actor=actor)
            except (LeaseConflict, CASConflict, OSError, ValueError):
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("status", help="Inspect active coordination leases")
    st.add_argument("--state", type=Path, required=True)

    eng = sub.add_parser("engines", help="Inspect local inference engines, RAM, and active inference lease")
    eng.add_argument("--state", type=Path, default=None)

    rec = sub.add_parser("reclaim-orphans", help="Reclaim confirmed dead-PID orphan leases")
    rec.add_argument("--state", type=Path, default=None)

    act = sub.add_parser("activity", help="Inspect recent coordination and handoff events")
    act.add_argument("--state", type=Path, required=True)
    act.add_argument("--limit", type=int, default=25)

    acq = sub.add_parser("acquire", help="Acquire a CAS coordination lease")
    acq.add_argument("--state", type=Path, required=True)
    acq.add_argument("--actor", required=True)
    acq.add_argument("--resource", required=True)
    acq.add_argument("--branch", default="")
    acq.add_argument("--path", action="append", default=[])
    acq.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS)
    acq.add_argument("--note", default="")

    rel = sub.add_parser("release", help="Release a CAS coordination lease")
    rel.add_argument("--state", type=Path, required=True)
    rel.add_argument("--actor", required=True)
    rel.add_argument("--lease-id", required=True)

    ho = sub.add_parser("handoff", help="Record an inter-actor handoff event")
    ho.add_argument("--state", type=Path, required=True)
    ho.add_argument("--from-actor", required=True)
    ho.add_argument("--to-actor", required=True)
    ho.add_argument("--resource", required=True)
    ho.add_argument("--summary", required=True)
    ho.add_argument("--evidence-ref", default="")
    ho.add_argument("--branch", default="")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "status":
            print(json.dumps(active_leases(args.state), indent=2, ensure_ascii=False))
            return 0
        if args.cmd == "engines":
            print(json.dumps(probe_local_engines(state_root=args.state), indent=2, ensure_ascii=False))
            return 0
        if args.cmd == "reclaim-orphans":
            reclaimed = reclaim_orphan_leases(args.state, resource_id=None)
            print(json.dumps({"reclaimed": reclaimed, "count": len(reclaimed)}, indent=2, ensure_ascii=False))
            return 0
        if args.cmd == "activity":
            print(json.dumps({"events": recent_activity(args.state, limit=args.limit)}, indent=2, ensure_ascii=False))
            return 0
        if args.cmd == "acquire":
            lease = acquire_lease(
                args.state,
                actor=args.actor,
                resource_id=args.resource,
                branch=args.branch,
                paths=args.path,
                ttl_seconds=args.ttl,
                note=args.note,
            )
            print(json.dumps(lease, indent=2, ensure_ascii=False))
            return 0
        if args.cmd == "handoff":
            ev = record_handoff(
                args.state,
                from_actor=args.from_actor,
                to_actor=args.to_actor,
                resource_id=args.resource,
                summary=args.summary,
                evidence_ref=args.evidence_ref,
                branch=args.branch,
            )
            print(json.dumps(ev, indent=2, ensure_ascii=False))
            return 0
        res = release_lease(args.state, args.lease_id, actor=args.actor)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, LeaseConflict, CASConflict) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
