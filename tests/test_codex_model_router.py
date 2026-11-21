import json
from pathlib import Path
import subprocess
import sys
import tempfile
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

    def test_catalog_uses_exposed_model_field_and_rejects_conflicting_entries(self):
        variant = dict(LUNA, model="account-visible-2026-11-18", id="catalog-card")
        self.assertIn(variant["model"], self.start(live=snapshot(variant)).exec_args)
        self.assert_blocked("BLOCKED_MODEL", self.start, live=snapshot(LUNA, variant))
        self.assert_blocked("BLOCKED_MODEL", self.start, live=snapshot(variant, dict(variant, hidden=True)))
        self.assert_blocked("BLOCKED_MODEL", self.start, live=snapshot(dict(variant, model="-override")))
        self.assert_blocked("BLOCKED_MODEL", self.start, live=snapshot(dict(variant, availabilityNux={"message": "no access"})))

    def test_catalog_accepts_the_hyphenated_app_server_label(self):
        visible = dict(SOL, displayName="GPT-6.2-Sol")
        self.assertEqual(self.start("coding", live=snapshot(visible)).attempt["model"], SOL["model"])

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

    def test_unknown_quota_bucket_cannot_hide_an_exhausted_limit(self):
        limits = quota()
        limits["rateLimitsByLimitId"] = {
            "codex": dict(limits["rateLimits"], limitName="Cosmetic name"),
            "unmapped": dict(quota(weekly=99)["rateLimits"], limitId="unmapped"),
        }
        self.assert_blocked("WAITING_QUOTA", self.start, live=snapshot(LUNA, limits=limits))
        limits["rateLimitsByLimitId"]["unmapped"]["secondary"]["usedPercent"] = 25
        self.assertEqual(self.start(live=snapshot(LUNA, limits=limits)).attempt["model"], LUNA["model"])
        limits["rateLimitsByLimitId"]["codex"]["spendControlReached"] = True
        self.assert_blocked("WAITING_QUOTA", self.start, live=snapshot(LUNA, limits=limits))

    def test_malformed_account_quota_and_checkpoint_are_classified(self):
        self.assert_blocked("BLOCKED_AUTH", self.start, live=snapshot(LUNA, plan=[]))
        self.assert_blocked("WAITING_QUOTA", self.start, live=snapshot(LUNA, observed_at="now"))
        plan = self.start()
        del plan.attempt["quota_before"]
        self.assert_blocked("BLOCKED_CHECKPOINT", self.finish, plan, "worker_error")

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

    def test_conflicting_terminal_events_do_not_supply_usage(self):
        plan = self.start()
        output = "\n".join((
            '{"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":0,"output_tokens":3}}',
            '{"type":"turn.failed","error":{"message":"secret"}}',
        ))
        attempt = self.finish(plan, "worker_error", exec_jsonl=output)["attempts"][0]
        self.assertIsNone(attempt["cli_usage"]["tokens"])
        self.assertIsNone(attempt["cli_usage"]["terminal_event"])
        self.assertNotIn("secret", json.dumps(attempt))

    def test_reported_effective_model_mismatch_stops_escalation(self):
        attempt = self.start("debug")
        state = self.finish(attempt, "tests_failed", test_evidence_sha256=VERDICT,
                            effective_settings={"model": "other-model", "effort": "low", "source_sha256": ARTIFACT})
        result = state["attempts"][0]
        self.assertEqual(result["status"], "worker_error")
        self.assertEqual(result["cli_usage"]["effective_settings"]["model"], "other-model")
        self.assert_blocked("ROUTE_FINISHED", self.start, state=state)

    def test_spliced_exec_is_released_only_after_checkpoint_and_resumes_without_relaunch(self):
        from local_codex import call as worker_call

        args = ["codex.exe", "-a", "never", "exec", "--ignore-user-config", "--ephemeral",
                "--sandbox", "workspace-write", "-c", "windows.sandbox=mxc", "-"]
        events = []
        with tempfile.TemporaryDirectory() as directory:
            def persist(state):
                temporary = saved.with_suffix(".tmp")
                temporary.write_text(json.dumps(state), encoding="utf-8")
                temporary.replace(saved)
                events.append("persist")

            def fake_exec(argv, **kwargs):
                self.assertEqual(argv[:len(args)-1], args[:-1])
                self.assertEqual(argv[-1], "-")
                current = json.loads(saved.read_text(encoding="utf-8"))["attempts"][-1]
                self.assertEqual(current["status"], "running")
                self.assertEqual(argv[argv.index("--model") + 1], current["model"])
                self.assertIn(f'model_reasoning_effort="{current["effort"]}"', argv)
                events.append((current["model"], current["effort"]))
                if kwargs["input"] == "interrupted":
                    raise subprocess.TimeoutExpired(argv, 1)
                return subprocess.CompletedProcess(argv, 0, '{"type":"turn.completed"}', "")

            with patch("local_codex.subprocess.run", side_effect=fake_exec) as calls:
                for task, profile, prompt in (("ONE", "routine", "answer"), ("TWO", "coding", "interrupted")):
                    saved = Path(directory) / f"{task}.json"
                    state = router.new_checkpoint(task, APPROVAL, profile)
                    plan, command = router.prepare_exec(args, state, APPROVAL, BASE,
                                                        snapshot(LUNA, SOL), persist)
                    if task == "ONE":
                        result = worker_call(command, input_text=prompt)
                        persist(self.finish(plan, "tests_passed", test_evidence_sha256=VERDICT,
                                            exec_jsonl=result.stdout))
                    else:
                        with self.assertRaises(subprocess.TimeoutExpired):
                            worker_call(command, input_text=prompt)
                        pending = json.loads(saved.read_text(encoding="utf-8"))
                        self.assert_blocked("RECONCILE_ATTEMPT", router.prepare_exec, args, pending,
                                            APPROVAL, BASE, snapshot(LUNA, SOL), persist)
                        persist(router.record_result(pending, APPROVAL, 1, "worker_error", duration_ms=1000))
                self.assertEqual(calls.call_count, 2)
            for task, status in (("ONE", "tests_passed"), ("TWO", "worker_error")):
                completed = json.loads((Path(directory) / f"{task}.json").read_text(encoding="utf-8"))
                self.assertEqual(completed["attempts"][0]["status"], status)
        self.assertEqual(events, ["persist", (LUNA["model"], "low"), "persist",
                                  "persist", (SOL["model"], "medium"), "persist"])

    def test_prepare_exec_refuses_competing_overrides_and_cannot_return_on_store_failure(self):
        state = router.new_checkpoint("ONE", APPROVAL, "routine")
        args = ["codex.exe", "exec", "--ignore-user-config"]
        persist = unittest.mock.Mock(side_effect=OSError("store unavailable"))
        for overrides in (["--model=alternate"], ["-c", 'service_tier="fast"'], ["--"], ["-pother"]):
            with self.subTest(overrides=overrides):
                self.assertRaises(ValueError, router.prepare_exec, [*args, *overrides, "-"],
                                  state, APPROVAL, BASE, snapshot(LUNA), persist)
        persist.assert_not_called()
        self.assertRaises(OSError, router.prepare_exec, [*args, "-"], state, APPROVAL, BASE,
                          snapshot(LUNA), persist)
        persist.assert_called_once()


class DiscoveryTests(unittest.TestCase):
    def read_from_child(self, before_catalog="pass"):
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
    if method == "model/list":
        {before_catalog}
    if "id" in msg:
        print(json.dumps({{"method": "metadata/notification"}}))
        print(json.dumps({{"id": msg["id"], "result": replies[method]}}))
"""
        spawn = subprocess.Popen

        def simulate(argv, **kwargs):
            self.assertEqual(argv, ["codex.exe", *router.STANDARD_CONFIG, "app-server"])
            return spawn([sys.executable, "-u", "-c", script], **kwargs)

        with patch.object(router.subprocess, "Popen", side_effect=simulate):
            return router.read_snapshot("codex.exe", ".", None)

    def test_ndjson_transport_with_a_local_child_process(self):
        result = self.read_from_child(
            'for _ in range(40): print(json.dumps({"method":"metadata/notification"}))')
        self.assertEqual(result.models, (LUNA,))
        self.assertEqual(result.limits, quota())

    def test_oversized_response_blocks_discovery_before_any_quota_use(self):
        with self.assertRaisesRegex(router.RouteBlocked, "size limit") as exc:
            self.read_from_child(
                'print(json.dumps({"method":"metadata/notification","params":"x" * (1024 * 1024)}))')
        self.assertEqual(exc.exception.status, "BLOCKED_MODEL")

    def test_non_object_json_rpc_frame_blocks_discovery(self):
        with self.assertRaisesRegex(router.RouteBlocked, "not a JSON object") as exc:
            self.read_from_child('print("[null]")')
        self.assertEqual(exc.exception.status, "BLOCKED_MODEL")

    def test_deep_json_frame_fails_closed_across_parsers(self):
        with self.assertRaises(router.RouteBlocked) as exc:
            self.read_from_child('print("[" * 3000 + "null" + "]" * 3000)')
        self.assertEqual(exc.exception.status, "BLOCKED_MODEL")

    @patch.object(router, "_app_server")
    def test_catalog_page_cannot_exceed_the_requested_entry_limit(self, mock_server):
        request = mock_server.return_value.__enter__.return_value
        request.side_effect = (
            {"account": {"type": "chatgpt", "planType": "plus"}},
            {"data": [LUNA] * 51, "nextCursor": None},
            quota(),
        )
        with self.assertRaises(router.RouteBlocked) as exc:
            router.read_snapshot("codex.exe", ".", {})
        self.assertEqual(exc.exception.status, "BLOCKED_MODEL")
        self.assertEqual(request.call_count, 2)

    @patch.object(router, "_app_server")
    def test_catalog_rejects_oversized_cursor_before_requesting_another_page(self, mock_server):
        request = mock_server.return_value.__enter__.return_value
        request.side_effect = (
            {"account": {"type": "chatgpt", "planType": "plus"}},
            {"data": [LUNA], "nextCursor": "a" * 8192},
            {"data": [], "nextCursor": None},
            quota(),
        )
        with self.assertRaisesRegex(router.RouteBlocked, "Invalid Codex catalog cursor"):
            router.read_snapshot("codex.exe", ".", {})
        self.assertEqual(request.call_count, 2)

    def test_metadata_deadline_stops_a_blocking_write_to_the_child(self):
        script = (
            "import json, sys, time\n"
            "msg = json.loads(sys.stdin.readline())\n"
            "print(json.dumps({'id': msg['id'], 'result': {}}), flush=True)\n"
            "time.sleep(2)\n"
        )
        spawn = subprocess.Popen
        initialized = False
        started = time.monotonic()
        with (
            patch.object(router, "METADATA_TIMEOUT_SECONDS", 0.5, create=True),
            patch.object(router.subprocess, "Popen",
                         side_effect=lambda argv, **kwargs: spawn([sys.executable, "-u", "-c", script], **kwargs)),
            self.assertRaises(router.RouteBlocked) as exc,
        ):
            with router._app_server("codex.exe", ".", None) as request:
                initialized = True
                request("model/list", {"cursor": "a" * (1024 * 1024)})
        self.assertTrue(initialized)
        self.assertEqual(exc.exception.status, "BLOCKED_MODEL")
        self.assertLess(time.monotonic() - started, 1.5)

    def test_metadata_teardown_does_not_wait_for_inherited_stdout(self):
        started = time.monotonic()
        result = self.read_from_child(
            'import subprocess; subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"])'
        )
        self.assertEqual(result.models, (LUNA,))
        self.assertLess(time.monotonic() - started, 1.5)

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
        self.assertEqual(request.call_args_list[2].args[1]["modelProvider"], "openai")

    @patch.object(router, "_app_server")
    def test_discovery_rejects_a_repeated_catalog_cursor_before_quota(self, mock_server):
        request = mock_server.return_value.__enter__.return_value
        request.side_effect = (
            {"account": {"type": "chatgpt", "planType": "plus"}},
            {"data": [LUNA], "nextCursor": "page-2"},
            {"data": [SOL], "nextCursor": "page-2"},
        )
        with self.assertRaises(router.RouteBlocked) as exc:
            router.read_snapshot("codex.exe", ".", {})
        self.assertEqual(exc.exception.status, "BLOCKED_MODEL")
        self.assertEqual(request.call_count, 3)

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
