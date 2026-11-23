"""Read a GitHub local-code campaign ledger and write a private measurement report."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from scripts.agents.automation import compare_local_code as evidence, local_team
from scripts.agents.automation.autonomy_runtime import Blocked, fingerprint, local_codegen, validate_contract
from scripts.agents.automation.github_local_code_campaign import CONFIG_KEY, REPO, TRANSPORT
from scripts.agents.intelligence.memory import _write_new_private


def _read(state, key):
    name = f"ledger/{key}.json"
    return evidence._object(evidence._read(state, name), name)


def _measure(state, binding, task, checkpoint):
    mid = task["id"]
    claim = _read(state, f"kilo-claims/{mid}")
    observation = evidence._observe_checkpoint(state, task, local_codegen._source(task), checkpoint, claim)
    proof = checkpoint.get("verification") or {}
    tools = []
    if any(attempt["generation_seconds"] is not None for attempt in observation["attempts"]):
        tools.append("ollama-native" if task.get("port") == 11434 else "llama.cpp")
    if proof.get("verifier") == local_codegen.VERIFIER:
        tools.append("docker-independent-verifier")
    handoff = None
    if local_team.enabled(task) and observation["accepted"]:
        receipt = checkpoint["result"]
        if not local_team.valid_trace(task, receipt):
            raise ValueError("inconsistent verified team handoff")
        analyst = receipt["agent_trace"]["analyst"]
        if proof.get("verification_role", {}).get("analyst_sha256") != analyst["sha256"]:
            raise ValueError("independent verifier did not bind the team handoff")
        handoff = {"from": local_team.TEAM[0], "to": local_team.TEAM[1],
                   "model": analyst["model"], "sha256": analyst["sha256"]}
    attempts = observation["attempts"]
    for attempt in attempts:
        attempt.pop("reason")
        if attempt["failed_checks"]:
            attempt["outcome"] = "INDEPENDENT_CHECK_FAILED"
        elif attempt["accepted"]:
            attempt["outcome"] = "INDEPENDENT_CHECKS_PASSED"
        else:
            attempt["outcome"] = "EVIDENCE_UNAVAILABLE"
    return {
        "id": mid, "issue": binding["issue"], "approval_comment": binding["comment_id"],
        "contract_sha256": binding["contract_sha256"], "objective_sha256": evidence._sha(task["objective"]),
        "base_sha": task["base_sha"], "path": task["path"], "function": task["function"],
        "test_sha256": evidence._sha(task["test"]), "dependencies": task["dependencies"],
        "max_attempts": task.get("max_attempts", 1), "model": task["model"],
        "status": observation["status"], "model_outcome_attributable": bool(
            attempts and attempts[-1]["attributed_model_outcome"]),
        "observed_at": observation["observed_at"],
        "claim_to_terminal_seconds": observation["claim_to_terminal_seconds"],
        "handoff": handoff, "tools": tools, "attempts": attempts,
    }


def export(state, mandate_sha256, output):
    """Archive measurements from a finished campaign without modifying its CAS."""
    state = Path(state).resolve(strict=True)
    output = Path(output)
    if output.resolve().is_relative_to(state):
        raise ValueError("write the learning report outside the campaign ledger")
    config = _read(state, CONFIG_KEY)
    if (not re.fullmatch(r"[0-9a-f]{64}", mandate_sha256)
            or config.get("mandate_sha256") != mandate_sha256 or config.get("repo") != REPO
            or config.get("profile") != TRANSPORT or config.get("campaign") is not True
            or any(type(config.get(field)) is not int or config[field] <= 0
                   for field in ("issue", "mandate_id"))):
        raise ValueError("local campaign does not match the pinned GitHub mandate")
    suffix = "ledger/kilo-github/approvals"
    directory = state / suffix
    if directory.resolve() != directory or not directory.is_dir():
        raise ValueError("local campaign approvals unavailable")
    with os.scandir(directory) as files:
        names = []
        for entry in files:
            if re.fullmatch(r"[A-Za-z0-9-]{1,48}\.json", entry.name):
                names.append(entry.name[:-5])
                if len(names) > 2:
                    raise ValueError("unexpected number of local campaign approvals")
    if not names:
        raise ValueError("no local campaign approvals")
    rows, pending = [], []
    for mid in sorted(names):
        binding = _read(state, f"kilo-github/approvals/{mid}")
        task = binding.get("mission")
        if (not isinstance(task, dict) or task.get("id") != mid or task.get("owner") != "local"
                or "routing" in task or binding.get("base_sha") != task.get("base_sha")
                or binding.get("contract_sha256") != fingerprint(task)
                or type(binding.get("issue")) is not int or binding["issue"] <= config["issue"]
                or type(binding.get("comment_id")) is not int or binding["comment_id"] <= 0):
            raise ValueError("inconsistent local campaign approval")
        validate_contract(task, {mid: binding["contract_sha256"]})
        key = f"kilo-local/{mid}"
        checkpoint_file = state / f"ledger/{key}.json"
        if not (checkpoint_file.exists() or checkpoint_file.is_symlink()):
            pending.append({"id": mid, "issue": binding["issue"], "status": "WAITING"})
            continue
        checkpoint = _read(state, key)
        status = checkpoint.get("status")
        if (checkpoint.get("id"), checkpoint.get("contract_sha256")) != (mid, binding["contract_sha256"]):
            raise ValueError("checkpoint differs from approved mission")
        if status in ("ACK", "RUNNING", "WORKER_EXITED"):
            pending.append({"id": mid, "issue": binding["issue"], "checkpoint": status})
            continue
        rows.append(_measure(state, binding, task, checkpoint))
    failed_checks = {}
    for row in rows:
        for attempt in row["attempts"]:
            for name in attempt["failed_checks"]:
                failed_checks[name] = failed_checks.get(name, 0) + 1
    report = {
        "schema_version": 1, "kind": "tel99-github-campaign-measurements",
        "repository": REPO, "controller_issue": config["issue"], "mandate_comment": config["mandate_id"],
        "mandate_sha256": mandate_sha256, "missions": rows, "pending": pending,
        "summary": {"missions": len(rows), "pending": len(pending), "accepted": sum(row["status"] == "ACCEPTED" for row in rows),
                    "model_outcomes_attributable": sum(row["model_outcome_attributable"] for row in rows),
                    "failed_checks": failed_checks},
    }
    _write_new_private(output, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--mandate-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = export(args.state, args.mandate_sha256, args.output)
    except (Blocked, OSError, ValueError, KeyError, TypeError, SyntaxError, RecursionError) as exc:
        parser.exit(2, f"Campaign measurements refused: {exc}\n")
    print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
