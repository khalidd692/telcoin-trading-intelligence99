"""Verification tests for the frozen 120-mission 12-role executable benchmark and LoRA corpus builder."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import tempfile
import unittest

from scripts.agents.automation import benchmark_suite_100, lora_corpus_builder


class Benchmark120Tests(unittest.TestCase):
    def test_120_distinct_tasks_all_12_roles_strictly_disjoint_splits(self):
        manifest = benchmark_suite_100.benchmark_manifest()
        self.assertEqual(manifest["total_tasks"], 120)
        self.assertEqual(manifest["roles_covered"], 12)
        self.assertEqual(manifest["counts_by_split"], {"train": 24, "dev": 24, "held_out_final": 72})
        for role in benchmark_suite_100.ROLES_12:
            self.assertEqual(manifest["counts_by_role"][role], 10)

        ids = [t["id"] for t in benchmark_suite_100.BENCHMARK_120]
        self.assertEqual(len(ids), len(set(ids)))

        tr = {t["id"] for t in benchmark_suite_100.get_split("train")}
        dv = {t["id"] for t in benchmark_suite_100.get_split("dev")}
        ho = {t["id"] for t in benchmark_suite_100.get_split("held_out_final")}
        self.assertEqual(len(tr & dv), 0)
        self.assertEqual(len(tr & ho), 0)
        self.assertEqual(len(dv & ho), 0)

    def test_all_120_verifiers_parse_and_reject_trivial_stub(self):
        for task in benchmark_suite_100.BENCHMARK_120:
            if task["kind"] == "code":
                ast.parse(task["test_code"])
            res = benchmark_suite_100.verify_task_output(task, "def _stub(*a, **k): return None\n")
            self.assertFalse(res["ok"], f"Verifier for {task['id']} must reject trivial stub!")

    def test_lora_corpus_builder_dedups_scrubs_and_guards_held_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp) / "trajectories.jsonl"
            rows = [
                {"mission_id": "m1", "project": "p", "role": "tel99-dev", "objective": "Implement safe parser with token=ghp_123456789012345678901234", "verdict": "SUCCESS", "model": "gemma4"},
                {"mission_id": "m1-dup", "project": "p", "role": "tel99-dev", "objective": "Implement safe parser with token=ghp_123456789012345678901234", "verdict": "SUCCESS", "model": "gemma4"},
                {"mission_id": "m-fail", "project": "p", "role": "tel99-dev", "objective": "Failed task must be excluded from SFT corpus", "verdict": "FAILURE", "model": "gemma4"},
                {"mission_id": "upgraded-dev-ho-01", "project": "p", "role": "tel99-dev", "objective": "Held out task must never enter training corpus", "verdict": "SUCCESS", "model": "gemma4"},
            ]
            tpath.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            out = Path(tmp) / "corpus.jsonl"
            rep = lora_corpus_builder.build_verified_trajectory_corpus([tpath], out, excluded_task_ids={"dev-ho-01"})
            self.assertEqual(rep["records_kept"], 1)
            self.assertEqual(rep["skipped_duplicates"], 1)
            self.assertEqual(rep["skipped_unverified"], 1)
            self.assertEqual(rep["skipped_held_out_leak_guard"], 1)
            text = out.read_text(encoding="utf-8")
            self.assertNotIn("ghp_", text)


if __name__ == "__main__":
    unittest.main()
