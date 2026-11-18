import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

AUTOMATION = Path(__file__).resolve().parents[1] / "scripts" / "agents" / "automation"
sys.path.insert(0, str(AUTOMATION))
import codex_model_router as router

APPROVAL = "a" * 64
ARTIFACT = "b" * 64
VERDICT = "c" * 64
BASE = "d" * 40


def model(slug, name, *efforts, hidden=False):
    return {
        "model": slug, "displayName": name, "hidden": hidden,
        "supportedReasoningEfforts": [{"reasoningEffort": effort} for effort in efforts],
    }


LUNA = model("gpt-6-luna", "GPT-6 Luna", "low", "medium")
SOL = model("gpt-6.2-sol", "GPT-6.2 Sol", "low", "medium", "high")
ASTRA = model("gpt-6.2-astra", "GPT-6.2 Astra", "high", "xhigh")


def quota(five_hours=14, weekly=54):
    return {
        "rateLimits": {
            "limitId": "codex",
            "credits": {"hasCredits": False, "unlimited": False},
            "primary": {"windowDurationMins": 300, "usedPercent": five_hours, "resetsAt": 1900000000},
            "secondary": {"windowDurationMins": 10080, "usedPercent": weekly, "resetsAt": 1900400000},
        }
    }


def snapshot(*models, limits=None, observed_at=None, account_type="chatgpt", plan="plus"):
    return router.Snapshot(
        {"account": {"type": account_type, "planType": plan}},
        models, quota() if limits is None else limits,
        time.time() if observed_at is None else observed_at,
    )


class RouterTests(unittest.TestCase):
    def start(self, profile="routine", state=None, live=None, **options):
        if state is None:
            state = router.new_checkpoint("TASK-01", APPROVAL, profile)
        if live is None:
            live = snapshot(LUNA, SOL, ASTRA)
        return router.prepare_attempt(state, APPROVAL, BASE, live, **options)

    def finish(self, plan, status, **args):
        return router.record_result(
            plan.checkpoint, APPROVAL, plan.attempt["number"], status,
            duration_ms=530, artifact_sha256=ARTIFACT, **args,
        )

    def assert_blocked(self, status, fn, *args, **kwargs):
        with self.assertRaises(router.RouteBlocked) as exc:
            fn(*args, **kwargs)
        self.assertEqual(exc.exception.status, status)

    def test_profiles(self):
        for profile, slug, effort in (
            ("routine", LUNA["model"], "low"),
            ("coding", SOL["model"], "medium"),
            ("debug", SOL["model"], "high"),
            ("critical", ASTRA["model"], "high"),
        ):
            with self.subTest(profile=profile):
                plan = self.start(profile)
                self.assertEqual((plan.attempt["model"], plan.attempt["effort"]), (slug, effort))
                self.assertEqual(plan.attempt["reason"], "preferred")
                self.assertIn(slug, plan.exec_args)
                self.assertIn(f'model_reasoning_effort="{effort}"', plan.exec_args)

    def test_two_distinct_approved_tasks_are_planned_and_finished_in_order(self):
        seen = []
        for task, profile, expected in (
            ("TASK-01", "routine", "low"), ("TASK-02", "coding", "medium"),
        ):
            state = router.new_checkpoint(task, APPROVAL, profile)
            plan = self.start(state=state)
            persisted = json.loads(json.dumps(plan.checkpoint))
            self.assert_blocked("RECONCILE_ATTEMPT", self.start, state=persisted)
            seen.append(plan.attempt["effort"])
            self.assertEqual(plan.attempt["effort"], expected)
            finished = self.finish(plan, "tests_passed", test_evidence_sha256=VERDICT)
            self.assert_blocked("ROUTE_FINISHED", self.start, state=finished)
        self.assertEqual(seen, ["low", "medium"])

    def test_fallback_requires_visible_compatible_model_and_local_policy(self):
        decision = self.start(live=snapshot(dict(LUNA, hidden=True), SOL))
        self.assertEqual(decision.attempt["model"], SOL["model"])
        self.assertEqual(decision.attempt["reason"], "authorized_fallback")
        self.assert_blocked("BLOCKED_MODEL", self.start, "critical", live=snapshot(SOL))
        permitted = router.Policy(fallbacks={"critical": ("GPT-6.2 Sol",)})
        self.assertEqual(self.start("critical", live=snapshot(SOL), policy=permitted).attempt["effort"], "high")
        self.assert_blocked("BLOCKED_MODEL", self.start, "debug", live=snapshot(LUNA))
        self.assert_blocked("BLOCKED_MODEL", self.start, live=snapshot(dict(LUNA, model="gpt-6-luna-fast")))

    def test_confirmed_debug_failure_escalates_to_astra_then_extra_high(self):
        first = self.start("debug")
        self.assertRaises(ValueError, self.finish, first, "tests_failed")
        second = self.start(state=self.finish(first, "tests_failed", test_evidence_sha256=VERDICT))
        self.assertEqual((second.attempt["model"], second.attempt["effort"]), (ASTRA["model"], "high"))
        failed = self.finish(second, "tests_failed", test_evidence_sha256=VERDICT)
        self.assert_blocked("ROUTE_FINISHED", self.start, state=failed)
        third = self.start(state=failed, escalation_evidence_sha256=ARTIFACT)
        self.assertEqual(third.attempt["effort"], "xhigh")
        end = self.finish(third, "tests_failed", test_evidence_sha256=VERDICT)
        self.assert_blocked("ATTEMPT_LIMIT", self.start, state=end)

    def test_incompatible_extra_high_unknown_failure_and_small_task_do_not_retry(self):
        attempt = self.start("critical")
        failed = self.finish(attempt, "tests_failed", test_evidence_sha256=VERDICT)
        only_high = model(ASTRA["model"], ASTRA["displayName"], "high")
        self.assert_blocked("BLOCKED_MODEL", self.start, state=failed, live=snapshot(only_high),
                            escalation_evidence_sha256=ARTIFACT)
        stopped = self.finish(attempt, "worker_error")
        self.assert_blocked("ROUTE_FINISHED", self.start, state=stopped, escalation_evidence_sha256=ARTIFACT)
        simple_failure = self.finish(self.start(), "tests_failed", test_evidence_sha256=VERDICT)
        self.assert_blocked("ROUTE_FINISHED", self.start, state=simple_failure, escalation_evidence_sha256=ARTIFACT)
        self.assert_blocked("ATTEMPT_LIMIT", self.start, state=failed, policy=router.Policy(max_attempts=1))

    def test_quota_fails_closed_without_two_fresh_windows_and_no_credits(self):
        for limits in (
            quota(five_hours=90), quota(weekly=90), quota(weekly=True), quota(weekly=float("nan")),
            {"rateLimits": dict(quota()["rateLimits"], secondary=None)},
            {"rateLimits": dict(quota()["rateLimits"], credits=None)},
            {"rateLimits": dict(quota()["rateLimits"], credits={"hasCredits": True, "unlimited": False})},
            {"rateLimits": dict(quota()["rateLimits"], rateLimitReachedType="rate_limit_reached")},
        ):
            self.assert_blocked("WAITING_QUOTA", self.start, live=snapshot(LUNA, limits=limits))
        self.assert_blocked("WAITING_QUOTA", self.start, live=snapshot(LUNA, observed_at=time.time()-31))
        self.assert_blocked("BLOCKED_AUTH", self.start, live=snapshot(LUNA, account_type="apiKey"))
        self.assert_blocked("BLOCKED_AUTH", self.start, live=snapshot(LUNA, plan="enterprise_cbp_usage_based"))

    def test_matching_model_quota_is_checked_with_shared_quota(self):
        limits = quota()
        limits["rateLimitsByLimitId"] = {
            "luna": dict(quota(weekly=99)["rateLimits"], limitId="luna", normalModelSlug=LUNA["model"]),
        }
        self.assert_blocked("WAITING_QUOTA", self.start, live=snapshot(LUNA, SOL, limits=limits))
        self.assertEqual(self.start("coding", live=snapshot(SOL, limits=limits)).attempt["model"], SOL["model"])

    def test_checkpoint_binding_and_serialized_evidence(self):
        plan = self.start()
        self.assert_blocked("BLOCKED_CHECKPOINT", router.prepare_attempt,
                            plan.checkpoint, "e" * 64, BASE, snapshot(LUNA))
        self.assert_blocked("BLOCKED_CHECKPOINT", router.record_result, plan.checkpoint, APPROVAL, 2,
                            "worker_error", duration_ms=1)
        stdout = "\n".join(map(json.dumps, (
            {"type": "thread.started", "thread_id": "thread-1"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "sensitive"}},
            {"type": "turn.completed", "usage": {"input_tokens": 90, "cached_input_tokens": 10, "output_tokens": 20}},
        )))
        before_time = plan.attempt["quota_before"]["observed_at"]
        after = snapshot(LUNA, limits=quota(16, 56), observed_at=before_time + 1)
        with patch.object(router.time, "time", return_value=before_time + 2):
            persisted = self.finish(plan, "tests_passed", test_evidence_sha256=VERDICT,
                                    quota_after=after, exec_jsonl=stdout)
        evidence = persisted["attempts"][0]
        self.assertEqual(evidence["quota_before"]["limits"]["codex"][0]["used_percent"], 14)
        self.assertEqual(evidence["quota_after"]["limits"]["codex"][0]["used_percent"], 16)
        self.assertEqual(evidence["cli_usage"]["tokens"]["output_tokens"], 20)
        self.assertIsNone(evidence["cli_usage"]["effective_settings"])
        self.assertNotIn("sensitive", json.dumps(persisted))
        self.assertEqual(plan.attempt["status"], "running")

    def test_missing_independent_evidence_and_unreadable_usage(self):
        attempt = self.start()
        with self.assertRaises(ValueError):
            self.finish(attempt, "tests_passed")
        state = self.finish(attempt, "worker_error", exec_jsonl='{"type":"turn.completed"}')
        evidence = state["attempts"][0]
        self.assertIsNone(evidence["quota_after"])
        self.assertIsNone(evidence["cli_usage"]["tokens"])

    def test_reported_effective_model_mismatch_stops_escalation(self):
        attempt = self.start("debug")
        state = self.finish(attempt, "tests_failed", test_evidence_sha256=VERDICT,
                            effective_settings={"model": "other-model", "effort": "low", "source_sha256": ARTIFACT})
        result = state["attempts"][0]
        self.assertEqual(result["status"], "worker_error")
        self.assertEqual(result["cli_usage"]["effective_settings"]["model"], "other-model")
        self.assert_blocked("ROUTE_FINISHED", self.start, state=state)


class DiscoveryTests(unittest.TestCase):
    def test_ndjson_transport_with_a_local_child_process(self):
        replies = {
            "initialize": {},
            "account/read": {"account": {"type": "chatgpt", "planType": "plus"}},
            "model/list": {"data": [LUNA], "nextCursor": None},
            "account/rateLimits/read": quota(),
        }
        script = f"""
import json
import sys
replies = {replies!r}
expected = iter(("initialize", "initialized", "account/read", "model/list", "account/rateLimits/read"))
for line in sys.stdin:
    msg = json.loads(line)
    method = msg["method"]
    assert method == next(expected), method
    if "id" in msg:
        print(json.dumps({{"method": "metadata/notification"}}))
        print(json.dumps({{"id": msg["id"], "result": replies[method]}}))
"""
        spawn = subprocess.Popen

        def simulate(argv, **kwargs):
            self.assertEqual(argv, ["codex.exe", *router.STANDARD_CONFIG, "app-server"])
            return spawn([sys.executable, "-u", "-c", script], **kwargs)

        with patch.object(router.subprocess, "Popen", side_effect=simulate):
            result = router.read_snapshot("codex.exe", ".", None)
        self.assertEqual(result.models, (LUNA,))
        self.assertEqual(result.limits, quota())

    @patch.object(router, "_app_server")
    def test_metadata_only_discovery_paginates_then_reads_quota(self, mock_server):
        request = mock_server.return_value.__enter__.return_value
        request.side_effect = (
            {"account": {"type": "chatgpt", "planType": "plus"}},
            {"data": [LUNA], "nextCursor": "page-2"},
            {"data": [SOL], "nextCursor": None},
            quota(),
        )
        result = router.read_snapshot("codex.exe", ".", {})
        self.assertEqual([m["model"] for m in result.models], [LUNA["model"], SOL["model"]])
        self.assertEqual([call.args[0] for call in request.call_args_list], [
            "account/read", "model/list", "model/list", "account/rateLimits/read",
        ])
        self.assertEqual(request.call_args_list[2].args[1]["cursor"], "page-2")

    @patch.object(router, "_app_server")
    def test_discovery_stops_before_catalog_when_account_is_api_key(self, mock_server):
        request = mock_server.return_value.__enter__.return_value
        request.return_value = {"account": {"type": "apiKey"}}
        with self.assertRaises(router.RouteBlocked) as exc:
            router.read_snapshot("codex.exe", ".", {})
        self.assertEqual(exc.exception.status, "BLOCKED_AUTH")
        request.assert_called_once_with("account/read", {"refreshToken": False})


if __name__ == "__main__":
    unittest.main()
