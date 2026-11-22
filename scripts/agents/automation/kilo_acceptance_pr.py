"""Publish a verified synthetic Kilo artifact on an isolated draft PR."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urlencode

from scripts.agents.automation.autonomy_runtime import fingerprint, validate_contract
from scripts.agents.automation.github_mission_source import GitHubWriteNotSent, fenced_json
from protocol.store import StoreError


REPO = "khalidd692/telcoin-trading-intelligence99"
OWNER = "khalidd692"
OWNER_ID = 275517051
ACCEPTANCE_BASE = "codex/kilo-cloud-handoff-20261120"
ACCEPTANCE_BASE_SHA = "a903ebc45c0217ca7e0df527388f21b449cd3215"
EVIDENCE_EVENT = "kilo-relay-event/v1"
VERIFIER = "tel99-fixed-subprocess-v1"
CHECK_NAMES = ("synthetic-contract", "artifact-sha256", "specialist-identity", "zero-cost-evidence")


def _digest(value, length):
    return isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None


def _owner(user):
    return (isinstance(user, dict) and user.get("login") == OWNER
            and user.get("id") == OWNER_ID and user.get("type") == "User")


def _accepted_artifact(store, issue, state):
    mission_id = state.get("id")
    contract = state.get("contract_sha256")
    if (not isinstance(mission_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,48}", mission_id)
            or not _digest(contract, 64) or state.get("project") != "synthetic"
            or state.get("status") != "ACCEPTED" or state.get("execution_status") != "COMPLETED"
            or state != store.get(f"kilo-local/{mission_id}")):
        raise ValueError("the durable Kilo checkpoint is not accepted")

    binding = store.get(f"kilo-github/approvals/{mission_id}") or {}
    mission = binding.get("mission")
    config = store.get("kilo-github/config") or {}
    control_issue = config.get("issue")
    if (not isinstance(mission, dict) or mission.get("id") != mission_id or mission.get("owner") != "kilo"
            or binding.get("contract_sha256") != contract or binding.get("issue") != issue
            or binding.get("base") != ACCEPTANCE_BASE or binding.get("base_sha") != ACCEPTANCE_BASE_SHA
            or config.get("repo") != REPO or config.get("campaign") is not True
            or type(control_issue) is not int or not 0 < control_issue < issue
            or not _digest(config.get("mandate_sha256"), 64)
            or any(type(number) is not int or number <= 0
                   for number in (config.get("mandate_id"), binding.get("comment_id")))):
        raise ValueError("the checkpoint is not bound to the approved GitHub queue")
    validate_contract(mission, {mission_id: contract})

    result = state.get("result") or {}
    report = state.get("verification") or {}
    verdict = state.get("verdict") or {}
    cost = result.get("provider_evidence") or {}
    artifact = result.get("artifact")
    if not isinstance(artifact, str):
        raise ValueError("the artifact must be UTF-8 text")
    data = artifact.encode("utf-8")
    artifact_sha = hashlib.sha256(data).hexdigest()
    checks = [{"name": name, "ok": True} for name in CHECK_NAMES]
    actual_checks = report.get("checks")
    if (not 1 <= len(data) <= 65536
            or artifact_sha != result.get("sha256") or artifact_sha != mission.get("expected_sha256")
            or artifact_sha != report.get("artifact_sha256") or report.get("verifier") != VERIFIER
            or report.get("ok") is not True or verdict.get("validated") is not True
            or actual_checks != checks or any(check.get("ok") is not True for check in actual_checks)
            or result.get("provider") != "kilo-auto-free" or result.get("specialist_id") != mission["specialist"]
            or cost.get("cost_usd") != "0" or cost.get("http_status") != 200
            or not all(_digest(cost.get(k), 64) for k in ("catalog_sha256", "response_sha256"))):
        raise ValueError("the artifact lacks the approved hash, fixed verifier, or zero-cost evidence")

    proof = {"event": EVIDENCE_EVENT, "phase": "EVIDENCE", "issue": issue, "status": "ACCEPTED",
             "execution_status": "COMPLETED", "scope": "synthetic-text", "mission_id": mission_id,
             "mandate_comment_id": config["mandate_id"], "mandate_sha256": config["mandate_sha256"],
             "approval_comment_id": binding["comment_id"], "contract_sha256": contract,
             "artifact_sha256": artifact_sha, "verification_sha256": fingerprint(report), "checks": checks,
             "verifier": VERIFIER, "specialist": mission["specialist"], "cost_usd": "0",
             "catalog_sha256": cost["catalog_sha256"], "response_sha256": cost["response_sha256"]}
    blob_sha = hashlib.sha1(f"blob {len(data)}\0".encode() + data, usedforsecurity=False).hexdigest()
    return artifact, blob_sha, proof


def _verify_proof(github, issue, evidence_url, expected):
    prefix = f"https://github.com/{REPO}/issues/{issue}#issuecomment-"
    if not isinstance(evidence_url, str) or not evidence_url.startswith(prefix):
        raise ValueError("proof URL must identify a comment on the campaign issue")
    comment_id = evidence_url.removeprefix(prefix)
    if not re.fullmatch(r"[1-9][0-9]{0,19}", comment_id):
        raise ValueError("invalid proof comment ID")
    row = github(f"issues/comments/{comment_id}")
    if (not isinstance(row, dict) or row.get("id") != int(comment_id) or not _owner(row.get("user"))
            or row.get("html_url") != evidence_url or not isinstance(row.get("created_at"), str)
            or row.get("created_at") != row.get("updated_at")
            or row.get("issue_url") != f"https://api.github.com/repos/{REPO}/issues/{issue}"):
        raise ValueError("untrusted proof comment")
    event = fenced_json(row.get("body"), EVIDENCE_EVENT)
    if not event or any(event.get(key) != value for key, value in expected.items()):
        raise ValueError("proof comment differs from the verified checkpoint")


def _ref_sha(github, branch):
    refs = github(f"git/matching-refs/heads/{branch}")
    if not isinstance(refs, list) or any(not isinstance(ref, dict) for ref in refs):
        raise ValueError("invalid GitHub ref response")
    objects = [row.get("object") for row in refs if row.get("ref") == f"refs/heads/{branch}"]
    if not objects:
        return None
    if (len(objects) != 1 or not isinstance(objects[0], dict) or objects[0].get("type") != "commit"
            or not _digest(objects[0].get("sha"), 40)):
        raise ValueError("invalid GitHub branch head")
    return objects[0]["sha"]


def _existing_pull(github, branch):
    # Use the head without a base filter to detect a draft redirected to another branch.
    filters = urlencode({"state": "all", "head": f"{OWNER}:{branch}", "per_page": 2})
    pulls = github(f"pulls?{filters}")
    if not isinstance(pulls, list) or len(pulls) > 1 or any(not isinstance(pr, dict) for pr in pulls):
        raise ValueError("invalid or ambiguous pull request response")
    return pulls[0] if pulls else None


def _verified_pull_url(pr, branch, commit, title, body):
    number = pr.get("number")
    if (type(number) is not int or number <= 0 or not _owner(pr.get("user"))
            or pr.get("state") not in {"open", "closed"} or pr.get("draft") is not True
            or pr.get("merged_at") is not None or pr.get("title") != title or pr.get("body") != body):
        raise ValueError("unexpected metadata for the evidence draft")
    for side, ref, sha in (("base", ACCEPTANCE_BASE, ACCEPTANCE_BASE_SHA), ("head", branch, commit)):
        data = pr.get(side) or {}
        repo = data.get("repo") or {}
        if (data.get("ref"), data.get("sha"), repo.get("full_name")) != (ref, sha, REPO):
            raise ValueError("unexpected head or base for the evidence draft")
    url = f"https://github.com/{REPO}/pull/{number}"
    if pr.get("html_url") != url:
        raise ValueError("untrusted evidence draft URL")
    return url


def _create_commit(github, path, artifact, blob_sha, issue):
    parent = github(f"git/commits/{ACCEPTANCE_BASE_SHA}")
    tree = (parent.get("tree") or {}).get("sha")
    if parent.get("sha") != ACCEPTANCE_BASE_SHA or not _digest(tree, 40):
        raise ValueError("cannot verify the pinned base tree")
    blob = github("git/blobs", method="POST", payload={"content": artifact, "encoding": "utf-8"})
    if blob.get("sha") != blob_sha:
        raise ValueError("the GitHub blob differs from the verified UTF-8 bytes")
    created_tree = github("git/trees", method="POST", payload={"base_tree": tree, "tree": [
        {"path": path, "mode": "100644", "type": "blob", "sha": blob_sha},
    ]}).get("sha")
    if not _digest(created_tree, 40):
        raise ValueError("invalid GitHub evidence tree")
    commit = github("git/commits", method="POST", payload={
        "message": f"docs: retain verified synthetic evidence for #{issue}",
        "tree": created_tree, "parents": [ACCEPTANCE_BASE_SHA],
    }).get("sha")
    if not _digest(commit, 40):
        raise ValueError("invalid GitHub evidence commit")
    return commit


def _verify_diff(github, commit, path, blob_sha):
    comparison = github(f"compare/{ACCEPTANCE_BASE_SHA}...{commit}")
    files = comparison.get("files")
    commits = comparison.get("commits")
    if (comparison.get("status") != "ahead" or comparison.get("ahead_by") != 1
            or comparison.get("behind_by") != 0 or comparison.get("total_commits") != 1
            or not isinstance(commits, list) or len(commits) != 1 or commits[0].get("sha") != commit
            or not isinstance(files, list) or len(files) != 1
            or (files[0].get("filename"), files[0].get("status"), files[0].get("sha")) != (path, "added", blob_sha)):
        raise ValueError("the draft would contain changes outside the single verified artifact")


def publish_verified_pr(repo, issue, base, base_sha, state, evidence_url, *, api, store) -> str | None:
    """Return a reconciled draft URL, or None when proof or publication is uncertain."""
    if ((repo, base, base_sha) != (REPO, ACCEPTANCE_BASE, ACCEPTANCE_BASE_SHA)
            or type(issue) is not int or issue <= 0 or not isinstance(state, dict)):
        return None

    def github(endpoint, *, method="GET", payload=None):
        return api(f"repos/{REPO}/{endpoint}", method=method, payload=payload)

    try:
        artifact, blob_sha, proof = _accepted_artifact(store, issue, state)
        _verify_proof(github, issue, evidence_url, proof)
        if _ref_sha(github, base) != base_sha:
            return None

        mission_id = proof["mission_id"]
        artifact_sha = proof["artifact_sha256"]
        suffix = f"{issue}-{mission_id}-{proof['contract_sha256'][:12]}"
        branch = f"codex/tel99-acceptance/{suffix}"
        path = f"docs/agents/autonomy-evidence/acceptance/{suffix}.txt"
        key = f"kilo-github/acceptance-pr/{issue}/{mission_id}"
        intent = {"branch": branch, "base_sha": base_sha, "blob_sha": blob_sha,
                  "contract_sha256": proof["contract_sha256"], "evidence_url": evidence_url}
        existing = store.get(key)
        journal = existing if existing is not None else {"intent": intent}
        if journal.get("intent") != intent:
            return None
        commit = journal.get("commit_sha")
        head = _ref_sha(github, branch)
        pull = _existing_pull(github, branch)
        if (head is not None and head != commit) or (pull is not None and (head is None or not journal.get("pr_pending"))):
            return None

        if existing is None and not store.put_cas(key, journal, None):
            return None
        if commit is None:
            commit = _create_commit(github, path, artifact, blob_sha, issue)
            _verify_diff(github, commit, path, blob_sha)
            prepared = {**journal, "commit_sha": commit}
            if not store.put_cas(key, prepared, journal):
                return None
            journal = prepared
        else:
            if not _digest(commit, 40):
                return None
            _verify_diff(github, commit, path, blob_sha)

        if head is None:
            if journal.get("pr_pending") or _ref_sha(github, base) != base_sha:
                return None
            try:
                github("git/refs", method="POST", payload={"ref": f"refs/heads/{branch}", "sha": commit})
            except (OSError, ValueError, TypeError):
                pass
            if _ref_sha(github, branch) != commit:
                return None

        title = f"Synthetic Kilo evidence for #{issue} ({mission_id})"
        body = "\n".join((f"Refs #{issue}", "", f"Proof {evidence_url}",
                          f"Artifact SHA-256 `{artifact_sha}`", f"Verifier `{VERIFIER}`",
                          f"Checks passed: {', '.join(CHECK_NAMES)}", "Recorded provider cost $0."))
        if pull is None:
            if (journal.get("pr_pending") or _ref_sha(github, base) != base_sha
                    or _ref_sha(github, branch) != commit):
                return None
            pending = {**journal, "pr_pending": True}
            if not store.put_cas(key, pending, journal):
                return None
            journal = pending
            try:
                pull = github("pulls", method="POST", payload={
                    "title": title, "body": body, "head": branch, "base": base, "draft": True,
                })
            except GitHubWriteNotSent:
                store.put_cas(key, {k: v for k, v in journal.items() if k != "pr_pending"}, journal)
                return None
            except (OSError, ValueError, TypeError):
                # A lost POST response is reconciled by reads, including closed drafts.
                pull = _existing_pull(github, branch)
        if not isinstance(pull, dict) or _ref_sha(github, base) != base_sha or _ref_sha(github, branch) != commit:
            return None
        url = _verified_pull_url(pull, branch, commit, title, body)
        if journal.get("pr_url") == url:
            return url
        if "pr_url" in journal:
            return None
        saved = {**journal, "pr_url": url}
        return url if store.put_cas(key, saved, journal) or store.get(key) == saved else None
    except (AttributeError, KeyError, OSError, StoreError, TypeError, ValueError):
        return None
