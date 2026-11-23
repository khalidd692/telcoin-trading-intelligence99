"""Fail-closed unit tests for selecting models from pinned historical Docker proof."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.agents.automation import evidence_route
from scripts.agents.automation.compare_local_code import _case_key

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/agents/TEL99_QWEN_REPAIR_QUEUE_20261123.json"
PIN = "dfc7ae6328f82894b97b2a5a6d7676096fb643d289bc50cba704b30a7ca01bf9"
GEMMA_PIN = "463badf6cbde82728da958ce2aed3c834ca749eca5ff4dc8c93804fff9f4c062"
CODER_PIN = "c20e346be8f2368ddd055d4af99361c926230ad4fb66131d1e68bfab59622617"


def observation(accepted, seconds=25.0, attributable=True):
    return {"accepted": accepted, "attempts": [{
        "generation_seconds": seconds, "attributed_model_outcome": attributable,
    }]}


def fixtures():
    originals = json.loads(SOURCE.read_bytes())["missions"]
    left, right = {}, {}
    gm, qw = {}, {}
    for i, item in enumerate(originals, 1):
        key = _case_key(item)
        left[key] = {**item, "id": "gemma-historical-%02d" % i}
        right[key] = {**item, "id": "coder-historical-%02d" % i}
        gm[key] = observation(i in (1, 2, 3), seconds=20.0)
        qw[key] = observation(i in (2, 4, 5), seconds=40.0)
    sessions = [
        SimpleNamespace(pin=GEMMA_PIN, model="gemma4:e4b-tel99-8k"),
        SimpleNamespace(pin=CODER_PIN, model="qwen2.5-coder:7b"),
    ]
    return sessions, [left, right], [gm, qw]


class EvidenceRoutingTests(unittest.TestCase):
    def test_complementary_verified_outcomes_prepare_five_scoped_contracts(self):
        with patch.object(evidence_route, "_checked_sessions", return_value=fixtures()):
            registry, plan = evidence_route.prepare_from_evidence(
                (SOURCE, PIN), "proven", "gemma-session", GEMMA_PIN, "coder-session", CODER_PIN,
            )
        chosen = {m["function"]: m["model"] for m in registry["missions"]}
        self.assertEqual(chosen, {
            "git_changes": "gemma4:e4b-tel99-8k",
            "load_json": "gemma4:e4b-tel99-8k",
            "inventory_view": "gemma4:e4b-tel99-8k",
            "kv_env": "qwen2.5-coder:7b",
            "load_tasks": "qwen2.5-coder:7b",
        })
        self.assertEqual(len(registry["missions"]), 5)
        self.assertEqual(len(registry["approvals"]), 5)
        self.assertEqual(len(plan["decisions"]), 5)
        self.assertTrue(all(m["port"] == 11434 for m in registry["missions"]))
        self.assertTrue(all(d["selected_session_registry_sha256"] in (GEMMA_PIN, CODER_PIN)
                            for d in plan["decisions"]))

    def test_unverified_or_missing_success_blocks_whole_registry(self):
        sessions, paired, observations = fixtures()
        target = next(k for k, m in paired[0].items() if m["function"] == "kv_env")
        observations[1][target] = observation(False)
        with patch.object(evidence_route, "_checked_sessions",
                          return_value=(sessions, paired, observations)):
            with self.assertRaisesRegex(ValueError, "no independently verified"):
                evidence_route.prepare_from_evidence(
                    (SOURCE, PIN), "blocked", "gemma-session", GEMMA_PIN, "coder-session", CODER_PIN,
                )

    def test_success_without_attributable_independent_proof_is_refused(self):
        sessions, paired, observations = fixtures()
        target = next(k for k, m in paired[0].items() if m["function"] == "load_tasks")
        observations[1][target] = observation(True, attributable=False)
        with patch.object(evidence_route, "_checked_sessions",
                          return_value=(sessions, paired, observations)):
            with self.assertRaisesRegex(ValueError, "no independently verified"):
                evidence_route.prepare_from_evidence(
                    (SOURCE, PIN), "blocked", "gemma-session", GEMMA_PIN, "coder-session", CODER_PIN,
                )

    def test_final_verified_success_can_follow_earlier_empty_generation(self):
        repaired = {"accepted": True, "attempts": [
            {"generation_seconds": 20.0, "attributed_model_outcome": False},
            {"generation_seconds": 30.0, "attributed_model_outcome": True},
        ]}
        rejected = observation(False)
        self.assertEqual(evidence_route._winner((repaired, rejected)), 0)

    def test_tampered_historical_source_refused_before_evidence(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            evidence_route._read_pinned_source(SOURCE, "0" * 64)

    def test_fewer_attempts_preferred_over_faster_unreliable_model(self):
        first = {"accepted": True, "attempts": [
            {"generation_seconds": 10, "attributed_model_outcome": True},
            {"generation_seconds": 10, "attributed_model_outcome": True},
        ]}
        second = observation(True, seconds=60)
        self.assertEqual(evidence_route._winner((first, second)), 1)


if __name__ == "__main__":
    unittest.main()
