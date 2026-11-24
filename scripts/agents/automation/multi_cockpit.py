"""Loopback cockpit for TEL99 multi-mandate auto-feed, learning, recovery & providers.

Read-only by default (POST endpoints return 403 unless --allow-controls is
explicitly enabled). Never exposes source code, prompts, private tests, or secrets.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.agents.automation import learning_loop, provider_router, recovery_tool
from scripts.agents.automation.autonomy_runtime import LEGACY_STOP
from scripts.agents.automation.github_owner_feed import ARCHIVE_KEY, PIN_KEY
from scripts.agents.automation.local_model_routing import available_memory_mib
from scripts.agents.intelligence.memory import MemoryStore
from scripts.agents.protocol.store import FileStore

HTML = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TEL99 · Cockpit Multi-Mandats</title>
<style>
:root{color-scheme:dark;--bg:#09101a;--card:#111c2d;--line:#25354c;--fg:#e8f1ff;--muted:#9fb1ca;--ok:#5ce0b5;--warn:#f7cf6b;--err:#ff9e8a}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:var(--bg);color:var(--fg)}
header{padding:16px 24px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}
main{max-width:1280px;margin:auto;padding:20px;display:grid;gap:16px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.num{font-size:1.7rem;font-weight:700}.label{font-size:.82rem;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
table{width:100%;border-collapse:collapse;font-size:.86rem}th,td{padding:8px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.ACCEPTED,.PASS,.READY{color:var(--ok);font-weight:600}.RUNNING,.ACK,.PREPARING,.OPT_IN_NO_RPC_QUOTA{color:var(--warn);font-weight:600}.BLOCKED,.REJECTED,.AWAITING_HUMAN,.WAITING_QUOTA{color:var(--err);font-weight:600}
button{background:#1b2d47;color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:6px 12px;cursor:pointer;font-size:.82rem}
button:hover{background:#263f63}
a{color:#7dc3ff;text-decoration:none}a:hover{text-decoration:underline}
</style>
</head>
<body>
<header>
  <div><strong>TEL99 · COCKPIT MULTI-AGENTS</strong> <span id="modeBadge" class="label"></span></div>
  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
    <span id="meta" class="label">Chargement…</span>
    <span id="controls" style="display:none;gap:8px">
      <button id="btnStop" onclick="sendAction('/api/stop')">Arrêt sûr (STOP)</button>
      <button id="btnClear" onclick="sendAction('/api/clear-stop')">Effacer STOP</button>
    </span>
  </div>
</header>
<main>
<section class="kpis" id="kpis"></section>
<section class="grid">
  <div class="card"><h3>Contrôleurs Auto-Feed & Campagnes</h3><div id="campaigns"></div></div>
  <div class="card"><h3>Apprentissage, Mémoire & Procédures</h3><div id="learning"></div></div>
  <div class="card"><h3>Fournisseurs, Modèles & Quotas</h3><div id="providers"></div></div>
  <div class="card"><h3>Blocages & Reprise Sûre</h3><div id="recovery"></div></div>
</section>
<section class="card"><h3>Missions & Preuves</h3><table><thead><tr><th>Mission</th><th>Contrôleur</th><th>État</th><th>Modèle</th><th>Checks</th><th>PR / Reçus</th></tr></thead><tbody id="missions"></tbody></table></section>
</main>
<script>
const el = id => document.getElementById(id);
let csrfToken = null;
function txt(tag, value, cls) { const n = document.createElement(tag); n.textContent = String(value ?? ""); if (cls) n.className = cls; return n; }
async function sendAction(path) {
  if (!csrfToken) return;
  const r = await fetch(path, {method: 'POST', headers: {'X-TEL99-Token': csrfToken}});
  if (r.ok) await refresh();
}
async function refresh() {
  try {
    const r = await fetch('/api/snapshot.json', {cache: 'no-store'});
    if (!r.ok) throw new Error(r.status);
    const d = await r.json();
    csrfToken = d.controls_token || null;
    el('modeBadge').textContent = d.controls_enabled ? '(contrôles locaux actifs)' : '(lecture seule)';
    el('controls').style.display = d.controls_enabled ? 'inline-flex' : 'none';
    el('meta').textContent = `Mis à jour ${d.read_at} · RAM libre ${d.resources.available_memory_mib ?? "?"} MiB · STOP=${d.resources.stop_requested}`;
    const kpis = [
      ['Contrôleurs actifs', d.feed.active_pins.length],
      ['Archivés complets', d.feed.archived_pins.length],
      ['Missions acceptées', `${d.summary.accepted}/${d.summary.missions_total}`],
      ['Mémoire / Procédures', `${d.memory.entries_total} (${d.memory.procedures} proc.)`],
    ];
    el('kpis').replaceChildren(...kpis.map(([k,v]) => { const c = txt('div','','card'); c.append(txt('div',v,'num'), txt('div',k,'label')); return c; }));
    el('campaigns').replaceChildren(...(d.campaigns.length ? d.campaigns.map(c => {
      const box = txt('div','','label'); box.style.marginBottom = '8px';
      box.textContent = `#${c.issue} · complet=${c.complete} · missions=${c.missions.length} · base=${(c.base_sha||"").slice(0,10)}`;
      return box;
    }) : [txt('div','Aucune campagne active dans ce dossier d’état.','label')]));
    const mq = Object.entries(d.learning.measured_quality || {});
    el('learning').replaceChildren(...(mq.length ? mq.map(([m,s]) => {
      const box = txt('div','','label'); box.style.marginBottom = '8px';
      box.textContent = `${m}: ${Math.round(s.success_rate*100)}% (${s.accepted}/${s.tasks}) · avg ${s.avg_generation_seconds}s gen / ${s.avg_verification_seconds}s docker`;
      return box;
    }) : [txt('div','Aucune mesure terminale encore enregistrée.','label')]));
    const provs = Object.entries(d.providers || {});
    el('providers').replaceChildren(...(provs.length ? provs.map(([name,p]) => {
      const box = txt('div','','label'); box.style.marginBottom = '6px';
      box.textContent = `${name} [${p.billing_class}] · ${p.quota_status} · ${(p.models||[]).length} modèle(s)`;
      return box;
    }) : [txt('div','Sonde fournisseurs non activée dans ce cliché.','label')]));
    const rec = d.recovery || {};
    const recRows = [];
    if (rec.needs_attention) {
      for (const b of (rec.blocked_missions || [])) recRows.push(`BLOCKED ${b.campaign}/${b.mission_id}: ${b.reason || ''}`);
      for (const a of (rec.awaiting_human || [])) recRows.push(`AWAITING_HUMAN ${a.campaign}/${a.mission_id}: ${a.reason || ''}`);
      for (const r2 of (rec.crashed_running || [])) recRows.push(`CRASHED_RUNNING ${r2.campaign}/${r2.mission_id}`);
      if (rec.parent_stop || (rec.campaign_stops||[]).length) recRows.push('Marqueur stop.request présent');
    } else {
      recRows.push('Aucun blocage ni marqueur STOP actif.');
    }
    el('recovery').replaceChildren(...recRows.map(line => { const b = txt('div', line, 'label'); b.style.marginBottom = '6px'; return b; }));
    el('missions').replaceChildren(...d.campaigns.flatMap(c => c.missions.map(m => {
      const tr = document.createElement('tr');
      tr.append(txt('td', m.id), txt('td', `#${c.issue} -> #${m.issue ?? "?"}`), txt('td', m.status, m.status), txt('td', m.model || "?"));
      tr.append(txt('td', `${m.checks_passed}/${m.checks_total} (att ${m.attempt ?? 1})`));
      const td = document.createElement('td');
      if (m.pull_request_url) { const a = txt('a', 'Draft PR'); a.href = m.pull_request_url; a.target = '_blank'; td.append(a); }
      else { td.textContent = m.result_url ? 'RESULT ok' : 'En attente'; }
      tr.append(td);
      return tr;
    })));
  } catch (e) { el('meta').textContent = 'Erreur lecture cockpit: ' + e.message; }
}
refresh(); setInterval(refresh, 4000);
</script>
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
        return {"entries_total": 0, "fixes": 0, "errors": 0, "procedures": 0, "has_procedures_doc": False}
    store = MemoryStore(mem_dir)
    entries = store.all_entries("tel99", include_common=True)
    return {
        "entries_total": len(entries),
        "fixes": sum(1 for e in entries if e.kind == "fix"),
        "errors": sum(1 for e in entries if e.kind == "error"),
        "procedures": sum(1 for e in entries if e.kind == "procedure"),
        "has_procedures_doc": (root / "learning" / "learned_procedures.md").is_file(),
    }


def build_snapshot(state_root: Path | str, *, include_providers: bool = False,
                   controls_enabled: bool = False, controls_token: str | None = None,
                   providers_override: dict | None = None) -> dict:
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
            missions_out.append({
                "id": mid,
                "issue": binding.get("issue"),
                "status": cp.get("status", "PENDING"),
                "attempt": cp.get("attempt"),
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
        },
        "memory": _memory_summary(root),
        "recovery": recovery,
        "providers": providers,
        "summary": {
            "campaigns": len(campaigns),
            "missions_total": metrics["missions_total"],
            "accepted": metrics["accepted"],
            "repaired": metrics["repaired"],
            "pending": metrics["pending"],
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


def make_server(state_root: Path | str, *, host: str = "127.0.0.1", port: int = 8765,
                allow_controls: bool = False, include_providers: bool = False) -> ThreadingHTTPServer:
    root = Path(state_root).resolve()
    csrf_token = secrets.token_hex(16) if allow_controls else None
    provider_cache = {"at": 0.0, "data": {}}

    def cached_providers() -> dict:
        if not include_providers:
            return {}
        now = time.monotonic()
        if now - provider_cache["at"] > 30.0 or not provider_cache["data"]:
            provider_cache["data"] = provider_router.probe_all_providers()["providers"]
            provider_cache["at"] = now
        return provider_cache["data"]

    class Handler(BaseHTTPRequestHandler):
        def _valid_loopback_host(self) -> bool:
            actual_port = self.server.server_port
            return self.headers.get("Host") in (f"127.0.0.1:{actual_port}", f"localhost:{actual_port}")

        def _send_bytes(self, body: bytes, ctype: str, code: int = 200) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._valid_loopback_host():
                self.send_error(403)
                return
            if self.path == "/":
                self._send_bytes(HTML.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/api/snapshot.json":
                snap = build_snapshot(
                    root,
                    controls_enabled=allow_controls,
                    controls_token=csrf_token,
                    providers_override=cached_providers(),
                )
                self._send_bytes(
                    json.dumps(snap, ensure_ascii=False).encode("utf-8"),
                    "application/json; charset=utf-8",
                )
            else:
                self.send_error(404)

        def do_POST(self):
            if not allow_controls or not self._valid_loopback_host():
                self.send_error(403)
                return
            actual_port = self.server.server_port
            origin = self.headers.get("Origin")
            allowed_origins = (None, f"http://127.0.0.1:{actual_port}", f"http://localhost:{actual_port}")
            if origin not in allowed_origins or self.headers.get("X-TEL99-Token") != csrf_token:
                self.send_error(403)
                return
            if self.path == "/api/stop":
                root.mkdir(parents=True, exist_ok=True)
                (root / "stop.request").touch()
                for ledger in root.glob("campaign-*"):
                    if ledger.is_dir():
                        (ledger / "stop.request").touch()
                self._send_bytes(
                    json.dumps({"ok": True, "action": "stop"}).encode("utf-8"),
                    "application/json; charset=utf-8",
                )
            elif self.path == "/api/clear-stop":
                report = recovery_tool.clear_stops(root)
                self._send_bytes(
                    json.dumps({"ok": True, "action": "clear-stop", **report}).encode("utf-8"),
                    "application/json; charset=utf-8",
                )
            else:
                self.send_error(404)

        def log_message(self, *_args):
            pass

    return ThreadingHTTPServer((host, port), Handler)


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
        args.state, port=args.port,
        allow_controls=args.allow_controls,
        include_providers=args.include_providers,
    )
    print(f"TEL99 cockpit listening on http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
