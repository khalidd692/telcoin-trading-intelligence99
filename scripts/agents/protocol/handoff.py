#!/usr/bin/env python3
"""TEL99 handoff engine — the *code* half of the zero-copy-paste contract.

Issue #94 asks the owners to stop being the human transport between agents. A
Markdown protocol cannot do that; a runnable, testable mechanism can. This
module is that mechanism. It is stdlib-only, deterministic, offline, and reuses
the existing bus/envelope/store rather than creating a competing one (the
dossier forbids a second bus).

It implements the four code gaps the audit of ``main`` found missing:

  * :func:`select_next_task` / :class:`HandoffLedger` — **automatic next-task
    selection**: given the backlog and the *live* statuses, pick the highest
    admissible task (dependencies accepted, owner not human-reserved) and record
    the handoff durably so a later session resumes without a human relaying it.
  * :class:`Inbox` — an **idempotent receiver** keyed on a stable ``request_id``:
    the same message delivered twice produces exactly one action and one ACK,
    which is what makes "ACK lost / message re-delivered" safe (gate G6).
  * :func:`content_digest` / :func:`approve` / :func:`approval_is_current` — a
    **content-bound approval**: the approved mission is tied to a hash, so an
    issue edited after approval is refused instead of silently executed
    (gate G0/S-06, anti-injection).
  * :func:`verify_mission` — a **real verdict** that can return ``REJECTED``
    even when every agent role reports PASS but an acceptance check is red
    (gate G3/S-05: "un test réellement rouge doit produire REJECTED").

Nothing here calls a paid service, submits an order, merges a branch, changes a
permission or writes repository history: it writes only to the bus store (KV in
the cloud, files locally).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve()
_AGENTS_DIR = _HERE.parents[1]           # scripts/agents
if str(_AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENTS_DIR))

from protocol.envelope import utcnow_iso          # noqa: E402
from protocol.store import default_store          # noqa: E402

HUMAN_RESERVED_OWNERS = frozenset(
    {"owner", "human", "proprietaire", "propriétaire", "user"}
)


def _normalise_owner(owner) -> str:
    """Case- and whitespace-insensitive owner key (``" Owner "`` == ``"owner"``)."""
    return str(owner or "").strip().lower()

NON_STARTABLE_STATES = frozenset(
    {"accepted", "blocked", "awaiting_human", "cancelled", "in_progress"}
)

ACCEPTED = "accepted"
DEFAULT_STATUS = "todo"

MISSION_ACCEPTED = "MISSION_ACCEPTED"
REJECTED = "REJECTED"
NEEDS_HUMAN = "NEEDS_HUMAN"


def priority_rank(task: dict) -> int:
    raw = str(task.get("priority", "P9")).strip().upper()
    if len(raw) == 2 and raw[0] == "P" and raw[1].isdigit():
        return int(raw[1])
    return 9


def task_state(task: dict, statuses: dict | None = None) -> str:
    statuses = statuses or {}
    if task.get("id") in statuses:
        return str(statuses[task["id"]])
    return str(task.get("initial_state", DEFAULT_STATUS))


def is_admissible(task: dict, statuses: dict | None = None, *,
                  owner: str | None = None) -> tuple[bool, str]:
    statuses = statuses or {}
    if _normalise_owner(task.get("owner")) in HUMAN_RESERVED_OWNERS:
        return False, f"owner {task.get('owner')!r} is human-reserved"
    if owner is not None and _normalise_owner(task.get("owner")) != _normalise_owner(owner):
        return False, f"owner {task.get('owner')!r} is not {owner!r}"

    state = task_state(task, statuses)
    if state in NON_STARTABLE_STATES:
        return False, f"state {state!r} is not startable"

    missing = [d for d in task.get("dependencies", [])
               if statuses.get(d) != ACCEPTED]
    if missing:
        return False, f"dependencies not accepted: {missing}"
    return True, ""


def select_next_task(backlog: dict, statuses: dict | None = None, *,
                     owner: str | None = None) -> dict | None:
    candidates = [t for t in backlog.get("tasks", [])
                  if is_admissible(t, statuses, owner=owner)[0]]
    if not candidates:
        return None
    candidates.sort(key=lambda t: (priority_rank(t), str(t.get("id", ""))))
    return candidates[0]


def admissibility_report(backlog: dict, statuses: dict | None = None, *,
                         owner: str | None = None) -> dict:
    statuses = statuses or {}
    rows = []
    for task in backlog.get("tasks", []):
        ok, reason = is_admissible(task, statuses, owner=owner)
        rows.append({
            "id": task.get("id"),
            "priority": task.get("priority"),
            "owner": task.get("owner"),
            "state": task_state(task, statuses),
            "dependencies": list(task.get("dependencies", [])),
            "admissible": ok,
            "reason": reason,
        })
    chosen = select_next_task(backlog, statuses, owner=owner)
    return {"tasks": rows,
            "next_task": chosen.get("id") if chosen else None}


def content_digest(content: str) -> str:
    normalised = "\n".join(line.rstrip() for line in (content or "").strip().splitlines())
    return "sha256:" + hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def approve(content: str, *, approver: str, approved_at: str | None = None) -> dict:
    if not approver:
        raise ValueError("an approval needs an approver")
    return {
        "approved_content_hash": content_digest(content),
        "approved_by": approver,
        "approved_at": approved_at or utcnow_iso(),
    }


def approval_is_current(content: str, approval: dict | None) -> tuple[bool, str]:
    if not isinstance(approval, dict) or not approval.get("approved_content_hash"):
        return False, "no content-bound approval on record"
    if content_digest(content) != approval["approved_content_hash"]:
        return False, "mission content changed after approval (hash mismatch)"
    return True, "approved content unchanged"


class Inbox:
    def __init__(self, receiver_id: str, store=None) -> None:
        if not receiver_id:
            raise ValueError("an inbox needs a receiver id")
        self.receiver_id = receiver_id
        self.store = store or default_store()

    @staticmethod
    def _request_id(message: dict) -> str:
        rid = (message or {}).get("request_id") or (message or {}).get("envelope_id")
        if not isinstance(rid, str) or not rid.strip():
            raise ValueError("message has no stable request_id/envelope_id to dedupe on")
        return rid.strip()

    def _key(self, request_id: str) -> str:
        return f"inbox/{self.receiver_id}/{request_id}"

    def receive(self, message: dict, *, act=None) -> dict:
        """Receive a message; run ``act`` at most once per stable request id.

        Two-phase and crash-safe: a *claim* is persisted **before** the action
        runs, so a duplicate that arrives after a crash is never re-executed
        (no double action — gate G6). The only exception is a previously
        *failed* action, which may be retried once; a completed or in-flight
        request is always a no-op.
        """
        request_id = self._request_id(message)
        existing = self.store.get(self._key(request_id))
        if isinstance(existing, dict) and existing.get("status") != "failed":
            return {"accepted": False, "duplicate": True,
                    "request_id": request_id, "ack": existing, "action": None,
                    "status": existing.get("status", "ACK")}

        # Claim first: any later delivery (even after a crash mid-action) sees
        # this record and will not re-run the action.
        self.store.put(self._key(request_id), {
            "request_id": request_id,
            "receiver": self.receiver_id,
            "claimed_at": utcnow_iso(),
            "status": "claimed",
        })

        action = None
        try:
            if act is not None:
                action = act(message)
        except Exception:
            self.store.put(self._key(request_id), {
                "request_id": request_id, "receiver": self.receiver_id,
                "failed_at": utcnow_iso(), "status": "failed",
            })
            raise

        ack = {
            "request_id": request_id,
            "receiver": self.receiver_id,
            "acked_at": utcnow_iso(),
            "status": "ACK",
            "action": action,
        }
        self.store.put(self._key(request_id), ack)
        return {"accepted": True, "duplicate": False,
                "request_id": request_id, "ack": ack, "action": action,
                "status": "ACK"}

    def seen(self, request_id: str) -> bool:
        return isinstance(self.store.get(self._key(request_id)), dict)


def _as_check(entry) -> dict:
    if isinstance(entry, dict):
        return entry
    return {
        "id": getattr(entry, "claim", None) or getattr(entry, "kind", "check"),
        "command": getattr(entry, "command", None),
        "exit_code": getattr(entry, "exit_code", None),
        "output_digest": getattr(entry, "output_digest", None),
        "reproducible": getattr(entry, "reproducible", False),
    }


def verify_mission(*, conversation_finished: bool, roles: dict,
                   acceptance_checks: list | None = None) -> dict:
    checks: list[dict] = []
    rejected = False
    needs_human = False
    satisfied: list[str] = []
    failed: list[str] = []
    human: list[str] = []

    checks.append({"check": "conversation_finished", "ok": bool(conversation_finished)})
    if not conversation_finished:
        rejected = True

    if not roles:
        checks.append({"check": "roles_reported", "ok": False,
                       "detail": "no roles supplied"})
        rejected = True
    for role, info in (roles or {}).items():
        reported = bool(info.get("reported")) if isinstance(info, dict) else bool(info)
        checks.append({"check": f"role_{role}_reported", "ok": reported})
        if not reported:
            rejected = True

    for raw in (acceptance_checks or []):
        entry = _as_check(raw)
        cid = str(entry.get("id") or entry.get("command") or "check")
        automatable = bool(entry.get("command")) if entry.get("automatable") is None \
            else bool(entry.get("automatable"))
        if not automatable:
            human.append(cid)
            checks.append({"check": f"criterion_{cid}", "ok": False,
                           "detail": "not automatable -> NEEDS_HUMAN"})
            needs_human = True
            continue
        ok = (entry.get("exit_code") == 0 and bool(entry.get("reproducible"))
              and bool(entry.get("output_digest")))
        checks.append({"check": f"criterion_{cid}", "ok": ok,
                       "detail": f"exit_code={entry.get('exit_code')!r} "
                                 f"reproducible={bool(entry.get('reproducible'))}"})
        if ok:
            satisfied.append(cid)
        else:
            failed.append(cid)
            rejected = True

    if rejected:
        verdict = REJECTED
    elif needs_human:
        verdict = NEEDS_HUMAN
    elif not satisfied:
        verdict = REJECTED
        checks.append({"check": "at_least_one_satisfied_check", "ok": False,
                       "detail": "no verifiable acceptance check declared"})
    else:
        verdict = MISSION_ACCEPTED

    return {
        "verdict": verdict,
        "validated": verdict == MISSION_ACCEPTED,
        "checks": checks,
        "satisfied": satisfied,
        "failed": failed,
        "needs_human": human,
    }


class HandoffLedger:
    STATUSES_KEY = "handoff/statuses"
    EVENTS_KEY = "handoff/events"

    def __init__(self, store=None) -> None:
        self.store = store or default_store()

    def statuses(self) -> dict:
        data = self.store.get(self.STATUSES_KEY)
        return dict(data) if isinstance(data, dict) else {}

    def events(self) -> list:
        data = self.store.get(self.EVENTS_KEY)
        return list(data) if isinstance(data, list) else []

    def set_status(self, task_id: str, status: str) -> None:
        statuses = self.statuses()
        statuses[task_id] = status
        self.store.put(self.STATUSES_KEY, statuses)

    def record_handoff(self, *, task_id: str, owner: str, status: str,
                       sha: str = "", tests: str = "", proof: str = "",
                       next_task: str = "", block_reason: str = "") -> dict:
        event = {
            "task_id": task_id,
            "owner": owner,
            "status": status,
            "sha": sha,
            "tests": tests,
            "proof": proof,
            "next_task": next_task,
            "block_reason": block_reason,
            "at": utcnow_iso(),
        }
        log = self.events()
        log.append(event)
        self.store.put(self.EVENTS_KEY, log)
        self.set_status(task_id, status)
        return event

    def next_task(self, backlog: dict, *, owner: str | None = None) -> dict | None:
        return select_next_task(backlog, self.statuses(), owner=owner)

    def report(self, backlog: dict, *, owner: str | None = None) -> dict:
        return admissibility_report(backlog, self.statuses(), owner=owner)


def load_backlog(path: str | pathlib.Path) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
