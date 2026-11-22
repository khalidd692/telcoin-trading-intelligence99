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
import re
import sqlite3
import sys
from pathlib import Path

MISSION_A = "HERMES-LIVE-20261121-A"
MISSION_B = "HERMES-LIVE-20261121-B"
MISSION_C = "HERMES-QWEN4-20261121-C"
MISSIONS = (MISSION_A, MISSION_B, MISSION_C)
QWEN_MODEL = "qwen/qwen4-max:free"
EXPECTED_ARTIFACT_SHA256 = hashlib.sha256(b"OK").hexdigest()
EXPECTED_CONTRACTS = {
    MISSION_A: "597576eaa2ec84b3311df4186fe11eecf7f3ecc154a916c16f9b105a405e7d58",
    MISSION_B: "450bb0f2b524dba38e875ea26cd6ae461cc26747c42610afdf79b1f03a22d8e3",
    MISSION_C: "1ce10da1e79b71aa8354f78552a4b59c0fe99f8139956d346c84e01d3590b617",
}
EXPECTED_MODELS = {
    MISSION_A: "meituan/longcat-2.5:free",
    MISSION_B: "meituan/longcat-2.5:free",
    MISSION_C: QWEN_MODEL,
}
EXPECTED_ROLES = {
    MISSION_A: "tel99-analyst", MISSION_B: "tel99-dev", MISSION_C: "tel99-analyst",
}
EXPECTED_SESSIONS = {
    MISSION_A: "local-3139741921003cb68e6b35387e61ef623a8c1517b56431e4cdb6f7de17e29e62",
    MISSION_B: "local-5e538a446c010b0cac78b968f64f1d7280fbc2baa58670c325e242e6884e9c86",
}
REQUIRED_CHECKS = frozenset({
    "synthetic-contract", "artifact-sha256", "specialist-identity",
    "hermes-session-evidence", "zero-cost-evidence",
})


def default_state() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise ValueError("LOCALAPPDATA missing; pass --state explicitly")
    return Path(local) / "hermes-tel99" / "autonomous" / "recipe-20261121-AB"


def unique_checkpoint_fields(pairs):
    value = {}
    for name, item in pairs:
        if name in value:
            raise ValueError("duplicate checkpoint key")
        value[name] = item
    return value


def read_mission(state: Path, mission_id: str) -> dict:
    """Inspect a single checkpoint; never initialise Runtime or FileStore."""
    checkpoint = state / "ledger" / "kilo-local" / (mission_id + ".json")
    try:
        with checkpoint.open("rb") as stream:
            raw = stream.read(1_000_001)
    except FileNotFoundError:
        return {"id": mission_id, "status": "MISSING"}
    if len(raw) > 1_000_000:
        raise ValueError(f"oversized checkpoint for {mission_id}")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_checkpoint_fields)
    if not isinstance(value, dict) or value.get("id") != mission_id:
        raise ValueError(f"invalid checkpoint identity for {mission_id}")
    status = value.get("status")
    if status not in {"ACCEPTED", "REJECTED", "BLOCKED", "AWAITING_HUMAN",
                      "ACK", "RUNNING", "WORKER_EXITED", "STOPPED"}:
        raise ValueError(f"unrecognised checkpoint status for {mission_id}")
    verification = value.get("verification") or {}
    verdict = value.get("verdict") or {}
    if not isinstance(verification, dict) or not isinstance(verdict, dict):
        raise ValueError(f"invalid verifier report for {mission_id}")
    checks = verification.get("checks") or []
    if not isinstance(checks, list) or any(
            not isinstance(check, dict) or not isinstance(check.get("name"), str)
            for check in checks):
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
    check_names = {x["name"] for x in checks}
    checks_ok = (check_names == REQUIRED_CHECKS
                 and len(checks) == len(REQUIRED_CHECKS)
                 and all(x.get("ok") is True for x in checks))
    session_id = result.get("session_id")
    specialist_ok = (result.get("specialist_id") == EXPECTED_ROLES[mission_id]
                     and isinstance(session_id, str)
                     and re.fullmatch(r"local-[0-9a-f]{64}", session_id) is not None
                     and (mission_id not in EXPECTED_SESSIONS
                          or session_id == EXPECTED_SESSIONS[mission_id]))
    cost_verified = (evidence.get("model") == result.get("model")
                     and evidence.get("billing_provider") == "nous"
                     and all(type(evidence.get(name)) in (int, float) and evidence[name] == 0
                             for name in ("estimated_cost_usd", "actual_cost_usd"))
                     and evidence.get("session_id") == result.get("session_id")
                     and type(evidence.get("api_call_count")) is int
                     and evidence["api_call_count"] >= 1)
    return {
        "id": mission_id,
        "status": status,
        "contract_sha256_matches_original_approval": (
            value.get("contract_sha256") == EXPECTED_CONTRACTS[mission_id]),
        "artifact_sha256_matches": artifact_ok,
        "specialist_and_session_identity_match": specialist_ok,
        "independent_verification_recorded": (
            verification.get("ok") is True and checks_ok
            and verification.get("verifier") == "hermes-fixed-subprocess-v1"
            and verdict.get("validated") is True),
        "model": result.get("model"),
        "model_matches_original_execution": result.get("model") == EXPECTED_MODELS[mission_id],
        "session_id": result.get("session_id"),
        "provider_cost_evidence_present_and_zero": cost_verified,
        "estimated_cost_usd": evidence.get("estimated_cost_usd"),
        "actual_cost_usd": evidence.get("actual_cost_usd"),
    }


def inspect_qwen_billing_db(session_id: str | None, db: Path) -> dict:
    """Read the exact historical C session from Hermes DB without writing it."""
    if not isinstance(session_id, str) or re.fullmatch(r"local-[0-9a-f]{64}", session_id) is None:
        return {"status": "NOT_VERIFIED", "reason": "INVALID_OR_MISSING_SESSION_ID"}
    if not db.is_file():
        return {"status": "NOT_VERIFIED", "reason": "BILLING_DB_UNAVAILABLE"}
    try:
        con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            row = con.execute(
                "SELECT model, billing_provider, estimated_cost_usd, actual_cost_usd, "
                "cost_status FROM session_model_usage WHERE session_id=? "
                "ORDER BY last_seen DESC LIMIT 1", (session_id,)
            ).fetchone()
        finally:
            con.close()
    except (sqlite3.Error, OSError):
        return {"status": "NOT_VERIFIED", "reason": "BILLING_DB_READ_FAILED"}
    if row is None:
        return {"status": "NOT_VERIFIED", "reason": "SESSION_NOT_FOUND"}
    model, provider, estimate, actual, recorded_status = row
    valid = (model == QWEN_MODEL and provider == "nous"
             and estimate == 0.0 and actual == 0.0)
    return {"status": "VERIFIED_ZERO_IN_LOCAL_DB" if valid else "NOT_VERIFIED",
            "model": model, "billing_provider": provider,
            "estimated_cost_usd": estimate, "actual_cost_usd": actual,
            "cost_status": recorded_status}


def audit(state: Path, billing_db: Path | None = None) -> dict:
    if not state.is_dir():
        raise ValueError("state directory not found; no mission executed")
    snapshots = {mission_id: read_mission(state, mission_id) for mission_id in MISSIONS}
    ab_pass = all(
        snapshots[mid]["status"] == "ACCEPTED"
        and snapshots[mid]["contract_sha256_matches_original_approval"]
        and snapshots[mid]["artifact_sha256_matches"]
        and snapshots[mid]["specialist_and_session_identity_match"]
        and snapshots[mid]["model_matches_original_execution"]
        and snapshots[mid]["independent_verification_recorded"]
        and snapshots[mid]["provider_cost_evidence_present_and_zero"]
        for mid in (MISSION_A, MISSION_B)
    )
    c = snapshots[MISSION_C]
    # The audited A/B state cannot authorize C, regardless of the raw checkpoint.
    return {
        "mode": "READ_ONLY_HISTORICAL_AUDIT",
        "ab_existing_acceptance_verified_from_local_checkpoints": ab_pass,
        "c_historical_status": c["status"],
        "c_billing_db_readonly": (inspect_qwen_billing_db(c.get("session_id"), billing_db)
                                  if billing_db is not None else {"status": "NOT_CHECKED"}),
        "c_currently_accepted": False,
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
    parser.add_argument("--billing-db", type=Path,
                        help="Optional read-only Hermes state.db path; never creates a database")
    args = parser.parse_args(argv)
    try:
        state = args.state if args.state is not None else default_state()
        db = args.billing_db
        if db is None:
            hermes_home = Path(os.environ["HERMES_HOME"]) if os.environ.get("HERMES_HOME") else (Path.home() / "AppData" / "Local" / "hermes")
            db = hermes_home / "state.db"
        report = audit(state, billing_db=db)
        print(json.dumps(report, ensure_ascii=True, sort_keys=True))
        return 0 if report["ab_existing_acceptance_verified_from_local_checkpoints"] else 2
    except (OSError, ValueError, UnicodeError, TypeError, KeyError) as exc:
        print(json.dumps({"mode": "READ_ONLY_HISTORICAL_AUDIT", "status": "BLOCKED",
                          "reason": str(exc)[:250]}, ensure_ascii=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
