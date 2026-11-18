#!/usr/bin/env python3
"""Bridge between the cloud-autonomy orchestrator and the agent bus.

The orchestrator (``orchestrator.py``) already knows how to pick one authorised
mission and drive the three-agent team, with a KV lock and a deadline. The bus
(``scripts/agents/protocol/bus.py``) adds the *distributed ledger*: one envelope
per mission, a persisted state machine, deduplication and centralised results
that survive a container destruction.

This module is the only glue between them. It never re-implements either side:

  * it turns a GitHub mission issue into a bus mission whose three steps are the
    existing roles (analyst, developer, verifier) from ``team_config``;
  * it makes the correlation id **deterministic** from
    ``(repository, issue number)`` so a re-run maps to the same mission and the
    same work branch — a finished mission is therefore never reprocessed;
  * it records the outcome as a result envelope plus a validated learning, so
    the next run (possibly on another container) reads it back from the store.

Read-only with respect to repository history: it writes only to the bus store
(KV in the cloud, files locally).
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve()
_AGENTS_DIR = _HERE.parents[1]           # scripts/agents
if str(_AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENTS_DIR))

from protocol.bus import Bus  # noqa: E402
from protocol.envelope import Actor  # noqa: E402

# The three team roles, in execution order. Reused from team_config so the bus
# never invents a team of its own.
ROLE_ORDER = ("analyst", "developer", "verifier")


def correlation_id(repository: str, issue_number: int) -> str:
    """Deterministic mission id: the same issue always maps to the same mission.

    The id is a stable hash, so it does not depend on when the run happens —
    which is what lets a later run recognise an already-processed mission.
    """
    digest = hashlib.sha256(f"{repository}#{issue_number}".encode()).hexdigest()[:12]
    return f"msn-gh-{issue_number}-{digest}"


def roles_from_team_config() -> list[str]:
    """The three active roles, read from team_config (never hard-coded)."""
    import team_config as cfg

    return [spec.role for spec in cfg.ACTIVE_AGENTS]


def _origin() -> dict:
    return Actor(
        environment="openhands", id="cloud-orchestrator",
        capabilities=("select_mission", "drive_team", "record_result"),
        connected=True,
    ).to_dict()


def _steps_for_roles(work_branch: str, repository: str, issue_number: int) -> list[dict]:
    """One bus step per team role, assigned to the (connected) Hermes router.

    The bus does not dispatch to a live cloud conversation itself — the
    orchestrator does that. The bus records the *plan* and the *outcome* of each
    role so the mission is auditable and resumable.
    """
    return [
        {
            "id": role,
            "description": f"role {role} on mission #{issue_number}",
            "intent": role,
            "assigned_to": "hermes-router",
        }
        for role in roles_from_team_config()
    ]


def mission_state(bus: Bus, corr: str) -> str | None:
    record = bus.load_mission(corr)
    return record.state if record else None


def is_already_finished(bus: Bus, corr: str) -> bool:
    """True when the bus already holds a terminal success for this mission.

    This is the guarantee that a finished mission is not reprocessed: even if a
    later run picks the same issue, the bus says it is done.
    """
    record = bus.load_mission(corr)
    if record is None:
        return False
    return record.state == "done" or (
        record.result is not None and record.result.get("status") == "success"
    )


def open_or_resume(bus: Bus, *, repository: str, issue: dict, work_branch: str) -> dict:
    """Open a fresh bus mission, or resume an interrupted one.

    Returns a small dict describing what happened, so the orchestrator can
    journal it verbatim.
    """
    corr = correlation_id(repository, issue["number"])
    existing = bus.load_mission(corr)

    if existing is not None and existing.state == "done":
        return {"correlation_id": corr, "action": "already_done",
                "state": existing.state}

    if existing is not None and existing.state in ("running", "blocked", "queued"):
        resumed = bus.resume(corr)
        return {"correlation_id": corr, "action": "resumed", "state": resumed.state}

    # A failed-but-resumable mission is retried: reopen a fresh record under the
    # same deterministic id so the ledger keeps one entry per mission and the
    # attempt is a genuine new try rather than a silent reuse of the failure.
    if existing is not None and existing.state == "failed" and existing.resumable:
        record = bus.open_mission(
            title=f"GitHub mission #{issue['number']}: {issue.get('title', '')}".strip(),
            origin=_origin(),
            steps=_steps_for_roles(work_branch, repository, issue["number"]),
            description=(issue.get("body") or "")[:2000],
            correlation_id=corr,
        )
        return {"correlation_id": corr, "action": "retried", "state": record.state}

    record = bus.open_mission(
        title=f"GitHub mission #{issue['number']}: {issue.get('title', '')}".strip(),
        origin=_origin(),
        steps=_steps_for_roles(work_branch, repository, issue["number"]),
        description=(issue.get("body") or "")[:2000],
        correlation_id=corr,
    )
    return {"correlation_id": corr, "action": "opened", "state": record.state}


def record_outcome(bus: Bus, corr: str, *, success: bool, summary: str,
                   conversation_id: str = "", work_branch: str = "",
                   status_detail: str = "", evidence: dict | None = None,
                   verdict: dict | None = None) -> dict:
    """Record the final outcome of a mission and, only if validated, a learning.

    Called once per run, on success *and* on failure, so the ledger is always
    truthful. ``success`` must already be the *verified* verdict computed by the
    orchestrator from observable evidence — a conversation merely reporting
    ``finished`` is not a success.

    A validated success writes a result envelope and a learning marked
    ``verified: True`` (verified by the orchestrator's evidence checks). A
    non-validated outcome records a failure with the evidence and leaves the
    mission resumable; it never writes a ``verified`` learning.
    """
    if success and not (verdict and verdict.get("validated")):
        raise ValueError("refusing to record an unverified success as a success")

    learning_id = f"mission-{corr}"
    proof = (evidence or {}).get("independent_verification") or {}
    artifact = ({"path": proof["artifact"], "commit_sha": proof["commit_sha"],
                 "sha256": proof["artifact_sha256"]} if proof.get("verifier")
                else {"path": work_branch} if work_branch else None)

    def complete(record):
        if record.state == "done":
            return

        record.result = {
            "status": "success" if success else "failure",
            "summary": summary,
            "artifacts": [artifact] if success and artifact else [],
            "metrics": {"conversation_id": conversation_id or ""},
            "evidence": evidence or {},
            "verdict": verdict or {},
        }
        if success:
            for step in record.steps:
                if step["id"] not in record.completed_step_ids:
                    record.completed_step_ids.append(step["id"])
            record.state = "done"
            record.result["metrics"]["roles"] = len(record.steps)
            record.learnings.append({
                "id": learning_id,
                "text": f"Mission {corr} reussie en lecture seule: {summary}",
                "kind": "procedure",
                "verified": True,
                "verified_by": proof.get("verifier", "openhands"),
                "source_envelope_id": record.envelopes[-1] if record.envelopes else None,
            })
        else:
            record.state = "failed"
            record.resumable = True
            record.errors.append({
                "code": "orchestrator.outcome_unvalidated",
                "message": status_detail or summary,
                "retryable": True, "attempt": 1, "max_attempts": 3, "fatal": False,
            })

    record = bus.mutate_mission(corr, complete)
    learning = next((entry for entry in record.learnings
                     if entry.get("id") == learning_id), None)
    return {"state": record.state, "result": record.result, "learning": learning}


def ledger(bus: Bus) -> dict:
    """A compact view of the whole ledger, for reports and the journal."""
    missions = []
    for corr in bus.list_missions():
        record = bus.load_mission(corr)
        if record is None:
            continue
        missions.append({
            "correlation_id": corr,
            "title": record.title,
            "state": record.state,
            "completed": len(record.completed_step_ids),
            "steps": len(record.steps),
            "resumable": record.resumable,
        })
    return {"storage": bus.storage_report(), "count": len(missions),
            "missions": missions}
