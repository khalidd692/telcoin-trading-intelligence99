from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest

from scripts.agents import cockpit
from scripts.agents.cockpit.__main__ import handler


class CockpitTests(unittest.TestCase):
    def test_projects_roles_receipts_and_unknowns(self):
        report = cockpit.snapshot(
            status={"state": "IDLE", "missions": {"example": {
                "id": "example", "project": "atlas-lab", "status": "ACCEPTED",
                "verification": {"ok": True, "artifact_sha256": "a" * 64},
            }}, "github_receipts": {"kilo-github/outbox/example/ACK":
                "https://github.com/acme/atlas/issues/1#issuecomment-7"}},
            pulls=[{"number": 12, "state": "open", "draft": True,
                    "html_url": "https://github.com/acme/atlas/pull/12"}],
            repository="acme/atlas",
        )
        self.assertEqual(len(report["roles"]), 12)
        self.assertEqual(report["missions"][0]["state"], "ACCEPTED")
        self.assertEqual(report["events"][0]["phase"], "ACK")
        self.assertEqual(report["pulls"][0]["number"], 12)
        self.assertIsNone(report["budget"]["quota"])
        self.assertTrue(all(row["activity"] is None for row in report["roles"]))

    def test_untrusted_output_does_not_cross_projection(self):
        result = cockpit.snapshot(
            status={"state": "x-token-secret", "last_observed": {"BLOCKER": "<private>"},
                    "missions": {"<script>": {"id": "<script>", "status": "ACCEPTED",
                        "result": {"credentials": "x-token-secret"}}},
                    "github_receipts": {"kilo-github/outbox/safe/ACK":
                        "https://github.com.evil.test/acme/atlas/issues/1#issuecomment-7"}},
            repository="acme/atlas",
        )
        rendered = json.dumps(result)
        for value in ("<script>", "<private>", "x-token-secret", "evil.test"):
            self.assertNotIn(value, rendered)
        self.assertIsNone(result["state"])

    def test_reader_fails_closed_on_bad_or_oversized_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "report.json"
            path.write_text("{", encoding="utf-8")
            self.assertIsNone(cockpit.read_snapshot(path))
            path.write_bytes(b" " * (cockpit.MAX_JSON + 1))
            self.assertIsNone(cockpit.read_snapshot(path))

    def test_http_serves_only_public_assets_and_snapshot(self):
        data = cockpit.snapshot(repository="acme/atlas")
        with ThreadingHTTPServer(("127.0.0.1", 0), handler(lambda: data)) as server:
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                with_connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                self.addCleanup(with_connection.close)
                for method, route, headers, expected in (
                    ("GET", "/snapshot.json", {}, 200),
                    ("GET", "/../.env", {}, 404),
                    ("GET", "/", {"Host": "rebind.test"}, 403),
                    ("POST", "/snapshot.json", {}, 501),
                ):
                    with self.subTest(route=route, method=method):
                        with_connection.request(method, route, headers=headers)
                        response = with_connection.getresponse()
                        self.assertEqual(response.status, expected)
                        if expected == 200:
                            self.assertIn("frame-ancestors 'none'",
                                          response.getheader("Content-Security-Policy"))
                            self.assertEqual(json.loads(response.read()), data)
                        else:
                            response.read()
            finally:
                server.shutdown()
                worker.join(timeout=3)
