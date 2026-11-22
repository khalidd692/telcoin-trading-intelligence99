#!/usr/bin/env python3
"""Serve the TEL99 cockpit locally for preview (read-only, no secrets).

A tiny static server that serves ``cockpit/`` on a port. It exists only to let
a human open the cockpit on a phone/desktop before any hosting decision. It
serves files as-is and never runs the build script, so no token is involved.

Usage::

    python3 cockpit/serve.py --port 12000
"""

from __future__ import annotations

import argparse
import functools
import http.server
import pathlib
import socketserver

HERE = pathlib.Path(__file__).resolve().parent


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # No caching so a rebuilt data.json is picked up immediately.
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def log_message(self, *args):  # keep the console quiet
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the TEL99 cockpit.")
    parser.add_argument("--port", type=int, default=12000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args(argv)
    handler = functools.partial(Handler, directory=str(HERE))
    with socketserver.TCPServer((args.host, args.port), handler) as httpd:
        print(f"[cockpit] serving {HERE} on http://{args.host}:{args.port}/")
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
