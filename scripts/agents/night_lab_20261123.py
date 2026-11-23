#!/usr/bin/env python3
"""TEL99 Night Lab: bounded local-code missions + role/skill audit + read-only dashboard.

Preserves current supervisor, worktrees and GitHub. Does not auto-merge/push or trade.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser

BASE = "2671228398ecfc18e506332bb9d5011266ceedd5"
IMAGE = "python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"
MODEL = "qwen2.5-3b-instruct"
REPO_NAME = "khalidd692/telcoin-trading-intelligence99"
ROLES = {
    "coordination": ["tests.test_autonomy_runtime", "tests.test_agent_handoff", "tests.test_agent_state_cas"],
    "development": ["tests.test_local_codegen", "tests.test_agent_native", "tests.test_local_codex"],
    "quant": ["tests.test_indicators", "tests.test_tradingview_quality"],
    "cloud": ["tests.test_cloud_autonomy", "tests.test_cloud_integration"],
    "quality": ["tests.test_autonomy_review_regressions", "tests.test_agent_evaluation_lab"],
    "security": ["tests.test_agent_approval", "tests.test_agent_platform_security"],
    "mobile": ["tests.test_agent_cockpit"],
    "documentation": ["tests.test_verification_plan_skill"],
    "evaluation": ["tests.test_oos_evaluation", "tests.test_evaluate_prospective"],
    "market_data": ["tests.test_publication_cadence", "tests.test_monitor"],
    "monitoring": ["tests.test_windows_diagnostic", "tests.test_agent_cockpit"],
    "release": ["tests.test_publication_gate", "tests.test_agent_project_kit"],
}

# Independent tests are fixed in code. Registry JSON is hashed and only passed to
# the existing local-code transport after explicit user execution of this script.
MISSIONS = [
  dict(id="night-save-path", path="docs/agents/autonomy-demo/tasks.py", function="save_tasks", dependencies=[],
       objective="Fix a real reliability bug: saving a task database to a nested path whose parent directory does not yet exist crashes. In save_tasks, create the destination's parent directories if needed, while preserving the existing JSON encoding and signature. No extra module imports.",
       test='''import json, subprocess, sys, tempfile
from pathlib import Path
with tempfile.TemporaryDirectory(dir="/scratch") as folder:
    db = Path(folder)/"nested"/"subdir"/"tasks.json"
    added = subprocess.run([sys.executable,"-I","-B","/work/program.py","--db",str(db),"add","trial"],capture_output=True,text=True,timeout=5)
    assert added.returncode == 0, added.stderr
    item = json.loads(added.stdout)
    assert item["title"] == "trial" and db.exists()
    assert json.loads(db.read_text(encoding="utf-8")) == [item]
'''),
  dict(id="night-protect-refs", path="scripts/agents/automation/policy.py", function="branch_is_protected", dependencies=[],
       objective="Fix a branch-protection bypass: GitHub ref strings such as refs/heads/main, refs/heads/master, refs/heads/tel99-live-data and refs/heads/codex/tel99-quant-terminal must be protected just like their corresponding short branch names. Preserve existing behavior for ordinary branches. Minimal standard-library-only change with same signature.",
       test='''import runpy
scope=runpy.run_path("/work/program.py")
f=scope["branch_is_protected"]
for value in ("main","master","tel99-live-data","codex/tel99-quant-terminal", "refs/heads/main", "refs/heads/master", "refs/heads/tel99-live-data", "refs/heads/codex/tel99-quant-terminal"):
    assert f(value) is True, value
for value in ("feature/safe", "refs/heads/feature/safe"):
    assert f(value) is False, value
'''),
  dict(id="night-mixed-ids", path="docs/agents/autonomy-demo/tasks.py", function="find_task_index", dependencies=["night-save-path"],
       objective="Fix a crash when older JSON task lists contain non-dict entries (null, strings, integers) before a valid task. Skip such malformed entries and records lacking id, but return the original index of the first matching dict id. Return None if absent. Keep the original signature and no new imports.",
       test='''import json, subprocess, sys, tempfile
from pathlib import Path
with tempfile.TemporaryDirectory(dir="/scratch") as folder:
    db=Path(folder)/"tasks.json"
    original=[None,"old",17,{"title":"legacy"},{"id":"ok","title":"old title","done":False}]
    db.write_text(json.dumps(original),encoding="utf-8")
    edited=subprocess.run([sys.executable,"-I","-B","/work/program.py","--db",str(db),"edit","ok","new title"],capture_output=True,text=True,timeout=5)
    assert edited.returncode == 0,edited.stderr
    result=json.loads(edited.stdout)
    assert result["title"] == "new title"
    assert json.loads(db.read_text())[:4] == original[:4]
    missing=subprocess.run([sys.executable,"-I","-B","/work/program.py","--db",str(db),"delete","missing"],capture_output=True,text=True,timeout=5)
    assert missing.returncode == 1 and json.loads(missing.stdout)["error"] == "Task not found"
'''),
]

HTML = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TEL99 · Night Lab</title><style>
:root{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color-scheme:dark;--bg:#0b111d;--panel:#151f30;--line:#2b3a52;--fg:#eaf3ff;--muted:#a8b7d0;--teal:#58d9c1}*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 95% 2%,#15374e 0,transparent 42%),var(--bg);color:var(--fg)}header{padding:22px max(18px,calc((100vw - 1280px)/2));border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}.brand{font-weight:800;letter-spacing:.04em}.brand span{color:var(--teal)}main{max-width:1280px;margin:auto;padding:24px 18px 70px}h1{font-size:clamp(2rem,5vw,3.4rem);line-height:1.1;margin:0 0 14px}h2{font-size:1.05rem;margin:0 0 13px}p{color:var(--muted);line-height:1.55}.hero{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap}.right{min-width:180px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:23px 0}.card,.panel{border:1px solid var(--line);background:linear-gradient(140deg,#172338,#111a2a);border-radius:16px;padding:18px}.num{font-size:2.05rem;font-weight:800;display:block}.hint{font-size:.79rem;color:var(--muted)}.layout{display:grid;grid-template-columns:1.4fr 1fr;gap:15px}.section{margin:18px 0}.rolegrid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.role{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:#111d2e}.tag{display:inline-block;border-radius:999px;background:#25394f;padding:3px 9px;font-size:.76rem;font-weight:700}.PASS,.ACCEPTED{color:#77ebbf}.FAIL,.BLOCKED,.REJECTED,.ERROR{color:#ffad98}.RUNNING{color:#fdd77a}.line{border-top:1px solid var(--line);padding:9px 0;font-size:.88rem;overflow-wrap:anywhere}.line:first-of-type{border-top:0}code{font-size:.83rem;color:#b7d3ff}small{color:var(--muted)}@media(max-width:850px){.layout{grid-template-columns:1fr}.rolegrid{grid-template-columns:repeat(2,1fr)}}@media(max-width:560px){.cards{grid-template-columns:repeat(2,1fr)}.rolegrid{grid-template-columns:1fr}}
</style></head><body><header><div class="brand">◆ TEL<span>99</span> / NIGHT LAB</div><small>Surveillance réelle · lecture seule · mise à jour toutes les 4 s</small></header><main><div class="hero"><div><p>LABORATOIRE AUTONOME · QWEN LOCAL + DOCKER</p><h1>La nuit des agents</h1><p id="subtitle">Lecture des preuves de ton PC…</p></div><div class="right"><span class="tag" id="phase">DÉMARRAGE</span><p id="updated"></p></div></div><div class="cards"><div class="card"><span class="num" id="gates">0</span><span class="hint">Suites testées</span></div><div class="card"><span class="num" id="success">0</span><span class="hint">Suites réussies</span></div><div class="card"><span class="num" id="missions">0</span><span class="hint">Missions CODE acceptées</span></div><div class="card"><span class="num" id="skills">0</span><span class="hint">Skills trouvés</span></div></div><div class="layout"><div><section class="panel section"><h2>12 domaines de responsabilité · preuves techniques</h2><p>Un domaine testé n'est pas un processus IA autonome. Les vrais rôles actifs sont distingués.</p><div id="roles" class="rolegrid"></div></section><section class="panel section"><h2>Travail de programmation local</h2><div id="tasks"></div></section></div><div><section class="panel section"><h2>Chronologie réelle</h2><div id="events"></div></section><section class="panel section"><h2>État de sécurité</h2><div id="safety"></div></section></div></div><p><small>Les propositions de code ne sont ni fusionnées ni publiées automatiquement. Aucun ordre de trading. Compteur HTTP indépendant au modèle non garanti.</small></p></main><script src="/dashboard.js"></script></body></html>'''
JS = r'''"use strict";
const el=id=>document.getElementById(id);
function set(id,v){el(id).textContent=String(v??"INCONNU")}
function make(tag,text,css){const x=document.createElement(tag);x.textContent=String(text??"");if(css)x.className=css;return x}
function renderRows(id,rows,fn){const box=el(id);box.replaceChildren();for(const row of rows)box.append(fn(row))}
async function tick(){try{const r=await fetch('/status.json',{cache:'no-store'});if(!r.ok)throw Error(r.status);const d=await r.json();set('phase',d.phase);set('subtitle',d.note||'Épreuve en cours');set('updated',d.updated||'');const results=Object.values(d.gates||{});set('gates',results.length);set('success',results.filter(x=>x.status==='PASS').length);set('missions',Object.values(d.missions||{}).filter(x=>x==='ACCEPTED').length);set('skills',(d.skills||[]).length);renderRows('roles',Object.entries(d.roles||{}),([name,x])=>{const e=make('div','','role');e.append(make('strong',name),make('div',x.status||'NON TESTÉ',x.status||''),make('small',x.detail||''));return e});renderRows('tasks',Object.entries(d.missions||{}),([name,status])=>{const e=make('div','','line');e.append(make('code',name+' · '),make('strong',status,status));return e});renderRows('events',(d.events||[]).slice(-35).reverse(),row=>make('div',(row.at||'')+' · '+(row.message||''),'line'));renderRows('safety',Object.entries(d.safety||{}),([name,val])=>make('div',name+': '+val,'line'));}catch(e){set('subtitle','Impossible de lire le statut local : '+e.message)}}tick();setInterval(tick,4000);'''


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def save(path, obj):
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)
    tmp = path.with_suffix(path.suffix + ".writing")
    tmp.write_text(raw + "\n", encoding="utf-8")
    os.replace(tmp, path)


def run_cmd(args, root, timeout, log):
    with log.open("w", encoding="utf-8") as out:
        try:
            proc = subprocess.run(args, cwd=str(root), stdout=out, stderr=subprocess.STDOUT, timeout=timeout, check=False)
            return proc.returncode
        except subprocess.TimeoutExpired:
            out.write("\nTIMEOUT: bounded process interrupted\n")
            return 124
        except OSError as e:
            out.write("\nSTART_ERROR: " + type(e).__name__ + "\n")
            return 127


def new_registry():
    ms=[]
    for m in MISSIONS:
        ms.append({**m, "owner":"local", "project":"tel99", "specialist":"tel99-dev", "priority":"P1",
                   "base_sha":BASE, "sandbox_image":IMAGE, "model":MODEL, "port":18089})
    def fp(m):
        return hashlib.sha256(json.dumps(m,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
    payload={"missions":ms,"approvals":{m["id"]:fp(m) for m in ms}}
    return payload,hashlib.sha256(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def audit_skills(root):
    dirs=[root/".agents"/"skills",root/".kilo"/"skills",root/".claude"/"skills",root/".github"/"skills",root/"skills"]
    rows=[]
    for p in dirs:
        if p.is_dir():
            for x in sorted(p.rglob("SKILL.md")):
                if x.is_file() and len(x.relative_to(root).parts)<=6:
                    rows.append(x.relative_to(root).as_posix())
    return rows[:300]


def serve(session, port):
    path=session/"status.json"
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get("Host") not in (f"127.0.0.1:{port}",f"localhost:{port}"):
                self.send_error(403);return
            if self.path == "/": body=HTML.encode();typ="text/html"
            elif self.path == "/dashboard.js": body=JS.encode();typ="application/javascript"
            elif self.path == "/status.json":
                try:
                    body=path.read_bytes()
                    if len(body)>512_000: raise ValueError()
                except (OSError,ValueError): body=b'{}'
                typ="application/json"
            else: self.send_error(404);return
            self.send_response(200);self.send_header("Content-Type",typ+"; charset=utf-8")
            self.send_header("Cache-Control","no-store");self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    with ThreadingHTTPServer(("127.0.0.1",port),Handler) as server:
        print(f"TEL99 DASHBOARD http://127.0.0.1:{port}/",flush=True)
        server.serve_forever()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=["run","serve","selftest"])
    parser.add_argument("--repo",type=Path)
    parser.add_argument("--session",type=Path)
    parser.add_argument("--hours",type=float,default=6)
    parser.add_argument("--port",type=int,default=8791)
    a=parser.parse_args()
    if a.command=="selftest":
        reg,pin=new_registry(); assert len(reg["missions"])==3 and len(pin)==64
        assert len(ROLES)==12 and all(len(m["test"])<=8000 for m in MISSIONS)
        print("NIGHT_LAB_SELFTEST_OK");return 0
    if a.command=="serve":
        if not a.session or not a.session.is_dir():parser.error("--session must exist")
        serve(a.session,a.port);return 0
    if not a.repo or not a.repo.is_dir():parser.error("--repo must be an existing TEL99 worktree")
    if not .25 <= a.hours <= 12:parser.error("--hours must be between .25 and 12")
    root=a.repo.resolve()
    if not (root/"scripts/agents/automation/local_codegen.py").exists():
        raise SystemExit("Local CODE worker absent; stop before running")
    session=a.session or (Path.home()/"Desktop"/("TEL99_GRANDE_NUIT_"+datetime.now().strftime("%Y%m%d-%H%M%S")))
    session.mkdir(parents=True,exist_ok=False)
    lock=session/"campaign.lock"
    lock.write_text(str(os.getpid()))
    state={"phase":"PREFLIGHT","note":"Vérification des dépendances locales", "updated":now(),
           "gates":{},"missions":{},"roles":{role:{"status":"NON TESTÉ","detail":"Rôle logique, pas processus IA"} for role in ROLES},
           "skills":[],"events":[],"safety":{"merge":"DÉSACTIVÉ","trading":"INTERDIT","paid_models":"NON UTILISÉS","HTTP_calls":"NON COMPTÉS"}}
    def publish(msg,phase=None):
        if phase:state["phase"]=phase
        state["note"]=msg;state["updated"]=now()
        state["events"].append({"at":now(),"message":msg})
        state["events"]=state["events"][-120:]
        save(session/"status.json",state)
        print("[TEL99] "+msg,flush=True)
    def gate(key,cmd,timeout=240,role=None):
        if (session/"STOP_NUIT").exists():
            publish("STOP demandé avant "+key,"STOPPED");return False
        publish("Tests : "+key,"TESTS")
        safe=key.replace("/","-").replace(" ","-")
        code=run_cmd(cmd,root,timeout,session/(safe+".log"))
        status="PASS" if code==0 else "FAIL"
        state["gates"][key]={"status":status,"exit_code":code,"log":safe+".log"}
        if role:
            state["roles"][role]={"status":status,"detail":"Tests techniques, pas agent autonome"}
        publish(f"{key}: {status} (code {code})")
        return code==0
    publish("Séance TEL99 créée : aucune ancienne preuve modifiée")
    if shutil.which("pwsh") is None or shutil.which("docker") is None:
        publish("PowerShell 7 ou Docker introuvable", "BLOCKED");return 2
    try:
        result=subprocess.run(["git","-C",str(root),"cat-file","-e",BASE+"^{commit}"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
        if result.returncode:raise RuntimeError("Commit Git de base absent")
        with urllib.request.urlopen("http://127.0.0.1:18089/health",timeout=5) as u:
            if json.load(u).get("status")!="ok":raise RuntimeError("Qwen non prêt")
        result=subprocess.run(["docker","image","inspect",IMAGE],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
        if result.returncode:raise RuntimeError("Image Docker épinglée absente")
    except Exception as e:
        publish("Pré-vol bloqué : "+str(e),"BLOCKED");return 2
    state["skills"]=audit_skills(root)
    publish(f"Pré-vol OK : Qwen, Docker et Git ; {len(state['skills'])} Skills inventoriés")
    # Start a dashboard on loopback, separate from the existing read-only cockpit :8787.
    if a.port:
        try:
            devnull=(session/"dashboard.log").open("w",encoding="utf-8")
            flags=getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0)
            subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve()),"serve","--session",str(session),"--port",str(a.port)],
                             cwd=str(root),stdin=subprocess.DEVNULL,stdout=devnull,stderr=subprocess.STDOUT,creationflags=flags)
            devnull.close()
            publish(f"Cockpit vivant : http://127.0.0.1:{a.port}/")
        except OSError:
            publish("Cockpit séparé indisponible ; preuves toujours conservées")
    deadline=time.monotonic()+a.hours*3600
    # Real test groups mapped to role responsibilities. No claim that 12 separate
    # LLMs execute these tests; each is an independent subprocess and log.
    for role, modules in ROLES.items():
        if time.monotonic()>deadline or (session/"STOP_NUIT").exists():break
        gate("role-"+role,[sys.executable,"-B","-m","unittest",*modules],timeout=240,role=role)
    if time.monotonic()<deadline and not (session/"STOP_NUIT").exists():
        gate("all-python-tests",[sys.executable,"-B","-m","unittest","discover","-s","tests","-p","test_*.py"],timeout=1000)
    if shutil.which("node") and time.monotonic()<deadline and not (session/"STOP_NUIT").exists():
        gate("node-dashboard-and-realtime",["node","--test","tests/test_dashboard.js","tests/test_realtime.js"],timeout=240)
    else:
        state["gates"]["node-dashboard-and-realtime"]={"status":"SKIPPED","reason":"Node unavailable or time budget/STOP"};save(session/"status.json",state)
    if time.monotonic()<deadline and not (session/"STOP_NUIT").exists():
        reg,pin=new_registry()
        raw=json.dumps(reg,sort_keys=True,indent=2,ensure_ascii=False)
        registry=session/"registry.json";registry.write_text(raw,encoding="utf-8")
        pin=hashlib.sha256(registry.read_bytes()).hexdigest()
        (session/"registry.sha256").write_text(pin+"\n",encoding="ascii")
        worker_state=session/"code-state"
        publish("3 NOUVELLES missions de correction bornées → superviseur TEL99", "CODE")
        cmd=["pwsh","-NoProfile","-NonInteractive","-File",str(root/"start-agents.ps1"),"-Action","RUN","-LocalCode",
             "-State",str(worker_state),"-Registry",str(registry),"-RegistrySha256",pin,"-Seconds","900","-Once"]
        with (session/"code-missions.log").open("w",encoding="utf-8") as log:
            proc=subprocess.Popen(cmd,cwd=str(root),stdout=log,stderr=subprocess.STDOUT)
            begun=time.monotonic()
            while proc.poll() is None:
                if (session/"STOP_NUIT").exists() or time.monotonic()-begun>915:
                    subprocess.run(["pwsh","-NoProfile","-File",str(root/"start-agents.ps1"),"-Action","STOP","-LocalCode","-State",str(worker_state)],
                                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
                    proc.wait(timeout=25)
                    break
                time.sleep(3)
        # Read only the durable status; do not falsely infer it from a log string.
        snapshot=run_cmd(["pwsh","-NoProfile","-File",str(root/"start-agents.ps1"),"-Action","STATUS","-LocalCode","-State",str(worker_state)],root,30,session/"code-status.json")
        try:
            status=json.loads((session/"code-status.json").read_text(encoding="utf-8")) if snapshot==0 else {}
            state["missions"]={mid:record.get("status","UNKNOWN") for mid,record in status.get("missions",{}).items()}
        except (ValueError,KeyError):
            status={};state["missions"]={}
        code_ok=all(state["missions"].get(m["id"])=="ACCEPTED" for m in reg["missions"])
        state["gates"]["new-code-missions"]={"status":"PASS" if code_ok else "FAIL","log":"code-missions.log"}
        publish("Génération CODE terminée : "+str(state["missions"]))
        # Re-run same checkpoint to test idempotence, never new approval.
        if code_ok and time.monotonic()<deadline:
            replay=run_cmd(cmd,root,45,session/"replay.log")
            state["gates"]["no-replay-check"]={"status":"PASS" if replay==0 else "FAIL","exit_code":replay,"note":"No independent HTTP call count"}
            publish("Relance sans erreur : "+str(replay))
        # Combined proposals remain separate by default; independently audited
        # source/diff under `code-state/verified-code`. No git writes.
    # 2nd health and regression verification after code missions.
    if time.monotonic()<deadline and not (session/"STOP_NUIT").exists():
        gate("post-code-safety-regressions",[sys.executable,"-B","-m","unittest","tests.test_agent_approval","tests.test_agent_state_cas","tests.test_local_codegen","tests.test_agent_platform_security"],timeout=300)
    publish("Épreuves principales terminées ; surveillance nocturne limitée", "SOAK")
    loop=0
    while time.monotonic()<deadline and not (session/"STOP_NUIT").exists():
        loop+=1
        try:
            with urllib.request.urlopen("http://127.0.0.1:18089/health",timeout=5) as u:
                healthy=json.load(u).get("status")=="ok"
        except Exception:healthy=False
        state["gates"]["qwen-health"]={"status":"PASS" if healthy else "FAIL","observations":loop}
        publish(f"Surveillance {loop} : Qwen "+("OK" if healthy else "INDISPONIBLE"))
        if not healthy:publish("Arrêt prudent : serveur Qwen indisponible","BLOCKED");break
        if loop%4==0:
            gate("soak-check-"+str(loop),[sys.executable,"-B","-m","unittest","tests.test_agent_cockpit","tests.test_agent_state_cas"],timeout=120)
        for _ in range(60):
            if time.monotonic()>=deadline or (session/"STOP_NUIT").exists():break
            time.sleep(15)  # health check every ~15 minutes; sleeps are interruptible
    if (session/"STOP_NUIT").exists():publish("Arrêt manuel demandé : aucune nouvelle mission","STOPPED")
    elif state["phase"]!="BLOCKED":publish("Session terminée ; vérifier les statuts et journaux", "COMPLETE")
    # Morning summary of what was actually done, no invented passes.
    report=session/"LIRE_AU_REVEIL.md"
    lines=["# TEL99 — Rapport du réveil",f"",f"Date UTC : {now()}",f"Statut : {state['phase']}","",
           "## Rôles / domaines (tests techniques, pas processus IA autonomes)"]
    lines += [f"- {k}: {v['status']} — {v['detail']}" for k,v in state['roles'].items()]
    lines += ["","## Missions de programmation (candidates isolées)"]
    lines += [f"- {k}: {v}" for k,v in state['missions'].items()]
    lines += ["","## Suites et journaux"]
    lines += [f"- {k}: {v.get('status')} — {v.get('log','')}" for k,v in state['gates'].items()]
    lines += ["","## Contrôles non démontrés","- Pas de mesure indépendante du nombre d'appels HTTP au modèle.",
              "- Pas d'activité indépendante démontrée pour les 12 processus IA.",
              "- Pas d'ordre financier, de merge GitHub, de push ni de déploiement.",
              "- Les correctifs générés ne sont pas appliqués au dépôt : inspecter code-state/verified-code.",""]
    report.write_text("\n".join(lines),encoding="utf-8")
    print(f"[TEL99] RAPPORT DU REVEIL : {report}",flush=True)
    return 0 if state["phase"]=="COMPLETE" else 2

if __name__ == "__main__":
    sys.exit(main())