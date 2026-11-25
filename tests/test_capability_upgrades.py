"""Offline unit tests for TEL99 agent capability upgrades (adaptive budgets, auto-decomposition, smart repair, academy)."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUTOMATION_DIR = ROOT / "scripts" / "agents" / "automation"
for p in (str(ROOT), str(AUTOMATION_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from scripts.agents.automation import agent_academy, mission_planner, ollama_native, smart_repair


class CapabilityUpgradeTests(unittest.TestCase):
    def test_adaptive_budget_scales_safely_with_profile_and_ram(self):
        patch_b = ollama_native.compute_adaptive_budget("gemma4:e4b-tel99-8k", task_profile="patch", available_memory_mib=4000)
        self.assertLessEqual(patch_b["max_tokens"], 1024)
        self.assertLessEqual(patch_b["timeout"], 90)

        mod_b = ollama_native.compute_adaptive_budget("gemma4:e4b-tel99-8k", task_profile="module", estimated_lines=95, available_memory_mib=4000)
        self.assertEqual(mod_b["max_tokens"], 2048)
        self.assertGreater(mod_b["timeout"], 90)

        large_ok = ollama_native.compute_adaptive_budget("gemma4:e4b-tel99-8k", task_profile="large_module", estimated_lines=180, available_memory_mib=4500)
        self.assertEqual(large_ok["max_tokens"], 4096)

        # Low RAM must clamp large_module down to safe 2048 to protect 16 GB host
        large_low_ram = ollama_native.compute_adaptive_budget("gemma4:e4b-tel99-8k", task_profile="large_module", estimated_lines=180, available_memory_mib=1600)
        self.assertLessEqual(large_low_ram["max_tokens"], 2048)
        self.assertTrue(large_low_ram["ram_clamped"])

    def test_extract_code_block_handles_closed_and_truncated_fences(self):
        closed = "Here is code:\n```python\ndef f(x):\n    return x + 1\n```\nDone."
        self.assertEqual(ollama_native.extract_code_block(closed).strip(), "def f(x):\n    return x + 1")
        truncated = "```python\ndef f(x):\n    return x + 1"
        self.assertEqual(ollama_native.extract_code_block(truncated).strip(), "def f(x):\n    return x + 1")

    def test_ollama_provider_preserves_legacy_patch_limits_and_allows_module_profile(self):
        with self.assertRaises(ollama_native.ProviderError):
            ollama_native.OllamaNativeProvider(model="gemma4:e4b-tel99-8k", max_tokens=2048, timeout=90)
        p = ollama_native.OllamaNativeProvider(model="gemma4:e4b-tel99-8k", max_tokens=2048, timeout=160, task_profile="module")
        self.assertEqual(p.max_tokens, 2048)
        self.assertEqual(p.timeout, 160)

    def test_mission_planner_auto_decomposes_oversized_mission(self):
        big_task = {
            "id": "radar-engine",
            "path": "app/radar_engine.py",
            "estimated_lines": 150,
            "functions": ["load_dataset", "search_models", "compare_models", "check_pc_compatibility", "recommend_models", "import_payload"],
            "objective": "Implement all 6 functions for AI Radar.",
        }
        plan = mission_planner.assess_and_decompose_mission(big_task, model_id="local/ollama-gemma4-e4b", max_safe_lines=65)
        self.assertTrue(plan["needs_decomposition"])
        self.assertEqual(len(plan["subtasks"]), 3)
        self.assertEqual(plan["subtasks"][0]["dependencies"], [])
        self.assertEqual(plan["subtasks"][1]["dependencies"], [plan["subtasks"][0]["id"]])
        self.assertEqual(plan["subtasks"][2]["dependencies"], [plan["subtasks"][1]["id"]])

    def test_smart_repair_bounds_errors_and_detects_repeated_attempts(self):
        fp1 = smart_repair.code_fingerprint("def f():\n    return 1  \n")
        self.assertTrue(smart_repair.detect_repeated_attempt("def f():\n    return 1\n", [fp1]))
        self.assertFalse(smart_repair.detect_repeated_attempt("def f():\n    return 2\n", [fp1]))
        prompt = smart_repair.build_smart_repair_prompt(
            previous_code="def f():\n    return 1",
            exact_error="E" * 10000,
            passed_checks=["syntax", "security"],
            failed_checks=["behavior"],
            prior_attempts=[{"attempt": 1, "code_sha256": fp1, "error": "wrong return"}],
            memory_lessons=["Return int 2"],
        )
        self.assertLess(len(prompt), 2500)
        self.assertIn("DO NOT REPEAT", prompt)
        self.assertIn("Checks already PASSING", prompt)

    def test_agent_academy_maps_all_12_roles(self):
        cur = agent_academy.audit_12_roles_curriculum()
        self.assertEqual(cur["total_roles"], 12)


if __name__ == "__main__":
    unittest.main()
