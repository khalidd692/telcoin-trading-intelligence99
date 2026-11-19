"""Authenticated GitHub admission source for the existing #124 supervisor.

This is the missing adapter identified in the #94 checkpoint of 2026-11-19:
it turns owner-approved GitHub mission comments into the exact contract shape
``Runtime.run_queue`` already validates, without a second supervisor, bus or
journal. Approval is bound to (1) the GitHub author identity, (2) a pinned
owner mandate comment, (3) an explicit expiry and (4) a content fingerprint.
``seal()``/``fingerprint()`` remain fingerprints, not signatures: the trust
anchor is the authenticated owner account plus the pinned mandate.

Only ``owner=hermes`` synthetic missions are admitted here; ``owner=kilo``
contracts keep their existing transport. Published relay events carry a
distinct marker and are never re-admitted (no feedback loop).
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone

try:
    from .autonomy_runtime import fingerprint, validate_contract
except ImportError:  # flat script execution
    from autonomy_runtime import fingerprint, validate_contract

APPROVERS = {"khalidd692"}
MARKER = "hermes-mission/v1"
EVENT_MARKER = "hermes-relay-event/v1"
BLOCK_RE = re.compile(r"```" + re.escape(MARKER) + r"\s*\n(.*?)\n```", re.DOTALL)
MAX_PAGES = 3
MAX_MISSIONS = 20


def default_fetcher(endpoint):
    completed = subprocess.run(["gh", "api", endpoint], capture_output=True,
                               text=True, timeout=60, check=False)
    if completed.returncode != 0:
        raise OSError(f"gh api unavailable: {completed.stderr.strip()[:200]}")
    return json.loads(completed.stdout)


def fetch_comments(repo, issue, *, fetcher=None, max_pages=MAX_PAGES):
    fetcher = fetcher or default_fetcher
    comments = []
    for page in range(1, max_pages + 1):
        data = fetcher(f"repos/{repo}/issues/{issue}/comments?per_page=100&page={page}")
        if not isinstance(data, list):
            raise ValueError("unexpected GitHub comments payload")
        comments.extend(data)
        if len(data) < 100:
            break
    return comments


def fetch_mandate(repo, issue, comment_id, *, fetcher=None):
    fetcher = fetcher or default_fetcher
    # Single issue comments live under issues/comments/{id} (no issue number).
    comment = fetcher(f"repos/{repo}/issues/comments/{comment_id}")
    if not isinstance(comment, dict) or (comment.get("user") or {}).get("login") not in APPROVERS:
        raise ValueError("mandate comment is not owner-authored")
    return comment


def _expiry_ok(approval, now):
    try:
        expiry = datetime.strptime(approval["expires_at"], "%Y-%m-%dT%H:%M:%SZ")
    except (KeyError, TypeError, ValueError):
        return False
    return expiry.replace(tzinfo=timezone.utc) > now


def parse_approvals(comments, *, mandate_comment_id, now=None):
    now = now or datetime.now(timezone.utc)
    missions, approvals, sources = [], {}, {}
    for comment in comments:
        login = (comment.get("user") or {}).get("login", "")
        body = comment.get("body") or ""
        if login not in APPROVERS or EVENT_MARKER in body:
            continue
        match = BLOCK_RE.search(body)
        if not match:
            continue
        try:
            payload = json.loads(match.group(1))
        except ValueError:
            continue
        mission, approval = payload.get("mission"), payload.get("approval")
        if not isinstance(mission, dict) or not isinstance(approval, dict):
            continue
        if mission.get("owner") != "hermes":
            continue
        if approval.get("approver") != login:
            continue
        if approval.get("mandate_comment_id") != mandate_comment_id:
            continue
        if not _expiry_ok(approval, now):
            continue
        mid = mission.get("id")
        if not isinstance(mid, str) or mid in approvals:
            continue
        digest = fingerprint(mission)
        if approval.get("mission_sha256") != digest:
            continue
        try:
            validate_contract(mission, {mid: digest})
        except (ValueError, TypeError):
            continue
        missions.append(mission)
        approvals[mid] = digest
        sources[mid] = comment.get("id")
    return {"missions": missions[:MAX_MISSIONS], "approvals": approvals, "sources": sources}


def github_source(repo, issue, mandate_issue, mandate_comment_id, *, fetcher=None):
    """Return the ``{"missions": [...], "approvals": {...}}`` poll payload.

    Raises OSError/ValueError on GitHub failure or invalid mandate so the
    engine's ``poll`` fail-closes to BLOCKED (SOURCE_UNAVAILABLE_OR_INVALID).
    """
    fetcher = fetcher or default_fetcher
    fetch_mandate(repo, mandate_issue, mandate_comment_id, fetcher=fetcher)
    comments = fetch_comments(repo, issue, fetcher=fetcher)
    return parse_approvals(comments, mandate_comment_id=mandate_comment_id)
