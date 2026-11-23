"""Offline regression tests for native Ollama TEL99 code missions."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

# The existing TEL99 worker imports local_codex and protocol as legacy top-level
# modules. Its normal isolated CLI sets these paths before importing worker code.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "agents"))
sys.path.insert(0, str(ROOT / "scripts" / "agents" / "automation"))

from scripts.agents.automation import local_codegen, local_model_routing, prepare_local_code
from scripts.agents.automation.ollama_native import OllamaNativeProvider
from scripts.agents.native.provider import ProviderError


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/agents/TEL99_QWEN_REPAIR_QUEUE_20261123.json"
GEMMA = {
    "id": "local/ollama-gemma4-e4b",
    "model": "gemma4:e4b-tel99-8k",
    "port": 11434,
}
QWEN = {
    "id": "local/ollama-qwen2.5-coder-7b",
    "model": "qwen2.5-coder:7b",
    "port": 11434,
}
REASONER = {
    "id": "local/ollama-qwen3.5-9b",
    "model": "qwen3.5:9b-q4_K_M",
    "port": 11434,
}


class _Response(io.BytesIO):
    status = 200


class _Client:
    def __init__(self, response):
        self.response = response
        self.payload = None
        self.url = None

    def open(self, request, timeout):
        self.url = request.full_url
        self.payload = json.loads(request.data)
        assert timeout == 40
        return _Response(json.dumps(self.response).encode("utf-8"))


class OllamaNativeCodeTests(unittest.TestCase):
    def setUp(self):
        memory = patch.object(local_model_routing, "available_memory_mib", return_value=12_000)
        memory.start()
        self.addCleanup(memory.stop)

    def test_fixed_model_checks_host_ram_before_starting_ollama(self):
        with (patch.object(local_model_routing, "available_memory_mib", return_value=7000),
              patch("scripts.agents.automation.ollama_native.build_opener") as opener):
            with self.assertRaisesRegex(ProviderError, "physical memory"):
                OllamaNativeProvider(model=GEMMA["model"]).complete(system="Code only", prompt="Fix function")
            opener.assert_not_called()

    def test_provider_calls_only_native_loopback_without_tools(self):
        client = _Client({"model": GEMMA["model"], "response": "def test():\n    return 42"})
        with patch("scripts.agents.automation.ollama_native.build_opener", return_value=client) as mocked:
            provider = OllamaNativeProvider(model=GEMMA["model"], timeout=40, max_tokens=256)
            answer = provider.complete(system="Only code", prompt="Implement a function")
        self.assertEqual(answer, "def test():\n    return 42")
        self.assertEqual(client.url, "http://127.0.0.1:11434/api/generate")
        self.assertEqual(client.payload["model"], GEMMA["model"])
        self.assertEqual(client.payload["stream"], False)
        self.assertIs(client.payload["think"], False)
        self.assertEqual(client.payload["keep_alive"], "0s")
        self.assertEqual(client.payload["options"]["num_ctx"], 8192)
        self.assertEqual(client.payload["options"]["num_predict"], 256)
        self.assertNotIn("tools", client.payload)
        self.assertTrue(mocked.called)

    def test_coder_without_thinking_override_and_qwen35_with_override(self):
        for model, expects_think in ((QWEN["model"], False), (REASONER["model"], True)):
            with self.subTest(model=model):
                client = _Client({"model": model, "response": "def done():\n    return True"})
                with patch("scripts.agents.automation.ollama_native.build_opener", return_value=client):
                    answer = OllamaNativeProvider(model=model, timeout=40).complete(
                        system="Only code", prompt="Return the correct function"
                    )
                self.assertTrue(answer.startswith("def done():"))
                self.assertEqual(client.payload.get("think"), False if expects_think else None)

    def test_empty_final_answer_does_not_turn_reasoning_into_code(self):
        client = _Client({
            "model": GEMMA["model"],
            "response": "",
            "thinking": "Internal reasoning text must never reach Docker or logs",
            "done_reason": "length",
            "eval_count": 768,
        })
        with patch("scripts.agents.automation.ollama_native.build_opener", return_value=client):
            provider = OllamaNativeProvider(model=GEMMA["model"], timeout=40)
            response = provider.complete(system="Only final code", prompt="Fix function")
        self.assertEqual(response, "")
        self.assertEqual(provider.last_metadata, {
            "done_reason": "length",
            "eval_count": 768,
            "thinking_present": True,
        })

    def test_local_codegen_reports_empty_reason_without_exposing_thinking(self):
        original = next(row for row in json.loads(REGISTRY.read_bytes())["missions"]
                        if row["function"] == "load_json")
        mission = {**original, "model": GEMMA["model"], "port": 11434}
        fake_source = "def load_json(path):\n    return {}\n"
        with (patch.object(local_codegen.sandbox, "require_local_image"),
              patch.object(local_codegen, "_source", return_value=fake_source),
              patch.object(local_codegen, "OllamaNativeProvider") as provider_class):
            provider = provider_class.return_value
            provider.complete.return_value = ""
            provider.last_metadata = {
                "done_reason": "length", "eval_count": 768, "thinking_present": True
            }
            with self.assertRaises(local_codegen.GenerationBlocked) as raised:
                local_codegen.execute(mission)
        self.assertEqual(raised.exception.feedback, {"kind": "empty-completion"})
        self.assertIn("done_reason=length", raised.exception.reason)
        self.assertIn("thinking_present=True", raised.exception.reason)
        self.assertNotIn("Internal reasoning", raised.exception.reason)

    def test_wrong_served_model_and_unknown_model_fail_closed(self):
        with self.assertRaises(ProviderError):
            OllamaNativeProvider(model="injected:remote")
        with patch("scripts.agents.automation.ollama_native.build_opener", return_value=_Client({
            "model": "different-model", "response": "def x(): pass"
        })):
            with self.assertRaisesRegex(ProviderError, "unapproved model"):
                OllamaNativeProvider(model=GEMMA["model"], timeout=40).complete(
                    system="code", prompt="x"
                )

    def test_native_bindings_allow_only_pinned_models_and_local_port(self):
        local_model_routing.validate_candidates([GEMMA, QWEN, REASONER])
        for bad in (
            {**GEMMA, "port": 18089},
            {**GEMMA, "model": QWEN["model"]},
            {**GEMMA, "model": "unapproved:tag"},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                local_model_routing.validate_candidates([bad])

    def test_probe_ollama_installed_models_and_selected_model(self):
        def probe(port, path):
            self.assertEqual((port, path), (11434, "/api/tags"))
            return {"models": [
                {"name": GEMMA["model"]}, {"name": QWEN["model"]},
                {"name": REASONER["model"]},
            ]}
        with patch.object(local_model_routing, "_probe_json", side_effect=probe), patch.object(
            local_model_routing, "available_memory_mib", return_value=12_000
        ):
            self.assertTrue(local_model_routing.check_selected(GEMMA))
            self.assertTrue(local_model_routing.check_selected(QWEN))
            self.assertTrue(local_model_routing.check_selected(REASONER))
            self.assertEqual(local_model_routing._probe_ollama("not-installed")[0], None)

    def test_registry_preparation_reuses_historical_tests_and_new_ids(self):
        source = json.loads(REGISTRY.read_bytes())["missions"]
        fixed = prepare_local_code.prepare(source, "nativefixed", "fixed", [GEMMA], [])
        routed = prepare_local_code.prepare(
            source, "nativeroute", "routed", [GEMMA, QWEN, REASONER],
            ["qwen-repair-metadata-shape-20261123"],
        )
        self.assertEqual(len(fixed["missions"]), 5)
        self.assertEqual(len(routed["missions"]), 6)
        self.assertEqual([m["test"] for m in fixed["missions"]], [m["test"] for m in source])
        self.assertEqual([m["base_sha"] for m in fixed["missions"]], [m["base_sha"] for m in source])
        self.assertEqual(fixed["missions"][0]["model"], GEMMA["model"])
        self.assertEqual(fixed["missions"][0]["port"], 11434)
        for candidate in (QWEN, REASONER):
            other = prepare_local_code.prepare(source, "fixed" + candidate["id"].split("/")[-1].replace(".", ""), "fixed", [candidate], [])
            self.assertEqual(len(other["missions"]), 5)
            self.assertEqual({m["model"] for m in other["missions"]}, {candidate["model"]})
            self.assertEqual({m["port"] for m in other["missions"]}, {11434})
        for mission in fixed["missions"]:
            local_codegen.validate_scope(mission)
        for mission in routed["missions"]:
            local_codegen.validate_scope(mission)
        self.assertNotEqual(fixed["approvals"], routed["approvals"])
        self.assertEqual(
            hashlib.sha256(REGISTRY.read_bytes()).hexdigest(),
            "dfc7ae6328f82894b97b2a5a6d7676096fb643d289bc50cba704b30a7ca01bf9",
        )


if __name__ == "__main__":
    unittest.main()
