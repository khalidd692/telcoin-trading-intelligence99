#!/usr/bin/env python3
"""Controlled self-improvement loop for the TEL99 agent team.

The loop is the five steps required by issue #67, axis 3:

    observe -> propose -> test -> compare -> keep-or-reject

It is deliberately *not* autonomous: it produces a proposal and a measured
comparison, and it writes a decision record. It never edits a permission, a
security rule, a model choice in production, or the repository history. A human
keeps the last word; the loop only makes the comparison reproducible.

The measurable quantity is a model's **success rate on a fixed task set**: the
same tasks are run with a baseline and a candidate, and the candidate is kept
only when it does not regress. That measured rate is exactly what
``router.load_measured_quality`` reads back, which closes the loop between
"what we measured" and "what the router chooses next time".
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

KEEP, REJECT, INCONCLUSIVE = "keep", "reject", "inconclusive"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


@dataclass
class Outcome:
    """One observation: how a model did on one task."""

    task_id: str
    model_id: str
    success: bool
    tokens: int = 0
    seconds: float = 0.0
    evidence: str = ""


@dataclass
class Comparison:
    """Before/after comparison of a baseline and a candidate on the same tasks."""

    baseline_id: str
    candidate_id: str
    baseline_rate: float
    candidate_rate: float
    delta: float
    verdict: str
    task_count: int
    per_task: list[dict] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    decided_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> dict:
        return {
            "decided_at": self.decided_at,
            "baseline": self.baseline_id,
            "candidate": self.candidate_id,
            "baseline_rate": self.baseline_rate,
            "candidate_rate": self.candidate_rate,
            "delta": self.delta,
            "verdict": self.verdict,
            "task_count": self.task_count,
            "per_task": self.per_task,
            "reasons": self.reasons,
        }


def success_rate(outcomes: list[Outcome], model_id: str) -> float:
    """Success rate of one model over its outcomes (0.0 when it has none)."""
    rows = [o for o in outcomes if o.model_id == model_id]
    if not rows:
        return 0.0
    return sum(1 for o in rows if o.success) / len(rows)


def compare(
    outcomes: list[Outcome],
    *,
    baseline_id: str,
    candidate_id: str,
    min_delta: float = 0.0,
) -> Comparison:
    """Compare a candidate against a baseline on the tasks they both ran.

    Only tasks present for *both* models are counted, so a candidate cannot win
    by skipping the hard tasks. The candidate is kept only when its rate is at
    least ``min_delta`` better and it did not lose any task the baseline won —
    a guard against trading one failure for another.
    """
    by_task: dict[str, dict[str, Outcome]] = {}
    for o in outcomes:
        by_task.setdefault(o.task_id, {})[o.model_id] = o

    shared = sorted(
        t for t, m in by_task.items() if baseline_id in m and candidate_id in m
    )
    if not shared:
        return Comparison(
            baseline_id=baseline_id, candidate_id=candidate_id,
            baseline_rate=0.0, candidate_rate=0.0, delta=0.0,
            verdict=INCONCLUSIVE, task_count=0,
            reasons=["no task was run by both models: cannot compare"],
        )

    base_wins = sum(1 for t in shared if by_task[t][baseline_id].success)
    cand_wins = sum(1 for t in shared if by_task[t][candidate_id].success)
    base_rate = base_wins / len(shared)
    cand_rate = cand_wins / len(shared)
    delta = cand_rate - base_rate

    regressions = [
        t for t in shared
        if by_task[t][baseline_id].success and not by_task[t][candidate_id].success
    ]
    per_task = [
        {
            "task_id": t,
            "baseline": by_task[t][baseline_id].success,
            "candidate": by_task[t][candidate_id].success,
        }
        for t in shared
    ]

    reasons: list[str] = []
    if regressions:
        reasons.append(f"regressed on {len(regressions)} task(s) the baseline won: "
                       f"{regressions}")
        verdict = REJECT
    elif delta > min_delta:
        reasons.append(f"candidate improves {delta:+.2%} with no regression")
        verdict = KEEP
    elif delta >= 0:
        reasons.append(f"no measurable improvement ({delta:+.2%}); keeping baseline")
        verdict = REJECT
    else:
        reasons.append(f"candidate is worse ({delta:+.2%})")
        verdict = REJECT

    return Comparison(
        baseline_id=baseline_id, candidate_id=candidate_id,
        baseline_rate=base_rate, candidate_rate=cand_rate, delta=delta,
        verdict=verdict, task_count=len(shared), per_task=per_task, reasons=reasons,
    )


def measured_quality(outcomes: list[Outcome]) -> dict[str, dict]:
    """Aggregate outcomes into the measured-quality file the router reads."""
    model_ids = sorted({o.model_id for o in outcomes})
    result: dict[str, dict] = {}
    for model_id in model_ids:
        rows = [o for o in outcomes if o.model_id == model_id]
        result[model_id] = {
            "success_rate": round(success_rate(outcomes, model_id), 4),
            "tasks": len(rows),
            "avg_tokens": round(sum(o.tokens for o in rows) / len(rows), 1),
            "avg_seconds": round(sum(o.seconds for o in rows) / len(rows), 2),
        }
    return result


def write_measured_quality(path: str | pathlib.Path, outcomes: list[Outcome]) -> dict:
    """Persist the measured quality so the router uses evidence, not priors."""
    data = measured_quality(outcomes)
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    tmp.replace(target)
    return data


def apply_verdict(comparison: Comparison, store, project: str, *,
                  actor: str = "improvement-loop") -> str:
    """Record the loop's outcome in shared memory.

    A ``keep`` records a verified procedure; a ``reject`` records an error entry
    so the same candidate is not re-tried blindly. Returns the entry id.
    """
    from .memory import Entry

    if comparison.verdict == KEEP:
        entry = Entry(
            id=f"improve-{comparison.candidate_id}-{comparison.decided_at}",
            project=project,
            kind="procedure",
            title=f"Adopt {comparison.candidate_id} over {comparison.baseline_id}",
            body=(f"Measured on {comparison.task_count} shared task(s): "
                  f"baseline {comparison.baseline_rate:.0%} -> candidate "
                  f"{comparison.candidate_rate:.0%} ({comparison.delta:+.0%}). "
                  + "; ".join(comparison.reasons)),
            tags=("improvement", "adopted"),
            source="improvement-loop",
            author=actor,
            confidence=min(0.95, 0.5 + abs(comparison.delta)),
            verified=True,
            verified_by="improvement-loop",
        )
    else:
        entry = Entry(
            id=f"improve-{comparison.candidate_id}-{comparison.decided_at}",
            project=project,
            kind="error",
            title=f"Reject {comparison.candidate_id} vs {comparison.baseline_id}",
            body=("Candidate not adopted. " + "; ".join(comparison.reasons)),
            tags=("improvement", "rejected"),
            source="improvement-loop",
            author=actor,
            confidence=0.7,
        )
    store.record(entry, actor=actor)
    return entry.id
