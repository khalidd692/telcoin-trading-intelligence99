"""Offline tests for mission preparation with the existing router and protocol."""
import copy
import unittest

from scripts.agents.intelligence import capabilities
from scripts.agents.protocol import envelope


def contract(project="atlas-lab"):
    return {
        "project": project, "mission_id": "sample-1",
        "approved_models": ["openhands/deepseek-v4.1-flash"],
        "budget": {"max_calls": 3, "quota_remaining": 15, "reserve": 12,
                   "max_seconds": 30, "max_context_tokens": 4500},
        "steps": [
            {"role": "quant", "estimated_tokens": 1500, "estimated_seconds": 10},
            {"role": "development", "estimated_tokens": 1500, "estimated_seconds": 10},
            {"role": "quality", "estimated_tokens": 1500, "estimated_seconds": 10,
             "skills": ["plan-verification"]},
        ],
        "verification": {
            "budget": 5, "obligations": ["syntax", "behavior"], "mandatory": ["syntax"],
            "checks": [{"id": "syntax", "cost": 2, "covers": ["syntax"]},
                       {"id": "combined", "cost": 3, "covers": ["syntax", "behavior"]},
                       {"id": "behavior", "cost": 6, "covers": ["behavior"]}],
        },
    }


class MissionPlanTests(unittest.TestCase):
    def test_role_catalog_and_structured_chain(self):
        roles = capabilities.roles()
        self.assertEqual(len(roles), 12)
        self.assertEqual(sum(r["active"] for r in roles), 3)
        plan = capabilities.plan(contract())
        self.assertEqual(plan["status"], "PLANNED")
        self.assertEqual(plan["provider_status"], "PROVIDER_PENDING")
        self.assertEqual(plan["verification"]["checks"], ["combined", "syntax"])
        self.assertEqual([row["role"] for row in plan["steps"]], ["quant", "development", "quality"])
        handoffs = [row["handoff"] for row in plan["steps"]]
        self.assertTrue(all(not envelope.validate(row) for row in handoffs))
        self.assertEqual(handoffs[-1]["parent_envelope_id"], handoffs[-2]["envelope_id"])
        self.assertTrue(all(row["mission"]["read_only"] for row in handoffs))
        self.assertEqual(plan["provider_calls"], 0)

    def test_exhausted_quota_time_context_and_calls_have_explicit_codes(self):
        for field, value, code in (
            ("quota_remaining", 14, "QUOTA_RESERVE"),
            ("max_seconds", 29, "TIME_BUDGET"),
            ("max_context_tokens", 4499, "CONTEXT_BUDGET"),
            ("max_calls", 2, "CALL_BUDGET"),
        ):
            with self.subTest(field=field):
                payload = contract()
                payload["budget"][field] = value
                report = capabilities.plan(payload)
                self.assertEqual(report["status"], "BLOCKED")
                self.assertIn(code, report["codes"])
                self.assertEqual(report["steps"], [])

    def test_blocked_route_and_unapproved_skill(self):
        payload = contract()
        payload["approved_models"] = ["gpt-5.6"]
        self.assertEqual(capabilities.plan(payload)["codes"], ["MODEL_UNAVAILABLE"])
        payload = contract()
        payload["steps"][0]["skills"] = ["plan-verification"]
        with self.assertRaisesRegex(ValueError, "not allowed for role"):
            capabilities.plan(payload)
        payload = contract()
        payload["steps"][0]["tools"] = ["shell"]
        with self.assertRaises(ValueError):
            capabilities.plan(payload)

    def test_skill_budget_refuses_without_handoffs(self):
        payload = contract()
        payload["verification"]["budget"] = 4
        report = capabilities.plan(payload)
        self.assertEqual(report["codes"], ["VERIFICATION_UNAVAILABLE"])
        self.assertEqual(report["verification"]["minimum_cost"], 5)
        self.assertEqual(report["steps"], [])

    def test_context_window_and_confidentiality_refuse_cloud_route(self):
        payload = contract()
        payload["confidential"] = True
        result = capabilities.plan(payload)
        self.assertEqual(result["codes"], ["MODEL_UNAVAILABLE"])
        self.assertIn("confidential", str(result["routing"][0]["rejected"]))
        payload["confidential"] = False
        payload["budget"]["max_context_tokens"] = 500_000
        payload["steps"][0]["estimated_tokens"] = 130_000
        result = capabilities.plan(payload)
        self.assertEqual(result["codes"], ["MODEL_UNAVAILABLE"])
        self.assertIn("context exceeds", str(result["routing"][0]["rejected"]))

    def test_reserved_roles_can_be_planned_and_project_ids_are_isolated(self):
        payload = contract()
        payload["steps"] = [{"role": "documentation", "estimated_tokens": 200, "estimated_seconds": 1}]
        payload.pop("verification")
        plan = capabilities.plan(payload)
        self.assertEqual(plan["status"], "PLANNED")
        self.assertFalse(plan["steps"][0]["role_active"])
        copy_payload = copy.deepcopy(payload)
        copy_payload["project"] = "boreal-lab"
        other = capabilities.plan(copy_payload)
        self.assertNotEqual(plan["steps"][0]["handoff"]["envelope_id"],
                            other["steps"][0]["handoff"]["envelope_id"])
        self.assertEqual(plan["steps"][0]["handoff"]["envelope_id"],
                         capabilities.plan(payload)["steps"][0]["handoff"]["envelope_id"])
