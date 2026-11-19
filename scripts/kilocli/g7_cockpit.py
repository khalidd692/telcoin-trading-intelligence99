#!/usr/bin/env python3
"""Kilo G7 Cockpit — état de connexion, commandes STATUS/STOP, documentation Windows.

Fournit :
  * un registre d'état des sessions workers (CONNECTED/IDLE/BUSY/BLOCKED)
  * une commande STATUS pour interroger l'état
  * une commande STOP pour demander l'arrêt gracieux d'un worker
  * une documentation d'utilisation sous Windows
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]  # scripts/kilocli -> scripts -> root
COCKPIT_DIR = ROOT / ".kilo" / "cockpit"

CONNECTED = "CONNECTED"
IDLE = "IDLE"
BUSY = "BUSY"
BLOCKED = "BLOCKED"
STOPPED = "STOPPED"

VALID_STATES = {CONNECTED, IDLE, BUSY, BLOCKED, STOPPED}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Cockpit:
    """Registre d'état des workers Kilo."""

    def __init__(self, root: pathlib.Path | None = None) -> None:
        self.dir = pathlib.Path(root or COCKPIT_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, worker_id: str) -> pathlib.Path:
        return self.dir / f"{worker_id}.json"

    def set_state(self, worker_id: str, state: str,
                  detail: str = "", mission_id: str | None = None) -> None:
        """Définit l'état d'un worker."""
        if state not in VALID_STATES:
            raise ValueError(f"état invalide: {state} (valeurs valides: {VALID_STATES})")
        record = {
            "worker_id": worker_id,
            "state": state,
            "detail": detail,
            "mission_id": mission_id,
            "updated_at": _now_iso(),
        }
        self._path(worker_id).write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def get_state(self, worker_id: str) -> dict | None:
        """Récupère l'état d'un worker."""
        path = self._path(worker_id)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def list_workers(self) -> list[str]:
        if not self.dir.is_dir():
            return []
        return sorted(p.stem for p in self.dir.glob("*.json"))

    def all_states(self) -> dict[str, dict]:
        return {w: self.get_state(w) for w in self.list_workers()}

    def request_stop(self, worker_id: str) -> tuple[bool, str]:
        """Demande l'arrêt gracieux d'un worker (marque STOPPED)."""
        current = self.get_state(worker_id)
        if current is None:
            return False, f"worker inconnu: {worker_id}"
        if current["state"] == STOPPED:
            return False, f"worker déjà arrêté: {worker_id}"
        self.set_state(worker_id, STOPPED, detail="arrêt demandé par le cockpit")
        return True, f"arrêt demandé: {worker_id}"


def cockpit_status(worker_id: str | None = None,
                   root: pathlib.Path | None = None) -> dict:
    """Retourne l'état du cockpit (un worker ou tous)."""
    cockpit = Cockpit(root)
    if worker_id:
        state = cockpit.get_state(worker_id)
        if state is None:
            return {"worker_id": worker_id, "state": "UNKNOWN",
                    "detail": "worker non enregistré"}
        return state
    return {"workers": cockpit.all_states(),
            "count": len(cockpit.list_workers())}


def _cmd_status(args, cockpit):
    if args.all:
        states = cockpit.all_states()
        for wid, st in states.items():
            print(f"{wid:<24} {st['state']:<10} {st.get('detail','')}")
    else:
        state = cockpit_status(args.worker, root=cockpit.dir.parent if hasattr(cockpit, 'dir') else None)
        print(json.dumps(state, indent=2, ensure_ascii=False))


def _cmd_stop(args, cockpit):
    ok, msg = cockpit.request_stop(args.worker)
    print(msg)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Kilo G7 Cockpit — état des workers")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status")
    p_status.add_argument("--worker", default=None)
    p_status.add_argument("--all", action="store_true")
    p_status.set_defaults(func=lambda args: _cmd_status(args, cockpit))

    p_stop = sub.add_parser("stop")
    p_stop.add_argument("--worker", required=True)
    p_stop.set_defaults(func=lambda args: _cmd_stop(args, cockpit))

    args = parser.parse_args()
    cockpit = Cockpit()
    args.func(args)
