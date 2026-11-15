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
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
AUTOMATION = ROOT / "scripts" / "agents" / "automation"
GUARD = ROOT / "scripts" / "agents" / "guard" / "guard.py"
PLUGIN = ROOT / ".plugin" / "plugin.json"


def _load(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


policy = _load("tel99_automation_policy", AUTOMATION / "policy.py")
verify_runtime = _load("tel99_verify_runtime", AUTOMATION / "verify_runtime.py")


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

    def test_unknown_quota_does_not_block(self):
        self.assertEqual(self._go(quota_remaining=None), [])


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


if __name__ == "__main__":
    unittest.main()
