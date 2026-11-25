"""Metacognition, Confidence Calibration, Exploratory Reasoning, Failure Library & Trajectory Learning.

Covers TEL99 Ultimate Agent Evolution sections §6, §7, §13, and §14:
- Bounded exploratory reasoning: compare <= 3 candidate approaches using objective checks.
- Metacognition & confidence calibration: Brier score, ECE, overconfidence penalty, abstention/escalation
  triggers (declared confidence NEVER replaces independent verification).
- Structured Failure Library: 10 failure categories persisted with provenance, attempts, confirmed cause,
  validated fix, and preventive rule.
- Secret-scrubbed Trajectory Learning: captures end-to-end verifiable traces (AgentTuning principles)
  classified into SUCCESS / FAILURE / UNCERTAIN for Skills, RAG, and future audited evaluation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, Sequence

from scripts.agents.intelligence.memory import Entry, MemoryStore

FAILURE_CATEGORIES = (
    "PROGRAMMING_ERROR",
    "PLANNING_ERROR",
    "MODEL_SELECTION_ERROR",
    "TOOL_USAGE_ERROR",
    "CONTEXT_ERROR",
    "PERMISSION_ERROR",
    "ENGINE_ERROR",
    "VERIFICATION_ERROR",
    "TRUNCATED_OUTPUT",
    "INEFFECTIVE_REPAIR",
)

SECRET_REDACT_PATTERNS = (
    re.compile(
        r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9\-_]{16,}|"
        r"gsk_[A-Za-z0-9]{16,}|AIza[0-9A-Za-z\-_]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
    ),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?([^\s'\",;]{6,})"),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def scrub_secrets(value: Any) -> Any:
    """Recursively redact token/key/password patterns before writing trajectories or failure logs."""
    if isinstance(value, str):
        out = value
        out = SECRET_REDACT_PATTERNS[0].sub("[REDACTED_SECRET]", out)
        out = SECRET_REDACT_PATTERNS[1].sub(r"\1=[REDACTED]", out)
        return out
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for k, v in value.items():
            if any(s in str(k).lower() for s in ("secret", "token", "password", "api_key", "apikey")):
                clean[str(k)] = "[REDACTED]"
            else:
                clean[str(k)] = scrub_secrets(v)
        return clean
    if isinstance(value, list):
        return [scrub_secrets(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# 1. Bounded Exploratory Reasoning (§6)
# ---------------------------------------------------------------------------
def explore_approaches(
    objective: str,
    approaches: Sequence[dict[str, Any]],
    evaluator: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    max_branches: int = 3,
    early_stop_score: float = 0.95,
) -> dict[str, Any]:
    """Compare up to `max_branches` approaches via objective checks and abandon weak branches early."""
    if not 1 <= max_branches <= 5:
        raise ValueError("max_branches must be 1..5")
    evaluated: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None

    for idx, app in enumerate(list(approaches)[:max_branches], 1):
        res = evaluator(app)
        ok = bool(res.get("ok"))
        score = float(res.get("score", 1.0 if ok else 0.0))
        record = {
            "branch": idx,
            "id": str(app.get("id") or f"approach-{idx}"),
            "strategy": str(app.get("strategy") or ""),
            "ok": ok,
            "score": round(score, 4),
            "evidence": str(res.get("evidence") or "")[:300],
            "abandoned": not ok,
        }
        evaluated.append(record)
        if best is None or (record["ok"], record["score"]) > (best["ok"], best["score"]):
            best = record
        if ok and score >= early_stop_score:
            break

    return {
        "objective": objective[:240],
        "branches_evaluated": len(evaluated),
        "max_branches": max_branches,
        "selected": best if (best and best["ok"]) else None,
        "decision": "SELECTED" if (best and best["ok"]) else "ABSTAIN_OR_ESCALATE",
        "branches": evaluated,
    }


# ---------------------------------------------------------------------------
# 2. Metacognition & Confidence Calibration (§7)
# ---------------------------------------------------------------------------
def estimate_task_confidence(
    *,
    estimated_lines: int,
    missing_info_items: Sequence[str] = (),
    prior_role_success_rate: float = 0.7,
    calibration_penalty: float = 0.0,
    has_verified_memory: bool = False,
) -> dict[str, Any]:
    """Estimate pre-execution confidence and recommend action (execute, verify_strict, delegate, switch_model, abstain)."""
    base = max(0.05, min(0.95, float(prior_role_success_rate)))
    if estimated_lines > 120:
        base -= 0.25
    elif estimated_lines > 75:
        base -= 0.10
    if missing_info_items:
        base -= min(0.45, 0.15 * len(missing_info_items))
    if has_verified_memory:
        base += 0.08
    calibrated = max(0.05, min(0.95, round(base - max(0.0, float(calibration_penalty)), 4)))

    if missing_info_items and len(missing_info_items) >= 2:
        action = "abstain_request_context"
    elif calibrated < 0.35:
        action = "decompose_or_delegate"
    elif calibrated < 0.60:
        action = "switch_model_or_verify_strict"
    else:
        action = "execute_and_verify"

    difficulty = "hard" if (estimated_lines > 100 or calibrated < 0.45) else ("medium" if estimated_lines > 45 else "easy")
    return {
        "raw_confidence": round(max(0.05, min(0.95, base)), 4),
        "calibrated_confidence": calibrated,
        "difficulty": difficulty,
        "missing_info": list(missing_info_items),
        "recommended_action": action,
        "requires_independent_verification": True,  # Invariant: confidence NEVER replaces independent tests
    }


def compute_calibration_metrics(observations: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Measure Brier score, Expected Calibration Error (ECE), overconfidence rate & recalibration penalty."""
    valid = [
        o for o in observations
        if isinstance(o, dict) and isinstance(o.get("confidence"), (int, float)) and isinstance(o.get("success"), bool)
    ]
    n = len(valid)
    if n == 0:
        return {
            "count": 0,
            "brier_score": None,
            "ece": None,
            "mean_confidence": None,
            "actual_accuracy": None,
            "overconfidence_gap": 0.0,
            "recommended_penalty": 0.0,
            "recalibration_required": False,
        }

    brier = sum((float(o["confidence"]) - (1.0 if o["success"] else 0.0)) ** 2 for o in valid) / n
    mean_conf = sum(float(o["confidence"]) for o in valid) / n
    acc = sum(1.0 for o in valid if o["success"]) / n
    overconf_gap = round(mean_conf - acc, 4)

    # 5-bin ECE
    ece = 0.0
    for b in range(5):
        lo, hi = b * 0.2, (b + 1) * 0.2
        bucket = [o for o in valid if (lo <= float(o["confidence"]) < hi) or (b == 4 and float(o["confidence"]) == 1.0)]
        if not bucket:
            continue
        b_conf = sum(float(o["confidence"]) for o in bucket) / len(bucket)
        b_acc = sum(1.0 for o in bucket if o["success"]) / len(bucket)
        ece += (len(bucket) / n) * abs(b_conf - b_acc)

    penalty = round(max(0.0, min(0.35, overconf_gap * 0.75)), 4) if overconf_gap > 0.08 else 0.0
    return {
        "count": n,
        "brier_score": round(brier, 4),
        "ece": round(ece, 4),
        "mean_confidence": round(mean_conf, 4),
        "actual_accuracy": round(acc, 4),
        "overconfidence_gap": overconf_gap,
        "recommended_penalty": penalty,
        "recalibration_required": bool(overconf_gap > 0.12 or ece > 0.15),
    }


# ---------------------------------------------------------------------------
# 3. Structured Failure Library (§13)
# ---------------------------------------------------------------------------
class FailureLibrary:
    """Structured, queryable library of verified failures & preventive fixes (project-isolated)."""

    def __init__(self, root: Path | str, *, memory_root: Path | str | None = None) -> None:
        self.root = Path(root)
        self.path = self.root / "failure_library.json"
        self.memory_root = Path(memory_root) if memory_root is not None else None

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _save(self, rows: list[dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def record_failure(
        self,
        *,
        project: str,
        mission_id: str,
        category: str,
        context_summary: str,
        cause: str,
        cause_confirmed: bool,
        evidence: str,
        attempts: Sequence[dict[str, Any]] = (),
        validated_solution: str = "",
        preventive_measure: str = "",
        model: str = "",
        role: str = "tel99-dev",
    ) -> dict[str, Any]:
        if category not in FAILURE_CATEGORIES:
            raise ValueError(f"unknown failure category: {category!r}")
        rows = self._load()
        fid = f"fail-{hashlib.sha256(f'{project}:{mission_id}:{category}:{cause}'.encode()).hexdigest()[:12]}"
        item = scrub_secrets({
            "id": fid,
            "recorded_at": _now_iso(),
            "project": project,
            "mission_id": mission_id,
            "category": category,
            "model": model,
            "role": role,
            "context_summary": context_summary[:350],
            "cause": cause[:300],
            "cause_status": "CONFIRMED" if cause_confirmed else "HYPOTHESIS",
            "evidence": evidence[:400],
            "attempts_count": len(attempts),
            "validated_solution": validated_solution[:350],
            "preventive_measure": preventive_measure[:350],
        })
        rows = [r for r in rows if r.get("id") != fid]
        rows.append(item)
        self._save(rows)

        if self.memory_root is not None and validated_solution and cause_confirmed:
            store = MemoryStore(self.memory_root)
            if store.get(project, fid) is None:
                store.record(
                    Entry(
                        id=fid,
                        project=project,
                        kind="fix",
                        title=f"[{category}] {cause[:80]}",
                        body=f"Solution: {validated_solution[:150]} | Prevention: {preventive_measure[:120]}",
                        tags=(category.lower(), mission_id, role, "failure-library"),
                        source=f"failure-library/{mission_id}",
                        author=role,
                        verified=True,
                        verified_by="tel99-verifier",
                        confidence=0.9,
                    ),
                    actor="failure-library",
                )
        return item

    def query(self, project: str, text: str, *, limit: int = 3) -> list[dict[str, Any]]:
        tokens = set(re.findall(r"[a-z0-9_]{3,}", (text or "").lower()))
        scored: list[tuple[int, dict[str, Any]]] = []
        for row in self._load():
            if row.get("project") != project:
                continue
            blob = " ".join(str(row.get(k) or "") for k in ("category", "context_summary", "cause", "validated_solution", "preventive_measure")).lower()
            hay = set(re.findall(r"[a-z0-9_]{3,}", blob))
            hits = len(tokens & hay)
            if hits > 0 or not tokens:
                bonus = 2 if row.get("validated_solution") else 0
                scored.append((hits + bonus, row))
        scored.sort(key=lambda x: (-x[0], x[1].get("id", "")))
        return [r for _, r in scored[:limit]]


# ---------------------------------------------------------------------------
# 4. Verifiable Trajectory Store (§14 — AgentTuning Principles, Secret-Free)
# ---------------------------------------------------------------------------
class TrajectoryRecorder:
    """Append-only, secret-redacted JSONL recorder of agent execution trajectories."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.path = self.root / "trajectories.jsonl"

    def record(
        self,
        *,
        project: str,
        mission_id: str,
        objective: str,
        model: str,
        role: str,
        tools_used: Sequence[dict[str, Any]],
        decisions: Sequence[str],
        errors: Sequence[str],
        repairs: Sequence[dict[str, Any]],
        tests: Sequence[dict[str, Any]],
        artifacts: Sequence[str],
        verdict: str,
        duration_seconds: float,
        cost_usd: float = 0.0,
    ) -> dict[str, Any]:
        if verdict not in ("SUCCESS", "FAILURE", "UNCERTAIN"):
            raise ValueError(f"invalid trajectory verdict: {verdict!r}")
        entry = scrub_secrets({
            "schema_version": 1,
            "recorded_at": _now_iso(),
            "project": project,
            "mission_id": mission_id,
            "objective": objective[:500],
            "model": model,
            "role": role,
            "tools_used": list(tools_used)[:30],
            "decisions": list(decisions)[:20],
            "errors": list(errors)[:20],
            "repairs": list(repairs)[:10],
            "tests": list(tests)[:20],
            "artifacts": list(artifacts)[:20],
            "verdict": verdict,
            "duration_seconds": round(float(duration_seconds), 3),
            "cost_usd": round(float(cost_usd), 6),
        })
        self.root.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def load_all(self, *, project: str | None = None, verdict: str | None = None) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        out: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if project and row.get("project") != project:
                continue
            if verdict and row.get("verdict") != verdict:
                continue
            out.append(row)
        return out

    def summarize(self) -> dict[str, Any]:
        rows = self.load_all()
        return {
            "total": len(rows),
            "success": sum(1 for r in rows if r.get("verdict") == "SUCCESS"),
            "failure": sum(1 for r in rows if r.get("verdict") == "FAILURE"),
            "uncertain": sum(1 for r in rows if r.get("verdict") == "UNCERTAIN"),
            "models": sorted({str(r.get("model")) for r in rows if r.get("model")}),
            "roles": sorted({str(r.get("role")) for r in rows if r.get("role")}),
        }
