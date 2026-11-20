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

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.agents.automation.autonomy_runtime import (
    Blocked, QuotaBlocked, Runtime, TERMINAL, fingerprint, run_session,
)
from scripts.agents.automation.github_mission_source import (
    MAX_MISSIONS, approval_is_current, fetch_comments, fenced_json, gh_json, parse_approvals,
)

REPO = "khalidd692/telcoin-trading-intelligence99"
OWNER_LOGIN = "khalidd692"
OWNER_ID = 275517051
EVENT = "kilo-relay-event/v1"
HISTORICAL_ISSUES = {67, 94, 109, 112, 113, 114, 123}
CONFIG_KEY = "kilo-github/config"


def is_owner(user):
    return (isinstance(user, dict) and user.get("login") == OWNER_LOGIN
            and user.get("id") == OWNER_ID and user.get("type") == "User")


class KiloGitHubHandoff:
    def __init__(self, runtime, issue, mandate_id, mandate_sha, *, fetcher=None, publisher=None):
        if issue in HISTORICAL_ISSUES or issue <= 0 or mandate_id <= 0:
            raise ValueError("use a dedicated issue and a positive mandate comment ID")
        if not re.fullmatch(r"[0-9a-f]{64}", mandate_sha):
            raise ValueError("pin the exact UTF-8 mandate comment body with SHA-256")
        self.runtime = runtime
        self.issue = issue
        self.mandate_id = mandate_id
        self.mandate_sha = mandate_sha
        self.issue_endpoint = f"repos/{REPO}/issues/{issue}"
        self.fetch = fetcher or self.github
        self.post = publisher or self.post_event
        self.source_valid = False
        self.waiting_for_github = False
        self.runtime.before_execute = self.before_execute
        config = {"repo": REPO, "issue": issue, "mandate_id": mandate_id, "mandate_sha256": mandate_sha}
        if runtime.store.get(CONFIG_KEY) is None:
            if runtime.store.keys("kilo-local"):
                raise ValueError("use a dedicated state directory for the GitHub queue")
            runtime.store.put_cas(CONFIG_KEY, config, None)
        if runtime.store.get(CONFIG_KEY) != config:
            raise ValueError("state is bound to another GitHub queue or mandate")

    def github(self, endpoint, *, body=None):
        runtime = self.runtime
        if runtime.stopped() or runtime.expired():
            raise OSError("session stopped or expired")
        remaining = 8 if runtime.deadline is None else runtime.deadline - time.monotonic()
        return gh_json(endpoint, body=body, timeout=min(8, max(0.05, remaining)))

    def post_event(self, body):
        return self.github(f"{self.issue_endpoint}/comments", body=body)

    def comment(self, cid):
        return self.fetch(f"repos/{REPO}/issues/comments/{cid}")

    def trusted(self, row):
        return (isinstance(row, dict) and is_owner(row.get("user"))
                and row.get("issue_url") == f"https://api.github.com/{self.issue_endpoint}"
                and type(row.get("id")) is int and row["id"] > 0
                and isinstance(row.get("created_at"), str)
                and row["created_at"] == row.get("updated_at"))

    def check_mandate(self):
        issue = self.fetch(self.issue_endpoint)
        mandate = self.comment(self.mandate_id)
        if (not isinstance(issue, dict) or issue.get("number") != self.issue
                or issue.get("state") != "open" or "pull_request" in issue
                or not self.trusted(mandate) or mandate["id"] != self.mandate_id):
            raise ValueError("GitHub issue or mandate identity is invalid")
        body = mandate.get("body")
        if not isinstance(body, str) or hashlib.sha256(body.encode("utf-8")).hexdigest() != self.mandate_sha:
            raise ValueError("GitHub mandate bytes changed")
        contract = fenced_json(body, "kilo-mandate/v1")
        labels = issue.get("labels")
        if (not contract or contract.get("repo") != REPO or contract.get("issue") != self.issue
                or not isinstance(contract.get("label"), str) or not isinstance(labels, list)
                or not any(isinstance(label, dict) and label.get("name") == contract["label"] for label in labels)
                or not approval_is_current(contract, datetime.now(timezone.utc))):
            raise ValueError("GitHub mandate scope, label or expiry is invalid")

    def comments(self):
        return fetch_comments(REPO, self.issue, fetcher=self.fetch)

    def approvals(self, comments):
        return parse_approvals((row for row in comments if self.trusted(row)),
                               mandate_comment_id=self.mandate_id, owner="kilo")

    def source(self):
        self.check_mandate()
        data = self.approvals(self.comments())
        store = self.runtime.store
        admitted = {}
        for mission in data["missions"]:
            mid = mission["id"]
            key = f"kilo-github/approvals/{mid}"
            binding = {"comment_id": data["sources"][mid], "contract_sha256": data["approvals"][mid],
                       "mission": mission}
            if store.get(key) is None:
                store.put_cas(key, binding, None)
            if store.get(key) == binding:
                admitted[mid] = mission
        # A removed or expired approval may no longer start a worker. It can
        # still reconcile a checkpoint that is already past the launch boundary.
        for state in self.states():
            mid = state["id"]
            if mid in admitted or state["status"] not in {"RUNNING", "WORKER_EXITED"}:
                continue
            binding = store.get(f"kilo-github/approvals/{mid}")
            if binding and binding["contract_sha256"] == state["contract_sha256"]:
                admitted[mid] = binding["mission"]
        if len(admitted) > MAX_MISSIONS:
            raise ValueError("active missions and recovery checkpoints exceed the queue limit")
        data["missions"] = list(admitted.values())
        data["approvals"] = {mid: fingerprint(mission) for mid, mission in admitted.items()}
        self.source_valid = True
        return data

    def states(self):
        store = self.runtime.store
        for key in store.keys("kilo-local"):
            state = store.get(key)
            if isinstance(state, dict):
                yield state

    def event(self, phase, state, binding):
        event = {
            "event": EVENT, "phase": phase, "mission_id": state["id"], "issue": self.issue,
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
        return event

    def receipt_url(self, row, event):
        if not self.trusted(row) or fenced_json(row.get("body"), EVENT) != event:
            return None
        url = f"https://github.com/{REPO}/issues/{self.issue}#issuecomment-{row['id']}"
        return url if row.get("html_url") == url else None

    def publish_once(self, phase, state, binding, *, evidence=None):
        store = self.runtime.store
        key = f"kilo-github/outbox/{state['id']}/{phase}"
        event = self.event(phase, state, binding)
        if evidence is not None:
            event["evidence_url"] = evidence
        previous = store.get(key)
        if previous and previous.get("event") != event:
            return None
        if previous and previous.get("url"):
            return previous["url"]
        try:
            for row in self.comments():
                url = self.receipt_url(row, event)
                if url:
                    # A receipt without a claim in this ledger belongs to another run.
                    if previous is None and phase == "ACK":
                        return None
                    return url if store.put_cas(key, {"event": event, "url": url}, previous) else None
            if previous is not None:
                # The POST might have reached GitHub. Only a read can reconcile it.
                return None
            pending = {"event": event}
            if not store.put_cas(key, pending, None):
                return None
            body = f"```{EVENT}\n{json.dumps(event, ensure_ascii=True, sort_keys=True)}\n```"
            url = self.receipt_url(self.post(body), event)
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
            if not self.publish_once("ACK", state, binding):
                self.waiting_for_github = True
                return False
            self.check_mandate()
            current = self.approvals([self.comment(binding["comment_id"])])
            if current["approvals"].get(mid) == binding["contract_sha256"]:
                return True
        except (OSError, ValueError):
            pass
        self.waiting_for_github = True
        return False

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
            evidence = None
            if state.get("verification"):
                evidence = self.publish_once("EVIDENCE", state, binding)
                if not evidence:
                    self.waiting_for_github = True
                    continue
            if state["status"] == "ACCEPTED" and not evidence:
                self.waiting_for_github = True
                continue
            if not self.publish_once("RESULT", state, binding, evidence=evidence):
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
            handoff = KiloGitHubHandoff(runtime, args.issue, args.mandate_comment, args.mandate_sha256)
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
