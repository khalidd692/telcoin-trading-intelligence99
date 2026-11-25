"""Offline local proposal & contract builder for owner-approved TEL99 campaigns.

Strictly read-only toward GitHub: generates validated JSON contracts, SHA-256
fingerprints, and optional Docker baseline-red pre-checks for owner review.
Never creates issues, comments, approvals, or PRs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.agents.automation.autonomy_runtime import fingerprint, validate_contract
from scripts.agents.automation import local_codegen, local_team
from scripts.agents.automation.env_doctor import DEFAULT_SANDBOX_IMAGE
from scripts.agents.automation.github_local_code_campaign import APPROVAL, MANDATE, LocalCodeCampaign
from scripts.agents.automation.kilo_github_adapter import REPO
from scripts.agents.automation.local_code_pr import valid_campaign_base


def _canonical_mission(item: dict, *, base_sha: str) -> dict:
    mission = {
        "id": item["id"],
        "owner": "local",
        "project": "tel99",
        "specialist": "tel99-dev",
        "priority": item.get("priority", "P1"),
        "dependencies": list(item.get("dependencies", [])),
        "objective": item["objective"],
        "base_sha": base_sha,
        "path": item["path"],
        "function": item["function"],
        "test": item["test"],
        "sandbox_image": item.get("sandbox_image", DEFAULT_SANDBOX_IMAGE),
        "model": item.get("model", "gemma4:e4b-tel99-8k"),
        "port": item.get("port", 11434),
        "team": local_team.TEAM.copy(),
        "max_attempts": item.get("max_attempts", 2),
    }
    validate_contract(mission, {mission["id"]: fingerprint(mission)})
    return mission


def build_proposal(spec: dict, *, verify_baseline: bool = False,
                   source_loader=local_codegen._source,
                   behavior_runner=local_codegen._behavior) -> dict:
    """Validate a local campaign specification and produce owner-reviewable blocks."""
    if not isinstance(spec, dict):
        raise ValueError("proposal spec must be a JSON object")
    controller_issue = spec.get("controller_issue")
    if type(controller_issue) is not int or controller_issue <= 203:
        raise ValueError("controller_issue must be an integer > 203")
    base_ref = spec.get("base_ref")
    base_sha = spec.get("base_sha")
    if not valid_campaign_base(base_ref, base_sha):
        raise ValueError("base_ref and base_sha must define an approved isolated campaign base")
    expires_at = spec.get("expires_at")
    if not isinstance(expires_at, str) or not expires_at.endswith("Z"):
        raise ValueError("expires_at must be an ISO UTC timestamp ending in Z")
    mandate_comment_id = spec.get("mandate_comment_id", 0)
    if type(mandate_comment_id) is not int or mandate_comment_id < 0:
        raise ValueError("mandate_comment_id must be a non-negative integer")
    raw_missions = spec.get("missions")
    if not isinstance(raw_missions, list) or not 2 <= len(raw_missions) <= 10:
        raise ValueError("proposal requires 2..10 missions")

    contracts: dict[str, str] = {}
    missions_out: list[dict] = []
    candidates: dict[str, dict] = {}
    baseline_checks: dict[str, dict] = {}

    for item in raw_missions:
        if not isinstance(item, dict):
            raise ValueError("each mission entry must be an object")
        issue_num = item.get("issue")
        if type(issue_num) is not int or issue_num <= controller_issue:
            raise ValueError("each mission requires an issue integer > controller_issue")
        mission = _canonical_mission(item, base_sha=base_sha)
        mid = mission["id"]
        if mid in contracts:
            raise ValueError(f"duplicate mission id: {mid}")
        digest = fingerprint(mission)
        contracts[mid] = digest
        candidates[mid] = {"mission": mission}
        if verify_baseline:
            source = source_loader(mission)
            local_codegen._function(source, mission["function"])
            passed, line = behavior_runner(mission["sandbox_image"], source, mission["test"])
            if passed:
                raise ValueError(f"baseline test for {mid} already passes (expected baseline-red)")
            baseline_checks[mid] = {"baseline_red": True, "assertion_line": line}
        approval_packet = {
            "mission": mission,
            "approval": {
                "approver": "khalidd692",
                "origin": "owner-direct",
                "mandate_comment_id": mandate_comment_id,
                "issue": issue_num,
                "mission_sha256": digest,
                "expires_at": expires_at,
            },
        }
        missions_out.append({
            "id": mid,
            "issue": issue_num,
            "contract_sha256": digest,
            "fenced_approval": f"```{APPROVAL}\n{json.dumps(approval_packet, ensure_ascii=True, separators=(',', ':'))}\n```",
            "baseline_check": baseline_checks.get(mid),
        })

    mandate_scope = {
        "repo": REPO,
        "issue": controller_issue,
        "label": "enhancement",
        "expires_at": expires_at,
        "base": base_ref,
        "base_sha": base_sha,
        "contracts": contracts,
    }
    for item in candidates.values():
        if not LocalCodeCampaign._mission_allowed(item["mission"], mandate_scope):
            raise ValueError(f"mission {item['mission']['id']} violates LocalCodeCampaign policy")
    LocalCodeCampaign.check_campaign_graph(candidates, mandate_scope)

    fenced_mandate = f"```{MANDATE}\n{json.dumps(mandate_scope, ensure_ascii=True, separators=(',', ':'))}\n```"
    return {
        "schema_version": 1,
        "status": "DRAFT_READY_FOR_OWNER_REVIEW",
        "github_writes_performed": 0,
        "controller_issue": controller_issue,
        "controller_marker": "tel99-autofeed-controller/v1",
        "mandate_scope": mandate_scope,
        "mandate_fenced_block": fenced_mandate,
        "mandate_sha256": hashlib.sha256(fenced_mandate.encode("utf-8")).hexdigest(),
        "missions": missions_out,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--verify-baseline", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    proposal = build_proposal(spec, verify_baseline=args.verify_baseline)
    rendered = json.dumps(proposal, indent=2, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
