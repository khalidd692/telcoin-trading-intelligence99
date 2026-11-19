"""Kilo transport extension of the existing Windows supervisor, without a second bus.

Only content-pinned synthetic text missions are executable. Registry approvals must
be supplied by a trusted operator; seal() computes fingerprints, not signatures.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from local_codex import Supervisor, exclusive, Blocked, heartbeat, heartbeat_status
from protocol.handoff import Inbox, verify_mission
from protocol.store import FileStore
from intelligence.memory import MemoryStore, Entry

ROLES=("tel99-analyst","tel99-dev","tel99-verifier")
TERMINAL={"ACCEPTED","REJECTED","BLOCKED","AWAITING_HUMAN"}
def fingerprint(m):
    return hashlib.sha256(json.dumps(m,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def seal(missions):
    return {m["id"]:fingerprint(m) for m in missions}
def validate_contract(m,approvals):
    if not isinstance(m,dict) or not re.fullmatch(r"[a-zA-Z0-9-]{1,48}",str(m.get("id",""))):
        raise ValueError("invalid mission id")
    if approvals.get(m["id"]) != fingerprint(m):
        raise ValueError("unapproved or modified contract")
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
    def __init__(self,root,executor=None,verifier=None):
        root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
        super().__init__(root)
        self.inbox=Inbox("kilo-windows",store=self.store)
        self.executor=executor or self.execute_worker
        self.verifier=verifier or self.verify_worker
    def state(self,m):
        key=f"kilo-local/{m['id']}"
        path=self.store._path(key)
        value=self.store.get(key)
        if path.exists() and not isinstance(value,dict):raise Blocked("corrupt checkpoint")
        return value or {}
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
        return (self.root/"stop.request").exists()
    def worker_command(self,m):
        return [sys.executable,"-B",str(Path(__file__).with_name("kilo_executor.py")),"worker"]
    def execute_worker(self,m):
        command=self.worker_command(m)
        env={k:v for k,v in os.environ.items() if not k.upper().endswith(("_TOKEN","_KEY","_SECRET","_PASSWORD"))
             and not k.upper().startswith(("OPENAI_","ANTHROPIC_","GH_","GITHUB_","PYTHON"))}
        output=self.root/f"{m['id']}.worker.json"
        error=self.root/f"{m['id']}.worker.err"
        with output.open("wb") as out,error.open("wb") as err:
            p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=out,stderr=err,env=env,cwd=self.root)
            try:
                p.stdin.write(json.dumps(m).encode());p.stdin.close()
                deadline=min(time.monotonic()+100,self.deadline or float("inf"))
                while p.poll() is None:
                    if self.stopped() or time.monotonic()>deadline:
                        p.kill();p.wait(timeout=10)
                        raise Blocked("worker stopped or timed out; no automatic replay")
                    time.sleep(.1)
                if p.returncode:raise Blocked("free specialist unavailable; no fallback")
            finally:
                if p.poll() is None:p.kill();p.wait(timeout=10)
        if output.stat().st_size>1024*1024:raise Blocked("worker output too large")
        return json.loads(output.read_text(encoding="utf-8"))
    @staticmethod
    def verify_worker(m,result):
        from kilo_executor import verify
        return verify(m,result)
    def remember(self,m,saved):
        memory=MemoryStore(self.root/"memory")
        if memory.get(m["project"],m["id"]) is None:
            memory.record(Entry(id=m["id"],project=m["project"],kind="fact",
                title="Verified synthetic artifact "+m["id"],
                body=json.dumps({"contract_sha256":fingerprint(m),"artifact_sha256":saved["result"]["sha256"]}),
                source="kilo-local/"+m["id"],author=m["specialist"],verified=True,
                verified_by="tel99-fixed-subprocess-v1",confidence=1.0))
    def _process(self,m,approvals):
        validate_contract(m,approvals)
        saved=self.state(m)
        if saved and saved.get("contract_sha256")!=fingerprint(m):
            raise Blocked("existing mission identity bound to different content")
        if saved.get("status")=="ACCEPTED":
            self.remember(m,saved);return
        if saved.get("status") in TERMINAL:return
        if saved.get("status")=="RUNNING":
            self.save(m,"AWAITING_HUMAN",reason="uncertain worker outcome; never replay")
            return
        if saved.get("status")!="WORKER_EXITED":
            if not self.claim(m):
                self.save(m,"AWAITING_HUMAN",reason="existing claim requires reconciliation")
                return
            ack=self.inbox.receive({"request_id":m["id"]})
            if not ack["accepted"]:
                self.save(m,"AWAITING_HUMAN",reason="existing ACK requires reconciliation");return
            self.save(m,"ACK",execution_status="NOT_STARTED")
            if self.stopped():self.save(m,"AWAITING_HUMAN",reason="STOP after claim");return
            if self.expired():self.save(m,"AWAITING_HUMAN",reason="session deadline after claim");return
            self.save(m,"RUNNING")
            try:result=self.executor(m)
            except Exception as exc:
                self.save(m,"BLOCKED",reason=type(exc).__name__);return
            saved=self.save(m,"WORKER_EXITED",result=result)
        try:
            verified=self.verifier(m,saved["result"])
        except Exception as exc:
            self.save(m,"AWAITING_HUMAN",reason="independent verifier unavailable",error=type(exc).__name__);return
        if verified.get("unavailable"):
            self.save(m,"AWAITING_HUMAN",reason="independent verifier unavailable");return
        ok=verified.get("ok") is True and bool(verified.get("checks"))
        verdict=verify_mission(conversation_finished=True,roles={m["specialist"]:{"reported":True}},
             acceptance_checks=[{"id":"independent-text-contract","command":"fixed subprocess verifier",
                   "exit_code":0 if ok else 1,"reproducible":True,"output_digest":fingerprint(verified)}])
        if verdict["validated"]:
            try:self.remember(m,saved)
            except (OSError,ValueError):
                self.save(m,"AWAITING_HUMAN",reason="memory persistence unavailable");return
        self.save(m,"ACCEPTED" if verdict["validated"] else "REJECTED",verification=verified,verdict=verdict)
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
                pending=sorted(by_id.values(),key=lambda m:(str(m.get("priority","P9")),m["id"]))
                while pending and count<max_tasks and not self.stopped() and not self.expired():
                    progressed=False
                    for m in list(pending):
                        try:validate_contract(m,approvals)
                        except (ValueError,TypeError):pending.remove(m);continue
                        if any(d not in by_id or self.state(by_id[d]).get("status")!="ACCEPTED"
                               or self.state(by_id[d]).get("contract_sha256")!=fingerprint(by_id[d])
                               for d in m["dependencies"]):
                            continue
                        self._process(m,approvals)
                        pending.remove(m);count+=1;progressed=True
                        if self.stopped() or self.expired() or count>=max_tasks:break
                    if not progressed:break
                self.observe(STATE="STOPPED" if self.stopped() else "BLOCKED" if invalid else "IDLE",ACTIVE_TASK=None)
        except Blocked as exc:
            self.observe(STATE="BUSY" if "superviseur" in str(exc) and "cette file" in str(exc) else "BLOCKED",
                         BLOCKER=type(exc).__name__)
    def poll(self,source):
        try:
            data=source()
            self.run_queue(data["missions"],data["approvals"])
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
        if self.stopped() and observed!="STOPPED":observed="STOP_REQUESTED"
        elif self.live["STATE"]!="IDLE":observed=self.live["STATE"]
        return {"state":observed,"last_observed":health,"missions":missions,"quota":"unknown",
                "local_requires_pc_on":True,"cloud_connected":False}

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["run","status","stop"])
    p.add_argument("--state",type=Path,required=True)
    p.add_argument("--registry",type=Path)
    p.add_argument("--registry-sha256")
    p.add_argument("--seconds",type=int,default=300)
    p.add_argument("--once",action="store_true")
    a=p.parse_args(argv);r=Runtime(a.state)
    if a.action=="stop":
        (r.root/"stop.request").touch();print("STOP requested");return 0
    if a.action=="status":print(json.dumps(r.status(),ensure_ascii=True));return 0
    if not a.registry or not re.fullmatch(r"[0-9a-f]{64}",a.registry_sha256 or ""):
        p.error("trusted registry path and pinned SHA256 required")
    if not 1<=a.seconds<=3600:p.error("seconds must be 1..3600")
    if r.stopped():print("STOP remains set; operator must explicitly acknowledge before run");return 2
    deadline=time.monotonic()+a.seconds
    r.deadline=deadline
    def source():
        raw=a.registry.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=a.registry_sha256:raise ValueError("registry changed")
        return json.loads(raw)
    failed=False
    with exclusive(r.root/"session.lock"), heartbeat(r):
        while not r.stopped() and time.monotonic()<deadline:
            failed=not r.poll(source) or failed
            if a.once:break
            until=min(deadline,time.monotonic()+10)
            while not r.stopped() and time.monotonic()<until:time.sleep(.1)
    report=r.status()
    print(json.dumps(report))
    return 2 if failed or any(m["status"] in {"BLOCKED","REJECTED","AWAITING_HUMAN"} for m in report["missions"].values()) else 0
if __name__=="__main__":sys.exit(main())
