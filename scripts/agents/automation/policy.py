"""Pure decision logic for the TEL99 cloud-autonomy orchestrator.

Everything here is deterministic and side-effect free so it can be tested
without a network, an agent server or the OpenHands SDK. The orchestrator
imports these helpers; it never re-implements them.

Design rules encoded here:
  * only repositories on an explicit allowlist are served;
  * only issues carrying the configured mission label are eligible, so old,
    unauthorised issues are never picked up;
  * a work branch may never be a protected product / data / deployment branch;
  * at most one mission is active at a time.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

# The only repository the team is authorised to work on. Adding a repository
# here is a deliberate, reviewable act, not a configuration value.
ALLOWED_REPOSITORIES = frozenset({"khalidd692/telcoin-trading-intelligence99"})

# Branches the automation must never push to or branch from as its own output.
PROTECTED_BRANCHES = frozenset(
    {
        "main",
        "master",
        "codex/tel99-quant-terminal",
        "tel99-live-data",
        "tel99-evaluation-data",
    }
)

# Branch families that are product / data / deployment and therefore protected.
PROTECTED_PREFIXES = ("tel99-",)

# One mission at a time. The plugin schema also pins max_concurrent_missions=1;
# this constant is the second, code-level half of that guarantee.
MAX_CONCURRENT_MISSIONS = 1


def repository_allowed(repository: str) -> bool:
    """True only for a repository on the explicit allowlist."""
    return repository in ALLOWED_REPOSITORIES


def branch_is_protected(branch: str) -> bool:
    """True if ``branch`` is a protected product, data or deployment branch."""
    if not isinstance(branch, str) or not branch.strip():
        return True
    branch = branch.strip()
    if branch in PROTECTED_BRANCHES:
        return True
    return branch.startswith(PROTECTED_PREFIXES)


def work_branch_name(prefix: str, issue_number: int, title: str) -> str:
    """Build the isolated work branch name for a mission.

    Deterministic for a given (prefix, number, title): the same mission always
    maps to the same branch, so a re-run cannot scatter work across branches.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")[:40].strip("-")
    stem = f"{prefix}{issue_number}" + (f"-{slug}" if slug else "")
    name = stem[:120]
    if branch_is_protected(name):
        raise ValueError(f"refusing to build a protected branch name: {name}")
    return name


def _labels(issue: dict) -> list[str]:
    """Return only string label names from a genuine list of label objects."""
    if not isinstance(issue, dict):
        return []
    labels = issue.get("labels")
    if not isinstance(labels, list):
        return []
    return [
        label["name"]
        for label in labels
        if isinstance(label, dict) and isinstance(label.get("name"), str)
    ]


def is_eligible_mission(issue: dict, mission_label: str) -> bool:
    """True if an issue is an authorised, still-open mission.

    Pull requests are never missions (GitHub exposes them through the issues
    endpoint too), and an issue without the mission label is ignored even if it
    looks like a task.
    """
    if not isinstance(issue, dict):
        return False
    if issue.get("pull_request"):
        return False
    if issue.get("state") not in (None, "open"):
        return False
    return mission_label in _labels(issue)


def select_mission(
    issues: list[dict],
    mission_label: str,
    already_processed: set[int] | None = None,
) -> dict | None:
    """Return the single oldest eligible, not-yet-processed mission, or None.

    Deterministic ordering: earliest ``created_at`` first, then lowest number.
    """
    processed = already_processed or set()
    candidates = [
        i
        for i in issues
        if is_eligible_mission(i, mission_label)
        and type(i.get("number")) is int
        and i["number"] > 0
        and (i.get("created_at") is None or isinstance(i.get("created_at"), str))
        and i["number"] not in processed
    ]
    if not candidates:
        return None

    def sort_key(issue: dict):
        created = issue.get("created_at") or ""
        return (created, issue["number"])

    return sorted(candidates, key=sort_key)[0]


def evaluate_preconditions(
    *,
    repository: str,
    base_branch: str,
    work_branch: str,
    quota_remaining: int | None,
    quota_min_remaining: int,
    active_missions: int,
    max_concurrent_missions: int = MAX_CONCURRENT_MISSIONS,
    dry_run: bool = True,
) -> list[str]:
    """Return the list of reasons the run must NOT proceed (empty means go).

    Every reason is a plain, quotable string so it can be written to the
    execution journal and to the GitHub report verbatim.
    """
    reasons: list[str] = []

    if not repository_allowed(repository):
        reasons.append(f"repository {repository!r} is not on the allowlist")

    if branch_is_protected(base_branch):
        reasons.append(f"base branch {base_branch!r} is protected")

    if branch_is_protected(work_branch):
        reasons.append(f"work branch {work_branch!r} is protected")

    if work_branch == base_branch:
        reasons.append("work branch must differ from the base branch")

    if max_concurrent_missions > MAX_CONCURRENT_MISSIONS:
        reasons.append(
            f"max_concurrent_missions {max_concurrent_missions} exceeds the "
            f"hard cap {MAX_CONCURRENT_MISSIONS}"
        )

    if active_missions >= max(1, max_concurrent_missions):
        reasons.append(
            f"{active_missions} mission(s) already active; only "
            f"{max_concurrent_missions} allowed at a time"
        )

    if quota_remaining is None:
        # Fail-closed: an unknown quota (absent, unreadable, or the API
        # unreachable) is treated as "cannot verify", never as "ok". A real
        # mission must not start when the free-conversation budget cannot be
        # confirmed. A dry_run starts no conversation, so it may proceed.
        if not dry_run:
            reasons.append(
                "free conversation quota unknown (absent, unreadable or "
                "inaccessible): refusing to start"
            )
    elif quota_remaining < quota_min_remaining:
        reasons.append(
            f"free conversation quota too low: {quota_remaining} left, "
            f"minimum {quota_min_remaining} required"
        )

    return reasons


def utcnow_iso() -> str:
    """Current UTC time, second precision, ISO-8601 with a trailing Z."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


# --------------------------------------------------------------------------- #
# Mission approval (S-06): content-bound AND actor-authorised
# --------------------------------------------------------------------------- #
# A mission label alone is not an authorisation. Before a mission may start, the
# issue must carry a single machine-readable approval marker whose (a) content
# hash matches the issue's current title+body and (b) approver is on an explicit
# allowlist. An issue edited after approval therefore fails the hash check, and
# an approval written by anyone not on the allowlist is refused. Both checks are
# pure and fail-closed, so the decision can be unit-tested with no network.
#
# This consumes the *same* approval record shape the handoff engine defines
# (``approved_content_hash`` / ``approved_by`` / ``approved_at``); the record is
# carried inside the issue body as a comment so the decision needs no second
# store. The hashing mirrors the repo's existing sha256 idiom.
#
# Marker syntax (one line, HTML comment so it stays invisible on GitHub):
#   <!-- tel99-approval:v1 hash=sha256:<hex> by=<login> -->
APPROVAL_SCHEMES = frozenset({"v1"})
# Any line that *looks* like an approval marker (well-formed or not). Used to
# detect and reject ambiguous or unbound marker-like content.
_MARKER_LINE_PREFIX = re.compile(r"^\s*<!--\s*tel99-approval:", re.IGNORECASE)
# Exactly one well-formed v1 marker line: a sha256 hex digest, a non-empty
# approver with no whitespace, and nothing else on the line. A line that
# starts like a marker but does not match this is NOT removed from the
# digest, so any text an editor smuggles onto such a line still changes the
# hash and is refused.
_WELL_FORMED_MARKER = re.compile(
    r"^\s*<!--\s*tel99-approval:(?P<scheme>[A-Za-z0-9._-]+)"
    r"\s+hash=(?P<hash>sha256:[0-9a-f]{64})\s+by=(?P<by>\S+)\s*-->\s*$"
)


def mission_content(issue: dict) -> str:
    """The content an approval is bound to: normalised title + body.

    The approval marker line itself is removed so approving an issue does not
    change the very digest being approved. Trailing whitespace and trailing
    blank lines are stripped, so a marker appended at the end never perturbs the
    digest.
    """
    if not isinstance(issue, dict):
        return ""
    raw = f"{issue.get('title') or ''}\n{issue.get('body') or ''}"
    lines = [line.rstrip() for line in raw.strip().splitlines()]
    # Remove only an exact, well-formed approval marker line from the digest.
    # A line that merely starts with the marker prefix is kept, so text an
    # editor smuggles onto such a line is still covered by the hash (and the
    # parser below refuses the malformed line).
    lines = [line for line in lines if not _WELL_FORMED_MARKER.match(line)]
    return "\n".join(lines).strip()


def mission_digest(content: str) -> str:
    """``sha256:<hex>`` over the normalised mission content."""
    normalised = "\n".join(
        line.rstrip() for line in (content or "").strip().splitlines()
    )
    return "sha256:" + hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def approval_marker(content: str, *, approver: str, scheme: str = "v1") -> str:
    """Render the approval marker an authorised actor places in the body.

    Kept here so the writer and the reader cannot drift apart.
    """
    return (
        f"<!-- tel99-approval:{scheme} hash={mission_digest(content)} "
        f"by={approver} -->"
    )


def read_approval(issue: dict) -> tuple[dict | None, str]:
    """Extract the approval record from the issue body.

    Returns ``(record, reason)``. ``record`` is ``None`` when no well-formed
    marker of a known scheme is present, and ``reason`` explains why.
    """
    body = issue.get("body") if isinstance(issue, dict) else None
    if not isinstance(body, str):
        return None, "issue body is not a string; refusing"
    text = body
    # Every line that begins like a marker must be a single, well-formed one.
    # Two markers (or one malformed) is ambiguous and is refused: a smuggled
    # marker must never be able to shadow the real approval.
    marker_lines = [ln for ln in text.splitlines() if _MARKER_LINE_PREFIX.match(ln)]
    if not marker_lines:
        return None, "no content-bound approval on the issue"
    if len(marker_lines) > 1:
        return None, "multiple approval markers present; refusing an ambiguous approval"
    match = _WELL_FORMED_MARKER.match(marker_lines[0])
    if not match:
        return None, "malformed approval marker; refusing"
    scheme = match.group("scheme")
    if scheme not in APPROVAL_SCHEMES:
        return None, f"unsupported approval scheme {scheme!r}"
    approver = match.group("by").strip()
    if not approver:
        return None, "the approval marker names no approver"
    return {
        "approved_content_hash": match.group("hash"),
        "approved_by": approver,
        "approved_at": None,
    }, "approval marker found"


def approval_is_authorized(
    issue: dict, authorized: "frozenset[str] | set[str] | list[str] | None"
) -> tuple[bool, str]:
    """True only for a current, content-bound approval by an authorised actor.

    Fail-closed: an empty/missing allowlist refuses every mission; a missing or
    malformed marker refuses; an unknown approver refuses; an issue edited after
    approval refuses (hash mismatch). Returns ``(ok, reason)``.
    """
    allowed = frozenset(str(a) for a in (authorized or ()))
    if not allowed:
        return False, "no authorized approvers configured"
    record, reason = read_approval(issue)
    if record is None:
        return False, reason
    if record["approved_by"] not in allowed:
        return False, (
            f"approval by {record['approved_by']!r} is not an authorized approver"
        )
    if mission_digest(mission_content(issue)) != record["approved_content_hash"]:
        return False, "content changed after approval (hash mismatch)"
    return True, "approved content unchanged and approver authorized"


_APPROVAL_MAX_AGE_SECONDS = 24 * 60 * 60


def has_authenticated_approval(issue: dict, comments: list, *, now: datetime) -> bool:
    """Match the issue approval to a recent unedited GitHub comment.

    The author and timestamps come from GitHub metadata. The comment must
    contain only the canonical marker for the selected mission.
    """
    approval, _ = read_approval(issue)
    if approval is None:
        return False
    approver = approval["approved_by"]
    marker = approval_marker(mission_content(issue), approver=approver)
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        user = comment.get("user")
        if not isinstance(user, dict) or user.get("login") != approver:
            continue
        if str(comment.get("body") or "").strip() != marker:
            continue
        created = comment.get("created_at")
        if not isinstance(created, str) or comment.get("updated_at") != created:
            continue
        try:
            timestamp = datetime.fromisoformat(created.replace("Z", "+00:00"))
            age = (now - timestamp).total_seconds()
        except (ValueError, TypeError):
            continue
        if 0 <= age <= _APPROVAL_MAX_AGE_SECONDS:
            return True
    return False
