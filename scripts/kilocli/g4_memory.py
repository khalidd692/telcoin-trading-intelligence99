#!/usr/bin/env python3
"""Kilo G4 Memory — persistance d'état inter-sessions sans copier-coller.

Session A écrit son état dans .kilo/memory/ ; Session B le recharge et
reprend exactement là où A s'est arrêté, sans aucune transmission manuelle.

Format : un fichier JSON par session, indexé par session_id.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]  # scripts/kilocli -> scripts -> root
MEMORY_DIR = ROOT / ".kilo" / "memory"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return "sha256:" + h.hexdigest()


class MemoryStore:
    """Magasin de persistance inter-sessions."""

    def __init__(self, root: pathlib.Path | None = None) -> None:
        self.dir = pathlib.Path(root or MEMORY_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> pathlib.Path:
        return self.dir / f"{session_id}.json"

    def save(self, session_id: str, state: dict) -> str:
        """Sauvegarde l'état d'une session. Retourne le SHA-256 de l'artefact."""
        state["session_id"] = session_id
        state["saved_at"] = _now_iso()
        path = self._path(session_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        tmp.replace(path)
        return sha256_file(path)

    def load(self, session_id: str) -> dict | None:
        """Recharge l'état d'une session précédente."""
        path = self._path(session_id)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def list_sessions(self) -> list[str]:
        if not self.dir.is_dir():
            return []
        return sorted(p.stem for p in self.dir.glob("*.json"))

    def latest(self) -> tuple[str, dict] | None:
        """Retourne (session_id, état) de la session la plus récente."""
        sessions = self.list_sessions()
        if not sessions:
            return None
        # Trier par date de modification
        files = [(p, p.stat().st_mtime) for p in self.dir.glob("*.json")]
        files.sort(key=lambda x: x[1], reverse=True)
        latest_path = files[0][0]
        state = json.loads(latest_path.read_text(encoding="utf-8"))
        return latest_path.stem, state


def handoff_memory(from_session: str, to_session: str,
                   state: dict, store: MemoryStore | None = None) -> str:
    """Transfère l'état de la session from_session vers to_session.

    L'état est écrit dans .kilo/memory/<to_session>.json avec une référence
    vers la session source. La session to_session peut le recharger sans
    aucun copier-coller manuel.
    """
    store = store or MemoryStore()
    state["from_session"] = from_session
    state["to_session"] = to_session
    state["handoff_at"] = _now_iso()
    state["status"] = "transmitted"
    return store.save(to_session, state)


def _cmd_save(args, store):
    import json
    state = json.loads(pathlib.Path(args.file).read_text(encoding="utf-8"))
    sha = store.save(args.session, state)
    print(f"session {args.session} sauvegardée (sha={sha})")


def _cmd_load(args, store):
    state = store.load(args.session)
    if state is None:
        print(f"aucune session {args.session}")
    else:
        print(json.dumps(state, indent=2, ensure_ascii=False))


def _cmd_list(args, store):
    for sid in store.list_sessions():
        print(sid)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Kilo G4 Memory — persistance inter-sessions")
    sub = parser.add_subparsers(dest="command", required=True)

    p_save = sub.add_parser("save")
    p_save.add_argument("--session", required=True)
    p_save.add_argument("--file", required=True, help="fichier JSON d'état à sauvegarder")
    p_save.set_defaults(func=lambda args: _cmd_save(args, store))

    p_load = sub.add_parser("load")
    p_load.add_argument("--session", required=True)
    p_load.set_defaults(func=lambda args: _cmd_load(args, store))

    p_list = sub.add_parser("list")
    p_list.set_defaults(func=lambda args: _cmd_list(args, store))

    args = parser.parse_args()
    store = MemoryStore()
    args.func(args)
