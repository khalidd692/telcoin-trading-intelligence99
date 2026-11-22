"""Check a SHA-pinned native proof without executing tool results or editing state."""
from __future__ import annotations

import hashlib
import re

from .native.mission import MissionEngine, MissionSpec, PASS, valid_artifact_name, valid_mission_id
from .project_kit import strict_json

LIMIT = 512 * 1024
ARTIFACT_LIMIT = 2 * 1024 * 1024


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def verify(kit, mission_id, expected_journal_sha):
    if not isinstance(mission_id, str) or not valid_mission_id(mission_id):
        raise ValueError("invalid mission identifier")
    if not _sha(expected_journal_sha):
        raise ValueError("invalid journal SHA-256")
    project = kit.profile["project"]
    spec = MissionSpec(mission_id=mission_id, prompt="", project=project)
    engine = MissionEngine(provider=None, store_root=kit.state, workspace_root=kit.artifacts,
                           memory_root=kit.memory, quota_remaining=None)
    directory = engine.artifact_directory(spec)
    journal = directory / "journal.json"
    if (directory.resolve() != directory or journal.is_symlink() or not journal.is_file()):
        raise ValueError("journal is missing or linked")
    with journal.open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT or hashlib.sha256(raw).hexdigest() != expected_journal_sha:
        raise ValueError("journal hash or size does not match")
    data = strict_json(raw)
    if (not isinstance(data, dict) or data.get("project") != project
            or data.get("mission_id") != mission_id or data.get("verdict") != PASS
            or not _sha(data.get("contract_sha256"))):
        raise ValueError("journal does not record a successful mission for this project")

    checks, digests = data.get("checks"), data.get("artifact_digests")
    if (not isinstance(checks, list) or not checks
            or any(not isinstance(check, dict) or check.get("ok") is not True for check in checks)):
        raise ValueError("journal lacks passing checks")
    if not isinstance(digests, dict) or not 1 <= len(digests) <= 32:
        raise ValueError("journal lacks bounded artifact digests")
    files = data.get("artifacts")
    if (not isinstance(files, list) or len(files) != len(digests)
            or any(not isinstance(name, str) or name not in digests for name in files)
            or len(set(files)) != len(files)):
        raise ValueError("journal artifact list does not match its digests")
    for name, digest in digests.items():
        if not valid_artifact_name(name) or not _sha(digest):
            raise ValueError("invalid artifact identity or digest")
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > ARTIFACT_LIMIT:
            raise ValueError("artifact is missing, linked or oversized")
    if not engine.artifacts_match(spec, digests):
        raise ValueError("artifact hash does not match the pinned journal")
    return {"status": "VERIFIED_ARTIFACTS", "project": project, "mission_id": mission_id,
            "journal_sha256": expected_journal_sha, "checked_artifacts": len(digests),
            "recorded_checks": len(checks)}
