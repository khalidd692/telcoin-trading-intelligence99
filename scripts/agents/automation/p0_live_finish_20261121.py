"""Read-only audit of the historical A/B/C Hermes recipe (#138).

This replaces the retired "live finish" runner. In particular, it cannot
start Hermes, invoke the relay, claim/replay a mission, publish to GitHub, or
rewrite a terminal verdict. The approved C mission required *separate* state;
C was in fact executed inside the A/B state and remains REJECTED. A later
model allowlist fix does not retroactively authorise or accept C.

Read-only audit != demonstrated live idempotent restart or verified billing.
Use an isolated worktree for subsequent code changes and independently review
any future recovery procedure. No automatic retry/fallback is implemented.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

MISSION_A = "HERMES-LIVE-20261121-A"
MISSION_B = "HERMES-LIVE-20261121-B"
MISSION_C = "HERMES-QWEN4-20261121-C"
MISSIONS = (MISSION_A, MISSION_B, MISSION_C)
QWEN_MODEL = "qwen/qwen4-max:free"
EXPECTED_ARTIFACT_SHA256 = hashlib.sha256(b"OK").hexdigest()


def default_state() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise ValueError("LOCALAPPDATA missing; pass --state explicitly")
    return Path(local) / "hermes-tel99" / "autonomous" / "recipe-20261121-AB"


def read_mission(state: Path, mission_id: str) -> dict:
    """Inspect a single checkpoint; never initialise Runtime or FileStore."""
    checkpoint = state / "ledger" / "kilo-local" / (mission_id + ".json")
    try:
        raw = checkpoint.read_bytes()
    except FileNotFoundError:
        return {"id": mission_id, "status": "MISSING"}
    if len(raw) > 1_000_000:
        raise ValueError(f"oversized checkpoint for {mission_id}")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or value.get("id") != mission_id:
        raise ValueError(f"invalid checkpoint identity for {mission_id}")
    status = value.get("status")
    if status not in {"ACCEPTED", "REJECTED", "BLOCKED", "AWAITING_HUMAN",
                      "ACK", "RUNNING", "WORKER_EXITED", "STOPPED"}:
        raise ValueError(f"unrecognised checkpoint status for {mission_id}")
    verification = value.get("verification") or {}
    checks = verification.get("checks") or []
    if not isinstance(verification, dict) or not isinstance(checks, list):
        raise ValueError(f"invalid verifier report for {mission_id}")
    result = value.get("result") or {}
    if not isinstance(result, dict):
        raise ValueError(f"invalid worker result for {mission_id}")
    evidence = result.get("provider_evidence") or {}
    if not isinstance(evidence, dict):
        raise ValueError(f"invalid provider evidence for {mission_id}")
    artifact = result.get("artifact")
    actual_artifact_sha = (hashlib.sha256(artifact.encode("utf-8")).hexdigest()
                           if isinstance(artifact, str) else None)
    artifact_ok = (actual_artifact_sha == EXPECTED_ARTIFACT_SHA256
                   and result.get("sha256") == EXPECTED_ARTIFACT_SHA256)
    checks_ok = (len(checks) >= 5 and all(
        isinstance(x, dict) and x.get("ok") is True for x in checks))
    cost_verified = (evidence.get("model") == result.get("model")
                     and evidence.get("billing_provider") == "nous"
                     and evidence.get("estimated_cost_usd") == 0.0
                     and evidence.get("actual_cost_usd") == 0.0
                     and evidence.get("session_id") == result.get("session_id")
                     and isinstance(evidence.get("api_call_count"), int)
                     and evidence["api_call_count"] >= 1)
    return {
        "id": mission_id,
        "status": status,
        "contract_sha256": value.get("contract_sha256"),
        "artifact_sha256_matches": artifact_ok,
        "independent_verification_recorded": verification.get("ok") is True and checks_ok,
        "model": result.get("model"),
        "session_id": result.get("session_id"),
        "provider_cost_evidence_present_and_zero": cost_verified,
        "estimated_cost_usd": evidence.get("estimated_cost_usd"),
        "actual_cost_usd": evidence.get("actual_cost_usd"),
    }


def audit(state: Path) -> dict:
    if not state.is_dir():
        raise ValueError("state directory not found; no mission executed")
    snapshots = {mission_id: read_mission(state, mission_id) for mission_id in MISSIONS}
    ab_pass = all(
        snapshots[mid]["status"] == "ACCEPTED"
        and snapshots[mid]["artifact_sha256_matches"]
        and snapshots[mid]["independent_verification_recorded"]
        and snapshots[mid]["provider_cost_evidence_present_and_zero"]
        for mid in (MISSION_A, MISSION_B)
    )
    c = snapshots[MISSION_C]
    # Do not reinterpret/rewrite REJECTED even if stored cost evidence is zero.
    return {
        "mode": "READ_ONLY_HISTORICAL_AUDIT",
        "ab_existing_acceptance_verified_from_local_checkpoints": ab_pass,
        "c_historical_status": c["status"],
        "c_currently_accepted": False if c["status"] == "REJECTED" else c["status"] == "ACCEPTED",
        "c_expected_model": QWEN_MODEL,
        "c_wrong_state_scope": c["status"] != "MISSING",  # C required separate state.
        "c_reconciliation_authorised": False,
        "live_replay_without_duplicate_calls_proven": False,
        "github_ack_publication_counts_checked": False,
        "local_worker_invoked": False,
        "github_posts_made": False,
        "missions": snapshots,
        "next": "Preserve C verdict, independently inspect session billing and scope; "
                "separately authorise any new mission and verify true replay.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path,
                        help="Existing recipe state; defaults to LOCALAPPDATA path")
    args = parser.parse_args(argv)
    try:
        state = args.state if args.state is not None else default_state()
        report = audit(state)
        print(json.dumps(report, ensure_ascii=True, sort_keys=True))
        return 0 if report["ab_existing_acceptance_verified_from_local_checkpoints"] else 2
    except (OSError, ValueError, UnicodeError, TypeError, KeyError) as exc:
        print(json.dumps({"mode": "READ_ONLY_HISTORICAL_AUDIT", "status": "BLOCKED",
                          "reason": str(exc)[:250]}, ensure_ascii=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
