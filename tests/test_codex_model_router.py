import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "agents" / "automation"))
from codex_model_router import (RoutingBlocked, check_quota, classify,
                                load_policy, model_catalog, select_route)

POLICY = load_policy()
MODELS = [
    {"id": m, "model": m, "hidden": False,
     "supportedReasoningEfforts": [{"reasoningEffort": e} for e in efforts]}
    for m, efforts in (("gpt-6-luna", ("low", "medium")),
                       ("gpt-6.2-sol", ("medium", "high")),
                       ("gpt-6.2-astra", ("high", "xhigh")))
]
PAGES = [{"data": MODELS, "nextCursor": None}]
QUOTA = {"credits": {"hasCredits": False, "unlimited": False},
         "rateLimitsByLimitId": {"codex": {"rateLimitReachedType": None,
            "primary": {"usedPercent": 12, "windowDurationMins": 300},
            "secondary": {"usedPercent": 31, "windowDurationMins": 10080}}}}


def proof(char):
    return {"verifier": "independent", "status": "FAIL", "tests_run": 3,
            "commit_sha": char * 40}


class RouterTests(unittest.TestCase):
    def route(self, mission, attempt=0, proofs=None, pages=PAGES, quota=QUOTA):
        return select_route(mission, pages, quota, attempt=attempt,
                            proofs=proofs, policy=POLICY, approved=True)[0]

    def test_luna_small_cli_argv(self):
        route = self.route({"id": "T1", "kind": "documentation"})
        self.assertEqual(route.cli_args(), ["--model", "gpt-6-luna", "-c", "model_reasoning_effort=low"])

    def test_sol_coding(self):
        route = self.route({"id": "T2", "kind": "code", "priority": "P1", "files": ["utils.py"]})
        self.assertEqual((route.model, route.effort), ("gpt-6.2-sol", "medium"))

    def test_sol_debugging(self):
        route = self.route({"id": "T2", "kind": "code", "priority": "P0", "files": ["utils.py"]})
        self.assertEqual((route.model, route.effort), ("gpt-6.2-sol", "high"))

    def test_astra_security(self):
        route = self.route({"id": "T2", "kind": "code", "files": ["scripts/agents/automation/local_coordination.py"]})
        self.assertEqual((route.model, route.effort), ("gpt-6.2-astra", "high"))

    def test_fallback_only_account_catalog(self):
        pages = [{"data": [MODELS[1]], "nextCursor": None}]
        self.assertEqual(self.route({"id": "T1"}, pages=pages).model, "gpt-6.2-sol")

    def test_fail_no_model(self):
        with self.assertRaisesRegex(RoutingBlocked, "BLOCKED_MODEL"):
            self.route({"id": "T2", "kind": "code"}, pages=[{"data": [MODELS[0]]}])

    def test_hidden_not_usable(self):
        with self.assertRaisesRegex(RoutingBlocked, "BLOCKED_MODEL"):
            self.route({"id": "T1"}, pages=[{"data": [{**MODELS[0], "hidden": True}]}])

    def test_absent_approval(self):
        with self.assertRaisesRegex(RoutingBlocked, "AWAITING_APPROVAL"):
            select_route({"id": "T1"}, PAGES, QUOTA, policy=POLICY)

    def test_high_effort_only_after_verified_failure(self):
        self.assertEqual(self.route({"id": "T1"}, attempt=1, proofs=[proof("a")]).tier, "escalated")
        self.assertEqual(self.route({"id": "T1"}, attempt=2,
                                    proofs=[proof("a"), proof("b")]).effort, "xhigh")

    def test_no_escalation_on_unverified_failure(self):
        with self.assertRaisesRegex(RoutingBlocked, "BLOCKED_ESCALATION"):
            self.route({"id": "T1"}, attempt=1, proofs=[{"status": "FAIL"}])

    def test_no_unlimited_retries(self):
        with self.assertRaisesRegex(RoutingBlocked, "BLOCKED_ESCALATION"):
            self.route({"id": "T1"}, attempt=3, proofs=[proof("a"), proof("b"), proof("c")])

    def test_quota_five_hour_limit(self):
        q = json.loads(json.dumps(QUOTA))
        q["rateLimitsByLimitId"]["codex"]["primary"]["usedPercent"] = 90
        with self.assertRaisesRegex(RoutingBlocked, "WAITING_QUOTA"):
            self.route({"id": "T1"}, quota=q)

    def test_quota_weekly_limit(self):
        q = json.loads(json.dumps(QUOTA))
        q["rateLimitsByLimitId"]["codex"]["secondary"]["usedPercent"] = 99
        with self.assertRaisesRegex(RoutingBlocked, "WAITING_QUOTA"):
            self.route({"id": "T1"}, quota=q)

    def test_quota_missing_week_or_credits(self):
        for malformed in ({"credits": QUOTA["credits"], "rateLimits": {"primary": QUOTA["rateLimitsByLimitId"]["codex"]["primary"]}},
                          {"rateLimitsByLimitId": QUOTA["rateLimitsByLimitId"]}):
            with self.subTest(malformed=malformed), self.assertRaisesRegex(RoutingBlocked, "WAITING_QUOTA"):
                self.route({"id": "T1"}, quota=malformed)

    def test_two_approved_sequential_plans_have_distinct_flags_and_quota(self):
        small, first = select_route({"id": "DOC"}, PAGES, QUOTA, policy=POLICY, approved=True)
        hard, second = select_route({"id": "CAS", "kind": "code", "files": ["security/auth.py"]},
                                    PAGES, QUOTA, policy=POLICY, approved=True)
        self.assertNotEqual(small.cli_args(), hard.cli_args())
        self.assertEqual(first, second)
        self.assertEqual(len(first["codex"]), 2)

    def test_fail_unknown_complexity(self):
        with self.assertRaisesRegex(RoutingBlocked, "BLOCKED_MISSION"):
            classify({"id": "T1", "complexity": "pay_more"})

    def test_model_catalog_duplicate(self):
        with self.assertRaisesRegex(RoutingBlocked, "BLOCKED_MODEL"):
            model_catalog([{"data": MODELS + [MODELS[0]]}])


if __name__ == "__main__":
    unittest.main()
