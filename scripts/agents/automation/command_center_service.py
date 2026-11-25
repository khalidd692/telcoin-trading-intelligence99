"""TEL99 Command Center backend service (REUSE-FIRST, zero second supervisor/router/memory).

Wires the browser Command Center directly to existing TEL99 modules:
- 12 official specialists (`specialist_dispatch`, `team_config`, `agent_cli`, `mentor_curriculum`)
- Multi-turn persistent conversations (isolated per session on disk, 8k-bounded context window)
- Real Commander / Coordinator delegation mode (invokes only relevant specialists sequentially)
- Non-blocking background chat job queue obeying global `concurrence=1` & CAS leases
- Autonomous project lifecycle (`autonomous_project_runner` detached runner, preview, launch, pause/resume/stop, read-only file viewer)
- Real on-disk telemetry for Skills, Memory, Academy, V3/V4 benchmarks, 12x12 Matrix, Passports, Docker Sandbox, Cloud Budget Ledger, and AI Radar.
"""
from __future__ import annotations

from datetime import datetime, timezone
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
from typing import Any, Callable
import uuid

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agents import specialist_dispatch, team_config
from scripts.agents.automation import (
    agent_cli,
    autonomous_project_runner,
    ide_coordination,
    local_deterministic_tools,
    mentor_curriculum,
    ollama_native,
    provider_router,
    smart_repair,
)
from scripts.agents.intelligence.memory import MemoryStore
from scripts.agents.native.provider import ProviderError

DESKTOP = Path.home() / "Desktop"
BENCH_STATE = DESKTOP / "TEL99_BENCHMARK_120_STATE"
CHAIN1_STATE = DESKTOP / "TEL99_LOCAL_CHAIN_STATE"
CHAIN2_STATE = DESKTOP / "TEL99_LOCAL_CHAIN_STATE_PHASE2"
AI_RADAR_DIR = DESKTOP / "AI_RADAR"
SKILLS_DIR = ROOT / ".agents" / "skills"
LOCAL_MODEL = "gemma4:e4b-tel99-8k"

AGENT_FRENCH_PROFILE: dict[str, dict[str, str]] = {
    "development": {
        "label_fr": "Développeur",
        "tagline": "Architecture logicielle, Python/JS, API et implémentation propre",
        "avatar": "DEV",
    },
    "quant": {
        "label_fr": "Analyste quantitatif",
        "tagline": "Modélisation, indicateurs causaux, mathématiques et statistiques",
        "avatar": "QNT",
    },
    "quality": {
        "label_fr": "Expert qualité",
        "tagline": "Tests indépendants, détection de régressions et critères d'acceptation",
        "avatar": "QA",
    },
    "security": {
        "label_fr": "Expert sécurité",
        "tagline": "Audit défensif, isolation, gestion des secrets et conformité",
        "avatar": "SEC",
    },
    "coordination": {
        "label_fr": "Coordinateur (Mode Commandant)",
        "tagline": "Décomposition d'objectifs, délégation multi-spécialistes et synthèse",
        "avatar": "CMD",
    },
    "cloud": {
        "label_fr": "Expert cloud",
        "tagline": "Conteneurs, déploiement, routage hybride et infrastructure",
        "avatar": "CLD",
    },
    "mobile": {
        "label_fr": "Développeur mobile",
        "tagline": "Interfaces responsives, UX web/mobile, accessibilité et frontend sûr",
        "avatar": "MOB",
    },
    "documentation": {
        "label_fr": "Documentaliste",
        "tagline": "Spécifications claires, guides, synthèses et traçabilité",
        "avatar": "DOC",
    },
    "evaluation": {
        "label_fr": "Expert évaluation",
        "tagline": "Métriques rigoureuses, protocoles de preuve et calibration",
        "avatar": "EVL",
    },
    "market_data": {
        "label_fr": "Expert données",
        "tagline": "Ingestion, nettoyage, validation de schémas et pipelines de données",
        "avatar": "DAT",
    },
    "monitoring": {
        "label_fr": "Expert surveillance",
        "tagline": "Observabilité, télémétrie, diagnostic de pannes et alertes",
        "avatar": "MON",
    },
    "release": {
        "label_fr": "Expert livraison",
        "tagline": "Packaging, scripts de lancement, CI/CD et mise en service sûre",
        "avatar": "REL",
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json_safe(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _safe_conv_id(conv_id: str) -> str:
    if not isinstance(conv_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{4,64}", conv_id):
        raise ValueError("identifiant de conversation invalide")
    return conv_id


def build_bounded_history_context(messages: list[dict[str, Any]], *, max_chars: int = 2600) -> str:
    """Build an 8k-safe multi-turn context block from real conversation messages (zero invention)."""
    valid = [
        m for m in (messages or [])
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and str(m.get("content") or "").strip()
    ]
    if not valid:
        return ""

    # Always keep the latest turns verbatim, summarize older turns cleanly if exceeding budget
    kept_rev: list[str] = []
    used = 0
    split_idx = len(valid)
    for idx in range(len(valid) - 1, -1, -1):
        m = valid[idx]
        speaker = "Utilisateur" if m["role"] == "user" else f"Assistant ({m.get('agent_name') or 'agent'})"
        body = str(m.get("content") or "").strip()
        if len(body) > 950:
            body = body[:950] + "…"
        line = f"{speaker}: {body}"
        if used + len(line) + 2 > max_chars and kept_rev:
            break
        kept_rev.append(line)
        used += len(line) + 2
        split_idx = idx

    parts: list[str] = []
    if split_idx > 0:
        older_notes: list[str] = []
        for m in valid[:split_idx]:
            tag = "U" if m["role"] == "user" else "A"
            snippet = " ".join(str(m.get("content") or "").split())[:130]
            older_notes.append(f"- [{tag}] {snippet}")
        summary_block = "Résumé factuel des échanges précédents:\n" + "\n".join(older_notes[-6:])
        parts.append(summary_block[:700])
    parts.append("Historique récent de la conversation:\n" + "\n\n".join(reversed(kept_rev)))
    return "\n\n".join(parts)


def get_enriched_team_catalog() -> list[dict[str, Any]]:
    """Return all 12 official TEL99 agents with French metadata, real passport levels, and V3/V4 scores."""
    overview = agent_cli.get_team_overview()
    v3 = _read_json_safe(BENCH_STATE / "artifacts" / "unseen_v3_report.json") or {}
    v4 = _read_json_safe(BENCH_STATE / "artifacts" / "unseen_v4_report.json") or {}
    v3_loc_by_role = ((v3.get("local_after") or {}).get("by_role") or {}) if isinstance(v3, dict) else {}
    v3_hyb_by_role = ((v3.get("hybrid_after") or {}).get("by_role") or {}) if isinstance(v3, dict) else {}
    v4_loc_by_role = ((v4.get("local") or {}).get("by_role") or {}) if isinstance(v4, dict) else {}
    spec_map = team_config.role_catalog()

    agents: list[dict[str, Any]] = []
    for row in overview.get("agents") or []:
        role = row["role"]
        fr = AGENT_FRENCH_PROFILE.get(role) or {
            "label_fr": role,
            "tagline": row.get("specialty", "Spécialiste TEL99"),
            "avatar": role[:3].upper(),
        }
        spec = spec_map.get(role)
        agents.append({
            **row,
            "label_fr": fr["label_fr"],
            "tagline": fr["tagline"],
            "avatar": fr["avatar"],
            "description": spec.description if spec else fr["tagline"],
            "is_commander": role == "coordination",
            "v3_local": v3_loc_by_role.get(role),
            "v3_hybrid": v3_hyb_by_role.get(role),
            "v4_local": v4_loc_by_role.get(role),
        })
    return agents


def _probe_ai_radar_live(port: int = 8780) -> dict[str, Any]:
    url = f"http://127.0.0.1:{port}/"
    try:
        conn = HTTPConnection("127.0.0.1", port, timeout=1.0)
        conn.request("GET", "/")
        resp = conn.getresponse()
        resp.read(256)
        conn.close()
        return {"online": resp.status == 200, "http_status": resp.status, "url": url}
    except OSError:
        return {"online": False, "http_status": None, "url": url}


def _default_model_call(
    *,
    system: str,
    prompt: str,
    role: str,
    hybrid: bool,
    confidential: bool,
    status_cb: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Invoke real local Ollama (concurrence=1 CAS) or opt-in free Groq mentor ($0.00, non-confidential only)."""
    policy = local_deterministic_tools.check_cloud_escalation_policy(
        confidential=confidential,
        allow_cloud=hybrid,
        prompt_text=f"{system}\n{prompt}",
    )
    use_cloud = bool(hybrid and policy["allowed"] and provider_router.load_local_provider_key("GROQ_API_KEY"))
    t0 = time.monotonic()

    if use_cloud:
        if status_cb:
            status_cb("RUNNING_HYBRID_FREE")
        mentor = (
            "qwen/qwen3.8-27b"
            if role in ("development", "mobile", "market_data")
            else "openai/gpt-oss-120b"
        )
        ad = provider_router.OpenAICompatFreeCloudAdapter(
            provider="groq",
            model=mentor,
            timeout=60,
            max_tokens=1400,
            confidential=False,
            fallback_ollama_model=LOCAL_MODEL,
        )
        reply = ad.complete(system=system, prompt=prompt)
        meta = dict(ad.last_metadata)
        prov = str(meta.get("provider_used") or "groq")
        mdl = str(meta.get("model_used") or mentor)
        return {
            "response": reply,
            "provider_used": prov,
            "model_used": mdl,
            "cloud_calls": 1 if prov == "groq" else 0,
            "cost_usd": 0.0,
            "duration_seconds": round(time.monotonic() - t0, 2),
            "cloud_policy_reason": policy["reason"],
        }

    # Check if local Ollama inference lease is held by another campaign
    leases = ide_coordination.active_leases(ide_coordination.default_coordination_state_root())
    active_inf = [l for l in (leases.get("active") or []) if "ollama" in str(l.get("resource_id") or "").lower()]
    if active_inf and status_cb:
        status_cb("WAITING_OLLAMA")

    eng = ide_coordination.probe_local_engines()
    resident = LOCAL_MODEL in ((eng.get("ollama") or {}).get("loaded_models") or [])
    budget = ollama_native.compute_adaptive_budget(
        LOCAL_MODEL,
        task_profile="module",
        estimated_lines=55,
        available_memory_mib=eng.get("available_memory_mib"),
        model_is_resident=resident,
    )
    if status_cb:
        status_cb("RUNNING_LOCAL")
    provider = ollama_native.OllamaNativeProvider(
        model=LOCAL_MODEL,
        timeout=budget["timeout"],
        max_tokens=min(1200, int(budget["max_tokens"])),
        keep_alive="120s",
        task_profile=budget["effective_profile"],
        num_ctx=budget["num_ctx"],
        num_thread=budget["num_thread"],
    )
    reply = provider.complete(system=system, prompt=prompt)
    return {
        "response": reply,
        "provider_used": "ollama",
        "model_used": LOCAL_MODEL,
        "cloud_calls": 0,
        "cost_usd": 0.0,
        "duration_seconds": round(time.monotonic() - t0, 2),
        "cloud_policy_reason": policy["reason"],
    }


class CommandCenterService:
    """Unified backend for conversations, Commander delegation, autonomous projects, and live telemetry."""

    def __init__(
        self,
        state_root: Path | str,
        *,
        model_caller: Callable[..., dict[str, Any]] | None = None,
    ):
        self.state_root = Path(state_root).resolve()
        self.cc_dir = self.state_root / "command_center"
        self.conv_dir = self.cc_dir / "conversations"
        self.registry_path = self.cc_dir / "projects_registry.json"
        self.cc_dir.mkdir(parents=True, exist_ok=True)
        self.conv_dir.mkdir(parents=True, exist_ok=True)
        self._model_caller = model_caller or _default_model_call

        self._jobs_lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._cancel_flags: dict[str, threading.Event] = {}
        self._job_queue: queue.Queue[str] = queue.Queue()
        self._worker = threading.Thread(target=self._worker_loop, name="tel99-cc-chat-worker", daemon=True)
        self._worker.start()

    # ------------------------------------------------------------------
    # Conversations CRUD (isolated per session, atomic locked JSON)
    # ------------------------------------------------------------------

    def _conv_path(self, conv_id: str) -> Path:
        cid = _safe_conv_id(conv_id)
        return self.conv_dir / f"{cid}.json"

    def list_conversations(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for p in sorted(self.conv_dir.glob("*.json")):
            data = _read_json_safe(p)
            if not isinstance(data, dict) or not data.get("id"):
                continue
            msgs = data.get("messages") or []
            rows.append({
                "id": data["id"],
                "title": data.get("title") or "Nouvelle conversation",
                "role": data.get("role") or "coordination",
                "team_mode": bool(data.get("team_mode")),
                "confidential": bool(data.get("confidential", True)),
                "hybrid": bool(data.get("hybrid", False)),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "message_count": len(msgs),
                "last_preview": (str(msgs[-1].get("content") or "")[:90] if msgs else ""),
            })
        rows.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
        return rows

    def create_conversation(
        self,
        *,
        title: str = "Nouvelle conversation",
        role: str = "coordination",
        team_mode: bool | None = None,
        confidential: bool = True,
        hybrid: bool = False,
    ) -> dict[str, Any]:
        spec = specialist_dispatch.resolve_specialist(role)
        # Safety invariant: confidential=True strictly disables hybrid cloud
        eff_conf = bool(confidential)
        eff_hyb = bool(hybrid and not eff_conf)
        eff_team = (spec.role == "coordination") if team_mode is None else bool(team_mode)
        now = _now_iso()
        cid = f"conv-{uuid.uuid4().hex[:12]}"
        conv = {
            "schema_version": 1,
            "id": cid,
            "title": (str(title or "").strip() or "Nouvelle conversation")[:100],
            "role": spec.role,
            "agent_name": spec.name,
            "team_mode": eff_team,
            "confidential": eff_conf,
            "hybrid": eff_hyb,
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        local_deterministic_tools.write_json_atomic_locked(self._conv_path(cid), conv)
        return conv

    def get_conversation(self, conv_id: str) -> dict[str, Any]:
        p = self._conv_path(conv_id)
        data = _read_json_safe(p)
        if not isinstance(data, dict):
            raise KeyError(f"conversation introuvable: {conv_id}")
        return data

    def update_conversation(
        self,
        conv_id: str,
        *,
        title: str | None = None,
        role: str | None = None,
        team_mode: bool | None = None,
        confidential: bool | None = None,
        hybrid: bool | None = None,
    ) -> dict[str, Any]:
        p = self._conv_path(conv_id)
        if not p.is_file():
            raise KeyError(f"conversation introuvable: {conv_id}")

        def _upd(cur: dict[str, Any]) -> dict[str, Any]:
            if title is not None and str(title).strip():
                cur["title"] = str(title).strip()[:100]
            if role is not None:
                spec = specialist_dispatch.resolve_specialist(role)
                cur["role"] = spec.role
                cur["agent_name"] = spec.name
            if team_mode is not None:
                cur["team_mode"] = bool(team_mode)
            if confidential is not None:
                cur["confidential"] = bool(confidential)
                if cur["confidential"]:
                    cur["hybrid"] = False
            if hybrid is not None:
                cur["hybrid"] = bool(hybrid and not cur.get("confidential", True))
            cur["updated_at"] = _now_iso()
            return cur

        return local_deterministic_tools.locked_json_update(p, _upd)

    def delete_conversation(self, conv_id: str) -> dict[str, Any]:
        p = self._conv_path(conv_id)
        if not p.is_file():
            raise KeyError(f"conversation introuvable: {conv_id}")
        p.unlink(missing_ok=True)
        return {"ok": True, "deleted": conv_id}

    # ------------------------------------------------------------------
    # Non-Blocking Chat & Commander Delegation Queue
    # ------------------------------------------------------------------

    def submit_chat_message(
        self,
        *,
        conv_id: str,
        message: str,
        role: str | None = None,
        team_mode: bool | None = None,
        confidential: bool | None = None,
        hybrid: bool | None = None,
    ) -> dict[str, Any]:
        text = str(message or "").strip()
        if not text:
            raise ValueError("Le message ne peut pas être vide.")
        if len(text) > 12_000:
            raise ValueError("Message trop long (max 12 000 caractères).")

        inj = local_deterministic_tools.detect_prompt_injection(text)
        if not inj["safe"]:
            raise PermissionError("Requête bloquée par la sécurité : motif d'injection de prompt détecté.")
        if not local_deterministic_tools.detect_secret_leak(text)["safe"]:
            raise PermissionError("Requête bloquée : secret ou jeton sensible détecté dans le message.")

        conv = self.get_conversation(conv_id)
        if role is not None or team_mode is not None or confidential is not None or hybrid is not None:
            conv = self.update_conversation(
                conv_id, role=role, team_mode=team_mode, confidential=confidential, hybrid=hybrid
            )

        eff_role = conv["role"]
        eff_conf = bool(conv.get("confidential", True))
        eff_hyb = bool(conv.get("hybrid", False) and not eff_conf)
        eff_team = bool(conv.get("team_mode", eff_role == "coordination"))

        # Append user message durably immediately
        user_msg = {
            "id": f"msg-{uuid.uuid4().hex[:10]}",
            "role": "user",
            "content": text,
            "created_at": _now_iso(),
        }
        p = self._conv_path(conv_id)

        def _append_user(cur: dict[str, Any]) -> dict[str, Any]:
            cur.setdefault("messages", []).append(user_msg)
            if cur.get("title") in ("Nouvelle conversation", "") and len(cur["messages"]) == 1:
                cur["title"] = text.splitlines()[0][:64]
            cur["updated_at"] = _now_iso()
            return cur

        local_deterministic_tools.locked_json_update(p, _append_user)

        job_id = f"job-{uuid.uuid4().hex[:12]}"
        cancel_ev = threading.Event()
        job = {
            "job_id": job_id,
            "conversation_id": conv_id,
            "status": "QUEUED",
            "phase": "En file d'attente",
            "role": eff_role,
            "agent_name": conv.get("agent_name") or specialist_dispatch.resolve_specialist(eff_role).name,
            "team_mode": eff_team,
            "confidential": eff_conf,
            "hybrid": eff_hyb,
            "delegated_specialists": [],
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "started_at": None,
            "finished_at": None,
            "provider_used": None,
            "model_used": None,
            "duration_seconds": None,
            "error": None,
            "assistant_message": None,
            "prompt_text": text,
        }
        with self._jobs_lock:
            self._jobs[job_id] = job
            self._cancel_flags[job_id] = cancel_ev
        self._job_queue.put(job_id)
        return self._public_job(job)

    @staticmethod
    def _public_job(job: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in job.items() if k != "prompt_text"}

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(f"job introuvable: {job_id}")
            return self._public_job(dict(job))

    def list_jobs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._jobs_lock:
            rows = [self._public_job(dict(j)) for j in self._jobs.values()]
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return rows[:limit]

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(f"job introuvable: {job_id}")
            ev = self._cancel_flags.get(job_id)
            if ev:
                ev.set()
            if job["status"] in ("QUEUED", "WAITING_OLLAMA"):
                job["status"] = "CANCELLED"
                job["phase"] = "Annulé par l'utilisateur"
                job["finished_at"] = _now_iso()
                job["updated_at"] = _now_iso()
            elif job["status"] in ("RUNNING", "DELEGATING"):
                job["phase"] = "Annulation demandée…"
                job["updated_at"] = _now_iso()
            return self._public_job(dict(job))

    def _set_job(self, job_id: str, **fields: Any) -> None:
        with self._jobs_lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(fields)
                self._jobs[job_id]["updated_at"] = _now_iso()

    def _build_specialist_prompts(
        self,
        *,
        role: str,
        user_text: str,
        history_block: str,
        extra_instructions: str = "",
    ) -> tuple[str, str, str]:
        spec = specialist_dispatch.resolve_specialist(role)
        fr = AGENT_FRENCH_PROFILE.get(spec.role) or {"label_fr": spec.role, "tagline": spec.description}
        mem_dir = BENCH_STATE / "memory"
        ctx = mentor_curriculum.build_two_layer_generalist_context(
            agent_role=spec.role,
            target_domain=spec.role,
            skills_dir=SKILLS_DIR,
            memory_dir=mem_dir if mem_dir.is_dir() else None,
            objective=user_text,
        )
        system = (
            f"Tu es {spec.name} ({fr['label_fr']} — {fr['tagline']}), spécialiste officiel de l'équipe TEL99.\n"
            "Réponds en français de manière claire, structurée, précise et honnête sur tes limites.\n"
            "Ne prétends jamais avoir exécuté des commandes ou écrit des fichiers en mode conversation simple.\n"
            "Sécurité stricte : aucun secret, aucune commande destructrice, aucun eval/exec/shell=True/0.0.0.0.\n"
            "Respecte fidèlement les informations et contraintes fournies dans l'historique de cette session.\n"
            + (f"\n{extra_instructions}\n" if extra_instructions else "")
        )
        prompt = (
            (f"{history_block}\n\n" if history_block else "")
            + f"Nouvelle demande de l'utilisateur :\n{user_text}\n\n"
            + f"Contexte Skill & mémoire vérifiée :\n{ctx['context_text'][:1800]}"
        )
        return spec.name, system, prompt

    def _worker_loop(self) -> None:
        while True:
            job_id = self._job_queue.get()
            try:
                self._process_job(job_id)
            except Exception as exc:
                self._set_job(
                    job_id,
                    status="ERROR",
                    phase="Erreur interne",
                    error=f"{type(exc).__name__}: {str(exc)[:260]}",
                    finished_at=_now_iso(),
                )
            finally:
                self._job_queue.task_done()

    def _process_job(self, job_id: str) -> None:
        with self._jobs_lock:
            job = dict(self._jobs.get(job_id) or {})
            cancel_ev = self._cancel_flags.get(job_id)
        if not job or job.get("status") == "CANCELLED" or (cancel_ev and cancel_ev.is_set()):
            self._set_job(job_id, status="CANCELLED", phase="Annulé par l'utilisateur", finished_at=_now_iso())
            return

        t0 = time.monotonic()
        self._set_job(job_id, status="RUNNING", phase="Préparation du contexte…", started_at=_now_iso())

        conv_id = job["conversation_id"]
        conv = self.get_conversation(conv_id)
        # History EXCLUDING the very last user message we are answering right now
        all_msgs = list(conv.get("messages") or [])
        prior_msgs = all_msgs[:-1] if (all_msgs and all_msgs[-1].get("role") == "user") else all_msgs
        history_block = build_bounded_history_context(prior_msgs, max_chars=2400)
        user_text = str(job["prompt_text"])
        eff_role = job["role"]
        eff_team = bool(job["team_mode"])
        eff_conf = bool(job["confidential"])
        eff_hyb = bool(job["hybrid"])

        def _status_cb(code: str) -> None:
            labels = {
                "WAITING_OLLAMA": "En attente d'Ollama local (concurrence=1)…",
                "RUNNING_LOCAL": f"Inférence locale ({LOCAL_MODEL})…",
                "RUNNING_HYBRID_FREE": "Inférence hybride gratuite autorisée…",
            }
            st = "WAITING_OLLAMA" if code == "WAITING_OLLAMA" else ("DELEGATING" if eff_team else "RUNNING")
            self._set_job(job_id, status=st, phase=labels.get(code, code))

        delegated_results: list[dict[str, Any]] = []
        total_cloud_calls = 0

        try:
            if eff_team:
                # Commander mode: pick 2 genuinely relevant specialists (never artificially all 12!)
                picks = specialist_dispatch.select_specialists(user_text, include_verifier=False, max_specialists=3)
                chosen_roles = [p["role"] for p in picks if p["role"] != "coordination"][:2]
                if len(chosen_roles) < 2:
                    for fallback_r in ("development", "security", "documentation"):
                        if fallback_r not in chosen_roles and fallback_r != "coordination":
                            chosen_roles.append(fallback_r)
                        if len(chosen_roles) >= 2:
                            break

                for s_role in chosen_roles:
                    if cancel_ev and cancel_ev.is_set():
                        self._set_job(job_id, status="CANCELLED", phase="Annulé avant délégation", finished_at=_now_iso())
                        return
                    fr_lbl = (AGENT_FRENCH_PROFILE.get(s_role) or {}).get("label_fr", s_role)
                    self._set_job(job_id, status="DELEGATING", phase=f"Délégation réelle à {fr_lbl}…")
                    s_name, s_sys, s_usr = self._build_specialist_prompts(
                        role=s_role,
                        user_text=user_text,
                        history_block=history_block,
                        extra_instructions=(
                            "Tu contribues en tant que spécialiste consulté par le Coordinateur TEL99. "
                            "Donne une contribution concrète, concise (<= 10 lignes), actionnable dans ton domaine."
                        ),
                    )
                    s_res = self._model_caller(
                        system=s_sys,
                        prompt=s_usr,
                        role=s_role,
                        hybrid=eff_hyb,
                        confidential=eff_conf,
                        status_cb=_status_cb,
                    )
                    total_cloud_calls += int(s_res.get("cloud_calls") or 0)
                    s_text = str(s_res.get("response") or "").strip()
                    if not local_deterministic_tools.detect_secret_leak(s_text)["safe"]:
                        s_text = "[Réponse filtrée par sécurité : motif de secret détecté]"
                    delegated_results.append({
                        "role": s_role,
                        "agent_name": s_name,
                        "label_fr": fr_lbl,
                        "provider_used": s_res.get("provider_used"),
                        "model_used": s_res.get("model_used"),
                        "duration_seconds": s_res.get("duration_seconds"),
                        "response": s_text,
                    })
                    self._set_job(job_id, delegated_specialists=list(delegated_results))

                if cancel_ev and cancel_ev.is_set():
                    self._set_job(job_id, status="CANCELLED", phase="Annulé avant synthèse", finished_at=_now_iso())
                    return

                self._set_job(job_id, status="RUNNING", phase="Synthèse du Coordinateur…")
                contrib_blob = "\n\n".join(
                    f"[{d['label_fr']} / {d['agent_name']} — {d['model_used']}]\n{d['response'][:700]}"
                    for d in delegated_results
                )
                c_name, c_sys, c_usr = self._build_specialist_prompts(
                    role="coordination",
                    user_text=(
                        f"{user_text}\n\n"
                        f"Contributions réelles reçues de tes spécialistes :\n{contrib_blob}\n\n"
                        "Synthétise ces contributions en un plan concret, cohérent et actionnable en français, "
                        "en indiquant clairement ce qui relève de la discussion et ce qui pourrait faire l'objet d'un projet autonome."
                    ),
                    history_block=history_block,
                )
                final_res = self._model_caller(
                    system=c_sys,
                    prompt=c_usr,
                    role="coordination",
                    hybrid=eff_hyb,
                    confidential=eff_conf,
                    status_cb=_status_cb,
                )
                total_cloud_calls += int(final_res.get("cloud_calls") or 0)
                reply_agent = c_name
                reply_role = "coordination"
            else:
                a_name, a_sys, a_usr = self._build_specialist_prompts(
                    role=eff_role,
                    user_text=user_text,
                    history_block=history_block,
                )
                final_res = self._model_caller(
                    system=a_sys,
                    prompt=a_usr,
                    role=eff_role,
                    hybrid=eff_hyb,
                    confidential=eff_conf,
                    status_cb=_status_cb,
                )
                total_cloud_calls += int(final_res.get("cloud_calls") or 0)
                reply_agent = a_name
                reply_role = eff_role

            if cancel_ev and cancel_ev.is_set():
                self._set_job(job_id, status="CANCELLED", phase="Annulé par l'utilisateur", finished_at=_now_iso())
                return

            reply_text = str(final_res.get("response") or "").strip()
            if not local_deterministic_tools.detect_secret_leak(reply_text)["safe"]:
                reply_text = "[BLOQUÉ : un motif de secret sensible a été détecté dans la sortie]"

            dur = round(time.monotonic() - t0, 2)
            asst_msg = {
                "id": f"msg-{uuid.uuid4().hex[:10]}",
                "role": "assistant",
                "content": reply_text,
                "agent_role": reply_role,
                "agent_name": reply_agent,
                "label_fr": (AGENT_FRENCH_PROFILE.get(reply_role) or {}).get("label_fr", reply_role),
                "provider_used": final_res.get("provider_used"),
                "model_used": final_res.get("model_used"),
                "cloud_calls": total_cloud_calls,
                "cost_usd": 0.0,
                "confidential": eff_conf,
                "hybrid": eff_hyb,
                "response_kind": "team_synthesis" if eff_team else "discussion",
                "delegated_specialists": delegated_results,
                "duration_seconds": dur,
                "created_at": _now_iso(),
            }

            p = self._conv_path(conv_id)
            if p.is_file():
                def _append_asst(cur: dict[str, Any]) -> dict[str, Any]:
                    cur.setdefault("messages", []).append(asst_msg)
                    cur["updated_at"] = _now_iso()
                    return cur
                local_deterministic_tools.locked_json_update(p, _append_asst)

            self._set_job(
                job_id,
                status="DONE",
                phase="Terminé",
                provider_used=asst_msg["provider_used"],
                model_used=asst_msg["model_used"],
                duration_seconds=dur,
                delegated_specialists=delegated_results,
                assistant_message=asst_msg,
                finished_at=_now_iso(),
            )
        except ProviderError as exc:
            self._set_job(
                job_id,
                status="ERROR",
                phase="Ressource modèle indisponible",
                error=f"Modèle temporairement indisponible : {str(exc)[:220]}",
                finished_at=_now_iso(),
            )
        except Exception as exc:
            self._set_job(
                job_id,
                status="ERROR",
                phase="Erreur d'exécution",
                error=f"{type(exc).__name__}: {str(exc)[:220]}",
                finished_at=_now_iso(),
            )

    # ------------------------------------------------------------------
    # Autonomous Projects Management (wired to autonomous_project_runner)
    # ------------------------------------------------------------------

    def _load_registry(self) -> list[dict[str, Any]]:
        data = _read_json_safe(self.registry_path)
        items = list(data.get("projects") or []) if isinstance(data, dict) else []
        known_paths = {str(Path(it["path"]).resolve()).lower() for it in items if isinstance(it, dict) and it.get("path")}
        # Auto-discover well-known Desktop projects without overwriting user entries
        for default_dir in (
            DESKTOP / "TEL99_BUDGET_FAMILIAL_V2",
            DESKTOP / "TEL99_GENERALIZATION_NOTES",
            DESKTOP / "TEL99_BUDGET_FAMILIAL",
            AI_RADAR_DIR,
        ):
            if default_dir.is_dir():
                rp = str(default_dir.resolve())
                if rp.lower() not in known_paths:
                    items.append({"path": rp, "added_at": _now_iso(), "discovered": True})
                    known_paths.add(rp.lower())
        return items

    def _register_project_path(self, project_dir: Path, *, goal: str = "") -> None:
        rp = str(project_dir.resolve())

        def _upd(cur: dict[str, Any]) -> dict[str, Any]:
            projs = list(cur.get("projects") or [])
            for item in projs:
                if isinstance(item, dict) and str(item.get("path") or "").lower() == rp.lower():
                    item["updated_at"] = _now_iso()
                    if goal:
                        item["last_goal"] = goal[:400]
                    cur["projects"] = projs
                    return cur
            projs.append({"path": rp, "added_at": _now_iso(), "updated_at": _now_iso(), "last_goal": goal[:400]})
            cur["projects"] = projs
            return cur

        local_deterministic_tools.locked_json_update(self.registry_path, _upd)

    def _validate_target_project_dir(self, raw_path: str) -> Path:
        txt = str(raw_path or "").strip()
        if not txt or "\x00" in txt:
            raise ValueError("Chemin du dossier projet requis.")
        p = Path(txt)
        if not p.is_absolute():
            # Allow convenient folder name under Desktop
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", txt).strip("._")
            if not safe_name or ".." in txt or "/" in txt or "\\" in txt:
                raise ValueError("Nom de dossier projet invalide.")
            p = DESKTOP / safe_name
        if p.is_symlink() or os.path.islink(p):
            raise PermissionError("Les liens symboliques / jonctions sont interdits comme dossier projet.")
        err = autonomous_project_runner._is_forbidden_workspace(p)
        if err:
            raise PermissionError(err)
        return p.resolve()

    def preview_project_scope(
        self,
        *,
        goal_text: str,
        project_dir: str,
        confidential: bool = True,
        hybrid: bool = False,
    ) -> dict[str, Any]:
        goal = str(goal_text or "").strip()
        if len(goal) < 12:
            raise ValueError("Décrivez votre projet en au moins 12 caractères.")
        inj = local_deterministic_tools.detect_prompt_injection(goal)
        if not inj["safe"]:
            raise PermissionError("Objectif bloqué : motif d'injection de prompt détecté.")
        if not local_deterministic_tools.detect_secret_leak(goal)["safe"]:
            raise PermissionError("Objectif bloqué : secret sensible détecté.")

        target = self._validate_target_project_dir(project_dir)
        slug = autonomous_project_runner._slugify_project(target.name)
        manifest = autonomous_project_runner.build_requirements_manifest(goal, project_slug=slug)
        eff_conf = bool(confidential)
        eff_hyb = bool(hybrid and not eff_conf)
        docker_ready, docker_reason = autonomous_project_runner.check_docker_sandbox_ready()
        existing_plan = _read_json_safe(target / "artifacts" / "project_plan.json")
        goal_mismatch = False
        if isinstance(existing_plan, dict) and existing_plan.get("goal_sha256"):
            goal_mismatch = existing_plan["goal_sha256"] != manifest["goal_sha256"]

        return {
            "ok": True,
            "project_slug": slug,
            "workspace_root": str(target),
            "existing_workspace": target.exists(),
            "existing_plan": isinstance(existing_plan, dict),
            "goal_mismatch_requires_revision": goal_mismatch,
            "confidential": eff_conf,
            "hybrid": eff_hyb,
            "docker_sandbox_ready": docker_ready,
            "docker_sandbox_reason": docker_reason,
            "requirements_count": len(manifest["requirements"]),
            "requirements": manifest["requirements"],
        }

    def launch_autonomous_project(
        self,
        *,
        goal_text: str,
        project_dir: str,
        confidential: bool = True,
        hybrid: bool = False,
        resume_rejected: bool = False,
        revise_plan: bool = False,
        confirmed: bool = False,
        spawn_process: bool = True,
    ) -> dict[str, Any]:
        if not confirmed:
            raise PermissionError("Confirmation explicite du périmètre requise avant lancement.")
        preview = self.preview_project_scope(
            goal_text=goal_text, project_dir=project_dir, confidential=confidential, hybrid=hybrid
        )
        target = Path(preview["workspace_root"])
        if autonomous_project_runner._is_runner_active(target):
            return {
                "ok": False,
                "status": "LOCKED",
                "workspace_root": str(target),
                "error": "Un orchestrateur autonome est déjà actif sur ce dossier projet.",
            }
        if preview["goal_mismatch_requires_revision"] and not revise_plan:
            return {
                "ok": False,
                "status": "BLOCKED",
                "workspace_root": str(target),
                "reason": "goal_or_scope_mismatch",
                "error": "Ce dossier contient déjà un plan scellé pour un autre objectif. Choisissez un nouveau dossier ou cochez 'Réviser le plan'.",
            }

        target.mkdir(parents=True, exist_ok=True)
        log_dir = target / "artifacts"
        log_dir.mkdir(parents=True, exist_ok=True)
        self._register_project_path(target, goal=goal_text)

        argv = [
            sys.executable, "-B", "-m", "scripts.agents.automation.autonomous_project_runner",
            "--project", str(target),
            "--task", goal_text.strip(),
        ]
        if preview["hybrid"]:
            argv.append("--hybrid")
        if preview["confidential"]:
            argv.append("--confidential")
        if resume_rejected:
            argv.append("--resume-rejected")
        if revise_plan:
            argv.append("--revise-plan")

        pid = None
        if spawn_process:
            out_f = (log_dir / "runner.log").open("ab")
            err_f = (log_dir / "runner.err.log").open("ab")
            creation = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
            proc = subprocess.Popen(
                argv,
                cwd=str(ROOT),
                stdout=out_f,
                stderr=err_f,
                creationflags=creation,
                close_fds=True,
            )
            pid = proc.pid
            out_f.close()
            err_f.close()

        return {
            "ok": True,
            "status": "LAUNCHED" if spawn_process else "DRY_LAUNCHED",
            "pid": pid,
            "project_slug": preview["project_slug"],
            "workspace_root": str(target),
            "confidential": preview["confidential"],
            "hybrid": preview["hybrid"],
            "requirements_count": preview["requirements_count"],
        }

    def control_autonomous_project(
        self,
        *,
        project_dir: str,
        action: str,
        hybrid: bool = False,
        confidential: bool = True,
        resume_rejected: bool = False,
        spawn_on_resume: bool = True,
    ) -> dict[str, Any]:
        target = self._validate_target_project_dir(project_dir)
        if action not in ("pause", "resume", "stop"):
            raise ValueError(f"Action projet inconnue: {action!r}")
        ctrl = autonomous_project_runner.control_project(target, action)
        restarted_pid = None
        if action == "resume" and not ctrl.get("runner_active") and spawn_on_resume:
            plan = _read_json_safe(target / "artifacts" / "project_plan.json")
            if isinstance(plan, dict) and str(plan.get("goal") or "").strip():
                argv = [
                    sys.executable, "-B", "-m", "scripts.agents.automation.autonomous_project_runner",
                    "--project", str(target),
                    "--resume-process",
                ]
                if hybrid and not confidential:
                    argv.append("--hybrid")
                if confidential:
                    argv.append("--confidential")
                if resume_rejected:
                    argv.append("--resume-rejected")
                log_dir = target / "artifacts"
                log_dir.mkdir(parents=True, exist_ok=True)
                out_f = (log_dir / "runner.log").open("ab")
                err_f = (log_dir / "runner.err.log").open("ab")
                creation = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
                proc = subprocess.Popen(
                    argv, cwd=str(ROOT), stdout=out_f, stderr=err_f, creationflags=creation, close_fds=True
                )
                restarted_pid = proc.pid
                out_f.close()
                err_f.close()
        return {**ctrl, "workspace_root": str(target), "restarted_pid": restarted_pid}

    def list_projects(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for entry in self._load_registry():
            p = Path(entry["path"])
            if not p.is_dir():
                continue
            prog = autonomous_project_runner.get_project_progress(p)
            manifest = _read_json_safe(p / "artifacts" / "requirements_manifest.json") or {}
            deliv = _read_json_safe(p / "artifacts" / "delivery_report.json") or {}
            plan = _read_json_safe(p / "artifacts" / "project_plan.json") or {}
            log_tail = ""
            log_p = p / "artifacts" / "runner.log"
            if log_p.is_file():
                try:
                    lines = log_p.read_text(encoding="utf-8", errors="replace").splitlines()
                    log_tail = "\n".join(lines[-12:])
                except OSError:
                    pass
            # List safe deliverable files present on disk
            files_on_disk: list[str] = []
            for fp in sorted(p.rglob("*")):
                if not fp.is_file():
                    continue
                rel = fp.relative_to(p)
                if rel.parts[0].lower() in autonomous_project_runner.RESERVED_PROJECT_TOP_DIRS or "__pycache__" in rel.parts:
                    continue
                files_on_disk.append(str(rel).replace("\\", "/"))
                if len(files_on_disk) >= 40:
                    break
            rows.append({
                "path": str(p.resolve()),
                "name": p.name,
                "project": prog.get("project") or p.name,
                "initialized": bool(prog.get("initialized")),
                "status": prog.get("status") or ("LIVE_APP" if p.name == "AI_RADAR" else "UNINITIALIZED"),
                "ok": bool(deliv.get("ok")) or (p.name == "AI_RADAR" and (p / "tests" / "verify_ai_radar.py").is_file()),
                "runner_active": bool(prog.get("runner_active")),
                "paused": bool(prog.get("paused")),
                "stopped": bool(prog.get("stopped")),
                "goal": prog.get("goal") or entry.get("last_goal") or "",
                "plan_revision": prog.get("plan_revision") or plan.get("plan_revision") or 1,
                "missions_accepted": prog.get("missions_accepted"),
                "missions_total": prog.get("missions_total"),
                "deliverables": prog.get("deliverables") or [],
                "files_on_disk": files_on_disk,
                "requirements_summary": prog.get("requirements_summary"),
                "requirements": (manifest.get("requirements") or [])[:20] if isinstance(manifest, dict) else [],
                "agents_called": deliv.get("agents_called") or [],
                "deterministic_verifiers_run": deliv.get("deterministic_verifiers_run") or [],
                "post_build_verification": deliv.get("post_build_verification"),
                "startup_command": prog.get("startup_command") or plan.get("startup_command") or "",
                "log_tail": log_tail,
                "loopback_url": "http://127.0.0.1:8780/" if p.name == "AI_RADAR" else None,
            })
        return rows

    def read_project_file(self, *, project_dir: str, rel_path: str) -> dict[str, Any]:
        target_root = self._validate_target_project_dir(project_dir)
        fp = local_deterministic_tools.safe_subpath(
            target_root,
            rel_path,
            blocked_top_dirs=autonomous_project_runner.RESERVED_PROJECT_TOP_DIRS,
        )
        if not fp.is_file():
            raise FileNotFoundError(f"Fichier introuvable: {rel_path}")
        raw = fp.read_bytes()
        if len(raw) > 65_536:
            text = raw[:65_536].decode("utf-8", errors="replace") + "\n\n... [tronqué à 64 Ko]"
        else:
            text = raw.decode("utf-8", errors="replace")
        if not local_deterministic_tools.detect_secret_leak(text)["safe"]:
            raise PermissionError("Affichage bloqué : motif de secret détecté dans ce fichier.")
        return {
            "ok": True,
            "project_dir": str(target_root),
            "rel_path": rel_path,
            "size_bytes": len(raw),
            "content": text,
        }

    # ------------------------------------------------------------------
    # Unified Real Telemetry for Command Center Spaces
    # ------------------------------------------------------------------

    def build_command_center_state(self) -> dict[str, Any]:
        v3 = _read_json_safe(BENCH_STATE / "artifacts" / "unseen_v3_report.json") or {}
        v4 = _read_json_safe(BENCH_STATE / "artifacts" / "unseen_v4_report.json") or {}
        matrix = _read_json_safe(BENCH_STATE / "artifacts" / "competency_matrix_12x12.json") or {}
        academy = _read_json_safe(AI_RADAR_DIR / "artifacts" / "academy_12_agents_report.json") or {}
        chain2 = _read_json_safe(CHAIN2_STATE / "local_chain_report.json") or {}
        endurance = _read_json_safe(DESKTOP / "TEL99_ENDURANCE_20261125_RUN3" / "hour_campaign_report.json") or {}

        # Read real collective memory entries (verified & unverified clearly labeled)
        mem_entries: list[dict[str, Any]] = []
        for mem_root in (BENCH_STATE / "memory", self.state_root / "learning" / "memory"):
            if mem_root.is_dir():
                try:
                    st = MemoryStore(mem_root)
                    for e in st.all_entries("tel99", include_common=True)[-40:]:
                        mem_entries.append({
                            "id": e.id,
                            "project": e.project,
                            "kind": e.kind,
                            "title": e.title,
                            "body": (e.body or "")[:260],
                            "author": e.author,
                            "verified": bool(e.verified),
                            "verified_by": e.verified_by,
                            "created_at": e.created_at,
                        })
                except Exception:
                    pass

        docker_ready, docker_reason = autonomous_project_runner.check_docker_sandbox_ready()
        budget_ledger = provider_router.CloudBudgetLedger()
        cloud_budgets = {
            "groq": budget_ledger.status("groq"),
            "openrouter": budget_ledger.status("openrouter"),
        }
        ai_radar = _probe_ai_radar_live(8780)
        engines = ide_coordination.probe_local_engines()
        leases = ide_coordination.active_leases(self.state_root)

        return {
            "schema_version": 1,
            "generated_at": _now_iso(),
            "team": get_enriched_team_catalog(),
            "conversations": self.list_conversations(),
            "chat_jobs": self.list_jobs(limit=15),
            "projects": self.list_projects(),
            "ai_radar": ai_radar,
            "docker_sandbox": {
                "ready": docker_ready,
                "reason": docker_reason,
                "image": autonomous_project_runner.DEFAULT_SANDBOX_IMAGE,
            },
            "engines": engines,
            "leases": leases,
            "cloud_budgets": cloud_budgets,
            "certification": {
                "v3_local_after": (v3.get("local_after") or {}) if isinstance(v3, dict) else {},
                "v3_hybrid_after": (v3.get("hybrid_after") or {}) if isinstance(v3, dict) else {},
                "v4_local": (v4.get("local") or {}) if isinstance(v4, dict) else {},
                "v4_hybrid": (v4.get("hybrid") or {}) if isinstance(v4, dict) else {},
                "matrix_global": (matrix.get("global_metrics") or {}) if isinstance(matrix, dict) else {},
                "academy": {
                    "before_rate": academy.get("baseline_pass_rate") or academy.get("before_rate"),
                    "after_rate": academy.get("after_pass_rate") or academy.get("after_rate"),
                } if isinstance(academy, dict) else {},
                "phase2_chain": {
                    "status": chain2.get("status"),
                    "pid": chain2.get("pid"),
                    "steps_done": list((chain2.get("steps") or {}).keys()),
                    "steps_requested": chain2.get("steps_requested") or [],
                } if isinstance(chain2, dict) else {},
                "endurance_run3": {
                    "status": endurance.get("status"),
                    "duration_minutes": endurance.get("duration_minutes"),
                    "missions_accepted": endurance.get("missions_accepted"),
                    "missions_total": endurance.get("missions_total"),
                } if isinstance(endurance, dict) else {},
            },
            "memory_entries": mem_entries[-60:],
            "skills": sorted(p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md") if p.is_file()),
        }
