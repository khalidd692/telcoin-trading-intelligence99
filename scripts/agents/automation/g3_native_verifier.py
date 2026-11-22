"""Independent, non-LLM acceptance evidence for TEL99 issue #114.

Run with a pinned candidate checkout. Execute *only* in a trusted CI runner
with Docker; generated code runs in a credential-free, network-disabled,
read-only container. The report is evidence, not an ACCEPTED transition.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

MISSION = "CODEX110-WINDOWS-NATIVE-SHORTPATH"
PROJECT = "agent-core"
COMMIT = "caec35793c9d2e04900c8bb4cf31ce6ca9bdbfe3"
BASE = "982f5e22297694f122d87a1419c12d13a6aa7188"
BRANCH = "agents/codex-local/codex110-windows-native-shortpath"
PREFIX = "docs/agents/codex-local-results/codex110-windows-native-shortpath/"
DIGESTS = {
    "tasks.py": "1e72cf3ab3c9049b735ec9451f6d50191e0af0e9321a14d7e99913cc646bc0f8",
    "README.md": "eb01edaaa004ab93d1d3a945b498fc72d6e3f1eadc8a95893fb2bc8cff6dc51c",
}
IMAGE = "docker.io/library/python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"
REQUIRED = (
    "empty-list", "add", "edit", "complete", "persisted-list", "delete",
    "empty-after-delete", "unknown-id-rejected", "unknown-command-rejected",
)


class Rejected(RuntimeError):
    pass


class NeedsHuman(RuntimeError):
    pass


def verdict(checks, *, reported_llm_passes=()):
    """Three lying LLMs cannot overrule a real red test."""
    del reported_llm_passes
    if not isinstance(checks, list) or not checks:
        return "NEEDS_HUMAN"
    seen = set()
    red = False
    unknown = False
    for item in checks:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            return "REJECTED"
        if item["id"] in seen:
            return "REJECTED"
        seen.add(item["id"])
        if item.get("status") == "FAIL":
            red = True
        elif item.get("status") != "PASS" or item.get("reproducible") is not True:
            unknown = True
    if red:
        return "REJECTED"
    if unknown or seen != set(REQUIRED):
        return "NEEDS_HUMAN"
    return "PASS"


def git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-c", "core.longpaths=true", "-C", str(repo), *args],
        capture_output=True, timeout=30, check=False,
    )
    if result.returncode:
        raise Rejected("Git could not prove the pinned commit and tree")
    return result.stdout


def read_blob(repo: Path, commit: str, path: str) -> bytes:
    listing = git(repo, "ls-tree", "-r", "-z", "--full-tree", commit, "--", path)
    rows = [row for row in listing.split(b"\x00") if row]
    if len(rows) != 1:
        raise Rejected("expected exactly one tree entry")
    meta, tab, name = rows[0].partition(b"\t")
    parts = meta.split()
    if (not tab or name != path.encode("utf-8") or len(parts) != 3
            or parts[1] != b"blob" or re.fullmatch(rb"[0-9a-f]{40,64}", parts[2]) is None):
        raise Rejected("unexpected Git tree entry")
    return git(repo, "cat-file", "blob", parts[2].decode("ascii"))


def verify_pinned_commit(repo: Path):
    current = git(repo, "rev-parse", "HEAD").decode().strip()
    parents = git(repo, "rev-list", "--parents", "-n", "1", COMMIT).decode().split()
    if current != COMMIT or parents != [COMMIT, BASE]:
        raise Rejected("wrong commit or wrong parent")
    changed = git(repo, "diff", "--name-only", BASE, COMMIT).decode().splitlines()
    expected = [PREFIX + name for name in DIGESTS]
    if sorted(changed) != sorted(expected):
        raise Rejected("commit changed files outside approved scope")
    data = {}
    for name, sha in DIGESTS.items():
        raw = read_blob(repo, COMMIT, PREFIX + name)
        if hashlib.sha256(raw).hexdigest() != sha or (repo / (PREFIX + name)).read_bytes() != raw:
            raise Rejected("artifact digest or worktree differs from approved result")
        data[name] = raw
    try:
        ast.parse(data["tasks.py"].decode("utf-8"))
        docs = data["README.md"].decode("utf-8")
    except (UnicodeError, SyntaxError) as exc:
        raise Rejected("source or documentation is invalid") from exc
    if len([line for line in docs.splitlines() if line.startswith("tasks.py --db demo.json ")]) != 5:
        raise Rejected("README does not contain five required examples")
    return data


def docker_checks(candidate: Path, harness: Path):
    cmd = [
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "64", "--memory", "192m", "--cpus", "1",
        "--user", "65534:65534", "--tmpfs", "/tmp:rw,nosuid,nodev,size=16m,mode=1777",
        "--mount", f"type=bind,source={candidate.resolve()},target=/candidate/tasks.py,readonly",
        "--mount", f"type=bind,source={harness.resolve()},target=/harness.py,readonly",
        "--entrypoint", "python", IMAGE, "-B", "/harness.py", "/candidate/tasks.py",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise NeedsHuman("isolated Docker execution unavailable") from exc
    if result.returncode:
        raise Rejected("sandbox acceptance test failed")
    try:
        response = json.loads(result.stdout)
    except ValueError as exc:
        raise Rejected("sandbox evidence is not valid JSON") from exc
    if response.get("ok") is not True or tuple(response.get("checks", ())) != REQUIRED:
        raise Rejected("sandbox did not prove all nine checks")
    return [{"id": name, "status": "PASS", "reproducible": True} for name in REQUIRED]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = {
        "schema_version": 1, "project_id": PROJECT, "mission_id": MISSION,
        "work_branch": BRANCH, "work_commit": COMMIT, "base_sha": BASE,
        "artifact_digests": DIGESTS, "provider_calls": 0,
        "model_used": False, "verdict": "NEEDS_HUMAN", "checks": [],
        "accepted": False,
    }
    try:
        verify_pinned_commit(args.candidate)
        harness = Path(__file__).resolve().with_name("g3_native_harness.py")
        checks = docker_checks(args.candidate / (PREFIX + "tasks.py"), harness)
        report["checks"] = checks
        report["verdict"] = verdict(checks)
    except Rejected as exc:
        report["verdict"] = "REJECTED"
        report["blocker"] = str(exc)
    except NeedsHuman as exc:
        report["blocker"] = str(exc)
    except (OSError, ValueError) as exc:
        report["blocker"] = type(exc).__name__
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"mission_id": MISSION, "sha": COMMIT, "verdict": report["verdict"],
                      "checks": len(report["checks"]), "accepted": False}, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
