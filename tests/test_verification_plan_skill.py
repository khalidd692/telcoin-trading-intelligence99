"""Development examples for the verification planning Skill."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[1] / ".agents" / "skills"
          / "plan-verification" / "scripts" / "plan_checks.py")


def invoke(contract, exit_code=0):
    proc = subprocess.run([sys.executable, "-I", "-B", str(SCRIPT)],
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
