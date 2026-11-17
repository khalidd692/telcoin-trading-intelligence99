"""Deterministic tests for the TEL99 cloud-autonomy plugin.

Stdlib-only: no OpenHands SDK, no network, no agent server. Everything here runs
in CI. The tests cover:

  * the plugin manifest is valid and pins one mission at a time;
  * mission selection only accepts authorised, labelled, open issues;
  * preconditions refuse protected branches, foreign repos and low quota;
  * the orchestrator reuses the existing team (terminal-only, guard, contract);
  * the guard blocks forbidden commands and allows read-only ones;
  * the runtime verifier fails when a sub-agent is not restricted.

Run:
    python -m unittest discover -s tests -p 'test_cloud_autonomy*.py' -v
"""

import importlib.util
import io
import json
import os
import pathlib
import subprocess
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
AUTOMATION = ROOT / "scripts" / "agents" / "automation"
GUARD = ROOT / "scripts" / "agents" / "guard" / "guard.py"
PLUGIN = ROOT / ".plugin" / "plugin.json"
CONFIG = ROOT / "scripts" / "agents" / "automation" / "automation.config.json"


def _load(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


policy = _load("tel99_automation_policy", AUTOMATION / "policy.py")
verify_runtime = _load("tel99_verify_runtime", AUTOMATION / "verify_runtime.py")
preflight = _load("tel99_preflight", AUTOMATION / "preflight.py")
orchestrator = _load("tel99_orchestrator", AUTOMATION / "orchestrator.py")
team_config = _load("tel99_team_config", ROOT / "scripts" / "agents" / "team_config.py")
emergency = _load("tel99_emergency", AUTOMATION / "emergency.py")


def run_guard(command, tool_name="terminal"):
    event = {"tool_name": tool_name, "tool_input": {"command": command}}
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(event).encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.returncode


def issue(number, title="t", labels=("tel99-mission",), created="2026-11-01T00:00:00Z",
          state="open", pull_request=False):
    payload = {
        "number": number,
        "title": title,
        "body": "b",
        "state": state,
        "created_at": created,
        "labels": [{"name": l} for l in labels],
    }
    if pull_request:
        payload["pull_request"] = {"url": "x"}
    return payload


class PluginManifestTests(unittest.TestCase):
    def test_manifest_is_valid_json(self):
        data = json.loads(PLUGIN.read_text(encoding="utf-8"))
        self.assertEqual(data["automation"]["schema_version"],
                         "openhands.automation.plugin.v1")

    def test_entrypoint_is_a_script_runner(self):
        data = json.loads(PLUGIN.read_text(encoding="utf-8"))
        entry = data["automation"]["entrypoint"]
        self.assertEqual(entry["runner"], "script")
        self.assertIn("orchestrator.py", entry["command"])

    def test_entrypoint_has_no_shell_metacharacters(self):
        # The plugin schema rejects ;&|`$(){}<>!\ in entrypoint.command.
        data = json.loads(PLUGIN.read_text(encoding="utf-8"))
        command = data["automation"]["entrypoint"]["command"]
        for ch in ';&|`$(){}<>!\\"':
            self.assertNotIn(ch, command, f"metacharacter {ch!r} in entrypoint")

    def test_schema_pins_one_mission_at_a_time(self):
        data = json.loads(PLUGIN.read_text(encoding="utf-8"))
        prop = data["automation"]["config_schema"]["properties"]["max_concurrent_missions"]
        self.assertEqual(prop["maximum"], 1)
        self.assertEqual(prop["default"], 1)

    def test_dry_run_defaults_to_true(self):
        data = json.loads(PLUGIN.read_text(encoding="utf-8"))
        prop = data["automation"]["config_schema"]["properties"]["dry_run"]
        self.assertTrue(prop["default"])

    def test_no_free_model_is_used(self):
        data = json.loads(PLUGIN.read_text(encoding="utf-8"))
        profile = data["automation"]["runtime"]["llm_profile"]["default_name"]
        self.assertEqual(profile, "openhands_deepseek-v4.1-flash")

    def test_shipped_automation_config_matches_the_plugin_schema(self):
        """The config we hand the operator must be accepted by the plugin schema.

        ``additionalProperties`` is false, so a stray key (e.g. a ``_comment``)
        would make the platform reject the config. This test uses a real JSON
        Schema validator when available and otherwise checks the two rules that
        matter here: no unknown keys and all required keys present.
        """
        plugin = json.loads(PLUGIN.read_text(encoding="utf-8"))
        schema = plugin["automation"]["config_schema"]
        config = json.loads(CONFIG.read_text(encoding="utf-8"))

        try:
            import jsonschema  # noqa: PLC0415 - optional dependency
        except ImportError:
            jsonschema = None

        if jsonschema is not None:
            jsonschema.validate(config, schema)
            return

        properties = set(schema.get("properties", {}))
        unknown = set(config) - properties
        self.assertEqual(unknown, set(), f"unknown keys rejected by schema: {unknown}")
        missing = set(schema.get("required", [])) - set(config)
        self.assertEqual(missing, set(), f"missing required keys: {missing}")

    def test_shipped_automation_config_has_no_comment_key(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertNotIn("_comment", config)

    def test_suggested_trigger_is_a_deliverable_event(self):
        """The trigger must be an event the platform actually delivers.

        The deployment lists its deliverable GitHub event types; ``repository_dispatch``
        is not among them, so a trigger on it would never fire. The manifest must
        suggest an event from that delivered set (``issues.labeled`` for a mission).
        """
        data = json.loads(PLUGIN.read_text(encoding="utf-8"))
        trigger = data["automation"]["suggested_trigger_template"]
        self.assertEqual(trigger["type"], "event")
        self.assertEqual(trigger["source"], "github")
        self.assertEqual(trigger["on"], "issues.labeled")
        self.assertNotIn("suggested_trigger", data["automation"])
        self.assertIn("mission_label", trigger["filter"])


class MissionSelectionTests(unittest.TestCase):
    def test_only_labelled_issues_are_eligible(self):
        issues = [
            issue(1, labels=("bug",)),
            issue(2, labels=("tel99-mission",)),
        ]
        chosen = policy.select_mission(issues, "tel99-mission")
        self.assertEqual(chosen["number"], 2)

    def test_pull_requests_are_never_missions(self):
        issues = [issue(3, labels=("tel99-mission",), pull_request=True)]
        self.assertIsNone(policy.select_mission(issues, "tel99-mission"))

    def test_closed_issues_are_ignored(self):
        issues = [issue(4, labels=("tel99-mission",), state="closed")]
        self.assertIsNone(policy.select_mission(issues, "tel99-mission"))

    def test_processed_issues_are_not_re_selected(self):
        issues = [issue(5, labels=("tel99-mission",))]
        self.assertIsNone(policy.select_mission(issues, "tel99-mission", {5}))

    def test_selection_is_deterministic_oldest_first(self):
        issues = [
            issue(9, created="2026-11-02T00:00:00Z"),
            issue(7, created="2026-11-01T00:00:00Z"),
        ]
        chosen = policy.select_mission(issues, "tel99-mission")
        self.assertEqual(chosen["number"], 7)

    def test_unlabelled_queue_yields_nothing(self):
        issues = [issue(1, labels=("enhancement",)), issue(2, labels=())]
        self.assertIsNone(policy.select_mission(issues, "tel99-mission"))


class PreconditionTests(unittest.TestCase):
    def _go(self, **overrides):
        base = dict(
            repository="khalidd692/telcoin-trading-intelligence99",
            base_branch="agents/hermes-simple-team-20261114",
            work_branch="agent/mission-12-fix",
            quota_remaining=10,
            quota_min_remaining=2,
            active_missions=0,
            max_concurrent_missions=1,
            dry_run=True,
        )
        base.update(overrides)
        return policy.evaluate_preconditions(**base)

    def test_clean_configuration_has_no_reasons(self):
        self.assertEqual(self._go(), [])

    def test_foreign_repository_is_refused(self):
        self.assertTrue(self._go(repository="attacker/repo"))

    def test_protected_base_branch_is_refused(self):
        self.assertTrue(self._go(base_branch="main"))
        self.assertTrue(self._go(base_branch="tel99-live-data"))

    def test_protected_work_branch_is_refused(self):
        self.assertTrue(self._go(work_branch="tel99-live-data"))

    def test_work_branch_equal_to_base_is_refused(self):
        self.assertTrue(self._go(work_branch="agents/hermes-simple-team-20261114"))

    def test_low_quota_is_refused(self):
        self.assertTrue(self._go(quota_remaining=1, quota_min_remaining=2))

    def test_second_active_mission_is_refused(self):
        self.assertTrue(self._go(active_missions=1))

    def test_concurrency_above_cap_is_refused(self):
        self.assertTrue(self._go(max_concurrent_missions=3))

    def test_unknown_quota_is_refused_for_a_real_run(self):
        # Fail-closed: an unknown quota must block a real mission.
        self.assertTrue(self._go(quota_remaining=None, dry_run=False))

    def test_unknown_quota_does_not_block_a_dry_run(self):
        # A dry run starts no conversation, so it may rehearse the selection.
        self.assertEqual(self._go(quota_remaining=None, dry_run=True), [])

    def test_absent_quota_key_is_refused(self):
        # quota_remaining() returns None when the API is unreachable, the key
        # is missing, or the response has no "remaining" field.
        self.assertTrue(self._go(quota_remaining=None, dry_run=False))


class WorkBranchTests(unittest.TestCase):
    def test_branch_name_is_deterministic(self):
        a = policy.work_branch_name("agent/mission-", 12, "Fix the widget")
        b = policy.work_branch_name("agent/mission-", 12, "Fix the widget")
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("agent/mission-12"))

    def test_branch_name_refuses_protected_result(self):
        with self.assertRaises(ValueError):
            policy.work_branch_name("tel99-", 12, "x")

    def test_branch_name_is_slugged(self):
        name = policy.work_branch_name("agent/mission-", 3, "A/b c:d!")
        self.assertNotIn("/", name.replace("agent/mission-", "", 1))
        self.assertNotIn("!", name)


class OrchestratorReuseTests(unittest.TestCase):
    """The orchestrator must reuse the existing team, not re-implement it."""

    @classmethod
    def setUpClass(cls):
        cls.orch = _load("tel99_orchestrator", AUTOMATION / "orchestrator.py")

    def test_payload_has_three_agents_with_suffixed_names(self):
        cfg = dict(self.orch.DEFAULT_CONFIG)
        payload = self.orch.build_payload(
            issue(12), "agent/mission-12-fix", cfg, {"model": "m"}
        )
        names = [d["name"] for d in payload["agent_definitions"]]
        self.assertEqual(len(names), 3)
        self.assertEqual(len(set(names)), 3)

    def test_agents_are_terminal_only_with_guard(self):
        cfg = dict(self.orch.DEFAULT_CONFIG)
        payload = self.orch.build_payload(
            issue(12), "agent/mission-12-fix", cfg, {"model": "m"}
        )
        for definition in payload["agent_definitions"]:
            self.assertEqual(definition["tools"], ["terminal"])
            self.assertTrue(definition["hooks"]["pre_tool_use"])
            self.assertIn("LECTURE SEULE", definition["system_prompt"])

    def test_parent_delegation_is_scoped(self):
        cfg = dict(self.orch.DEFAULT_CONFIG)
        payload = self.orch.build_payload(
            issue(12), "agent/mission-12-fix", cfg, {"model": "m"}
        )
        names = [t["name"] for t in payload["agent"]["tools"]]
        self.assertIn("task_tool_set", names)
        self.assertIn("terminal", names)
        self.assertNotIn("file_editor", names)

    def test_payload_carries_the_mission_issue(self):
        cfg = dict(self.orch.DEFAULT_CONFIG)
        payload = self.orch.build_payload(
            issue(12, title="Fix"), "agent/mission-12-fix", cfg, {"model": "m"}
        )
        text = payload["initial_message"]["content"][0]["text"]
        self.assertIn("#12", text)

    def test_budgets_come_from_config(self):
        cfg = dict(self.orch.DEFAULT_CONFIG)
        cfg["agent_max_budget_usd"] = 0.1
        payload = self.orch.build_payload(
            issue(12), "agent/mission-12-fix", cfg, {"model": "m"}
        )
        for definition in payload["agent_definitions"]:
            self.assertEqual(definition["max_budget_per_run"], 0.1)


class GuardBehaviourTests(unittest.TestCase):
    BLOCKED = [
        "rm -rf /tmp/x",
        "git push origin main",
        "git checkout main",
        "git commit -m x",
        "pip install requests",
        "curl -X POST https://example.com",
        "wget https://example.com/x",
        "python3 -c \"open('/tmp/f','w').write('x')\"",
        "kraken order buy TELUSD",
        "sudo rm -rf /",
        "bash -c 'git push'",
    ]
    ALLOWED = [
        "ls -la",
        "git status",
        "git log --oneline -3",
        "git rev-parse HEAD",
        "cat AGENTS.md",
        "grep -rn TODO src",
    ]

    def test_forbidden_commands_are_blocked(self):
        for command in self.BLOCKED:
            with self.subTest(command=command):
                self.assertEqual(run_guard(command), 2, command)

    def test_read_only_commands_are_allowed(self):
        for command in self.ALLOWED:
            with self.subTest(command=command):
                self.assertEqual(run_guard(command), 0, command)

    def test_verifier_sample_matches_the_guard(self):
        self.assertEqual(verify_runtime.guard_behaviour_ok(), [])


class RuntimeVerifierTests(unittest.TestCase):
    def _write_subagent(self, root, name, tools, hooks, policy_kind):
        sub = root / "subagents" / name
        sub.mkdir(parents=True)
        state = {
            "agent": {"tools": tools},
            "confirmation_policy": {"kind": policy_kind},
            "hook_config": hooks,
        }
        (sub / "base_state.json").write_text(json.dumps(state), encoding="utf-8")

    def _conversation(self, tmp, subagents):
        import tempfile
        data_dir = pathlib.Path(tempfile.mkdtemp(dir=tmp))
        conv = data_dir / "abc123"
        (conv / "subagents").mkdir(parents=True)
        (conv / "meta.json").write_text(
            json.dumps({"agent_definitions": [{"name": n} for n, *_ in subagents]}),
            encoding="utf-8",
        )
        for name, tools, hooks, policy_kind in subagents:
            self._write_subagent(conv, name, tools, hooks, policy_kind)
        return str(data_dir)

    def test_pass_on_compliant_state(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = self._conversation(
                tmp,
                [("tel99-dev-120000", ["terminal"], {"pre_tool_use": [{}]}, "ConfirmRisky")],
            )
            rc = verify_runtime.verify("abc123", data_dir, "120000")
            self.assertEqual(rc, 0)

    def test_fail_on_non_terminal_tools(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = self._conversation(
                tmp,
                [("tel99-dev-120000", ["terminal", "file_editor"],
                  {"pre_tool_use": [{}]}, "ConfirmRisky")],
            )
            self.assertEqual(verify_runtime.verify("abc123", data_dir, "120000"), 1)

    def test_fail_when_guard_missing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = self._conversation(
                tmp,
                [("tel99-dev-120000", ["terminal"], {}, "ConfirmRisky")],
            )
            self.assertEqual(verify_runtime.verify("abc123", data_dir, "120000"), 1)

    def test_fail_when_no_subagent_state(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = pathlib.Path(tmp) / "data"
            (data_dir / "abc123").mkdir(parents=True)
            self.assertEqual(verify_runtime.verify("abc123", str(data_dir), None), 1)


class CallbackTests(unittest.TestCase):
    """The script runner does not complete a run by itself: prove the callback."""

    def test_fire_callback_posts_completed_to_the_service(self):
        import http.server
        import threading

        received = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                received["body"] = json.loads(self.rfile.read(length))
                received["auth"] = self.headers.get("Authorization")
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        env = dict(os.environ)
        env["AUTOMATION_CALLBACK_URL"] = f"http://127.0.0.1:{server.server_port}/cb"
        env["AUTOMATION_CALLBACK_API_KEY"] = "k"
        env["AUTOMATION_RUN_ID"] = "run-1"
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys;sys.path.insert(0,'%s');import orchestrator;"
             "orchestrator.fire_callback('COMPLETED')" % AUTOMATION],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        thread.join(timeout=5)
        server.server_close()
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())
        self.assertEqual(received.get("body", {}).get("status"), "COMPLETED")
        self.assertEqual(received.get("body", {}).get("run_id"), "run-1")
        self.assertEqual(received.get("auth"), "Bearer k")

    def test_fire_callback_is_a_noop_without_a_url(self):
        env = {k: v for k, v in os.environ.items() if k != "AUTOMATION_CALLBACK_URL"}
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys;sys.path.insert(0,'%s');import orchestrator;"
             "orchestrator.fire_callback('COMPLETED')" % AUTOMATION],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())


class PreflightTests(unittest.TestCase):
    """Fail-closed preflight: the run must refuse unless safety is provable."""

    def test_guard_is_detected_active_on_the_real_repository(self):
        self.assertEqual(preflight.check_guard_active(), [])

    def test_team_config_is_valid_and_terminal_only(self):
        self.assertEqual(preflight.check_team_config(), [])

    def test_preflight_reports_a_missing_guard(self):
        original = preflight.GUARD
        try:
            preflight.GUARD = pathlib.Path("/nonexistent/guard.py")
            problems = preflight.check_guard_active()
        finally:
            preflight.GUARD = original
        self.assertTrue(any("missing" in p for p in problems))

    def test_preflight_flags_a_weakened_guard(self):
        # A guard that lets a forbidden command through must be reported.
        original = preflight._run_guard
        try:
            preflight._run_guard = lambda command: 0
            problems = preflight.check_guard_active()
        finally:
            preflight._run_guard = original
        self.assertTrue(any("did not block" in p for p in problems))

    def test_payload_must_declare_three_restricted_agents(self):
        good = {
            "agent": {"tools": [{"name": "task_tool_set"}, {"name": "terminal"}]},
            "agent_definitions": [
                {"name": f"a{i}", "tools": ["terminal"],
                 "hooks": {"pre_tool_use": [1]}, "permission_mode": "confirm_risky"}
                for i in range(3)
            ],
        }
        self.assertEqual(preflight.check_payload(good), [])

    def test_payload_with_a_widened_agent_is_rejected(self):
        bad = {
            "agent": {"tools": [{"name": "task_tool_set"}, {"name": "terminal"}]},
            "agent_definitions": [
                {"name": "a0", "tools": ["terminal"],
                 "hooks": {"pre_tool_use": [1]}, "permission_mode": "confirm_risky"},
                {"name": "a1", "tools": ["terminal", "file_editor"],
                 "hooks": {"pre_tool_use": [1]}, "permission_mode": "confirm_risky"},
                {"name": "a2", "tools": ["terminal"],
                 "hooks": {"pre_tool_use": [1]}, "permission_mode": "confirm_risky"},
            ],
        }
        problems = preflight.check_payload(bad)
        self.assertTrue(any("terminal-only" in p for p in problems))

    def test_payload_without_a_guard_hook_is_rejected(self):
        bad = {
            "agent": {"tools": [{"name": "task_tool_set"}, {"name": "terminal"}]},
            "agent_definitions": [
                {"name": "a0", "tools": ["terminal"],
                 "permission_mode": "confirm_risky"} for _ in range(3)
            ],
        }
        problems = preflight.check_payload(bad)
        self.assertTrue(any("guard hook not declared" in p for p in problems))

    def test_real_payload_from_team_config_passes_preflight(self):
        mission = {"number": 1, "title": "t", "body": "b"}
        payload = orchestrator.build_payload(
            mission, "agent/mission-1", orchestrator.DEFAULT_CONFIG, {"model": "m"}
        )
        self.assertEqual(preflight.check_payload(payload), [])

    def test_free_model_is_accepted(self):
        payload = {"agent": {"llm": {"model": "openhands/deepseek-v4.1-flash"}}}
        self.assertEqual(preflight.check_model(payload), [])

    def test_a_paid_or_unknown_model_is_refused(self):
        """No-spend: the server default gpt-5.6 (unknown cost) must be refused."""
        payload = {"agent": {"llm": {"model": "gpt-5.6"}}}
        problems = preflight.check_model(payload)
        self.assertTrue(any("not on the free allowlist" in p for p in problems))

    def test_a_payload_without_a_model_is_refused(self):
        self.assertTrue(preflight.check_model({"agent": {}}))

    def test_team_config_refuses_a_paid_model_override(self):
        """An env override to a paid model must make validate() fail loudly."""
        original = team_config.DEFAULT_MODEL
        try:
            team_config.DEFAULT_MODEL = "gpt-5.6"
            with self.assertRaises(ValueError):
                team_config.validate()
        finally:
            team_config.DEFAULT_MODEL = original

    def test_real_payload_from_team_config_uses_the_free_model(self):
        mission = {"number": 1, "title": "t", "body": "b"}
        payload = orchestrator.build_payload(
            mission, "agent/mission-1", orchestrator.DEFAULT_CONFIG,
            {"model": team_config.DEFAULT_MODEL},
        )
        self.assertEqual(preflight.check_model(payload), [])


class LockTests(unittest.TestCase):
    """The single-mission lock must be atomic across distinct cloud runs."""

    def test_lock_uses_a_conditional_create(self):
        """From an empty key the lock is taken with a conditional (nx) write."""
        calls = []
        store = {}

        def fake_request(method, url, payload=None, headers=None, timeout=60):
            calls.append((method, url, payload))
            if method == "GET":
                return 404, "missing"
            if method == "PUT":
                store["lock"] = payload
                return 201, {}
            return 200, {}

        original_req = orchestrator._request
        original_avail = orchestrator.kv_available
        try:
            orchestrator._request = fake_request
            orchestrator.kv_available = lambda: True
            acquired, detail = orchestrator.acquire_lock("run-a")
        finally:
            orchestrator._request = original_req
            orchestrator.kv_available = original_avail
        self.assertTrue(acquired, detail)
        puts = [c for c in calls if c[0] == "PUT"]
        self.assertTrue(puts)
        self.assertIn("nx=true", puts[0][1])
        self.assertEqual(store["lock"]["owner"], "run-a")

    def test_second_run_cannot_take_a_held_lock(self):
        original_meta = orchestrator.kv_get_meta
        original_avail = orchestrator.kv_available
        try:
            orchestrator.kv_available = lambda: True
            orchestrator.kv_get_meta = lambda key: (
                {"owner": "run-a", "expires_at": "2999-01-01T00:00:00Z"}, 1)
            acquired, detail = orchestrator.acquire_lock("run-b")
        finally:
            orchestrator.kv_get_meta = original_meta
            orchestrator.kv_available = original_avail
        self.assertFalse(acquired)
        self.assertIn("run-a", detail)

    def test_lock_refuses_when_no_atomic_kv_is_available(self):
        # Fail-closed: without an atomic KV lock a real mission must not start.
        original = orchestrator.kv_available
        try:
            orchestrator.kv_available = lambda: False
            acquired, detail = orchestrator.acquire_lock("run-a")
        finally:
            orchestrator.kv_available = original
        self.assertFalse(acquired)
        self.assertIn("atomic KV", detail)

    def test_an_expired_lock_can_be_retaken(self):
        """An expired record is overwritten with a versioned (CAS) write."""
        puts = []

        def fake_request(method, url, payload=None, headers=None, timeout=60):
            if method == "GET":
                return 200, {"value": {"owner": "run-a",
                                       "expires_at": "2000-01-01T00:00:00Z"},
                             "version": 7}
            puts.append(url)
            return 201, {}

        original_req = orchestrator._request
        original_avail = orchestrator.kv_available
        try:
            orchestrator.kv_available = lambda: True
            orchestrator._request = fake_request
            acquired, detail = orchestrator.acquire_lock("run-b")
        finally:
            orchestrator.kv_available = original_avail
            orchestrator._request = original_req
        self.assertTrue(acquired, detail)
        self.assertTrue(puts)
        self.assertIn("if_version=7", puts[0])


class QuotaTests(unittest.TestCase):
    """quota_remaining() must return None (not a guess) when unverifiable."""

    def test_missing_api_key_returns_none(self):
        saved = dict(orchestrator.os.environ)
        try:
            orchestrator.os.environ.pop("OPENHANDS_API_KEY", None)
            orchestrator.os.environ.pop("TEL99_CLOUD_API_KEY", None)
            self.assertIsNone(orchestrator.quota_remaining())
        finally:
            orchestrator.os.environ.clear()
            orchestrator.os.environ.update(saved)

    def test_unreachable_api_returns_none(self):
        original_req = orchestrator._request
        saved = dict(orchestrator.os.environ)
        try:
            orchestrator.os.environ["OPENHANDS_API_KEY"] = "x"
            orchestrator._request = lambda *a, **k: (503, {"detail": "down"})
            self.assertIsNone(orchestrator.quota_remaining())
        finally:
            orchestrator._request = original_req
            orchestrator.os.environ.clear()
            orchestrator.os.environ.update(saved)

    def test_response_without_remaining_field_returns_none(self):
        original_req = orchestrator._request
        saved = dict(orchestrator.os.environ)
        try:
            orchestrator.os.environ["OPENHANDS_API_KEY"] = "x"
            orchestrator._request = lambda *a, **k: (200, {"daily_limit": 20})
            self.assertIsNone(orchestrator.quota_remaining())
        finally:
            orchestrator._request = original_req
            orchestrator.os.environ.clear()
            orchestrator.os.environ.update(saved)


class BudgetTests(unittest.TestCase):
    """The budget must be enforced by the payload, not merely displayed."""

    def test_coordinator_carries_a_bounded_budget(self):
        cfg = dict(orchestrator.DEFAULT_CONFIG)
        payload = orchestrator.build_payload(
            issue(12), "agent/mission-12-fix", cfg, {"model": "m"}
        )
        self.assertEqual(payload["max_budget_per_run"], cfg["max_budget_usd"])
        self.assertEqual(payload["max_iterations"], cfg["max_iterations"])

    def test_every_sub_agent_carries_a_bounded_budget(self):
        cfg = dict(orchestrator.DEFAULT_CONFIG)
        payload = orchestrator.build_payload(
            issue(12), "agent/mission-12-fix", cfg, {"model": "m"}
        )
        for definition in payload["agent_definitions"]:
            self.assertEqual(definition["max_budget_per_run"],
                             cfg["agent_max_budget_usd"])
            self.assertEqual(definition["max_iteration_per_run"],
                             cfg["agent_max_iterations"])

    def test_budget_is_positive_and_below_the_ceiling(self):
        cfg = dict(orchestrator.DEFAULT_CONFIG)
        self.assertGreater(cfg["max_budget_usd"], 0)
        self.assertLessEqual(cfg["max_budget_usd"], 5.0)
        self.assertLessEqual(cfg["agent_max_budget_usd"], cfg["max_budget_usd"])

    def test_payload_declares_positive_budgets(self):
        # A non-positive budget would be accepted by the schema as "no budget";
        # the orchestrator must never send one.
        cfg = dict(orchestrator.DEFAULT_CONFIG)
        payload = orchestrator.build_payload(
            issue(12), "agent/mission-12-fix", cfg, {"model": "m"}
        )
        self.assertGreater(payload["max_budget_per_run"], 0)
        for definition in payload["agent_definitions"]:
            self.assertGreater(definition["max_budget_per_run"], 0)

    def test_preflight_refuses_a_missing_coordinator_budget(self):
        cfg = dict(orchestrator.DEFAULT_CONFIG)
        payload = orchestrator.build_payload(
            issue(12), "agent/mission-12-fix", cfg, {"model": "m"}
        )
        payload["max_budget_per_run"] = None
        problems = orchestrator.preflight.check_budget(payload)
        self.assertTrue(any("coordinator max_budget_per_run" in p for p in problems))

    def test_preflight_refuses_a_non_positive_sub_agent_budget(self):
        cfg = dict(orchestrator.DEFAULT_CONFIG)
        payload = orchestrator.build_payload(
            issue(12), "agent/mission-12-fix", cfg, {"model": "m"}
        )
        payload["agent_definitions"][0]["max_budget_per_run"] = 0
        problems = orchestrator.preflight.check_budget(payload)
        self.assertTrue(any("must be a positive number" in p for p in problems))

    def test_preflight_refuses_a_budget_above_the_ceiling(self):
        cfg = dict(orchestrator.DEFAULT_CONFIG)
        payload = orchestrator.build_payload(
            issue(12), "agent/mission-12-fix", cfg, {"model": "m"}
        )
        payload["max_budget_per_run"] = 999.0
        problems = orchestrator.preflight.check_budget(payload)
        self.assertTrue(any("exceeds ceiling" in p for p in problems))

    def test_preflight_refuses_missing_iterations(self):
        cfg = dict(orchestrator.DEFAULT_CONFIG)
        payload = orchestrator.build_payload(
            issue(12), "agent/mission-12-fix", cfg, {"model": "m"}
        )
        payload["max_iterations"] = None
        problems = orchestrator.preflight.check_budget(payload)
        self.assertTrue(any("max_iterations" in p for p in problems))

    def test_real_payload_passes_the_budget_check(self):
        cfg = dict(orchestrator.DEFAULT_CONFIG)
        payload = orchestrator.build_payload(
            issue(12), "agent/mission-12-fix", cfg, {"model": "m"}
        )
        self.assertEqual(orchestrator.preflight.check_budget(payload), [])


class ResumeAfterInterruptionTests(unittest.TestCase):
    """An interrupted mission must be re-queued, never lost nor duplicated."""

    def _state(self, active=True):
        return {
            "version": 1,
            "processed": [],
            "active": (
                {"issue": 70, "work_branch": "agent/mission-70-x",
                 "started_at": "2026-11-14T00:00:00Z", "owner": "run-a"}
                if active else None
            ),
            "journal": [],
        }

    def test_expired_lock_requeues_the_interrupted_mission(self):
        original_avail = orchestrator.kv_available
        original_get = orchestrator.kv_get
        saved = orchestrator.save_state
        try:
            orchestrator.kv_available = lambda: True
            orchestrator.kv_get = lambda key: {
                "owner": "run-a", "expires_at": "2000-01-01T00:00:00Z"
            }
            orchestrator.save_state = lambda state: None
            state = self._state()
            reason = orchestrator.reconcile_stale_active(state, dry_run=False)
        finally:
            orchestrator.kv_available = original_avail
            orchestrator.kv_get = original_get
            orchestrator.save_state = saved
        self.assertIsNone(reason)
        self.assertIsNone(state["active"])
        # The mission is still unprocessed, so it is resumed, not lost.
        self.assertEqual(state["processed"], [])

    def test_live_lock_still_blocks_a_second_mission(self):
        original_avail = orchestrator.kv_available
        original_get = orchestrator.kv_get
        try:
            orchestrator.kv_available = lambda: True
            orchestrator.kv_get = lambda key: {
                "owner": "run-a", "expires_at": "2999-01-01T00:00:00Z"
            }
            reason = orchestrator.reconcile_stale_active(self._state(), dry_run=False)
        finally:
            orchestrator.kv_available = original_avail
            orchestrator.kv_get = original_get
        self.assertIsNotNone(reason)
        self.assertIn("run-a", reason)

    def test_unreadable_lock_refuses_to_reconcile(self):
        # Fail-closed: without the lock we cannot prove nothing is running.
        original_avail = orchestrator.kv_available
        try:
            orchestrator.kv_available = lambda: False
            state = self._state()
            reason = orchestrator.reconcile_stale_active(state, dry_run=False)
        finally:
            orchestrator.kv_available = original_avail
        self.assertIsNotNone(reason)
        self.assertIsNotNone(state["active"])

    def test_dry_run_never_touches_persistent_state(self):
        original_avail = orchestrator.kv_available
        try:
            orchestrator.kv_available = lambda: True
            state = self._state()
            reason = orchestrator.reconcile_stale_active(state, dry_run=True)
        finally:
            orchestrator.kv_available = original_avail
        self.assertIsNone(reason)
        self.assertIsNotNone(state["active"])

    def test_no_active_mission_is_a_noop(self):
        state = self._state(active=False)
        self.assertIsNone(
            orchestrator.reconcile_stale_active(state, dry_run=False)
        )


class ReconcileDecisionTests(unittest.TestCase):
    """The interruption decision must never re-queue a mission that is running.

    Two independent proofs are consulted: the atomic KV lock and the recorded
    conversation's real status on the agent server. Any uncertainty is a
    fail-closed ``abort`` so a duplicate conversation can never be started.
    """

    def _state(self, conversation_id=None):
        return {
            "version": 1, "processed": [], "journal": [],
            "active": {"issue": 70, "work_branch": "agent/mission-70-x",
                       "started_at": "2026-11-14T00:00:00Z", "owner": "run-a",
                       "conversation_id": conversation_id},
        }

    def _patch(self, *, kv=True, lock=None, outcome="alive", status="running"):
        self._orig = (orchestrator.kv_available, orchestrator.kv_get,
                      orchestrator.conversation_status)
        orchestrator.kv_available = lambda: kv
        orchestrator.kv_get = lambda key: lock
        orchestrator.conversation_status = lambda cid: (outcome, status)

    def _restore(self):
        (orchestrator.kv_available, orchestrator.kv_get,
         orchestrator.conversation_status) = self._orig

    def test_live_lock_is_an_abort(self):
        self._patch(lock={"owner": "run-a", "expires_at": "2999-01-01T00:00:00Z"})
        try:
            action, detail = orchestrator._reconcile_decision(self._state("cid-x"))
        finally:
            self._restore()
        self.assertEqual(action, "abort")
        self.assertIn("run-a", detail)

    def test_unreadable_kv_is_an_abort(self):
        self._patch(kv=False)
        try:
            action, _ = orchestrator._reconcile_decision(self._state("cid-x"))
        finally:
            self._restore()
        self.assertEqual(action, "abort")

    def test_live_conversation_is_reattached_not_requeued(self):
        # No lock, but the recorded conversation is still running -> re-attach.
        self._patch(lock=None, outcome="alive", status="running")
        try:
            action, detail = orchestrator._reconcile_decision(self._state("cid-x"))
        finally:
            self._restore()
        self.assertEqual(action, "reattach")
        self.assertEqual(detail, "cid-x")

    def test_dead_conversation_is_requeued(self):
        # The conversation is gone (server answered but it is terminal) -> safe
        # to re-queue: nothing is running.
        self._patch(lock=None, outcome="gone", status="finished")
        try:
            action, _ = orchestrator._reconcile_decision(self._state("cid-x"))
        finally:
            self._restore()
        self.assertEqual(action, "proceed")

    def test_unreachable_server_is_fail_closed(self):
        # Cannot prove the conversation is dead -> never re-queue (could dupe).
        self._patch(lock=None, outcome="unknown")
        try:
            action, _ = orchestrator._reconcile_decision(self._state("cid-x"))
        finally:
            self._restore()
        self.assertEqual(action, "abort")

    def test_no_conversation_id_falls_back_to_the_lock_only(self):
        # A kill before the POST recorded an id: only the lock can prove safety.
        self._patch(lock=None)
        try:
            action, _ = orchestrator._reconcile_decision(self._state(None))
        finally:
            self._restore()
        self.assertEqual(action, "proceed")

    def test_reconcile_wrapper_clears_state_only_on_proceed(self):
        self._patch(lock=None, outcome="gone", status="error")
        saved = orchestrator.save_state
        orchestrator.save_state = lambda state: None
        try:
            state = self._state("cid-x")
            reason = orchestrator.reconcile_stale_active(state, dry_run=False)
        finally:
            orchestrator.save_state = saved
            self._restore()
        self.assertIsNone(reason)
        self.assertIsNone(state["active"])


class ConversationStatusTests(unittest.TestCase):
    """``conversation_status`` must distinguish alive, gone and unknown."""

    def _patch(self, response):
        self._orig = orchestrator._request
        orchestrator._request = lambda *a, **k: response

    def _restore(self):
        orchestrator._request = self._orig

    def test_running_200_is_alive(self):
        self._patch((200, {"execution_status": "running"}))
        try:
            self.assertEqual(orchestrator.conversation_status("cid"), ("alive", "running"))
        finally:
            self._restore()

    def test_finished_200_is_gone(self):
        self._patch((200, {"execution_status": "finished"}))
        try:
            self.assertEqual(orchestrator.conversation_status("cid"), ("gone", "finished"))
        finally:
            self._restore()

    def test_404_is_gone(self):
        self._patch((404, "not found"))
        try:
            self.assertEqual(orchestrator.conversation_status("cid"), ("gone", ""))
        finally:
            self._restore()

    def test_transport_error_is_unknown(self):
        self._orig = orchestrator._request

        def boom(*a, **k):
            raise OSError("network down")

        orchestrator._request = boom
        try:
            self.assertEqual(orchestrator.conversation_status("cid"), ("unknown", ""))
        finally:
            self._restore()

    def test_500_is_unknown(self):
        self._patch((500, "server error"))
        try:
            self.assertEqual(orchestrator.conversation_status("cid"), ("unknown", ""))
        finally:
            self._restore()

    def test_empty_cid_is_gone(self):
        self.assertEqual(orchestrator.conversation_status(""), ("gone", ""))


class DiagnoseEnvironmentTests(unittest.TestCase):
    """diagnose_environment() must authenticate its reachability probe.

    Regression: the probe used to call GET /api/conversations without the
    session key, which the agent server rejects with HTTP 422/401, so a live
    server was reported unreachable. It must send X-Session-API-Key and hit a
    parameterless endpoint.
    """

    def test_probe_sends_the_session_key_and_uses_the_count_endpoint(self):
        original_req = orchestrator._request
        saved = dict(orchestrator.os.environ)
        seen = {}
        try:
            orchestrator.os.environ["SESSION_API_KEY"] = "test-key"
            orchestrator.os.environ["AGENT_SERVER_URL"] = "http://agent.test"

            def fake_request(method, url, headers=None, **kwargs):
                seen["url"] = url
                seen["headers"] = headers or {}
                return 200, 3

            orchestrator._request = fake_request
            report = orchestrator.diagnose_environment()
        finally:
            orchestrator._request = original_req
            orchestrator.os.environ.clear()
            orchestrator.os.environ.update(saved)

        self.assertTrue(report["agent_server_reachable"])
        self.assertEqual(report["agent_server_detail"], "HTTP 200 (authenticated)")
        self.assertEqual(seen["headers"].get("X-Session-API-Key"), "test-key")
        self.assertTrue(seen["url"].endswith("/api/conversations/count"))

    def test_a_non_200_probe_is_reported_unreachable(self):
        original_req = orchestrator._request
        saved = dict(orchestrator.os.environ)
        try:
            orchestrator.os.environ["SESSION_API_KEY"] = "test-key"
            orchestrator._request = lambda *a, **k: (401, {"detail": "no"})
            report = orchestrator.diagnose_environment()
        finally:
            orchestrator._request = original_req
            orchestrator.os.environ.clear()
            orchestrator.os.environ.update(saved)
        self.assertFalse(report["agent_server_reachable"])
        self.assertEqual(report["agent_server_detail"], "HTTP 401")


class EmergencyStopTests(unittest.TestCase):
    """The kill-switch must halt a run from any of its three sources."""

    def setUp(self):
        self.saved = dict(os.environ)
        os.environ.pop(emergency.ENV_FLAG, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)

    def test_no_source_set_means_no_stop(self):
        stopped, reason = emergency.stop_requested("/nonexistent-dir-tel99", None)
        self.assertFalse(stopped)
        self.assertEqual(reason, "")

    def test_env_flag_stops_the_run(self):
        os.environ[emergency.ENV_FLAG] = "true"
        stopped, reason = emergency.stop_requested("/nonexistent-dir-tel99", None)
        self.assertTrue(stopped)
        self.assertIn(emergency.ENV_FLAG, reason)

    def test_env_flag_accepts_one_and_on(self):
        for value in ("1", "on", "yes", "TRUE"):
            os.environ[emergency.ENV_FLAG] = value
            self.assertTrue(emergency.env_stop(), value)

    def test_env_flag_is_not_triggered_by_a_false_like_value(self):
        os.environ[emergency.ENV_FLAG] = "false"
        self.assertFalse(emergency.env_stop())

    def test_sentinel_file_stops_the_run(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / emergency.SENTINEL_NAME).write_text("stop")
            stopped, reason = emergency.stop_requested(tmp, None)
        self.assertTrue(stopped)
        self.assertIn(emergency.SENTINEL_NAME, reason)

    def test_kv_flag_stops_the_run(self):
        stopped, reason = emergency.stop_requested(
            "/nonexistent-dir-tel99", lambda key: {"stopped": True}
        )
        self.assertTrue(stopped)
        self.assertIn(emergency.KV_KEY, reason)

    def test_unreadable_kv_does_not_stop_the_run(self):
        def boom(key):
            raise RuntimeError("KV down")

        stopped, reason = emergency.stop_requested("/nonexistent-dir-tel99", boom)
        self.assertFalse(stopped)

    def test_run_returns_three_when_the_brake_is_set(self):
        saved = dict(os.environ)
        original_state = orchestrator.load_state
        original_save = orchestrator.save_state
        try:
            os.environ[emergency.ENV_FLAG] = "true"
            orchestrator.load_state = lambda: {"version": 1, "processed": [],
                                               "active": None, "journal": []}
            orchestrator.save_state = lambda state: None
            code = orchestrator.run(dict(orchestrator.DEFAULT_CONFIG), offline=True)
        finally:
            orchestrator.load_state = original_state
            orchestrator.save_state = original_save
            os.environ.clear()
            os.environ.update(saved)
        self.assertEqual(code, 3)

    def test_config_flag_stops_the_run(self):
        saved = dict(os.environ)
        original_state = orchestrator.load_state
        original_save = orchestrator.save_state
        try:
            os.environ.pop(emergency.ENV_FLAG, None)
            orchestrator.load_state = lambda: {"version": 1, "processed": [],
                                               "active": None, "journal": []}
            orchestrator.save_state = lambda state: None
            config = dict(orchestrator.DEFAULT_CONFIG)
            config["emergency_stop"] = True
            code = orchestrator.run(config, offline=True)
        finally:
            orchestrator.load_state = original_state
            orchestrator.save_state = original_save
            os.environ.clear()
            os.environ.update(saved)
        self.assertEqual(code, 3)

    def test_local_stop_reports_env_without_network(self):
        os.environ[emergency.ENV_FLAG] = "1"
        stopped, reason = emergency.local_stop("/nonexistent-dir-tel99")
        self.assertTrue(stopped)
        self.assertIn(emergency.ENV_FLAG, reason)

    def test_local_stop_ignores_kv_source(self):
        # local_stop must not consult the KV reader at all.
        def boom(key):
            raise AssertionError("local_stop must not read the KV store")

        stopped, _ = emergency.local_stop("/nonexistent-dir-tel99")
        self.assertFalse(stopped)
        # stop_requested still consults KV, and tolerates a raising reader.
        self.assertFalse(emergency.stop_requested("/nonexistent-dir-tel99", boom)[0])

    def test_stopped_path_makes_no_network_call(self):
        """The local brake must return before load_state (a possible KV read)."""
        saved = dict(os.environ)
        original_load = orchestrator.load_state
        original_save = orchestrator.save_state
        called = {"load": False, "save": False}

        def spy_load():
            called["load"] = True
            return {"version": 1, "processed": [], "active": None, "journal": []}

        try:
            os.environ[emergency.ENV_FLAG] = "true"
            orchestrator.load_state = spy_load
            orchestrator.save_state = lambda state: called.__setitem__("save", True)
            code = orchestrator.run(dict(orchestrator.DEFAULT_CONFIG), offline=False)
        finally:
            orchestrator.load_state = original_load
            orchestrator.save_state = original_save
            os.environ.clear()
            os.environ.update(saved)
        self.assertEqual(code, 3)
        self.assertFalse(called["load"], "the brake must precede load_state")
        self.assertFalse(called["save"], "the stopped path must not write state")

    def test_kv_flag_stops_the_next_run(self):
        """The durable KV flag is honoured once the local sources are clear."""
        saved = dict(os.environ)
        original_load = orchestrator.load_state
        original_kv_avail = orchestrator.kv_available
        original_kv_get = orchestrator.kv_get
        original_save = orchestrator.save_state
        try:
            os.environ.pop(emergency.ENV_FLAG, None)
            orchestrator.load_state = lambda: {"version": 1, "processed": [],
                                               "active": None, "journal": []}
            orchestrator.save_state = lambda state: None
            orchestrator.kv_available = lambda: True
            orchestrator.kv_get = lambda key: {"stopped": True}
            code = orchestrator.run(dict(orchestrator.DEFAULT_CONFIG), offline=True)
        finally:
            orchestrator.load_state = original_load
            orchestrator.kv_available = original_kv_avail
            orchestrator.kv_get = original_kv_get
            orchestrator.save_state = original_save
            os.environ.clear()
            os.environ.update(saved)
        self.assertEqual(code, 3)

    def test_wait_for_interrupts_when_the_brake_is_set(self):
        """An active conversation is interrupted and reported as ``stopped``."""
        import tempfile
        saved = dict(os.environ)
        original_req = orchestrator._request
        original_interrupt = orchestrator.interrupt_conversation
        calls = {"interrupt": []}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                (pathlib.Path(tmp) / emergency.SENTINEL_NAME).write_text("stop")
                os.environ.pop(emergency.ENV_FLAG, None)
                orchestrator._request = lambda *a, **k: (200, {"execution_status": "running"})
                orchestrator.interrupt_conversation = (
                    lambda cid: calls["interrupt"].append(cid) or True
                )
                final = orchestrator.wait_for("cid-x", deadline=time.time() + 5,
                                              poll=0, state_dir=tmp)
        finally:
            orchestrator._request = original_req
            orchestrator.interrupt_conversation = original_interrupt
            os.environ.clear()
            os.environ.update(saved)
        self.assertEqual(final, "stopped")
        self.assertEqual(calls["interrupt"], ["cid-x"])

    def test_wait_for_deadline_interrupts_the_child(self):
        saved = dict(os.environ)
        original_interrupt = orchestrator.interrupt_conversation
        calls = {"interrupt": []}
        try:
            os.environ.pop(emergency.ENV_FLAG, None)
            orchestrator.interrupt_conversation = (
                lambda cid: calls["interrupt"].append(cid) or True
            )
            final = orchestrator.wait_for("cid-y", deadline=time.time() - 1, poll=0)
        finally:
            orchestrator.interrupt_conversation = original_interrupt
            os.environ.clear()
            os.environ.update(saved)
        self.assertEqual(final, "timeout")
        self.assertEqual(calls["interrupt"], ["cid-y"])

    def test_brake_is_checked_before_any_network_probe(self):
        """The stop must return before diagnose_environment is ever called."""
        saved = dict(os.environ)
        original_state = orchestrator.load_state
        original_save = orchestrator.save_state
        original_diag = orchestrator.diagnose_environment
        called = {"diag": False}

        def spy_diag():
            called["diag"] = True
            return {}

        try:
            os.environ[emergency.ENV_FLAG] = "true"
            orchestrator.load_state = lambda: {"version": 1, "processed": [],
                                               "active": None, "journal": []}
            orchestrator.save_state = lambda state: None
            orchestrator.diagnose_environment = spy_diag
            code = orchestrator.run(dict(orchestrator.DEFAULT_CONFIG), offline=False)
        finally:
            orchestrator.load_state = original_state
            orchestrator.save_state = original_save
            orchestrator.diagnose_environment = original_diag
            os.environ.clear()
            os.environ.update(saved)
        self.assertEqual(code, 3)
        self.assertFalse(called["diag"], "the brake must precede any probe")


class UnattendedConfirmationTests(unittest.TestCase):
    """An unattended run must never stall on a confirmation it cannot answer."""

    def test_payload_does_not_confirm_unknown_risk(self):
        """UNKNOWN-risk coordination actions must not require a confirmation.

        The security analyzer rates ``task_tool_set``/``task_tracker`` as UNKNOWN.
        With ``confirm_unknown: True`` the coordinator freezes in
        ``waiting_for_confirmation`` and the platform timeout kills the run.
        """
        cfg = dict(orchestrator.DEFAULT_CONFIG)
        payload = orchestrator.build_payload(
            issue(12), "agent/mission-12-fix", cfg, {"model": "m"}
        )
        policy = payload["confirmation_policy"]
        self.assertEqual(policy["kind"], "ConfirmRisky")
        self.assertFalse(policy["confirm_unknown"])

    def test_wait_for_fails_fast_on_a_confirmation_stall(self):
        saved = dict(os.environ)
        original_req = orchestrator._request
        original_interrupt = orchestrator.interrupt_conversation
        calls = {"interrupt": []}
        try:
            os.environ.pop(emergency.ENV_FLAG, None)
            orchestrator._request = lambda *a, **k: (
                200, {"execution_status": "waiting_for_confirmation"}
            )
            orchestrator.interrupt_conversation = (
                lambda cid: calls["interrupt"].append(cid) or True
            )
            final = orchestrator.wait_for("cid-z", deadline=time.time() + 5,
                                          poll=0, confirm_grace_polls=3)
        finally:
            orchestrator._request = original_req
            orchestrator.interrupt_conversation = original_interrupt
            os.environ.clear()
            os.environ.update(saved)
        self.assertEqual(final, "confirmation_required")
        self.assertEqual(calls["interrupt"], ["cid-z"])

    def test_run_aborts_without_processing_the_mission(self):
        """A confirmation stall aborts the run and leaves the mission resumable."""
        saved = dict(os.environ)
        originals = {
            name: getattr(orchestrator, name)
            for name in ("load_state", "save_state", "kv_available", "kv_get",
                         "diagnose_environment", "preflight", "quota_remaining",
                         "list_mission_issues", "acquire_lock", "release_lock",
                         "_request", "wait_for", "interrupt_conversation",
                         "report_phase", "bus_bridge")
        }
        written = {}

        class _Preflight:
            @staticmethod
            def preflight():
                return []

            @staticmethod
            def check_payload(payload):
                return []

            @staticmethod
            def check_budget(payload):
                return []

            @staticmethod
            def check_model(payload):
                return []

        try:
            os.environ.pop(emergency.ENV_FLAG, None)
            orchestrator.bus_bridge = None
            orchestrator.load_state = lambda: {"version": 1, "processed": [],
                                               "active": None, "journal": []}
            orchestrator.save_state = lambda state: written.update(state)
            orchestrator.kv_available = lambda: False
            orchestrator.kv_get = lambda key: None
            orchestrator.diagnose_environment = lambda: {}
            orchestrator.preflight = _Preflight
            orchestrator.quota_remaining = lambda: 20
            orchestrator.list_mission_issues = lambda repo, label: [
                {"number": 12, "title": "Fix", "labels": [{"name": "tel99-mission"}],
                 "state": "open", "body": "b"}
            ]
            orchestrator.acquire_lock = lambda owner, ttl_seconds=0: (True, "ok")
            orchestrator.release_lock = lambda owner: None
            orchestrator.report_phase = lambda phase: None
            orchestrator._request = lambda *a, **k: (201, {"id": "conv-1"})
            orchestrator.wait_for = lambda *a, **k: "confirmation_required"
            orchestrator.interrupt_conversation = lambda cid: True
            cfg = dict(orchestrator.DEFAULT_CONFIG)
            cfg["dry_run"] = False
            cfg["require_durable_bus"] = False
            code = orchestrator.run(cfg)
        finally:
            for name, value in originals.items():
                setattr(orchestrator, name, value)
            os.environ.clear()
            os.environ.update(saved)
        self.assertEqual(code, 2)
        self.assertIsNone(written.get("active"))
        self.assertEqual(written.get("processed", []), [])
        events = [e.get("event") for e in written.get("journal", [])]
        self.assertIn("abort", events)


if __name__ == "__main__":
    unittest.main()
