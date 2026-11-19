"""Verify an independent GitHub attestation without executing issue commands."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from urllib.parse import quote

MARKER = "tel99-evidence:v1 "
_COMMIT = re.compile(r"[0-9a-f]{40}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_ARTIFACT = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*")
_MAX_ARTIFACT_BYTES = 256 * 1024


def _artifact_path(body: str) -> str | None:
    paths = re.findall(r"^[ \t]*[-*]?[ \t]*acceptance-artifact:[ \t]*([^\s]+)[ \t]*$",
                       body, re.MULTILINE | re.IGNORECASE)
    if len(paths) != 1:
        return None
    path = paths[0]
    if not _ARTIFACT.fullmatch(path) or any(p in (".", "..") for p in path.split("/")):
        return None
    return path


def _attestation(comments, verifiers, conversation_id):
    candidates = []
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        body = comment.get("body")
        user = comment.get("user")
        comment_id = comment.get("id")
        if (not isinstance(body, str) or len(body) > 8192 or not body.startswith(MARKER)
                or not isinstance(user, dict) or not isinstance(user.get("login"), str)
                or user["login"].lower() not in verifiers
                or type(comment_id) is not int or comment_id < 1
                or not comment.get("created_at")
                or comment.get("created_at") != comment.get("updated_at")):
            continue
        try:
            payload = json.loads(body[len(MARKER):])
        except (ValueError, RecursionError):
            continue
        if isinstance(payload, dict) and payload.get("conversation_id") == conversation_id:
            candidates.append((comment_id, user["login"], payload))
    return max(candidates, key=lambda candidate: candidate[0], default=None)


def _map(value):
    return value if isinstance(value, dict) else {}


def _matches(pattern, value):
    return isinstance(value, str) and bool(pattern.fullmatch(value))


def _positive_int(value):
    return type(value) is int and value > 0


def _artifact_matches(blob, path, digest):
    if (blob.get("path") != path or blob.get("type") != "file"
            or blob.get("encoding") != "base64"
            or not _positive_int(blob.get("size")) or blob["size"] > _MAX_ARTIFACT_BYTES):
        return False
    content = blob.get("content")
    if not isinstance(content, str) or len(content) > 2 * _MAX_ARTIFACT_BYTES:
        return False
    try:
        raw = base64.b64decode("".join(content.splitlines()), validate=True)
    except (ValueError, binascii.Error):
        return False
    return len(raw) == blob["size"] and hashlib.sha256(raw).hexdigest() == digest


def verify(*, comments, verifiers, conversation_id, mission_digest, mission_body,
           repository, work_branch, checks, trusted_workflows, fetch) -> tuple[list[dict], dict | None]:
    """Return criterion results plus the verified provenance, when present.

    `fetch` reads paths relative to the mission repository on GitHub. A trusted
    verifier maps each criterion to a job. GitHub supplies the branch commit,
    file bytes and actual job conclusions independently of the comment.
    """
    waiting = [{"id": "independent-evidence", "automatable": False}]

    def rejected(reason):
        return ([{"id": "independent-evidence", "automatable": True, "exit_code": 1,
                  "command": "verify independent GitHub evidence"}], {"reason": reason})

    candidate = _attestation(comments, verifiers, conversation_id)
    if not candidate or not mission_digest:
        return waiting, None
    comment_id, verifier, proof = candidate
    artifact = _artifact_path(mission_body)
    ids = {check["id"] for check in checks}
    if not artifact or not ids or len(ids) != len(checks):
        return waiting, None

    sha, digest = proof.get("sha"), proof.get("artifact_sha256")
    run, attempt = proof.get("run_id"), proof.get("run_attempt")
    job_names = _map(proof.get("jobs"))
    if (proof.get("mission_digest") != mission_digest or proof.get("artifact") != artifact
            or not _matches(_COMMIT, sha) or not _matches(_DIGEST, digest)
            or not _positive_int(run) or not _positive_int(attempt)
            or job_names.keys() != ids
            or not all(isinstance(name, str) and 0 < len(name) <= 255
                       for name in job_names.values())
            or len(set(job_names.values())) != len(job_names)):
        return rejected("attestation does not match the approved mission")

    ref = fetch("git/ref/heads/" + quote(work_branch, safe="/"))
    target = _map(ref.get("object"))
    if (ref.get("ref") != f"refs/heads/{work_branch}" or target.get("type") != "commit"
            or target.get("sha") != sha):
        return rejected("verification commit differs from the mission branch")
    blob = fetch(f"contents/{quote(artifact, safe='/')}?ref={sha}")
    if not _artifact_matches(blob, artifact, digest):
        return rejected("artifact does not match the attested bytes")

    execution = fetch(f"actions/runs/{run}")
    if (execution.get("id") != run or execution.get("run_attempt") != attempt
            or execution.get("head_sha") != sha or execution.get("head_branch") != work_branch
            or execution.get("event") not in ("push", "workflow_dispatch")
            or _map(execution.get("head_repository")).get("full_name") != repository):
        return rejected("workflow execution is not for the attested commit")
    if execution.get("status") != "completed":
        return waiting, None
    workflow_id = execution.get("workflow_id")
    workflow_digest = trusted_workflows.get(str(workflow_id))
    workflow_path = execution.get("path")
    if (not _positive_int(workflow_id) or not _matches(_DIGEST, workflow_digest)
            or not _matches(re.compile(r"\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml"),
                            workflow_path)):
        return rejected("workflow is outside the trusted verification policy")
    workflow = fetch(f"contents/{quote(workflow_path, safe='/')}?ref={sha}")
    if not _artifact_matches(workflow, workflow_path, workflow_digest):
        return rejected("workflow definition differs from the trusted version")

    page = fetch(f"actions/runs/{run}/attempts/{attempt}/jobs?per_page=100")
    jobs = page.get("jobs")
    if not isinstance(jobs, list) or page.get("total_count") != len(jobs):
        return rejected("incomplete workflow job listing")
    checked = []
    job_ids = {}
    for check in checks:
        cid = check["id"]
        matching = [job for job in jobs if isinstance(job, dict)
                    and job.get("name") == job_names[cid]]
        if len(matching) != 1:
            return rejected("missing or ambiguous verification job")
        job = matching[0]
        if (not _positive_int(job.get("id")) or job.get("run_id") != run
                or job.get("run_attempt") != attempt or job.get("head_sha") != sha
                or job.get("status") != "completed"):
            return rejected("verification job does not belong to the attested run")
        job_ids[cid] = job["id"]
        passed = execution.get("conclusion") == job.get("conclusion") == "success"
        checked.append({**check, "exit_code": 0 if passed else 1, "reproducible": True,
                        "output_digest": f"sha256:{digest}"})
    return checked, {"verifier": verifier, "comment_id": comment_id, "commit_sha": sha,
                     "artifact": artifact, "artifact_sha256": digest,
                     "run_id": run, "run_attempt": attempt, "job_ids": job_ids,
                     "workflow_id": workflow_id, "workflow_sha256": workflow_digest}
