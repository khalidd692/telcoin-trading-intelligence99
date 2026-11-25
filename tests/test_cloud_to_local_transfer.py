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


if __name__ == "__main__":
    unittest.main()
