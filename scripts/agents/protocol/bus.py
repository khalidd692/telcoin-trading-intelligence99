#!/usr/bin/env python3
"""TEL99 agent bus — centralised, verifiable routing for distributed missions.

The bus is the integration layer that makes "one mission, many environments"
possible. It:

  * keeps an **actor registry** with an explicit ``connected`` flag, and refuses
    to route a live mission to an actor that is not connected (fail-closed);
  * persists every envelope in a **file bus** so results are centralised and
    auditable, and survives a process restart (this is the resume substrate);
  * tracks each mission's **state machine** and its **step progress**, so a
    mission interrupted mid-way can be resumed at the right step;
  * enforces **loop control**: a per-mission step cap and an attempt cap, so a
    failing or flapping mission stops instead of spinning;
  * performs **error detection and retry policy** deterministically: a
    retryable error is retried up to ``max_attempts``; a fatal or exhausted
    error moves the mission to ``failed`` and records the reason;
  * records **validated learnings** into the shared memory through the Hermes
    adapter, closing the loop between execution and knowledge.

Everything is stdlib and deterministic. Nothing here calls a paid service,
submits an order, merges a branch or changes a permission.
"""

from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass, field

from .envelope import (Envelope, TERMINAL_STATES, new_id, utcnow_iso, validate)

_HERE = pathlib.Path(__file__).resolve()
_AGENTS_DIR = _HERE.parents[1]           # scripts/agents
if str(_AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENTS_DIR))

# Hard loop guards. A mission may not exceed these, whatever an adapter returns.
MAX_STEPS_PER_MISSION = 50
MAX_ATTEMPTS_PER_STEP = 3

DEFAULT_BUS_ROOT = _AGENTS_DIR.parents[1] / "bus"


@dataclass
class MissionRecord:
    """Persisted state of one distributed mission."""

    correlation_id: str
    title: str
    state: str = "queued"
    created_at: str = field(default_factory=utcnow_iso)
    updated_at: str = field(default_factory=utcnow_iso)
    steps: list[dict] = field(default_factory=list)
    completed_step_ids: list[str] = field(default_factory=list)
    attempts: dict[str, int] = field(default_factory=dict)
    envelopes: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    result: dict | None = None
    resumable: bool = False

    def to_dict(self) -> dict:
        return {
            "correlation_id": self.correlation_id,
            "title": self.title,
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "steps": self.steps,
            "completed_step_ids": self.completed_step_ids,
            "attempts": self.attempts,
            "envelopes": self.envelopes,
            "errors": self.errors,
            "result": self.result,
            "resumable": self.resumable,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MissionRecord":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})

    @property
    def next_step_id(self) -> str | None:
        for step in self.steps:
            if step["id"] not in self.completed_step_ids:
                return step["id"]
        return None


class Bus:
    """File-backed bus with an actor registry and loop control."""

    def __init__(self, root: str | pathlib.Path | None = None) -> None:
        self.root = pathlib.Path(root or DEFAULT_BUS_ROOT)
        self.actors: dict[str, dict] = {}
        self.register_default_actors()

    # -- actor registry -----------------------------------------------------
    def register_default_actors(self) -> None:
        from .adapters import hermes, kilo, openhands

        for adapter in (openhands, hermes, kilo):
            a = adapter.actor()
            self.actors[a.id] = a.to_dict()

    def register_actor(self, actor_dict: dict) -> None:
        self.actors[actor_dict["id"]] = actor_dict

    def connected_actors(self) -> list[str]:
        return sorted(k for k, v in self.actors.items() if v.get("connected"))

    def is_connected(self, actor_id: str) -> bool:
        return bool(self.actors.get(actor_id, {}).get("connected"))

    # -- persistence --------------------------------------------------------
    def _missions_dir(self) -> pathlib.Path:
        return self.root / "missions"

    def _envelopes_dir(self) -> pathlib.Path:
        return self.root / "envelopes"

    def _record_path(self, correlation_id: str) -> pathlib.Path:
        return self._missions_dir() / f"{correlation_id}.json"

    def save_mission(self, record: MissionRecord) -> None:
        record.updated_at = utcnow_iso()
        self._missions_dir().mkdir(parents=True, exist_ok=True)
        path = self._record_path(record.correlation_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record.to_dict(), indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        tmp.replace(path)

    def load_mission(self, correlation_id: str) -> MissionRecord | None:
        path = self._record_path(correlation_id)
        if not path.is_file():
            return None
        try:
            return MissionRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None

    def list_missions(self) -> list[str]:
        if not self._missions_dir().is_dir():
            return []
        return sorted(p.stem for p in self._missions_dir().glob("*.json"))

    def persist_envelope(self, envelope: Envelope) -> pathlib.Path:
        self._envelopes_dir().mkdir(parents=True, exist_ok=True)
        path = self._envelopes_dir() / f"{envelope.envelope_id}.json"
        path.write_text(envelope.to_json(), encoding="utf-8")
        return path

    def read_envelope(self, envelope_id: str) -> Envelope | None:
        path = self._envelopes_dir() / f"{envelope_id}.json"
        if not path.is_file():
            return None
        try:
            return Envelope.from_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    # -- mission lifecycle --------------------------------------------------
    def open_mission(self, *, title: str, origin: dict, steps: list[dict],
                     description: str = "", target: dict | None = None,
                     correlation_id: str | None = None) -> MissionRecord:
        """Create a mission and its first envelope (state ``queued``)."""
        cid = correlation_id or new_id("msn")
        record = MissionRecord(correlation_id=cid, title=title,
                               steps=[dict(s) for s in steps], state="queued")
        self.save_mission(record)

        origin_env = Envelope.create(
            origin=_actor_from(origin), kind="mission", state="queued",
            mission_id=cid, title=title, description=description,
            steps=record.steps, correlation_id=cid,
            target=_actor_from(target) if target else None,
        )
        self.persist_envelope(origin_env)
        record.envelopes.append(origin_env.envelope_id)
        self.save_mission(record)
        return record

    def dispatch_step(self, correlation_id: str) -> Envelope:
        """Send the next unfinished step to its assigned, connected actor.

        Fail-closed: if the assigned actor is not connected, the step is not
        dispatched; the mission is marked ``blocked`` and the reason is recorded.
        """
        record = self._require_mission(correlation_id)
        if record.state in TERMINAL_STATES:
            raise RuntimeError(f"mission {correlation_id} is already {record.state}")

        next_step = None
        for step in record.steps:
            if step["id"] not in record.completed_step_ids:
                next_step = step
                break
        if next_step is None:
            return self._finish_success(record)

        if len(record.completed_step_ids) >= MAX_STEPS_PER_MISSION:
            return self._fail(record, "bus.step_cap",
                              f"step cap {MAX_STEPS_PER_MISSION} reached")

        assigned = next_step.get("assigned_to") or ""
        if assigned and not self.is_connected(assigned):
            record.state = "blocked"
            record.errors.append({
                "code": "bus.actor_not_connected",
                "message": f"step {next_step['id']} assigned to {assigned!r}, "
                           "which is not connected",
                "retryable": False, "attempt": 1, "max_attempts": 1, "fatal": False,
            })
            self.save_mission(record)
            raise RuntimeError(f"actor {assigned!r} is not connected")

        envelope = Envelope.create(
            origin=_actor_from(self.actors[assigned]) if assigned else
            _actor_from(self.actors["hermes-router"]),
            kind="sub_mission", state="running",
            mission_id=f"{correlation_id}:{next_step['id']}",
            title=next_step["description"],
            description=next_step.get("intent", next_step["description"]),
            correlation_id=correlation_id,
            parent_envelope_id=record.envelopes[-1] if record.envelopes else None,
            target=_actor_from(self.actors[assigned]) if assigned else None,
        )
        record.state = "running"
        self.persist_envelope(envelope)
        record.envelopes.append(envelope.envelope_id)
        self.save_mission(record)
        return envelope

    def record_result(self, correlation_id: str, step_id: str, *,
                      status: str, summary: str = "",
                      envelope: Envelope | None = None,
                      errors: list[dict] | None = None) -> MissionRecord:
        """Record a step outcome and advance, retry or fail deterministically."""
        record = self._require_mission(correlation_id)
        attempt = record.attempts.get(step_id, 0) + 1
        record.attempts[step_id] = attempt

        if envelope is not None:
            self.persist_envelope(envelope)
            record.envelopes.append(envelope.envelope_id)

        if status == "success":
            if step_id not in record.completed_step_ids:
                if len(record.completed_step_ids) >= MAX_STEPS_PER_MISSION:
                    return self._fail(record, "bus.step_cap",
                                      f"step cap {MAX_STEPS_PER_MISSION} reached",
                                      step_id=step_id)
                record.completed_step_ids.append(step_id)
            self.save_mission(record)
            if record.next_step_id is None:
                return self._finish_success(record)
            return record

        # Failure path: decide retry vs terminal, with a hard attempt cap.
        fatal = bool(errors and any(e.get("fatal") for e in errors))
        if errors:
            record.errors.extend(errors)
        if fatal or attempt >= MAX_ATTEMPTS_PER_STEP:
            reason = ("fatal error" if fatal
                      else f"attempt cap {MAX_ATTEMPTS_PER_STEP} reached")
            return self._fail(record, "bus.step_failed",
                              f"step {step_id} failed: {reason}", step_id=step_id)
        record.state = "queued"
        self.save_mission(record)
        return record

    def resume(self, correlation_id: str) -> MissionRecord:
        """Resume an interrupted mission at its next unfinished step."""
        record = self._require_mission(correlation_id)
        if record.state in TERMINAL_STATES:
            return record
        record.state = "queued"
        record.resumable = False
        self.save_mission(record)
        return record

    # -- internals ----------------------------------------------------------
    def _require_mission(self, correlation_id: str) -> MissionRecord:
        record = self.load_mission(correlation_id)
        if record is None:
            raise KeyError(f"unknown mission {correlation_id}")
        return record

    def _finish_success(self, record: MissionRecord) -> MissionRecord:
        record.state = "done"
        record.result = {
            "status": "success",
            "summary": f"{len(record.completed_step_ids)}/{len(record.steps)} "
                       "step(s) completed",
            "artifacts": [],
            "metrics": {"steps": len(record.steps),
                        "completed": len(record.completed_step_ids)},
        }
        self.save_mission(record)
        return record

    def _fail(self, record: MissionRecord, code: str, message: str,
              step_id: str | None = None) -> MissionRecord:
        record.state = "failed"
        record.resumable = bool(step_id)
        record.result = {
            "status": "failure", "summary": message, "artifacts": [],
            "metrics": {"steps": len(record.steps),
                        "completed": len(record.completed_step_ids)},
        }
        record.errors.append({"code": code, "message": message,
                              "retryable": False,
                              "attempt": record.attempts.get(step_id or "", 1),
                              "max_attempts": MAX_ATTEMPTS_PER_STEP,
                              "fatal": True})
        self.save_mission(record)
        return record


def _actor_from(data: dict):
    from .envelope import Actor

    return Actor(
        environment=data.get("environment", "unknown"),
        id=data.get("id", ""),
        capabilities=tuple(data.get("capabilities", ())),
        connected=bool(data.get("connected", False)),
    )
