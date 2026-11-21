"""Evaluate reserved budget-planning cases. Run with --root CHECKOUT [--baseline-only]."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

# Pin compare/Outcome to the unchanged module in base 44ca6bd9.
COMPARISON_SHA256 = "5ee7f8222e039670d1b37fe07c46da4cd5a4aa2e2442b5e0304b1ba1c2e72550"


def baseline(case):
    needs = set(case["obligations"])
    selected = [
        check for check in case["checks"]
        if check["id"] in case["mandatory"] or needs.intersection(check["covers"])
    ]
    return {"status": "planned", "checks": [check["id"] for check in selected],
            "cost": sum(check["cost"] for check in selected)}


def verify(case, result):
    if not isinstance(result, dict) or not isinstance(result.get("checks"), list):
        return False
    catalog = {check["id"]: check for check in case["checks"]}
    required = set(case["mandatory"])
    needs = set(case["obligations"])

    def fits(ids):
        cost = sum(catalog[key]["cost"] for key in ids)
        covered = {need for key in ids for need in catalog[key]["covers"]}
        return cost <= case["budget"] and required.issubset(ids) and needs <= covered

    ids = result["checks"]
    if result.get("status") == "blocked":
        # The small reserved cases permit exhaustive, independent feasibility checks.
        return ids == [] and not any(
            fits(group) for size in range(len(catalog) + 1)
            for group in itertools.combinations(catalog, size)
        )
    if result.get("status") != "planned" or not all(isinstance(key, str) for key in ids):
        return False
    if len(set(ids)) != len(ids) or not set(ids) <= catalog.keys():
        return False
    return (type(result.get("cost")) is int and fits(ids)
            and result["cost"] == sum(catalog[key]["cost"] for key in ids))


def run_candidate(script, case, workdir):
    try:
        process = subprocess.run(
            [sys.executable, "-I", "-B", str(script)], cwd=workdir, input=json.dumps(case),
            text=True, encoding="utf-8", capture_output=True, timeout=10, check=False,
        )
        if process.returncode == 0:
            return json.loads(process.stdout)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--baseline-only", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    module = root / "scripts/agents/intelligence/improvement.py"
    if hashlib.sha256(module.read_bytes()).hexdigest() != COMPARISON_SHA256:
        parser.error("comparison module differs from the frozen base")
    api = runpy.run_path(str(module))
    cases = json.loads(Path(__file__).with_name("reserved_cases.json").read_text(encoding="utf-8"))
    outcomes = [api["Outcome"](name, "baseline", verify(case, baseline(case)))
                for name, case in cases.items()]
    if args.baseline_only:
        print(json.dumps({"passed": sum(row.success for row in outcomes), "total": len(cases)}))
        return 0
    script = root / ".agents/skills/plan-verification/scripts/plan_checks.py"
    for name, case in cases.items():
        with tempfile.TemporaryDirectory() as workdir:
            result = run_candidate(script, case, workdir)
        outcomes.append(api["Outcome"](name, "candidate", verify(case, result)))
    report = api["compare"](outcomes, baseline_id="baseline", candidate_id="candidate")
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.verdict == "keep" else 1


if __name__ == "__main__":
    raise SystemExit(main())
