"""Offline safety and integration tests for the existing 3-agent TEL99 pilot.

No Ollama request or Docker run occurs in this suite.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "agents"))
sys.path.insert(0, str(ROOT / "scripts" / "agents" / "automation"))

from scripts.agents.automation import evidence_route, local_codegen, local_team
from scripts.agents.native.provider import ProviderError
from scripts.agents.team_config import role_catalog
from tests.test_evidence_route import fixtures, SOURCE, PIN, GEMMA_PIN, CODER_PIN

HISTORICAL = json.loads(SOURCE.read_bytes())["missions"]
TEAM = local_team.TEAM
FUNCTION = "def load_json(path):\n    return {}\n"
FIX = "def load_json(path):\n    return {'ok': True}\n"


def mission(**changes):
    row = next(m for m in HISTORICAL if m["function"] == "load_json").copy()
    row["model"] = "gemma4:e4b-tel99-8k"
    row["port"] = 11434
    row["team"] = TEAM.copy()
    row.update(changes)
    return row


def advice():
    note = "Check JSON types after parsing. Return a dictionary only."
    return {
        "role": "tel99-analyst", "model": local_team.ANALYST_MODEL,
        "kind": "read-only-advice", "analysis": note,
        "sha256": hashlib.sha256(note.encode()).hexdigest(),
    }


class ExistingTeamPilotTests(unittest.TestCase):
    def test_canonical_catalog_has_three_active_and_nine_reserved(self):
        specs = role_catalog()
        active = {s.name for s in specs.values() if s.active}
        reserved = {s.name for s in specs.values() if not s.active}
        self.assertEqual(active, set(TEAM))
        self.assertEqual(len(reserved), 9)

    def test_team_is_explicitly_sealed_and_invalid_roles_cannot_enter(self):
        good = mission()
        local_codegen.validate_scope(good)
        for bad in (
            mission(team=["tel99-dev", "tel99-verifier"]),
            mission(team=["tel99-analyst", "tel99-dev", "tel99-release"]),
            mission(team="tel99-analyst"),
        ):
            with self.subTest(bad=bad["team"]), self.assertRaises(ValueError):
                local_codegen.validate_scope(bad)
        routed = mission()
        routed.pop("model")
        routed.pop("port")
        routed["routing"] = {"candidates": [
            {"id": "local/ollama-gemma4-e4b", "model": "gemma4:e4b-tel99-8k", "port": 11434}
        ]}
        with self.assertRaises(ValueError):
            local_codegen.validate_scope(routed)

    def test_analyst_executes_one_real_model_provider_call_without_tools(self):
        with patch.object(local_team, "OllamaNativeProvider") as provider:
            provider.return_value.complete.return_value = advice()["analysis"]
            result = local_team.analyze(mission(), FUNCTION)
        self.assertEqual(result, advice())
        provider.assert_called_once_with(
            model=local_team.ANALYST_MODEL, timeout=55, max_tokens=256
        )
        self.assertIn("code-review note", provider.return_value.complete.call_args.kwargs["prompt"])
        self.assertIn("No tool use", provider.return_value.complete.call_args.kwargs["system"])
        self.assertNotIn("trade order", provider.return_value.complete.call_args.kwargs["system"])

    def test_analyst_rejects_empty_or_code_shaped_notes(self):
        for output in ("", "def load_json(x):\n    return {}", "x" * 1300):
            with self.subTest(output=output[:20]), patch.object(
                local_team, "OllamaNativeProvider"
            ) as provider:
                provider.return_value.complete.return_value = output
                with self.assertRaises(ProviderError):
                    local_team.analyze(mission(), FUNCTION)

    def test_developer_receives_untrusted_advice_and_emits_bound_trace(self):
        m = mission()
        with (patch.object(local_codegen.sandbox, "require_local_image"),
              patch.object(local_codegen, "_source", return_value=FUNCTION),
              patch.object(local_codegen.local_team, "analyze", return_value=advice()) as analyst,
              patch.object(local_codegen, "OllamaNativeProvider") as provider,
              patch.object(local_codegen.local_model_routing, "available_memory_mib",
                           return_value=2048)):
            provider.return_value.complete.return_value = FIX
            receipt = local_codegen.execute(m)
        analyst.assert_called_once()
        self.assertTrue(local_team.valid_trace(m, receipt))
        self.assertIn("Read-only analyst advice", provider.return_value.complete.call_args.kwargs["prompt"])
        self.assertIn(advice()["analysis"], provider.return_value.complete.call_args.kwargs["prompt"])
        self.assertEqual(receipt["agent_trace"]["developer"]["role"], "tel99-dev")

    def test_docker_verifier_refuses_missing_or_tampered_analyst_trace(self):
        m = mission()
        result = {
            "artifact": FIX, "sha256": hashlib.sha256(FIX.encode()).hexdigest(),
            "specialist_id": "tel99-dev", "provider": local_codegen.PROVIDER,
            "model": m["model"],
        }
        with tempfile.TemporaryDirectory() as temp:
            report = local_codegen.verify(m, result, Path(temp))
        self.assertFalse(report["ok"])
        self.assertEqual(report["checks"], [{"name": "bounded-model-receipt", "ok": False}])
        result["agent_trace"] = local_team.trace(advice(), developer_model=m["model"], artifact=FIX)
        self.assertTrue(local_team.valid_trace(m, result))
        result["agent_trace"]["analyst"]["analysis"] += " fabricated"
        self.assertFalse(local_team.valid_trace(m, result))

    def test_historical_evidence_seals_pilot_only_when_opted_in(self):
        with patch.object(evidence_route, "_checked_sessions", return_value=fixtures()):
            registry, plan = evidence_route.prepare_from_evidence(
                (SOURCE, PIN), "teamverify", "gemma-session", GEMMA_PIN, "coder-session", CODER_PIN,
                team=True,
            )
        self.assertEqual(len(registry["missions"]), 5)
        self.assertTrue(all(m["team"] == TEAM for m in registry["missions"]))
        self.assertEqual(len(plan["decisions"]), 5)
        self.assertEqual(
            {m["function"]: m["model"] for m in registry["missions"]},
            {"git_changes": "gemma4:e4b-tel99-8k",
             "load_json": "gemma4:e4b-tel99-8k",
             "inventory_view": "gemma4:e4b-tel99-8k",
             "kv_env": "qwen2.5-coder:7b",
             "load_tasks": "qwen2.5-coder:7b"},
        )


if __name__ == "__main__":
    unittest.main()
