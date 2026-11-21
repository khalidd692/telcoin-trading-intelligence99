"""Exercise native Hermes Skill lookup and the packaged planner without a model."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from contextlib import chdir
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-root", required=True, type=Path, help="Local upstream Hermes checkout")
    args = parser.parse_args()
    sys.path.insert(0, str(args.hermes_root.resolve(strict=True)))
    skills = Path(__file__).resolve().parents[3] / ".agents" / "skills"

    contract = {
        "budget": 5,
        "obligations": ["lecture", "reprise"],
        "mandatory": ["politique"],
        "checks": [
            {"id": "lecture", "cost": 3, "covers": ["lecture"]},
            {"id": "reprise", "cost": 3, "covers": ["reprise"]},
            {"id": "combiné", "cost": 4, "covers": ["lecture", "reprise"]},
            {"id": "politique", "cost": 1, "covers": []},
        ],
    }
    resumed = {"contract": dict(contract, budget=3), "passed": ["lecture", "politique"],
               "unavailable": ["combiné"]}

    with tempfile.TemporaryDirectory(prefix="hermes-skill-") as temporary:
        home = Path(temporary)
        profile = home / "profile"
        profile.mkdir()
        os.environ.update(HERMES_HOME=str(profile), HOME=str(home), USERPROFILE=str(home))
        (profile / "config.yaml").write_text(json.dumps({
            "skills": {"external_dirs": [str(skills)], "project_discovery": False},
        }), encoding="utf-8")
        workdir = home / "projet indépendant"
        workdir.mkdir()

        with chdir(workdir):
            from tools.skills_tool import skill_view

            skill = json.loads(skill_view("plan-verification"))
            if not skill.get("success"):
                raise SystemExit(f"Hermes did not discover plan-verification: {skill}")
            skill_dir = Path(skill["skill_dir"]).resolve()
            script = "scripts/plan_checks.py"
            if (skill_dir != (skills / "plan-verification").resolve()
                    or script not in skill.get("linked_files", {}).get("scripts", [])
                    or "--input" not in skill["content"]):
                raise SystemExit("Hermes did not load the expected portable Skill and its planner.")

            results = {}
            for name, options, request in (("plan", [], contract), ("replan", ["--replan"], resumed)):
                request_file = Path("données de vérification.json")
                request_file.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
                command = [sys.executable, "-IB", str(skill_dir / script), *options, "--input", str(request_file)]
                results[name] = json.loads(subprocess.check_output(command, stdin=subprocess.DEVNULL, timeout=10))

    if (results["plan"]["status"], results["plan"]["checks"], results["plan"]["cost"]) != (
            "planned", ["combiné", "politique"], 5):
        raise SystemExit(f"Unexpected initial plan: {results['plan']}")
    if results["replan"] != {"status": "planned", "checks": ["reprise"], "cost": 3,
                             "all_relevant_cost": 3, "reused": ["lecture", "politique"]}:
        raise SystemExit(f"Unexpected resumed plan: {results['replan']}")
    print(json.dumps({"message": "Native skill_view and both CLI modes passed", **results}, indent=2))


if __name__ == "__main__":
    main()
