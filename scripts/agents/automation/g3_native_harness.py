"""Deterministic offline CLI checks for a toy task manager in a sealed sandbox."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile


EXPECTED = (
    "empty-list", "add", "edit", "complete", "persisted-list", "delete",
    "empty-after-delete", "unknown-id-rejected", "unknown-command-rejected",
)


def run(candidate: str, db: Path, *args: str, ok: bool = True):
    result = subprocess.run(
        [sys.executable, "-B", candidate, "--db", str(db), *args],
        capture_output=True, text=True, timeout=5, check=False,
    )
    if (result.returncode == 0) != ok:
        raise AssertionError(f"{args[0]} returned an unexpected status")
    return json.loads(result.stdout) if ok else None


def verify(candidate: str):
    checks = []
    with tempfile.TemporaryDirectory(prefix="g3-", dir="/tmp") as directory:
        db = Path(directory) / "demo.json"
        if run(candidate, db, "list") != []:
            raise AssertionError("empty database must list []")
        checks.append("empty-list")
        first = run(candidate, db, "add", "Example task")
        if not isinstance(first, dict) or not isinstance(first.get("id"), str) or not first["id"] or first.get("done") is not False:
            raise AssertionError("task creation response malformed")
        uid = first["id"]
        checks.append("add")
        edited = run(candidate, db, "edit", uid, "Revised task")
        if edited.get("title") != "Revised task":
            raise AssertionError("edit not persisted")
        checks.append("edit")
        done = run(candidate, db, "complete", uid)
        if done.get("done") is not True:
            raise AssertionError("task not completed")
        checks.append("complete")
        found = run(candidate, db, "list")
        if len(found) != 1 or found[0].get("id") != uid or found[0].get("done") is not True:
            raise AssertionError("persisted list incorrect")
        checks.append("persisted-list")
        deleted = run(candidate, db, "delete", uid)
        if deleted.get("id") != uid:
            raise AssertionError("deleted different task")
        checks.append("delete")
        if run(candidate, db, "list") != []:
            raise AssertionError("deletion not persisted")
        checks.append("empty-after-delete")
        run(candidate, db, "complete", "no-such-id", ok=False)
        checks.append("unknown-id-rejected")
        run(candidate, db, "nonsense", ok=False)
        checks.append("unknown-command-rejected")
    if tuple(checks) != EXPECTED:
        raise AssertionError("harness did not run every required check")
    return checks


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python g3_native_harness.py /candidate/tasks.py")
    print(json.dumps({"checks": verify(sys.argv[1]), "ok": True}, sort_keys=True))
