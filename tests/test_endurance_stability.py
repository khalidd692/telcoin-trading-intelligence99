"""Offline unit tests for endurance stability: progressive report, safe resume, RAM guard & Gemma 4 pool."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import run_hour_autonomy_acceptance as endurance


class EnduranceStabilityTests(unittest.TestCase):
    def test_endurance_pool_uses_gemma4_only(self):
        pool = endurance.build_endurance_pool()
        self.assertGreaterEqual(len(pool), 10)
        models = {model for _, model in pool}
        self.assertEqual(models, {endurance.GEMMA4_MODEL})
        for specs, _ in pool:
            self.assertGreaterEqual(len(specs), 2)

    def test_memory_guard_unloads_ollama_and_recovers(self):
        samples = iter([
            {"system_ram_free_mb": 1050.0, "system_memory_load_pct": 92},
            {"system_ram_free_mb": 1200.0, "system_memory_load_pct": 89},
            {"system_ram_free_mb": 3200.0, "system_memory_load_pct": 72},
        ])
        unloaded = []
        res = endurance.ensure_memory_headroom(
            min_free_mb=1400.0,
            max_load_pct=88,
            wait_seconds=10.0,
            snapshot_fn=lambda: next(samples),
            unload_fn=lambda: unloaded.append("gemma4:e4b-tel99-8k") or ["gemma4:e4b-tel99-8k"],
            sleep_fn=lambda _s: None,
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["action"], "unloaded_and_recovered")
        self.assertEqual(res["unloaded_models"], ["gemma4:e4b-tel99-8k"])
        self.assertEqual(len(unloaded), 1)

    def test_memory_guard_pauses_cleanly_on_critical_low_ram(self):
        res = endurance.ensure_memory_headroom(
            min_free_mb=1400.0,
            critical_free_mb=900.0,
            max_load_pct=88,
            wait_seconds=0.0,
            snapshot_fn=lambda: {"system_ram_free_mb": 520.0, "system_memory_load_pct": 96},
            unload_fn=lambda: ["qwen3.5:9b-q4_K_M"],
            sleep_fn=lambda _s: None,
        )
        self.assertFalse(res["ok"])
        self.assertEqual(res["action"], "pause_low_memory")

    def test_resume_preserves_state_writes_progressive_report_and_avoids_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_root = root / "hour_campaign"
            report_path = root / "hour_campaign_report.json"
            state_root.mkdir(parents=True)
            sentinel = state_root / "sentinel_existing_evidence.txt"
            sentinel.write_text("do-not-delete", encoding="utf-8")

            # Seed checkpoint as if w1 + w2-repair already completed before interruption.
            endurance.save_checkpoint(state_root, {
                "schema_version": 2,
                "status": "INTERRUPTED",
                "completed_tags": ["w1", "w2-repair"],
                "waves": [{"wave": "w1", "total_count": 3, "accepted_count": 3, "duration_seconds": 40.0}],
                "repair_proof": {"mission_id": "hour-repair-proof", "status": "ACCEPTED", "duration_seconds": 25.0},
                "interruption_proof": None,
                "memory_guards": [],
                "next_wave_idx": 272,
                "next_pool_idx": 0,
                "accumulated_elapsed_seconds": 65.0,
            })

            ran_waves: list[str] = []

            def fake_wave(*, wave_tag, specs, **_kw):
                ran_waves.append(wave_tag)
                return {"wave": wave_tag, "total_count": len(specs), "accepted_count": len(specs), "duration_seconds": 5.0}

            with patch.object(endurance, "_enforce_cloud_independence", return_value={"allow_subscription_cli": False}), \
                 patch.object(endurance, "_snapshot_ram", return_value={"system_ram_total_mb": 14181.0, "system_ram_free_mb": 5000.0, "system_ram_used_mb": 9181.0, "system_memory_load_pct": 64, "python_rss_mb": 40.0, "ollama_rss_mb": 200.0, "localharness_rss_mb": 0.0}), \
                 patch.object(endurance, "_run_wave", side_effect=fake_wave), \
                 patch.object(endurance, "_run_repair_proof", side_effect=AssertionError("must not replay w2-repair")), \
                 patch.object(endurance, "_run_interruption_and_no_duplicate_proof", return_value={"post_crash_replayed_workers": 0, "accepted_wave_replayed_workers": 0, "duration_seconds": 1.0}):
                rc = endurance.main([
                    "--min-minutes", "1.0",
                    "--state-root", str(state_root),
                    "--report", str(report_path),
                ])

            self.assertEqual(rc, 0)
            self.assertTrue(sentinel.is_file(), "existing state directory must never be deleted")
            self.assertEqual(ran_waves, [], "w1 must not be replayed and 65s >= 60s target already satisfied")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "COMPLETED")
            self.assertTrue(report["resumed_from_checkpoint"])
            self.assertEqual(report["missions_accepted"], 4)
            self.assertEqual(report["duplicates_count"], 0)
            cp = endurance.load_checkpoint(state_root)
            self.assertEqual(cp["status"], "COMPLETED")
            self.assertIn("w3-recovery", cp["completed_tags"])


if __name__ == "__main__":
    unittest.main()
