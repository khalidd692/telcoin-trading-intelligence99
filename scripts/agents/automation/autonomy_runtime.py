"""Local mission transport of the existing Windows supervisor, using its durable bus.

Registry approvals for synthetic text and scoped code missions must be supplied
by a trusted operator; seal() computes fingerprints, not signatures.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, subprocess, sys, tempfile, time
from graphlib import TopologicalSorter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from local_codex import Supervisor, exclusive, Blocked, QuotaBlocked, heartbeat, heartbeat_status
from protocol.handoff import Inbox, verify_mission
from protocol.store import FileStore, StoreError
from intelligence.memory import MemoryStore, Entry
from intelligence import catalog
import local_codegen

ROLES=("tel99-analyst","tel99-dev","tel99-verifier")
TERMINAL={"ACCEPTED","REJECTED","BLOCKED","AWAITING_HUMAN"}
CHECKPOINT_STATUSES = TERMINAL | {"ACK", "RUNNING", "WORKER_EXITED"}
REJECTED_MISSION = "HERMES-QWEN4-20261121-C"
LEGACY_STOP = Path(__file__).resolve().parents[3] / ".kilo" / "STOP"
LOCAL_VERIFICATION_SECONDS = 75


class WorkerInterrupted(Blocked):
    pass


def fingerprint(m):
    return hashlib.sha256(json.dumps(m,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def seal(missions):
    return {m["id"]:fingerprint(m) for m in missions}


def mission_edges(mission):
    predecessor = mission.get("escalates_from")
    return [*mission["dependencies"], predecessor] if predecessor else mission["dependencies"]


def escalation_matches(mission, parent):
    keys = ("base_sha", "path", "function", "test", "sandbox_image", "objective")
    return (parent is not None and "routing" in parent
            and parent.get("max_attempts") == 2 and all(parent.get(key) == mission[key] for key in keys))


def delivered(missions, states):
    pending = {m["id"] for m in missions if states.get(m["id"]) != "ACCEPTED"}
    by_id = {m["id"]: m for m in missions}
    for mission in missions:
        prior = mission.get("escalates_from")
        if prior is None or not escalation_matches(mission, by_id.get(prior)):
            continue
        if states.get(prior) == "ACCEPTED":
            pending.discard(mission["id"])
        elif states.get(prior) == "BLOCKED" and states.get(mission["id"]) == "ACCEPTED":
            pending.discard(prior)
    return not pending


def validate_contract(m,approvals):
    if not isinstance(m,dict) or not re.fullmatch(r"[a-zA-Z0-9-]{1,48}",str(m.get("id",""))):
        raise ValueError("invalid mission id")
    if m["id"] in {REJECTED_MISSION, "night-mixed-ids"}:
        raise ValueError("historical rejected mission is permanently excluded")
    if approvals.get(m["id"]) != fingerprint(m):
        raise ValueError("unapproved or modified contract")
    if m.get("owner") == "local":
        if (not isinstance(m.get("objective"), str) or not 1 <= len(m["objective"]) <= 2000
                or not isinstance(m.get("dependencies"), list)
                or any(not isinstance(dep, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,48}", dep)
                       for dep in m["dependencies"])):
            raise ValueError("invalid local code objective or dependencies")
        local_codegen.validate_scope(m)
        return True
    # Additive owner allowlist for the Hermes failover relay (hermes/relay-github-adapter-20261120).
    # The engine, bus, CAS, ACK and memory paths are unchanged; only the admitted owner set grows.
    if (m.get("project")!="synthetic" or m.get("synthetic_data") is not True
        or m.get("owner") not in ("kilo","hermes") or m.get("specialist") not in ROLES
        or not isinstance(m.get("objective"),str) or not 1<=len(m["objective"])<=4000
        or not re.fullmatch(r"[0-9a-f]{64}",str(m.get("expected_sha256","")))
        or not isinstance(m.get("dependencies"),list)
        or any(not isinstance(x,str) or not re.fullmatch(r"[A-Za-z0-9-]{1,48}",x) for x in m["dependencies"])
        or any(k not in {"id","project","owner","priority","dependencies","specialist","synthetic_data","objective","expected_sha256"} for k in m)):
        raise ValueError("unsupported synthetic scope")
    return True

class Runtime(Supervisor):
    def __init__(self,root,executor=None,verifier=None,*,before_execute=None,legacy_stop=None):
        root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
        super().__init__(root)
        self.inbox=Inbox("kilo-windows",store=self.store)
        self._default_executor = self.execute_worker
        self.executor = executor or self._default_executor
        self.verifier=verifier or self.verify_worker
        self.before_execute = before_execute
        self.legacy_stop = legacy_stop
        self.quota_exhausted = False
    def bind_transport(self, transport):
        """Pin a working ledger to one entry point while allowing same-transport restart."""
        key = "runtime-config/transport"
        previous = self.store.read(key)
        if previous is None:
            legacy_kilo = self.store.get("kilo-github/config") is not None
            legacy_hermes = bool(self.store.keys("hermes-relay-source"))
            if (legacy_kilo and transport != "kilo-github"
                    or legacy_hermes and transport != "hermes-github"):
                raise Blocked("state belongs to another transport")
            try:
                self.store.put_cas(key, transport, None)
            except StoreError as exc:
                raise Blocked("cannot bind the state transport") from exc
            previous = self.store.read(key)
        if previous != transport:
            raise Blocked("state belongs to another transport")

    def state(self,m):
        key=f"kilo-local/{m['id']}"
        try:
            missing = object()
            value = self.store.read(key, default=missing)
        except (OSError, ValueError) as exc:
            raise Blocked("corrupt checkpoint") from exc
        if value is missing:
            return {}
        if not isinstance(value, dict) or not value:
            raise Blocked("corrupt checkpoint")
        return value
    def save(self,m,status,**details):
        old=self.state(m)
        value={**old,"id":m["id"],"project":m["project"],"status":status,
               "contract_sha256":fingerprint(m),"at":time.time(),
               "execution_status":("RUNNING" if status=="RUNNING" else "COMPLETED" if status in {"WORKER_EXITED","ACCEPTED","REJECTED"} else "NOT_STARTED" if status=="ACK" else "UNKNOWN"),**details}
        if not self.store.put_cas(f"kilo-local/{m['id']}",value,old or None):
            raise Blocked("checkpoint CAS conflict")
        self.observe(STATE=status,ACTIVE_TASK=m["id"] if status=="RUNNING" else None)
        print(json.dumps({"mission_id":m["id"],"status":status}),flush=True)
        return value
    def claim(self,m):
        return self.store.put_cas(f"kilo-claims/{m['id']}",
             {"contract_sha256":fingerprint(m),"project":m["project"],"at":time.time()},None)
    def expired(self):
        return self.deadline is not None and time.monotonic()>=self.deadline
    def stopped(self):
        return ((self.root / "stop.request").exists()
                or self.legacy_stop is not None and self.legacy_stop.exists())
    def worker_command(self,m):
        if m.get("owner") == "local":
            return [sys.executable, "-I", "-B", str(Path(__file__).with_name("local_codegen.py"))]
        return [sys.executable,"-B",str(Path(__file__).with_name("kilo_executor.py")),"worker"]
    def execute_worker(self, m, *, feedback=None, attempt=1, previous=None):
        command=self.worker_command(m)
        env={k:v for k,v in os.environ.items() if not k.upper().endswith(("_TOKEN","_KEY","_SECRET","_PASSWORD"))
             and not k.upper().startswith(("OPENAI_","ANTHROPIC_","GH_","GITHUB_","PYTHON"))}
        if m.get("owner") == "local":
            env = {k: v for k, v in env.items() if k.upper() in
                   {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR"}}
        scoped_retry = m.get("owner") == "local" and m.get("max_attempts", 1) > 1
        name = f"{m['id']}.attempt-{attempt}" if scoped_retry else m["id"]
        output = self.root / f"{name}.worker.json"
        error = self.root / f"{name}.worker.err"
        if feedback is None:
            if previous is not None:
                raise Blocked("previous candidate requires verifier feedback")
            request = m
        else:
            request = {"mission": m, "feedback": feedback}
        if previous is not None:
            request["previous"] = previous
        with tempfile.TemporaryFile() as worker_input, output.open("wb") as out, error.open("wb") as err:
            worker_input.write(json.dumps(request, ensure_ascii=False).encode("utf-8"))
            worker_input.seek(0)
            p=subprocess.Popen(command,stdin=worker_input,stdout=out,stderr=err,env=env,cwd=self.root)
            try:
                # Two sequential bounded Ollama calls only in the explicitly
                # sealed 3-role pilot; legacy single-agent workers keep 100 s.
                worker_seconds = 160 if m.get("team") else 100
                deadline=min(time.monotonic()+worker_seconds,self.deadline or float("inf"))
                while p.poll() is None:
                    if self.stopped() or time.monotonic()>deadline:
                        p.kill();p.wait(timeout=10)
                        raise WorkerInterrupted("worker stopped or timed out; no automatic replay")
                    time.sleep(.1)
                if p.returncode == 5:
                    raise QuotaBlocked("Kilo free provider HTTP 429")
                if p.returncode and not (m.get("owner") == "local" and p.returncode == 4):
                    raise Blocked("free specialist unavailable; no fallback")
            finally:
                if p.poll() is None:p.kill();p.wait(timeout=10)
        if output.stat().st_size>1024*1024:raise Blocked("worker output too large")
        response = json.loads(output.read_text(encoding="utf-8"))
        if p.returncode == 4:
            if not isinstance(response, dict) or response.get("status") != "BLOCKED":
                raise Blocked("invalid local generator failure receipt")
            reason = response.get("reason")
            if not isinstance(reason, str) or not 1 <= len(reason) <= 200:
                raise Blocked("invalid local generator diagnostic")
            feedback = response.get("feedback")
            raise local_codegen.GenerationBlocked(
                reason, feedback if feedback == {"kind": "empty-completion"} else None,
            )
        return response
    def verify_worker(self,m,result):
        if m.get("owner") == "local":
            return local_codegen.verify(m, result, self.root)
        from kilo_executor import verify
        return verify(m,result)
    def remember(self,m,saved):
        memory=MemoryStore(self.root/"memory")
        if memory.get(m["project"],m["id"]) is None:
            code = m.get("owner") == "local"
            evidence = {"contract_sha256": fingerprint(m), "artifact_sha256": saved["result"]["sha256"]}
            if code:
                evidence.update({key: saved["verification"][key] for key in
                                 ("base_sha", "path", "candidate_sha256", "diff_sha256", "test_sha256")})
            memory.record(Entry(id=m["id"],project=m["project"],kind="fact",
                title=("Verified code change " if code else "Verified synthetic artifact ")+m["id"],
                body=json.dumps(evidence),
                source="kilo-local/"+m["id"],author=m["specialist"],verified=True,
                verified_by=(saved.get("verification") or {}).get("verifier") or "independent-verifier",
                confidence=1.0))
    def _process(self, m, approvals, *, escalation=None):
        validate_contract(m,approvals)
        saved=self.state(m)
        if saved and saved.get("contract_sha256")!=fingerprint(m):
            raise Blocked("existing mission identity bound to different content")
        if saved and (saved.get("id") != m["id"] or saved.get("status") not in CHECKPOINT_STATUSES):
            raise Blocked("unrecognized prior checkpoint; reconciliation required")
        if saved.get("status")=="ACCEPTED":
            self.remember(m,saved);return
        if saved.get("status") in TERMINAL:return
        if self.legacy_stop is not None and (
                self.legacy_stop.parent / "state" / f"{m['id']}_state.json").exists():
            raise Blocked("legacy mission checkpoint exists; reconciliation required")
        if saved.get("status")=="RUNNING":
            self.save(m,"AWAITING_HUMAN",reason="uncertain worker outcome; never replay")
            return
        maximum = m.get("max_attempts", 1) if m.get("owner") == "local" else 1
        while self._attempt(m, saved, maximum, escalation or {}):
            saved = self.state(m)

    def escalation_options(self, mission, by_id):
        """Admit an approved successor only after a matching independent failure."""
        predecessor = mission.get("escalates_from")
        if predecessor is None:
            return {}
        parent = by_id.get(predecessor)
        if not escalation_matches(mission, parent):
            return None
        state = self.state(parent)
        route = state.get("model_route")
        selected = route.get("selection") if isinstance(route, dict) else None
        history = state.get("attempt_history")
        expected_attempts = parent.get("max_attempts", 1)
        if (state.get("status") != "BLOCKED" or state.get("contract_sha256") != fingerprint(parent)
                or expected_attempts != 2 or type(state.get("attempt")) is not int
                or state["attempt"] != expected_attempts
                or selected not in parent["routing"]["candidates"]
                or not isinstance(history, list) or len(history) != expected_attempts):
            return None
        test_sha = hashlib.sha256(parent["test"].encode("utf-8")).hexdigest()
        for number, attempt in enumerate(history, 1):
            proof = attempt.get("verification") if isinstance(attempt, dict) else None
            if (not isinstance(proof, dict) or type(attempt.get("number")) is not int or attempt["number"] != number
                    or proof.get("verifier") != local_codegen.VERIFIER
                    or proof.get("base_sha") != parent["base_sha"] or proof.get("path") != parent["path"]
                    or proof.get("test_sha256") != test_sha or proof.get("model") != selected["model"]
                    or proof.get("ok") is not False or not isinstance(proof.get("checks"), list)):
                return None
            checks = {c["name"]: c for c in proof["checks"]
                      if isinstance(c, dict) and isinstance(c.get("name"), str)}
            failed = checks.get("candidate-passes", {})
            if (any(checks.get(name, {}).get("ok") is not True for name in
                    ("bounded-model-receipt", "approved-function-diff", "baseline-fails"))
                    or failed.get("ok") is not False or type(failed.get("exit_code")) is not int
                    or failed["exit_code"] != 1):
                return None
        if history[-1]["verification"] != state.get("verification"):
            return None
        spec = catalog.by_id(selected["id"])
        if spec is None:
            return None
        return {"exclude": (selected["id"],), "minimum_memory_mib": spec.memory_mib + 1}

    def local_generation_times(self, mission):
        """Reuse the latest verified generation timings for these same local bindings."""
        rows = []
        for key in self.store.keys("kilo-local"):
            row = self.store.get(key)
            if not isinstance(row, dict) or row.get("status") not in {"ACCEPTED", "BLOCKED"}:
                continue
            route, proof = row.get("model_route"), row.get("verification")
            selection = route.get("selection") if isinstance(route, dict) else None
            if selection not in mission["routing"]["candidates"] or not isinstance(proof, dict):
                continue
            decision = route.get("decision")
            level = decision.get("difficulty") if isinstance(decision, dict) else None
            seconds, at = proof.get("generation_seconds"), row.get("at")
            if (proof.get("verifier") == local_codegen.VERIFIER and proof.get("model") == selection["model"]
                    and level in ("easy", "medium", "hard")
                    and type(seconds) in (int, float) and 0 <= seconds <= 80
                    and type(at) in (int, float) and 0 <= at < float("inf")):
                rows.append((at, level, selection["id"], seconds))
        samples = {}
        for _, level, model, seconds in sorted(rows, reverse=True)[:20]:
            samples.setdefault(level, {}).setdefault(model, []).append(seconds)
        return {level: {model: round(sum(values) / len(values), 3) for model, values in models.items()}
                for level, models in samples.items()}

    def _retry(self, m, saved, maximum, *, reason, feedback, verification=None):
        if maximum == 1 or not local_codegen.valid_feedback(feedback):
            return False
        number = saved["attempt"]
        diagnostic = {"number": number, "reason": reason, "feedback": feedback}
        if verification is not None:
            diagnostic["verification"] = verification
        history = [*saved.get("attempt_history", ()), diagnostic]
        retry = number < maximum
        keep_receipt = retry and feedback["kind"] == "candidate-test" and "candidate_sha256" in feedback
        self.save(m, "ACK" if retry else "BLOCKED", attempt_history=history,
                  feedback=feedback if retry else None, reason=reason,
                  result=saved["result"] if keep_receipt else None, verification=verification)
        return True

    def _attempt(self, m, saved, maximum, escalation):
        routed = "routing" in m
        effective = m
        if maximum > 1:
            history = saved.get("attempt_history", [])
            expected = len(history) if isinstance(history, list) else maximum
            feedback = saved.get("feedback")
            if (expected >= maximum or (expected > 0 and saved.get("status") == "ACK"
                    and (not local_codegen.valid_feedback(feedback)
                         or not isinstance(history[-1], dict)
                         or history[-1].get("number") != expected
                         or history[-1].get("feedback") != feedback))
                    or (saved.get("status") == "WORKER_EXITED" and (
                        type(saved.get("attempt")) is not int or saved["attempt"] != expected + 1))):
                self.save(m, "AWAITING_HUMAN", reason="invalid retry checkpoint; reconciliation required")
                return
        if saved.get("status")!="WORKER_EXITED":
            if saved.get("status") != "ACK":
                if not self.claim(m):
                    self.save(m,"AWAITING_HUMAN",reason="existing claim requires reconciliation")
                    return
                ack=self.inbox.receive({"request_id":m["id"]})
                if not ack["accepted"]:
                    self.save(m,"AWAITING_HUMAN",reason="existing ACK requires reconciliation");return
                saved = self.save(m,"ACK",execution_status="NOT_STARTED")
            claim = self.store.get(f"kilo-claims/{m['id']}")
            if (not isinstance(claim, dict) or claim.get("contract_sha256") != fingerprint(m)
                    or not self.inbox.seen(m["id"])):
                self.save(m, "AWAITING_HUMAN", reason="missing or mismatched claim or local ACK")
                return
            if self.stopped() or (self.before_execute is not None and not self.before_execute(m, saved)):
                return
            if self.stopped():return  # Keep the ACK so an explicit resume can start once.
            if self.expired():
                if m.get("owner") != "local":
                    self.save(m, "AWAITING_HUMAN", reason="session deadline after claim")
                return
            details = ({"attempt": len(saved.get("attempt_history", ())) + 1,
                        "reason": None, "verification": None} if maximum > 1 else {})
            if routed:
                route = saved.get("model_route")
                if escalation and isinstance(route, dict) and route.get("selection") is None:
                    route = None  # A deferred successor has no binding to restore.
                if route is None and saved.get("attempt_history"):
                    self.save(m, "AWAITING_HUMAN", reason="missing checkpoint model binding")
                    return
                try:
                    if route is None:
                        timings = self.local_generation_times(m)
                        options = {**escalation, **({"measured_seconds": timings} if timings else {})}
                        route = local_codegen.choose_route(m, **options)
                        if route.get("selection") is None:
                            status = "ACK" if escalation else "BLOCKED"
                            self.save(m, status, reason="no eligible verified local model", model_route=route)
                            return
                    effective = local_codegen.fixed_contract(m, route, **escalation)
                except (Blocked, OSError, ValueError, SyntaxError) as exc:
                    self.save(m, "AWAITING_HUMAN", reason="local model binding unavailable", error=type(exc).__name__)
                    return
                if self.stopped() or self.expired():
                    self.save(m, "ACK", model_route=route)
                    return
                if not local_codegen.check_selected(route["selection"]):
                    self.save(m, "AWAITING_HUMAN", reason="checkpoint model is no longer ready", model_route=route)
                    return
                if self.stopped() or self.expired():
                    self.save(m, "ACK", model_route=route)
                    return
                details["model_route"] = route
            running = self.save(m, "RUNNING", **details)
            if self.stopped():
                self.save(m, "ACK")  # This process knows it has not launched the worker yet.
                return
            try:
                if maximum > 1 and self.executor == self._default_executor:
                    previous = running.get("result")
                    retry_context = {"previous": previous["artifact"]} if isinstance(previous, dict) else {}
                    result = self.execute_worker(effective, feedback=running.get("feedback"),
                                                 attempt=running["attempt"], **retry_context)
                else:
                    result = self.executor(effective)
            except QuotaBlocked as exc:
                self.quota_exhausted = True
                self.save(m, "BLOCKED", reason=getattr(exc, "reason", "BLOCKED_PROVIDER_RATE_LIMIT"))
                return
            except local_codegen.GenerationBlocked as exc:
                if self._retry(m, running, maximum, reason=exc.reason, feedback=exc.feedback):
                    return self.state(m)["status"] == "ACK"
                self.save(m, "BLOCKED", reason=exc.reason)
                return
            except WorkerInterrupted as exc:
                self.save(m, "AWAITING_HUMAN" if m.get("owner") == "local" else "BLOCKED",
                          reason=str(exc))
                return
            except Exception as exc:
                self.save(m,"BLOCKED",reason=type(exc).__name__);return
            saved=self.save(m,"WORKER_EXITED",result=result)
        if self.stopped() or self.expired():
            return
        if (maximum > 1 and self.deadline is not None
                and self.deadline - time.monotonic() < LOCAL_VERIFICATION_SECONDS):
            return  # Keep the receipt for verification on explicit resume.
        try:
            if routed:
                effective = local_codegen.fixed_contract(m, saved.get("model_route"), **escalation)
            started = time.monotonic()
            verified = self.verifier(effective, saved["result"])
        except Exception as exc:
            self.save(m,"AWAITING_HUMAN",reason="independent verifier unavailable",error=type(exc).__name__);return
        if not isinstance(verified, dict) or verified.get("unavailable"):
            self.save(m,"AWAITING_HUMAN",reason="independent verifier unavailable");return
        if self.stopped() or self.expired():
            return
        if m.get("owner") == "local":
            verified = {**verified, "verification_seconds": round(time.monotonic() - started, 3)}
        checks = verified.get("checks")
        artifact = saved["result"].get("artifact") if isinstance(saved["result"], dict) else None
        code = m.get("owner") == "local"
        ok = (verified.get("ok") is True and isinstance(checks, list) and bool(checks)
              and all(isinstance(check, dict) and check.get("ok") is True for check in checks)
              and isinstance(verified.get("verifier"), str) and bool(verified["verifier"])
              and isinstance(artifact, str)
              and hashlib.sha256(artifact.encode("utf-8")).hexdigest() == verified.get("artifact_sha256")
              == saved["result"].get("sha256")
              and (verified.get("verifier") == local_codegen.VERIFIER
                   and verified.get("base_sha") == m["base_sha"] and verified.get("path") == m["path"]
                   and (not routed or verified.get("model") == effective["model"] == saved["result"].get("model"))
                   and {c.get("name") for c in checks} == {
                       "bounded-model-receipt", "approved-function-diff", "baseline-fails", "candidate-passes"}
                   if code else saved["result"].get("sha256") == m["expected_sha256"]))
        verdict=verify_mission(conversation_finished=True,roles={m["specialist"]:{"reported":True}},
             acceptance_checks=[{"id":"independent-code-contract" if code else "independent-text-contract",
                   "command":"isolated Docker baseline and candidate" if code else "fixed subprocess verifier",
                   "exit_code":0 if ok else 1,"reproducible":True,"output_digest":fingerprint(verified)}])
        feedback = verified.get("feedback")
        if (not verdict["validated"] and code and local_codegen.valid_feedback(feedback)
                and verified.get("ok") is False and isinstance(checks, list)
                and verified.get("verifier") == local_codegen.VERIFIER
                and verified.get("base_sha") == m["base_sha"] and verified.get("path") == m["path"]
                and (not routed or verified.get("model") == effective["model"] == saved["result"].get("model"))
                and isinstance(artifact, str)
                and hashlib.sha256(artifact.encode("utf-8")).hexdigest()
                == verified.get("artifact_sha256") == saved["result"].get("sha256")
                and feedback.get("candidate_sha256", verified["artifact_sha256"]) == verified["artifact_sha256"]):
            outcomes = {c["name"]: c.get("ok") for c in checks
                        if isinstance(c, dict) and isinstance(c.get("name"), str)}
            correctable = (
                feedback["kind"] == "candidate-diff" and outcomes.get("approved-function-diff") is False
                or feedback["kind"] == "candidate-test" and outcomes.get("baseline-fails") is True
                and outcomes.get("candidate-passes") is False
            )
            if correctable:
                if self._retry(m, saved, maximum, reason="independent verification rejected the candidate",
                               feedback=feedback, verification=verified):
                    return self.state(m)["status"] == "ACK"
        if verdict["validated"]:
            try:self.remember(m,{**saved, "verification": verified})
            except (OSError,ValueError):
                self.save(m,"AWAITING_HUMAN",reason="memory persistence unavailable");return
        status = "ACCEPTED" if verdict["validated"] else "REJECTED"
        details = {}
        if maximum > 1:
            details["feedback"] = None
            if status == "REJECTED" and saved["attempt"] >= maximum:
                status = "BLOCKED"
                details["reason"] = "attempt limit reached without independent verification"
        self.save(m, status, verification=verified, verdict=verdict, **details)
    def run_queue(self,missions,approvals,max_tasks=20):
        # Shared queue lock also prevents a second watcher declaring a live RUNNING
        # worker orphaned. Per-mission permanent CAS protects independent claimers.
        try:
            with exclusive(self.root/"runtime.lock"):
                count=0
                pending=list(missions)
                if len(pending)>20 or len({m.get("id") for m in pending})!=len(pending):
                    raise ValueError("bounded registry requires at most 20 unique identities")
                by_id={}
                invalid=False
                for m in pending:
                    try:
                        validate_contract(m,approvals)
                        saved=self.state(m)
                        if saved and saved.get("contract_sha256")!=fingerprint(m):
                            raise ValueError("identity content changed")
                        by_id[m["id"]]=m
                    except (ValueError,TypeError):
                        invalid=True
                TopologicalSorter({mid: mission_edges(m) for mid, m in by_id.items()}).prepare()
                pending=sorted(by_id.values(),key=lambda m:(str(m.get("priority","P9")),m["id"]))
                while pending and count<max_tasks and not self.stopped() and not self.expired() and not self.quota_exhausted:
                    progressed=False
                    for m in list(pending):
                        try:validate_contract(m,approvals)
                        except (ValueError,TypeError):pending.remove(m);continue
                        recovering = (self.before_execute is not None
                                      and self.state(m).get("status") in {"RUNNING", "WORKER_EXITED"})
                        if not recovering and any(d not in by_id or self.state(by_id[d]).get("status")!="ACCEPTED"
                                                  or self.state(by_id[d]).get("contract_sha256")!=fingerprint(by_id[d])
                                                  for d in m["dependencies"]):
                            continue
                        escalation = self.escalation_options(m, by_id)
                        if escalation is None:
                            continue
                        self._process(m, approvals, escalation=escalation)
                        pending.remove(m);count+=1;progressed=True
                        if self.stopped() or self.expired() or self.quota_exhausted or count>=max_tasks:break
                    if not progressed:break
                self.observe(STATE="STOPPED" if self.stopped() else "BLOCKED" if invalid else "IDLE",ACTIVE_TASK=None)
        except Blocked as exc:
            self.observe(STATE="BUSY" if "superviseur" in str(exc) and "cette file" in str(exc) else "BLOCKED",
                         BLOCKER=type(exc).__name__)
    def poll(self,source,max_tasks=20):
        try:
            data=source()
            self.run_queue(data["missions"],data["approvals"],max_tasks=max_tasks)
            return self.live["STATE"] not in {"BLOCKED","BUSY"}
        except (OSError,ValueError,KeyError):
            self.observe(STATE="BLOCKED",BLOCKER="SOURCE_UNAVAILABLE_OR_INVALID");return False
    def status(self):
        missions={}
        for key in self.store.keys("kilo-local"):
            value=self.store.get(key)
            if isinstance(value,dict):missions[value["id"]]={k:v for k,v in value.items() if k!="result"}
        health=heartbeat_status(self.root)
        observed=health.get("STATE","UNKNOWN")
        if self.stopped() and self.live["STATE"]=="STOPPED":observed="STOPPED"
        elif self.stopped() and observed!="STOPPED":observed="STOP_REQUESTED"
        elif self.live["STATE"]!="IDLE":observed=self.live["STATE"]
        return {"state":observed,"last_observed":health,"missions":missions,"quota":"unknown",
                "local_requires_pc_on":True,"cloud_connected":False}

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["run","status","stop"])
    p.add_argument("--state",type=Path,required=True)
    p.add_argument("--registry",type=Path)
    p.add_argument("--registry-sha256")
    p.add_argument("--local-code", action="store_true", help="admit approved local Python code missions")
    p.add_argument("--seconds",type=int,default=300)
    p.add_argument("--once",action="store_true")
    a=p.parse_args(argv);r=Runtime(a.state, legacy_stop=LEGACY_STOP)
    if a.action=="stop":
        (r.root/"stop.request").touch();print("STOP requested");return 0
    if a.action=="status":print(json.dumps(r.status(),ensure_ascii=True));return 0
    if not a.registry or not re.fullmatch(r"[0-9a-f]{64}",a.registry_sha256 or ""):
        p.error("trusted registry path and pinned SHA256 required")
    limit = 21600 if a.local_code else 3600
    if not 1 <= a.seconds <= limit:
        p.error(f"seconds must be 1..{limit}")
    if r.stopped():print("STOP remains set; operator must explicitly acknowledge before run");return 2
    try:
        r.bind_transport("local-code" if a.local_code else "kilo-local")
    except (Blocked, OSError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return 2
    deadline=time.monotonic()+a.seconds
    r.deadline=deadline
    expected = None
    def source():
        nonlocal expected
        raw=a.registry.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=a.registry_sha256:raise ValueError("registry changed")
        data = json.loads(raw)
        missions = data.get("missions") if isinstance(data, dict) else None
        owner = "local" if a.local_code else "kilo"
        if (not isinstance(missions, list) or not isinstance(data.get("approvals"), dict)
                or any(not isinstance(m, dict) or m.get("owner") != owner
                       or not isinstance(m.get("id"), str) for m in missions)):
            raise ValueError("registry owner does not match the selected local transport")
        expected = missions
        return data
    failed = run_session(r, lambda: r.poll(source), once=a.once)
    report=r.status()
    states = {mid: row["status"] for mid, row in report["missions"].items()}
    complete = (not failed and expected is not None and set(states) <= {m["id"] for m in expected}
                and delivered(expected, states))
    report["delivery"] = "COMPLETE" if complete and expected else "EMPTY" if complete else "INCOMPLETE"
    print(json.dumps(report))
    return 0 if complete else 2


def run_session(runtime, poll, *, once=False, done=None):
    """Run a bounded source poll using the existing lock and heartbeat."""
    failed = False
    with exclusive(runtime.root / "session.lock"), heartbeat(runtime):
        while not (runtime.stopped() or runtime.expired() or runtime.quota_exhausted):
            failed = not poll() or failed
            if once or runtime.quota_exhausted or (done is not None and done()):
                break
            until = min(runtime.deadline, time.monotonic() + 10)
            while not runtime.stopped() and time.monotonic() < until:
                time.sleep(.1)
    return failed


if __name__=="__main__":sys.exit(main())
