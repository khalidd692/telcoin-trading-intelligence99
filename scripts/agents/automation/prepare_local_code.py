"""Prepare fresh fixed-model or routed Night Lab contracts from an approved task set."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from scripts.agents.automation.autonomy_runtime import seal, validate_contract
from scripts.agents.automation.local_model_routing import validate_candidates
from scripts.agents.intelligence.catalog import by_id
from scripts.agents.night_lab_20261123 import load_registry


def prepare(missions, prefix, mode, bindings, escalate):
    if not re.fullmatch(r"[A-Za-z0-9-]{1,44}", prefix):
        raise ValueError("invalid new mission ID prefix")
    validate_candidates(bindings)
    if mode == "fixed" and (len(bindings) != 1 or escalate):
        raise ValueError("fixed comparison runs require one binding and no escalation")
    if mode == "routed" and escalate and len(bindings) < 2:
        raise ValueError("escalation requires at least two approved model bindings")
    ids = {m["id"]: f"{prefix}-{i:02d}" for i, m in enumerate(missions, 1)}
    if (set(ids) & set(ids.values()) or set(escalate) - ids.keys()
            or len(set(escalate)) != len(escalate) or len(missions) + len(escalate) > 8):
        raise ValueError("new IDs must be distinct and each escalation must name one source mission")

    prepared = []
    for mission in missions:
        if "escalates_from" in mission:
            raise ValueError("use a source registry without conditional successors")
        row = {k: v for k, v in mission.items() if k not in {"model", "port", "routing"}}
        row["id"] = ids[mission["id"]]
        row["dependencies"] = [ids[dep] for dep in mission["dependencies"]]
        if mode == "fixed":
            row.update(model=bindings[0]["model"], port=bindings[0]["port"])
        else:
            row["routing"] = {"candidates": bindings}
        prepared.append(row)
    for old in escalate:
        parent = next(m for m in prepared if m["id"] == ids[old])
        if parent.get("max_attempts") != 2:
            raise ValueError("an escalation predecessor must allow two verified attempts")
        prepared.append({**parent, "id": f"{prefix}-{len(prepared) + 1:02d}",
                         "escalates_from": parent["id"]})
    if set(ids) & {m["id"] for m in prepared}:
        raise ValueError("prepared registry would reuse an existing mission ID")
    approvals = seal(prepared)
    for mission in prepared:
        validate_contract(mission, approvals)
    return {"missions": prepared, "approvals": approvals}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--mode", required=True, choices=("fixed", "routed"))
    parser.add_argument("--binding", nargs=2, action="append", required=True, metavar=("MODEL_ID", "PORT"))
    parser.add_argument("--escalate", action="append", default=[], metavar="SOURCE_MISSION_ID")
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        _, original = load_registry(args.source, args.source_sha256)
        bindings = []
        for model_id, port in args.binding:
            spec = by_id(model_id)
            if spec is None or not spec.served_ids:
                raise ValueError("unknown llama.cpp catalogue ID")
            bindings.append({"id": model_id, "model": spec.served_ids[0], "port": int(port)})
        data = prepare(original, args.prefix, args.mode, bindings, args.escalate)
        raw = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")
        with args.output.open("xb") as handle:
            handle.write(raw)
        print(hashlib.sha256(raw).hexdigest())
        return 0
    except (OSError, ValueError) as exc:
        print(f"Registry preparation refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
