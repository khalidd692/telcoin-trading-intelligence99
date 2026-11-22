"""Authenticated GitHub admission source for the existing #124 supervisor.

This is the missing adapter identified in the #94 checkpoint of 2026-11-19:
it turns owner-approved GitHub mission comments into the exact contract shape
``Runtime.run_queue`` already validates, without a second supervisor, bus or
journal. Approval is bound to (1) the GitHub author identity, (2) a pinned
owner mandate comment, (3) an explicit expiry and (4) a content fingerprint.
``seal()``/``fingerprint()`` remain fingerprints, not signatures: the trust
anchor is the authenticated owner account plus the pinned mandate.

The default profile admits Hermes contracts. The Kilo transport selects its
own marker and supplies only comments from its pinned issue and owner.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone

try:
    from .autonomy_runtime import REJECTED_MISSION, fingerprint, validate_contract
except ImportError:  # flat script execution
    from autonomy_runtime import REJECTED_MISSION, fingerprint, validate_contract

OWNER_LOGIN = "khalidd692"
OWNER_ID = 275517051
APPROVERS = {OWNER_LOGIN}
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


class GitHubRateLimited(OSError):
    """GitHub refused the request because its API limit was reached."""


class GitHubWriteNotSent(OSError):
    """A local guard prevented a GitHub write before any request was sent."""


def is_owner(user):
    return (isinstance(user, dict) and user.get("login") == OWNER_LOGIN
            and user.get("id") == OWNER_ID and user.get("type") == "User")


def default_fetcher(endpoint):
    return gh_json(endpoint)


def gh_json(endpoint, *, body=None, timeout=60, method="GET", payload=None):
    command = ["gh", "api", "--hostname", "github.com", endpoint]
    if body is not None:
        method, payload = "POST", {"body": body}
    if method != "GET":
        command.extend(["--method", method])
    if payload is not None:
        command.extend(["--input", "-"])
    try:
        completed = subprocess.run(command, input=json.dumps(payload).encode("utf-8") if payload is not None else None,
                                   capture_output=True,
                                   env={**os.environ, "GH_PROMPT_DISABLED": "1"},
                                   timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        # Fail-closed to the engine's SOURCE_UNAVAILABLE path (review F1).
        raise OSError("gh api timeout") from exc
    if completed.returncode != 0:
        error = completed.stderr.decode("utf-8", errors="replace").casefold()
        if "(http 429)" in error or "(http 403)" in error and "rate limit" in error:
            raise GitHubRateLimited("GitHub API rate limit reached")
        raise OSError(f"gh api unavailable (exit {completed.returncode})")
    return json.loads(completed.stdout.decode("utf-8"))


def fetch_comments(repo, issue, *, fetcher=None, max_pages=MAX_PAGES):
    fetcher = fetcher or default_fetcher
    return fetch_pages(f"repos/{repo}/issues/{issue}/comments?per_page=100",
                       fetcher=fetcher, max_pages=max_pages)


def fetch_pages(endpoint, *, fetcher, max_pages=MAX_PAGES):
    rows = []
    for page in range(1, max_pages + 1):
        data = fetcher(f"{endpoint}&page={page}")
        if not isinstance(data, list):
            raise ValueError("unexpected GitHub list payload")
        rows.extend(data)
        if len(data) < 100:
            return rows
    raise ValueError("pagination cap reached; refusing to truncate the queue")


def _unique_keys(pairs):
    """Reject ambiguous duplicate JSON keys for both admission profiles."""
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
    if "id" in (comment.get("user") or {}) and not is_owner(comment["user"]):
        raise ValueError("mandate is not from the pinned owner account")
    if comment.get("id", comment_id) != comment_id or comment.get(
        "issue_url", f"https://api.github.com/repos/{repo}/issues/{issue}"
    ) != f"https://api.github.com/repos/{repo}/issues/{issue}":
        raise ValueError("mandate issue or comment identity mismatch")
    # Reserve F6: the mandate is pinned by content, not only by author/id.
    if mandate_sha256 is not None:
        digest = hashlib.sha256((comment.get("body") or "").encode("utf-8")).hexdigest()
        if digest != mandate_sha256:
            raise ValueError("mandate content does not match the pinned sha256")
    return comment


def approval_is_current(approval, now):
    try:
        expiry = datetime.strptime(approval["expires_at"], "%Y-%m-%dT%H:%M:%SZ")
    except (KeyError, TypeError, ValueError):
        return False
    return expiry.replace(tzinfo=timezone.utc) > now


def fenced_json(body, marker):
    """Read one exact fenced JSON object and reject ambiguous duplicate keys."""
    if not isinstance(body, str):
        return None
    match = re.fullmatch(r"```" + re.escape(marker) + r"\r?\n(.*?)\r?\n```",
                         body.strip(), re.DOTALL)
    if match is None:
        return None

    try:
        data = json.loads(match[1], object_pairs_hook=_unique_keys)
    except (ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def parse_approvals(comments, *, mandate_comment_id, now=None,
                    owner_approval_reader=None, owner="hermes"):
    now = now or datetime.now(timezone.utc)
    strict = owner == "kilo"
    missions, approvals, sources, conflicts = [], {}, {}, set()
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        user = comment.get("user")
        if not isinstance(user, dict) or ("id" in user and not is_owner(user)):
            continue
        login = user.get("login", "")
        body = comment.get("body") or ""
        if (not isinstance(login, str) or login not in APPROVERS or not isinstance(body, str)
                or EVENT_MARKER in body or PROPOSAL_MARKER in body):
            continue
        if strict:
            payload = fenced_json(body, "kilo-mission/v1")
        else:
            match = BLOCK_RE.search(body)
            try:
                payload = json.loads(match[1], object_pairs_hook=_unique_keys) if match else None
            except (ValueError, RecursionError):
                continue
        if not isinstance(payload, dict):
            continue
        mission, approval = payload.get("mission"), payload.get("approval")
        if not isinstance(mission, dict) or not isinstance(approval, dict):
            continue
        if mission.get("owner") != owner:
            continue
        if approval.get("approver") != login:
            continue
        if approval.get("mandate_comment_id") != mandate_comment_id:
            continue
        if not approval_is_current(approval, now):
            continue
        mid = mission.get("id")
        if not isinstance(mid, str) or mid == REJECTED_MISSION:
            continue
        digest = fingerprint(mission)
        if approval.get("mission_sha256") != digest:
            continue
        # Review point 3: distinguish AI-delegated approval from a distinct
        # human approval. Missing origin stays backward-compatible with the
        # validated synthetic demo and is treated as delegated-mandate.
        origin = approval.get("origin", "delegated-mandate")
        if not isinstance(origin, str) or origin not in ORIGINS:
            continue
        if origin == "owner-direct":
            # Requires a local owner artifact the adapter only READS (never
            # writes): approval distinct from the agent that proposes/executes.
            artifact = owner_approval_reader(mid) if owner_approval_reader else None
            if (not isinstance(artifact, dict)
                    or artifact.get("approved_by") != login
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
        if mid in approvals:
            if strict and approvals[mid] != digest:
                conflicts.add(mid)
            continue
        missions.append(mission)
        approvals[mid] = digest
        sources[mid] = comment.get("id")
    if conflicts:
        missions = [mission for mission in missions if mission["id"] not in conflicts]
        for mid in conflicts:
            del approvals[mid], sources[mid]
    if strict and len(missions) > MAX_MISSIONS:
        raise ValueError("too many eligible Kilo missions for the bounded queue")
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
