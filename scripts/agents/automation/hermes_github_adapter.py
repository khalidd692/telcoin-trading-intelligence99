"""CLI admission adapter: GitHub -> #124 Runtime -> Hermes worker -> verifier -> memory.

Reuses the existing engine end to end (Runtime/Supervisor, FileStore CAS,
Inbox ACK, MemoryStore, heartbeat, exclusive locks). Adds only:
  * the authenticated GitHub source (github_mission_source),
  * the real Hermes free-model executor (hermes_executor),
  * the fixed independent verifier (hermes_verifier),
  * idempotent GitHub ACK/result publication with durable CAS dedupe,
  * a durable relay event journal.

No second supervisor, bus, router or memory is created. STOP, crash-resume
and anti-duplicate semantics are exactly those of autonomy_runtime.py.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from autonomy_runtime import Runtime
from local_codex import exclusive, heartbeat
from protocol.handoff import Inbox
from hermes_executor import HermesExecutor, FREE_MODELS
from hermes_verifier import verify as hermes_verify
from github_mission_source import github_source, EVENT_MARKER

REPO = "khalidd692/telcoin-trading-intelligence99"
TERMINAL_PUBLISH = {"ACCEPTED", "REJECTED", "BLOCKED", "AWAITING_HUMAN"}
PAST_ACK = {"RUNNING", "WORKER_EXITED"} | TERMINAL_PUBLISH


def publish_comment(repo, issue, body, *, publisher=None):
    if publisher is not None:
        return publisher(body)
    payload = json.dumps({"body": body})
    try:
        completed = subprocess.run(
            ["gh", "api", "-X", "POST", f"repos/{repo}/issues/{issue}/comments", "--input", "-"],
            input=payload, capture_output=True, text=True, timeout=60, check=False)
    except subprocess.TimeoutExpired as exc:
        # Durable state is already claimed; publication is retried later (review F2).
        raise OSError("gh publish timeout") from exc
    if completed.returncode != 0:
        raise OSError("gh publish failed")
    return json.loads(completed.stdout).get("html_url", "")


def event_body(mid, status, state, *, issue=None, comment_id=None):
    event = {"event": EVENT_MARKER, "mission_id": mid, "status": status,
             "contract_sha256": state.get("contract_sha256"),
             "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "pid": os.getpid(), "issue": issue, "approval_comment_id": comment_id}
    result = state.get("result") or {}
    if result:
        event["artifact_sha256"] = result.get("sha256")
        event["session_id"] = result.get("session_id")
        event["model"] = result.get("model")
        event["specialist"] = result.get("specialist_id")
    if status in {"BLOCKED", "AWAITING_HUMAN"}:
        event["reason"] = state.get("reason")
    return ("```" + EVENT_MARKER + "\n" + json.dumps(event, ensure_ascii=True, indent=1)
            + "\n```\n<!-- récepteur Hermes : événement du relais, pas une nouvelle mission -->")


class AckInbox(Inbox):
    """Inbox that notifies the publisher exactly once per accepted claim."""

    def __init__(self, receiver_id, store, on_ack=None):
        super().__init__(receiver_id, store=store)
        self.on_ack = on_ack

    def receive(self, message, *, act=None):
        result = super().receive(message, act=act)
        if result.get("accepted") and self.on_ack is not None:
            try:
                self.on_ack(message["request_id"])
            except OSError:
                pass  # publication retried by Publisher.sync; never blocks execution
        return result


class Publisher:
    def __init__(self, runtime, repo, issue, *, publisher=None, enabled=True):
        self.r = runtime
        self.repo = repo
        self.issue = issue
        self.publisher = publisher
        self.enabled = enabled

    def _key(self, mid, phase):
        return f"hermes-relay-published/{mid}/{phase}"

    def _publish_once(self, mid, phase, body):
        key = self._key(mid, phase)
        if self.r.store.get(key) is not None:
            return
        if not self.enabled:
            return
        try:
            url = publish_comment(self.repo, self.issue, body, publisher=self.publisher)
        except (OSError, ValueError):
            return  # GitHub outage: durable state kept, publication retried later
        self.r.store.put_cas(key, {"phase": phase, "url": url, "at": time.time()}, None)

    def ack(self, mid):
        claim = self.r.store.get(f"kilo-claims/{mid}") or {}
        source = self.r.store.get(f"hermes-relay-source/{mid}") or {}
        self._publish_once(mid, "ACK", event_body(
            mid, "ACK", {"contract_sha256": claim.get("contract_sha256")},
            issue=self.issue, comment_id=source.get("comment_id")))

    def sync(self):
        for key in self.r.store.keys("kilo-local"):
            state = self.r.store.get(key)
            if not isinstance(state, dict) or "id" not in state:
                continue
            mid, status = state["id"], state.get("status")
            self._journal(mid, state)
            source = self.r.store.get(f"hermes-relay-source/{mid}") or {}
            if status in PAST_ACK:
                self._publish_once(mid, "ACK", event_body(
                    mid, "ACK", state, issue=self.issue, comment_id=source.get("comment_id")))
            if status in TERMINAL_PUBLISH:
                self._publish_once(mid, status, event_body(
                    mid, status, state, issue=self.issue, comment_id=source.get("comment_id")))

    def _journal(self, mid, state):
        key = f"hermes-relay-journal/{mid}"
        old = self.r.store.get(key) or {}
        status = state.get("status")
        if old.get("status") == status:
            return
        row = {"mission_id": mid, "status": status, "at": time.time(),
               "contract_sha256": state.get("contract_sha256"),
               "reason": state.get("reason")}
        result = state.get("result") or {}
        if result:
            row["artifact_sha256"] = result.get("sha256")
            row["session_id"] = result.get("session_id")
        with (self.r.root / "relay-events.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps(row, ensure_ascii=True) + "\n")
        self.r.store.put_cas(key, {"status": status}, old or None)


def build_runtime(state, *, model=FREE_MODELS[0], cli_exe=None, issue=None,
                  publisher=None, publish=True):
    executor = HermesExecutor(root=state, model=model,
                              cli_command=[cli_exe] if cli_exe else None)
    # Runtime expects a callable executor, not an object: bind .execute.
    runtime = Runtime(state, executor=executor.execute, verifier=hermes_verify)
    pub = Publisher(runtime, REPO, issue, publisher=publisher, enabled=publish)
    runtime.inbox = AckInbox("hermes-windows", store=runtime.store, on_ack=pub.ack)
    return runtime, pub


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "status", "stop"])
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--issue", type=int)
    parser.add_argument("--mandate-issue", type=int, default=67)
    parser.add_argument("--mandate-comment", type=int)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-tasks", type=int, default=20)
    parser.add_argument("--model", choices=FREE_MODELS, default=FREE_MODELS[0])
    parser.add_argument("--cli-exe")
    parser.add_argument("--no-publish", action="store_true")
    args = parser.parse_args(argv)
    runtime, pub = build_runtime(args.state, model=args.model, cli_exe=args.cli_exe,
                                 issue=args.issue, publish=not args.no_publish)
    if args.action == "stop":
        (runtime.root / "stop.request").touch()
        print("STOP requested")
        return 0
    if args.action == "status":
        report = runtime.status()
        report["published"] = {k: runtime.store.get(k) for k in runtime.store.keys("hermes-relay-published")}
        print(json.dumps(report, ensure_ascii=True))
        return 0
    if not args.issue or not args.mandate_comment:
        parser.error("run requires --issue and --mandate-comment")
    if not 1 <= args.seconds <= 3600:
        parser.error("seconds must be 1..3600")
    if runtime.stopped():
        print("STOP remains set; operator must explicitly acknowledge before run")
        return 2
    deadline = time.monotonic() + args.seconds
    runtime.deadline = deadline

    def source():
        payload = github_source(REPO, args.issue, args.mandate_issue, args.mandate_comment)
        for mid, comment_id in (payload.get("sources") or {}).items():
            runtime.store.put(f"hermes-relay-source/{mid}",
                              {"comment_id": comment_id, "issue": args.issue})
        return payload

    failed = False
    with exclusive(runtime.root / "session.lock"), heartbeat(runtime):
        while not runtime.stopped() and time.monotonic() < deadline:
            failed = not runtime.poll(source) or failed
            pub.sync()
            if args.once:
                break
            until = min(deadline, time.monotonic() + 10)
            while not runtime.stopped() and time.monotonic() < until:
                time.sleep(0.1)
    pub.sync()
    report = runtime.status()
    print(json.dumps(report, ensure_ascii=True))
    return 2 if failed or any(m["status"] in {"BLOCKED", "REJECTED", "AWAITING_HUMAN"}
                              for m in report["missions"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())
