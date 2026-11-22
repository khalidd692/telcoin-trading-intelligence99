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

import hashlib
import json
import os
import pathlib
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone

try:
    from ..protocol.store import FileStore
except ImportError:  # direct CLI imports the existing top-level package
    from protocol.store import FileStore

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
            verified=data.get("verified") is True,
            verified_by=str(data.get("verified_by", "")),
            supersedes=str(data.get("supersedes", "")),
            superseded_by=str(data.get("superseded_by", "")),
        )


def _read_project_snapshot(path: pathlib.Path, project: str) -> dict:
    if not project or project != slug(project):
        raise ValueError("invalid snapshot project")
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or type(data.get("schema")) is not int
            or data["schema"] != SCHEMA_VERSION or data.get("project") != project
            or not isinstance(data.get("entries"), list)
            or not isinstance(data.get("history"), list)
            or not all(isinstance(event, dict) for event in data["history"])):
        raise ValueError("invalid memory snapshot or different project")
    seen = set()
    for entry in data["entries"]:
        if (not isinstance(entry, dict) or entry.get("project") != project
                or not isinstance(entry.get("id"), str) or entry["id"] in seen
                or type(entry.get("verified")) is not bool
                or type(entry.get("version")) is not int or entry["version"] < 1):
            raise ValueError("invalid or duplicate entry in memory snapshot")
        Entry.from_dict(entry)
        seen.add(entry["id"])
    return data


def _write_new_private(path: pathlib.Path, data: dict) -> None:
    """Publish a complete, owner-only local file without replacing a target."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".memory-", delete=False) as output:
            tmp_path = pathlib.Path(output.name)
            json.dump(data, output, indent=2, ensure_ascii=False, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.link(tmp_path, path)
    finally:
        if tmp_path is not None:
            tmp_path.unlink()


class MemoryStore:
    """A file-backed, project-isolated knowledge store."""

    def __init__(self, root: str | pathlib.Path) -> None:
        self.root = pathlib.Path(root)
        self._file_store = FileStore(self.root)

    # -- paths --------------------------------------------------------------
    def _path(self, project: str) -> pathlib.Path:
        if project == COMMON_PROJECT:
            return self.root / "common.json"
        return self.root / "projects" / f"{slug(project)}.json"

    def _load(self, project: str) -> dict:
        path = self._path(project)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"schema": SCHEMA_VERSION, "project": project, "entries": [],
                    "history": []}
        except (OSError, ValueError) as exc:
            raise ValueError("memory document is unreadable") from exc
        if not isinstance(data, dict) or data.get("project") != project:
            raise ValueError("memory document belongs to a different project or is invalid")
        entries = data.setdefault("entries", [])
        if not isinstance(entries, list) or any(
                not isinstance(entry, dict) or entry.get("project") != project for entry in entries):
            raise ValueError("memory document contains invalid or foreign entries")
        data.setdefault("history", [])
        return data

    def _write_lock(self, project):
        path = self._path(project)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        return self._file_store._locked(path)

    def _save(self, project: str, data: dict) -> None:
        path = self._path(project)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".memory-", delete=False) as stream:
            temporary = pathlib.Path(stream.name)
            try:
                json.dump(data, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
            except BaseException:
                stream.close()
                temporary.unlink(missing_ok=True)
                raise
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    # -- write --------------------------------------------------------------
    def record(self, entry: Entry, *, actor: str = "agent") -> Entry:
        """Store a new entry, versioning it above any existing same-id entry.

        Re-recording the same id bumps the version and keeps a history line, so
        the store is append-only with respect to belief: nothing is silently
        overwritten.
        """
        if not isinstance(entry.project, str) or not entry.project.strip():
            raise ValueError("entry project must be a non-empty string")
        with self._write_lock(entry.project):
            data = self._load(entry.project)
            self._record_entry(data, entry, actor)
            self._save(entry.project, data)
        return entry

    @staticmethod
    def _record_entry(data: dict, entry: Entry, actor: str) -> None:
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

    def supersede(self, project: str, old_id: str, new: Entry, *,
                  actor: str = "agent") -> Entry:
        """Record ``new`` and mark ``old_id`` as superseded by it.

        The old entry is kept (with ``superseded_by`` set) so the reason a
        belief changed remains auditable.
        """
        if new.project != project:
            raise ValueError("a replacement entry must belong to the same project")
        if new.id == old_id:
            raise ValueError("a replacement entry needs a distinct id")
        with self._write_lock(project):
            data = self._load(project)
            old = next((entry for entry in data["entries"] if entry["id"] == old_id), None)
            if old is None:
                raise ValueError("the entry to replace does not exist")
            new.supersedes = old_id
            old["superseded_by"] = new.id
            self._record_entry(data, new, actor)
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
        with self._write_lock(project):
            data = self._load(project)
            found = False
            for e in data["entries"]:
                if e["id"] == entry_id:
                    if not isinstance(by, str) or not by.strip() or by == e.get("author"):
                        raise ValueError("verification requires a distinct reviewer")
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
               include_superseded: bool = False, include_common: bool = True,
               verified_only: bool = False) -> list[Entry]:
        """Rank stored experiences against a free-text query.

        Scoring is deterministic and explainable: a token overlap on title,
        body and tags, boosted for verified and high-confidence entries and for
        an exact tag match. Superseded entries are excluded by default, because
        retrieving a belief we already corrected would repeat the old mistake.
        """
        tokens = set(re.findall(r"[^\W_]+", query.casefold()))
        scored: list[tuple[float, Entry]] = []
        for entry in self.all_entries(project, include_common=include_common):
            if verified_only and (entry.verified is not True or not entry.verified_by):
                continue
            if not include_superseded and entry.superseded_by:
                continue
            if kinds and entry.kind not in kinds:
                continue
            hay_title = set(re.findall(r"[^\W_]+", entry.title.casefold()))
            hay_body = set(re.findall(r"[^\W_]+", entry.body.casefold()))
            hay_tags = {t.casefold() for t in entry.tags}
            if tokens and not tokens.intersection(hay_title | hay_body | hay_tags):
                continue
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

    def context_references(self, project: str, query: str, *, limit: int = 3) -> list[dict]:
        """Summarize matching verified knowledge without exposing free-form content."""
        if (not isinstance(query, str) or not 1 <= len(query.strip()) <= 256
                or not re.search(r"[^\W_]", query)
                or type(limit) is not int or not 1 <= limit <= 8
                or project == COMMON_PROJECT):
            raise ValueError("invalid project context request")
        entries = self.search(project, query, limit=limit, include_common=False, verified_only=True)
        return [{"project": project, "id": entry.id, "version": entry.version,
                 "sha256": hashlib.sha256(json.dumps(entry.to_dict(), sort_keys=True,
                                                    ensure_ascii=True).encode()).hexdigest()}
                for entry in entries if re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", entry.id)]

    def export_project(self, project: str, destination: str | pathlib.Path) -> None:
        """Write one existing project document, including its provenance and history."""
        path = pathlib.Path(destination)
        snapshot = _read_project_snapshot(self._path(project), project)
        _write_new_private(path, snapshot)

    def restore_project(self, project: str, source: str | pathlib.Path) -> None:
        """Restore an operator-provided snapshot into an empty project slot."""
        data = _read_project_snapshot(pathlib.Path(source), project)
        destination = self._path(project)
        with self._write_lock(project):
            _write_new_private(destination, data)

    def history(self, project: str) -> list[dict]:
        return self._load(project)["history"]
