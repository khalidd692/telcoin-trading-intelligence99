"""CAS lease coordination between Antigravity IDE, TEL99 CLI, and Codex CLI.

Prevents concurrent work on the same controller, mission, or (branch, path)
across IDE subagents, PowerShell/Python CLI supervisors, and Codex sessions.
Reuses ``FileStore`` CAS and ``exclusive()`` without building a second supervisor.
"""
from __future__ import annotations

import argparse
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

from scripts.agents.automation.local_codex import exclusive
from scripts.agents.protocol.store import CASConflict, FileStore

LEASES_KEY = "coordination/leases"
ACTOR_RE = re.compile(r"^(antigravity-ide|tel99-cli|codex-cli|subagent:[A-Za-z0-9_.-]{1,48})$")
RESOURCE_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,96}$")
MAX_TTL_SECONDS = 7200
DEFAULT_TTL_SECONDS = 1800


class LeaseConflict(RuntimeError):
    """Raised when another actor already holds an active lease on the target scope."""


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
    """Read-only inspection of active and expired leases without creating files."""
    ts = time.time() if now is None else float(now)
    cdir = _coord_dir(state_root)
    if not (cdir / "ledger").is_dir():
        return {
            "schema_version": 1,
            "active": [],
            "expired_count": 0,
            "actors_active": [],
            "locked_paths": [],
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
        "active": active,
        "expired_count": expired,
        "actors_active": actors,
        "locked_paths": locked_paths,
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
    with exclusive(cdir / "leases.lock"):
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
    with exclusive(cdir / "leases.lock"):
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
        return {"released": True, "lease_id": lease_id, "remaining": len(remaining)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("status", help="Inspect active coordination leases")
    st.add_argument("--state", type=Path, required=True)

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

    args = parser.parse_args(argv)
    try:
        if args.cmd == "status":
            print(json.dumps(active_leases(args.state), indent=2, ensure_ascii=False))
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
        res = release_lease(args.state, args.lease_id, actor=args.actor)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, LeaseConflict, CASConflict) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
