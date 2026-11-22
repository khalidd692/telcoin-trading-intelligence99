"""Install and use a local project profile without starting a runtime."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re

from .intelligence import capabilities, catalog
from .intelligence.memory import MemoryStore
from .native.mission import MissionError, validate_project
from .team_config import role_catalog

LIMIT = 65536


def strict_json(raw):
    def unique(pairs):
        obj = dict(pairs)
        if len(obj) != len(pairs):
            raise ValueError("duplicate configuration key")
        return obj

    def invalid_constant(_value):
        raise ValueError("non-finite JSON value")

    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)


def read_json(path, *, limit=LIMIT):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("input exceeds the byte limit")
    return strict_json(raw)


def _names(data, field, allowed, *, required=True):
    rows = data[field]
    if (not isinstance(rows, list) or (required and not rows)
            or any(not isinstance(row, str) or row not in allowed for row in rows)
            or len(set(rows)) != len(rows)):
        raise ValueError(f"invalid allowlist: {field}")


def _validate(data):
    fields = {"schema_version", "project", "repository", "roles", "skills", "approved_models"}
    if (not isinstance(data, dict) or data.keys() != fields
            or type(data["schema_version"]) is not int or data["schema_version"] != 1):
        raise ValueError("unknown project profile fields or version")
    try:
        validate_project(data["project"])
    except MissionError as exc:
        raise ValueError("invalid project identifier") from exc
    repo = data["repository"]
    if not isinstance(repo, str) or not re.fullmatch(
            r"[A-Za-z0-9-]{1,39}/[A-Za-z0-9_.-]{1,100}", repo):
        raise ValueError("invalid repository identifier")
    _names(data, "roles", role_catalog())
    _names(data, "skills", {capabilities.PLAN_SKILL}, required=False)
    _names(data, "approved_models", {spec.id for spec in catalog.free_models()})


@dataclass(frozen=True)
class ProjectKit:
    root: Path
    profile: dict

    @property
    def state(self):
        return self.root / "state"

    @property
    def memory(self):
        return self.root / "memory"

    @property
    def artifacts(self):
        return self.root / "artifacts"


def load(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("invalid project kit directory")
    root = root.resolve()
    profile = root / "project.json"
    if profile.is_symlink() or not profile.is_file():
        raise ValueError("invalid project.json")
    data = read_json(profile)
    _validate(data)
    kit = ProjectKit(root, data)
    for path in (kit.state, kit.memory, kit.artifacts):
        if path.is_symlink() or not path.is_dir():
            raise ValueError(f"invalid kit directory: {path.name}")
    return kit


def install(root, profile):
    _validate(profile)
    root = Path(root)
    root.mkdir(mode=0o700)
    kit = ProjectKit(root, profile)
    for path in (kit.state, kit.memory, kit.artifacts):
        path.mkdir(mode=0o700)
    target = root / "project.json"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(profile, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    return load(root)


def prepare(kit, contract):
    if not isinstance(contract, dict) or contract.get("project") != kit.profile["project"]:
        raise ValueError("contract belongs to another project")
    steps = contract.get("steps")
    if not isinstance(steps, list):
        raise ValueError("missing role steps")
    for step in steps:
        if not isinstance(step, dict) or step.get("role") not in kit.profile["roles"]:
            raise ValueError("role is outside the project profile")
        skills = step.get("skills", [])
        if not isinstance(skills, list) or any(skill not in kit.profile["skills"] for skill in skills):
            raise ValueError("skill is outside the project profile")
    models = contract.get("approved_models")
    if not isinstance(models, list) or any(mid not in kit.profile["approved_models"] for mid in models):
        raise ValueError("model is outside the project profile")
    return capabilities.plan(contract, memory_store=MemoryStore(kit.memory))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "status", "plan", "verify"):
        child = commands.add_parser(command)
        child.add_argument("--directory", type=Path, required=True)
        if command == "init":
            child.add_argument("--profile", type=Path, required=True)
        elif command == "plan":
            child.add_argument("--contract", type=Path, required=True)
        elif command == "verify":
            child.add_argument("--mission-id", required=True)
            child.add_argument("--journal-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            kit = install(args.directory, read_json(args.profile))
        else:
            kit = load(args.directory)
        if args.command == "plan":
            report = prepare(kit, read_json(args.contract))
        elif args.command == "verify":
            from .platform_evidence import verify

            report = verify(kit, args.mission_id, args.journal_sha256)
        else:
            report = {"status": "READY", "project": kit.profile["project"],
                      "repository": kit.profile["repository"], "state": str(kit.state),
                      "memory": str(kit.memory), "artifacts": str(kit.artifacts)}
    except (OSError, ValueError, RecursionError) as exc:
        print(json.dumps({"status": "INVALID", "error": str(exc)}))
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 3 if report["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
