#!/usr/bin/env python3
"""
Produit la version resume d'un fichier de resultats de backtest.

La version resume retire les tableaux de detail volumineux (episodes,
retournements manques/detectes), qui sont regenerables a l'identique par
`run_backtest.py` depuis le cache local. Elle conserve l'empreinte du
detecteur, le protocole, la couverture des donnees et l'ensemble des
statistiques fondees sur lesquelles le rapport s'appuie.

Usage :
    python scripts/backtest/summarize_results.py backtest_results_p1.json \\
        --output backtest_results_p1_summary.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
from pathlib import Path

BULKY_KEYS = ("episodes_detail", "missed_reversals_detail", "detected_reversals_detail")


def summarize(payload: dict) -> dict:
    summary = json.loads(json.dumps(payload))
    for res in summary.get("results", {}).values():
        for crit in res.get("criteria", {}).values():
            for key in BULKY_KEYS:
                crit.pop(key, None)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--output", default=None)
    parser.add_argument("--gzip", dest="gzip_copy", action="store_true",
                        help="produit en plus une archive .json.gz du fichier complet")
    args = parser.parse_args()

    source = Path(args.input)
    payload = json.loads(source.read_text(encoding="utf-8"))
    summary = summarize(payload)

    out = Path(args.output) if args.output else source.with_name(source.stem + "_summary.json")
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"resume  -> {out} ({out.stat().st_size / 1024:.1f} Ko)")

    if args.gzip_copy:
        target = source.with_suffix(source.suffix + ".gz")
        with source.open("rb") as src, gzip.open(target, "wb", compresslevel=9) as dst:
            shutil.copyfileobj(src, dst)
        print(f"complet -> {target} ({target.stat().st_size / 1048576:.2f} Mo, "
              f"source {source.stat().st_size / 1048576:.2f} Mo)")

    detector = payload.get("detector", {}).get("sha256", "?")
    print(f"empreinte du detecteur evalue : {detector}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
