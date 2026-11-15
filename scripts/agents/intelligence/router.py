#!/usr/bin/env python3
"""Deterministic multi-model router for the TEL99 agent team.

Given a task, the router:

  1. classifies its **difficulty** from observable signals (task kind, size,
     whether it needs tools, confidentiality);
  2. filters the catalogue by hard constraints — **free only**, **tools
     required**, **availability verified** (fail-closed), **quota** left;
  3. ranks the survivors by a transparent score that combines the **quality
     prior / measured quality**, **latency**, **locality** (a confidential task
     prefers a local model) and **cost** (all free, so cost only breaks ties);
  4. returns the best choice, an ordered **fallback** list, and a **decision
     journal** entry explaining every rejection.

Every decision is explainable and reproducible: no randomness, no hidden
state. The router never chooses a model it cannot prove is free; when nothing
qualifies it refuses with a reason rather than guessing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import catalog
from .catalog import ModelSpec

# Difficulty levels, ordered.
EASY, MEDIUM, HARD = "easy", "medium", "hard"
DIFFICULTY_ORDER = {EASY: 0, MEDIUM: 1, HARD: 2}

# Minimum quality prior required per difficulty. A hard task needs a model we
# believe is strong; an easy one tolerates a small local model.
MIN_QUALITY = {EASY: 0.30, MEDIUM: 0.50, HARD: 0.65}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


@dataclass
class TaskProfile:
    """Observable signals about a task, used to classify its difficulty."""

    kind: str = "general"          # "code" | "analysis" | "review" | "general"
    description: str = ""
    touches_files: int = 0
    needs_tools: bool = True
    confidential: bool = False
    estimated_tokens: int = 0


@dataclass
class Decision:
    """The outcome of a routing call, with full provenance."""

    task: TaskProfile
    difficulty: str
    chosen: ModelSpec | None
    fallbacks: list[ModelSpec]
    rejected: list[dict]
    reasons: list[str] = field(default_factory=list)
    decided_at: str = field(default_factory=utcnow_iso)

    @property
    def ok(self) -> bool:
        return self.chosen is not None

    def to_dict(self) -> dict:
        return {
            "decided_at": self.decided_at,
            "difficulty": self.difficulty,
            "task": {
                "kind": self.task.kind,
                "touches_files": self.task.touches_files,
                "needs_tools": self.task.needs_tools,
                "confidential": self.task.confidential,
                "estimated_tokens": self.task.estimated_tokens,
            },
            "chosen": self.chosen.id if self.chosen else None,
            "fallbacks": [m.id for m in self.fallbacks],
            "rejected": self.rejected,
            "reasons": self.reasons,
        }


def classify_difficulty(task: TaskProfile) -> tuple[str, list[str]]:
    """Classify a task as easy / medium / hard from observable signals.

    Returns the level and the list of signals that drove it, so the decision is
    auditable rather than a black box.
    """
    signals: list[str] = []
    score = 0

    if task.kind in ("code", "analysis"):
        score += 1
        signals.append(f"kind={task.kind} (+1)")
    if task.kind == "review":
        score += 1
        signals.append("kind=review (+1)")

    if task.touches_files >= 5:
        score += 2
        signals.append(f"touches_files={task.touches_files} (+2)")
    elif task.touches_files >= 2:
        score += 1
        signals.append(f"touches_files={task.touches_files} (+1)")

    if task.estimated_tokens >= 60_000:
        score += 2
        signals.append(f"estimated_tokens={task.estimated_tokens} (+2)")
    elif task.estimated_tokens >= 20_000:
        score += 1
        signals.append(f"estimated_tokens={task.estimated_tokens} (+1)")

    if task.needs_tools:
        signals.append("needs_tools (+0)")

    if score >= 3:
        level = HARD
    elif score >= 1:
        level = MEDIUM
    else:
        level = EASY
    signals.append(f"=> {level}")
    return level, signals


def _rank_key(spec: ModelSpec, task: TaskProfile,
              measured: dict[str, float] | None) -> tuple:
    """Sort key: higher is better. Deterministic, no randomness."""
    quality = (measured or {}).get(spec.id, spec.quality_prior)
    locality = 1.0 if (task.confidential and spec.is_local) else 0.0
    latency = {"fast": 1.0, "medium": 0.5, "slow": 0.0}.get(spec.latency_tier, 0.0)
    verified = 1.0 if spec.verified else 0.0
    score = 3.0 * quality + 1.0 * locality + 0.5 * latency + 0.5 * verified
    return (-score, spec.id)


def route(
    task: TaskProfile,
    *,
    quota_remaining: int | None = None,
    min_quota: int = 1,
    dry_run: bool = False,
    measured_quality: dict[str, float] | None = None,
    journal: list[dict] | None = None,
) -> Decision:
    """Choose a model for ``task`` and explain the decision.

    Hard rules:
      * only ``cost_tier == free`` models are eligible (no-spend project rule);
      * a task that needs tools requires ``supports_tools``;
      * availability must be ``verified`` — except in ``dry_run``, where an
        unverified model is allowed but flagged, because a dry run spends
        nothing and its purpose is exactly to decide what to probe;
      * quota is checked fail-closed for a real run: an unknown quota refuses.
    """
    difficulty, signals = classify_difficulty(task)
    min_quality = MIN_QUALITY[difficulty]

    rejected: list[dict] = []
    eligible: list[ModelSpec] = []

    for spec in catalog.MODEL_CATALOG:
        if not spec.is_free:
            rejected.append({"id": spec.id, "reason": f"cost_tier={spec.cost_tier} "
                             "(no-spend rule)"})
            continue
        if task.needs_tools and not spec.supports_tools:
            rejected.append({"id": spec.id, "reason": "does not support tools"})
            continue
        quality = (measured_quality or {}).get(spec.id, spec.quality_prior)
        if quality < min_quality:
            rejected.append({
                "id": spec.id,
                "reason": f"quality {quality:.2f} < minimum {min_quality:.2f} "
                          f"for {difficulty}",
            })
            continue
        if not spec.verified and not dry_run:
            rejected.append({"id": spec.id, "reason": "availability not verified "
                             "(fail-closed on a real run)"})
            continue
        if spec.is_local and not dry_run:
            # A local model is only reachable when the operator's machine is on.
            rejected.append({"id": spec.id, "reason": "local model unreachable "
                             "when the operator's PC is off"})
            continue
        eligible.append(spec)

    # Quota: fail-closed on a real run.
    reasons: list[str] = []
    if not dry_run:
        if quota_remaining is None:
            reasons.append("quota unknown: refusing to start a real run")
        elif quota_remaining < min_quota:
            reasons.append(f"quota too low: {quota_remaining} < {min_quota}")

    eligible.sort(key=lambda s: _rank_key(s, task, measured_quality))

    chosen = eligible[0] if eligible and not reasons else None
    fallbacks = eligible[1:] if chosen else []

    decision = Decision(
        task=task,
        difficulty=difficulty,
        chosen=chosen,
        fallbacks=fallbacks,
        rejected=rejected,
        reasons=reasons + signals,
    )

    if journal is not None:
        journal.append(decision.to_dict())
    return decision


def load_measured_quality(path: str) -> dict[str, float]:
    """Read measured success rates written by the improvement loop.

    A missing or unreadable file yields an empty map, so the router falls back
    to the catalogue priors instead of failing.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    out: dict[str, float] = {}
    for model_id, payload in (data or {}).items():
        if isinstance(payload, dict) and "success_rate" in payload:
            try:
                out[model_id] = float(payload["success_rate"])
            except (TypeError, ValueError):
                continue
    return out
