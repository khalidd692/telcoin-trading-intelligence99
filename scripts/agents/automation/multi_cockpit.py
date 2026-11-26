"""Loopback TEL99 Command Center & multi-mandate cockpit (REUSE-FIRST, 127.0.0.1 only).

Extends the existing TEL99 cockpit into the full browser Command Center without adding a
second supervisor, router, or competing memory system:
- Preserves 100% backward compatibility with `/`, `/health`, `/api/snapshot.json`,
  `POST /api/stop`, `POST /api/clear-stop`, and `--allow-controls` gating.
- Serves strict CSP static UI (`/assets/styles.css`, `/assets/app.js`, ZERO inline scripts).
- Exposes `/api/cc/*` for multi-turn persistent conversations with the 12 official agents,
  Commander/Coordinator delegation mode, autonomous project preview/launch/pause/resume/stop,
  and read-only confined deliverable inspection.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sys
import threading
import time
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[3]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.agents import specialist_dispatch
from scripts.agents.automation import (
    command_center_service,
    ide_coordination,
    learning_loop,
    provider_router,
    recovery_tool,
)
from scripts.agents.automation.antigravity_sdk_backend import probe_sdk_backend
from scripts.agents.automation.autonomy_runtime import LEGACY_STOP
from scripts.agents.automation.github_owner_feed import ARCHIVE_KEY, PIN_KEY
from scripts.agents.automation.local_model_routing import available_memory_mib
from scripts.agents.intelligence.memory import MemoryStore
from scripts.agents.protocol.store import FileStore

UI_ASSETS_DIR = Path(__file__).resolve().parent / "command_center_ui"
MAX_JSON_BODY_BYTES = 65_536
STRICT_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
)

HTML = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TEL99 · Command Center (12 Agents IA)</title>
<link rel="stylesheet" href="/assets/styles.css">
<script src="/assets/app.js" defer></script>
</head>
<body>
<div class="app-shell">
  <header class="topbar">
    <div class="brand">
      <span class="brand-dot"></span>
      <span>TEL99 · COMMAND CENTER</span>
      <span class="muted">12 agents IA personnels</span>
    </div>
    <div id="topPills" class="status-pills"></div>
  </header>

  <nav class="sidebar" aria-label="Navigation principale">
    <button class="nav-btn active" data-view="conversations"><span>Conversations</span><span id="badgeConvs" class="nav-badge">0</span></button>
    <button class="nav-btn" data-view="brief"><span>Brief du matin (G8)</span><span id="badgeBrief" class="nav-badge">0</span></button>
    <button class="nav-btn" data-view="team"><span>Mon équipe (12)</span><span id="badgeTeam" class="nav-badge">12</span></button>
    <button class="nav-btn" data-view="projects"><span>Projets &amp; Missions</span><span id="badgeProjects" class="nav-badge">0</span></button>
    <button class="nav-btn" data-view="activity"><span>Activité en direct</span></button>
    <button class="nav-btn" data-view="skills"><span>Compétences &amp; Apprentissage</span></button>
    <button class="nav-btn" data-view="memory"><span>Mémoire</span></button>
    <button class="nav-btn" data-view="resources"><span>Ressources &amp; Modèles</span></button>
    <button class="nav-btn" data-view="deliveries"><span>Livraisons</span></button>
    <button class="nav-btn" data-view="radar"><span>AI Radar</span></button>
  </nav>

  <main class="workspace">
    <!-- 1. CONVERSATIONS -->
    <section id="view-conversations" class="view-panel active">
      <div class="chat-layout">
        <aside class="conv-sidebar">
          <div class="row-inline" style="justify-content:space-between">
            <strong>Discussions</strong>
            <button id="btnNewConv" class="btn primary sm">+ Nouvelle</button>
          </div>
          <div id="convList"></div>
        </aside>

        <div class="chat-main">
          <div class="chat-toolbar">
            <select id="chatRoleSelect" class="select" style="max-width:300px" aria-label="Agent sélectionné"></select>
            <label class="toggle-label"><input type="checkbox" id="chatTeamToggle"> Mode Commandant (délégation possible)</label>
            <label>Réponse <select id="chatResponseMode" class="select" aria-label="Mode de réponse"><option value="auto" selected>Intelligent — adaptatif</option><option value="fast">Rapide — un agent</option><option value="deep">Approfondi — équipe</option></select></label>
            <label class="toggle-label"><input type="checkbox" id="chatConfidentialToggle" checked> Local confidentiel</label>
            <label class="toggle-label"><input type="checkbox" id="chatHybridToggle" disabled> Hybride gratuit (opt-in)</label>
            <button id="btnRenameConv" class="btn sm">Renommer</button>
            <button id="btnDeleteConv" class="btn danger sm">Supprimer</button>
          </div>

          <div id="chatMessages" class="chat-messages"></div>

          <div class="chat-status-bar">
            <span id="chatStatusText" class="muted">Prêt — mode local confidentiel par défaut (aucun appel modèle automatique).</span>
            <div class="row-inline">
              <button id="btnRetryJob" class="btn primary sm hidden">Réessayer</button>
              <button id="btnCancelJob" class="btn danger sm hidden">Annuler</button>
            </div>
          </div>

          <div class="chat-composer">
            <textarea id="chatInput" class="textarea" rows="2" placeholder="Parlez à votre agent ou donnez un ordre au Coordinateur… (Entrée pour envoyer, Maj+Entrée pour nouvelle ligne)"></textarea>
            <button id="btnSendChat" class="btn primary">Envoyer</button>
          </div>
        </div>
      </div>
    </section>

    <!-- 2. TEAM -->
    <section id="view-team" class="view-panel">
      <div class="section-header">
        <div>
          <h2>Mon équipe de 12 agents IA</h2>
          <div class="muted">Registre officiel TEL99 · Skills spécialisés, niveaux prouvés et accès direct en conversation</div>
        </div>
      </div>
      <div id="teamGrid" class="grid-3"></div>
    </section>

    <!-- 3. PROJECTS & MISSIONS -->
    <section id="view-projects" class="view-panel">
      <div class="section-header">
        <div>
          <h2>Confier un projet autonome &amp; Superviser</h2>
          <div class="muted">Mode distinct de la discussion simple · Exécution détachée avec sandbox Docker OS, tests indépendants et reprise durable</div>
        </div>
      </div>

      <div class="card">
        <h3>Nouveau projet autonome</h3>
        <div class="grid-2">
          <div>
            <label class="muted" for="projGoalInput">Demande en langage naturel</label>
            <textarea id="projGoalInput" class="textarea" rows="3" placeholder="Ex : Construis une application locale de gestion de tâches avec serveur 127.0.0.1, interface web responsive, persistance JSON, tests unittest et README.md…"></textarea>
          </div>
          <div>
            <label class="muted" for="projDirInput">Dossier de travail isolé (nom sur le Bureau ou chemin absolu hors dépôt TEL99)</label>
            <input id="projDirInput" class="input" type="text" placeholder="Ex : TEL99_MON_PROJET ou C:\Users\sabri\Desktop\MON_PROJET">
            <div class="row-inline" style="margin-top:10px">
              <label class="toggle-label"><input type="checkbox" id="projConfidentialToggle" checked> Local confidentiel</label>
              <label class="toggle-label"><input type="checkbox" id="projHybridToggle" disabled> Hybride gratuit (opt-in)</label>
              <label class="toggle-label"><input type="checkbox" id="projReviseToggle"> Réviser le plan existant</label>
            </div>
            <div class="row-inline" style="margin-top:12px">
              <button id="btnPreviewProject" class="btn">1. Prévisualiser périmètre &amp; exigences</button>
              <button id="btnLaunchProject" class="btn primary" disabled>2. Confirmer et lancer le projet</button>
            </div>
          </div>
        </div>
        <div id="projFeedback" class="muted" style="margin-top:8px"></div>
        <div id="projPreviewBox" class="card hidden" style="margin-top:10px"></div>
      </div>

      <div id="fileViewerCard" class="card hidden">
        <div class="section-header">
          <h3 id="fileViewerTitle">Fichier (lecture seule)</h3>
          <button id="btnCloseFileViewer" class="btn sm">Fermer</button>
        </div>
        <div id="fileViewerContent" class="code-viewer"></div>
      </div>

      <div id="projectsList"></div>
    </section>

    <!-- 4. LIVE ACTIVITY -->
    <section id="view-activity" class="view-panel">
      <div class="section-header"><h2>Activité en direct &amp; File d'exécution</h2></div>
      <div class="card">
        <h3>Requêtes conversationnelles récentes</h3>
        <table><thead><tr><th>Job</th><th>Agent</th><th>État</th><th>Étape</th><th>Fournisseur / Modèle</th></tr></thead><tbody id="jobsTable"></tbody></table>
      </div>
      <div class="card">
        <h3>Baux CAS actifs (concurrence locale = 1)</h3>
        <div id="leasesList"></div>
      </div>
    </section>

    <!-- 5. SKILLS & LEARNING -->
    <section id="view-skills" class="view-panel">
      <div class="section-header"><h2>Compétences, Benchmarks &amp; Apprentissage</h2></div>
      <div id="certKpis" class="kpis"></div>
      <div class="card">
        <h3>Skills spécialisés actifs (.agents/skills)</h3>
        <div id="skillsList" class="row-inline"></div>
      </div>
    </section>

    <!-- 6. MEMORY -->
    <section id="view-memory" class="view-panel">
      <div class="section-header">
        <h2>Mémoire vérifiée (isolée des conversations)</h2>
        <input id="memFilterInput" class="input" style="max-width:280px" type="text" placeholder="Filtrer par mot-clé, type ou agent…">
      </div>
      <div class="card">
        <table><thead><tr><th>Type</th><th>Titre</th><th>Vérification</th><th>Auteur</th><th>Extrait</th></tr></thead><tbody id="memoryTable"></tbody></table>
      </div>
    </section>

    <!-- 7. RESOURCES & MODELS -->
    <section id="view-resources" class="view-panel">
      <div class="section-header"><h2>Ressources, Modèles &amp; Quotas gratuits</h2></div>
      <div class="card">
        <div id="resourcesList" style="display:grid;gap:8px"></div>
      </div>
    </section>

    <!-- 8. DELIVERIES -->
    <section id="view-deliveries" class="view-panel">
      <div class="section-header"><h2>Livraisons vérifiées</h2></div>
      <div class="card">
        <table><thead><tr><th>Projet</th><th>Statut</th><th>Fichiers</th><th>Commande / URL</th><th>Action</th></tr></thead><tbody id="deliveriesTable"></tbody></table>
      </div>
    </section>

    <!-- 9. AI RADAR -->
    <section id="view-radar" class="view-panel">
      <div class="section-header"><h2>AI Radar</h2></div>
      <div class="card">
        <p id="radarStatusText" class="muted">Vérification d'AI Radar…</p>
        <a href="http://127.0.0.1:8780/" target="_blank" rel="noopener noreferrer" class="btn primary">Ouvrir AI Radar (http://127.0.0.1:8780/)</a>
      </div>
    </section>

    <!-- 10. BRIEF DU MATIN (G8 PROACTIVITE & APPRENTISSAGE) -->
    <section id="view-brief" class="view-panel">
      <div class="section-header">
        <div>
          <h2>Bonjour, voici ce que nous avons préparé pour toi.</h2>
          <div id="briefSubtitle" class="muted">Proactivité bornée G8 &amp; Apprentissage continu G5/G6 · Priorité propriétaire absolue</div>
        </div>
        <div class="row-inline">
          <button id="btnToggleLearningPause" class="btn sm">Pause apprentissage</button>
          <button id="btnToggleProactive" class="btn sm">Désactiver G8</button>
        </div>
      </div>
      <div id="briefFeedbackBanner" class="muted" style="margin-bottom:10px"></div>
      <div id="briefActionRow" class="card hidden">
        <div class="section-header">
          <h3 id="briefLatestTitle">Dernier brief proactif</h3>
          <div class="row-inline">
            <button id="btnBriefAccept" class="btn primary sm">Accepter</button>
            <button id="btnBriefUseful" class="btn sm">Utile</button>
            <button id="btnBriefReject" class="btn sm">Refuser</button>
          </div>
        </div>
        <div id="briefLatestMeta" class="muted"></div>
      </div>
      <div id="briefSectionsGrid" class="grid-2"></div>
      <div class="card" style="margin-top:12px">
        <h3>Historique des cycles proactifs (G8)</h3>
        <table><thead><tr><th>Date</th><th>Déclencheur</th><th>Statut</th><th>Titre</th><th>Feedback</th></tr></thead><tbody id="briefHistoryTable"></tbody></table>
      </div>
    </section>
  </main>
</div>
</body>
</html>
"""


def _safe_checks(verification: dict | None) -> tuple[int, int]:
    checks = verification.get("checks") if isinstance(verification, dict) else None
    if not isinstance(checks, list):
        return 0, 0
    return sum(1 for c in checks if isinstance(c, dict) and c.get("ok") is True), len(checks)


def _memory_summary(root: Path) -> dict:
    mem_dir = root / "learning" / "memory"
    if not mem_dir.is_dir():
        return {"entries_total": 0, "fixes": 0, "errors": 0, "procedures": 0, "has_procedures_doc": False, "recent_entries": []}
    store = MemoryStore(mem_dir)
    entries = store.all_entries("tel99", include_common=True)
    recent = [
        {"id": e.id, "kind": e.kind, "title": e.title, "verified": bool(e.verified), "created_at": e.created_at}
        for e in entries[-10:]
    ]
    return {
        "entries_total": len(entries),
        "fixes": sum(1 for e in entries if e.kind == "fix"),
        "errors": sum(1 for e in entries if e.kind == "error"),
        "procedures": sum(1 for e in entries if e.kind == "procedure"),
        "has_procedures_doc": (root / "learning" / "learned_procedures.md").is_file(),
        "recent_entries": recent,
    }


def _discover_project_skills() -> list[str]:
    skills_dir = ROOT / ".agents" / "skills"
    if not skills_dir.is_dir():
        return []
    return sorted(p.parent.name for p in skills_dir.glob("*/SKILL.md") if p.is_file())


def _improvement_proposals(root: Path) -> dict:
    path = root / "learning" / "improvement_proposals.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _read_optional_json(path: Path) -> dict | list | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _academy_summary(root: Path) -> dict | None:
    data = _read_optional_json(root / "learning" / "academy_summary.json")
    return data if isinstance(data, dict) else None


def _evolution_telemetry(root: Path) -> dict:
    """Surface real on-disk passports, calibration, failure library, trajectories & champion-challenger (zero fabricated stats)."""
    learning_dir = root / "learning"
    passports = _read_optional_json(learning_dir / "agent_passports.json")
    calibration = _read_optional_json(learning_dir / "calibration_metrics.json")
    champion = _read_optional_json(learning_dir / "champion_challenger.json")
    failures = _read_optional_json(learning_dir / "failure_library.json")
    traj_file = learning_dir / "trajectories.jsonl"
    traj_count = 0
    if traj_file.is_file():
        try:
            traj_count = sum(1 for line in traj_file.read_text(encoding="utf-8").splitlines() if line.strip())
        except OSError:
            traj_count = 0
    return {
        "passports": passports if isinstance(passports, dict) else None,
        "calibration": calibration if isinstance(calibration, dict) else None,
        "champion_challenger": champion if isinstance(champion, dict) else None,
        "failure_library_count": len(failures) if isinstance(failures, list) else 0,
        "trajectories_count": traj_count,
    }


def build_snapshot(
    state_root: Path | str,
    *,
    include_providers: bool = False,
    controls_enabled: bool = False,
    controls_token: str | None = None,
    providers_override: dict | None = None,
) -> dict:
    """Build a public-safe read-only snapshot of a multi-mandate state directory."""
    root = Path(state_root).resolve()
    feed_store = FileStore(root / "feed-ledger")
    active_record = feed_store.get(PIN_KEY) or {}
    archive_record = feed_store.get(ARCHIVE_KEY) or {}
    active_pins = active_record.get("pins", []) if isinstance(active_record, dict) else []
    archived_pins = archive_record.get("pins", []) if isinstance(archive_record, dict) else []

    campaigns: list[dict] = []
    for camp_dir in sorted(root.glob("campaign-*")):
        if not camp_dir.is_dir():
            continue
        ledger = FileStore(camp_dir / "ledger")
        config = ledger.get("github-local-code/config")
        if not isinstance(config, dict):
            continue
        missions_out: list[dict] = []
        for key in sorted(ledger.keys("kilo-github/approvals")):
            binding = ledger.get(key)
            if not isinstance(binding, dict) or not isinstance(binding.get("mission"), dict):
                continue
            mission = binding["mission"]
            mid = mission.get("id")
            if not isinstance(mid, str):
                continue
            cp = ledger.get(f"kilo-local/{mid}") or {}
            ver = cp.get("verification") if isinstance(cp.get("verification"), dict) else {}
            res = cp.get("result") if isinstance(cp.get("result"), dict) else {}
            passed, total = _safe_checks(ver)
            pr_rec = ledger.get(f"github-local-code/PR/{binding.get('issue')}/{mid}") or {}
            out_ack = ledger.get(f"kilo-github/outbox/{mid}/ACK") or {}
            out_evi = ledger.get(f"kilo-github/outbox/{mid}/EVIDENCE") or {}
            out_res = ledger.get(f"kilo-github/outbox/{mid}/RESULT") or {}
            history = cp.get("attempt_history") if isinstance(cp.get("attempt_history"), list) else []
            missions_out.append({
                "id": mid,
                "issue": binding.get("issue"),
                "status": cp.get("status", "PENDING"),
                "reason": cp.get("reason"),
                "repaired": bool(cp.get("status") == "ACCEPTED" and history),
                "attempt": cp.get("attempt"),
                "auto_recovery_count": int(cp.get("auto_recovery_count") or 0),
                "backend": res.get("backend") or res.get("provider") or "ollama-native",
                "model": ver.get("model") or res.get("model") or mission.get("model"),
                "generation_seconds": ver.get("generation_seconds") or res.get("generation_seconds"),
                "verification_seconds": ver.get("verification_seconds"),
                "checks_passed": passed,
                "checks_total": total,
                "roles": list(mission.get("team") or []),
                "ack_url": out_ack.get("url"),
                "evidence_url": out_evi.get("url"),
                "result_url": out_res.get("url"),
                "pull_request_url": pr_rec.get("pr_url"),
            })
        campaigns.append({
            "issue": config.get("issue"),
            "mandate_id": config.get("mandate_id"),
            "base_ref": config.get("base_ref"),
            "base_sha": config.get("base_sha"),
            "stop_requested": (camp_dir / "stop.request").exists(),
            "complete": bool(missions_out) and all(
                m["status"] == "ACCEPTED" and m["result_url"] and m["pull_request_url"]
                for m in missions_out
            ),
            "missions": missions_out,
        })

    metrics = learning_loop.collect_campaign_metrics(root)
    recovery = recovery_tool.inspect_state(root)
    providers = {}
    if providers_override is not None:
        providers = providers_override
    elif include_providers:
        providers = provider_router.probe_all_providers()["providers"]

    specialists = specialist_dispatch.list_specialists()
    team_catalog = {
        "total": len(specialists),
        "active_count": sum(1 for item in specialists if item["active"]),
        "reserved_on_demand_count": sum(1 for item in specialists if not item["active"]),
        "max_concurrent_specialists": specialist_dispatch.MAX_CONCURRENT_SPECIALISTS,
        "agents": specialists,
    }
    coordination = ide_coordination.active_leases(root)

    skills = _discover_project_skills()
    terminal_tasks = sum(int(v.get("tasks") or 0) for v in (metrics.get("measured_quality") or {}).values())
    first_pass_accepted = sum(int(v.get("first_pass_accepted") or 0) for v in (metrics.get("measured_quality") or {}).values())
    final_accepted = sum(int(v.get("accepted") or 0) for v in (metrics.get("measured_quality") or {}).values())

    snapshot = {
        "schema_version": 1,
        "read_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "state_root": str(root),
        "controls_enabled": controls_enabled,
        "feed": {
            "active_pins": [p.get("issue") for p in active_pins if isinstance(p, dict)],
            "archived_pins": [p.get("issue") for p in archived_pins if isinstance(p, dict)],
        },
        "campaigns": campaigns,
        "learning": {
            "measured_quality": metrics["measured_quality"],
            "improvement_proposals": _improvement_proposals(root),
            "academy_summary": _academy_summary(root),
            "evolution": _evolution_telemetry(root),
        },
        "memory": _memory_summary(root),
        "recovery": recovery,
        "providers": providers,
        "sdk_backend": probe_sdk_backend(),
        "skills": skills,
        "team_catalog": team_catalog,
        "coordination": coordination,
        "summary": {
            "campaigns": len(campaigns),
            "missions_total": metrics["missions_total"],
            "accepted": metrics["accepted"],
            "first_pass_accepted": first_pass_accepted,
            "first_pass_rate": round(first_pass_accepted / terminal_tasks, 4) if terminal_tasks else 0.0,
            "final_success_rate": round(final_accepted / terminal_tasks, 4) if terminal_tasks else 0.0,
            "repaired": metrics["repaired"],
            "pending": metrics["pending"],
            "skills_count": len(skills),
        },
        "resources": {
            "available_memory_mib": available_memory_mib(),
            "stop_requested": (root / "stop.request").exists(),
            "legacy_stop": LEGACY_STOP.exists(),
        },
    }
    if controls_enabled and controls_token:
        snapshot["controls_token"] = controls_token
    return snapshot


def make_server(
    state_root: Path | str,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    allow_controls: bool = False,
    include_providers: bool = False,
    cc_service: command_center_service.CommandCenterService | None = None,
) -> ThreadingHTTPServer:
    if host != "127.0.0.1":
        raise ValueError("TEL99 Command Center must bind strictly to loopback 127.0.0.1")
    root = Path(state_root).resolve()
    csrf_token = secrets.token_hex(16) if allow_controls else None
    service = cc_service or command_center_service.CommandCenterService(root)
    provider_cache = {"at": 0.0, "data": {}, "refreshing": False}
    provider_lock = threading.Lock()
    provider_ready = threading.Event()

    def _refresh_providers_bg() -> None:
        try:
            data = provider_router.probe_all_providers()["providers"]
            with provider_lock:
                provider_cache["data"] = data
                provider_cache["at"] = time.monotonic()
        except Exception:
            pass
        finally:
            with provider_lock:
                provider_cache["refreshing"] = False
            provider_ready.set()

    def _trigger_provider_refresh() -> None:
        with provider_lock:
            if provider_cache["refreshing"]:
                return
            provider_cache["refreshing"] = True
        threading.Thread(target=_refresh_providers_bg, daemon=True).start()

    if include_providers:
        _trigger_provider_refresh()

    def cached_providers() -> dict:
        if not include_providers:
            return {}
        now = time.monotonic()
        with provider_lock:
            stale = (now - provider_cache["at"] > 30.0) or not provider_cache["data"]
            has_data = bool(provider_cache["data"])
        if stale:
            _trigger_provider_refresh()
            if not has_data:
                provider_ready.wait(timeout=1.5)
        with provider_lock:
            return dict(provider_cache["data"])

    class Handler(BaseHTTPRequestHandler):
        def _valid_loopback_host(self) -> bool:
            actual_port = self.server.server_port
            return self.headers.get("Host") in (f"127.0.0.1:{actual_port}", f"localhost:{actual_port}")

        def _valid_mutation_headers(self) -> bool:
            if not allow_controls or not self._valid_loopback_host():
                return False
            actual_port = self.server.server_port
            origin = self.headers.get("Origin")
            allowed_origins = (None, f"http://127.0.0.1:{actual_port}", f"http://localhost:{actual_port}")
            return origin in allowed_origins and self.headers.get("X-TEL99-Token") == csrf_token

        def _read_json_body(self) -> dict:
            raw_len = self.headers.get("Content-Length")
            if not raw_len:
                return {}
            try:
                length = int(raw_len)
            except ValueError as exc:
                raise ValueError("Content-Length invalide") from exc
            if length < 0 or length > MAX_JSON_BODY_BYTES:
                raise ValueError(f"Payload dépassant la limite autorisée ({MAX_JSON_BODY_BYTES} octets)")
            if length == 0:
                return {}
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Le corps JSON doit être un objet")
            return data

        def _send_bytes(self, body: bytes, ctype: str, code: int = 200) -> None:
            try:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy", STRICT_CSP)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                pass

        def _send_json(self, payload: dict | list, code: int = 200) -> None:
            self._send_bytes(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
                code=code,
            )

        def do_GET(self):
            if not self._valid_loopback_host():
                self.send_error(403)
                return
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            try:
                if path == "/":
                    self._send_bytes(HTML.encode("utf-8"), "text/html; charset=utf-8")
                elif path == "/assets/styles.css":
                    css = (UI_ASSETS_DIR / "styles.css").read_bytes()
                    self._send_bytes(css, "text/css; charset=utf-8")
                elif path == "/assets/app.js":
                    js = (UI_ASSETS_DIR / "app.js").read_bytes()
                    self._send_bytes(js, "application/javascript; charset=utf-8")
                elif path == "/health":
                    self._send_bytes(b'{"ok":true}', "application/json; charset=utf-8")
                elif path == "/api/snapshot.json":
                    snap = build_snapshot(
                        root,
                        controls_enabled=allow_controls,
                        controls_token=csrf_token,
                        providers_override=cached_providers(),
                    )
                    self._send_json(snap)
                elif path == "/api/cc/state":
                    self._send_json(service.build_command_center_state())
                elif path == "/api/cc/team":
                    self._send_json({"agents": command_center_service.get_enriched_team_catalog()})
                elif path == "/api/cc/conversations":
                    self._send_json({"conversations": service.list_conversations()})
                elif path.startswith("/api/cc/conversations/"):
                    cid = unquote(path[len("/api/cc/conversations/") :]).strip("/")
                    self._send_json(service.get_conversation(cid))
                elif path.startswith("/api/cc/jobs/"):
                    jid = unquote(path[len("/api/cc/jobs/") :]).strip("/")
                    self._send_json(service.get_job(jid))
                elif path == "/api/cc/projects":
                    self._send_json({"projects": service.list_projects()})
                elif path == "/api/cc/projects/file":
                    proj_dir = (qs.get("project") or [""])[0]
                    rel_path = (qs.get("path") or [""])[0]
                    self._send_json(service.read_project_file(project_dir=proj_dir, rel_path=rel_path))
                else:
                    self.send_error(404)
            except KeyError as exc:
                self._send_json({"ok": False, "error": str(exc)}, code=404)
            except FileNotFoundError as exc:
                self._send_json({"ok": False, "error": str(exc)}, code=404)
            except PermissionError as exc:
                self._send_json({"ok": False, "error": str(exc)}, code=403)
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, code=400)

        def do_POST(self):
            if not self._valid_mutation_headers():
                self.send_error(403)
                return
            path = urlparse(self.path).path
            try:
                if path == "/api/stop":
                    root.mkdir(parents=True, exist_ok=True)
                    (root / "stop.request").touch()
                    for ledger in root.glob("campaign-*"):
                        if ledger.is_dir():
                            (ledger / "stop.request").touch()
                    self._send_json({"ok": True, "action": "stop"})
                elif path == "/api/clear-stop":
                    report = recovery_tool.clear_stops(root)
                    self._send_json({"ok": True, "action": "clear-stop", **report})
                elif path == "/api/cc/conversations":
                    body = self._read_json_body()
                    conv = service.create_conversation(
                        title=str(body.get("title") or "Nouvelle conversation"),
                        role=str(body.get("role") or "coordination"),
                        team_mode=body.get("team_mode"),
                        confidential=bool(body.get("confidential", True)),
                        hybrid=bool(body.get("hybrid", False)),
                    )
                    self._send_json(conv, code=201)
                elif path.startswith("/api/cc/conversations/") and path.endswith("/messages"):
                    cid = unquote(path[len("/api/cc/conversations/") : -len("/messages")]).strip("/")
                    body = self._read_json_body()
                    job = service.submit_chat_message(
                        conv_id=cid,
                        message=str(body.get("message") or ""),
                        response_mode=body.get("response_mode"),
                        role=body.get("role"),
                        team_mode=body.get("team_mode"),
                        confidential=body.get("confidential"),
                        hybrid=body.get("hybrid"),
                    )
                    self._send_json(job, code=202)
                elif path.startswith("/api/cc/jobs/") and path.endswith("/cancel"):
                    jid = unquote(path[len("/api/cc/jobs/") : -len("/cancel")]).strip("/")
                    self._send_json(service.cancel_job(jid))
                elif path.startswith("/api/cc/jobs/") and path.endswith("/retry"):
                    jid = unquote(path[len("/api/cc/jobs/") : -len("/retry")]).strip("/")
                    self._send_json(service.retry_job(jid), code=202)
                elif path == "/api/cc/projects/preview":
                    body = self._read_json_body()
                    res = service.preview_project_scope(
                        goal_text=str(body.get("goal_text") or ""),
                        project_dir=str(body.get("project_dir") or ""),
                        confidential=bool(body.get("confidential", True)),
                        hybrid=bool(body.get("hybrid", False)),
                    )
                    self._send_json(res)
                elif path == "/api/cc/projects/launch":
                    body = self._read_json_body()
                    res = service.launch_autonomous_project(
                        goal_text=str(body.get("goal_text") or ""),
                        project_dir=str(body.get("project_dir") or ""),
                        confidential=bool(body.get("confidential", True)),
                        hybrid=bool(body.get("hybrid", False)),
                        resume_rejected=bool(body.get("resume_rejected", False)),
                        revise_plan=bool(body.get("revise_plan", False)),
                        confirmed=bool(body.get("confirmed", False)),
                    )
                    self._send_json(res, code=202 if res.get("ok") else 409)
                elif path == "/api/cc/projects/control":
                    body = self._read_json_body()
                    res = service.control_autonomous_project(
                        project_dir=str(body.get("project_dir") or ""),
                        action=str(body.get("action") or ""),
                        hybrid=bool(body.get("hybrid", False)),
                        confidential=bool(body.get("confidential", True)),
                        resume_rejected=bool(body.get("resume_rejected", False)),
                    )
                    self._send_json(res)
                elif path == "/api/cc/learning/control":
                    body = self._read_json_body()
                    res = service.control_learning_and_proactive(
                        action=str(body.get("action") or ""),
                        brief_id=str(body.get("brief_id") or ""),
                        feedback=str(body.get("feedback") or ""),
                        note=str(body.get("note") or ""),
                    )
                    self._send_json(res)
                else:
                    self.send_error(404)
            except KeyError as exc:
                self._send_json({"ok": False, "error": str(exc)}, code=404)
            except PermissionError as exc:
                self._send_json({"ok": False, "error": str(exc)}, code=403)
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, code=400)

        def do_PATCH(self):
            if not self._valid_mutation_headers():
                self.send_error(403)
                return
            path = urlparse(self.path).path
            try:
                if path.startswith("/api/cc/conversations/"):
                    cid = unquote(path[len("/api/cc/conversations/") :]).strip("/")
                    body = self._read_json_body()
                    conv = service.update_conversation(
                        cid,
                        title=body.get("title"),
                        role=body.get("role"),
                        team_mode=body.get("team_mode"),
                        confidential=body.get("confidential"),
                        hybrid=body.get("hybrid"),
                    )
                    self._send_json(conv)
                else:
                    self.send_error(404)
            except KeyError as exc:
                self._send_json({"ok": False, "error": str(exc)}, code=404)
            except PermissionError as exc:
                self._send_json({"ok": False, "error": str(exc)}, code=403)
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, code=400)

        def do_DELETE(self):
            if not self._valid_mutation_headers():
                self.send_error(403)
                return
            path = urlparse(self.path).path
            try:
                if path.startswith("/api/cc/conversations/"):
                    cid = unquote(path[len("/api/cc/conversations/") :]).strip("/")
                    self._send_json(service.delete_conversation(cid))
                else:
                    self.send_error(404)
            except KeyError as exc:
                self._send_json({"ok": False, "error": str(exc)}, code=404)
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, code=400)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer((host, port), Handler)
    server.cc_service = service  # type: ignore[attr-defined]
    server.csrf_token = csrf_token  # type: ignore[attr-defined]
    return server


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--include-providers", action="store_true")
    parser.add_argument("--allow-controls", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if args.snapshot:
        print(json.dumps(
            build_snapshot(args.state, include_providers=args.include_providers),
            indent=2, ensure_ascii=False,
        ))
        return 0
    server = make_server(
        args.state,
        port=args.port,
        allow_controls=args.allow_controls,
        include_providers=args.include_providers,
    )
    print(f"TEL99 Command Center listening on http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
