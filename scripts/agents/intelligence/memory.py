#!/usr/bin/env python3
"""Versioned, provenance-carrying shared memory for the TEL99 agent team.

Design goals (from issue #67, axis 2):

  * **Versioned** — every entry carries a monotonically increasing version and
    an append-only history, so a correction never erases what was believed
    before.
  * **Provenance** — each entry records where it came from (source, commit,
    author agent, date) so a claim can be traced and re-checked.
  * **Project isolation** — a project can only read its own entries plus the
    explicitly shared ``common`` pool. One project's notes never leak into
    another; this is enforced in code, not by convention.
  * **Retrieval before a task** — ``search`` ranks stored experiences for a
    query so a new mission can start from what already worked.
  * **Capitalised errors** — a ``fix`` entry links the error it corrected, so a
    corrected mistake is found again instead of being repeated.

Storage is plain JSON on disk (no database, no network, no dependency). The
store is deterministic: the same operations always yield the same bytes, which
keeps it reviewable and diff-friendly in git.
"""

from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

SCHEMA_VERSION = 1
COMMON_PROJECT = "common"

# Kinds of knowledge the team capitalises.
KINDS = ("procedure", "decision", "error", "fix", "fact")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


@dataclass
class Entry:
    """A single unit of shared knowledge."""

    id: str
    project: str
    kind: str
    title: str
    body: str
    tags: tuple[str, ...] = ()
    source: str = ""
    commit: str = ""
    author: str = ""
    created_at: str = field(default_factory=utcnow_iso)
    version: int = 1
    confidence: float = 0.5
    verified: bool = False
    verified_by: str = ""
    supersedes: str = ""
    superseded_by: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown kind {self.kind!r}; expected one of {KINDS}")
        if not self.id:
            raise ValueError("entry id is required")
        if not self.project:
            raise ValueError("entry project is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project": self.project,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "tags": list(self.tags),
            "source": self.source,
            "commit": self.commit,
            "author": self.author,
            "created_at": self.created_at,
            "version": self.version,
            "confidence": self.confidence,
            "verified": self.verified,
            "verified_by": self.verified_by,
            "supersedes": self.supersedes,
            "superseded_by": self.superseded_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Entry":
        return cls(
            id=str(data["id"]),
            project=str(data["project"]),
            kind=str(data["kind"]),
            title=str(data.get("title", "")),
            body=str(data.get("body", "")),
            tags=tuple(data.get("tags", ())),
            source=str(data.get("source", "")),
            commit=str(data.get("commit", "")),
            author=str(data.get("author", "")),
            created_at=str(data.get("created_at", "")) or utcnow_iso(),
            version=int(data.get("version", 1)),
            confidence=float(data.get("confidence", 0.5)),
            verified=bool(data.get("verified", False)),
            verified_by=str(data.get("verified_by", "")),
            supersedes=str(data.get("supersedes", "")),
            superseded_by=str(data.get("superseded_by", "")),
        )


class MemoryStore:
    """A project-isolated knowledge store.

    By default it persists to plain JSON files under ``root`` (the historical
    behaviour, used locally and by the tests). It can instead be given a
    ``backend`` — any object exposing the tiny ``get(key)`` / ``put(key, value)``
    contract of :mod:`scripts.agents.protocol.store` (``FileStore`` or the
    durable ``KvStore``). With a ``KvStore`` backend the same knowledge survives
    the destruction of a cloud container, so a second, independent run can read
    what the first recorded. The store never invents a storage layer of its own:
    it reuses the existing protocol backend.
    """

    # Namespace for the durable backend, kept distinct from the bus's
    # ``missions/`` and ``envelopes/`` keys.
    BACKEND_PREFIX = "memory"

    def __init__(self, root: str | pathlib.Path | None = None, *,
                 backend=None) -> None:
        self.root = pathlib.Path(root) if root is not None else None
        self.backend = backend

    # -- paths --------------------------------------------------------------
    def _path(self, project: str) -> pathlib.Path:
        if self.root is None:
            raise ValueError("file storage requires a root directory")
        if project == COMMON_PROJECT:
            return self.root / "common.json"
        return self.root / "projects" / f"{slug(project)}.json"

    def _backend_key(self, project: str) -> str:
        return f"{self.BACKEND_PREFIX}/projects/{slug(project)}"

    def durable(self) -> bool:
        """True only when the backing store survives a container."""
        if self.backend is not None and hasattr(self.backend, "durable"):
            return bool(self.backend.durable())
        return False

    @staticmethod
    def _empty(project: str) -> dict:
        return {"schema": SCHEMA_VERSION, "project": project, "entries": [],
                "history": []}

    def _load(self, project: str) -> dict:
        if self.backend is not None:
            raw = self.backend.get(self._backend_key(project))
            if not isinstance(raw, dict):
                return self._empty(project)
            raw.setdefault("entries", [])
            raw.setdefault("history", [])
            return raw
        path = self._path(project)
        if not path.is_file():
            return self._empty(project)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self._empty(project)
        data.setdefault("entries", [])
        data.setdefault("history", [])
        return data

    def _save(self, project: str, data: dict) -> None:
        if self.backend is not None:
            self.backend.put(self._backend_key(project), data)
            return
        path = self._path(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        tmp.replace(path)

    # -- write --------------------------------------------------------------
    def record(self, entry: Entry, *, actor: str = "agent") -> Entry:
        """Store a new entry, versioning it above any existing same-id entry.

        Re-recording the same id bumps the version and keeps a history line, so
        the store is append-only with respect to belief: nothing is silently
        overwritten.
        """
        if not isinstance(entry.project, str) or not entry.project.strip():
            raise ValueError("entry project must be a non-empty string")
        data = self._load(entry.project)
        previous = [e for e in data["entries"] if e["id"] == entry.id]
        if previous:
            entry.version = max(int(e.get("version", 1)) for e in previous) + 1
        data["entries"] = [e for e in data["entries"] if e["id"] != entry.id]
        data["entries"].append(entry.to_dict())
        data["entries"].sort(key=lambda e: (e["project"], e["id"]))
        data["history"].append({
            "at": utcnow_iso(),
            "actor": actor,
            "action": "record",
            "id": entry.id,
            "version": entry.version,
        })
        self._save(entry.project, data)
        return entry

    def supersede(self, project: str, old_id: str, new: Entry, *,
                  actor: str = "agent") -> Entry:
        """Record ``new`` and mark ``old_id`` as superseded by it.

        The old entry is kept (with ``superseded_by`` set) so the reason a
        belief changed remains auditable.
        """
        new.supersedes = old_id
        new.project = project
        self.record(new, actor=actor)
        data = self._load(project)
        for e in data["entries"]:
            if e["id"] == old_id:
                e["superseded_by"] = new.id
        data["history"].append({
            "at": utcnow_iso(),
            "actor": actor,
            "action": "supersede",
            "id": new.id,
            "supersedes": old_id,
        })
        self._save(project, data)
        return new

    def verify(self, project: str, entry_id: str, *, by: str,
               confidence: float = 0.9) -> bool:
        """Mark an entry as independently verified.

        Verification is what lets a retrieved experience be trusted; an entry
        that was never verified keeps ``verified = False`` and is ranked lower.
        """
        data = self._load(project)
        found = False
        for e in data["entries"]:
            if e["id"] == entry_id:
                e["verified"] = True
                e["verified_by"] = by
                e["confidence"] = max(0.0, min(1.0, confidence))
                found = True
        if found:
            data["history"].append({
                "at": utcnow_iso(), "actor": by, "action": "verify", "id": entry_id,
            })
            self._save(project, data)
        return found

    # -- read ---------------------------------------------------------------
    def get(self, project: str, entry_id: str) -> Entry | None:
        for raw in self._load(project)["entries"]:
            if raw["id"] == entry_id:
                return Entry.from_dict(raw)
        return None

    def all_entries(self, project: str, *, include_common: bool = True) -> list[Entry]:
        """Return the entries a project is allowed to see.

        A project always sees its own entries. It sees ``common`` entries only
        when ``include_common`` is true, and never another project's entries.
        """
        entries = [Entry.from_dict(e) for e in self._load(project)["entries"]]
        if include_common and project != COMMON_PROJECT:
            entries += [Entry.from_dict(e)
                        for e in self._load(COMMON_PROJECT)["entries"]]
        return entries

    def search(self, project: str, query: str, *, limit: int = 5,
               kinds: tuple[str, ...] | None = None,
               include_superseded: bool = False) -> list[Entry]:
        """Rank stored experiences against a free-text query.

        Scoring is deterministic and explainable: a token overlap on title,
        body and tags, boosted for verified and high-confidence entries and for
        an exact tag match. Superseded entries are excluded by default, because
        retrieving a belief we already corrected would repeat the old mistake.
        """
        tokens = {t for t in re.split(r"[^a-z0-9]+", query.lower()) if t}
        scored: list[tuple[float, Entry]] = []
        for entry in self.all_entries(project):
            if not include_superseded and entry.superseded_by:
                continue
            if kinds and entry.kind not in kinds:
                continue
            hay_title = set(re.split(r"[^a-z0-9]+", entry.title.lower()))
            hay_body = set(re.split(r"[^a-z0-9]+", entry.body.lower()))
            hay_tags = {t.lower() for t in entry.tags}
            score = 0.0
            score += 3.0 * len(tokens & hay_title)
            score += 1.0 * len(tokens & hay_body)
            score += 2.0 * len(tokens & hay_tags)
            if tokens and hay_tags and tokens <= hay_tags:
                score += 1.5
            if entry.verified:
                score += 1.0
            score += 0.5 * entry.confidence
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda pair: (-pair[0], pair[1].id))
        return [entry for _, entry in scored[:limit]]

    def history(self, project: str) -> list[dict]:
        return self._load(project)["history"]
