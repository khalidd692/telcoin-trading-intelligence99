#!/usr/bin/env python3
"""Hermes adapter — wraps the existing router, memory and improvement loop.

Hermes is the "router, memory and coordination" role of the team. In this
repository that role is implemented by ``scripts/agents/intelligence`` (model
router, versioned shared memory, controlled improvement loop) and by
``scripts/agents/team_config.py`` (the three-agent definition and the guard
wiring). This adapter does not re-implement any of it: it reuses those modules
and exposes them as protocol operations.

Capabilities are declared from what the modules can actually do, offline and
deterministically. The adapter is ``connected`` because it runs in-process; it
does not claim a network transport it does not have.
"""

from __future__ import annotations

import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve()
_AGENTS_DIR = _HERE.parents[2]           # scripts/agents
if str(_AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENTS_DIR))

from intelligence import improvement, memory, router  # noqa: E402

from ..envelope import Actor, Envelope

MEMORY_ROOT = _AGENTS_DIR.parents[1] / "memory"
MEASURED_PATH = MEMORY_ROOT / "measured_quality.json"


def actor() -> Actor:
    return Actor(
        environment="hermes",
        id="hermes-router",
        capabilities=("route_model", "recall_memory", "record_memory",
                      "compare_improvement"),
        connected=True,
    )


def _store(root: str | None = None) -> memory.MemoryStore:
    """Build the memory store, preferring the durable backend when present.

    An explicit ``root`` always means file storage at that path. Otherwise a
    durable store provided by the run environment (the automation KV store, via
    ``protocol.store.default_store``) is reused so knowledge survives the
    container; with no durable store we keep the repository-local files.
    """
    if root:
        return memory.MemoryStore(root)
    from protocol import store as protocol_store
    backend = protocol_store.default_store()
    if backend.durable():
        return memory.MemoryStore(backend=backend)
    return memory.MemoryStore(MEMORY_ROOT)


def route(task_kind: str, *, touches_files: int = 0, needs_tools: bool = True,
          confidential: bool = False, estimated_tokens: int = 0,
          quota_remaining: int | None = None, dry_run: bool = True) -> dict:
    """Reuse the existing router to choose a model for a task."""
    measured = router.load_measured_quality(str(MEASURED_PATH))
    task = router.TaskProfile(
        kind=task_kind, touches_files=touches_files, needs_tools=needs_tools,
        confidential=confidential, estimated_tokens=estimated_tokens,
    )
    decision = router.route(task, quota_remaining=quota_remaining,
                            dry_run=dry_run, measured_quality=measured)
    return decision.to_dict()


def recall(query: str, *, project: str = "tel99", limit: int = 5,
           root: str | None = None) -> list[dict]:
    """Reuse the versioned shared memory to retrieve past experience."""
    return [e.to_dict() for e in _store(root).search(project, query, limit=limit)]


def remember(entry: dict, *, root: str | None = None) -> dict:
    """Reuse the shared memory to record a validated learning."""
    store = _store(root)
    recorded = store.record(memory.Entry(
        id=entry["id"],
        project=entry.get("project", "tel99"),
        kind=entry.get("kind", "fact"),
        title=entry["title"],
        body=entry.get("body", ""),
        tags=tuple(entry.get("tags", ())),
        source=entry.get("source", "hermes-adapter"),
        verified=bool(entry.get("verified", False)),
        verified_by=entry.get("verified_by", "") or "",
        confidence=float(entry.get("confidence", 0.5)),
    ))
    return recorded.to_dict()


def compare(outcomes: list[dict], *, baseline_id: str, candidate_id: str) -> dict:
    """Reuse the improvement loop to compare a candidate against a baseline."""
    rows = [improvement.Outcome(**o) for o in outcomes]
    return improvement.compare(rows, baseline_id=baseline_id,
                               candidate_id=candidate_id).to_dict()


def handle(envelope: Envelope, *, root: str | None = None) -> Envelope:
    """Consume a protocol envelope and answer with a result envelope.

    A ``mission``/``sub_mission`` asking to route a model or to recall memory is
    answered with a ``result`` envelope carrying the router's decision or the
    recalled entries as evidence. Anything Hermes cannot do is reported as an
    explicit, non-retryable error rather than a silent success.
    """
    intent = (envelope.mission or {}).get("description", "").lower()
    result_env = Envelope.create(
        origin=actor(), kind="result", state="done",
        correlation_id=envelope.correlation_id,
        parent_envelope_id=envelope.envelope_id,
        result={"status": "success", "summary": "", "artifacts": [],
                "metrics": {}},
    )
    result_env.target = envelope.origin

    if "route" in intent or "model" in intent:
        decision = route("code", dry_run=True)
        result_env.result["summary"] = (
            f"routed to {decision['chosen']} (difficulty {decision['difficulty']})"
        )
        result_env.result["metrics"] = {"difficulty": decision["difficulty"],
                                        "chosen": decision["chosen"] or "none"}
    elif "recall" in intent or "memoire" in intent or "memory" in intent:
        hits = recall(intent, root=root)
        result_env.result["summary"] = f"recalled {len(hits)} memory entr(ies)"
        result_env.result["metrics"] = {"recalled": len(hits)}
    else:
        result_env.state = "failed"
        result_env.result = {
            "status": "not_run",
            "summary": "Hermes adapter received an intent it does not implement",
            "artifacts": [], "metrics": {},
        }
        result_env.errors = [{
            "code": "hermes.unsupported_intent",
            "message": f"no Hermes operation matches intent {intent!r}",
            "retryable": False, "attempt": 1, "max_attempts": 1, "fatal": True,
        }]
    return result_env
