"""Create a complete offline example in a newly created project kit."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from . import platform_evidence, project_kit
from .native import mission, provider


def _export(path, report):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def run(root, project="atlas-lab", repository="example/atlas"):
    roles = ["quant", "development", "quality"]
    models = ["openhands/deepseek-v4.1-flash"]
    kit = project_kit.install(root, {
        "schema_version": 1, "project": project, "repository": repository, "roles": roles,
        "skills": ["plan-verification"], "approved_models": models,
    })
    mission_id = "demo-double"
    steps = [{"role": role, "estimated_tokens": 1000, "estimated_seconds": 10} for role in roles]
    steps[-1]["skills"] = ["plan-verification"]
    plan = project_kit.prepare(kit, {
        "project": project, "mission_id": mission_id, "approved_models": models, "steps": steps,
        "budget": {"max_calls": 3, "quota_remaining": 15, "reserve": 12, "max_seconds": 30,
                   "max_context_tokens": 3000},
        "verification": {"budget": 1, "obligations": ["double"], "mandatory": ["behavior"],
                         "checks": [{"id": "behavior", "cost": 1, "covers": ["double"]}]},
    })
    if plan["status"] != "PLANNED":
        raise ValueError("fixture planning failed")

    scripted = provider.ScriptedProvider(["```double.py\ndef double(n):\n    return n * 2\n```"])
    engine = mission.MissionEngine(provider=scripted, quota_remaining=20,
                                   store_root=kit.state, workspace_root=kit.artifacts,
                                   memory_root=kit.memory)
    spec = mission.MissionSpec(
        mission_id=mission_id, project=project, prompt="Write double(n).", artifacts=["double.py"],
        checks=[mission.Check("behavior", [sys.executable, "-I", "-B", "-c",
                                           "import runpy; assert runpy.run_path('double.py')['double'](7) == 14"])],
        max_repairs=0,
    )
    result = engine.run(spec)
    if result.verdict != mission.PASS:
        raise ValueError("fixture did not pass its independent check")
    journal = engine.artifact_directory(spec) / "journal.json"
    raw = journal.read_bytes()
    pinned = hashlib.sha256(raw).hexdigest()
    evidence = platform_evidence.verify(kit, mission_id, pinned)
    recorded_at = json.loads(raw)["recorded_at"]
    status = {
        "data_mode": "fixture", "project": project, "state": result.verdict,
        "last_observed": {"HEARTBEAT": recorded_at},
        "missions": {mission_id: {"id": mission_id, "project": project, "status": result.verdict,
                                  "at": recorded_at, "verification": {
                                      "ok": True, "artifact_sha256": result.artifact_digests["double.py"]}}},
    }
    _export(kit.root / "plan.json", plan)
    _export(kit.root / "status.json", status)
    _export(kit.root / "evidence.json", evidence)
    return {"status": result.verdict, "project": project, "mission_id": mission_id,
            "journal_sha256": pinned, "provider_mode": "scripted",
            "provider_calls": scripted.calls, "external_model_calls": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--project", default="atlas-lab")
    parser.add_argument("--repository", default="example/atlas")
    args = parser.parse_args(argv)
    try:
        report = run(args.directory, args.project, args.repository)
    except (OSError, ValueError, mission.MissionError) as exc:
        print(json.dumps({"status": "INVALID", "error": str(exc)}))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
