"""Development examples for the verification planning Skill."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[1] / ".agents" / "skills"
          / "plan-verification" / "scripts" / "plan_checks.py")


def invoke(contract, exit_code=0, *, replan=False):
    command = [sys.executable, "-I", "-B", str(SCRIPT)]
    if replan:
        command.append("--replan")
    proc = subprocess.run(command,
                          input=json.dumps(contract), text=True, capture_output=True, timeout=5)
    if proc.returncode != exit_code:
        raise AssertionError(f"exit {proc.returncode}: {proc.stderr}")
    return json.loads(proc.stdout)


def example():
    return {"budget": 5, "obligations": ["load", "resume"], "mandatory": ["policy"],
            "checks": [{"id": "load", "cost": 3, "covers": ["load"]},
                       {"id": "resume", "cost": 3, "covers": ["resume"]},
                       {"id": "combined", "cost": 4, "covers": ["load", "resume"]},
                       {"id": "policy", "cost": 1, "covers": []}]}


class VerificationPlanTests(unittest.TestCase):
    def test_preserves_required_policy_and_covers_both_obligations(self):
        plan = invoke(example())
        self.assertEqual((plan["status"], plan["cost"], plan["checks"]),
                         ("planned", 5, ["combined", "policy"]))

    def test_reports_minimum_cost_or_uncovered_obligation(self):
        case = example()
        case["budget"] = 4
        plan = invoke(case)
        self.assertEqual((plan["status"], plan["checks"], plan["minimum_cost"]),
                         ("blocked", [], 5))
        case["obligations"].append("restore")
        plan = invoke(case)
        self.assertEqual((plan["status"], plan["checks"], plan["uncovered"]),
                         ("blocked", [], ["restore"]))

    def test_equal_cost_prefers_fewer_checks_then_stable_ids(self):
        case = example()
        case["checks"].extend([{"id": "a-combined", "cost": 4, "covers": ["load", "resume"]},
                               {"id": "cheap-load", "cost": 1, "covers": ["load"]}])
        first = invoke(case)
        case["checks"].reverse()
        self.assertEqual(invoke(case), first)
        self.assertEqual(first["checks"], ["a-combined", "policy"])

    def test_invalid_catalog_is_distinct_from_an_impossible_plan(self):
        for edit in ({"mandatory": ["unknown"]}, {"budget": True}, {"obligations": ["load"] * 2},
                     {"checks": [{"id": "bad", "cost": 1, "covers": ["unknown"]}]}):
            with self.subTest(edit=edit):
                self.assertEqual(invoke(dict(example(), **edit), 2)["status"], "invalid")


class VerificationReplanTests(unittest.TestCase):
    def test_reuses_passes_and_selects_available_alternative(self):
        result = invoke({"contract": dict(example(), budget=3),
                         "passed": ["policy", "load"], "unavailable": ["combined"]}, replan=True)
        self.assertEqual(result, {"status": "planned", "checks": ["resume"], "cost": 3,
                                  "all_relevant_cost": 3, "reused": ["load", "policy"]})

    def test_all_criteria_covered_still_requires_policy_until_it_passes(self):
        request = {"contract": dict(example(), budget=0),
                   "passed": ["combined"], "unavailable": []}
        result = invoke(request, replan=True)
        self.assertEqual(result, {"status": "blocked", "checks": [], "minimum_cost": 1,
                                  "reused": ["combined"]})
        request["passed"].append("policy")
        result = invoke(request, replan=True)
        self.assertEqual(result, {"status": "planned", "checks": [], "cost": 0,
                                  "all_relevant_cost": 0, "reused": ["combined", "policy"]})

    def test_reports_unavailable_mandatory_or_uncovered(self):
        request = {"contract": example(), "passed": ["load"], "unavailable": ["policy"]}
        self.assertEqual(invoke(request, replan=True), {
            "status": "blocked", "checks": [], "unavailable_mandatory": ["policy"],
            "reused": ["load"],
        })
        request["unavailable"] = ["resume", "combined"]
        self.assertEqual(invoke(request, replan=True), {
            "status": "blocked", "checks": [], "uncovered": ["resume"], "reused": ["load"],
        })

    def test_rejects_invalid_history_and_catalog_even_for_excluded_checks(self):
        for passed, unavailable in ((["missing"], []), (["load", "load"], []),
                                    ([], ["missing"]), (["load"], ["load"])):
            with self.subTest(passed=passed, unavailable=unavailable):
                result = invoke({"contract": example(), "passed": passed,
                                 "unavailable": unavailable}, 2, replan=True)
                self.assertEqual(result["status"], "invalid")
        contract = example()
        contract["checks"][0]["cost"] = 0
        request = {"contract": contract, "passed": [], "unavailable": ["load"]}
        self.assertEqual(invoke(request, 2, replan=True)["status"], "invalid")
