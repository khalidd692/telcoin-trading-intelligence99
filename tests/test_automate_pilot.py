"""Deterministic tests for the single TEL99 OpenHands pilot automation recipe.

Stdlib only: no network, no token, no agent server, no OpenHands SDK. These
tests lock the owner's issue #86 safety rules so a later edit cannot silently
weaken the recipe:

  * exactly one pilot, manual-only, no cron;
  * ``dry_run`` is true by default and starts no conversation;
  * a real launch is refused below 12/20 and when the quota is unknown;
  * only the free model is accepted;
  * the recipe matches the plugin config_schema exactly;
  * the recipe carries no GitHub write path (checked on the orchestrator).

Run:
    python -m unittest discover -s tests -p 'test_automate_pilot.py' -v
"""

import importlib.util
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "agents" / "automation" / "pilot_recipe.py"
PLUGIN = ROOT / ".plugin" / "plugin.json"
ORCHESTRATOR = ROOT / "scripts" / "agents" / "automation" / "orchestrator.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pilot = _load("pilot_recipe_under_test", MODULE_PATH)


class RecipeShapeTest(unittest.TestCase):
    def test_recipe_keys_match_plugin_schema_exactly(self):
        schema = json.loads(PLUGIN.read_text())
        schema_keys = set(schema["automation"]["config_schema"]["properties"])
        self.assertEqual(set(pilot.pilot_recipe()), schema_keys)

    def test_schema_forbids_additional_properties(self):
        schema = json.loads(PLUGIN.read_text())
        self.assertIs(schema["automation"]["config_schema"]["additionalProperties"], False)

    def test_valid_recipe_has_no_reasons(self):
        self.assertEqual(pilot.validate_recipe(), [])

    def test_repository_is_the_allowlisted_one(self):
        self.assertEqual(
            pilot.pilot_recipe()["repository"],
            "khalidd692/telcoin-trading-intelligence99",
        )

    def test_base_branch_is_not_protected(self):
        base = pilot.pilot_recipe()["base_branch"]
        self.assertNotIn(base, pilot.PROTECTED_BRANCHES)
        self.assertFalse(base.startswith(pilot.PROTECTED_PREFIXES))


class ManualOnlyTest(unittest.TestCase):
    def test_lifecycle_is_inactive_and_manual(self):
        life = pilot.lifecycle()
        self.assertFalse(life["enabled"])
        self.assertEqual(life["state"], "INACTIVE")
        self.assertTrue(life["manual_dispatch_only"])
        self.assertIsNone(life["cron"])

    def test_recipe_contains_no_cron_key(self):
        self.assertNotIn("cron", pilot.pilot_recipe())
        self.assertNotIn("schedule", pilot.pilot_recipe())

    def test_create_request_uses_the_repo_plugin(self):
        req = pilot.plugin_spec_request()
        self.assertEqual(req["plugin"]["source"], pilot.PLUGIN_SOURCE)
        self.assertEqual(req["plugin"]["repo_path"], ".plugin")
        self.assertEqual(req["config"], pilot.pilot_recipe())


class DryRunTest(unittest.TestCase):
    def test_dry_run_defaults_true(self):
        self.assertIs(pilot.pilot_recipe()["dry_run"], True)

    def test_dry_run_false_is_rejected(self):
        recipe = pilot.pilot_recipe()
        recipe["dry_run"] = False
        reasons = pilot.validate_recipe(recipe)
        self.assertTrue(any("dry_run" in r for r in reasons))

    def test_dry_run_launch_is_always_allowed(self):
        # Even with an unknown quota, a rehearsal is allowed (it starts nothing).
        decision = pilot.launch_decision(None, dry_run=True)
        self.assertTrue(decision["allowed"])
        self.assertEqual(decision["status"], "dry_run")

    def test_orchestrator_returns_before_creating_a_conversation(self):
        text = ORCHESTRATOR.read_text()
        dry_idx = text.index('if config["dry_run"]:')
        # The ONLY conversation-creating call is this POST (line ~980).
        conv_idx = text.index('"POST", f"{agent_server_base()}/api/conversations"')
        # The dry-run early return must appear before that POST.
        self.assertLess(dry_idx, conv_idx)


class QuotaFloorTest(unittest.TestCase):
    def test_floor_is_twelve(self):
        self.assertEqual(pilot.MIN_QUOTA_REQUIRED, 12)
        self.assertEqual(pilot.pilot_recipe()["quota_min_remaining"], 12)

    def test_real_launch_allowed_at_or_above_floor(self):
        for remaining in (12, 13, 20):
            d = pilot.launch_decision(remaining, dry_run=False)
            self.assertTrue(d["allowed"], remaining)
            self.assertEqual(d["status"], "allowed")

    def test_real_launch_blocked_below_floor(self):
        for remaining in (0, 1, 11):
            d = pilot.launch_decision(remaining, dry_run=False)
            self.assertFalse(d["allowed"], remaining)
            self.assertEqual(d["status"], "blocked_quota")

    def test_unknown_quota_blocks_a_real_launch(self):
        d = pilot.launch_decision(None, dry_run=False)
        self.assertFalse(d["allowed"])
        self.assertEqual(d["status"], "unknown")
        self.assertIn("unknown", d["reason"].lower())

    def test_floor_below_twelve_is_rejected(self):
        recipe = pilot.pilot_recipe()
        recipe["quota_min_remaining"] = 2
        reasons = pilot.validate_recipe(recipe)
        self.assertTrue(any("quota_min_remaining" in r for r in reasons))


class SingleMissionTest(unittest.TestCase):
    def test_max_concurrent_is_one(self):
        self.assertEqual(pilot.MAX_CONCURRENT_MISSIONS, 1)
        self.assertEqual(pilot.pilot_recipe()["max_concurrent_missions"], 1)

    def test_more_than_one_mission_is_rejected(self):
        recipe = pilot.pilot_recipe()
        recipe["max_concurrent_missions"] = 2
        reasons = pilot.validate_recipe(recipe)
        self.assertTrue(any("max_concurrent_missions" in r for r in reasons))

    def test_schema_pins_one_mission(self):
        schema = json.loads(PLUGIN.read_text())
        prop = schema["automation"]["config_schema"]["properties"]["max_concurrent_missions"]
        self.assertEqual(prop["maximum"], 1)
        self.assertEqual(prop["default"], 1)


class FreeModelTest(unittest.TestCase):
    def test_free_model_accepted(self):
        self.assertEqual(
            pilot.validate_recipe(model_id="openhands/deepseek-v4.1-flash"), []
        )

    def test_paid_model_rejected(self):
        reasons = pilot.validate_recipe(model_id="openhands/gpt-5.6")
        self.assertTrue(any("free allowlist" in r for r in reasons))

    def test_unknown_or_empty_model_rejected(self):
        self.assertTrue(pilot.validate_recipe(model_id=""))
        self.assertTrue(pilot.validate_recipe(model_id=None))

    def test_profile_name_form_is_also_free(self):
        self.assertEqual(
            pilot.validate_recipe(model_id="openhands_deepseek-v4.1-flash"), []
        )


class TimeAndBudgetCapsTest(unittest.TestCase):
    def test_runtime_within_platform_ceiling(self):
        self.assertLessEqual(pilot.pilot_recipe()["max_runtime_seconds"], 1800)

    def test_runtime_above_ceiling_rejected(self):
        recipe = pilot.pilot_recipe()
        recipe["max_runtime_seconds"] = 3600
        reasons = pilot.validate_recipe(recipe)
        self.assertTrue(any("max_runtime_seconds" in r for r in reasons))

    def test_durable_bus_required(self):
        recipe = pilot.pilot_recipe()
        recipe["require_durable_bus"] = False
        reasons = pilot.validate_recipe(recipe)
        self.assertTrue(any("require_durable_bus" in r for r in reasons))


class NoGithubWriteTest(unittest.TestCase):
    def test_automation_code_only_reads_github(self):
        text = ORCHESTRATOR.read_text()
        # The only GitHub endpoint in the orchestrator is a GET issues listing.
        self.assertIn("api.github.com/repos", text)
        for verb in ('"POST", f"https://api.github.com',
                     '"PATCH", f"https://api.github.com',
                     '"PUT", f"https://api.github.com',
                     '"DELETE", f"https://api.github.com'):
            self.assertNotIn(verb, text, verb)


class InventoryViewTest(unittest.TestCase):
    def test_empty_inventory_is_zero(self):
        view = pilot.inventory_view([])
        self.assertEqual(view["count"], 0)
        self.assertEqual(view["active_count"], 0)

    def test_inactive_automations_are_not_active(self):
        raw = [
            {
                "id": "abc",
                "name": "existing",
                "enabled": False,
                "state": "INACTIVE",
                "trigger": {"type": "cron", "schedule": "0 0 * * *"},
                "model": "openhands_deepseek-v4.1-flash",
                "plugin_spec": {"plugin": {"ref": "main"}, "config": {"dry_run": False}},
            }
        ]
        view = pilot.inventory_view(raw)
        self.assertEqual(view["count"], 1)
        self.assertEqual(view["active_count"], 0)
        self.assertEqual(view["active_ids"], [])
        self.assertFalse(view["automations"][0]["manual_only"])  # has a cron

    def test_none_inventory_is_zero(self):
        self.assertEqual(pilot.inventory_view(None)["count"], 0)


class DedupKeyTest(unittest.TestCase):
    def test_key_is_stable(self):
        a = pilot.dedup_key("o/r", 70, "Mission lecture seule")
        b = pilot.dedup_key("o/r", 70, "mission lecture seule")
        self.assertEqual(a, b)

    def test_key_differs_per_issue(self):
        self.assertNotEqual(
            pilot.dedup_key("o/r", 70, "x"),
            pilot.dedup_key("o/r", 71, "x"),
        )


if __name__ == "__main__":
    unittest.main()
