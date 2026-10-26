#!/usr/bin/env python3
"""
Evaluation chronologique hors echantillon : ancien moteur vs moteur v2.

Separation stricte : 60 % chronologique de conception (IS), 40 % de validation
(OOS). Protocole fige dans OOS_PROTOCOL.md et scripts/backtest/protocol.py.

Le protocole n'est PAS modifie ici : ce script ne fait que l'appliquer.

Usage :
    python scripts/backtest/run_oos.py --output oos_results.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.backtest import engine, evaluation, history_store as store  # noqa: E402
from scripts.backtest.harness import Bundle  # noqa: E402
from scripts.backtest.protocol import (  # noqa: E402
    COST_SCENARIOS,
    CRITERION,
    IS_SHARE,
    NULL_TEST_ITERATIONS,
    PROTOCOL,
    REFERENCE_REVERSAL_CRITERION,
)

VENUE, SYMBOL = "kucoin", store.KUCOIN_SYMBOL
TIMEFRAMES = ["15m", "1h", "4h", "1d", "1w", "1M"]
OLD_ENGINE_PATH = Path(
    r"C:\Users\sabri\AppData\Local\Temp\opencode\backup-mission-20261021-022330"
    r"\worktree\src\agent_analysis.py")


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_old_engine():
    if not OLD_ENGINE_PATH.exists():
        raise SystemExit(f"moteur ancien introuvable : {OLD_ENGINE_PATH}")
    spec = importlib.util.spec_from_file_location("agent_analysis_old", OLD_ENGINE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["agent_analysis_old"] = module
    spec.loader.exec_module(module)
    return module


def split_index(bundle: Bundle) -> tuple[int, int, int, int]:
    """Borne de separation absolute, calculee sur l'axe 15m (le plus fin).

    Les frontieres sont des DATES ABSOLUES, et non une fraction : l'historique
    ayant ete prolonge (90000 bougies 15m), une coupure en pourcentage
    deplacerait silencieusement le segment de validation deja publie.
    """
    first = store.close_time_ms(bundle.rows[0], bundle.timeframe)
    last = store.close_time_ms(bundle.rows[-1], bundle.timeframe)
    split = int(datetime(2026, 4, 16, 11, 36, tzinfo=timezone.utc).timestamp() * 1000)
    return first, last, split, split


SEGMENT_DATES = {
    # nom      (debut, fin)  -- frontieres absolues, voir OOS_PROTOCOL.md
    "NEW": ("2024-03-27", "2025-07-09"),   # periode VERGEINE (collectee pour cette phase)
    "IS1": ("2025-07-09", "2025-11-27"),   # conception (1re moitie)
    "IS2": ("2025-11-27", "2026-04-16"),   # validation de conception
    "OOS": ("2026-04-16", "2030-01-01"),   # validation finale (deja consultee)
}


def segment_bounds(times, segment: str) -> tuple[int, int]:
    start_text, end_text = SEGMENT_DATES[segment]
    start = int(datetime.fromisoformat(start_text + "T00:00:00+00:00").timestamp() * 1000)
    end = int(datetime.fromisoformat(end_text + "T00:00:00+00:00").timestamp() * 1000)
    return start, end


def segment_indices(bundle: Bundle, times, segment: str) -> list[int]:
    start, end = segment_bounds(times, segment)
    return [i for i, t in enumerate(times) if start <= t < end]


def sha256_of(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="oos_results.json")
    parser.add_argument("--null-iterations", type=int, default=NULL_TEST_ITERATIONS)
    parser.add_argument("--timeframes", default=None)
    args = parser.parse_args()
    tfs = ([t.strip() for t in args.timeframes.split(",")] if args.timeframes else TIMEFRAMES)

    detector_path = Path(__file__).resolve().parent.parent.parent / "src" / "agent_analysis.py"
    detector_sha = sha256_of(detector_path)
    old_engine_sha = sha256_of(OLD_ENGINE_PATH) if OLD_ENGINE_PATH.exists() else "ABSENT"
    print(f"moteur v2 evalue   : src/agent_analysis.py  sha256={detector_sha}")
    print(f"moteur ancien evalue : {OLD_ENGINE_PATH.name}  sha256={old_engine_sha}")

    bundles: dict[str, Bundle] = {}
    indexes: dict[str, engine.TimeframeIndex] = {}
    for tf in tfs:
        rows = store.load_timeframe(VENUE, SYMBOL, tf)
        if not rows:
            print(f"[{tf}] absent du cache")
            continue
        bundles[tf] = Bundle(tf, rows)
        indexes[tf] = engine.TimeframeIndex(bundles[tf])

    first, last, split_ms, _ = split_index(bundles["15m"])
    print(f"axe 15m      : {iso(first)} -> {iso(last)}")
    print(f"frontieres absolues : NEW / IS1 / IS2 / OOS  (coupure IS-OOS : {iso(split_ms)})")

    # Calculer la proportion reelle de donnees dans chaque segment (axe 15m)
    times_15m = [store.close_time_ms(r, "15m") for r in bundles["15m"].rows]
    total_bars = len(times_15m)
    segment_counts = {}
    for seg_name in ("NEW", "IS1", "IS2", "OOS"):
        indices = segment_indices(bundles["15m"], times_15m, seg_name)
        segment_counts[seg_name] = len(indices)
    real_is_share = (segment_counts["NEW"] + segment_counts["IS1"] + segment_counts["IS2"]) / total_bars
    print(f"repartmentition reelle (15m) : NEW={segment_counts['NEW']} "
          f"IS1={segment_counts['IS1']} IS2={segment_counts['IS2']} "
          f"OOS={segment_counts['OOS']} / {total_bars} total")
    print(f"  part conception reelle = {real_is_share:.1%} "
          f"(parametre de conception IS_SHARE = {IS_SHARE:.0%})")
    print()

    engines = {"ancien": load_old_engine().detect_early_reversal, "v2": None}

    results: dict[str, Any] = {
        "schema_version": 1,
        "kind": "oos_evaluation_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "venue": VENUE,
        "symbol": SYMBOL,
        "detectors": {
            "v2": {"path": "src/agent_analysis.py", "sha256": detector_sha},
            "ancien": {"path": str(OLD_ENGINE_PATH), "sha256": old_engine_sha},
        },
        "protocol": PROTOCOL,
        "split": {"first_ms": first, "last_ms": last, "split_ms": split_ms,
                  "first": iso(first), "last": iso(last), "split": iso(split_ms),
                  "is_share": IS_SHARE,
                  "real_is_share": round(real_is_share, 4),
                  "segment_bar_counts": segment_counts,
                  "total_bars": total_bars},
        "results": {},
    }

    for engine_name, detector in engines.items():
        print(f"=== moteur {engine_name} ===")
        results["results"][engine_name] = {}
        for tf in bundles:
            bundle = bundles[tf]
            signals, status_counts = engine.collect_signals(bundles, indexes, tf, detector)
            times = [store.close_time_ms(row, tf) for row in bundle.rows]
            segments = {}
            for segment_name in ("NEW", "IS1", "IS2", "OOS"):
                indices = segment_indices(bundle, times, segment_name)
                start, end = segment_bounds(times, segment_name)
                segment_signals = [s for s in signals
                                   if start <= store.close_time_ms(bundle.rows[s["index"]], tf) < end]
                episodes = engine.group_episodes(segment_signals)
                summary = evaluation.summarise_segment(
                    bundle, indices, episodes, CRITERION, COST_SCENARIOS, args.null_iterations)
                summary["status_counts_bars"] = {
                    status: sum(1 for e in episodes if e["status"] == status)
                    for status in sorted(set(e["status"] for e in episodes))}
                summary["status_counts_bars"]["TOTAL_EPISODES"] = len(episodes)
                segments[segment_name] = summary
                exploitable = summary["scenarios"]["S0_brut"].get("EXPLOITABLE", {})
                print(f"  {tf:4s} {segment_name:3s} : barres={len(indices):>6} "
                      f"episodes={summary['episodes']:>5} "
                      f"densite={(summary['density'] or 0)*100:5.2f}% "
                      f"tous={summary['scenarios']['S0_brut']['TOUS_SIGNALUX']['hit_rate'] if summary['scenarios']['S0_brut']['TOUS_SIGNALUX']['hit_rate'] else 0:.4f} "
                      f"exploitables={exploitable.get('evaluated', 0)}")
            results["results"][engine_name][tf] = {
                "status_counts": status_counts,
                "segments": segments,
            }
        print()

    output = Path(args.output)
    output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
