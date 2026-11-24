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
                      legacy_stop=LEGACY_STOP,
                      shared_memory_root=root / "learning" / "memory")
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


def detect_campaign_collisions(specs, root) -> dict[int, str]:
    """Detect active incomplete controllers targeting the exact same (base_ref, path)."""
    claimed_paths: dict[tuple[str, str], int] = {}
    collisions: dict[int, str] = {}
    for spec in specs:
        issue = spec["issue"]
        camp_dir = Path(root) / f"campaign-{issue}"
        ledger_dir = camp_dir / "ledger"
        if not ledger_dir.is_dir():
            continue
        from scripts.agents.protocol.store import FileStore
        store = FileStore(ledger_dir)
        approvals = [store.get(k) for k in store.keys("kilo-github/approvals")]
        paths = []
        done = bool(approvals)
        for row in approvals:
            if not isinstance(row, dict) or not isinstance(row.get("mission"), dict):
                continue
            mid = row["mission"].get("id")
            path = row["mission"].get("path")
            if isinstance(path, str):
                paths.append(path)
            st = store.get(f"kilo-local/{mid}") if mid else None
            if not isinstance(st, dict) or st.get("status") != "ACCEPTED":
                done = False
        if done:
            continue
        for path in paths:
            target = (spec["base_ref"], path)
            owner_issue = claimed_paths.get(target)
            if owner_issue is not None and owner_issue != issue:
                collisions[issue] = (
                    f"path collision on ({spec['base_ref']}, {path}) with active controller #{owner_issue}"
                )
                break
            claimed_paths[target] = issue
    return collisions


def _controller_has_terminal_blocker(campaign) -> bool:
    states = getattr(campaign, "states", None)
    if not callable(states):
        return False
    return any(
        isinstance(row, dict) and row.get("status") in {"AWAITING_HUMAN", "BLOCKED", "REJECTED"}
        for row in states()
    )


def run_campaigns(manifest, root, *, seconds=3600, poll_interval=30,
                  once=False, build=make_campaign, sleep=time.sleep, discover=None,
                  isolate_blocked=False):
    """One bounded session; later owner-pinned controllers may be added to manifest.

    A change to the pin of an existing controller is rejected by the dedicated
    durable ledger. Completed campaigns are never reexecuted; the existing
    GitHub publisher additionally reconciles uncertain receipts/PR writes.
    When ``isolate_blocked=True``, controllers that are already blocked or hit
    a human checkpoint are isolated without replaying workers so other valid
    controllers can still proceed.
    """
    if (manifest is None) == (discover is None):
        raise ValueError("choose exactly one owner-approved source: manifest or auto-feed")
    if not 1 <= seconds <= 3600 or not 1 <= poll_interval <= 3600:
        raise ValueError("seconds and poll interval must be within 1..3600")
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + seconds
    summary = {}
    isolated: dict[int, str] = {}
    with exclusive(root / "multi-session.lock"):
        while (not (root / "stop.request").exists() and not LEGACY_STOP.exists()
               and time.monotonic() < deadline):
            specs = discover(root) if discover is not None else load_manifest(manifest)
            if len(specs) > MAX_CAMPAIGNS:
                raise ValueError("too many owner-approved controllers")
            collisions = detect_campaign_collisions(specs, root)
            if collisions and not isolate_blocked:
                first_issue = next(iter(collisions))
                raise Blocked(f"controller #{first_issue}: {collisions[first_issue]}")
            active_specs = []
            active_campaigns = []
            if not isolate_blocked:
                active_specs = specs
                active_campaigns = preflight_campaigns(specs, root, deadline, build=build)
            else:
                for spec in specs:
                    issue = spec["issue"]
                    if issue in collisions:
                        isolated[issue] = collisions[issue]
                        summary[issue] = False
                        continue
                    try:
                        campaign = build(spec, root, deadline)
                        if _controller_has_terminal_blocker(campaign):
                            isolated[issue] = "existing checkpoint requires human review"
                            summary[issue] = False
                            continue
                        campaign.check_github_identity()
                        approved = campaign.preflight()
                        expected = len(campaign.check_mandate()["contracts"])
                        if len(approved) != expected:
                            isolated[issue] = "lacks signed approvals"
                            summary[issue] = False
                            continue
                        active_specs.append(spec)
                        active_campaigns.append(campaign)
                    except (OSError, ValueError, KeyError, Blocked) as exc:
                        isolated[issue] = str(exc)
                        summary[issue] = False
            for spec, campaign in zip(active_specs, active_campaigns):
                if ((root / "stop.request").exists() or LEGACY_STOP.exists()
                        or time.monotonic() >= deadline):
                    break
                issue = spec["issue"]
                if not campaign.complete():
                    if not campaign.poll() or campaign.github_rate_limited:
                        msg = f"controller #{issue} blocked: inspect its ledger"
                        if not isolate_blocked:
                            raise Blocked(msg)
                        isolated[issue] = msg
                        summary[issue] = False
                        continue
                    if _controller_has_terminal_blocker(campaign):
                        msg = f"controller #{issue} needs human review; checkpoints preserved"
                        if not isolate_blocked:
                            raise Blocked(msg)
                        isolated[issue] = msg
                        summary[issue] = False
                        continue
                summary[issue] = campaign.complete()
            if any((root / f"campaign-{spec['issue']}" / "ledger" / "kilo-local").is_dir() for spec in specs):
                try:
                    from scripts.agents.automation import learning_loop
                    learning_loop.sync_measured_quality(root)
                except (OSError, ValueError):
                    pass
            if once:
                break
            until = min(deadline, time.monotonic() + poll_interval)
            while not (root / "stop.request").exists() and time.monotonic() < until:
                sleep(min(0.1, max(0, until - time.monotonic())))
    if isolated and not any(summary.values()):
        first_issue = next(iter(isolated))
        raise Blocked(f"controller #{first_issue}: {isolated[first_issue]}")
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
    parser.add_argument("--auto-feed", action="store_true",
                        help="read-only discovery of new owner-approved GitHub controllers")
    parser.add_argument("--seconds", type=int, default=3600)
    parser.add_argument("--poll-interval", type=int, default=30)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--isolate-blocked", action="store_true",
                        help="isolate blocked/unapproved controllers without stopping healthy ones")
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
    if (args.manifest is None) == (not args.auto_feed):
        parser.error("choose exactly one: --manifest or --auto-feed")
    discover = None
    if args.auto_feed:
        from scripts.agents.automation.github_owner_feed import pinned_owner_feed
        discover = pinned_owner_feed
    if (root / "stop.request").exists() or LEGACY_STOP.exists():
        print(json.dumps({"status": "BLOCKED", "reason": "stop.request or legacy STOP exists"}))
        return 2
    try:
        if args.action == "preflight":
            specs = discover(root) if discover is not None else load_manifest(args.manifest)
            campaigns = preflight_campaigns(specs, root, None)
            print(json.dumps({"preflight": "READY" if specs else "WAITING_OWNER_APPROVAL",
                              "controllers": [spec["issue"] for spec in specs],
                              "missions": [len(c.check_mandate()["contracts"]) for c in campaigns]}))
            return 0
        report = run_campaigns(args.manifest, root, seconds=args.seconds,
                               poll_interval=args.poll_interval, once=args.once,
                               discover=discover, isolate_blocked=args.isolate_blocked)
        print(json.dumps({"results": report, "all_complete": bool(report) and all(report.values()),
                          "bounded_seconds": args.seconds}))
        return 0 if report and all(report.values()) else 2
    except (OSError, ValueError, KeyError, Blocked) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
