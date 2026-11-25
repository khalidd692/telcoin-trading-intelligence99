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
from protocol.store import CASConflict, FileStore, StoreError
from intelligence.memory import MemoryStore, Entry
from intelligence import catalog
import local_codegen

ROLES=("tel99-analyst","tel99-dev","tel99-verifier")
TERMINAL={"ACCEPTED","REJECTED","BLOCKED","AWAITING_HUMAN"}
CHECKPOINT_STATUSES = TERMINAL | {"PREPARING", "ACK", "RUNNING", "WORKER_EXITED"}
REJECTED_MISSION = "HERMES-QWEN4-20261121-C"
LEGACY_STOP = Path(__file__).resolve().parents[3] / ".kilo" / "STOP"
LOCAL_VERIFICATION_SECONDS = 75
EXECUTION_STATUS = {
    "PREPARING": "NOT_STARTED", "ACK": "NOT_STARTED", "RUNNING": "RUNNING",
    "WORKER_EXITED": "COMPLETED", "ACCEPTED": "COMPLETED", "REJECTED": "COMPLETED",
}


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


ERROR_TAXONOMY = (
    "MODEL_ERROR",
    "PROVIDER_ERROR",
    "ENVIRONMENT_ERROR",
    "CONTRACT_ERROR",
    "VERIFICATION_ERROR",
    "COORDINATION_ERROR",
)

PROJECT_FILE_REQUIRED_FIELDS = frozenset({
    "id", "owner", "project", "specialist", "priority", "dependencies", "objective",
    "workspace_root", "allowed_paths", "target_file",
})
PROJECT_FILE_OPTIONAL_FIELDS = frozenset({
    "task_profile", "max_attempts", "acceptance_criteria",
})


def classify_failure(reason: str | None, error: str | None = None) -> str:
    """Classify a failure into the 6 canonical TEL99 diagnostic categories."""
    blob = f"{reason or ''} {error or ''}".lower()
    if any(k in blob for k in ("lease", "collision", "casconflict", "conflict", "dependency", "claim")):
        return "COORDINATION_ERROR"
    if any(k in blob for k in ("contract", "unapproved", "scope", "traversal", "outside allowed", "invalid mission")):
        return "CONTRACT_ERROR"
    if any(k in blob for k in ("quota", "rate_limit", "429", "providererror", "ollama native api unavailable", "http status")):
        return "PROVIDER_ERROR"
    if any(k in blob for k in ("memory", "ram", "oom", "docker", "sandbox", "timeout", "timed out", "stop marker", "environment", "resourceunavailable", "resourcebusy")):
        return "ENVIRONMENT_ERROR"
    if any(k in blob for k in ("verifier", "assertion", "syntaxerror", "candidate-passes", "candidate-diff", "rejected")):
        return "VERIFICATION_ERROR"
    return "MODEL_ERROR"


def _safe_rel_path(value: object) -> bool:
    if not isinstance(value, str) or not value.strip() or len(value) > 240:
        return False
    norm = value.replace("\\", "/")
    if norm.startswith("/") or ":" in norm or norm.startswith("~"):
        return False
    parts = norm.split("/")
    return all(part not in ("", ".", "..") for part in parts)


def validate_project_file_contract(m: dict) -> bool:
    """Validate a bounded multi-project, multi-file contract without weakening TEL99 guards."""
    keys = set(m.keys())
    if not PROJECT_FILE_REQUIRED_FIELDS <= keys or (keys - PROJECT_FILE_REQUIRED_FIELDS - PROJECT_FILE_OPTIONAL_FIELDS):
        raise ValueError("invalid project-file contract fields")
    project = m.get("project")
    if not isinstance(project, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,47}", project) or project == "synthetic":
        raise ValueError("invalid project identifier for project-file contract")
    from scripts.agents.team_config import role_catalog
    valid_specialists = {spec.name for spec in role_catalog().values()}
    if m.get("specialist") not in valid_specialists:
        raise ValueError("unknown specialist in project-file contract")
    if not isinstance(m.get("objective"), str) or not 1 <= len(m["objective"]) <= 4000:
        raise ValueError("invalid project-file objective")
    deps = m.get("dependencies")
    if not isinstance(deps, list) or any(not isinstance(d, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,48}", d) for d in deps):
        raise ValueError("invalid project-file dependencies")
    ws = m.get("workspace_root")
    if not isinstance(ws, str) or not ws.strip() or ".." in Path(ws).parts or not Path(ws).is_absolute():
        raise ValueError("workspace_root must be a clean absolute path without '..'")
    allowed = m.get("allowed_paths")
    if not isinstance(allowed, list) or not 1 <= len(allowed) <= 20 or not all(_safe_rel_path(p) for p in allowed):
        raise ValueError("allowed_paths must contain 1..20 safe relative paths")
    target = m.get("target_file")
    if not _safe_rel_path(target) or target.replace("\\", "/") not in {p.replace("\\", "/") for p in allowed}:
        raise ValueError("target_file must be explicitly listed in allowed_paths")
    profile = m.get("task_profile", "module")
    if profile not in ("patch", "module", "large_module"):
        raise ValueError("invalid task_profile")
    max_attempts = m.get("max_attempts", 3)
    if type(max_attempts) is not int or not 1 <= max_attempts <= 4:
        raise ValueError("project-file max_attempts must be 1..4")
    return True


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
    if m.get("owner") == "project-file":
        return validate_project_file_contract(m)
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
    def __init__(self,root,executor=None,verifier=None,*,before_execute=None,legacy_stop=None,shared_memory_root=None,auto_recover_local_crash=False):
        root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
        super().__init__(root)
        self.inbox=Inbox("kilo-windows",store=self.store)
        self._default_executor = self.execute_worker
        self.executor = executor or self._default_executor
        self.verifier=verifier or self.verify_worker
        self.before_execute = before_execute
        self.legacy_stop = legacy_stop
        self.shared_memory_root = Path(shared_memory_root).resolve() if shared_memory_root is not None else (self.root / "memory")
        self.auto_recover_local_crash = bool(auto_recover_local_crash)
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
               "execution_status":EXECUTION_STATUS.get(status, "UNKNOWN"),**details}
        if not self.store.put_cas(f"kilo-local/{m['id']}",value,old or None):
            raise Blocked("checkpoint CAS conflict")
        self.observe(STATE=status, ACTIVE_TASK=m["id"] if status=="RUNNING" else None,
                     PHASE="WORKER" if status=="RUNNING" else None)
        print(json.dumps({"mission_id":m["id"],"status":status}),flush=True)
        return value
    def claim(self,m):
        return self.store.put_cas(f"kilo-claims/{m['id']}",
             {"contract_sha256":fingerprint(m),"project":m["project"],"at":time.time()},None)

    def claim_matches(self, mission):
        claim = self.store.get(f"kilo-claims/{mission['id']}")
        return (isinstance(claim, dict) and claim.get("contract_sha256") == fingerprint(mission)
                and claim.get("project") == mission["project"])

    def prepare_ack(self, mission, saved):
        mid = mission["id"]
        missing = object()
        try:
            claim = self.store.read(f"kilo-claims/{mid}", default=missing)
        except (OSError, ValueError) as exc:
            raise Blocked("invalid mission claim") from exc
        if not saved:
            if claim is not missing or self.inbox.seen(mid):
                self.save(mission, "AWAITING_HUMAN", reason="existing claim or ACK requires reconciliation")
                return None
            self.save(mission, "PREPARING")
        # PREPARING is only persisted before any ACK or worker launch. The
        # queue lock makes it safe to finish a partial claim after restart.
        if claim is missing:
            self.claim(mission)
        if not self.claim_matches(mission):
            self.save(mission, "AWAITING_HUMAN", reason="missing or mismatched claim")
            return None
        receipt = self.inbox.receive({"request_id": mid})["ack"]
        # receive() runs without an action here. Even a partial inbox claim
        # can be completed by the durable runtime ACK below.
        if (receipt.get("request_id") != mid or receipt.get("receiver") != self.inbox.receiver_id
                or receipt.get("status") not in {"claimed", "ACK"} or receipt.get("action") is not None):
            self.save(mission, "AWAITING_HUMAN", reason="existing ACK requires reconciliation")
            return None
        return self.save(mission, "ACK")
    def expired(self):
        return self.deadline is not None and time.monotonic()>=self.deadline
    def stopped(self):
        return ((self.root / "stop.request").exists()
                or self.legacy_stop is not None and self.legacy_stop.exists())
    def worker_command(self,m):
        if m.get("owner") == "local":
            return [sys.executable, "-I", "-B", str(Path(__file__).with_name("local_codegen.py"))]
        return [sys.executable,"-B",str(Path(__file__).with_name("kilo_executor.py")),"worker"]
    def _wait_for_ollama_ready(self, *, timeout: float = 20.0) -> None:
        """Avoid transient llama-server shutdown races between consecutive local missions."""
        from http.client import HTTPConnection
        from scripts.agents.automation import local_model_routing

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not self.stopped():
            avail = local_model_routing.available_memory_mib()
            models = None
            conn = HTTPConnection("127.0.0.1", 11434, timeout=1.5)
            try:
                conn.request("GET", "/api/ps")
                resp = conn.getresponse()
                if resp.status == 200:
                    payload = json.loads(resp.read(32_768))
                    models = payload.get("models") if isinstance(payload, dict) else []
            except (OSError, ValueError):
                return
            finally:
                conn.close()
            if (models == [] or models is None) and (avail is None or avail >= local_model_routing.AVAILABLE_MEMORY_RESERVE_MIB):
                return
            if models and avail is not None and avail >= local_model_routing.AVAILABLE_MEMORY_RESERVE_MIB:
                return
            time.sleep(0.75)

    def execute_worker(self, m, *, feedback=None, attempt=1, previous=None):
        if m.get("owner") == "local" and m.get("port") == 11434:
            self._wait_for_ollama_ready()
        command=self.worker_command(m)
        env={k:v for k,v in os.environ.items() if not k.upper().endswith(("_TOKEN","_KEY","_SECRET","_PASSWORD"))
             and not k.upper().startswith(("OPENAI_","ANTHROPIC_","GH_","GITHUB_","PYTHON"))}
        if m.get("owner") == "local":
            allowed_local_env = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR"}
            sdk_opt_in = os.environ.get("TEL99_EXECUTION_BACKEND", "").strip().lower() == "antigravity_sdk"
            if sdk_opt_in:
                allowed_local_env |= {
                    "TEL99_EXECUTION_BACKEND",
                    "TEL99_SDK_NO_FALLBACK",
                    "USERPROFILE",
                    "LOCALAPPDATA",
                }
            env = {k: v for k, v in env.items() if k.upper() in allowed_local_env}
        scoped_retry = m.get("owner") == "local" and m.get("max_attempts", 1) > 1
        name = f"{m['id']}.attempt-{attempt}" if scoped_retry else m["id"]
        output = self.root / f"{name}.worker.json"
        error = self.root / f"{name}.worker.err"
        lessons = []
        if m.get("owner") == "local" and self.shared_memory_root.exists():
            try:
                from scripts.agents.automation import learning_loop
                lessons = learning_loop.retrieve_lessons(self.shared_memory_root, m["project"], m)
            except (OSError, ValueError):
                lessons = []
        if feedback is None:
            if previous is not None:
                raise Blocked("previous candidate requires verifier feedback")
            request = {"mission": m, "lessons": lessons} if lessons else m
        else:
            request = {"mission": m, "feedback": feedback}
            if lessons:
                request["lessons"] = lessons
        if previous is not None:
            request["previous"] = previous
        with tempfile.TemporaryFile() as worker_input, output.open("wb") as out, error.open("wb") as err:
            worker_input.write(json.dumps(request, ensure_ascii=False).encode("utf-8"))
            worker_input.seek(0)
            p=subprocess.Popen(command,stdin=worker_input,stdout=out,stderr=err,env=env,cwd=self.root)
            try:
                # Two sequential bounded Ollama calls only in the explicitly
                # sealed 3-role pilot; legacy single-agent workers keep 100 s.
                sdk_opt_in = os.environ.get("TEL99_EXECUTION_BACKEND", "").strip().lower() == "antigravity_sdk"
                worker_seconds = 280 if (sdk_opt_in and m.get("team")) else (160 if m.get("team") else 100)
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
            project_file = m.get("owner") == "project-file"
            evidence = {"contract_sha256": fingerprint(m), "artifact_sha256": saved["result"]["sha256"]}
            if code:
                evidence.update({key: saved["verification"][key] for key in
                                 ("base_sha", "path", "candidate_sha256", "diff_sha256", "test_sha256")})
                if m.get("team"):
                    role = saved["verification"].get("verification_role", {})
                    trace = saved["result"].get("agent_trace", {})
                    analyst = trace.get("analyst", {}) if isinstance(trace, dict) else {}
                    if (role.get("role") != "tel99-verifier"
                            or not isinstance(analyst.get("sha256"), str)
                            or len(analyst["sha256"]) != 64):
                        raise ValueError("verified team trace is incomplete")
                    evidence["analyst_sha256"] = analyst["sha256"]
                    evidence["roles"] = m["team"]
            elif project_file:
                evidence.update({
                    "target_file": m["target_file"],
                    "project": m["project"],
                    "allowed_paths": list(m["allowed_paths"]),
                })
            title_prefix = (
                "Verified code change " if code
                else ("Verified project file " if project_file else "Verified synthetic artifact ")
            )
            entry = Entry(id=m["id"],project=m["project"],kind="fact",
                title=title_prefix + m["id"],
                body=json.dumps(evidence),
                source="kilo-local/"+m["id"],author=m["specialist"],verified=True,
                verified_by=(saved.get("verification") or {}).get("verifier") or "independent-verifier",
                confidence=1.0)
            memory.record(entry)
            if self.shared_memory_root != self.root / "memory":
                try:
                    shared = MemoryStore(self.shared_memory_root)
                    if shared.get(m["project"], m["id"]) is None:
                        shared.record(Entry(**entry.to_dict()), actor="runtime-shared-memory")
                except (OSError, ValueError):
                    pass
    def _can_auto_recover_local_crash(self, m, saved) -> tuple[bool, str]:
        if not self.auto_recover_local_crash:
            return False, "uncertain worker outcome; never replay"
        if m.get("owner") != "local":
            return False, "external worker crash requires human review"
        if int(saved.get("auto_recovery_count", 0)) >= 1:
            return False, "auto-recovery limit reached after repeated crash"
        if self.stopped():
            return False, "stop marker active during crash recovery"
        if not self.claim_matches(m) or not self.inbox.seen(m["id"]):
            return False, "missing claim or ACK receipt prevents safe auto-recovery"
        if self.store.get(f"kilo-github/outbox/{m['id']}/RESULT") is not None:
            return False, "irreversible RESULT receipt already recorded"
        for key in self.store.keys("github-local-code/PR"):
            rec = self.store.get(key)
            if key.endswith(f"/{m['id']}") or (isinstance(rec, dict) and rec.get("mission_id") == m["id"]):
                return False, "irreversible draft PR receipt already recorded"
        return True, "safe local crash auto-recovery"

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
            can_recover, reason = self._can_auto_recover_local_crash(m, saved)
            if not can_recover:
                self.save(m,"AWAITING_HUMAN",reason=reason)
                return
            count = int(saved.get("auto_recovery_count", 0)) + 1
            history = [*saved.get("recovery_history", ()), {"from": "RUNNING", "to": "ACK", "at": time.time()}]
            saved = self.save(
                m, "ACK",
                auto_recovery_count=count,
                recovery_history=history,
                reason="auto-recovered from interrupted local RUNNING checkpoint",
            )
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
        keep_receipt = not retry or (
            feedback["kind"] == "candidate-test" and "candidate_sha256" in feedback)
        saved_state = self.save(m, "ACK" if retry else "BLOCKED", attempt_history=history,
                                feedback=feedback if retry else None, reason=reason,
                                result=saved.get("result") if keep_receipt else None, verification=verification)
        if not retry and m.get("owner") == "local":
            try:
                from scripts.agents.automation import learning_loop
                learning_loop.record_outcome(self.shared_memory_root, m, saved_state)
            except (OSError, ValueError):
                pass
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
                saved = self.prepare_ack(m, saved)
                if saved is None:
                    return
            if not self.claim_matches(m) or not self.inbox.seen(m["id"]):
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
                        measured_quality = {}
                        quality_file = self.shared_memory_root.parent / "measured_quality.json"
                        if quality_file.is_file():
                            from scripts.agents.intelligence import router as intelligence_router
                            measured_quality = intelligence_router.load_measured_quality(str(quality_file))
                        options = {
                            **escalation,
                            **({"measured_seconds": timings} if timings else {}),
                            **({"measured_quality": measured_quality} if measured_quality else {}),
                        }
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
                blocked_state = self.save(m, "BLOCKED", reason=exc.reason)
                if m.get("owner") == "local":
                    try:
                        from scripts.agents.automation import learning_loop
                        learning_loop.record_outcome(self.shared_memory_root, m, blocked_state)
                    except (OSError, ValueError):
                        pass
                return
            except WorkerInterrupted as exc:
                self.save(m, "AWAITING_HUMAN" if m.get("owner") == "local" else "BLOCKED",
                          reason=str(exc))
                return
            except Exception as exc:
                blocked_state = self.save(m,"BLOCKED",reason=type(exc).__name__)
                if m.get("owner") == "local":
                    try:
                        from scripts.agents.automation import learning_loop
                        learning_loop.record_outcome(self.shared_memory_root, m, blocked_state)
                    except (OSError, ValueError):
                        pass
                return
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
            self.observe(STATE="WORKER_EXITED", ACTIVE_TASK=m["id"], PHASE="VERIFICATION")
            try:
                verified = self.verifier(effective, saved["result"])
            finally:
                self.observe(ACTIVE_TASK=None, PHASE=None)
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
        project_file = m.get("owner") == "project-file"
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
                   if code else (
                       verified.get("target_file") == m["target_file"]
                       and verified.get("project") == m["project"]
                       if project_file else saved["result"].get("sha256") == m["expected_sha256"]
                   )))
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
        if status in ("REJECTED", "BLOCKED"):
            details["error_class"] = classify_failure(
                details.get("reason") or status,
                str(verified.get("error") or ""),
            )
        final_state = self.save(m, status, verification=verified, verdict=verdict, **details)
        if m.get("owner") in ("local", "project-file") and status in ("ACCEPTED", "REJECTED", "BLOCKED"):
            try:
                from scripts.agents.automation import learning_loop
                learning_loop.record_outcome(self.shared_memory_root, m, final_state)
            except (OSError, ValueError):
                pass
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
        except (Blocked, CASConflict, StoreError) as exc:
            self.observe(STATE="BUSY" if "superviseur" in str(exc) and "cette file" in str(exc) else "BLOCKED",
                         BLOCKER=type(exc).__name__, ACTIVE_TASK=None, PHASE=None)
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
    p.add_argument("--poll-interval",type=int,default=30,metavar="SECONDS",
                   help="idle re-discovery sweep interval (default 30)")
    a=p.parse_args(argv);r=Runtime(a.state, legacy_stop=LEGACY_STOP)
    if a.action=="stop":
        (r.root/"stop.request").touch();print("STOP requested");return 0
    if a.action=="status":print(json.dumps(r.status(),ensure_ascii=True));return 0
    if not a.registry or not re.fullmatch(r"[0-9a-f]{64}",a.registry_sha256 or ""):
        p.error("trusted registry path and pinned SHA256 required")
    if not 1 <= a.poll_interval <= 3600:
        p.error("--poll-interval must be 1..3600")
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
    failed = run_session(r, lambda: r.poll(source), once=a.once, poll_interval=a.poll_interval)
    report=r.status()
    states = {mid: row["status"] for mid, row in report["missions"].items()}
    complete = (not failed and expected is not None and set(states) <= {m["id"] for m in expected}
                and delivered(expected, states))
    report["delivery"] = "COMPLETE" if complete and expected else "EMPTY" if complete else "INCOMPLETE"
    print(json.dumps(report))
    return 0 if complete and expected else 2


def run_session(runtime, poll, *, once=False, done=None, poll_interval=30):
    """Run a bounded source poll using the existing lock and heartbeat.

    poll_interval controls how long the loop sleeps between re-discovery
    sweeps when the queue is empty. A deadline is never mistaken for a
    request to re-poll: expired() returns True, so the loop exits.
    """
    failed = False
    with exclusive(runtime.root / "session.lock"), heartbeat(runtime):
        while not (runtime.stopped() or runtime.expired() or runtime.quota_exhausted):
            failed = not poll() or failed
            if once or runtime.quota_exhausted or (done is not None and done()):
                break
            if runtime.expired():
                break
            until = min(runtime.deadline, time.monotonic() + poll_interval)
            while not runtime.stopped() and time.monotonic() < until:
                if runtime.expired():
                    break
                time.sleep(.1)
    return failed


if __name__=="__main__":sys.exit(main())
