"""Read-only G3 reconciliation of an authenticated GitHub Actions bot proof.

No model, no write access, no runner claims. A valid external proof is
evidence for the next authorized supervisor step, NOT the final ACCEPTED state.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import g3_bot_acceptance as acceptance

REPO = "khalidd692/telcoin-trading-intelligence99"
POLICY_PATH = Path(__file__).resolve().parents[3] / "docs/agents/G3_AUTO_TRUST_114.json"
OUT = Path("/tmp/tel99-g3/external-proof.json")


def github(path):
    result = subprocess.run(
        ["gh", "api", f"repos/{REPO}/{path}"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode:
        raise OSError("GitHub proof lookup failed")
    return json.loads(result.stdout)


def main():
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    try:
        comments = github(f"issues/{policy['issue']}/comments?per_page=100")
        if not isinstance(comments, list):
            raise ValueError("comments not a list")
        proof = acceptance.verify(
            policy=policy, comments=comments, repository=REPO, fetch=github,
        )
        result = {
            "schema_version": 1, "project_id": policy["project_id"],
            "mission_id": policy["mission_id"], "subject_sha": policy["commit_sha"],
            "verifier_sha": policy["verifier_sha"], "accepted": False,
            "status": "VERIFIED_EXTERNAL" if proof else "NEEDS_HUMAN",
        }
        if proof:
            result["run_id"] = proof["run_id"]
            result["workflow_id"] = proof["workflow_id"]
            result["checks"] = proof["criteria"]
    except (OSError, KeyError, ValueError, json.JSONDecodeError):
        result = {
            "schema_version": 1, "mission_id": policy["mission_id"],
            "subject_sha": policy["commit_sha"], "accepted": False,
            "status": "NEEDS_HUMAN",
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "VERIFIED_EXTERNAL" else 2


if __name__ == "__main__":
    sys.exit(main())
