"""Read-only acceptance of an authenticated, SHA-pinned GitHub Actions bot proof.

This is a SECOND explicit trust mode, never a fallback that weakens the
original acceptance.verify() contract. The policy must be pinned by an
authorized reviewer for each mission. No model is used or invoked.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from urllib.parse import quote

MARKER = "tel99-g3-bot-proof:v1 "
SHA40 = re.compile(r"[0-9a-f]{40}")
SHA64 = re.compile(r"[0-9a-f]{64}")
BOT = "github-actions[bot]"
CHECK_JOB = "Independent native code check (SHA pinned)"
ATTEST_JOB = "G3 authenticated bot evidence"
MAX_SIZE = 256 * 1024
TRUSTED_PATHS = {
    ".github/workflows/tel99-g3-independent-native.yml",
    "scripts/agents/automation/g3_native_verifier.py",
    "scripts/agents/automation/g3_native_harness.py",
    "tests/test_g3_native_verifier.py",
}


def sha40(value):
    return isinstance(value, str) and SHA40.fullmatch(value) is not None


def sha64(value):
    return isinstance(value, str) and SHA64.fullmatch(value) is not None


def content_matches(blob, path, digest):
    if not (isinstance(blob, dict) and blob.get("path") == path
            and blob.get("type") == "file" and blob.get("encoding") == "base64"
            and type(blob.get("size")) is int and 0 < blob["size"] <= MAX_SIZE):
        return False
    content = blob.get("content")
    if not isinstance(content, str) or len(content) > 2 * MAX_SIZE:
        return False
    try:
        raw = base64.b64decode("".join(content.splitlines()), validate=True)
    except (ValueError, binascii.Error):
        return False
    return len(raw) == blob["size"] and hashlib.sha256(raw).hexdigest() == digest


def verify(*, policy, comments, repository, fetch):
    """Check GitHub facts independently; return proof or None (fail closed).

    The fetch callback reads trusted GitHub REST JSON. This never executes a
    command from an issue or comment and never marks a mission ACCEPTED.
    """
    if not isinstance(policy, dict) or not isinstance(comments, list):
        return None
    issue = policy.get("issue")
    branch = policy.get("work_branch")
    sha = policy.get("commit_sha")
    base = policy.get("base_sha")
    verifier_branch = policy.get("verifier_branch")
    verifier_sha = policy.get("verifier_sha")
    workflow_id = policy.get("workflow_id")
    blobs = policy.get("trusted_blobs")
    files = policy.get("artifact_digests")
    checks = policy.get("criteria")
    if (type(issue) is not int or issue < 1
            or not all(isinstance(x, str) and x for x in (
                policy.get("project_id"), policy.get("mission_id"), branch, verifier_branch))
            or not sha40(sha) or not sha40(base) or not sha40(verifier_sha)
            or type(workflow_id) is not int or workflow_id <= 0
            or not isinstance(blobs, dict) or set(blobs) != TRUSTED_PATHS
            or not all(sha40(v) for v in blobs.values())
            or not isinstance(files, dict) or set(files) != {"tasks.py", "README.md"}
            or not all(sha64(x) for x in files.values())
            or not isinstance(checks, list) or len(checks) != 9
            or len(set(checks)) != len(checks)
            or not all(isinstance(x, str) and x for x in checks)):
        return None

    candidates = []
    for comment in comments:
        if not isinstance(comment, dict) or not isinstance(comment.get("body"), str):
            continue
        body = comment["body"]
        actor = comment.get("user")
        if (len(body) > 8192 or not body.startswith(MARKER)
                or not isinstance(actor, dict) or actor.get("login") != BOT
                or type(comment.get("id")) is not int or comment["id"] < 1
                or not comment.get("created_at")
                or comment["created_at"] != comment.get("updated_at")):
            continue
        try:
            proof = json.loads(body[len(MARKER):])
        except (ValueError, RecursionError):
            continue
        if isinstance(proof, dict) and proof.get("mission_id") == policy["mission_id"]:
            candidates.append((comment["id"], proof))
    if not candidates:
        return None
    _, proof = max(candidates)
    if (
        proof.get("version") != 1
        or proof.get("project_id") != policy["project_id"]
        or proof.get("mission_id") != policy["mission_id"]
        or proof.get("issue") != issue
        or proof.get("candidate_branch") != branch
        or proof.get("candidate_sha") != sha
        or proof.get("candidate_digests") != files
        or proof.get("verifier_branch") != verifier_branch
        or proof.get("verifier_sha") != verifier_sha
        or proof.get("check_job") != CHECK_JOB
        or proof.get("checks") != checks
        or proof.get("verdict") != "PASS"
        or proof.get("accepted") is not False
        or type(proof.get("run_id")) is not int or proof["run_id"] <= 0
        or type(proof.get("run_attempt")) is not int or proof["run_attempt"] <= 0
    ):
        return None

    def get(path):
        try:
            value = fetch(path)
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, KeyError):
            return {}

    ref = get("git/ref/heads/" + quote(branch, safe="/"))
    subject = ref.get("object") or {}
    if (ref.get("ref") != "refs/heads/" + branch
            or subject.get("type") != "commit" or subject.get("sha") != sha):
        return None
    commit = get("commits/" + sha)
    if (commit.get("sha") != sha or not isinstance(commit.get("parents"), list)
            or [p.get("sha") for p in commit["parents"]] != [base]):
        return None
    prefix = "docs/agents/codex-local-results/" + policy["mission_id"].lower() + "/"
    for name, digest in files.items():
        path = prefix + name
        if not content_matches(get("contents/" + quote(path, safe="/") + "?ref=" + sha),
                               path, digest):
            return None

    # Immutable verifier tree is pinned separately from candidate source.
    for path, pinned_git_blob in blobs.items():
        item = get("contents/" + quote(path, safe="/") + "?ref=" + verifier_sha)
        if (item.get("path") != path or item.get("type") != "file"
                or item.get("sha") != pinned_git_blob):
            return None

    run_id, attempt = proof["run_id"], proof["run_attempt"]
    run = get(f"actions/runs/{run_id}")
    if (run.get("id") != run_id or run.get("run_attempt") != attempt
            or run.get("event") != "push"
            or run.get("head_sha") != verifier_sha
            or run.get("head_branch") != verifier_branch
            or (run.get("head_repository") or {}).get("full_name") != repository
            or run.get("workflow_id") != workflow_id
            or run.get("path") not in blobs
            or run.get("status") != "completed" or run.get("conclusion") != "success"):
        return None
    jobs_page = get(f"actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100")
    jobs = jobs_page.get("jobs")
    if not isinstance(jobs, list) or jobs_page.get("total_count") != len(jobs):
        return None
    found = {}
    for name in (CHECK_JOB, ATTEST_JOB):
        matching = [j for j in jobs if isinstance(j, dict) and j.get("name") == name]
        if len(matching) != 1:
            return None
        job = matching[0]
        if (type(job.get("id")) is not int or job["id"] < 1
                or job.get("run_id") != run_id or job.get("run_attempt") != attempt
                or job.get("head_sha") != verifier_sha
                or job.get("status") != "completed" or job.get("conclusion") != "success"):
            return None
        found[name] = job["id"]
    return {
        "project_id": policy["project_id"], "mission_id": policy["mission_id"],
        "commit_sha": sha, "base_sha": base, "artifact_digests": files,
        "verifier": BOT, "verifier_sha": verifier_sha,
        "workflow_id": workflow_id, "run_id": run_id, "run_attempt": attempt,
        "job_ids": found, "criteria": checks, "status": "VERIFIED_EXTERNAL",
    }
