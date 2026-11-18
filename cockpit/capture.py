#!/usr/bin/env python3
"""Capture the cockpit screenshots with headless chromium (local preview only).

Start the preview server first (``python3 cockpit/serve.py``), then run this.
It writes the two PNGs referenced by ``cockpit/README.md``.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "docs" / "cockpit"


def shot(url: str, out: pathlib.Path, size: str, scale: str = "1") -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "chromium", "--headless", "--no-sandbox", "--disable-gpu",
        "--hide-scrollbars", f"--force-device-scale-factor={scale}",
        f"--window-size={size}", f"--screenshot={out}", url,
    ]
    subprocess.run(cmd, check=False, capture_output=True)
    ok = out.exists() and out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    print(("OK   " if ok else "FAIL ") + str(out))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture cockpit screenshots.")
    parser.add_argument("--url", default="http://127.0.0.1:12000/index.html")
    args = parser.parse_args(argv)
    shot(args.url, OUT / "cockpit-mobile-390.png", "390,2600", "2")
    shot(args.url, OUT / "cockpit-desktop-1100.png", "1100,2200", "1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
