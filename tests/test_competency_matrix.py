"""Unit tests for the 12x12 Generalist Competency Matrix & 2-layer cross-agent knowledge sharing."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.agents.automation import competency_matrix, mentor_curriculum
from scripts.agents.intelligence.memory import Entry, MemoryStore


class CompetencyMatrixTests(unittest.TestCase):
    def test_two_layer_context_bounded_for_8k(self):
        root = Path(__file__).resolve().parents[1]
        ctx = mentor_curriculum.build_two_layer_generalist_context(
            agent_role="security",
            target_domain="quant",
            skills_dir=root / ".agents" / "skills",
            objective="Write a causal rolling mean function",
        )
        self.assertTrue(ctx["cross_domain_transfer"])
        self.assertLessEqual(ctx["context_chars"], 1150)
        self.assertIn("SOCLE GÉNÉRALISTE", ctx["context_text"])
        self.assertIn("tel99-role-quant", ctx["context_text"])

    def test_cross_agent_knowledge_sync_and_12x12_matrix(self):
        with tempfile.TemporaryDirectory() as tmp:
            ms = MemoryStore(tmp)
            ms.record(
                Entry(
                    id="verified-quant-1",
                    project="tel99-bench",
                    kind="procedure",
                    title="Causal slicing rule",
                    body="Always slice values[max(0, i-w+1):i+1] without lookahead.",
                    tags=("quant",),
                    source="test",
                    author="tel99-analyst",
                    verified=True,
                    verified_by="test",
                    confidence=0.95,
                ),
                actor="test",
            )
            sync = competency_matrix.sync_cross_agent_shared_knowledge(Path(tmp))
            self.assertEqual(sync["promoted_new"], 1)
            self.assertEqual(sync["total_shared_verified_entries"], 1)

        plan = competency_matrix.plan_cross_domain_rotations(rotations_per_agent=2)
        self.assertEqual(len(plan), 24)
        self.assertTrue(all(p["agent_role"] != p["target_domain"] for p in plan))

        mat = competency_matrix.build_competency_matrix(
            primary_results=[{"role": "development", "ok": True, "cloud_calls": 0}],
            cross_domain_results=[{"agent_role": "development", "target_domain": "quant", "ok": True, "cloud_calls": 0}],
            hybrid_results=[{"role": "development", "ok": True}],
        )
        self.assertEqual(len(mat["matrix_12x12"]), 12)
        self.assertEqual(mat["matrix_12x12"]["development"]["development"]["status"], "PROVEN")
        self.assertEqual(mat["matrix_12x12"]["development"]["quant"]["status"], "PROVEN")
        # Unevaluated cell stays honestly PENDING
        self.assertEqual(mat["matrix_12x12"]["cloud"]["release"]["status"], "PENDING")
        self.assertEqual(mat["global_metrics"]["cloud_calls_in_local_matrix"], 0)


if __name__ == "__main__":
    unittest.main()
