"""Connect a pinned synthetic GitHub queue to the existing Kilo runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.agents.automation.autonomy_runtime import (
    Blocked, QuotaBlocked, Runtime, TERMINAL, fingerprint, run_session,
)
from scripts.agents.automation.github_mission_source import (
    MAX_MISSIONS, approval_is_current, fetch_comments, fetch_pages, fenced_json, gh_json, parse_approvals,
)
from scripts.agents.automation.kilo_acceptance_pr import (
    ACCEPTANCE_BASE, ACCEPTANCE_BASE_SHA, publish_verified_pr,
)
from scripts.agents.automation.policy import is_eligible_mission

REPO = "khalidd692/telcoin-trading-intelligence99"
OWNER_LOGIN = "khalidd692"
OWNER_ID = 275517051
EVENT = "kilo-relay-event/v1"
HISTORICAL_ISSUES = {67, 94, 109, 112, 113, 114, 123}
CONFIG_KEY = "kilo-github/config"
CAMPAIGN = "kilo-campaign/v1"


def is_owner(user):
    return (isinstance(user, dict) and user.get("login") == OWNER_LOGIN
            and user.get("id") == OWNER_ID and user.get("type") == "User")


class KiloGitHubHandoff:
    def __init__(self, runtime, issue, mandate_id, mandate_sha, *, campaign=False,
                 fetcher=None, publisher=None, pr_publisher=None):
        if (issue <= 0 or mandate_id <= 0
                or issue in HISTORICAL_ISSUES and not (campaign and issue == 123)):
            raise ValueError("use a dedicated issue and a positive mandate comment ID")
        if not re.fullmatch(r"[0-9a-f]{64}", mandate_sha):
            raise ValueError("pin the exact UTF-8 mandate comment body with SHA-256")
        self.runtime = runtime
        self.issue = issue
        self.mandate_id = mandate_id
        self.mandate_sha = mandate_sha
        self.issue_endpoint = f"repos/{REPO}/issues/{issue}"
        self.fetch = fetcher or self.github
        self.post = publisher
        self.pr_publisher = pr_publisher or publish_verified_pr
        self.campaign = campaign
        self.source_valid = False
        self.waiting_for_github = False
        self.runtime.before_execute = self.before_execute
        config = {"repo": REPO, "issue": issue, "mandate_id": mandate_id, "mandate_sha256": mandate_sha}
        if campaign:
            config["campaign"] = True
        if runtime.store.get(CONFIG_KEY) is None:
            if runtime.store.keys("kilo-local"):
                raise ValueError("use a dedicated state directory for the GitHub queue")
            runtime.store.put_cas(CONFIG_KEY, config, None)
        if runtime.store.get(CONFIG_KEY) != config:
            raise ValueError("state is bound to another GitHub queue or mandate")

    def github(self, endpoint, *, body=None, method="GET", payload=None):
        runtime = self.runtime
        if runtime.stopped() or runtime.expired():
            raise OSError("session stopped or expired")
        remaining = 8 if runtime.deadline is None else runtime.deadline - time.monotonic()
        return gh_json(endpoint, body=body, method=method, payload=payload,
                       timeout=min(8, max(0.05, remaining)))

    def post_event(self, issue, body):
        if self.post is not None:
            return self.post(issue, body) if self.campaign else self.post(body)
        return self.github(f"repos/{REPO}/issues/{issue}/comments", body=body)

    def comment(self, cid):
        return self.fetch(f"repos/{REPO}/issues/comments/{cid}")

    def trusted(self, row, issue):
        return (isinstance(row, dict) and is_owner(row.get("user"))
                and row.get("issue_url") == f"https://api.github.com/repos/{REPO}/issues/{issue}"
                and type(row.get("id")) is int and row["id"] > 0
                and isinstance(row.get("created_at"), str)
                and row["created_at"] == row.get("updated_at"))

    def check_mandate(self):
        issue = self.fetch(self.issue_endpoint)
        mandate = self.comment(self.mandate_id)
        if (not isinstance(issue, dict) or issue.get("number") != self.issue
                or issue.get("state") != "open" or "pull_request" in issue
                or not self.trusted(mandate, self.issue) or mandate["id"] != self.mandate_id):
            raise ValueError("GitHub issue or mandate identity is invalid")
        body = mandate.get("body")
        if not isinstance(body, str) or hashlib.sha256(body.encode("utf-8")).hexdigest() != self.mandate_sha:
            raise ValueError("GitHub mandate bytes changed")
        contract = fenced_json(body, CAMPAIGN if self.campaign else "kilo-mandate/v1")
        labels = issue.get("labels")
        if (not contract or contract.get("repo") != REPO or type(contract.get("issue")) is not int
                or contract["issue"] != self.issue or not isinstance(contract.get("label"), str)
                or not approval_is_current(contract, datetime.now(timezone.utc))):
            raise ValueError("GitHub mandate scope, label or expiry is invalid")
        if self.campaign:
            contracts = contract.get("contracts")
            if (not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", contract["label"])
                    or contract["label"] == "tel99-mission"
                    or contract.get("base") != ACCEPTANCE_BASE
                    or contract.get("base_sha") != ACCEPTANCE_BASE_SHA
                    or not isinstance(contracts, dict) or len(contracts) != 2
                    or any(not re.fullmatch(r"[a-zA-Z0-9-]{1,48}", mid)
                           or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                           for mid, digest in contracts.items())
                    or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", mandate["created_at"])):
                raise ValueError("expected a bounded campaign with two pinned contracts and an isolated base")
            return {**contract, "created_at": mandate["created_at"]}
        if not isinstance(labels, list) or not is_eligible_mission(issue, contract["label"]):
            raise ValueError("GitHub mandate label is invalid")
        return contract

    def comments(self, issue):
        return fetch_comments(REPO, issue, fetcher=self.fetch)

    def approvals(self, comments, issue, scope):
        rows = (row for row in comments if self.trusted(row, issue))
        if self.campaign:
            rows = (row for row in rows if self.campaign_approval(row, issue, scope))
        return parse_approvals(rows,
                               mandate_comment_id=self.mandate_id, owner="kilo")

    def campaign_approval(self, row, issue, scope):
        payload = fenced_json(row.get("body"), "kilo-mission/v1") or {}
        mission, approval = payload.get("mission"), payload.get("approval")
        if not isinstance(mission, dict) or not isinstance(approval, dict):
            return False
        mid = mission.get("id")
        return (type(approval.get("issue")) is int and approval["issue"] == issue
                and row["created_at"] > scope["created_at"]
                and isinstance(mid, str) and mid in scope["contracts"]
                and scope["contracts"][mid] == fingerprint(mission))

    def eligible_campaign_issue(self, row, scope):
        number = row.get("number") if isinstance(row, dict) else None
        return (type(number) is int and number > self.issue and number not in HISTORICAL_ISSUES
                and row.get("state") == "open" and "pull_request" not in row
                and is_owner(row.get("user")) and isinstance(row.get("labels"), list)
                and is_eligible_mission(row, scope["label"])
                and isinstance(row.get("created_at"), str) and row["created_at"] > scope["created_at"]
                and isinstance(row.get("body"), str)
                and f"kilo-campaign: {self.mandate_id}" in row["body"].splitlines())

    def discover(self, scope):
        if not self.campaign:
            yield self.issue
            return
        query = urlencode({"state": "open", "labels": scope["label"], "since": scope["created_at"],
                           "per_page": 100})
        issues = fetch_pages(f"repos/{REPO}/issues?{query}", fetcher=self.fetch, max_pages=3)
        yield from sorted({row["number"] for row in issues if self.eligible_campaign_issue(row, scope)})

    def source(self):
        scope = self.check_mandate()
        store = self.runtime.store
        admitted, candidates = {}, {}
        for issue in self.discover(scope):
            data = self.approvals(self.comments(issue), issue, scope)
            if self.campaign and len(data["missions"]) > 1:
                raise ValueError("more than one approved campaign contract on an issue")
            for mission in data["missions"]:
                mid = mission["id"]
                if mid in candidates:
                    raise ValueError("campaign identity approved on multiple issues")
                binding = {"comment_id": data["sources"][mid],
                           "contract_sha256": data["approvals"][mid], "mission": mission}
                if self.campaign:
                    binding.update(issue=issue, base=scope["base"], base_sha=scope["base_sha"])
                candidates[mid] = binding
        for mid, binding in candidates.items():
            key = f"kilo-github/approvals/{mid}"
            if store.get(key) is None:
                store.put_cas(key, binding, None)
            if store.get(key) == binding:
                admitted[mid] = binding["mission"]
        # A removed or expired approval may no longer start a worker. It can
        # still reconcile a checkpoint that is already past the launch boundary.
        recoverable = {"RUNNING", "WORKER_EXITED", "ACCEPTED"} if self.campaign else {"RUNNING", "WORKER_EXITED"}
        for state in self.states():
            mid = state["id"]
            if mid in admitted or state["status"] not in recoverable:
                continue
            binding = store.get(f"kilo-github/approvals/{mid}")
            if binding and binding["contract_sha256"] == state["contract_sha256"]:
                admitted[mid] = binding["mission"]
        if len(admitted) > MAX_MISSIONS:
            raise ValueError("active missions and recovery checkpoints exceed the queue limit")
        self.source_valid = True
        return {"missions": list(admitted.values()),
                "approvals": {mid: fingerprint(mission) for mid, mission in admitted.items()}}

    def states(self):
        store = self.runtime.store
        for key in store.keys("kilo-local"):
            state = store.get(key)
            if isinstance(state, dict):
                yield state

    def event(self, phase, state, binding):
        event = {
            "event": EVENT, "phase": phase, "mission_id": state["id"],
            "issue": binding.get("issue", self.issue),
            "mandate_comment_id": self.mandate_id, "approval_comment_id": binding["comment_id"],
            "mandate_sha256": self.mandate_sha,
            "contract_sha256": binding["contract_sha256"], "scope": "synthetic-text",
            "status": "ACK" if phase == "ACK" else state["status"],
        }
        if phase == "ACK":
            event["execution_status"] = "NOT_STARTED"
        else:
            event["execution_status"] = state["execution_status"]
            if state.get("reason"):
                event["reason"] = state["reason"]
        if phase == "EVIDENCE":
            report = state["verification"]
            result = state["result"]
            cost = result.get("provider_evidence", {})
            event.update(artifact_sha256=report.get("artifact_sha256"),
                         verification_sha256=fingerprint(report),
                         checks=report.get("checks"), verifier=report.get("verifier"),
                         specialist=result.get("specialist_id"))
            for key in ("cost_usd", "catalog_sha256", "response_sha256"):
                if key in cost:
                    event[key] = cost[key]
            if self.campaign:
                for key in ("response_model", "http_status"):
                    if key in cost:
                        event[key] = cost[key]
        return event

    def receipt_url(self, row, event):
        issue = event["issue"]
        if not self.trusted(row, issue) or fenced_json(row.get("body"), EVENT) != event:
            return None
        url = f"https://github.com/{REPO}/issues/{issue}#issuecomment-{row['id']}"
        return url if row.get("html_url") == url else None

    def publish_once(self, phase, state, binding, *, evidence=None, pull_request=None):
        store = self.runtime.store
        key = f"kilo-github/outbox/{state['id']}/{phase}"
        event = self.event(phase, state, binding)
        if evidence is not None:
            event["evidence_url"] = evidence
        if pull_request is not None:
            event["pull_request_url"] = pull_request
        previous = store.get(key)
        if previous and previous.get("event") != event:
            return None
        if previous and previous.get("url"):
            return previous["url"]
        try:
            for row in self.comments(event["issue"]):
                url = self.receipt_url(row, event)
                if url:
                    # A receipt without a claim in this ledger belongs to another run.
                    if previous is None and phase == "ACK":
                        return None
                    return url if store.put_cas(key, {"event": event, "url": url}, previous) else None
            if previous is not None:
                # The POST might have reached GitHub. Only a read can reconcile it.
                return None
            if self.campaign and not self.current_approval(binding, state["id"]):
                return None
            pending = {"event": event}
            if not store.put_cas(key, pending, None):
                return None
            body = f"```{EVENT}\n{json.dumps(event, ensure_ascii=True, sort_keys=True)}\n```"
            url = self.receipt_url(self.post_event(event["issue"], body), event)
            if url and store.put_cas(key, {"event": event, "url": url}, pending):
                return url
        except (OSError, ValueError):
            pass
        return None

    def before_execute(self, mission, state):
        mid = mission["id"]
        binding = self.runtime.store.get(f"kilo-github/approvals/{mid}")
        if not binding or binding["contract_sha256"] != state["contract_sha256"]:
            self.waiting_for_github = True
            return False
        try:
            if self.campaign:
                self.sync_results()
                if self.waiting_for_github or any(
                    not (self.runtime.store.get(f"kilo-github/outbox/{dep}/RESULT") or {}).get("url")
                    for dep in mission["dependencies"]
                ):
                    self.waiting_for_github = True
                    return False
                if not self.current_approval(binding, mid):
                    self.waiting_for_github = True
                    return False
            if not self.publish_once("ACK", state, binding):
                self.waiting_for_github = True
                return False
            if self.current_approval(binding, mid):
                return True
        except (OSError, ValueError):
            pass
        self.waiting_for_github = True
        return False

    def current_approval(self, binding, mid):
        scope = self.check_mandate()
        issue = binding.get("issue", self.issue)
        if self.campaign and not self.eligible_campaign_issue(self.fetch(f"repos/{REPO}/issues/{issue}"), scope):
            return False
        current = self.approvals([self.comment(binding["comment_id"])], issue, scope)
        return (current["sources"].get(mid) == binding["comment_id"]
                and current["approvals"].get(mid) == binding["contract_sha256"])

    def publish_pull_request(self, state, binding, evidence):
        def authorized_api(endpoint, *, method="GET", payload=None):
            if method != "GET" and (method != "POST" or not self.current_approval(binding, state["id"])):
                raise ValueError("campaign approval changed before a GitHub write")
            return self.github(endpoint, method=method, payload=payload)

        return self.pr_publisher(REPO, binding["issue"], binding["base"], binding["base_sha"], state,
                                 evidence, api=authorized_api, store=self.runtime.store)

    def sync_results(self):
        store = self.runtime.store
        for state in self.states():
            if state.get("status") not in TERMINAL:
                continue
            mid = state["id"]
            binding = store.get(f"kilo-github/approvals/{mid}")
            ack = store.get(f"kilo-github/outbox/{mid}/ACK")
            if not binding or not ack or not ack.get("url"):
                continue
            result = store.get(f"kilo-github/outbox/{mid}/RESULT")
            if result and result.get("url"):
                continue
            evidence = None
            if state.get("verification"):
                evidence = self.publish_once("EVIDENCE", state, binding)
                if not evidence:
                    self.waiting_for_github = True
                    continue
            if state["status"] == "ACCEPTED" and not evidence:
                self.waiting_for_github = True
                continue
            pull_request = None
            if self.campaign and state["status"] == "ACCEPTED":
                try:
                    # The mandate and issue approval still govern external publication.
                    if self.current_approval(binding, mid):
                        pull_request = self.publish_pull_request(state, binding, evidence)
                except (OSError, ValueError):
                    pass
                if not pull_request:
                    self.waiting_for_github = True
                    continue
            if not self.publish_once("RESULT", state, binding, evidence=evidence, pull_request=pull_request):
                self.waiting_for_github = True

    def poll(self):
        self.source_valid = self.waiting_for_github = False
        ok = self.runtime.poll(self.source)
        if self.source_valid:
            self.sync_results()
        if self.waiting_for_github and not self.runtime.stopped():
            self.runtime.observe(STATE="BLOCKED", BLOCKER="GITHUB_RECEIPT_OR_APPROVAL_UNCONFIRMED")
        elif ok and not self.runtime.quota_exhausted:
            self.runtime.observe(BLOCKER=None)
        return ok and not self.waiting_for_github


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "status", "stop"))
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--issue", type=int)
    parser.add_argument("--mandate-comment", type=int)
    parser.add_argument("--mandate-sha256")
    parser.add_argument("--campaign", action="store_true", help="discover two separately approved synthetic issues")
    parser.add_argument("--seconds", type=int, choices=range(1, 3601), metavar="1..3600", default=300)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    runtime = Runtime(args.state)
    if args.action == "stop":
        (runtime.root / "stop.request").touch()
        print("STOP requested")
        return 0
    if args.action == "run":
        if not all((args.issue, args.mandate_comment, args.mandate_sha256)):
            parser.error("run requires --issue, --mandate-comment and --mandate-sha256")
        if runtime.stopped():
            print("STOP remains set; archive the marker before explicitly resuming")
            return 2
        runtime.deadline = time.monotonic() + args.seconds
        try:
            handoff = KiloGitHubHandoff(runtime, args.issue, args.mandate_comment, args.mandate_sha256,
                                       campaign=args.campaign)
            if not is_owner(handoff.github("user")):
                raise ValueError("the GitHub CLI must be authenticated as the pinned owner")
            failed = run_session(runtime, handoff.poll, once=args.once)
        except (Blocked, OSError, ValueError) as exc:
            print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
            return 2
    else:
        failed = False
    report = runtime.status()
    report["github_queue"] = runtime.store.get(CONFIG_KEY)
    report["github_receipts"] = {
        key.replace("\\", "/"): row.get("url") or "PENDING_RECONCILIATION"
        for key in runtime.store.keys("kilo-github/outbox") if (row := runtime.store.get(key))
    }
    print(json.dumps(report, ensure_ascii=True))
    return 2 if failed or any(row["status"] in {"BLOCKED", "REJECTED", "AWAITING_HUMAN", "ACK"}
                              for row in report["missions"].values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
