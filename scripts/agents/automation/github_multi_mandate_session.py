"""Bounded multi-mandate dispatch for the EXISTING TEL99 GitHub supervisor.

Each manifest entry is an explicit, owner-pinned GitHub mandate.  A separate
persistent CAS directory per controller prevents cross-campaign collisions.
No code is executed without the existing LocalCodeCampaign authentication,
preflight, ACK, independent verifier, RESULT and draft-PR gates.

Manifest:
{"version": 1, "campaigns": [
  {"issue": 200, "mandate_comment": 1234, "mandate_sha256": "<64 hex>",
   "base_ref": "agents/approved-isolated-base", "base_sha": "<40 hex>"}
]}
Never reuse controller #178 or its completed #179-#181 missions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time

from scripts.agents.automation.autonomy_runtime import Runtime, LEGACY_STOP
from scripts.agents.automation.github_local_code_campaign import LocalCodeCampaign
from scripts.agents.automation.local_code_pr import valid_campaign_base
from scripts.agents.automation.local_codex import Blocked, exclusive

REQUIRED = {"issue", "mandate_comment", "mandate_sha256", "base_ref", "base_sha"}
MAX_CAMPAIGNS = 10
HISTORICAL_MAX_CONTROLLER = 181  # previous campaigns are permanently excluded


def load_manifest(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or set(data) != {"version", "campaigns"}
            or type(data["version"]) is not int or data["version"] != 1
            or not isinstance(data["campaigns"], list)
            or not 1 <= len(data["campaigns"]) <= MAX_CAMPAIGNS):
        raise ValueError("expected a bounded v1 campaign manifest")
    seen = set()
    for item in data["campaigns"]:
        if (not isinstance(item, dict) or set(item) != REQUIRED
                or type(item["issue"]) is not int or item["issue"] <= HISTORICAL_MAX_CONTROLLER
                or type(item["mandate_comment"]) is not int or item["mandate_comment"] <= 0
                or not isinstance(item["mandate_sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", item["mandate_sha256"])
                or not valid_campaign_base(item["base_ref"], item["base_sha"])
                or item["issue"] in seen):
            raise ValueError("invalid, repeated, or historical campaign pin")
        seen.add(item["issue"])
    return data["campaigns"]


def make_campaign(spec, root, deadline):
    runtime = Runtime(root / f"campaign-{spec['issue']}",
                      legacy_stop=LEGACY_STOP)
    runtime.deadline = deadline
    return LocalCodeCampaign(
        runtime, spec["issue"], spec["mandate_comment"],
        spec["mandate_sha256"], base_ref=spec["base_ref"],
        base_sha=spec["base_sha"],
    )


def preflight_campaigns(specs, root, deadline, *, build=make_campaign):
    """Authenticate *every* listed controller before executing any worker."""
    campaigns = []
    for spec in specs:
        campaign = build(spec, root, deadline)
        campaign.check_github_identity()
        approved = campaign.preflight()
        expected = len(campaign.check_mandate()["contracts"])
        if len(approved) != expected:
            raise Blocked(f"controller #{spec['issue']} lacks signed approvals")
        campaigns.append(campaign)
    return campaigns


def run_campaigns(manifest, root, *, seconds=3600, poll_interval=30,
                  once=False, build=make_campaign, sleep=time.sleep):
    """One bounded session; later owner-pinned controllers may be added to manifest.

    A change to the pin of an existing controller is rejected by the dedicated
    durable ledger. Completed campaigns are never reexecuted; the existing
    GitHub publisher additionally reconciles uncertain receipts/PR writes.
    """
    if not 1 <= seconds <= 3600 or not 1 <= poll_interval <= 3600:
        raise ValueError("seconds and poll interval must be within 1..3600")
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + seconds
    summary = {}
    with exclusive(root / "multi-session.lock"):
        while (not (root / "stop.request").exists() and not LEGACY_STOP.exists()
               and time.monotonic() < deadline):
            specs = load_manifest(manifest)
            campaigns = preflight_campaigns(specs, root, deadline, build=build)
            for spec, campaign in zip(specs, campaigns):
                if ((root / "stop.request").exists() or LEGACY_STOP.exists()
                        or time.monotonic() >= deadline):
                    break
                if not campaign.complete():
                    if not campaign.poll() or campaign.github_rate_limited:
                        raise Blocked(f"controller #{spec['issue']} blocked: inspect its ledger")
                summary[spec["issue"]] = campaign.complete()
            if once:
                break
            until = min(deadline, time.monotonic() + poll_interval)
            while not (root / "stop.request").exists() and time.monotonic() < until:
                sleep(min(0.1, max(0, until - time.monotonic())))
    return summary


def status(root, manifest=None):
    root = Path(root).resolve()
    if manifest is not None:
        controllers = [spec["issue"] for spec in load_manifest(manifest)]
    else:
        controllers = sorted(int(p.name.split("-")[-1]) for p in root.glob("campaign-*")
                             if p.is_dir() and p.name.split("-")[-1].isdigit())
    return {
        "stop_requested": (root / "stop.request").exists(),
        "campaigns": {
            str(issue): Runtime(root / f"campaign-{issue}").status()
            for issue in controllers if (root / f"campaign-{issue}").exists()
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "run", "status", "stop"))
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--seconds", type=int, default=3600)
    parser.add_argument("--poll-interval", type=int, default=30)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.seconds <= 3600 or not 1 <= args.poll_interval <= 3600:
        parser.error("--seconds and --poll-interval must be 1..3600")
    root = args.state.resolve()
    if args.action == "stop":
        root.mkdir(parents=True, exist_ok=True)
        (root / "stop.request").touch()
        for ledger in root.glob("campaign-*"):
            if ledger.is_dir():
                (ledger / "stop.request").touch()
        print("STOP requested")
        return 0
    if args.action == "status":
        print(json.dumps(status(root, args.manifest)))
        return 0
    if args.manifest is None:
        parser.error("preflight/run require --manifest with owner-pinned controllers")
    if (root / "stop.request").exists() or LEGACY_STOP.exists():
        print(json.dumps({"status": "BLOCKED", "reason": "stop.request or legacy STOP exists"}))
        return 2
    try:
        if args.action == "preflight":
            specs = load_manifest(args.manifest)
            campaigns = preflight_campaigns(specs, root, None)
            print(json.dumps({"preflight": "READY", "controllers":
                              [spec["issue"] for spec in specs],
                              "missions": [len(c.check_mandate()["contracts"]) for c in campaigns]}))
            return 0
        report = run_campaigns(args.manifest, root, seconds=args.seconds,
                               poll_interval=args.poll_interval, once=args.once)
        print(json.dumps({"results": report, "all_complete": bool(report) and all(report.values()),
                          "bounded_seconds": args.seconds}))
        return 0 if report and all(report.values()) else 2
    except (OSError, ValueError, KeyError, Blocked) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
