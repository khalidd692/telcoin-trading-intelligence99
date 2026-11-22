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

import hashlib
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
PROPOSAL_MARKER = "hermes-relay-proposal/v1"
BLOCK_RE = re.compile(r"```" + re.escape(MARKER) + r"\s*\n(.*?)\n```", re.DOTALL)
# Full bounded traversal (review point 1): 100 pages x 100 = 10 000 comments.
# Hitting the cap on a full page fails closed instead of silently dropping
# newer mandates/approvals from the queue.
MAX_PAGES = 100
MAX_MISSIONS = 20
ORIGINS = {"delegated-mandate", "owner-direct"}


def default_fetcher(endpoint):
    try:
        completed = subprocess.run(["gh", "api", endpoint], capture_output=True,
                                   text=True, encoding="utf-8", timeout=60, check=False)
    except subprocess.TimeoutExpired as exc:
        # Fail-closed to the engine's SOURCE_UNAVAILABLE path (review F1).
        raise OSError("gh api timeout") from exc
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
        if page == max_pages:
            raise ValueError("pagination cap reached; refusing to truncate the queue")
    return comments


def _unique_keys(pairs):
    """Reject ambiguous duplicate JSON keys (defence in depth, owner=hermes)."""
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def fetch_mandate(repo, issue, comment_id, *, fetcher=None, mandate_sha256=None):
    fetcher = fetcher or default_fetcher
    # Single issue comments live under issues/comments/{id} (no issue number).
    comment = fetcher(f"repos/{repo}/issues/comments/{comment_id}")
    if not isinstance(comment, dict) or (comment.get("user") or {}).get("login") not in APPROVERS:
        raise ValueError("mandate comment is not owner-authored")
    # Reserve F6: the mandate is pinned by content, not only by author/id.
    if mandate_sha256 is not None:
        digest = hashlib.sha256((comment.get("body") or "").encode("utf-8")).hexdigest()
        if digest != mandate_sha256:
            raise ValueError("mandate content does not match the pinned sha256")
    return comment


def _expiry_ok(approval, now):
    try:
        expiry = datetime.strptime(approval["expires_at"], "%Y-%m-%dT%H:%M:%SZ")
    except (KeyError, TypeError, ValueError):
        return False
    return expiry.replace(tzinfo=timezone.utc) > now


def parse_approvals(comments, *, mandate_comment_id, now=None, owner_approval_reader=None):
    now = now or datetime.now(timezone.utc)
    missions, approvals, sources = [], {}, {}
    for comment in comments:
        login = (comment.get("user") or {}).get("login", "")
        body = comment.get("body") or ""
        if login not in APPROVERS or EVENT_MARKER in body or PROPOSAL_MARKER in body:
            continue
        match = BLOCK_RE.search(body)
        if not match:
            continue
        try:
            payload = json.loads(match.group(1), object_pairs_hook=_unique_keys)
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
        # Review point 3: distinguish AI-delegated approval from a distinct
        # human approval. Missing origin stays backward-compatible with the
        # validated synthetic demo and is treated as delegated-mandate.
        origin = approval.get("origin", "delegated-mandate")
        if origin not in ORIGINS:
            continue
        if origin == "owner-direct":
            # Requires a local owner artifact the adapter only READS (never
            # writes): approval distinct from the agent that proposes/executes.
            artifact = owner_approval_reader(mid) if owner_approval_reader else None
            if (not isinstance(artifact, dict)
                    or artifact.get("approved_by") not in APPROVERS
                    or artifact.get("channel") != "owner-local"
                    or artifact.get("mission_sha256") != digest):
                continue
        # delegated-mandate is structurally confined to synthetic text missions:
        # validate_contract (project=synthetic, synthetic_data=true, fixed roles)
        # plus the tool-less worker forbid productive changes, permission grants
        # and sensitive operations. An AI cannot self-approve beyond that scope.
        try:
            validate_contract(mission, {mid: digest})
        except (ValueError, TypeError):
            continue
        missions.append(mission)
        approvals[mid] = digest
        sources[mid] = comment.get("id")
    return {"missions": missions[:MAX_MISSIONS], "approvals": approvals, "sources": sources}


def github_source(repo, issue, mandate_issue, mandate_comment_id, *, fetcher=None,
                  owner_approval_reader=None, mandate_sha256=None):
    """Return admitted missions and the hash of the checked mandate snapshot.

    Raises OSError/ValueError on GitHub failure or invalid mandate so the
    engine's ``poll`` fail-closes to BLOCKED (SOURCE_UNAVAILABLE_OR_INVALID).
    """
    fetcher = fetcher or default_fetcher
    mandate = fetch_mandate(repo, mandate_issue, mandate_comment_id, fetcher=fetcher,
                           mandate_sha256=mandate_sha256)
    comments = fetch_comments(repo, issue, fetcher=fetcher)
    admitted = parse_approvals(comments, mandate_comment_id=mandate_comment_id,
                               owner_approval_reader=owner_approval_reader)
    admitted["mandate_sha256"] = hashlib.sha256((mandate.get("body") or "").encode("utf-8")).hexdigest()
    return admitted
