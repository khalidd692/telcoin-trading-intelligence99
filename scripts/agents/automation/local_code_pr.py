"""Publish one independently verified local Python function to an isolated draft PR.

Reuses GitHub primitives and CAS journal from the existing synthetic publisher,
but requires the *different*, stronger local Docker code evidence. Never merges.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

from scripts.agents.automation import local_codegen, local_team
from scripts.agents.automation.autonomy_runtime import fingerprint, validate_contract
from scripts.agents.automation.github_mission_source import GitHubWriteNotSent, fenced_json, is_owner
from scripts.agents.automation.kilo_acceptance_pr import _ref_sha, _existing_pull, _digest
from protocol.store import StoreError

REPO = "khalidd692/telcoin-trading-intelligence99"
BASE_REF = "agents/tel99-code-pilot-base-20261123"
BASE_SHA = "934d9fd8a3fd498c6e3e69226007dd46276aa6da"
EVENT = "kilo-relay-event/v1"
REQUIRED = {"bounded-model-receipt", "approved-function-diff", "baseline-fails", "candidate-passes"}


def valid_campaign_base(ref, sha):
    return (_digest(sha, 40) and isinstance(ref, str)
            and ((ref, sha) == (BASE_REF, BASE_SHA)
                 or re.fullmatch(r"agents/tel99-code-base-[a-z0-9][a-z0-9-]{0,62}", ref) is not None))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_local_verified(store, root, issue, state, base, base_sha):
    mid = state.get("id")
    binding = store.get(f"kilo-github/approvals/{mid}") or {}
    mission = binding.get("mission")
    config = store.get("github-local-code/config") or {}
    if (not isinstance(mid, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,48}", mid)
            or state.get("status") != "ACCEPTED" or state.get("execution_status") != "COMPLETED"
            or store.get(f"kilo-local/{mid}") != state
            or config.get("profile") != "github-local-code" or config.get("campaign") is not True
            or config.get("repo") != REPO or type(config.get("issue")) is not int
            or not config["issue"] < issue
            or not isinstance(mission, dict) or mission.get("id") != mid
            or mission.get("owner") != "local" or mission.get("team") != local_team.TEAM
            or mission.get("base_sha") != base_sha
            or (base, base_sha) != (config.get("base_ref", BASE_REF), config.get("base_sha", BASE_SHA))
            or binding.get("issue") != issue or binding.get("base") != base
            or binding.get("base_sha") != base_sha
            or binding.get("contract_sha256") != fingerprint(mission)
            or state.get("contract_sha256") != fingerprint(mission)):
        raise ValueError("checkpoint does not match the signed local-code GitHub campaign")
    validate_contract(mission, {mid: fingerprint(mission)})
    result = state.get("result") or {}
    verification = state.get("verification") or {}
    verdict = state.get("verdict") or {}
    artifact = result.get("artifact")
    if (not isinstance(artifact, str) or not artifact.strip() or len(artifact.encode("utf-8")) > 16_000
            or result.get("sha256") != _sha(artifact.encode("utf-8"))
            or result.get("model") != mission.get("model")
            or result.get("provider") != local_codegen.PROVIDER
            or result.get("specialist_id") != "tel99-dev"
            or not local_team.valid_trace(mission, result)
            or verdict.get("validated") is not True or verification.get("ok") is not True
            or verification.get("verifier") != local_codegen.VERIFIER
            or verification.get("verification_role", {}).get("role") != "tel99-verifier"
            or verification.get("verification_role", {}).get("analyst_sha256") !=
               result["agent_trace"]["analyst"]["sha256"]
            or verification.get("model") != mission.get("model")
            or verification.get("artifact_sha256") != result["sha256"]
            or verification.get("test_sha256") != _sha(mission["test"].encode("utf-8"))
            or any(verification.get(k) != mission[k] for k in
                   ("base_sha", "path", "function", "sandbox_image"))):
        raise ValueError("worker role receipts or Docker verifier evidence are missing")
    checks = verification.get("checks")
    if (not isinstance(checks, list) or len(checks) != 4
            or {row.get("name") for row in checks if isinstance(row, dict)} != REQUIRED
            or any(not isinstance(row, dict) or row.get("ok") is not True for row in checks)
            or next(row for row in checks if row["name"] == "baseline-fails").get("exit_code") != 1
            or next(row for row in checks if row["name"] == "candidate-passes").get("exit_code") != 0):
        raise ValueError("Docker baseline-red / candidate-green evidence is incomplete")

    source = local_codegen._source(mission)
    candidate = local_codegen.replace_function(source, mission["function"], artifact)
    root = Path(root).resolve(strict=True)
    proof = root / "verified-code" / mid
    path = mission["path"]
    target = proof / path
    diff = proof / "change.diff"
    if (not target.is_file() or not diff.is_file()
            or target.resolve(strict=True) != target or diff.resolve(strict=True) != diff):
        raise ValueError("independent Docker-approved materialization is missing")
    raw = target.read_bytes()
    diff_bytes = diff.read_bytes()
    if (len(raw) > 120_000 or len(diff_bytes) > 256_000
            or raw != candidate.encode("utf-8")
            or _sha(source.encode("utf-8")) != verification.get("base_file_sha256")
            or _sha(raw) != verification.get("candidate_sha256")
            or _sha(diff_bytes) != verification.get("diff_sha256")):
        raise ValueError("approved source, candidate or diff changed after verification")
    blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False).hexdigest()
    return mission, raw.decode("utf-8"), blob


def _confirm_github_evidence(github, store, issue, state, evidence_url):
    mid = state["id"]
    record = store.get(f"kilo-github/outbox/{mid}/EVIDENCE") or {}
    event = record.get("event")
    prefix = f"https://github.com/{REPO}/issues/{issue}#issuecomment-"
    if (record.get("url") != evidence_url or not isinstance(evidence_url, str)
            or not evidence_url.startswith(prefix)
            or not re.fullmatch(r"[1-9][0-9]{0,19}", evidence_url.removeprefix(prefix))
            or not isinstance(event, dict) or event.get("event") != EVENT
            or event.get("phase") != "EVIDENCE" or event.get("issue") != issue
            or event.get("mission_id") != mid
            or event.get("scope") != "approved-python-function"
            or event.get("status") != "ACCEPTED"
            or event.get("contract_sha256") != state.get("contract_sha256")
            or event.get("artifact_sha256") != state["result"]["sha256"]
            or event.get("verification_sha256") != fingerprint(state["verification"])):
        raise ValueError("unverified GitHub evidence event")
    cid = int(evidence_url.removeprefix(prefix))
    row = github(f"issues/comments/{cid}")
    if (not isinstance(row, dict) or row.get("id") != cid or not is_owner(row.get("user"))
            or row.get("html_url") != evidence_url
            or row.get("issue_url") != f"https://api.github.com/repos/{REPO}/issues/{issue}"
            or row.get("created_at") != row.get("updated_at")
            or fenced_json(row.get("body"), EVENT) != event):
        raise ValueError("the GitHub evidence comment is not owner-authenticated")


def _verify_code_diff(github, base_sha, commit, path, blob):
    comparison = github(f"compare/{base_sha}...{commit}")
    rows = comparison.get("files") if isinstance(comparison, dict) else None
    commits = comparison.get("commits") if isinstance(comparison, dict) else None
    if (comparison.get("status") != "ahead" or comparison.get("ahead_by") != 1
            or comparison.get("behind_by") != 0 or comparison.get("total_commits") != 1
            or not isinstance(rows, list) or len(rows) != 1
            or not isinstance(commits, list) or len(commits) != 1
            or commits[0].get("sha") != commit
            or (rows[0].get("filename"), rows[0].get("status"), rows[0].get("sha"))
            != (path, "modified", blob)):
        raise ValueError("draft PR diff is not exactly one approved source-file modification")


def _create_code_commit(github, base_sha, path, artifact, blob):
    baseline = github(f"git/commits/{base_sha}")
    tree = (baseline.get("tree") or {}).get("sha")
    if baseline.get("sha") != base_sha or not _digest(tree, 40):
        raise ValueError("pinned base commit tree not available")
    remote_blob = github("git/blobs", method="POST", payload={
        "content": artifact, "encoding": "utf-8",
    })
    if remote_blob.get("sha") != blob:
        raise ValueError("GitHub returned an unexpected code blob SHA")
    created_tree = github("git/trees", method="POST", payload={
        "base_tree": tree,
        "tree": [{"path": path, "mode": "100644", "type": "blob", "sha": blob}],
    }).get("sha")
    if not _digest(created_tree, 40):
        raise ValueError("GitHub code tree could not be verified")
    commit = github("git/commits", method="POST", payload={
        "message": f"fix(tel99): independently verified code for {path}",
        "tree": created_tree, "parents": [base_sha],
    }).get("sha")
    if not _digest(commit, 40):
        raise ValueError("GitHub code commit could not be verified")
    _verify_code_diff(github, base_sha, commit, path, blob)
    return commit


def _verify_existing_pr(pr, *, branch, commit, title, body, base, base_sha):
    number = pr.get("number") if isinstance(pr, dict) else None
    if (type(number) is not int or number < 1 or not is_owner(pr.get("user"))
            or pr.get("draft") is not True or pr.get("merged_at") is not None
            or pr.get("state") != "open" or pr.get("title") != title or pr.get("body") != body):
        raise ValueError("draft PR does not have approved immutable metadata")
    for side, ref, sha in (("base", base, base_sha), ("head", branch, commit)):
        actual = pr.get(side) or {}
        if (actual.get("ref"), actual.get("sha"),
                (actual.get("repo") or {}).get("full_name")) != (ref, sha, REPO):
            raise ValueError("PR head, base or commit changed")
    url = f"https://github.com/{REPO}/pull/{number}"
    if pr.get("html_url") != url:
        raise ValueError("unexpected published PR URL")
    return url


def publish_verified_code_pr(repo, issue, base, base_sha, state, evidence_url, *,
                             api, store, root) -> str | None:
    """Publish and reconcile a single draft; return None on uncertainty, never merge."""
    if (repo != REPO or not valid_campaign_base(base, base_sha)
            or type(issue) is not int or issue <= 167):
        return None

    def github(endpoint, *, method="GET", payload=None):
        return api(f"repos/{REPO}/{endpoint}", method=method, payload=payload)

    try:
        mission, artifact, blob = _read_local_verified(
            store, root, issue, state, base, base_sha
        )
        _confirm_github_evidence(github, store, issue, state, evidence_url)
        if _ref_sha(github, base) != base_sha:
            return None
        mid = mission["id"]
        path = mission["path"]
        branch = f"agents/tel99-code/{issue}-{mid}-{fingerprint(mission)[:10]}"
        key = f"github-local-code/PR/{issue}/{mid}"
        intent = {
            "branch": branch, "base": base, "base_sha": base_sha,
            "contract_sha256": fingerprint(mission), "path": path,
            "blob_sha": blob, "evidence_url": evidence_url,
        }
        existing = store.get(key)
        journal = existing if existing is not None else {"intent": intent}
        if not isinstance(journal, dict) or journal.get("intent") != intent:
            return None
        commit = journal.get("commit_sha")
        head = _ref_sha(github, branch)
        pull = _existing_pull(github, branch)
        if head is not None and head != commit:
            return None
        if existing is None and not store.put_cas(key, journal, None):
            return None
        if commit is None:
            commit = _create_code_commit(github, base_sha, path, artifact, blob)
            updated = {**journal, "commit_sha": commit}
            if not store.put_cas(key, updated, journal):
                return None
            journal = updated
        else:
            if not _digest(commit, 40):
                return None
            _verify_code_diff(github, base_sha, commit, path, blob)

        if head is None:
            if journal.get("pr_pending") or _ref_sha(github, base) != base_sha:
                return None
            try:
                github("git/refs", method="POST", payload={
                    "ref": f"refs/heads/{branch}", "sha": commit,
                })
            except (OSError, ValueError, TypeError):
                pass  # Reconcile uncertain branch creation by a read, never assume success.
            if _ref_sha(github, branch) != commit:
                return None

        title = f"TEL99 verified Python fix for #{issue} ({mid})"
        body = "\n".join((
            f"Refs #{issue}", "", f"Independent Docker verification: {evidence_url}",
            f"Contract SHA-256: \u0060{fingerprint(mission)}\u0060",
            f"Artifact SHA-256: \u0060{state['verification']['candidate_sha256']}\u0060",
            f"Function: \u0060{mission['function']}\u0060",
            "Roles: tel99-analyst -> tel99-dev -> tel99-verifier (Docker)",
            "No auto-merge, deployment or trading.",
        ))
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
                    "title": title, "body": body, "head": branch,
                    "base": base, "draft": True,
                })
            except GitHubWriteNotSent:
                store.put_cas(key, {k: v for k, v in journal.items() if k != "pr_pending"}, journal)
                return None
            except (OSError, ValueError, TypeError):
                pull = _existing_pull(github, branch)
        if (not isinstance(pull, dict) or _ref_sha(github, base) != base_sha
                or _ref_sha(github, branch) != commit):
            return None
        url = _verify_existing_pr(
            pull, branch=branch, commit=commit,
            title=title, body=body, base=base, base_sha=base_sha,
        )
        if journal.get("pr_url") == url:
            return url
        if "pr_url" in journal:
            return None
        saved = {**journal, "pr_url": url}
        return url if store.put_cas(key, saved, journal) or store.get(key) == saved else None
    except (AttributeError, KeyError, OSError, TypeError, ValueError, StoreError):
        return None
