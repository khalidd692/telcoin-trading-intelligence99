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
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from autonomy_runtime import LEGACY_STOP, REJECTED_MISSION, Runtime
from local_codex import exclusive, heartbeat, Blocked
from hermes_executor import HermesExecutor, FREE_MODELS
from hermes_verifier import verify as hermes_verify
from github_mission_source import (
    github_source, EVENT_MARKER, PROPOSAL_MARKER, fetch_comments, gh_json, is_owner,
)

REPO = "khalidd692/telcoin-trading-intelligence99"
TERMINAL_PUBLISH = {"ACCEPTED", "REJECTED", "BLOCKED", "AWAITING_HUMAN"}
PAST_ACK = {"RUNNING", "WORKER_EXITED"} | TERMINAL_PUBLISH
EVENT_BLOCK_RE = re.compile(r"```" + re.escape(EVENT_MARKER) + r"\s*\n(.*?)\n```", re.DOTALL)


def owner_receipt_url(row, repo, issue):
    if not isinstance(row, dict) or not is_owner(row.get("user")):
        return None
    cid = row.get("id")
    if type(cid) is not int or cid <= 0:
        return None
    url = f"https://github.com/{repo}/issues/{issue}#issuecomment-{cid}"
    if (row.get("issue_url") == f"https://api.github.com/repos/{repo}/issues/{issue}"
            and row.get("html_url") == url
            and isinstance(row.get("created_at"), str)
            and row["created_at"] == row.get("updated_at")):
        return url
    return None


def existing_events(repo, issue, *, fetcher=None):
    """Scan GitHub for already-published relay events (review F3 hardening).

    Returns {(mission_id, status): {"url": html_url, "contract_sha256": sha}},
    or None when the scan is unavailable so the caller skips publication and
    retries later instead of blind-posting a possible duplicate after a crash
    between POST and CAS. The contract fingerprint is returned so a same-id
    re-approval with different content is never mistaken for a crash recovery
    (réserve #126-4).
    """
    try:
        comments = fetch_comments(repo, issue, fetcher=fetcher)
    except (OSError, ValueError):
        return None
    found = {}
    for comment in comments:
        url = owner_receipt_url(comment, repo, issue)
        if not url or not isinstance(comment.get("body"), str):
            continue
        match = EVENT_BLOCK_RE.search(comment["body"])
        if not match:
            continue
        try:
            event = json.loads(match.group(1))
        except ValueError:
            continue
        if (isinstance(event, dict) and event.get("event") == EVENT_MARKER
                and event.get("issue") == issue and isinstance(event.get("mission_id"), str)
                and event.get("status") in (TERMINAL_PUBLISH | {"ACK"})):
            found[(event["mission_id"], event["status"])] = {
                "url": url,
                # Reserve: bind the recovery to the approved contract content,
                # not only to the (mission_id, phase) pair.
                "contract_sha256": event.get("contract_sha256"),
            }
    return found


def owner_approval_reader_for(state):
    """Read-only access to owner-direct approval artifacts (review point 3).

    The adapter NEVER writes this directory: an owner-direct approval must be
    placed by the owner outside the agent's publication path. Residual trust
    boundary (same-user machine) is documented in the runbook.
    """
    base = Path(state) / "owner-approvals"

    def read(mid):
        if not re.fullmatch(r"[a-zA-Z0-9-]{1,48}", str(mid)):
            return None
        try:
            return json.loads((base / f"{mid}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return read


def session_executed(states, session_start):
    """Mission ids that consumed an execution slot during this session.

    Only fresh state transitions (at >= session_start) past ACK count; old
    terminal missions skipped idempotently do not consume the session budget.
    """
    done = set()
    for state in states:
        if (isinstance(state, dict) and state.get("at", 0) >= session_start
                and state.get("status") in PAST_ACK and state.get("id")):
            done.add(state["id"])
    return done


def poll_budget(states, max_tasks):
    """Hard intra-poll cap (review R1): session budget + terminal skips.

    run_queue counts idempotent terminal skips against max_tasks; adding the
    current terminal count keeps the intra-poll NEW-execution bound equal to
    max_tasks, while session_executed caps the total across polls. Bounded by
    the engine's 20-mission registry limit.
    """
    terminal = sum(1 for s in states if isinstance(s, dict)
                   and s.get("status") in {"ACCEPTED", "REJECTED", "BLOCKED", "AWAITING_HUMAN"})
    return min(20, max_tasks + terminal)


def build_proposal_body(tasks):
    """Backlog -> PROPOSED events: never an approval, never executable."""
    payload = {"proposal": PROPOSAL_MARKER, "status": "PROPOSED",
               "note": ("Proposition IA issue du backlog documentaire. Approbation "
                        "proprietaire liee au contenu requise avant toute execution. "
                        "Aucune permission accordee ici."),
               "tasks": tasks,
               "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    return ("```" + PROPOSAL_MARKER + "\n" + json.dumps(payload, ensure_ascii=True, indent=1)
            + "\n```\n<!-- récepteur Hermes : proposition du relais, pas une mission approuvée -->")


def publish_comment(repo, issue, body, *, publisher=None):
    if publisher is not None:
        return publisher(body)
    row = gh_json(f"repos/{repo}/issues/{issue}/comments", body=body)
    return owner_receipt_url(row, repo, issue)


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


class Publisher:
    def __init__(self, runtime, repo, issue, *, publisher=None, enabled=True, scan=None):
        self.r = runtime
        self.repo = repo
        self.issue = issue
        self.publisher = publisher
        self.enabled = enabled
        self.scan = scan  # callable -> {(mid, phase): {"url","contract_sha256"}} | None

    def _key(self, mid, phase):
        return f"hermes-relay-published/{mid}/{phase}"

    def _publish_once(self, mid, phase, body, state):
        key = self._key(mid, phase)
        if mid == REJECTED_MISSION or self.r.stopped() or self.r.expired() or not self.enabled:
            return False
        previous = self.r.store.get(key)
        if previous and previous.get("url"):
            return True
        state_sha = state.get("contract_sha256")
        if self.scan is not None:
            events = self.scan()
            if events is None:
                return False
            recovered = events.get((mid, phase))
            if (isinstance(recovered, dict) and state_sha
                    and recovered.get("contract_sha256") == state_sha and recovered.get("url")):
                return self.r.store.put_cas(key, {"phase": phase, "url": recovered["url"],
                                                  "at": time.time(), "recovered": True}, previous)
        if previous is not None or self.r.stopped() or self.r.expired():
            return False
        pending = {"phase": phase, "contract_sha256": state_sha, "pending": True}
        if not self.r.store.put_cas(key, pending, None):
            return False
        try:
            url = publish_comment(self.repo, self.issue, body, publisher=self.publisher)
        except (OSError, ValueError):
            return False
        return bool(url) and self.r.store.put_cas(
            key, {"phase": phase, "url": url, "at": time.time()}, pending)

    def ack(self, mid):
        claim = self.r.store.get(f"kilo-claims/{mid}") or {}
        source = self.r.store.get(f"hermes-relay-source/{mid}") or {}
        return self._publish_once(mid, "ACK", event_body(
            mid, "ACK", {"contract_sha256": claim.get("contract_sha256")},
            issue=self.issue, comment_id=source.get("comment_id")),
            {"contract_sha256": claim.get("contract_sha256")})

    def sync(self):
        for key in self.r.store.keys("kilo-local"):
            state = self.r.store.get(key)
            if not isinstance(state, dict) or "id" not in state:
                continue
            mid, status = state["id"], state.get("status")
            if mid == REJECTED_MISSION or self.r.stopped() or self.r.expired():
                continue
            self._journal(mid, state)
            source = self.r.store.get(f"hermes-relay-source/{mid}") or {}
            if status in PAST_ACK and not self._publish_once(mid, "ACK", event_body(
                    mid, "ACK", state, issue=self.issue, comment_id=source.get("comment_id")), state):
                continue
            if status in TERMINAL_PUBLISH:
                self._publish_once(mid, status, event_body(
                    mid, status, state, issue=self.issue, comment_id=source.get("comment_id")), state)

    def _journal(self, mid, state):
        key = f"hermes-relay-journal/{mid}"
        old = self.r.store.get(key) or {}
        status = state.get("status")
        if old.get("status") == status:
            return
        # Append BEFORE the mark (réserve #126-5): a crash between the two
        # leaves an auditable at-least-once line instead of a lost event; the
        # CAS mark then dedupes the normal case (F4). A duplicate line after a
        # crash is deliberate and auditable, never a silently lost transition.
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
                  publisher=None, publish=True, scan=None):
    runtime = Runtime(state, verifier=hermes_verify, legacy_stop=LEGACY_STOP)
    executor = HermesExecutor(
        root=runtime.root, model=model, cli_command=[cli_exe] if cli_exe else None,
        stop_requested=lambda: runtime.stopped() or runtime.expired(),
    )
    runtime.executor = executor.execute
    pub = Publisher(runtime, REPO, issue, publisher=publisher, enabled=publish, scan=scan)
    runtime.inbox.receiver_id = "hermes-windows"
    if publish:
        def before_execute(mission, _state):
            pub.sync()
            return pub.ack(mission["id"])

        runtime.before_execute = before_execute
    return runtime, pub


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "status", "stop", "propose", "preflight"])
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--issue", type=int)
    parser.add_argument("--mandate-issue", type=int, default=67)
    parser.add_argument("--mandate-comment", type=int)
    parser.add_argument("--mandate-sha256", help="content SHA-256 of the pinned mandate comment")
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-tasks", type=int, default=20)
    parser.add_argument("--model", choices=FREE_MODELS, default=FREE_MODELS[0])
    parser.add_argument("--cli-exe")
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--backlog", type=Path)
    parser.add_argument("--task")
    args = parser.parse_args(argv)
    if args.action == "preflight":
        # No Runtime instance, no writable state, no worker invocation,
        # no publication. The source itself authenticates the mandate and
        # mission approvals; pin the exact UTF-8 body returned by gh api.
        if not args.issue or not args.mandate_comment:
            parser.error("preflight requires --issue and --mandate-comment")
        try:
            payload = github_source(
                REPO, args.issue, args.mandate_issue, args.mandate_comment,
                mandate_sha256=args.mandate_sha256)
            missions = [{"id": m["id"],
                         "contract_sha256": payload["approvals"][m["id"]]}
                        for m in payload["missions"]]
            print(json.dumps({
                "preflight": "OK" if missions else "NO_ADMISSIONS",
                "mandate_sha256": payload["mandate_sha256"],
                "missions": missions,
            }, ensure_ascii=True), flush=True)
            return 0 if missions else 2
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            print(json.dumps({"preflight": "BLOCKED",
                              "error": type(exc).__name__,
                              "detail": str(exc)[:300]}, ensure_ascii=True),
                  flush=True)
            return 2
    scan = (lambda: existing_events(REPO, args.issue)) if (args.issue and not args.no_publish) else None
    runtime, pub = build_runtime(args.state, model=args.model, cli_exe=args.cli_exe,
                                 issue=args.issue, publish=not args.no_publish, scan=scan)
    if args.action == "stop":
        (runtime.root / "stop.request").touch()
        print("STOP requested")
        return 0
    if args.action == "status":
        report = runtime.status()
        report["published"] = {k: runtime.store.get(k) for k in runtime.store.keys("hermes-relay-published")}
        print(json.dumps(report, ensure_ascii=True))
        return 0
    if args.action == "propose":
        if not args.issue:
            parser.error("propose requires --issue")
        backlog_path = args.backlog or (Path(__file__).resolve().parents[3]
                                        / "docs" / "agents" / "AUTONOMIE_ZERO_COPIER_COLLER" / "BACKLOG.json")
        backlog = json.loads(backlog_path.read_text(encoding="utf-8"))
        tasks = [t for t in backlog.get("tasks", [])
                 if t.get("owner") == "hermes" and t.get("initial_state") in ("todo", "in_progress")
                 and (not args.task or t.get("id") == args.task)]
        if not tasks:
            print("NO_ELIGIBLE_BACKLOG_TASK")
            return 0
        key = "hermes-relay-proposals/" + hashlib.sha256(
            json.dumps(sorted(t["id"] for t in tasks)).encode()).hexdigest()[:16]
        existing = runtime.store.get(key)
        if existing:
            print(json.dumps({"already_proposed": True, "url": existing.get("url")}))
            return 0
        body = build_proposal_body(tasks)
        if args.no_publish:
            print(json.dumps({"dry_run": True, "tasks": [t["id"] for t in tasks]}))
            return 0
        # Réserve: proposer sous le verrou de session — deux propositions
        # concurrentes ne doivent pas publier toutes les deux avant le CAS.
        try:
            with exclusive(runtime.root / "session.lock"):
                if runtime.store.get(key) is not None:
                    print(json.dumps({"already_proposed": True,
                                      "url": (runtime.store.get(key) or {}).get("url")}))
                    return 0
                url = publish_comment(REPO, args.issue, body)
                recorded = runtime.store.put_cas(key, {"url": url, "tasks": [t["id"] for t in tasks], "at": time.time()}, None)
        except Blocked:
            # verrou non bloquant détenu par un autre propose : already_proposed
            print(json.dumps({"already_proposed": True, "reason": "lock_held"}))
            return 0
        except (OSError, ValueError) as exc:
            print(json.dumps({"proposed": [], "error": type(exc).__name__}))
            return 1
        # R2: on CAS conflict a concurrent propose already recorded its own URL;
        # our POST may duplicate the PROPOSED comment (bounded impact: proposals
        # are never executable nor admitted as approvals). Flagged for audit.
        print(json.dumps({"proposed": [t["id"] for t in tasks], "url": url,
                          "cas_conflict": not recorded}))
        return 0
    if not args.issue or not args.mandate_comment:
        parser.error("run requires --issue and --mandate-comment")
    # Phase-2 bounded session ceiling: 2 h (engine CLI stays at 1 h).
    if not 1 <= args.seconds <= 7200:
        parser.error("seconds must be 1..7200")
    if not 1 <= args.max_tasks <= 20:
        parser.error("max-tasks must be 1..20")
    if runtime.stopped():
        print("STOP remains set; operator must explicitly acknowledge before run")
        return 2
    try:
        runtime.bind_transport("hermes-github")
    except (Blocked, OSError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return 2
    deadline = time.monotonic() + args.seconds
    runtime.deadline = deadline
    session_start = time.time()
    reader = owner_approval_reader_for(args.state)

    def source():
        payload = github_source(REPO, args.issue, args.mandate_issue, args.mandate_comment,
                                owner_approval_reader=reader,
                                mandate_sha256=args.mandate_sha256)
        for mid, comment_id in (payload.get("sources") or {}).items():
            runtime.store.put(f"hermes-relay-source/{mid}",
                              {"comment_id": comment_id, "issue": args.issue})
        return payload

    failed = False
    with exclusive(runtime.root / "session.lock"), heartbeat(runtime):
        while not runtime.stopped() and time.monotonic() < deadline:
            try:
                states = [runtime.store.get(k) for k in runtime.store.keys("kilo-local")]
                failed = not runtime.poll(source, max_tasks=poll_budget(states, args.max_tasks)) or failed
                pub.sync()
            except (OSError, ValueError, KeyError, TypeError, AttributeError, Blocked) as exc:
                # Réserve #126-2: un incident inattendu doit être fail-closed
                # (BLOCKED), jamais une boucle morte ni un repli payant.
                runtime.observe(STATE="BLOCKED", BLOCKER=type(exc).__name__)
                failed = True
                break
            executed = session_executed(
                [runtime.store.get(k) for k in runtime.store.keys("kilo-local")], session_start)
            if len(executed) >= args.max_tasks:
                runtime.observe(STATE="IDLE", NEXT="SESSION_BUDGET_REACHED")
                print(json.dumps({"session_budget_reached": sorted(executed),
                                  "max_tasks": args.max_tasks}), flush=True)
                break
            if args.once:
                break
            until = min(deadline, time.monotonic() + 10)
            while not runtime.stopped() and time.monotonic() < until:
                time.sleep(0.1)
    report = runtime.status()
    print(json.dumps(report, ensure_ascii=True))
    return 2 if failed or any(m["status"] != "ACCEPTED"
                              for m in report["missions"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())
