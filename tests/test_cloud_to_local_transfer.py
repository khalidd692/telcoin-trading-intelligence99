"""Tests for Cloud-to-Local Skill Transfer, sandboxed tool proposals, Skill discovery, and auto-chaining."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.agents.automation import (
    autonomy_runtime,
    cloud_to_local_transfer,
    context_engine,
    evolution_lab,
    local_deterministic_tools,
    mentor_curriculum,
    refresh_passports,
)


class CloudToLocalAndAutoChainTests(unittest.TestCase):
    def test_skill_tel99_local_precision_discovered(self):
        root = Path(__file__).resolve().parents[1]
        caps = evolution_lab.discover_capabilities(root)
        self.assertIn("tel99-local-precision", caps["skills"])
        selected = context_engine.select_relevant_skills(
            root / ".agents" / "skills",
            "python validation bool int causal window ThreadingHTTPServer",
            limit=3,
        )
        self.assertTrue(any(s["name"] == "tel99-local-precision" for s in selected))

    def test_resource_unavailable_classified_as_environment_error(self):
        self.assertEqual(autonomy_runtime.classify_failure("ResourceUnavailableError"), "ENVIRONMENT_ERROR")
        self.assertEqual(autonomy_runtime.classify_failure("ResourceBusyError"), "ENVIRONMENT_ERROR")

    def test_stage_verified_mentor_tools_and_lessons_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            orig_mem = cloud_to_local_transfer.MEM_DIR
            orig_prop = cloud_to_local_transfer.PROPOSALS_DIR
            try:
                cloud_to_local_transfer.MEM_DIR = Path(tmp) / "memory"
                cloud_to_local_transfer.PROPOSALS_DIR = Path(tmp) / "proposals"
                res = cloud_to_local_transfer.stage_verified_mentor_tools_and_lessons()
                self.assertEqual(res["lessons_added"], 4)
                tp = res["sandboxed_tool_proposal"]
                self.assertTrue(tp["isolated_tests_passed"])
                self.assertEqual(tp["status"], "PROPOSED_AWAITING_OWNER_APPROVAL")
            finally:
                cloud_to_local_transfer.MEM_DIR = orig_mem
                cloud_to_local_transfer.PROPOSALS_DIR = orig_prop

    def test_auto_chain_wait_for_pid_triggers_on_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Spawn a short-lived dummy process (0.4s) and verify run_full_local_chain waits & runs preflight
            dummy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.4)"])
            rep_dir = Path(tmp) / "chain"
            proc = subprocess.run(
                [
                    sys.executable, "-B", "-m", "scripts.agents.automation.run_full_local_chain",
                    "--wait-for-pid", str(dummy.pid),
                    "--steps", "lora_corpus",
                    "--report-dir", str(rep_dir),
                ],
                capture_output=True, text=True, timeout=60, check=False,
            )
            dummy.wait(timeout=5)
            rep = json.loads((rep_dir / "local_chain_report.json").read_text(encoding="utf-8"))
            self.assertIn(dummy.pid, rep["waiting_for_pids"])
            self.assertIn("dependencies_cleared_at", rep)
            self.assertIn("lora_corpus", rep["steps"])
            self.assertEqual(proc.returncode, 0)

    def test_refresh_passports_strict_evidence_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ai_art = root / "ai" / "artifacts"
            gen_art = root / "gen" / "artifacts"
            bench_art = root / "bench" / "artifacts"
            for d in (ai_art, gen_art, bench_art):
                d.mkdir(parents=True)
            statuses = {m: "ACCEPTED" for m in (
                "radar-search", "radar-compat", "radar-import", "radar-api", "radar-server",
                "radar-ui-html", "radar-ui-css", "radar-ui-render", "radar-ui-app", "radar-doc",
            )}
            (ai_art / "agent_campaign_report.json").write_text(json.dumps({
                "accepted_count": 10, "repairs_count": 2, "runtime_statuses": statuses,
                "missions": {m: {"status": "ACCEPTED", "attempts": 1} for m in statuses},
            }), encoding="utf-8")
            (gen_art / "generalization_report.json").write_text(json.dumps({
                "all_accepted": True, "missions": {"gen-ledger-core": "ACCEPTED", "gen-budget-report": "ACCEPTED"},
            }), encoding="utf-8")
            (bench_art / "cloud_to_local_transfer_report.json").write_text(json.dumps({
                "cloud_calls_during_evaluation": 0, "delta_success_rate": 0.25,
                "details_before": [{"role": "development", "ok": False}],
                "details_after": [{"role": "development", "ok": True, "attempts": 1, "repaired": False}],
            }), encoding="utf-8")
            out = refresh_passports.build_refreshed_passports(
                ai_radar_dir=root / "ai", gen_dir=root / "gen", bench_dir=root / "bench"
            )
            self.assertEqual(out["total_agents"], 12)
            by_role = {p["identity"]["role"]: p for p in out["passports"]}
            self.assertGreaterEqual(by_role["development"]["proven_level"], 5)
            # Role with no evidence stays at L0 honestly
            self.assertEqual(by_role["cloud"]["proven_level"], 0)

    def test_deterministic_tools_strip_examples_and_security_check(self):
        code = (
            "def add(a, b):\n    return a + b\n\n"
            "if __name__ == '__main__':\n    try:\n        print(add(1, 2)\n"
        )
        cleaned = local_deterministic_tools.strip_trailing_example_blocks(code)
        self.assertNotIn("__main__", cleaned)
        pre = local_deterministic_tools.static_security_and_syntax_precheck(cleaned, kind="python")
        self.assertTrue(pre["ok"] and pre["syntax_ok"] and pre["security_ok"])

        bad_sec = local_deterministic_tools.static_security_and_syntax_precheck("eval('1+1')", kind="python")
        self.assertFalse(bad_sec["ok"])
        self.assertFalse(bad_sec["security_ok"])

        j = local_deterministic_tools.static_security_and_syntax_precheck("Here:\n```json\n{\"ok\": true}\n```", kind="json")
        self.assertTrue(j["ok"])
        self.assertEqual(json.loads(j["cleaned"]), {"ok": True})

        self.assertEqual(local_deterministic_tools.require_int(5, min_val=0, max_val=10), 5)
        with self.assertRaises(ValueError):
            local_deterministic_tools.require_int(True, min_val=0)
        self.assertEqual(local_deterministic_tools.causal_slice([10, 20, 30, 40], 2, 2), [20, 30])

    def test_all_12_specialized_role_skills_present_and_non_empty(self):
        from scripts.agents.automation import benchmark_suite_100
        root = Path(__file__).resolve().parents[1]
        caps = evolution_lab.discover_capabilities(root)
        for role in benchmark_suite_100.ROLES_12:
            sname = f"tel99-role-{role.replace('_', '-')}"
            self.assertIn(sname, caps["skills"])
            card = mentor_curriculum.load_role_skill_card(role, skills_dir=root / ".agents" / "skills", max_chars=750)
            self.assertGreater(len(card), 200)
            self.assertIn("Règles critiques", card)


if __name__ == "__main__":
    unittest.main()
