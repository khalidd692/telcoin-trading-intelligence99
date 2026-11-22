"""Serve the cockpit over loopback with an explicit list of published files."""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile

from ..project_kit import load as load_kit
from . import REPO_RE, read_snapshot, snapshot

ASSETS = Path(__file__).resolve().parent
FILES = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
         "/style.css": ("style.css", "text/css")}
DEFAULT_REPO = "khalidd692/telcoin-trading-intelligence99"


def demo():
    from ..automation.autonomy_runtime import Runtime, seal
    from ..intelligence.capabilities import plan
    from ..protocol.handoff import HandoffLedger

    def mission(mid, text, dependencies):
        sha = hashlib.sha256(text.encode()).hexdigest()
        return dict(id=mid, project="synthetic", owner="kilo", specialist="tel99-analyst",
                    priority="P0", dependencies=dependencies, synthetic_data=True,
                    objective=text, expected_sha256=sha)

    def fixture(m):
        return {"artifact": m["objective"], "sha256": m["expected_sha256"],
                "specialist_id": m["specialist"], "provider_evidence": {
                    "cost_usd": "0", "http_status": 200, "catalog_sha256": "a" * 64,
                    "response_sha256": "b" * 64}}

    first = mission("analyse-fixture", "READY", [])
    second = mission("verification-fixture", "PASS", [first["id"]])
    with tempfile.TemporaryDirectory(prefix="cockpit-demo-") as directory:
        runtime = Runtime(directory, executor=fixture)
        runtime.run_queue([first, second], seal([first, second]))
        status = runtime.status()
        ledger = HandoffLedger(runtime.store)
        for mid, row in status["missions"].items():
            ledger.record_handoff(task_id=mid, owner="fixture", status=row["status"])
        handoffs = {"events": ledger.events()}
    prepared = plan({
        "project": "synthetic", "mission_id": "analyse-fixture",
        "approved_models": ["openhands/deepseek-v4.1-flash"],
        "budget": {"max_calls": 3, "quota_remaining": 15, "reserve": 12,
                   "max_seconds": 30, "max_context_tokens": 4500},
        "steps": [{"role": role, "estimated_tokens": 1500, "estimated_seconds": 10}
                  for role in ("quant", "development", "quality")],
    })
    return snapshot(status=status, plan=prepared, handoffs=handoffs,
                    repository=DEFAULT_REPO, mode="demo")


def handler(read):
    class CockpitHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
                self.send_error(403)
                return
            if self.path == "/snapshot.json":
                content = json.dumps(read(), ensure_ascii=True).encode()
                content_type = "application/json"
            elif self.path in FILES:
                filename, content_type = FILES[self.path]
                content = (ASSETS / filename).read_bytes()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; script-src 'self'; style-src 'self'; "
                             "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format, *args):
            # Local reports and request strings are never echoed into a console log.
            return

    return CockpitHandler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--status", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--pulls", type=Path)
    parser.add_argument("--handoffs", type=Path)
    parser.add_argument("--repository")
    parser.add_argument("--kit", type=Path)
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535 or (args.repository and not REPO_RE.fullmatch(args.repository)):
        parser.error("port ou dépôt invalide")
    if args.kit and args.repository:
        parser.error("--kit fournit le dépôt")
    if args.demo and (args.status or args.plan or args.pulls or args.handoffs or args.kit):
        parser.error("--demo n'utilise pas de fichiers opérateur")
    repository, project = args.repository or DEFAULT_REPO, None
    if args.kit:
        try:
            profile = load_kit(args.kit).profile
        except (OSError, ValueError, RecursionError) as exc:
            parser.error(str(exc))
        repository, project = profile["repository"], profile["project"]
    if args.demo:
        data = demo()

        def read():
            return data
    else:
        def read():
            return snapshot(status=read_snapshot(args.status), plan=read_snapshot(args.plan),
                            pulls=read_snapshot(args.pulls), handoffs=read_snapshot(args.handoffs),
                            repository=repository, project=project)

    with ThreadingHTTPServer(("127.0.0.1", args.port), handler(read)) as server:
        print(f"http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
