"""Report replan quality, executable outcomes and paired costs from one run per case."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy


HERE = Path(__file__).resolve().parent
EVALUATOR_SHA256 = "ca9ebc453e98bbadcca72391b801ea28a041e3c07996ae491aaa9142d8f59923"
CASES_SHA256 = "34c721d5347e31f6f728651d7724fd17ce27fd669a1a387540557d49dc416366"


def pinned(name, digest):
    path = HERE / name
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit(f"Frozen artifact changed: {name}")
    return path


def executable(case, result, *, resume):
    if not isinstance(result, dict) or result.get("status") != "planned":
        return False

    contract = case["contract"]
    catalog = {check["id"]: check for check in contract["checks"]}
    unavailable = set(case["unavailable"])
    evidence = set(case["passed"]) if resume else set()
    if resume and result.get("reused") != sorted(evidence):
        return False
    selected = result.get("checks")
    if not isinstance(selected, list) or not all(isinstance(key, str) for key in selected):
        return False
    if len(selected) != len(set(selected)) or not set(selected) <= catalog.keys() - unavailable - evidence:
        return False
    validated = evidence.union(selected)
    if not set(contract["mandatory"]) <= validated:
        return False
    covered = {need for check in validated for need in catalog[check]["covers"]}
    additional_cost = sum(catalog[check]["cost"] for check in selected)
    return (set(contract["obligations"]) <= covered
            and type(result.get("cost")) is int
            and result["cost"] == additional_cost <= contract["budget"])


def valid_block(result, expected, *, reused=None):
    if not isinstance(result, dict) or result.get("status") != "blocked" or result.get("checks") != []:
        return False
    if reused is not None and result.get("reused") != reused:
        return False
    return expected["status"] == "blocked"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--candidate-revision", required=True)
    args = parser.parse_args()
    candidate_path = args.candidate.resolve()
    evaluator = runpy.run_path(str(pinned("evaluate_replan.py", EVALUATOR_SHA256)))
    cases = json.loads(pinned("cases.json", CASES_SHA256).read_text(encoding="utf-8"))
    base = evaluator["frozen_file"]("base_plan_checks.py", evaluator["BASE_PLANNER_SHA256"])
    comparison = evaluator["frozen_file"]("base_improvement.py", evaluator["COMPARISON_SHA256"])
    api = runpy.run_path(str(comparison))

    cases_report = {}
    outcomes = []
    paired = {"cases": 0, "baseline_checks": 0, "candidate_checks": 0, "baseline_cost": 0, "candidate_cost": 0}
    for name, case in cases.items():
        expected = evaluator["oracle"](case)
        observed = {
            "baseline": evaluator["baseline_result"](base, case),
            "candidate": evaluator["run_script"](candidate_path, case, "--replan"),
        }
        reused = sorted(case["passed"])
        arm_evidence = {}
        for arm, result in observed.items():
            resume = arm == "candidate"
            evidence = reused if resume else None
            exact = evaluator["check_result"](result, expected, reused=evidence)
            outcomes.append(api["Outcome"](name, arm, exact))
            arm_evidence[arm] = {
                "executable": executable(case, result, resume=resume),
                "valid_blocker": valid_block(result, expected, reused=evidence),
                "oracle_match": exact,
                "result": result,
            }

        if all(row["executable"] for row in arm_evidence.values()):
            paired["cases"] += 1
            for arm, result in observed.items():
                paired[f"{arm}_checks"] += len(result["checks"])
                paired[f"{arm}_cost"] += result["cost"]
        cases_report[name] = {"oracle": dict(expected, reused=reused), **arm_evidence}

    comparison = api["compare"](outcomes, baseline_id="baseline", candidate_id="candidate")
    report = {
        "candidate_revision": args.candidate_revision,
        "candidate_planner_sha256": hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
        "g5": comparison.to_dict(),
        "soundness": {
            arm: {label: sum(row[arm][label] for row in cases_report.values())
                  for label in ("executable", "valid_blocker", "oracle_match")}
            for arm in ("baseline", "candidate")
        },
        "jointly_executable": paired,
        "cases": cases_report,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return int(comparison.verdict != "keep" or report["soundness"]["candidate"]["oracle_match"] != len(cases))


if __name__ == "__main__":
    raise SystemExit(main())
