"""Read-only projections of existing agent reports for the local cockpit."""

from __future__ import annotations

from datetime import datetime, timezone
import re

from ..project_kit import read_json
from ..team_config import role_catalog

MAX_JSON = 512 * 1024
MAX_ROWS = 80
STATES = frozenset({
    "ACK", "RUNNING", "WORKER_EXITED", "ACCEPTED", "REJECTED", "AWAITING_HUMAN",
    "BLOCKED", "IDLE", "BUSY", "STOPPED", "STOP_REQUESTED", "PLANNED", "PASS", "FAIL",
})
BLOCKERS = frozenset({
    "SOURCE_UNAVAILABLE_OR_INVALID", "GITHUB_RECEIPT_OR_APPROVAL_UNCONFIRMED",
    "BLOCKED_PROVIDER_RATE_LIMIT", "Blocked", "OSError", "ValueError", "TimeoutError",
    "TypeError", "KeyError", "AttributeError",
})
REPO_RE = re.compile(r"[A-Za-z0-9-]{1,39}/[A-Za-z0-9_.-]{1,100}")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z")


def read_snapshot(path):
    if path is None:
        return None
    try:
        return read_json(path, limit=MAX_JSON)
    except (OSError, ValueError, RecursionError):
        pass
    return None


def object_fields(value):
    return value if isinstance(value, dict) else {}


def label(value, options):
    return value if isinstance(value, str) and value in options else None


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        return None
    if re.match(r"(gh[pousr]_|github_pat_|sk[-_]|akia)", value, re.IGNORECASE):
        return None
    return value


def number(value):
    return value if type(value) is int and 0 <= value <= 1_000_000_000 else None


def date(value):
    if isinstance(value, str) and UTC.fullmatch(value):
        try:
            return datetime.fromisoformat(value).isoformat().replace("+00:00", "Z")
        except ValueError:
            return None
    if type(value) in (int, float) and 0 < value < 4_000_000_000:
        return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")
    return None


def github_url(value, repo, suffix):
    if not isinstance(value, str) or len(value) > 300:
        return None
    prefix = "https://github.com/" + repo + "/"
    return value if re.fullmatch(re.escape(prefix) + suffix, value) else None


def snapshot(*, status=None, plan=None, pulls=None, handoffs=None, repository, mode="snapshot", project=None):
    if not REPO_RE.fullmatch(repository):
        raise ValueError("invalid repository")
    status = object_fields(status)
    plan = object_fields(plan)
    status_matches = project is None or status.get("project") == project
    if project is not None and plan.get("project") != project:
        plan = {}
    heartbeat = object_fields(status.get("last_observed")) if status_matches else {}
    mission_ids = set()
    rows = status.get("missions")
    missions = [] if isinstance(rows, dict) else None
    if missions is not None:
        for row in list(rows.values())[:MAX_ROWS]:
            row = object_fields(row)
            mid = identifier(row.get("id"))
            if mid is None or (project is not None and row.get("project") != project):
                continue
            mission_ids.add(mid)
            proof = object_fields(row.get("verification"))
            digest = proof.get("artifact_sha256")
            missions.append({
                "id": mid, "project": identifier(row.get("project")),
                "state": label(row.get("status"), STATES), "at": date(row.get("at")),
                "proof": digest if (proof.get("ok") is True and isinstance(digest, str)
                                    and re.fullmatch(r"[a-f0-9]{64}", digest)) else None,
            })
    receipts = status.get("github_receipts")
    events = [] if isinstance(receipts, dict) else None
    if events is not None:
        for key, value in list(receipts.items())[:MAX_ROWS]:
            match = re.fullmatch(r"kilo-github/outbox/([A-Za-z0-9-]{1,48})/(ACK|RESULT|EVIDENCE)", key)
            if (match and identifier(match[1])
                    and (project is None or (status_matches and match[1] in mission_ids))):
                url = github_url(value, repository, r"issues/[1-9][0-9]*#issuecomment-[1-9][0-9]*")
                if url or value == "PENDING_RECONCILIATION":
                    events.append({"mission": match[1], "phase": match[2], "url": url})
    handoff_data = object_fields(handoffs)
    handoffs = (handoff_data.get("events")
                if project is None or handoff_data.get("project") == project else None)
    if isinstance(handoffs, list):
        if events is None:
            events = []
        for event in reversed(handoffs[-MAX_ROWS:]):
            event = object_fields(event)
            mid = identifier(event.get("task_id"))
            phase = event.get("status")
            phase = label(phase.upper(), STATES) if isinstance(phase, str) else None
            if mid and phase and (project is None or mid in mission_ids):
                events.append({"mission": mid, "phase": phase, "at": date(event.get("at")), "url": None})
        events.sort(key=lambda row: row.get("at") or "", reverse=True)
        events = events[:MAX_ROWS]
    projected_pulls = [] if isinstance(pulls, list) else None
    if projected_pulls is not None:
        for item in pulls[:MAX_ROWS]:
            item = object_fields(item)
            num = number(item.get("number"))
            url = github_url(item.get("html_url"), repository, rf"pull/{num}")
            if num and url:
                projected_pulls.append({
                    "number": num, "url": url, "state": label(item.get("state"), {"open", "closed"}),
                    "draft": item.get("draft") if type(item.get("draft")) is bool else None,
                })
    steps = plan.get("steps")
    planned_roles = {
        row.get("role") for row in steps[:12]
        if isinstance(row, dict) and isinstance(row.get("role"), str)
    } if plan.get("status") == "PLANNED" and isinstance(steps, list) else set()
    estimates = object_fields(plan.get("estimates"))
    return {
        "mode": "demo" if mode == "demo" else "snapshot", "repository": repository,
        "project": project,
        "state": label(status.get("state"), STATES) if status_matches else None,
        "observed_at": date(heartbeat.get("HEARTBEAT")),
        "missions": missions, "events": events, "pulls": projected_pulls,
        "error": label(heartbeat.get("BLOCKER"), BLOCKERS),
        "roles": [{"role": role, "configured": spec.active,
                   "activity": "PLANNED" if role in planned_roles else None}
                  for role, spec in role_catalog().items()],
        "budget": {"quota": number(status.get("quota")) if status_matches else None,
                   "calls": number(estimates.get("model_calls")),
                   "seconds": number(estimates.get("seconds")),
                   "context_tokens": number(estimates.get("context_tokens"))},
    }
