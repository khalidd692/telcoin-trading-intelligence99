"""Authenticated GitHub intake for the existing TEL99 local-code supervisor.

This adapts the proven Kilo two-issue GitHub receiver, CAS/ACK bus and
reconciliation to owner=local, project=tel99, and independent Docker evidence.
It never admits historical issues or synthetic-text providers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
import time

from scripts.agents.automation.autonomy_runtime import (
    Blocked, LEGACY_STOP, Runtime, fingerprint, run_session, validate_contract,
)
from scripts.agents.automation.github_mission_source import (
    GitHubWriteNotSent, approval_is_current, fenced_json, is_owner,
)
from scripts.agents.automation.kilo_github_adapter import (
    KiloGitHubHandoff, REPO,
)
from scripts.agents.automation.policy import is_eligible_mission
from scripts.agents.automation import local_team
from scripts.agents.automation.local_code_pr import (
    BASE_REF, BASE_SHA, publish_verified_code_pr, valid_campaign_base,
)
from scripts.agents.automation.ollama_native import OllamaNativeProvider
from scripts.agents.native.provider import ProviderError

MANDATE = "tel99-code-campaign/v1"
APPROVAL = "tel99-code-mission/v1"
TRANSPORT = "github-local-code"
CONFIG_KEY = "github-local-code/config"
CODE_LABEL = "enhancement"


class LocalCodeCampaign(KiloGitHubHandoff):
    """Reuse the Kilo receiver's discovery, durable CAS, ACK and result outbox."""

    def __init__(self, runtime, issue, mandate_id, mandate_sha, *, fetcher=None,
                 publisher=None, pr_publisher=None, base_ref=None, base_sha=None):
        if type(issue) is not int or issue <= 167:
            raise ValueError("use a new dedicated controller issue, never a historical issue")
        if base_ref is None and base_sha is None:
            base_ref, base_sha = BASE_REF, BASE_SHA
        elif not valid_campaign_base(base_ref, base_sha):
            raise ValueError("provide an isolated campaign base ref and exact commit SHA together")
        self.base_ref, self.base_sha = base_ref, base_sha
        super().__init__(None, issue, mandate_id, mandate_sha, campaign=True,
                         fetcher=fetcher, publisher=publisher,
                         pr_publisher=pr_publisher or publish_verified_code_pr)
        self.runtime = runtime
        if runtime is None:
            return
        runtime.bind_transport(TRANSPORT)
        config = {
            "repo": REPO, "issue": issue, "mandate_id": mandate_id,
            "mandate_sha256": mandate_sha, "campaign": True, "profile": TRANSPORT,
        }
        if (base_ref, base_sha) != (BASE_REF, BASE_SHA):
            config.update(base_ref=base_ref, base_sha=base_sha)
        existing = runtime.store.get(CONFIG_KEY)
        if existing is None:
            if runtime.store.keys("kilo-local"):
                raise ValueError("use a fresh state directory for the local-code GitHub campaign")
            runtime.store.put_cas(CONFIG_KEY, config, None)
        if runtime.store.get(CONFIG_KEY) != config:
            raise ValueError("runtime ledger is pinned to a different campaign")
        runtime.before_execute = self.before_execute

    def check_mandate(self):
        issue = self.fetch(self.issue_endpoint)
        comment = self.comment(self.mandate_id)
        if (not isinstance(issue, dict) or issue.get("number") != self.issue
                or issue.get("state") != "open" or "pull_request" in issue
                or not is_owner(issue.get("user"))
                or not self.trusted(comment, self.issue)
                or comment["id"] != self.mandate_id):
            raise ValueError("invalid owner mandate issue/comment identity")
        body = comment.get("body")
        if (not isinstance(body, str)
                or hashlib.sha256(body.encode("utf-8")).hexdigest() != self.mandate_sha):
            raise ValueError("operator-pinned mandate body has changed")
        scope = fenced_json(body, MANDATE)
        if (not isinstance(scope, dict)
                or set(scope) != {"repo", "issue", "label", "expires_at", "base", "base_sha", "contracts"}
                or scope["repo"] != REPO or type(scope["issue"]) is not int
                or scope["issue"] != self.issue or scope["label"] != CODE_LABEL
                or (scope["base"], scope["base_sha"]) != (self.base_ref, self.base_sha)
                or not approval_is_current(scope, datetime.now(timezone.utc))
                or not isinstance(scope["contracts"], dict) or len(scope["contracts"]) != 2
                or any(not isinstance(mid, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,48}", mid)
                       or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                       for mid, digest in scope["contracts"].items())
                or not isinstance(comment.get("created_at"), str)
                or comment.get("created_at") != comment.get("updated_at")):
            raise ValueError("invalid signed code campaign or its expiry")
        return {**scope, "created_at": comment["created_at"]}

    def check_campaign_base(self):
        scope = self.check_mandate()
        result = self.fetch(f"repos/{REPO}/git/ref/heads/{self.base_ref}")
        obj = result.get("object") if isinstance(result, dict) else None
        if not isinstance(obj, dict) or (obj.get("sha"), obj.get("type")) != (scope["base_sha"], "commit"):
            raise ValueError("dedicated code base branch changed from approved commit")

    def eligible_campaign_issue(self, row, scope):
        number = row.get("number") if isinstance(row, dict) else None
        return (type(number) is int and number > self.issue
                and row.get("state") == "open" and "pull_request" not in row
                and is_owner(row.get("user")) and isinstance(row.get("labels"), list)
                and is_eligible_mission(row, scope["label"])
                and isinstance(row.get("created_at"), str)
                and row["created_at"] > scope["created_at"]
                and isinstance(row.get("body"), str)
                and f"tel99-code-campaign: {self.mandate_id}" in row["body"].splitlines())

    def campaign_approval(self, row, issue, scope):
        packet = fenced_json(row.get("body"), APPROVAL) or {}
        mission = packet.get("mission")
        approval = packet.get("approval")
        if (set(packet) != {"mission", "approval"}
                or not isinstance(mission, dict) or not isinstance(approval, dict)
                or mission.get("id") not in scope["contracts"]
                or not isinstance(row.get("created_at"), str)
                or row["created_at"] <= scope["created_at"]):
            return False
        return (scope["contracts"][mission["id"]] == fingerprint(mission)
                and approval.get("issue") == issue and type(approval.get("issue")) is int
                and approval.get("mandate_comment_id") == self.mandate_id
                and approval.get("approver") == "khalidd692"
                and approval.get("origin") == "owner-direct"
                and approval.get("mission_sha256") == fingerprint(mission)
                and approval_is_current(approval, datetime.now(timezone.utc))
                and self._mission_allowed(mission, scope))

    @staticmethod
    def _mission_allowed(mission, scope):
        if (mission.get("owner") != "local" or mission.get("project") != "tel99"
                or mission.get("specialist") != "tel99-dev"
                or mission.get("base_sha") != scope["base_sha"]
                or mission.get("team") != local_team.TEAM
                or mission.get("port") != 11434
                or "routing" in mission):
            return False
        try:
            validate_contract(mission, {mission["id"]: fingerprint(mission)})
            OllamaNativeProvider(model=mission["model"])
        except (ValueError, TypeError, KeyError, ProviderError):
            return False
        return True

    def approvals(self, comments, issue, scope):
        missions, digests, sources, conflicts = {}, {}, {}, set()
        for row in comments:
            if not self.trusted(row, issue) or not self.campaign_approval(row, issue, scope):
                continue
            mission = fenced_json(row["body"], APPROVAL)["mission"]
            mid = mission["id"]
            if mid in missions:
                conflicts.add(mid)
            else:
                missions[mid] = mission
                digests[mid] = fingerprint(mission)
                sources[mid] = row["id"]
        for mid in conflicts:
            missions.pop(mid, None)
            digests.pop(mid, None)
            sources.pop(mid, None)
        if conflicts:
            raise ValueError("multiple approval comments for the same approved mission")
        return {"missions": list(missions.values()), "approvals": digests, "sources": sources}

    @staticmethod
    def check_campaign_graph(candidates, scope):
        KiloGitHubHandoff.check_campaign_graph(candidates, scope)
        paths = [binding["mission"]["path"] for binding in candidates.values()]
        if len(paths) != len(set(paths)):
            raise ValueError("two independent draft PRs must modify different approved files")

    def event(self, phase, state, binding):
        record = super().event(phase, state, binding)
        record["scope"] = "approved-python-function"
        record["provider"] = "ollama-loopback"
        if phase == "EVIDENCE":
            report = state.get("verification") or {}
            record["base_sha"] = report.get("base_sha")
            record["path"] = report.get("path")
            record["test_sha256"] = report.get("test_sha256")
            roles = []
            if local_team.valid_trace(binding["mission"], state.get("result") or {}):
                roles.extend(local_team.TEAM[:2])
            if (report.get("verification_role") or {}).get("role") == local_team.TEAM[2]:
                roles.append(local_team.TEAM[2])
            record["roles"] = roles
        return record

    def publish_pull_request(self, state, binding, evidence):
        def authorized_api(endpoint, *, method="GET", payload=None):
            if method != "GET":
                try:
                    approved = method == "POST" and self.current_approval(binding, state["id"])
                except (OSError, ValueError, KeyError) as exc:
                    raise GitHubWriteNotSent("approved code mission is no longer current") from exc
                if not approved:
                    raise GitHubWriteNotSent("GitHub code mission approval changed before write")
            return self.github(endpoint, method=method, payload=payload)

        return self.pr_publisher(REPO, binding["issue"], binding["base"], binding["base_sha"],
                                 state, evidence, api=authorized_api, store=self.runtime.store,
                                 root=self.runtime.root)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "run", "status", "stop"))
    parser.add_argument("--state", type=Path)
    parser.add_argument("--issue", type=int)
    parser.add_argument("--mandate-comment", type=int)
    parser.add_argument("--mandate-sha256")
    parser.add_argument("--base-ref")
    parser.add_argument("--base-sha")
    parser.add_argument("--seconds", type=int, choices=range(1, 3601), default=3600)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=int, default=30, metavar="SECONDS",
                        help="idle re-discovery sweep interval (default 30)")
    args = parser.parse_args(argv)
    if not 1 <= args.poll_interval <= 3600:
        parser.error("--poll-interval must be 1..3600")
    if (args.base_ref is not None or args.base_sha is not None) and (
            args.action not in {"preflight", "run"} or not valid_campaign_base(args.base_ref, args.base_sha)):
        parser.error("--base-ref and --base-sha are required together for preflight or run")
    base_options = {"base_ref": args.base_ref, "base_sha": args.base_sha}
    if args.action == "preflight":
        if not (args.issue and args.mandate_comment and args.mandate_sha256):
            parser.error("preflight requires a pinned GitHub owner mandate")
        try:
            handler = LocalCodeCampaign(None, args.issue, args.mandate_comment,
                                        args.mandate_sha256, **base_options)
            handler.check_github_identity()
            tasks = handler.preflight()
            ok = len(tasks) == 2
            print(json.dumps({"preflight": "READY" if ok else "WAITING_APPROVALS",
                              "missions": tasks}))
            return 0 if ok else 2
        except (OSError, ValueError, KeyError) as exc:
            print(json.dumps({"preflight": "BLOCKED", "reason": str(exc)}))
            return 2
    if not args.state:
        parser.error("--state required")
    runtime = Runtime(args.state, legacy_stop=LEGACY_STOP)
    if args.action == "stop":
        (runtime.root / "stop.request").touch()
        print("STOP requested")
        return 0
    if args.action == "status":
        print(json.dumps(runtime.status()))
        return 0
    if not (args.issue and args.mandate_comment and args.mandate_sha256):
        parser.error("run requires pinned GitHub mandate arguments")
    if runtime.stopped():
        print(json.dumps({"status": "BLOCKED", "reason": "stop marker remains set"}))
        return 2
    runtime.deadline = time.monotonic() + args.seconds
    try:
        campaign = LocalCodeCampaign(runtime, args.issue, args.mandate_comment,
                                     args.mandate_sha256, **base_options)
        campaign.check_github_identity()
        # Multi-campaign: do NOT stop after the first campaign completes.
        # The session continues until deadline, stop.request, or quota exhaustion.
        # `done` only returns True on github_rate_limited or explicit operator stop.
        run_session(runtime, campaign.poll, once=args.once,
                    done=lambda: campaign.github_rate_limited,
                    poll_interval=args.poll_interval)
        complete = campaign.complete() and not campaign.github_rate_limited
    except (OSError, ValueError, KeyError, Blocked) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return 2
    report = runtime.status()
    report["delivery"] = "COMPLETE" if complete else "INCOMPLETE"
    report["github_code"] = runtime.store.get(CONFIG_KEY)
    report["github_receipts"] = {
        key: row.get("url") or ("NOT_SENT" if row.get("not_sent") else "PENDING_RECONCILIATION")
        for key in runtime.store.keys("kilo-github/outbox")
        if isinstance((row := runtime.store.get(key)), dict)
    }
    report["draft_prs"] = {
        key: row.get("pr_url") for key in runtime.store.keys("github-local-code/PR")
        if isinstance((row := runtime.store.get(key)), dict) and row.get("pr_url")
    }
    print(json.dumps(report))
    return 0 if complete else 2


if __name__ == "__main__":
    sys.exit(main())
