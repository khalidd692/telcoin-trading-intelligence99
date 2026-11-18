"""Pinned #110 native worker contract for approved synthetic Windows tickets."""

import hashlib
import json
import re
import sys

NATIVE_REF = "codex/native-kilo-free-20261118"
NATIVE_SHA = "982f5e22297694f122d87a1419c12d13a6aa7188"
IMAGE = "docker.io/library/python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"
OBJECTIVE = (
    "Créer un gestionnaire de tâches jouet. Dans README.md, donner cinq exemples fictifs "
    "avec tasks.py --db demo.json en texte simple, sans blocs Markdown imbriqués."
)
FILES = ("README.md", "tasks.py")


def native_scope(mission):
    return (
        re.fullmatch(r"CODEX110-[A-Z0-9-]+", mission["id"])
        and mission.get("base_sha") == NATIVE_SHA
        and mission.get("objective") == OBJECTIVE
        and mission.get("synthetic_data") is True
        and type(mission.get("call_budget")) is int and mission["call_budget"] == 1
    )


def native_digest(mission):
    scope = {key: mission[key] for key in (
        "id", "issue", "role", "assignee", "base_sha", "objective", "priority",
        "dependencies", "expires_at", "synthetic_data", "call_budget",
    )}
    scope["dependency_evidence"] = mission.get("dependency_evidence", {})
    return hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()


def args_for(workspace, issue, command):
    argv = [sys.executable, "-B", "-m", "scripts.agents.native.cli",
            "--state", str(workspace / "_native_state"),
            "--memory", str(workspace / "_native_memory")]
    if command == "run":
        # Engine quota bookkeeping, with exactly one permitted POST and zero repairs.
        argv += ["--quota", "12"]
    argv += [command, "--project", "tel99-windows", "--mission-id", f"github-{issue}"]
    if command == "run":
        argv += ["--synthetic-data", "--profile", "tasks", "--sandbox-image", IMAGE,
                 "--max-repairs", "0", "--mission", OBJECTIVE]
    return argv
