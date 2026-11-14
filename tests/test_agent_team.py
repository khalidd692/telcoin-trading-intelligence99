"""Automated tests for the TEL99 agent team: security, config and delegation.

Stdlib-only by design: the OpenHands SDK, PyYAML and python-frontmatter are
not installed in CI, so the frontmatter of the generated agent files is parsed
here with a minimal, dependency-free reader.

Run:
    python -m unittest discover -s tests -p 'test_agent_team*.py' -v
"""

import importlib.util
import contextlib
import io
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "agents"
AGENTS_DIR = ROOT / ".agents" / "agents"
RESERVE_DIR = AGENTS_DIR / "reserve"
GUARD = SCRIPTS / "guard" / "guard.py"


def _load(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


team_config = _load("tel99_team_config", SCRIPTS / "team_config.py")
verify_delegation = _load("tel99_verify_delegation", SCRIPTS / "verify_delegation.py")


def parse_frontmatter(path):
    """Minimal YAML frontmatter reader: top-level scalars and simple lists.

    Good enough for the flat frontmatter the renderer emits; avoids a PyYAML
    dependency in CI.
    """
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        return {}, text
    block = match.group(1)
    data = {}
    key = None
    for raw in block.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if indent == 0 and ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "":
                data[key] = []
            elif value.lower() in ("true", "false"):
                data[key] = value.lower() == "true"
            else:
                data[key] = value
        elif line.startswith("- ") and key is not None:
            if isinstance(data.get(key), list):
                data[key].append(line[2:].strip())
    return data, text[match.end():]


def run_guard(command, tool_name="terminal"):
    event = json.dumps({"tool_name": tool_name, "tool_input": {"command": command}})
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=event, capture_output=True, text=True,
    )
    return proc.returncode


class GuardSecurityTests(unittest.TestCase):
    """The PreToolUse guard must block mutations and allow read-only commands."""

    BLOCKED = [
        "rm -rf /tmp/x",
        "mv a b",
        "cp a b",
        "git commit -m x",
        "git push origin main",
        "git checkout main",
        "git reset --hard",
        "git branch -D topic",
        "git fetch origin",
        "git config user.name x",
        "echo hi > /tmp/leak",
        "echo hi >> src/file.py",
        "pip install requests",
        "pip3 install requests",
        "npm install left-pad",
        "apt-get install curl",
        "curl -X POST https://api.example.com",
        "curl --data x https://api.example.com",
        "wget https://example.com/x",
        "gh pr create --fill",
        "sudo rm -rf /",
        "touch /tmp/z",
        "mkdir /tmp/newdir",
        "python3 -c \"open('/tmp/f','w').write('x')\"",
        "python3 -c \"from pathlib import Path;Path('/tmp/x').write_text('a')\"",
        "python3 -c \"import shutil;shutil.rmtree('/tmp/x')\"",
        "sed -i 's/a/b/' file.txt",
        "kraken order buy TELUSD",
        "place a paper order",
        "bash -c 'rm -rf /tmp/q'",
        "sh -c 'git push'",
        "xargs rm",
        "env FOO=1 rm -rf /tmp/y",
    ]
    ALLOWED = [
        "ls -la",
        "git status",
        "git log --oneline -3",
        "git diff --stat",
        "git show HEAD:AGENTS.md",
        "git rev-parse HEAD",
        "grep -rn TODO src",
        "cat AGENTS.md",
        "ls > /dev/null",
        # Regression guards: these were wrongly blocked by a substring matcher.
        "find deploy -type f",
        "grep -n deploy-pages .github/workflows/monitor.yml",
        "cat deploy/README.md",
        "cmd 2>&1 | head",
        "python -c \"print(open('x').read())\"",
        "grep -c order file",
        "python3 scripts/agents/team_audit.py",
        "python3 -m unittest discover -s tests",
    ]

    def test_blocked_commands_return_exit_2(self):
        for command in self.BLOCKED:
            with self.subTest(command=command):
                self.assertEqual(run_guard(command), 2, command)

    def test_allowed_commands_return_exit_0(self):
        for command in self.ALLOWED:
            with self.subTest(command=command):
                self.assertEqual(run_guard(command), 0, command)

    def test_non_terminal_tools_are_not_policed(self):
        # The guard only polices the terminal tool; other tools are handled by
        # the agent's tool allowlist instead.
        self.assertEqual(run_guard("rm -rf /", tool_name="file_editor"), 0)

    def test_unparseable_event_allows(self):
        proc = subprocess.run(
            [sys.executable, str(GUARD)], input="not json", capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 0)


class TeamConfigTests(unittest.TestCase):
    """The central configuration must stay safe and consistent."""

    def test_validate_passes(self):
        team_config.validate()

    def test_three_active_agents(self):
        self.assertEqual(len(team_config.ACTIVE_AGENTS), 3)
        roles = {spec.role for spec in team_config.ACTIVE_AGENTS}
        self.assertEqual(roles, {"development", "quant", "quality"})

    def test_active_agents_are_terminal_only(self):
        for spec in team_config.ACTIVE_AGENTS:
            with self.subTest(agent=spec.name):
                self.assertEqual(spec.tools, ("terminal",))

    def test_active_agents_use_confirm_risky(self):
        for spec in team_config.ACTIVE_AGENTS:
            with self.subTest(agent=spec.name):
                self.assertEqual(spec.permission_mode, "confirm_risky")

    def test_budgets_are_positive_and_bounded(self):
        self.assertGreater(team_config.DEFAULT_MAX_BUDGET_USD, 0)
        self.assertLessEqual(
            team_config.DEFAULT_MAX_BUDGET_USD, team_config.MAX_BUDGET_CEILING_USD
        )
        self.assertGreater(team_config.DEFAULT_AGENT_MAX_BUDGET_USD, 0)

    def test_free_model_default(self):
        self.assertIn("deepseek", team_config.DEFAULT_MODEL)

    def test_hook_config_targets_terminal_guard(self):
        hooks = team_config.hook_config()
        matchers = hooks["pre_tool_use"]
        self.assertEqual(len(matchers), 1)
        self.assertEqual(matchers[0]["matcher"], "terminal")
        command = matchers[0]["hooks"][0]["command"]
        self.assertIn("guard/guard.py", command)

    def test_every_active_prompt_carries_read_only_contract(self):
        for spec in team_config.ACTIVE_AGENTS:
            with self.subTest(agent=spec.name):
                self.assertIn("LECTURE SEULE", spec.full_prompt())


class UniqueNameTests(unittest.TestCase):
    """Per-run unique names prevent the global-registry collision."""

    def test_names_carry_suffix(self):
        names = team_config.unique_names("120000")
        self.assertEqual(
            set(names.values()),
            {"tel99-dev-120000", "tel99-analyst-120000", "tel99-verifier-120000"},
        )

    def test_two_runs_never_collide(self):
        first = set(team_config.unique_names("000001").values())
        second = set(team_config.unique_names("000002").values())
        self.assertEqual(first & second, set())

    def test_default_suffix_is_generated(self):
        names = team_config.unique_names()
        self.assertEqual(len(names), 3)
        for name in names.values():
            self.assertRegex(name, r"^tel99-(dev|analyst|verifier)-\d{6}$")


class AgentFileTests(unittest.TestCase):
    """Generated Markdown definitions must match the configuration."""

    def test_active_files_exist_and_are_flat(self):
        for spec in team_config.ACTIVE_AGENTS:
            with self.subTest(agent=spec.name):
                path = AGENTS_DIR / f"{spec.name}.md"
                self.assertTrue(path.is_file(), path)

    def test_active_frontmatter_permissions_and_tools(self):
        for spec in team_config.ACTIVE_AGENTS:
            path = AGENTS_DIR / f"{spec.name}.md"
            fm, _ = parse_frontmatter(path)
            with self.subTest(agent=spec.name):
                self.assertEqual(fm.get("permission_mode"), "confirm_risky")
                self.assertEqual(fm.get("tools"), ["terminal"])
                self.assertEqual(fm.get("name"), spec.name)

    def test_active_files_declare_the_guard_hook(self):
        for spec in team_config.ACTIVE_AGENTS:
            text = (AGENTS_DIR / f"{spec.name}.md").read_text(encoding="utf-8")
            with self.subTest(agent=spec.name):
                self.assertIn("guard/guard.py", text)
                self.assertIn("pre_tool_use", text)

    def test_active_files_do_not_grant_file_editor(self):
        for spec in team_config.ACTIVE_AGENTS:
            text = (AGENTS_DIR / f"{spec.name}.md").read_text(encoding="utf-8")
            with self.subTest(agent=spec.name):
                self.assertNotIn("file_editor", text)


class ReservedRoleTests(unittest.TestCase):
    """The nine extra specializations are prepared but never auto-discovered."""

    def test_nine_reserved_roles(self):
        self.assertEqual(len(team_config.reserved_agents()), 9)

    def test_reserved_files_live_in_subdirectory(self):
        for spec in team_config.reserved_agents():
            with self.subTest(agent=spec.name):
                self.assertTrue((RESERVE_DIR / f"{spec.name}.md").is_file())

    def test_reserved_agents_are_not_top_level(self):
        # The SDK only loads top-level *.md, so a reserve/ file cannot be
        # triggered as a sub-agent.
        for spec in team_config.reserved_agents():
            with self.subTest(agent=spec.name):
                self.assertFalse((AGENTS_DIR / f"{spec.name}.md").exists())

    def test_reserved_names_are_distinct_from_active(self):
        active = {spec.name for spec in team_config.ACTIVE_AGENTS}
        reserved = {spec.name for spec in team_config.reserved_agents()}
        self.assertEqual(active & reserved, set())

    def test_reserved_are_marked_inactive(self):
        for spec in team_config.reserved_agents():
            with self.subTest(agent=spec.name):
                self.assertFalse(spec.active)


class RendererTests(unittest.TestCase):
    """render_agents.py must keep files in sync with team_config.py."""

    def test_check_passes(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "render_agents.py"), "--check"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class RunPilotPayloadTests(unittest.TestCase):
    """The launcher payload must encode the safety properties."""

    def setUp(self):
        self.run_pilot = _load("tel99_run_pilot", SCRIPTS / "run_pilot.py")
        # A fake LLM config keeps this test independent of any local profile.
        fake_llm = {"model": "openhands/deepseek-v4.1-flash", "api_key": "x",
                    "base_url": "https://llm-proxy.app.all-hands.dev"}
        self.payload = self.run_pilot.build_payload("test mission", "090909", fake_llm)

    def test_agents_have_unique_suffixed_names(self):
        names = [d["name"] for d in self.payload["agent_definitions"]]
        self.assertEqual(len(names), 3)
        self.assertEqual(len(set(names)), 3)
        for name in names:
            self.assertTrue(name.endswith("-090909"), name)

    def test_definitions_are_terminal_only_with_hooks(self):
        for definition in self.payload["agent_definitions"]:
            with self.subTest(agent=definition["name"]):
                self.assertEqual(definition["tools"], ["terminal"])
                self.assertEqual(definition["permission_mode"], "confirm_risky")
                self.assertIn("pre_tool_use", definition["hooks"])

    def test_parent_has_budget_guard_and_scoped_delegation(self):
        self.assertGreater(self.payload["max_budget_per_run"], 0)
        self.assertIn("pre_tool_use", self.payload["hook_config"])
        tools = {t["name"]: t.get("params", {}) for t in self.payload["agent"]["tools"]}
        self.assertEqual(tools["task_tool_set"]["sub_agent_scope"], {"tools": True})

    def test_no_credentials_are_committed(self):
        # The launcher reads the profile at runtime; the repo must never carry
        # a real key. Guard against accidental pasting of a live token.
        for path in [SCRIPTS / "run_pilot.py", SCRIPTS / "team_config.py"]:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("sk-", text)
                self.assertNotRegex(text, r"api_key\s*=\s*['\"][A-Za-z0-9]{20,}")

    def test_dry_run_does_not_require_the_server(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "run_pilot.py"), "--dry-run", "--suffix", "1"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        # On a machine without a saved profile this exits non-zero but must not
        # crash with a traceback; with a profile it prints the payload.
        self.assertNotIn("Traceback", proc.stderr)
        if proc.returncode == 0:
            self.assertIn("tel99-dev-1", proc.stdout)


class VerifyDelegationTests(unittest.TestCase):
    """verify_delegation.py must read real persisted state correctly."""

    def _make_conversation(self, tmp, tools, hook_present, declared):
        conv = pathlib.Path(tmp) / "conv123"
        (conv / "subagents" / "sub1").mkdir(parents=True)
        (conv / "meta.json").write_text(
            json.dumps({"agent_definitions": [{"name": n} for n in declared]}),
            encoding="utf-8",
        )
        state = {
            "agent": {"tools": tools},
            "confirmation_policy": {"kind": "ConfirmRisky"},
            "hook_config": {"pre_tool_use": [{"matcher": "terminal"}] if hook_present else []},
        }
        (conv / "subagents" / "sub1" / "base_state.json").write_text(
            json.dumps(state), encoding="utf-8"
        )
        return tmp

    def _verify_quietly(self, cid, data_dir, suffix):
        with contextlib.redirect_stdout(io.StringIO()):
            return verify_delegation.verify(cid, data_dir, suffix)

    def test_pass_on_compliant_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_conversation(
                tmp, [{"name": "terminal"}], True, ["tel99-dev-1"]
            )
            self.assertEqual(self._verify_quietly("conv123", tmp, "1"), 0)

    def test_fail_on_file_editor_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_conversation(
                tmp, [{"name": "terminal"}, {"name": "file_editor"}], True, ["tel99-dev-1"]
            )
            self.assertEqual(self._verify_quietly("conv123", tmp, "1"), 1)

    def test_fail_on_missing_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_conversation(tmp, [{"name": "terminal"}], False, ["tel99-dev-1"])
            self.assertEqual(self._verify_quietly("conv123", tmp, "1"), 1)

    def test_fail_on_wrong_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_conversation(tmp, [{"name": "terminal"}], True, ["tel99-dev-999"])
            self.assertEqual(self._verify_quietly("conv123", tmp, "1"), 1)


if __name__ == "__main__":
    unittest.main()
