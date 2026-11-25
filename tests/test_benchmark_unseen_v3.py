"""Integrity & disjointness tests for Brand-New Frozen Benchmark Unseen V3 (60 missions)."""
from __future__ import annotations

import ast
import re
import unittest

from scripts.agents.automation import agent_academy, benchmark_suite_100, benchmark_unseen_v3


class BenchmarkUnseenV3Tests(unittest.TestCase):
    def test_60_tasks_12_roles_balanced_and_sealed(self):
        m = benchmark_unseen_v3.unseen_v3_manifest()
        self.assertEqual(m["total_tasks"], 60)
        self.assertEqual(m["roles_covered"], 12)
        for role, cnt in m["tasks_per_role"].items():
            self.assertEqual(cnt, 5, f"Role {role} should have 5 unseen V3 tasks")
        self.assertGreaterEqual(m["critical_security_tasks"], 12)
        self.assertEqual(len(m["seal_sha256"]), 64)
        # Seal is deterministic
        self.assertEqual(m["seal_sha256"], benchmark_unseen_v3.unseen_v3_manifest()["seal_sha256"])

    def test_strictly_disjoint_from_v1_benchmark_and_academy(self):
        v1_ids = {t["id"] for t in benchmark_suite_100.BENCHMARK_120}
        acad_ids = {t["id"] for t in agent_academy.CALIBRATION_EXERCISES + agent_academy.HELD_OUT_EVAL_EXERCISES}
        v3_ids = {t["id"] for t in benchmark_unseen_v3.UNSEEN_V3_60}
        self.assertEqual(len(v3_ids), 60)
        self.assertFalse(v3_ids & v1_ids, "V3 IDs must not overlap V1 120-benchmark")
        self.assertFalse(v3_ids & acad_ids, "V3 IDs must not overlap Academy")

        def _extract_syms(tasks):
            syms = set()
            for t in tasks:
                syms.update(re.findall(r"(?:Write|class)\s+`([A-Za-z_][A-Za-z0-9_]*)\(", t["objective"]))
            return syms

        v1_syms = _extract_syms(benchmark_suite_100.BENCHMARK_120)
        acad_syms = _extract_syms(agent_academy.CALIBRATION_EXERCISES + agent_academy.HELD_OUT_EVAL_EXERCISES)
        v3_syms = _extract_syms(benchmark_unseen_v3.UNSEEN_V3_60)
        self.assertFalse(v3_syms & v1_syms, f"Function symbol overlap with V1: {v3_syms & v1_syms}")
        self.assertFalse(v3_syms & acad_syms, f"Function symbol overlap with Academy: {v3_syms & acad_syms}")

    def test_all_test_codes_compile_and_json_tasks_valid(self):
        for t in benchmark_unseen_v3.UNSEEN_V3_60:
            if t["kind"] == "python":
                ast.parse(t["test_code"])
            else:
                self.assertTrue(t["required_fields"])
                self.assertTrue(t["expected_values"])


if __name__ == "__main__":
    unittest.main()
