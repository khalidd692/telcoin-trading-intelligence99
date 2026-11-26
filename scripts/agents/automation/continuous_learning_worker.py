"""Safe, user-prioritized background continuous learning & proactive initiative worker (G5, G6 & G8).

Strictly Reuse-First (ZERO second supervisor, ZERO parallel system):
- Reuses ``MemoryStore`` + ``Entry`` (``scripts/agents/intelligence/memory.py``)
- Reuses ``learning_loop.retrieve_scoped_lessons``
- Reuses ``metacognition.explore_approaches`` (bounded <= 3 approaches) and ``scrub_secrets``
- Reuses ``ide_coordination`` (owner interactive priority, RAM guard, local inference lease)
- Reuses ``local_deterministic_tools.deterministic_security_gate``
- NEVER runs LoRA weight training on the 16 GB host (knowledge/memory/procedural only).
- NEVER competes with owner interactive sessions: yields immediately when
  ``owner_interactive_priority_active()`` is true or RAM is below guard threshold.
- NEVER creates human approvals, NEVER modifies production, NEVER merges ``main``,
  NEVER sends external messages, NEVER places financial orders, NEVER scans private data.
- NEVER uses held-out V3/V4 benchmark task IDs for training.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agents.automation import (
    ide_coordination,
    learning_loop,
    local_deterministic_tools,
    metacognition,
    ollama_native,
)
from scripts.agents.intelligence.memory import COMMON_PROJECT, Entry, MemoryStore

DEFAULT_MIN_FREE_RAM_MIB = 2500
RESIDENT_MIN_FREE_RAM_MIB = 950
TRAINING_PROJECT = "tel99"
PROACTIVE_STATUSES = ("DONE", "PARTIAL", "PROPOSAL", "NO_USEFUL_TASK")
FEEDBACK_VALUES = ("accept", "reject", "useful", "not_useful")

_PERSONAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"']+|[\\/]Users[\\/][^\\/\s\"']+|[\\/]home[\\/][^\\/\s\"']+)",
    re.IGNORECASE,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _extract_python_code(raw: str) -> str:
    text = str(raw or "").strip()
    if "```python" in text:
        parts = text.split("```python", 1)[1]
        if "```" in parts:
            return parts.split("```", 1)[0].strip()
    if "```" in text:
        parts = text.split("```", 1)[1]
        if "```" in parts:
            return parts.split("```", 1)[0].strip()
    return text


def _verify_strict_amount_validator(code: str) -> tuple[bool, str]:
    """Independent deterministic verifier for Training Task A (strict_positive_amount)."""
    gate = local_deterministic_tools.deterministic_security_gate(code, kind="python")
    if not gate.get("ok"):
        return False, f"security_gate_failed: {gate.get('violations')}"
    ns: dict[str, Any] = {}
    try:
        exec(compile(code, "<task_a>", "exec"), ns)
    except Exception as exc:
        return False, f"exec_error: {type(exc).__name__}: {exc}"
    fn = ns.get("strict_positive_amount")
    if not callable(fn):
        return False, "missing function strict_positive_amount"
    try:
        if fn(10) != 10.0 or fn(2.5) != 2.5:
            return False, "wrong value on valid numeric input"
    except Exception as exc:
        return False, f"raised on valid numeric input: {exc}"
    for bad in (True, False, 0, -5, "10", None, float("nan"), float("inf")):
        try:
            fn(bad)
            return False, f"accepted invalid input {bad!r} (must raise ValueError or TypeError)"
        except (ValueError, TypeError):
            pass
        except Exception as exc:
            return False, f"unexpected exception on {bad!r}: {type(exc).__name__}"
    return True, "ok"


def _verify_distinct_transfer_task(code: str) -> tuple[bool, str]:
    """Independent deterministic verifier for Distinct Transfer Task B (validate_order_quantity)."""
    gate = local_deterministic_tools.deterministic_security_gate(code, kind="python")
    if not gate.get("ok"):
        return False, f"security_gate_failed: {gate.get('violations')}"
    ns: dict[str, Any] = {}
    try:
        exec(compile(code, "<task_b>", "exec"), ns)
    except Exception as exc:
        return False, f"exec_error: {type(exc).__name__}: {exc}"
    fn = ns.get("validate_order_quantity")
    if not callable(fn):
        return False, "missing function validate_order_quantity"
    try:
        if fn(1) != 1 or fn(25) != 25:
            return False, "wrong value on valid positive int quantity"
    except Exception as exc:
        return False, f"raised on valid quantity: {exc}"
    for bad in (True, False, 0, -3, 2.5, "5", None):
        try:
            fn(bad)
            return False, f"accepted invalid quantity {bad!r} (must reject bool/non-int/non-positive)"
        except (ValueError, TypeError):
            pass
        except Exception as exc:
            return False, f"unexpected exception on {bad!r}: {type(exc).__name__}"
    return True, "ok"


# Training curriculum strictly separated from held-out V3/V4 benchmark IDs.
TRAINING_TASK_A = {
    "id": "cl-train-bool-amount-01",
    "role": "tel99-quality",
    "function": "strict_positive_amount",
    "path": "training/validation_amount.py",
    "objective": (
        "Write a pure Python function `strict_positive_amount(value)` that returns `float(value)` "
        "for finite strictly positive int/float values, and raises `TypeError` or `ValueError` "
        "for booleans (`True`/`False`), zero, negative numbers, NaN, Inf, strings, or None."
    ),
    "lesson_title": "Reject Python bool explicitly before int/float checks in numeric validators",
    "lesson_body": (
        "In Python `isinstance(True, int)` is True. Always check `if isinstance(value, bool): "
        "raise TypeError('bool not allowed')` BEFORE `isinstance(value, (int, float))`, and reject "
        "NaN/Inf via `math.isfinite` and non-positive values (`<= 0`)."
    ),
    "tags": ("validation", "bool-trap", "numeric", "strict_positive_amount", "validate_order_quantity"),
    "verifier": _verify_strict_amount_validator,
}

TRANSFER_TASK_B = {
    "id": "cl-transfer-order-qty-02",
    "role": "tel99-development",
    "function": "validate_order_quantity",
    "path": "training/order_quantity.py",
    "objective": (
        "Write a pure Python function `validate_order_quantity(qty)` that returns `int` `qty` "
        "only for strictly positive integers (`>= 1`), rejecting booleans (`True`/`False`), "
        "floats, strings, None, zero, and negative values with `TypeError` or `ValueError`."
    ),
    "verifier": _verify_distinct_transfer_task,
}


def _sanitize_text(text: str) -> str:
    cleaned = _PERSONAL_PATH_RE.sub("<LOCAL_HOST>", str(text or ""))
    return str(metacognition.scrub_secrets(cleaned))


class ContinuousLearningWorker:
    """User-prioritized continuous learning (G5/G6) & bounded proactive council (G8)."""

    def __init__(self, state_root: Path | str, *, min_free_ram_mib: int = DEFAULT_MIN_FREE_RAM_MIB) -> None:
        self.state_root = Path(state_root).resolve()
        self.learning_dir = self.state_root / "learning"
        self.memory_root = self.learning_dir / "memory"
        self.briefs_dir = self.learning_dir / "briefs"
        self.pause_flag = self.learning_dir / "learning_pause.request"
        self.stop_flag = self.learning_dir / "learning_stop.request"
        self.state_path = self.learning_dir / "continuous_learning_state.json"
        self.proactive_state_path = self.learning_dir / "proactive_briefs_state.json"
        self.preferences_path = self.learning_dir / "owner_preferences.json"
        self.min_free_ram_mib = int(min_free_ram_mib)
        self.learning_dir.mkdir(parents=True, exist_ok=True)
        self.memory_root.mkdir(parents=True, exist_ok=True)
        self.briefs_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # State & Controls (G5 + G8)
    # ------------------------------------------------------------------
    def load_state(self) -> dict[str, Any]:
        if self.state_path.is_file():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {
            "schema_version": 1,
            "worker_configured": True,
            "status": "IDLE",
            "paused": self.pause_flag.exists(),
            "lora_training_enabled": False,
            "exercises_run": 0,
            "verified_lessons_promoted": 0,
            "g6_chain_proven": False,
            "last_cycle_at": None,
            "last_reason": None,
            "history": [],
        }

    def save_state(self, state: dict[str, Any]) -> None:
        state["worker_configured"] = True
        state["paused"] = self.pause_flag.exists()
        state["lora_training_enabled"] = False
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self.state_path)

    def load_proactive_state(self) -> dict[str, Any]:
        if self.proactive_state_path.is_file():
            try:
                data = json.loads(self.proactive_state_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {
            "schema_version": 1,
            "enabled": True,
            "paused": self.pause_flag.exists(),
            "schedule": {
                "cadence": "daily_night_if_awake",
                "default_window_local": "02:00-06:00",
                "max_initiatives_per_day": 1,
                "forced_pc_wake": False,
                "paid_calls_allowed": False,
                "local_concurrency": 1,
            },
            "authorized_domains": [
                "projects_diagnostics",
                "quality_and_security_anticipation",
                "quota_and_resource_optimization",
                "product_and_business_opportunities",
            ],
            "daily_executed_keys": [],
            "delivered_fingerprints": [],
            "latest_brief": None,
            "briefs_history": [],
        }

    def save_proactive_state(self, data: dict[str, Any]) -> None:
        data["paused"] = self.pause_flag.exists()
        tmp = self.proactive_state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self.proactive_state_path)

    def load_preferences(self) -> dict[str, Any]:
        if self.preferences_path.is_file():
            try:
                data = json.loads(self.preferences_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {
            "schema_version": 1,
            "domain_weights": {},
            "feedback_log": [],
        }

    def save_preferences(self, prefs: dict[str, Any]) -> None:
        tmp = self.preferences_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(prefs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self.preferences_path)

    def pause(self) -> dict[str, Any]:
        self.pause_flag.write_text(_now_iso() + "\n", encoding="utf-8")
        st = self.load_state()
        st["status"] = "PAUSED"
        st["paused"] = True
        st["last_reason"] = "paused_by_owner"
        self.save_state(st)
        ps = self.load_proactive_state()
        ps["paused"] = True
        self.save_proactive_state(ps)
        return st

    def resume(self) -> dict[str, Any]:
        if self.pause_flag.exists():
            self.pause_flag.unlink()
        if self.stop_flag.exists():
            self.stop_flag.unlink()
        st = self.load_state()
        st["status"] = "IDLE"
        st["paused"] = False
        st["last_reason"] = "resumed_by_owner"
        self.save_state(st)
        ps = self.load_proactive_state()
        ps["paused"] = False
        self.save_proactive_state(ps)
        return st

    def set_proactive_enabled(self, enabled: bool) -> dict[str, Any]:
        ps = self.load_proactive_state()
        ps["enabled"] = bool(enabled)
        self.save_proactive_state(ps)
        return ps

    def record_brief_feedback(self, brief_id: str, feedback: str, *, note: str = "") -> dict[str, Any]:
        """Record owner feedback (accept/reject/useful/not_useful) to tune future initiative scoring."""
        if feedback not in FEEDBACK_VALUES:
            raise ValueError(f"Unsupported feedback {feedback!r}; expected one of {FEEDBACK_VALUES}")
        ps = self.load_proactive_state()
        prefs = self.load_preferences()
        domain = "general"
        matched = False
        for item in ps.get("briefs_history") or []:
            if isinstance(item, dict) and item.get("brief_id") == brief_id:
                item["owner_feedback"] = feedback
                item["owner_feedback_at"] = _now_iso()
                domain = str(item.get("domain") or "general")
                matched = True
                break
        latest = ps.get("latest_brief")
        if isinstance(latest, dict) and latest.get("brief_id") == brief_id:
            latest["owner_feedback"] = feedback
            latest["owner_feedback_at"] = _now_iso()
            domain = str(latest.get("domain") or domain)
            matched = True
        if not matched:
            raise KeyError(f"Unknown brief_id: {brief_id}")

        weights = dict(prefs.get("domain_weights") or {})
        delta = 0.15 if feedback in ("accept", "useful") else -0.15
        weights[domain] = round(max(0.2, min(2.0, float(weights.get(domain, 1.0)) + delta)), 3)
        prefs["domain_weights"] = weights
        log = list(prefs.get("feedback_log") or [])
        log.append({
            "at": _now_iso(),
            "brief_id": brief_id,
            "domain": domain,
            "feedback": feedback,
            "note": _sanitize_text(note)[:200],
        })
        prefs["feedback_log"] = log[-50:]
        self.save_preferences(prefs)
        self.save_proactive_state(ps)

        # Record feedback preference in collective MemoryStore (procedural/fact, never model weights)
        store = MemoryStore(self.memory_root)
        fid = f"pref-{brief_id}-{feedback}"
        if store.get(COMMON_PROJECT, fid) is None:
            store.record(
                Entry(
                    id=fid,
                    project=COMMON_PROJECT,
                    kind="fact",
                    title=f"Owner feedback ({feedback}) on proactive initiative in {domain}",
                    body=f"Brief {brief_id} marked '{feedback}' by owner. Domain weight updated to {weights[domain]}.",
                    tags=("proactive", "preference", domain, feedback),
                    source=f"proactive-feedback/{brief_id}",
                    author="tel99-coordination",
                    verified=True,
                    verified_by="owner-explicit-feedback",
                    confidence=0.9,
                ),
                actor="continuous-learning-worker",
            )
        return {"ok": True, "brief_id": brief_id, "feedback": feedback, "domain_weight": weights[domain]}

    def can_run_background(self, *, probe_engines: bool = True) -> tuple[bool, str]:
        if self.stop_flag.exists():
            return False, "stopped_by_owner"
        if self.pause_flag.exists():
            return False, "paused_by_owner"
        if ide_coordination.owner_interactive_priority_active(self.state_root):
            return False, "yielded_to_owner_priority"
        if probe_engines:
            engines = ide_coordination.probe_local_engines()
            if int(engines.get("active_inference_leases_count") or 0) > 0:
                return False, "yielded_to_active_inference_lease"
            avail = engines.get("available_memory_mib")
            ollama_loaded = bool(engines.get("ollama_models_loaded"))
            threshold = RESIDENT_MIN_FREE_RAM_MIB if ollama_loaded else self.min_free_ram_mib
            if isinstance(avail, (int, float)) and avail < threshold:
                return False, f"ram_guard_low_memory_{avail:.0f}mib_lt_{threshold}mib"
        return True, "ok"

    # ------------------------------------------------------------------
    # G6 Verified Learning Chain
    # ------------------------------------------------------------------
    def run_verified_g6_chain(
        self,
        *,
        model_call: Callable[[str, str], str],
        probe_engines: bool = True,
    ) -> dict[str, Any]:
        """Execute and verify the full G6 learning chain:
        Real error -> verified fix -> persisted lesson -> restart/reload -> distinct new task -> measured result.
        """
        st = self.load_state()
        allowed, reason = self.can_run_background(probe_engines=probe_engines)
        if not allowed:
            st["status"] = "YIELDED_TO_OWNER" if "owner" in reason else "DEFERRED"
            st["last_reason"] = reason
            self.save_state(st)
            return {"ok": False, "status": st["status"], "reason": reason}

        st["status"] = "RUNNING"
        self.save_state(st)

        prompt_a1 = (
            f"Objective: {TRAINING_TASK_A['objective']}\n"
            "Return ONLY valid Python code defining the requested function."
        )
        raw_a1 = model_call(TRAINING_TASK_A["role"], prompt_a1)
        code_a1 = _extract_python_code(raw_a1)
        ok_a1, err_a1 = TRAINING_TASK_A["verifier"](code_a1)

        repaired_a = False
        code_a_final = code_a1
        ok_a_final = ok_a1
        err_a_final = err_a1
        if not ok_a1:
            prompt_a2 = (
                f"Objective: {TRAINING_TASK_A['objective']}\n"
                f"Previous attempt failed independent verification with error: {err_a1}\n"
                "Fix this exact bug and return ONLY valid Python code."
            )
            raw_a2 = model_call(TRAINING_TASK_A["role"], prompt_a2)
            code_a_final = _extract_python_code(raw_a2)
            ok_a_final, err_a_final = TRAINING_TASK_A["verifier"](code_a_final)
            repaired_a = ok_a_final

        if not ok_a_final:
            st["status"] = "IDLE"
            st["exercises_run"] = int(st.get("exercises_run", 0)) + 1
            st["last_cycle_at"] = _now_iso()
            st["last_reason"] = f"task_a_unverified:{err_a_final}"
            self.save_state(st)
            return {
                "ok": False,
                "status": "TASK_A_FAILED",
                "initial_error": err_a1,
                "final_error": err_a_final,
                "lesson_promoted": False,
            }

        store = MemoryStore(self.memory_root)
        lesson_id = f"fix-{TRAINING_TASK_A['id']}"
        lesson_entry = Entry(
            id=lesson_id,
            project=COMMON_PROJECT,
            kind="fix",
            title=TRAINING_TASK_A["lesson_title"],
            body=TRAINING_TASK_A["lesson_body"],
            tags=TRAINING_TASK_A["tags"],
            source=f"continuous-learning/{TRAINING_TASK_A['id']}",
            author=TRAINING_TASK_A["role"],
            verified=True,
            verified_by="tel99-continuous-learning-deterministic-verifier-v1",
            confidence=0.95,
        )
        if store.get(COMMON_PROJECT, lesson_id) is None:
            store.record(lesson_entry, actor="continuous-learning-worker")
            promoted_new = True
        else:
            promoted_new = False

        reloaded_store = MemoryStore(self.memory_root)
        persisted_check = reloaded_store.get(COMMON_PROJECT, lesson_id)
        retrieved = learning_loop.retrieve_scoped_lessons(
            self.memory_root,
            TRAINING_PROJECT,
            {
                "path": TRANSFER_TASK_B["path"],
                "function": TRANSFER_TASK_B["function"],
                "objective": TRANSFER_TASK_B["objective"],
            },
            role=TRANSFER_TASK_B["role"],
            verified_only=True,
            limit=3,
        )
        lessons_found = retrieved.get("lessons") or []
        lesson_recalled_after_reload = bool(persisted_check and persisted_check.verified and lessons_found)

        lesson_block = "\n".join(f"- {item}" for item in lessons_found)
        prompt_b = (
            f"Verified lessons recalled from TEL99 collective memory:\n{lesson_block}\n\n"
            f"New distinct task objective: {TRANSFER_TASK_B['objective']}\n"
            "Apply the recalled lessons and return ONLY valid Python code."
        )
        raw_b = model_call(TRANSFER_TASK_B["role"], prompt_b)
        code_b = _extract_python_code(raw_b)
        ok_b, err_b = TRANSFER_TASK_B["verifier"](code_b)

        chain_proven = bool((not ok_a1) and repaired_a and lesson_recalled_after_reload and ok_b)
        transfer_verified = bool(ok_a_final and lesson_recalled_after_reload and ok_b)

        cycle_record = {
            "at": _now_iso(),
            "task_a_id": TRAINING_TASK_A["id"],
            "task_a_initial_passed": ok_a1,
            "task_a_initial_error": None if ok_a1 else err_a1,
            "task_a_repaired": repaired_a,
            "task_a_final_passed": ok_a_final,
            "lesson_id": lesson_id,
            "lesson_recalled_after_reload": lesson_recalled_after_reload,
            "task_b_id": TRANSFER_TASK_B["id"],
            "task_b_passed": ok_b,
            "task_b_error": None if ok_b else err_b,
            "g6_chain_proven": chain_proven,
            "transfer_verified": transfer_verified,
        }

        st["status"] = "IDLE"
        st["exercises_run"] = int(st.get("exercises_run", 0)) + 2
        if promoted_new:
            st["verified_lessons_promoted"] = int(st.get("verified_lessons_promoted", 0)) + 1
        st["g6_chain_proven"] = bool(st.get("g6_chain_proven") or chain_proven)
        st["transfer_verified"] = bool(st.get("transfer_verified") or transfer_verified)
        st["last_cycle_at"] = cycle_record["at"]
        st["last_reason"] = "g6_chain_proven" if chain_proven else ("transfer_verified" if transfer_verified else "task_b_failed")
        hist = list(st.get("history") or [])
        hist.append(cycle_record)
        st["history"] = hist[-20:]
        self.save_state(st)
        return {"ok": transfer_verified, **cycle_record}

    # ------------------------------------------------------------------
    # G8 Bounded Proactive Cycle (Observe -> Curiosity -> Council -> Deliverable -> Morning Brief)
    # ------------------------------------------------------------------
    def _observe_authorized_signals(self, authorized_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract bounded candidate initiatives ONLY from explicitly authorized signals."""
        candidates: list[dict[str, Any]] = []
        now = _now_iso()

        # 1. Unfinished / failing authorized projects
        for proj in authorized_snapshot.get("projects") or []:
            if not isinstance(proj, dict):
                continue
            name = str(proj.get("name") or "")
            status = str(proj.get("status") or "")
            acc = int(proj.get("missions_accepted") or 0)
            tot = int(proj.get("missions_total") or 0)
            if name and status not in {"COMPLETED", "ACCEPTED", "DELIVERED"} and tot > acc:
                fp = hashlib.sha256(f"proj:{name}:{acc}/{tot}".encode("utf-8")).hexdigest()[:16]
                candidates.append({
                    "id": f"init-proj-{fp[:8]}",
                    "fingerprint": fp,
                    "domain": "projects_diagnostics",
                    "title": f"Diagnostic proactif & plan de déblocage pour {name} ({acc}/{tot})",
                    "observation": f"Projet autorisé {name} en statut {status} ({acc}/{tot} missions acceptées) au {now}.",
                    "curiosity_question": f"Quelle mission restante bloque la livraison complète de {name} et quel est le correctif minimal vérifiable ?",
                    "hypothesis": "Une seule mission défectueuse ou en attente empêche la validation E2E complète.",
                    "prediction": "Réparer uniquement la mission en échec sans reconstruire les livrables acceptés débloquera le projet.",
                    "counterfactual": "Sans diagnostic ciblé, un relancement aveugle risque d'écraser ou retarder les livrables déjà validés.",
                    "invalidation_signal": "Si toutes les missions restantes échouent pour cause d'infrastructure (RAM/Docker) plutôt que de code.",
                    "roles": ["tel99-coordination", "tel99-quality", "tel99-development"],
                    "impact": 0.9,
                    "urgency": 0.85,
                    "confidence": 0.85,
                    "cost": 0.25,
                    "reversible": True,
                })

        # 2. Certification / weakness anticipation (e.g. V4 quota recovery or Endurance failure)
        cert = authorized_snapshot.get("certification") or {}
        endurance = cert.get("endurance_latest") or {}
        if isinstance(endurance, dict) and endurance.get("status") in {"FAILED", "NOT_RUN"}:
            fp = hashlib.sha256(f"endurance:{endurance.get('status')}".encode("utf-8")).hexdigest()[:16]
            candidates.append({
                "id": f"init-endur-{fp[:8]}",
                "fingerprint": fp,
                "domain": "quality_and_security_anticipation",
                "title": "Plan préventif RAM & reprise propre pour la certification endurance 60 min",
                "observation": f"Dernière endurance enregistrée en statut {endurance.get('status')} au {now}.",
                "curiosity_question": "Comment garantir >= 2500 MiB de RAM libre avant et pendant 60 min d'autonomie sans bloquer le propriétaire ?",
                "hypothesis": "Le déchargement préalable d'Ollama et l'exécution séquentielle hors concurrence suppriment le déclenchement du garde-fou RAM.",
                "prediction": "Un run endurance lancé avec > 5000 MiB libres et 0 autre campagne active terminera 60 min sans blocage RAM.",
                "counterfactual": "Lancer l'endurance alors qu'un modèle est chargé avec < 1500 MiB libres reproduira l'arrêt précoce.",
                "invalidation_signal": "Si la RAM disponible chute sous 2500 MiB malgré Ollama déchargé (autre processus Windows consommateur).",
                "roles": ["tel99-coordination", "tel99-monitoring", "tel99-quality"],
                "impact": 0.82,
                "urgency": 0.75,
                "confidence": 0.8,
                "cost": 0.2,
                "reversible": True,
            })

        # 3. Groq quota / latency optimization opportunity
        groq = authorized_snapshot.get("groq_quotas") or {}
        if isinstance(groq, dict) and groq.get("legacy_unattributed") is True:
            fp = hashlib.sha256(b"groq:legacy_unattributed").hexdigest()[:16]
            candidates.append({
                "id": f"init-quota-{fp[:8]}",
                "fingerprint": fp,
                "domain": "quota_and_resource_optimization",
                "title": "Préparation du basculement propre sur quotas Groq par modèle après 00:00 UTC",
                "observation": f"Le ledger Groq signale legacy_unattributed=true au {now}.",
                "curiosity_question": "Quels modèles gratuits Groq sont immédiatement disponibles pour préserver la réserve interactive de 120k TPD ?",
                "hypothesis": "Le rollover 00:00 UTC réinitialise proprement les 3 compteurs par modèle (600k théoriques, 120k réserve, 480k arrière-plan).",
                "prediction": "La reprise ciblée V4 (34 tâches) et les projets hybrides fonctionneront sans épuiser la réserve propriétaire.",
                "counterfactual": "Relancer le batch V4 avant le rollover consommerait inutilement des retries en échec quota.",
                "invalidation_signal": "Si Groq applique une limite projet inférieure aux 200k TPD par modèle (HTTP 429 anticipé).",
                "roles": ["tel99-coordination", "tel99-cloud", "tel99-evaluation"],
                "impact": 0.78,
                "urgency": 0.7,
                "confidence": 0.82,
                "cost": 0.15,
                "reversible": True,
            })

        return candidates

    def run_proactive_cycle(
        self,
        *,
        authorized_snapshot: dict[str, Any],
        trigger: str = "scheduled_idle",
        daily_key: str | None = None,
        model_call: Callable[[str, str], str] | None = None,
        probe_engines: bool = True,
    ) -> dict[str, Any]:
        """Run ONE bounded proactive cycle (G8): max 1 substantial initiative + Morning Brief.

        - Deduplicates per day (`daily_key`) and per initiative fingerprint.
        - Yields immediately if paused, disabled, owner priority active, or RAM low.
        - Honestly returns `NO_USEFUL_TASK` when no useful non-duplicate initiative exists.
        - Never creates human approvals or mutates production.
        """
        t0 = time.monotonic()
        day = daily_key or _today_utc()
        ps = self.load_proactive_state()

        if not ps.get("enabled", True):
            return {"ok": False, "status": "DISABLED", "reason": "proactive_disabled_by_owner"}

        allowed, reason = self.can_run_background(probe_engines=probe_engines)
        if not allowed:
            return {"ok": False, "status": "YIELDED_TO_OWNER" if "owner" in reason else "DEFERRED", "reason": reason}

        if day in (ps.get("daily_executed_keys") or []):
            return {
                "ok": True,
                "status": "NO_USEFUL_TASK",
                "reason": f"daily_dedup_already_executed:{day}",
                "trigger": trigger,
                "daily_key": day,
                "deduplicated": True,
            }

        # Observe strictly authorized signals & deduplicate against already-delivered fingerprints
        delivered_fps = set(ps.get("delivered_fingerprints") or [])
        prefs = self.load_preferences()
        weights = prefs.get("domain_weights") or {}
        raw_candidates = self._observe_authorized_signals(authorized_snapshot)
        candidates = [c for c in raw_candidates if c["fingerprint"] not in delivered_fps]

        if not candidates:
            brief_id = f"brief-{day}-none"
            brief = {
                "brief_id": brief_id,
                "daily_key": day,
                "generated_at": _now_iso(),
                "trigger": trigger,
                "status": "NO_USEFUL_TASK",
                "domain": "none",
                "title": "Aucune initiative utile supplémentaire requise aujourd'hui",
                "why_useful": "Évite de créer du travail artificiel : tous les signaux autorisés sont déjà couverts ou dédupliqués.",
                "deliverable_rel_path": None,
                "evidence": ["Observation lecture seule effectuée sur les projets et rapports autorisés."],
                "limits": ["Accès web externe non inventé ; périmètre limité aux sources locales autorisées."],
                "risks": [],
                "next_action": "Aucune action requise.",
                "duration_seconds": round(time.monotonic() - t0, 2),
                "requires_human_approval": False,
                "owner_feedback": None,
            }
            ps["daily_executed_keys"] = (list(ps.get("daily_executed_keys") or []) + [day])[-60:]
            ps["latest_brief"] = brief
            ps["briefs_history"] = (list(ps.get("briefs_history") or []) + [brief])[-30:]
            self.save_proactive_state(ps)
            return {"ok": True, **brief}

        # Bounded Adaptive Council reusing metacognition.explore_approaches (<= 3 approaches)
        def _score_candidate(cand: dict[str, Any]) -> dict[str, Any]:
            w = float(weights.get(cand["domain"], 1.0))
            score = (
                (0.35 * cand["impact"] + 0.25 * cand["urgency"] + 0.25 * cand["confidence"] + 0.15 * (1.0 - cand["cost"]))
                * w
            )
            return {
                "ok": bool(cand.get("reversible", True) and score >= 0.45),
                "score": min(1.0, round(score, 4)),
                "evidence": f"impact={cand['impact']} urgency={cand['urgency']} weight={w}",
            }

        exploration = metacognition.explore_approaches(
            objective="Sélectionner l'initiative proactive la plus utile pour le propriétaire",
            approaches=[{"id": c["id"], "strategy": c["title"], **c} for c in candidates[:3]],
            evaluator=_score_candidate,
            max_branches=3,
            early_stop_score=0.99,
        )
        selected_branch = exploration.get("selected")
        if not selected_branch:
            return {"ok": True, "status": "NO_USEFUL_TASK", "reason": "no_candidate_passed_threshold", "trigger": trigger}

        chosen = next(c for c in candidates if c["id"] == selected_branch["id"])

        # Adaptive council (3 targeted roles, NOT 12 agents): analyst, challenger, specialist -> coordinator synthesis
        council_notes: dict[str, str] = {}
        if model_call is not None:
            council_prompt = (
                f"Contexte autorisé (lecture seule) : {chosen['observation']}\n"
                f"Question de curiosité : {chosen['curiosity_question']}\n"
                f"Hypothèse : {chosen['hypothesis']}\n"
                f"Contre-factuel : {chosen['counterfactual']}\n"
                "En 4 puces concises en français : (1) diagnostic factuel, (2) objection / risque principal, "
                "(3) action réversible préparée hors production, (4) critère d'invalidation."
            )
            synthesis = _sanitize_text(model_call(chosen["roles"][0], council_prompt))
            council_notes["synthesis"] = synthesis[:1200]
        else:
            council_notes["synthesis"] = (
                f"- Observation vérifiée : {chosen['observation']}\n"
                f"- Contre-argument (contradicteur) : {chosen['invalidation_signal']}\n"
                f"- Prédiction réversible : {chosen['prediction']}\n"
                f"- Contre-factuel : {chosen['counterfactual']}"
            )

        # Write real consultable Markdown deliverable in sandboxed briefs_dir (NEVER production)
        brief_id = f"brief-{day}-{chosen['id']}"
        deliverable_name = f"{brief_id}.md"
        deliverable_path = self.briefs_dir / deliverable_name
        deliverable_md = (
            f"# Brief Proactif TEL99 — {chosen['title']}\n\n"
            f"- **Date (UTC)** : {_now_iso()}\n"
            f"- **Déclencheur** : `{trigger}` (sans sollicitation manuelle)\n"
            f"- **Statut** : `PROPOSAL` (aucune écriture production, aucune approbation auto-générée)\n"
            f"- **Conseil adaptatif sollicité** : {', '.join(chosen['roles'])} ({len(chosen['roles'])} rôles ciblés)\n\n"
            f"## 1. Observation vs Hypothèse vs Prédiction\n"
            f"- **Observation** : {chosen['observation']}\n"
            f"- **Question de curiosité** : {chosen['curiosity_question']}\n"
            f"- **Hypothèse** : {chosen['hypothesis']}\n"
            f"- **Prédiction** : {chosen['prediction']}\n"
            f"- **Contre-factuel** : {chosen['counterfactual']}\n"
            f"- **Signal d'invalidation** : {chosen['invalidation_signal']}\n\n"
            f"## 2. Synthèse du Conseil Adaptatif (exploration {exploration['branches_evaluated']} approche(s))\n"
            f"{council_notes['synthesis']}\n\n"
            f"## 3. Garde-fous & Limites\n"
            f"- Aucune modification de production, aucune fusion `main`, aucune dépense, aucune approbation fabriquée.\n"
            f"- Accès web externe non simulé ; analyse basée exclusivement sur les rapports locaux autorisés.\n"
        )
        deliverable_md = _sanitize_text(deliverable_md)
        # Independent deterministic verification of deliverable before saving
        leak = local_deterministic_tools.detect_secret_leak(deliverable_md)
        if not leak.get("safe", False):
            raise RuntimeError("Refusing to write proactive brief: secret leak detected")
        deliverable_path.write_text(deliverable_md, encoding="utf-8")

        duration_s = round(time.monotonic() - t0, 2)
        brief = {
            "brief_id": brief_id,
            "daily_key": day,
            "generated_at": _now_iso(),
            "trigger": trigger,
            "status": "PROPOSAL",
            "domain": chosen["domain"],
            "title": chosen["title"],
            "why_useful": chosen["prediction"],
            "council_roles": chosen["roles"],
            "branches_evaluated": exploration["branches_evaluated"],
            "deliverable_rel_path": f"learning/briefs/{deliverable_name}",
            "deliverable_bytes": len(deliverable_md.encode("utf-8")),
            "evidence": [
                chosen["observation"],
                f"Exploration bornée ({exploration['branches_evaluated']} branche(s), score={selected_branch['score']}).",
                f"Livrable vérifié sans fuite de secret ({len(deliverable_md)} chars).",
            ],
            "limits": [
                "Aucune action de production exécutée sans mandat explicite du propriétaire.",
                "Pas de veille web externe inventée.",
            ],
            "risks": [chosen["invalidation_signal"]],
            "next_action": "Consulter le brief dans Command Center et cliquer Accepter / Utile ou Refuser.",
            "duration_seconds": duration_s,
            "requires_human_approval": True,
            "owner_feedback": None,
        }

        ps["daily_executed_keys"] = (list(ps.get("daily_executed_keys") or []) + [day])[-60:]
        ps["delivered_fingerprints"] = (list(ps.get("delivered_fingerprints") or []) + [chosen["fingerprint"]])[-200:]
        ps["latest_brief"] = brief
        ps["briefs_history"] = (list(ps.get("briefs_history") or []) + [brief])[-30:]
        self.save_proactive_state(ps)

        # Persist verified proactive initiative trace in collective MemoryStore
        store = MemoryStore(self.memory_root)
        mem_id = f"proactive-{brief_id}"
        if store.get(COMMON_PROJECT, mem_id) is None:
            store.record(
                Entry(
                    id=mem_id,
                    project=COMMON_PROJECT,
                    kind="procedure",
                    title=f"Proactive brief prepared: {chosen['title'][:90]}",
                    body=_sanitize_text(f"Trigger={trigger}. Deliverable={brief['deliverable_rel_path']}. {chosen['prediction']}")[:260],
                    tags=("proactive", chosen["domain"], "morning-brief"),
                    source=f"proactive-council/{brief_id}",
                    author=chosen["roles"][0],
                    verified=True,
                    verified_by="tel99-proactive-deterministic-gate-v1",
                    confidence=round(float(selected_branch["score"]), 2),
                ),
                actor="continuous-learning-worker",
            )
        return {"ok": True, **brief}


def _ollama_model_call(role: str, prompt: str, *, model: str = "gemma4:e4b-tel99-8k") -> str:
    provider = ollama_native.OllamaNativeProvider(
        model=model,
        max_tokens=768,
        timeout=180,
        keep_alive="60s",
        task_profile="module",
        priority="background",
    )
    return str(
        provider.complete(
            system=f"You are {role}, a strict Python engineer. Return only clean Python code.",
            prompt=prompt,
        )
        or ""
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TEL99 continuous learning (G5/G6) & proactive council (G8).")
    parser.add_argument("--state-root", type=Path, default=Path.home() / "Desktop" / "TEL99_LOCAL_CHAIN_STATE")
    parser.add_argument(
        "--action",
        choices=("status", "pause", "resume", "run-g6-live", "run-proactive-live", "feedback"),
        default="status",
    )
    parser.add_argument("--trigger", default="scheduled_idle")
    parser.add_argument("--brief-id", default="")
    parser.add_argument("--feedback", default="")
    parser.add_argument("--model", default="gemma4:e4b-tel99-8k")
    parser.add_argument("--no-llm", action="store_true", help="Run proactive diagnostic without LLM synthesis.")
    args = parser.parse_args(argv)

    worker = ContinuousLearningWorker(args.state_root)
    if args.action == "pause":
        print(json.dumps(worker.pause(), indent=2, ensure_ascii=False))
        return 0
    if args.action == "resume":
        print(json.dumps(worker.resume(), indent=2, ensure_ascii=False))
        return 0
    if args.action == "feedback":
        print(json.dumps(worker.record_brief_feedback(args.brief_id, args.feedback), indent=2, ensure_ascii=False))
        return 0
    if args.action == "run-g6-live":
        res = worker.run_verified_g6_chain(
            model_call=lambda role, prompt: _ollama_model_call(role, prompt, model=args.model),
            probe_engines=True,
        )
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res.get("ok") else 1
    if args.action == "run-proactive-live":
        from scripts.agents.automation import publish_status_report as psr
        snap = psr.build_status_report(probe_live=True)
        res = worker.run_proactive_cycle(
            authorized_snapshot=snap,
            trigger=args.trigger,
            model_call=None if args.no_llm else (lambda role, prompt: _ollama_model_call(role, prompt, model=args.model)),
            probe_engines=True,
        )
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res.get("ok") else 1

    print(json.dumps({
        "learning": worker.load_state(),
        "proactive": worker.load_proactive_state(),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
