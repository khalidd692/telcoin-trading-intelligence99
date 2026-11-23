"""Prepare five evidence-selected, fixed-model TEL99 missions from two sealed sessions.

This does not weaken the existing dynamic escalation gate. Every candidate
model must have already passed the exact approved Docker test in one complete
pinned historical session. Both sessions are verified independently even when
their checkout HEAD commits differ.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from scripts.agents.automation import compare_local_code as evidence
from scripts.agents.automation.autonomy_runtime import seal, validate_contract
from scripts.agents.automation.local_model_routing import validate_candidates
from scripts.agents.intelligence.catalog import by_id

GEMMA = "local/ollama-gemma4-e4b"
CODER = "local/ollama-qwen2.5-coder-7b"
APPROVED = (GEMMA, CODER)


def _read_pinned_source(path, digest):
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("source requires operator-pinned SHA-256")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("source registry SHA-256 differs from operator pin")
    source = json.loads(raw)
    if not isinstance(source, dict) or not isinstance(source.get("missions"), list):
        raise ValueError("source must contain a complete mission list")
    missions = source["missions"]
    if len(missions) != 5:
        raise ValueError("expected exactly five approved historical cases")
    if len({evidence._case_key(m) for m in missions}) != len(missions):
        raise ValueError("historical cases are not unique")
    # Verify the original operator-approved contracts.
    if source.get("approvals") != seal(missions):
        raise ValueError("historical contracts do not match sealed approvals")
    for m in missions:
        validate_contract(m, source["approvals"])
    return missions


def _checked_sessions(gemma_path, gemma_pin, coder_path, coder_pin):
    paths = [Path(gemma_path).resolve(strict=True), Path(coder_path).resolve(strict=True)]
    if paths[0] == paths[1] or any(p.is_relative_to(q) for p, q in
                                         ((paths[0], paths[1]), (paths[1], paths[0]))):
        raise ValueError("evidence must be in separate, nonnested session directories")
    sessions = [
        evidence._load_session(paths[0], gemma_pin),
        evidence._load_session(paths[1], coder_pin),
    ]
    specs = [by_id(GEMMA), by_id(CODER)]
    for session, spec in zip(sessions, specs):
        if spec is None or session.model not in spec.served_ids:
            raise ValueError("session model differs from the approved local catalogue")
    paired = evidence._paired_cases(sessions[0].missions, sessions[1].missions)
    observations = []
    for session, tasks in zip(sessions, paired):
        observed = {}
        for key, mission in tasks.items():
            source = evidence.local_codegen._source(mission)
            row = evidence._observe(session, mission, source)
            if not row["attempts"]:
                raise ValueError("mission has no verifiable attempts")
            observed[key] = row
        successes = all(row["accepted"] for row in observed.values())
        expected = ("COMPLETE", 0) if successes else ("BLOCKED", 2)
        if (session.status.get("phase"), session.status.get("worker_exit")) != expected:
            raise ValueError("historical campaign terminal phase does not match proofs")
        if evidence._read(session.root, "status.json") != session.snapshot:
            raise ValueError("historical campaign evidence changed during validation")
        observations.append(observed)
    return sessions, paired, observations


def _winner(rows):
    eligible = []
    for index, row in enumerate(rows):
        # An earlier failed generation may have no Docker receipt. A completed
        # accepted attempt is still independently verified in _observe.
        if row["accepted"] and row["attempts"][-1]["attributed_model_outcome"]:
            durations = [attempt["generation_seconds"] for attempt in row["attempts"]]
            elapsed = sum(durations) if all(t is not None for t in durations) else None
            eligible.append((len(row["attempts"]), elapsed is None,
                             float("inf") if elapsed is None else elapsed, index))
    if not eligible:
        raise ValueError("no independently verified accepted model for one approved task")
    # Prefer first-attempt success; then measured generation time; stable Gemma tie-break.
    return min(eligible)[-1]


def prepare_from_evidence(source, prefix, gemma_path, gemma_pin, coder_path, coder_pin):
    if not isinstance(prefix, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,38}", prefix):
        raise ValueError("invalid evidence campaign prefix")
    originals = _read_pinned_source(*source)
    sessions, paired, observations = _checked_sessions(
        gemma_path, gemma_pin, coder_path, coder_pin
    )
    if any(set(tasks) != {evidence._case_key(m) for m in originals} for tasks in paired):
        raise ValueError("historical sessions do not cover the exact approved source queue")

    specs = [by_id(x) for x in APPROVED]
    bindings = [{"id": spec.id, "model": spec.served_ids[0], "port": 11434} for spec in specs]
    validate_candidates(bindings)
    ids = {m["id"]: f"{prefix}-{i:02d}" for i, m in enumerate(originals, 1)}
    result = []
    decisions = []
    for m in originals:
        key = evidence._case_key(m)
        choice = _winner([obs[key] for obs in observations])
        binding = bindings[choice]
        row = {k: v for k, v in m.items() if k not in {"model", "port", "routing"}}
        row.update(id=ids[m["id"]], dependencies=[ids[dep] for dep in m["dependencies"]],
                   model=binding["model"], port=binding["port"])
        result.append(row)
        decisions.append({
            "case_sha256": key, "function": m["function"], "mission": row["id"],
            "selected_model": binding["model"],
            "selected_session_registry_sha256": sessions[choice].pin,
            "selected_attempts": len(observations[choice][key]["attempts"]),
            "accepted_by": [sessions[i].model for i in range(2) if observations[i][key]["accepted"]],
        })
    approvals = seal(result)
    for mission in result:
        validate_contract(mission, approvals)
    return {"missions": result, "approvals": approvals}, {
        "method": "verified-per-case-selection-v1", "source_sha256": source[1],
        "gemma_registry_sha256": gemma_pin, "coder_registry_sha256": coder_pin,
        "decisions": decisions,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--gemma", type=Path, required=True)
    parser.add_argument("--gemma-sha256", required=True)
    parser.add_argument("--coder", type=Path, required=True)
    parser.add_argument("--coder-sha256", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        registry, plan = prepare_from_evidence(
            (args.source, args.source_sha256), args.prefix,
            args.gemma, args.gemma_sha256, args.coder, args.coder_sha256,
        )
        raw = (json.dumps(registry, sort_keys=True, indent=2) + "\n").encode("utf-8")
        # Unique campaign IDs, no replacement of existing registry or evidence.
        with args.output.open("xb") as handle:
            handle.write(raw)
        plan_path = args.output.with_suffix(".selection.json")
        with plan_path.open("xb") as handle:
            handle.write((json.dumps(plan, sort_keys=True, indent=2) + "\n").encode("utf-8"))
        print(hashlib.sha256(raw).hexdigest())
        return 0
    except (OSError, ValueError, SyntaxError) as exc:
        print(f"Evidence route refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
