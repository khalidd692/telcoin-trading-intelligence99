"""Offline verification tests for Enterprise Evolution methods (§5.1–§5.5 & Recipes D/E)."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agents.automation import evolution_lab


class TestEnterpriseEvolutionMethods(unittest.TestCase):
    def test_recipe_d_skillopt_promotes_winner_rejects_bad_and_supports_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            skill_dir = td_path / "tel99-role-quality"
            skill_dir.mkdir(parents=True)
            skill_file = skill_dir / "SKILL.md"
            original_text = "# Baseline Skill\nCheck basic types.\n"
            skill_file.write_text(original_text, encoding="utf-8")

            def evaluator(text: str) -> dict:
                if "WEAKEN_SECURITY" in text:
                    return {"pass_rate": 0.99, "critical_security_rate": 0.5}
                if "REJECT_BOOL_BEFORE_INT" in text:
                    return {"pass_rate": 0.95, "critical_security_rate": 1.0}
                return {"pass_rate": 0.70, "critical_security_rate": 1.0}

            res = evolution_lab.skillopt_optimize_skill(
                skill_path=skill_file,
                state_root=td_path / "state",
                candidates=[
                    {"id": "bad-sec", "content": "# Bad\nWEAKEN_SECURITY\n"},
                    {"id": "no-gain", "content": "# Same\nNo real improvement\n"},
                    {"id": "good-opt", "content": "# Improved\nREJECT_BOOL_BEFORE_INT\n"},
                ],
                validation_evaluator=evaluator,
                min_gain=0.05,
            )
            self.assertFalse(res["weights_modified"])
            self.assertTrue(res["promoted"])
            self.assertEqual(res["promoted_candidate_id"], "good-opt")
            self.assertIn("REJECT_BOOL_BEFORE_INT", skill_file.read_text(encoding="utf-8"))

            # Rejected strategies must be archived with exact causes
            rej = json.loads((td_path / "state" / "rejected_strategies.json").read_text(encoding="utf-8"))
            rej_ids = {r["candidate_id"]: r["reason"] for r in rej}
            self.assertEqual(rej_ids["bad-sec"], "security_regression_blocked")
            self.assertIn("insufficient_gain", rej_ids["no-gain"])

            # Deterministic rollback restores exact original Skill text
            rb = evolution_lab.rollback_skill_version(
                skill_path=skill_file,
                backup_path=res["rollback_backup_path"],
            )
            self.assertTrue(rb["ok"])
            self.assertEqual(skill_file.read_text(encoding="utf-8"), original_text)

    def test_skillopt_fails_closed_without_perfect_candidate_security_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = root / "role" / "SKILL.md"
            skill.parent.mkdir()
            original = "# Trusted baseline\n"
            skill.write_text(original, encoding="utf-8")

            for label, security_rate in (
                ("missing", None),
                ("partial", 0.999),
                ("nan", float("nan")),
                ("out-of-range", 1.1),
                ("boolean", True),
            ):
                skill.write_text(original, encoding="utf-8")
                def evaluator(text: str, security_rate=security_rate) -> dict:
                    result = {"pass_rate": 0.7 if text == original else 0.99}
                    if text == original:
                        result["critical_security_rate"] = 1.0
                    elif security_rate is not None:
                        result["critical_security_rate"] = security_rate
                    return result

                result = evolution_lab.skillopt_optimize_skill(
                    skill_path=skill,
                    state_root=root / label,
                    candidates=[{"id": "candidate", "content": "# Candidate\n"}],
                    validation_evaluator=evaluator,
                )
                self.assertFalse(result["promoted"], label)
                self.assertEqual(skill.read_text(encoding="utf-8"), original, label)

    def test_skillopt_requires_perfect_security_on_baseline_and_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = root / "role" / "SKILL.md"
            skill.parent.mkdir()
            original = "# Baseline\n"
            skill.write_text(original, encoding="utf-8")

            def unsafe_baseline(text: str) -> dict:
                return {
                    "pass_rate": 0.7 if text == original else 0.99,
                    "critical_security_rate": 0.9 if text == original else 1.0,
                }

            result = evolution_lab.skillopt_optimize_skill(
                skill_path=skill, state_root=root / "state", candidates=[{"id": "gain", "content": "# Better\n"}],
                validation_evaluator=unsafe_baseline,
            )
            self.assertFalse(result["promoted"])
            self.assertEqual(skill.read_text(encoding="utf-8"), original)
            self.assertEqual(result["baseline"]["critical_security_rate"], 0.9)

    def test_skillopt_missing_baseline_security_measurement_blocks_all_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = root / "role" / "SKILL.md"
            skill.parent.mkdir()
            original = "# Baseline\n"
            skill.write_text(original, encoding="utf-8")

            def missing_baseline(text: str) -> dict:
                return {"pass_rate": 0.7} if text == original else {
                    "pass_rate": 0.99, "critical_security_rate": 1.0,
                }

            result = evolution_lab.skillopt_optimize_skill(
                skill_path=skill, state_root=root / "state",
                candidates=[{"id": "gain", "content": "# Better\n"}],
                validation_evaluator=missing_baseline,
            )
            self.assertFalse(result["promoted"])
            self.assertEqual(result["blocked_reason"], "baseline_metrics_missing_or_critical_security_below_100_percent")
            self.assertEqual(skill.read_text(encoding="utf-8"), original)

    def test_halo_root_cause_classification_and_permission_lock(self) -> None:
        self.assertEqual(evolution_lab.classify_failure_root_cause("daily free token budget exhausted 429"), "QUOTA")
        self.assertEqual(evolution_lab.classify_failure_root_cause("RAM guard triggered low memory"), "INFRA")

        # Permission lock blocks self-modification of security gates
        blocked = evolution_lab.halo_synthesize_regression_and_verify(
            failure_trace="test failed",
            target_path="scripts/agents/guard/guard.py",
            regression_test_code="assert True",
            candidate_patch_code="def allow_all(): return True",
            independent_verifier=lambda p, t: (True, "ok"),
        )
        self.assertFalse(blocked["ok"])
        self.assertTrue(blocked["blocked"])

        # Legitimate regression + baseline-red -> candidate-green verified independently
        passed = evolution_lab.halo_synthesize_regression_and_verify(
            failure_trace="ValueError on bool input",
            target_path="scripts/utils/validator.py",
            regression_test_code="assert not accept_bool(True)",
            baseline_code="def accept_bool(x): return isinstance(x, int)",
            candidate_patch_code="def accept_bool(x): return not isinstance(x, bool)",
            independent_verifier=lambda code, t: ("not isinstance(x, bool)" in code, "verified"),
        )
        self.assertTrue(passed["ok"])
        self.assertFalse(passed["blocked"])
        self.assertTrue(passed["baseline_red"])
        self.assertTrue(passed["regression_test_present"])

    def test_recipe_e_programmatic_tool_calling_saves_llm_calls_and_latency(self) -> None:
        files = {
            "app.py": "def add(a: int, b: int) -> int:\n    return a + b\n",
            "data.json": '{"ok": true, "items": [1, 2, 3]}',
            "bad.py": "import subprocess\nsubprocess.run('id', shell=True)\n",
        }
        bench = evolution_lab.benchmark_programmatic_vs_llm(files)
        self.assertEqual(bench["files_checked"], 3)
        self.assertFalse(bench["all_ok"])  # Caught shell=True deterministically!
        self.assertEqual(bench["before_llm_calls"], 3)
        self.assertEqual(bench["after_llm_calls"], 0)
        self.assertEqual(bench["llm_calls_saved"], 3)
        self.assertEqual(bench["cost_usd_after"], 0.0)
        self.assertLess(bench["after_measured_ms"], bench["before_estimated_ms"])

    def test_alpha_evolve_bounded_candidates_and_rejected_memory(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            res = evolution_lab.alpha_evolve_candidates(
                objective="Select fastest valid parser",
                candidates=[
                    {"id": "slow-broken", "strategy": "regex", "ok": False, "score": 0.2},
                    {"id": "fast-valid", "strategy": "ast", "ok": True, "score": 0.94},
                ],
                evaluator=lambda c: {"ok": c["ok"], "score": c["score"], "evidence": c["strategy"]},
                state_root=td,
                max_branches=3,
            )
            self.assertEqual(res["decision"], "SELECTED")
            self.assertEqual(res["selected"]["id"], "fast-valid")
            rej = json.loads((Path(td) / "rejected_strategies.json").read_text(encoding="utf-8"))
            self.assertEqual(rej[0]["candidate_id"], "slow-broken")


if __name__ == "__main__":
    unittest.main()
