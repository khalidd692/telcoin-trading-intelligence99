import contextlib
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import unittest
from unittest.mock import patch

from scripts.agents.automation import local_model_routing as routing


SMALL = "local/llama-qwen2.5-3b", "qwen2.5-3b-instruct"
LARGE = "local/llama-qwen2.5-coder-7b", "qwen2.5-coder-7b-instruct"
SOURCE = "def lookup(items):\n    return items[0]\n"


def binding(model, port):
    return {"id": model[0], "model": model[1], "port": port}


def mission(*candidates):
    return {"objective": "Correct the lookup function.", "max_attempts": 2,
            "routing": {"candidates": list(candidates)}}


@contextlib.contextmanager
def endpoint(models, *, healthy=True, model_status=200, body_delay=0):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            if self.path == "/health":
                status = 200 if healthy else 503
                payload = {"status": "ok" if healthy else "loading model"}
            else:
                status = model_status
                payload = {"data": [{"id": model} for model in models]}
            body = json.dumps(payload).encode()
            self.send_response(status)
            if status == 302:
                self.send_header("Location", "/unexpected-redirect")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body_delay and self.path == "/v1/models":
                for byte in body:
                    try:
                        self.wfile.write(bytes((byte,)))
                        self.wfile.flush()
                    except OSError:
                        break
                    time.sleep(body_delay)
            else:
                self.wfile.write(body)

        def log_message(self, *_args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, args=(0.01,), daemon=True)
        thread.start()
        try:
            yield server.server_port, requests
        finally:
            server.shutdown()
            thread.join(timeout=2)


class LocalModelRoutingTests(unittest.TestCase):
    def test_candidates_pin_catalog_id_exact_api_id_and_port(self):
        small = binding(SMALL, 18089)
        routing.validate_candidates([small, binding(LARGE, 18089)])
        for candidates in (
            [], [small, binding(SMALL, 18090)], [{**small, "model": LARGE[1]}],
            [{**small, "id": "gpt-5.6"}], [{**small, "port": True}], [{**small, "port": 80}],
            [{**small, "url": "http://localhost:18089"}],
        ):
            with self.subTest(candidates=candidates), self.assertRaises(ValueError):
                routing.validate_candidates(candidates)

    def test_one_endpoint_only_verifies_the_exact_current_model(self):
        models = [SMALL[1]]
        with endpoint(models) as (port, requests), patch.object(
                routing, "available_memory_mib", return_value=2048):
            small, large = binding(SMALL, port), binding(LARGE, port)
            result = routing.choose(mission(small, large), SOURCE)
            self.assertEqual(result["selection"], small)
            self.assertEqual(result["decision"]["chosen"], SMALL[0])
            self.assertEqual(result["available_memory_mib"], 2048)
            self.assertEqual(requests, ["/health", "/v1/models"])
            entries = {row["id"]: row for row in result["inventory"]}
            self.assertTrue(entries[SMALL[0]]["verified"])
            self.assertFalse(entries[LARGE[0]]["verified"])
            self.assertGreaterEqual(entries[SMALL[0]]["probe_rtt_ms"], 0)
            self.assertIn("quality_prior", entries[SMALL[0]])
            models[:] = [LARGE[1]]
            self.assertFalse(routing.check_selected(small))
            self.assertTrue(routing.check_selected(large))

    def test_redirect_offline_ambiguity_and_oversized_reply_fail_closed(self):
        for models, options, expected_paths in (
            ([SMALL[1]], {"healthy": False}, ["/health"]),
            ([SMALL[1]], {"model_status": 302}, ["/health", "/v1/models"]),
            ([SMALL[1], LARGE[1]], {}, ["/health", "/v1/models"]),
            (["x" * 17_000], {}, ["/health", "/v1/models"]),
        ):
            with (
                self.subTest(options=options, count=len(models)),
                endpoint(models, **options) as (port, requests),
                patch.object(routing, "available_memory_mib", return_value=2048),
            ):
                result = routing.choose(mission(binding(SMALL, port)), SOURCE)
                self.assertIsNone(result["selection"])
                self.assertFalse(result["inventory"][0]["verified"])
                self.assertEqual(requests, expected_paths)

    def test_loaded_large_model_only_needs_available_memory_reserve(self):
        with endpoint([LARGE[1]]) as (port, _), patch.object(
                routing, "available_memory_mib", return_value=1536):
            large = binding(LARGE, port)
            result = routing.choose(mission(large), SOURCE, minimum_memory_mib=4096)
            self.assertEqual(result["selection"], large)
            self.assertGreater(result["inventory"][0]["model_memory_mib"], 1536)
            self.assertIsNone(routing.choose(mission(large), SOURCE, exclude=(LARGE[0],))["selection"])

    def test_skips_large_generation_if_two_approved_large_servers_are_ready(self):
        another = "local/llama-test-large", "fixture-coder-8b"
        catalog = routing.catalog
        spec = replace(catalog.by_id(LARGE[0]), id=another[0], served_ids=(another[1],))
        with (
            endpoint([LARGE[1]]) as (port_large, _),
            endpoint([another[1]]) as (port_another, _),
            patch.object(catalog, "MODEL_CATALOG", (*catalog.MODEL_CATALOG, spec)),
            patch.object(routing, "available_memory_mib", return_value=2048),
        ):
            approved = mission(binding(LARGE, port_large), binding(another, port_another))
            result = routing.choose(approved, SOURCE, exclude=(another[0],))
            self.assertIsNone(result["selection"])
            self.assertIn("more than one large", result["inventory"][0]["reason"])

    def test_unknown_or_low_available_memory_refuses_generation(self):
        with endpoint([SMALL[1]]) as (port, _):
            small = binding(SMALL, port)
            for available in (None, 1):
                with self.subTest(available=available), patch.object(
                        routing, "available_memory_mib", return_value=available):
                    result = routing.choose(mission(small), SOURCE)
                    self.assertIsNone(result["selection"])
                    self.assertFalse(result["inventory"][0]["eligible"])

    def test_ast_complexity_is_routed_differently_from_simple_lookup(self):
        complex_source = "def lookup(items):\n" + "    if items:\n        items = items[1:]\n" * 7 + "    return items\n"
        with endpoint([SMALL[1]]) as (port, _), patch.object(
                routing, "available_memory_mib", return_value=2048):
            small = binding(SMALL, port)
            simple = routing.choose(mission(small), SOURCE)
            complex_result = routing.choose(mission(small), complex_source)
            self.assertEqual(simple["decision"]["difficulty"], "easy")
            self.assertEqual(complex_result["decision"]["difficulty"], "hard")
            self.assertIsNone(complex_result["selection"])
            self.assertFalse(complex_result["inventory"][0]["eligible"])

    def test_probe_has_a_whole_response_timeout(self):
        with (
            endpoint([SMALL[1]], body_delay=0.03) as (port, requests),
            patch.object(routing, "PROBE_TIMEOUT_SECONDS", 0.3),
            patch.object(routing, "available_memory_mib", return_value=2048),
        ):
            result = routing.choose(mission(binding(SMALL, port)), SOURCE)
            self.assertEqual(requests, ["/health", "/v1/models"])
            self.assertIsNone(result["selection"])

    def test_recent_generation_time_changes_rank_separately_from_probe_latency(self):
        with (
            endpoint([SMALL[1]]) as (port_small, _),
            endpoint([LARGE[1]]) as (port_large, _),
            patch.object(routing, "available_memory_mib", return_value=2048),
        ):
            small, large = binding(SMALL, port_small), binding(LARGE, port_large)
            approved = mission(small, large)
            self.assertEqual(routing.choose(approved, SOURCE)["selection"], small)

            result = routing.choose(approved, SOURCE, measured_seconds={
                "easy": {SMALL[0]: 65.5, LARGE[0]: 20},
            })
            self.assertEqual(result["selection"], large)
            rows = {row["id"]: row for row in result["inventory"]}
            self.assertEqual(rows[SMALL[0]]["generation_seconds_observed"], 65.5)
            self.assertEqual(rows[SMALL[0]]["latency_tier_prior"], "fast")
            self.assertEqual(rows[SMALL[0]]["latency_tier_effective"], "slow")
            self.assertEqual(rows[LARGE[0]]["latency_tier_effective"], "fast")
            self.assertGreaterEqual(rows[LARGE[0]]["probe_rtt_ms"], 0)

            invalid = routing.choose(approved, SOURCE, measured_seconds={
                "easy": {SMALL[0]: True, LARGE[0]: float("inf")},
            })
            self.assertEqual(invalid["selection"], small)
            self.assertTrue(all(row["generation_seconds_observed"] is None for row in invalid["inventory"]))
            unrelated = routing.choose(approved, SOURCE, measured_seconds={
                "hard": {SMALL[0]: 65.5, LARGE[0]: 20},
            })
            self.assertEqual(unrelated["selection"], small)
            self.assertTrue(all(row["generation_seconds_observed"] is None for row in unrelated["inventory"]))
