#!/usr/bin/env python3
"""TEL99 agent interchange protocol, v1.

The single, versioned contract that lets OpenHands, Hermes and Kilo exchange a
distributed mission: ids, execution states, results, evidence, errors,
validated learnings and resume information.

Design rules:

  * **Versioned and explicit** — every envelope carries
    ``protocol: {name, version}``. A reader refuses an unknown major version
    instead of guessing.
  * **Fail-closed validation** — :func:`validate` returns a list of problems and
    never raises on bad input, so a malformed envelope is rejected, not
    silently accepted. An unreadable envelope is a hard error.
  * **Transport-agnostic** — an envelope is plain JSON. The same bytes travel
    through the file bus (``bus/``), a Git commit, or an HTTP body.
  * **Honest about connections** — an actor carries ``connected``; an actor
    declared but without a verified transport is marked ``connected: false``
    and the bus refuses to route a live mission to it.

The JSON Schema lives next to this module
(``schema/agent-message-v1.schema.json``) for external consumers; this module is
the stdlib-only reference implementation used by the bus and the tests.
"""

from __future__ import annotations

import json
import pathlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

PROTOCOL_NAME = "tel99-agent-interchange"
PROTOCOL_VERSION = 1

SCHEMA_PATH = pathlib.Path(__file__).resolve().parent / "schema" / "agent-message-v1.schema.json"

KINDS = (
    "mission", "sub_mission", "result", "evidence", "error", "learning",
    "resume", "heartbeat",
)
STATES = (
    "queued", "claimed", "running", "blocked", "awaiting_human",
    "done", "failed", "cancelled",
)
TERMINAL_STATES = ("done", "failed", "cancelled")
ENVIRONMENTS = ("openhands", "hermes", "kilo", "human", "unknown")
RESULT_STATUSES = ("success", "partial", "failure", "not_run")
LEARNING_KINDS = ("procedure", "decision", "error", "fix", "fact")

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def new_id(prefix: str = "env") -> str:
    """A unique, sortable-ish envelope id: ``<prefix>-<utc>-<short uuid>``."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


@dataclass
class Actor:
    environment: str
    id: str
    capabilities: tuple[str, ...] = ()
    connected: bool = False

    def to_dict(self) -> dict:
        return {
            "environment": self.environment,
            "id": self.id,
            "capabilities": list(self.capabilities),
            "connected": self.connected,
        }


@dataclass
class Evidence:
    kind: str
    claim: str
    command: str | None = None
    exit_code: int | None = None
    output_digest: str | None = None
    observed_at: str | None = None
    reproducible: bool = False

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "claim": self.claim,
            "command": self.command,
            "exit_code": self.exit_code,
            "output_digest": self.output_digest,
            "observed_at": self.observed_at,
            "reproducible": self.reproducible,
        }


@dataclass
class Envelope:
    """One protocol message. Use :meth:`create` to build a valid one."""

    origin: Actor
    kind: str
    state: str
    envelope_id: str = field(default_factory=lambda: new_id("env"))
    correlation_id: str | None = None
    parent_envelope_id: str | None = None
    target: Actor | None = None
    created_at: str = field(default_factory=utcnow_iso)
    updated_at: str = field(default_factory=utcnow_iso)
    priority: int = 5
    mission: dict | None = None
    result: dict | None = None
    evidence: list[Evidence] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    learnings: list[dict] = field(default_factory=list)
    resume: dict | None = None
    budget: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    @classmethod
    def create(cls, *, origin: Actor, kind: str, state: str = "queued",
               mission_id: str | None = None, title: str = "",
               description: str = "", target: Actor | None = None,
               parent_envelope_id: str | None = None,
               correlation_id: str | None = None, **kw) -> "Envelope":
        """Build an envelope; for a mission, fill the mission block for you."""
        mission = None
        if kind in ("mission", "sub_mission"):
            mission = {
                "id": mission_id or new_id("msn"),
                "title": title or mission_id or "untitled",
                "description": description,
                "acceptance_criteria": kw.pop("acceptance_criteria", []),
                "steps": kw.pop("steps", []),
                "read_only": kw.pop("read_only", True),
                "work_branch": kw.pop("work_branch", None),
            }
        env = cls(
            origin=origin, kind=kind, state=state, target=target,
            parent_envelope_id=parent_envelope_id,
            correlation_id=correlation_id or (mission["id"] if mission else None),
            mission=mission, **kw,
        )
        return env

    # -- serialisation ------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "protocol": {"name": PROTOCOL_NAME, "version": PROTOCOL_VERSION},
            "envelope_id": self.envelope_id,
            "correlation_id": self.correlation_id,
            "parent_envelope_id": self.parent_envelope_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "origin": self.origin.to_dict(),
            "target": self.target.to_dict() if self.target else None,
            "kind": self.kind,
            "state": self.state,
            "priority": self.priority,
            "mission": self.mission,
            "result": self.result,
            "evidence": [e.to_dict() for e in self.evidence],
            "errors": self.errors,
            "learnings": self.learnings,
            "resume": self.resume,
            "budget": self.budget,
            "tags": self.tags,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"

    @classmethod
    def from_dict(cls, data: dict) -> "Envelope":
        origin = data.get("origin") or {}
        target = data.get("target")
        return cls(
            envelope_id=data["envelope_id"],
            correlation_id=data.get("correlation_id"),
            parent_envelope_id=data.get("parent_envelope_id"),
            created_at=data.get("created_at", utcnow_iso()),
            updated_at=data.get("updated_at", utcnow_iso()),
            origin=Actor(
                environment=origin.get("environment", "unknown"),
                id=origin.get("id", ""),
                capabilities=tuple(origin.get("capabilities", ())),
                connected=bool(origin.get("connected", False)),
            ),
            target=Actor(
                environment=target.get("environment", "unknown"),
                id=target.get("id", ""),
                capabilities=tuple(target.get("capabilities", ())),
                connected=bool(target.get("connected", False)),
            ) if isinstance(target, dict) else None,
            kind=data.get("kind", ""),
            state=data.get("state", ""),
            priority=int(data.get("priority", 5)),
            mission=data.get("mission"),
            result=data.get("result"),
            evidence=[Evidence(**{k: e.get(k) for k in
                                  ("kind", "claim", "command", "exit_code",
                                   "output_digest", "observed_at", "reproducible")})
                      for e in data.get("evidence", [])],
            errors=list(data.get("errors", [])),
            learnings=list(data.get("learnings", [])),
            resume=data.get("resume"),
            budget=dict(data.get("budget", {})),
            tags=list(data.get("tags", [])),
        )

    @classmethod
    def from_json(cls, text: str) -> "Envelope":
        return cls.from_dict(json.loads(text))


# --------------------------------------------------------------------------- #
# Validation (stdlib, fail-closed, returns problems instead of raising)
# --------------------------------------------------------------------------- #
def validate(data: dict) -> list[str]:
    """Return the list of schema problems; an empty list means valid.

    This mirrors the published JSON Schema closely enough to be the reference
    for the bus and the tests, without pulling in a validator dependency.
    """
    problems: list[str] = []

    if not isinstance(data, dict):
        return ["envelope is not a JSON object"]

    protocol = data.get("protocol")
    if not isinstance(protocol, dict):
        problems.append("missing protocol block")
    else:
        if protocol.get("name") != PROTOCOL_NAME:
            problems.append(f"unknown protocol name {protocol.get('name')!r}")
        if protocol.get("version") != PROTOCOL_VERSION:
            problems.append(
                f"unsupported protocol version {protocol.get('version')!r} "
                f"(this reader speaks {PROTOCOL_VERSION})"
            )

    for key in ("envelope_id", "created_at", "origin", "kind", "state"):
        if key not in data:
            problems.append(f"missing required field {key!r}")

    eid = data.get("envelope_id")
    if isinstance(eid, str) and not _ID_RE.match(eid):
        problems.append(f"envelope_id {eid!r} does not match the id pattern")
    cid = data.get("correlation_id")
    if cid is not None and (not isinstance(cid, str) or not _ID_RE.match(cid)):
        problems.append(f"correlation_id {cid!r} does not match the id pattern")

    origin = data.get("origin")
    if not isinstance(origin, dict):
        problems.append("origin must be an object")
    else:
        if origin.get("environment") not in ENVIRONMENTS:
            problems.append(f"origin.environment {origin.get('environment')!r} "
                            "is not a known environment")
        if not origin.get("id"):
            problems.append("origin.id is required")

    if data.get("kind") not in KINDS:
        problems.append(f"kind {data.get('kind')!r} is not one of {KINDS}")
    if data.get("state") not in STATES:
        problems.append(f"state {data.get('state')!r} is not one of {STATES}")

    mission = data.get("mission")
    if data.get("kind") in ("mission", "sub_mission"):
        if not isinstance(mission, dict):
            problems.append("a mission envelope must carry a mission block")
        else:
            if not mission.get("id"):
                problems.append("mission.id is required")
            if not mission.get("title"):
                problems.append("mission.title is required")

    result = data.get("result")
    if result is not None:
        if not isinstance(result, dict):
            problems.append("result must be an object or null")
        elif result.get("status") not in RESULT_STATUSES:
            problems.append(f"result.status {result.get('status')!r} is not one "
                            f"of {RESULT_STATUSES}")

    if data.get("state") in TERMINAL_STATES and data.get("kind") in ("mission",
                                                                     "sub_mission"):
        if not isinstance(result, dict):
            problems.append(f"a mission in terminal state {data.get('state')!r} "
                            "must carry a result block")

    for i, err in enumerate(data.get("errors", []) or []):
        if not isinstance(err, dict) or not err.get("code") or not err.get("message"):
            problems.append(f"errors[{i}] needs both code and message")

    for i, learning in enumerate(data.get("learnings", []) or []):
        if not isinstance(learning, dict) or not learning.get("id") or not learning.get("text"):
            problems.append(f"learnings[{i}] needs both id and text")
        elif learning.get("kind", "fact") not in LEARNING_KINDS:
            problems.append(f"learnings[{i}].kind {learning.get('kind')!r} is "
                            f"not one of {LEARNING_KINDS}")

    resume = data.get("resume")
    if resume is not None and not isinstance(resume, dict):
        problems.append("resume must be an object or null")

    priority = data.get("priority", 5)
    if not isinstance(priority, int) or not 0 <= priority <= 9:
        problems.append("priority must be an integer within [0, 9]")

    return problems


def validate_file(path: str | pathlib.Path) -> list[str]:
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read envelope: {exc}"]
    try:
        data = json.loads(text)
    except ValueError as exc:
        return [f"envelope is not valid JSON: {exc}"]
    return validate(data)


def is_terminal(state: str) -> bool:
    return state in TERMINAL_STATES
