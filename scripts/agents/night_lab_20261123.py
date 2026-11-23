#!/usr/bin/env python3
"""TEL99 Night Lab: bounded local-code missions + role/skill audit + read-only dashboard.

Preserves current supervisor, worktrees and GitHub. Does not auto-merge/push or trade.
"""
from __future__ import annotations
import argparse
from graphlib import TopologicalSorter
from datetime import datetime, timezone
import hashlib
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from threading import Thread
import time

ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.agents.automation.autonomy_runtime import (
    LEGACY_STOP, Runtime, delivered, escalation_matches, mission_edges, validate_contract,
)
from local_codex import Blocked, exclusive
from protocol.store import FileStore
from scripts.agents.native import sandbox
from scripts.agents.native.mission import MissionError
from scripts.agents.team_config import role_catalog

STOP_GRACE = 70
STATE_VERSION = 1
LEGACY_MISSIONS = {"night-protect-refs", "night-save-path", "night-mixed-ids"}

HTML = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TEL99 · Night Lab</title><style>
:root{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color-scheme:dark;--bg:#0b111d;--panel:#151f30;--line:#2b3a52;--fg:#eaf3ff;--muted:#a8b7d0;--teal:#58d9c1}*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 95% 2%,#15374e 0,transparent 42%),var(--bg);color:var(--fg)}header{padding:22px max(18px,calc((100vw - 1280px)/2));border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}.brand{font-weight:800;letter-spacing:.04em}.brand span{color:var(--teal)}main{max-width:1280px;margin:auto;padding:24px 18px 70px}h1{font-size:clamp(2rem,5vw,3.4rem);line-height:1.1;margin:0 0 14px}h2{font-size:1.05rem;margin:0 0 13px}p{color:var(--muted);line-height:1.55}.hero{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap}.right{min-width:180px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:23px 0}.card,.panel{border:1px solid var(--line);background:linear-gradient(140deg,#172338,#111a2a);border-radius:16px;padding:18px}.num{font-size:2.05rem;font-weight:800;display:block}.hint{font-size:.79rem;color:var(--muted)}.layout{display:grid;grid-template-columns:1.4fr 1fr;gap:15px}.section{margin:18px 0}.rolegrid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.role{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:#111d2e}.tag{display:inline-block;border-radius:999px;background:#25394f;padding:3px 9px;font-size:.76rem;font-weight:700}.PASS,.ACCEPTED{color:#77ebbf}.FAIL,.BLOCKED,.REJECTED,.ERROR{color:#ffad98}.RUNNING{color:#fdd77a}.line{border-top:1px solid var(--line);padding:9px 0;font-size:.88rem;overflow-wrap:anywhere}.line:first-of-type{border-top:0}code{font-size:.83rem;color:#b7d3ff}small{color:var(--muted)}@media(max-width:850px){.layout{grid-template-columns:1fr}.rolegrid{grid-template-columns:repeat(2,1fr)}}@media(max-width:560px){.cards{grid-template-columns:repeat(2,1fr)}.rolegrid{grid-template-columns:1fr}}
</style></head><body><header><div class="brand">◆ TEL<span>99</span> / NIGHT LAB</div><small>Surveillance réelle · lecture seule · mise à jour toutes les 4 s</small></header><main><div class="hero"><div><p>LABORATOIRE AUTONOME · QWEN LOCAL + DOCKER</p><h1>La nuit des agents</h1><p id="subtitle">Lecture des preuves de ton PC…</p></div><div class="right"><span class="tag" id="phase">DÉMARRAGE</span><p id="updated"></p><p id="process"></p></div></div><div class="cards"><div class="card"><span class="num" id="gates">0</span><span class="hint">Contrôles locaux</span></div><div class="card"><span class="num" id="success">0</span><span class="hint">Contrôles réussis</span></div><div class="card"><span class="num" id="missions">0</span><span class="hint">Missions CODE acceptées</span></div><div class="card"><span class="num" id="skills">0</span><span class="hint">Skills trouvés</span></div></div><div class="layout"><div><section class="panel section"><h2>12 domaines de responsabilité · preuves techniques</h2><p>Un domaine testé n'est pas un processus IA autonome. Les vrais rôles actifs sont distingués.</p><div id="roles" class="rolegrid"></div></section><section class="panel section"><h2>Travail de programmation local</h2><div id="tasks"></div></section></div><div><section class="panel section"><h2>Chronologie réelle</h2><div id="events"></div></section><section class="panel section"><h2>État de sécurité</h2><div id="safety"></div></section></div></div><p><small>Les propositions de code ne sont ni fusionnées ni publiées automatiquement. Aucun ordre de trading. Compteur HTTP indépendant au modèle non garanti.</small></p></main><script src="/dashboard.js"></script></body></html>'''
JS = r'''"use strict";
const el=id=>document.getElementById(id);
function set(id,v){el(id).textContent=String(v??"INCONNU")}
function make(tag,text,css){const x=document.createElement(tag);x.textContent=String(text??"");if(css)x.className=css;return x}
function renderRows(id,rows,fn){const box=el(id);box.replaceChildren();for(const row of rows)box.append(fn(row))}
async function tick(){try{const r=await fetch('/status.json',{cache:'no-store'});if(!r.ok)throw Error(r.status);const d=await r.json();set('phase',d.phase);set('subtitle',d.note||'Épreuve en cours');set('updated',d.updated||'');const first=d.first_mission||{};set('process','PID campagne '+(d.pid??'—')+' · superviseur '+(d.supervisor_pid??'—')+(first.id?' · '+first.id+' · premier '+(first.RUNNING?'RUNNING':'ACK')+' observé · état '+(d.missions?.[first.id]??'inconnu'):''));const results=Object.values(d.gates||{});set('gates',results.length);set('success',results.filter(x=>x.status==='PASS').length);set('missions',Object.values(d.missions||{}).filter(x=>x==='ACCEPTED').length);set('skills',(d.skills||[]).length);renderRows('roles',Object.entries(d.roles||{}),([name,x])=>{const e=make('div','','role');e.append(make('strong',name),make('div',x.status||'NON TESTÉ',x.status||''),make('small',x.detail||''));return e});renderRows('tasks',Object.entries(d.missions||{}),([name,status])=>{const e=make('div','','line');e.append(make('code',name+' · '),make('strong',status,status));return e});renderRows('events',(d.events||[]).slice(-35).reverse(),row=>make('div',(row.at||'')+' · '+(row.message||''),'line'));renderRows('safety',Object.entries(d.safety||{}),([name,val])=>make('div',name+': '+val,'line'));}catch(e){set('subtitle','Impossible de lire le statut local : '+e.message)}}tick();setInterval(tick,4000);'''


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_text(path, text):
    tmp = path.with_suffix(path.suffix + ".writing")
    tmp.write_text(text, encoding="utf-8")
    FileStore._retry_file_access(lambda: tmp.replace(path))


def save(path, obj):
    write_text(path, json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def audit_skills(root):
    rows = []
    for relative in (".agents/skills", ".kilo/skills", ".claude/skills", ".github/skills", "skills"):
        for path in sorted((root / relative).rglob("SKILL.md")):
            name = path.relative_to(root)
            if path.is_file() and len(name.parts) <= 6:
                rows.append(name.as_posix())
    return rows[:300]


def cockpit(session, port):
    path = session / "status.json"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
                self.send_error(403)
                return
            if self.path == "/":
                body, kind = HTML.encode(), "text/html"
            elif self.path == "/dashboard.js":
                body, kind = JS.encode(), "application/javascript"
            elif self.path == "/status.json":
                try:
                    body = FileStore._retry_file_access(path.read_bytes)
                except OSError:
                    self.send_error(503)
                    return
                kind = "application/json"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind + "; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def load_registry(path, pin):
    with path.open("rb") as file:
        raw = file.read(512_001)
    if len(raw) > 512_000 or hashlib.sha256(raw).hexdigest() != pin:
        raise ValueError("SHA-256 du registre d'autorisation différent de l'empreinte fournie")
    registry = json.loads(raw)
    if not isinstance(registry, dict) or set(registry) != {"missions", "approvals"}:
        raise ValueError("Registre local invalide")
    missions, approvals = registry["missions"], registry["approvals"]
    if not isinstance(missions, list) or not 5 <= len(missions) <= 8 or not isinstance(approvals, dict):
        raise ValueError("La campagne exige de 5 à 8 missions locales autorisées")
    for mission in missions:
        validate_contract(mission, approvals)
        if mission["owner"] != "local":
            raise ValueError("La campagne accepte uniquement des missions CODE locales")
    ids = {mission["id"] for mission in missions}
    if len(ids) != len(missions) or ids != approvals.keys():
        raise ValueError("Identités ou autorisations de missions incohérentes")
    if ids & LEGACY_MISSIONS:
        raise ValueError("Les identités historiques du Night Lab sont réservées à leurs preuves existantes")
    graph = {mission["id"]: mission_edges(mission) for mission in missions}
    if any(set(dependencies) - ids for dependencies in graph.values()):
        raise ValueError("Dépendance absente du registre local")
    by_id = {m["id"]: m for m in missions}
    if any(not escalation_matches(m, by_id.get(m["escalates_from"])) for m in missions if "escalates_from" in m):
        raise ValueError("La mission d'escalade doit reprendre le contrat indépendant de son prédécesseur")
    TopologicalSorter(graph).prepare()
    return raw, missions


def active_windows_workers(pwsh, timeout):
    if os.name != "nt":
        return []
    # Query only matching process IDs, without exporting any command line.
    command = r"""
$ErrorActionPreference = 'Stop'
Get-CimInstance Win32_Process -Filter "Name LIKE 'python%.exe' OR Name = 'pwsh.exe' OR Name = 'powershell.exe'" |
    Where-Object {
        $_.ProcessId -ne $PID -and $_.ProcessId -ne RUNNER_PID -and (
            ($_.Name -like 'python*.exe' -and (
                $_.CommandLine -match 'night_lab_20261123(?:\.py)?["'']?\s+run(?:\s|$)' -or
                ($_.CommandLine -match 'autonomy_runtime\.py' -and $_.CommandLine -match '\s--local-code(?:\s|$)')
            )) -or
            ($_.Name -in 'pwsh.exe', 'powershell.exe' -and $_.CommandLine -match '\s-File\s+.*start-agents\.ps1' -and
                $_.CommandLine -match '\s-LocalCode(?:\s|$)')
        )
    } | Select-Object -ExpandProperty ProcessId
""".replace("RUNNER_PID", str(os.getpid()))
    result = subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, timeout=timeout, check=True,
    )
    return [int(line) for line in result.stdout.splitlines() if line.strip()]


def terminate_tree(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"
        try:
            subprocess.run(
                [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4, check=False,
            )
        finally:
            if process.poll() is None:
                process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
    process.wait(timeout=1)


class CampaignStopped(Exception):
    pass


class CampaignAwaiting(Exception):
    pass


class Campaign:
    def __init__(self, session, registry_pin, deadline):
        self.session = session
        self.root = session / "code-state"
        self.deadline = deadline
        self.registry_pin = registry_pin
        self.missions = []
        self.runtime = None
        self.log_offset = 0
        self.state = {
            "phase": "PREFLIGHT", "note": "", "updated": now(), "events": [],
            "pid": os.getpid(), "launcher_pid": None, "supervisor_pid": None,
            "first_mission": {}, "missions": {}, "gates": {}, "skills": [],
            "roles": {
                name: {"status": "CONFIGURÉ" if spec.active else "RÉSERVÉ", "detail": spec.name}
                for name, spec in role_catalog().items()
            },
            "safety": {"merge": "DÉSACTIVÉ", "trading": "INTERDIT",
                       "paid_models": "DÉSACTIVÉS", "HTTP_calls": "NON COMPTÉS"},
        }

    def publish(self, note, phase=None):
        if phase:
            self.state["phase"] = phase
        self.state["note"] = note
        self.state["updated"] = now()
        self.state["events"] = (self.state["events"] + [{"at": now(), "message": note}])[-120:]
        save(self.session / "status.json", self.state)
        print(f"[TEL99] {note}", flush=True)

    def check_stop(self):
        if (self.session / "STOP_NUIT").exists() or (self.root / "stop.request").exists():
            raise CampaignStopped("Arrêt demandé pour cette campagne")
        if LEGACY_STOP.exists():
            raise CampaignStopped("Arrêt global TEL99 en cours")
        if time.monotonic() >= self.deadline - STOP_GRACE:
            raise CampaignStopped("Budget de la campagne épuisé")

    def preflight(self):
        self.check_stop()
        pwsh = shutil.which("pwsh")
        if not pwsh:
            raise ValueError("PowerShell 7 introuvable")
        try:
            pids = active_windows_workers(pwsh, timeout=12)
        except subprocess.SubprocessError as exc:
            raise ValueError("Vérification des processus CODE Windows indisponible") from exc
        if pids:
            raise ValueError(f"Superviseur CODE ou Night Lab déjà actif, PID {', '.join(map(str, pids))}")
        self.check_stop()
        actual = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, timeout=10,
            capture_output=True, text=True, check=True,
        )
        checkout_sha = actual.stdout.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{40}", checkout_sha):
            raise ValueError("Empreinte du worktree Git illisible")
        if self.state.get("checkout_sha") not in (None, checkout_sha):
            raise ValueError("Le commit du worktree a changé depuis le premier démarrage")
        self.state["checkout_sha"] = checkout_sha
        for sha in sorted({mission["base_sha"] for mission in self.missions}):
            self.check_stop()
            subprocess.run(
                ["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=ROOT, timeout=10,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
            )
        for port in sorted({mission["port"] for mission in self.missions if "routing" not in mission}):
            self.check_stop()
            connection = HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                connection.request("GET", "/health")
                response = connection.getresponse()
                if response.status != 200 or json.loads(response.read(4096)).get("status") != "ok":
                    raise ValueError(f"Qwen non prêt sur 127.0.0.1:{port}")
            except (OSError, TypeError, AttributeError, json.JSONDecodeError) as exc:
                raise ValueError(f"Contrôle Qwen indisponible sur 127.0.0.1:{port}") from exc
            finally:
                connection.close()
        for image in sorted({mission["sandbox_image"] for mission in self.missions}):
            self.check_stop()
            sandbox.require_local_image(image)
        self.state["gates"]["preflight"] = {"status": "PASS"}
        self.state["skills"] = audit_skills(ROOT)
        self.publish(f"Pré-vol validé sur le commit {checkout_sha[:12]}")
        return pwsh

    def refresh(self, log=None, launch_time=None, prior_worker=None):
        if self.runtime is None:
            return {}
        worker = self.runtime.status()
        self.state["worker"] = worker["last_observed"]
        observed = self.state["worker"]
        if launch_time and observed.get("PID") and observed.get("HEARTBEAT") and observed != prior_worker:
            observed_at = datetime.fromisoformat(observed["HEARTBEAT"]).timestamp()
            if observed_at >= launch_time:
                self.state["supervisor_pid"] = observed["PID"]
        self.state["missions"] = {
            mission["id"]: worker["missions"].get(mission["id"], {}).get("status", "EN ATTENTE")
            for mission in self.missions
        }
        for mission in self.missions:
            mid = mission["id"]
            if (self.state["missions"][mid] == "EN ATTENTE"
                    and self.state["missions"].get(mission.get("escalates_from")) == "ACCEPTED"):
                self.state["missions"][mid] = "NON REQUISE"
        if log is not None:
            self.read_transitions(log)
        self.state["updated"] = now()
        save(self.session / "status.json", self.state)
        return worker["missions"]

    def read_transitions(self, log):
        with log.open("rb") as file:
            file.seek(self.log_offset)
            for line in file:
                if not line.endswith(b"\n"):
                    break
                self.log_offset += len(line)
                if len(line) > 512:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict) or row.get("mission_id") not in self.state["missions"]:
                    continue
                first = self.state["first_mission"]
                if row.get("status") in {"ACK", "RUNNING"}:
                    if not first:
                        first["id"] = row["mission_id"]
                    if row["mission_id"] == first["id"]:
                        first.setdefault(row["status"], now())

    def run_worker(self, pwsh, registry):
        self.check_stop()
        seconds = int(self.deadline - time.monotonic() - STOP_GRACE)
        if seconds < 1:
            raise CampaignStopped("Budget restant insuffisant pour le superviseur")
        command = [
            pwsh, "-NoProfile", "-NonInteractive", "-File", str(ROOT / "start-agents.ps1"),
            "-Action", "RUN", "-Python", sys.executable, "-LocalCode",
            "-State", str(self.root), "-Registry", str(registry),
            "-RegistrySha256", self.registry_pin, "-Seconds", str(seconds), "-Once",
        ]
        number = len(list(self.session.glob("code-missions.*.log"))) + 1
        log = self.session / f"code-missions.{number}.log"
        self.log_offset = 0
        self.state["log"] = log.name
        options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                   else {"start_new_session": True})
        launch_time = int(time.time())
        prior_worker = self.state.get("worker")
        with log.open("xb") as out:
            process = subprocess.Popen(
                command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, **options,
            )
            try:
                self.state["launcher_pid"] = process.pid
                self.state["supervisor_pid"] = None
                self.publish(f"Superviseur lancé, PID du lanceur {process.pid}", "CODE")
                stop_reason, stop_deadline = None, None
                while process.poll() is None:
                    if stop_reason is None:
                        try:
                            self.check_stop()
                        except CampaignStopped as exc:
                            stop_reason = str(exc)
                            (self.root / "stop.request").touch()
                            stop_deadline = min(self.deadline - 5, time.monotonic() + STOP_GRACE)
                            self.publish(stop_reason, "STOPPING")
                    if stop_deadline is not None and time.monotonic() >= stop_deadline:
                        terminate_tree(process)
                        self.state["forced_stop"] = True
                        break
                    self.refresh(log, launch_time, prior_worker)
                    time.sleep(.5)
                self.state["worker_exit"] = process.returncode
                self.refresh(log, launch_time, prior_worker)
                if stop_reason:
                    raise CampaignStopped(stop_reason)
            finally:
                if process.poll() is None:
                    (self.root / "stop.request").touch()
                    try:
                        process.wait(timeout=max(0, min(STOP_GRACE, self.deadline - time.monotonic() - 5)))
                    except subprocess.TimeoutExpired:
                        terminate_tree(process)
                        self.state["forced_stop"] = True
        return process.returncode

    def stop_orphan(self, pwsh):
        pid = self.state.get("supervisor_pid")
        if pid is None:
            return
        until = min(self.deadline - 1, time.monotonic() + STOP_GRACE)
        timeout = max(.1, min(12, until - time.monotonic()))
        if pid not in active_windows_workers(pwsh, timeout):
            return
        (self.root / "stop.request").touch()
        self.publish(f"Arrêt demandé au superviseur orphelin, PID {pid}", "STOPPING")
        while time.monotonic() < until:
            timeout = max(.1, min(12, until - time.monotonic()))
            try:
                if pid not in active_windows_workers(pwsh, timeout):
                    raise CampaignAwaiting(f"Le superviseur orphelin PID {pid} s'est arrêté. Les checkpoints sont conservés.")
            except subprocess.SubprocessError:
                break
            time.sleep(min(.5, max(0, until - time.monotonic())))
        raise CampaignAwaiting(f"Arrêt du superviseur orphelin PID {pid} demandé. Sortie non confirmée.")

    def execute(self, registry):
        for attempt in range(2):
            pwsh = self.preflight()
            code = self.run_worker(pwsh, registry)
            if code in (0, 2):
                return code
            self.stop_orphan(pwsh)
            if attempt == 0:
                self.publish(f"Fin anormale du superviseur ({code}). Une reprise avec les mêmes checkpoints.", "REPRISE")
        return code

    def report(self):
        worker = self.refresh()
        row = self.state
        statuses = row["missions"]
        missions = []
        for mission in self.missions:
            mid = mission["id"]
            checkpoint = worker.get(mid, {})
            missing = [dep for dep in mission["dependencies"] if statuses.get(dep) != "ACCEPTED"]
            missions.append({
                "id": mid, "status": statuses.get(mid, "EN ATTENTE"), "dependencies": mission["dependencies"],
                "unmet_dependencies": missing,
                "checkpoint": checkpoint, "path": mission["path"], "function": mission["function"],
                **({"escalates_from": mission["escalates_from"]} if "escalates_from" in mission else {}),
            })
        save(self.session / "MISSIONS.json", missions)
        save(self.session / "PREUVES.json", {
            "campagne": row["phase"], "pid_campagne": row["pid"],
            "pid_lanceur": row["launcher_pid"], "pid_superviseur": row["supervisor_pid"],
            "premiere_mission": row["first_mission"], "registre_sha256": self.registry_pin,
            "checkout_sha": row.get("checkout_sha"), "verifications": row["gates"],
            "code_sortie_superviseur": row.get("worker_exit"), "arret_force": row.get("forced_stop", False),
            "preuves_missions": {record["id"]: record["checkpoint"].get("verification") for record in missions},
            "routage_missions": {record["id"]: record["checkpoint"]["model_route"] for record in missions
                                 if "model_route" in record["checkpoint"]},
            "journaux": sorted(path.name for path in self.session.glob("code-missions.*.log")),
            "correctifs": "code-state/verified-code", "memoire": "code-state/memory",
        })
        summary = [
            "# TEL99 — Rapport du réveil", "", f"État **{row['phase']}**. {row['note']}", "",
            f"PID campagne **{row['pid']}**. PID superviseur observé **{row['supervisor_pid'] or 'aucun'}**.",
            "", "## Missions", "",
        ]
        blockers = ["# Blocages", ""]
        for record in missions:
            mid, status = record["id"], record["status"]
            summary.append(f"- `{mid}` · **{status}**")
            if status not in {"ACCEPTED", "NON REQUISE"}:
                checkpoint = record["checkpoint"]
                reason = checkpoint.get("reason") or ", ".join(record["unmet_dependencies"]) or row["note"]
                blockers.append(f"- `{mid}` · **{status}** · {reason}")
        if row["phase"] != "COMPLETE":
            blockers.append(f"- Campagne · **{row['phase']}** · {row['note']}")
        if len(blockers) == 2:
            blockers.append("Aucun blocage enregistré.")
        summary += [
            "", "## Preuves et limites", "",
            "- `MISSIONS.json` conserve les checkpoints durables. `PREUVES.json` référence les vérifications et journaux.",
            "- Les modifications indépendamment validées sont conservées dans `code-state/verified-code`.",
            "- Quand une mission démarre, le superviseur confie la génération à Qwen et la vérification à Docker.",
            "- Les 12 domaines sont des rôles logiques. Les Skills trouvés sont inventoriés dans `status.json`.",
            "- Les suites historiques Python et JavaScript restent hors de cette exécution locale.",
            "- Les appels HTTP au modèle ne sont pas comptés par une sonde indépendante.",
        ]
        priorities = [
            "# Prochaines priorités", "",
            "- Examiner les preuves et les correctifs isolés des missions acceptées avant leur intégration.",
            "- Consulter les journaux et `BLOCAGES.md` pour décider des prochaines missions autorisées.",
        ]
        for name, lines in (("LIRE_AU_REVEIL.md", summary), ("BLOCAGES.md", blockers),
                            ("PROCHAINES_PRIORITES.md", priorities)):
            write_text(self.session / name, "\n".join(lines) + "\n")


def run(args):
    started = time.time()
    if args.repo.resolve() != ROOT:
        raise ValueError("Exécuter le script depuis le worktree TEL99 sélectionné")
    session = (args.session or Path.home() / "Desktop" / (
        "TEL99_AUTONOMIE_NUIT_" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    )).resolve()
    manifest = session / "campaign.json"
    if args.resume:
        with manifest.open(encoding="utf-8") as file:
            meta = json.load(file)
        if (meta.get("version") != STATE_VERSION or meta.get("repo") != str(ROOT)
                or meta.get("registry_sha256") != args.registry_sha256):
            raise ValueError("La reprise exige le même worktree et le registre avec son empreinte initiale")
    else:
        session.mkdir(parents=True, exist_ok=False)
        meta = {"version": STATE_VERSION, "repo": str(ROOT), "registry_sha256": args.registry_sha256,
                "deadline_utc_epoch": started + args.hours * 3600}
        save(manifest, meta)
    remaining = min(args.hours * 3600, meta["deadline_utc_epoch"] - time.time())
    campaign = Campaign(session, args.registry_sha256, time.monotonic() + remaining)
    print(f"[TEL99] Dossier de preuves {session}", flush=True)
    username = (os.environ.get("USERNAME") or str(getattr(os, "getuid", lambda: 0)())).casefold()
    lock_name = "tel99-night-lab-" + hashlib.sha256(username.encode()).hexdigest()[:16] + ".lock"
    process_lock = Path(tempfile.gettempdir()) / lock_name
    if process_lock.is_symlink():
        raise ValueError("Chemin de verrou de campagne redirigé")
    # The per-user lock protects the local model across multiple new checkouts.
    # A resume contender never writes the active campaign's files.
    with exclusive(session / "campaign.lock"):
        if args.resume and (session / "status.json").is_file():
            previous = json.loads((session / "status.json").read_bytes())
            campaign.state["events"] = previous.get("events", [])
            campaign.state["first_mission"] = previous.get("first_mission", {})
            campaign.state["checkout_sha"] = previous.get("checkout_sha")
        try:
            with exclusive(process_lock):
                campaign.publish("Validation du registre local et des dépendances")
                raw, campaign.missions = load_registry(args.registry, args.registry_sha256)
                approved = session / "registry.json"
                if approved.exists():
                    if approved.read_bytes() != raw:
                        raise ValueError("Le registre de la session a changé")
                else:
                    with approved.open("xb") as file:
                        file.write(raw)
                campaign.runtime = Runtime(campaign.root, legacy_stop=LEGACY_STOP)
                if args.acknowledge_stop:
                    for path in (session / "STOP_NUIT", campaign.root / "stop.request"):
                        if path.exists():
                            path.replace(path.with_name(f"{path.name}.consumed-{time.time_ns()}"))
                campaign.refresh()
                campaign.check_stop()
                try:
                    server = cockpit(session, args.port)
                except OSError as exc:
                    raise ValueError(f"Cockpit indisponible sur 127.0.0.1:{args.port} ({exc})") from exc
                with server:
                    observer = Thread(target=server.serve_forever, kwargs={"poll_interval": .2}, daemon=True)
                    observer.start()
                    try:
                        campaign.state["cockpit"] = f"http://127.0.0.1:{args.port}/"
                        campaign.publish(f"Cockpit local ouvert sur {campaign.state['cockpit']}")
                        code = campaign.execute(approved)
                        accepted = delivered(campaign.missions, campaign.state["missions"])
                        if code == 0 and accepted:
                            campaign.publish("Toutes les missions ont été vérifiées et acceptées", "COMPLETE")
                        else:
                            campaign.publish("Le superviseur a terminé avec des missions en attente, bloquées ou rejetées", "BLOCKED")
                    finally:
                        server.shutdown()
                        observer.join()
        except CampaignAwaiting as exc:
            campaign.publish(str(exc), "AWAITING_HUMAN")
        except (CampaignStopped, KeyboardInterrupt) as exc:
            campaign.publish(str(exc) or "Interruption de la campagne", "STOPPED")
        except (Blocked, OSError, ValueError, MissionError, subprocess.SubprocessError) as exc:
            if "preflight" not in campaign.state["gates"]:
                campaign.state["gates"]["preflight"] = {"status": "BLOCKED", "reason": str(exc)}
            campaign.publish(f"Préparation ou exécution bloquée · {exc}", "BLOCKED")
        finally:
            campaign.report()
    return 0 if campaign.state["phase"] == "COMPLETE" else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "serve", "stop", "selftest"])
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--session", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--registry-sha256")
    parser.add_argument("--hours", type=float, default=6)
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--acknowledge-stop", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "selftest":
        assert len(role_catalog()) == 12 and STOP_GRACE < .25 * 3600
        print("NIGHT_LAB_SELFTEST_OK")
        return 0
    if args.command in {"serve", "stop"} or args.resume:
        if args.session is None or not args.session.is_dir():
            parser.error("--session doit désigner un dossier existant")
    if not 1024 <= args.port <= 65535:
        parser.error("--port doit être compris entre 1024 et 65535")
    if args.command == "serve":
        with cockpit(args.session, args.port) as server:
            print(f"TEL99 DASHBOARD http://127.0.0.1:{args.port}/", flush=True)
            server.serve_forever()
        return 0
    if args.command == "stop":
        if not (args.session / "campaign.json").is_file():
            parser.error("--session doit désigner un dossier de cette campagne TEL99")
        (args.session / "STOP_NUIT").touch()
        print("STOP demandé", flush=True)
        return 0
    if not .25 <= args.hours <= 6:
        parser.error("--hours doit être compris entre 0.25 et 6")
    if args.acknowledge_stop and not args.resume:
        parser.error("--acknowledge-stop exige --resume")
    if not args.registry or not re.fullmatch(r"[0-9a-f]{64}", args.registry_sha256 or ""):
        parser.error("--registry et --registry-sha256 sont obligatoires")
    try:
        return run(args)
    except (Blocked, OSError, ValueError) as exc:
        print(f"Campagne indisponible · {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
