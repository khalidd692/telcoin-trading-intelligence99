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
    return [str(l.get("name", "")) for l in issue.get("labels", []) if isinstance(l, dict)]


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
        and isinstance(i.get("number"), int)
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

    if quota_remaining is not None and quota_remaining < quota_min_remaining:
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
