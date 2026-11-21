"""Grade interrupted verification plans against an exhaustive oracle and frozen PR #132."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
BASE_PLANNER_SHA256 = "05900692cd1a667166cd93e8e98767898adf12faaed4e060488edd0ac6be0e49"
COMPARISON_SHA256 = "5ee7f8222e039670d1b37fe07c46da4cd5a4aa2e2442b5e0304b1ba1c2e72550"
PLAN_FIELDS = {"status", "checks", "cost", "unavailable_mandatory", "uncovered", "minimum_cost"}


def frozen_file(name, digest):
    path = HERE / name
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit(f"Frozen dependency changed: {name}")
    return path


def oracle(case):
    contract = case["contract"]
    passed = set(case["passed"])
    unavailable = set(case["unavailable"])
    pending_mandatory = set(contract["mandatory"]) - passed
    catalog = {row["id"]: row for row in contract["checks"]}
    remaining = sorted(catalog.keys() - passed - unavailable)
    obligations = set(contract["obligations"])
    blocked = {"status": "blocked", "checks": []}

    if pending_mandatory & unavailable:
        return dict(blocked, unavailable_mandatory=sorted(pending_mandatory & unavailable))

    def covered(ids):
        return {obligation for check in ids for obligation in catalog[check]["covers"]}

    missing = obligations - covered(passed.union(remaining))
    if missing:
        return dict(blocked, uncovered=sorted(missing))

    feasible_choices = (
        (sum(catalog[check]["cost"] for check in group), len(group), group)
        for size in range(len(remaining) + 1)
        for group in itertools.combinations(remaining, size)
        if pending_mandatory <= set(group) and obligations <= covered(passed.union(group))
    )
    cost, _, group = min(feasible_choices)
    if cost > contract["budget"]:
        return dict(blocked, minimum_cost=cost)
    return {"status": "planned", "checks": list(group), "cost": cost}


def run_script(script, stdin, *options):
    try:
        with tempfile.TemporaryDirectory() as working_directory:
            completed = subprocess.run(
                [sys.executable, "-IB", str(script), *options],
                cwd=working_directory,
                input=json.dumps(stdin),
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=5,
                check=False,
            )
        if completed.returncode == 0:
            return json.loads(completed.stdout)
        return {"error": f"exit {completed.returncode}"}
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        return {"error": type(exc).__name__}


def baseline_result(script, case):
    # Remove unavailable checks, preserving originally mandatory IDs. The base
    # planner has no input for already-completed checks and quotes the full cost.
    original = case["contract"]
    unavailable = set(case["unavailable"])
    missing_mandatory = sorted(unavailable.intersection(original["mandatory"]))
    if missing_mandatory:
        return {"status": "blocked", "checks": [], "unavailable_mandatory": missing_mandatory}
    contract = dict(
        original,
        checks=[row for row in original["checks"] if row["id"] not in unavailable],
    )
    return run_script(script, contract)


def check_result(result, expected, *, reused=None):
    if not isinstance(result, dict) or "error" in result:
        return False
    if reused is not None and result.get("reused") != reused:
        return False
    plan = {key: value for key, value in result.items() if key in PLAN_FIELDS}
    if any(type(plan[key]) is not int for key in ("cost", "minimum_cost") if key in plan):
        return False
    return plan == expected


def summary(cases, metrics):
    return {
        "correct_plans": sum(row["passed"] and row["expected"] == "planned" for row in metrics.values()),
        "correct_blockers": sum(row["passed"] and row["expected"] == "blocked" for row in metrics.values()),
        "budget_feasible_cases": sum(row["expected"] == "planned" for row in metrics.values()),
        "correct": sum(row["passed"] for row in metrics.values()),
        "total": len(cases),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--candidate", type=Path)
    selection.add_argument("--baseline-only", action="store_true")
    args = parser.parse_args()
    base = frozen_file("base_plan_checks.py", BASE_PLANNER_SHA256)
    api = runpy.run_path(str(frozen_file("base_improvement.py", COMPARISON_SHA256)))
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    outcomes = []
    metrics = {"baseline": {}, "candidate": {}}
    failure_details = {}
    for name, case in cases.items():
        expected = oracle(case)
        result = baseline_result(base, case)
        observations = [("baseline", result, check_result(result, expected))]
        if args.candidate:
            result = run_script(args.candidate.resolve(), case, "--replan")
            reused = sorted(case["passed"])
            success = check_result(result, expected, reused=reused)
            observations.append(("candidate", result, success))
            if not success:
                failure_details[name] = {"expected": dict(expected, reused=reused), "actual": result}
        for arm, _, success in observations:
            metrics[arm][name] = {"passed": success, "expected": expected["status"]}
            outcomes.append(api["Outcome"](name, arm, success))

    if args.baseline_only:
        print(json.dumps(summary(cases, metrics["baseline"]), sort_keys=True))
        return 0
    verdict = api["compare"](outcomes, baseline_id="baseline", candidate_id="candidate")
    report = verdict.to_dict()
    report["baseline_summary"] = summary(cases, metrics["baseline"])
    report["candidate_summary"] = summary(cases, metrics["candidate"])
    report["candidate_failures"] = failure_details
    print(json.dumps(report, indent=2))
    return int(verdict.verdict != "keep" or bool(failure_details))


if __name__ == "__main__":
    raise SystemExit(main())
