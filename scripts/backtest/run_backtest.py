#!/usr/bin/env python3
"""
Exécution du backtest historique du détecteur de retournement précoce TEL/USDT.

Usage :
    python scripts/backtest/run_backtest.py --output backtest_results_v2.json

Le détecteur de production n'est pas modifié. Les constantes du protocole sont
figées dans scripts/backtest/harness.py (PROTOCOL) avant toute exécution.
Les deux critères de significativité (v1 sigma, v2 quantile) sont évalués et
publiés côte à côte.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.backtest import engine, history_store as store  # noqa: E402
from scripts.backtest.harness import PROTOCOL, Bundle, horizons_in_bars  # noqa: E402

VENUE = "kucoin"
SYMBOL = store.KUCOIN_SYMBOL
DEFAULT_TFS = ["15m", "1h", "4h", "1d", "1w", "1M"]
CRITERIA = ["quantile", "sigma"]


def iso(ms: float | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def contiguous_valid_indices(bundle: Bundle) -> list[int]:
    """Indices évaluables : horizon le plus long disponible ET aucun trou entre
    l'indice et la fin de l'horizon."""
    horizons = horizons_in_bars(bundle.timeframe)
    h_max = max(horizons)
    rows = bundle.rows
    n = len(rows)
    gap_after: dict[int, int] = {}
    for index in range(1, n):
        step = (rows[index]["t"] - rows[index - 1]["t"]) / 1000
        period = store.PERIOD_SECONDS.get(bundle.timeframe)
        if period and step != period:
            gap_after[index - 1] = index
    valid = []
    for i in range(n):
        if i + h_max >= n:
            continue
        if bundle.atr_pct_at(i) is None:
            continue
        if any(j in gap_after for j in range(i, i + h_max)):
            continue
        valid.append(i)
    return valid


def evaluate_target(bundle: Bundle, valid: list[int], signals: list[dict],
                    episodes: list[dict], criterion: str) -> dict:
    evaluated_all = [engine.evaluate_episode(bundle, e, criterion) for e in episodes]
    evaluated = [e for e in evaluated_all if e["evaluable"]]
    not_evaluable = [e for e in evaluated_all if not e["evaluable"]]
    base = engine.base_rate(bundle, valid, criterion)
    base_dir = engine.directional_base_rate(bundle, valid, criterion)
    reversals = engine.find_reference_reversals(bundle, valid, criterion)
    matching = engine.match_reversals(reversals, episodes, bundle)
    null = engine.null_test(bundle, episodes, evaluated, criterion)

    hits = sum(1 for e in evaluated if e["significant"])
    low, high = engine.wilson_interval(hits, len(evaluated))
    leads = [m["lead_ms"] / 60000.0 for m in matching["detected"]]
    positives = [lead for lead in leads if lead > 0]
    negatives = [lead for lead in leads if lead <= 0]
    matched_alert_indices = {m["alert_index"] for m in matching["detected"]}
    orphan_alerts = [e for e in episodes if e["index"] not in matched_alert_indices]

    return {
        "criterion": criterion,
        "episodes": len(episodes),
        "alert_density_per_bar": (len(episodes) / len(bundle.rows)) if bundle.rows else None,
        "evaluated": len(evaluated),
        "not_evaluable": len(not_evaluable),
        "hits": hits,
        "hit_rate": (hits / len(evaluated)) if evaluated else None,
        "hit_rate_wilson95": [low, high],
        "base_rate": base,
        "directional_base_rate": base_dir,
        "reference_reversals": {
            "total": len(reversals),
            "warning_window_bars": matching["warning_bars"],
            "detected_in_advance": len(matching["detected"]),
            "missed": len(matching["missed"]),
            "detection_rate": (len(matching["detected"]) / len(reversals)) if reversals else None,
            "median_lead_minutes": statistics.median(leads) if leads else None,
            "mean_lead_minutes": statistics.fmean(leads) if leads else None,
            "pct_detected_before_entry": (100 * len(positives) / len(leads)) if leads else None,
            "median_lead_before_entry_minutes": statistics.median(positives) if positives else None,
            "median_lag_after_entry_minutes": statistics.median(negatives) if negatives else None,
        },
        "alerts_without_reference_reversal": len(orphan_alerts),
        "null_test": null,
        "episodes_detail": evaluated,
        "missed_reversals_detail": matching["missed"][:500],
        "detected_reversals_detail": matching["detected"][:500],
    }


def sha256_of(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(timeframes: list[str], output: Path) -> dict:
    detector_path = Path(__file__).resolve().parent.parent.parent / "src" / "agent_analysis.py"
    detector_sha = sha256_of(detector_path)
    bundles: dict[str, Bundle] = {}
    indexes: dict[str, engine.TimeframeIndex] = {}
    data_report: dict[str, dict] = {}

    for tf in timeframes:
        rows = store.load_timeframe(VENUE, SYMBOL, tf)
        if not rows:
            print(f"[{tf}] ABSENT du cache - ignore")
            continue
        bundles[tf] = Bundle(tf, rows)
        indexes[tf] = engine.TimeframeIndex(bundles[tf])
        cov = store.coverage(rows, tf)
        data_report[tf] = {
            "count": cov["count"],
            "from": iso(cov["from_ms"]), "to": iso(cov["to_ms"]),
            "span_days": round((cov["to_ms"] - cov["from_ms"]) / 86_400_000, 1),
            "gaps": len(cov["gaps"]), "off_grid": cov["off_grid"], "status": cov["status"],
            "atr_pct_median_last": bundles[tf].atr_pct_at(len(rows) - 1),
        }

    results: dict[str, dict] = {}
    for target in timeframes:
        if target not in bundles:
            continue
        bundle = bundles[target]
        print(f"\n=== Cible {target} ({len(bundle.rows)} bougies) ===")
        signals, status_counts = engine.collect_signals(bundles, indexes, target)
        episodes = engine.group_episodes(signals)
        valid = contiguous_valid_indices(bundle)
        print(f"  statuts : {status_counts}")
        print(f"  signaux bruts={len(signals)} episodes={len(episodes)} (fenetre evaluable={len(valid)} barres)")

        per_criterion = {}
        for criterion in CRITERIA:
            res = evaluate_target(bundle, valid, signals, episodes, criterion)
            per_criterion[criterion] = res
            base = res["base_rate"]
            rev = res["reference_reversals"]
            null = res["null_test"]
            print(f"  [{criterion}] episodes={res['episodes']} evaluables={res['evaluated']} "
                  f"hits={res['hits']} taux={(res['hit_rate'] or 0) * 100:.2f}%")
            print(f"  [{criterion}] base rate={base['base_rate'] * 100:.1f}% "
                  f"(haussier={res['directional_base_rate']['bullish_rate'] * 100:.1f}% "
                  f"baissier={res['directional_base_rate']['bearish_rate'] * 100:.1f}%) "
                  f"discriminant={base['discriminant']}")
            print(f"  [{criterion}] retournements ref={rev['total']} detectes={rev['detected_in_advance']} "
                  f"manques={rev['missed']} av mediane={rev['median_lead_minutes']}")
            print(f"  [{criterion}] nullite observe={null['observed_hit_rate']} "
                  f"mediane={null['null_hit_rate_median']} percentile={null['percentile']}")

        results[target] = {
            "data": data_report.get(target),
            "status_counts": status_counts,
            "raw_signals": len(signals),
            "criteria": per_criterion,
        }

    payload = {
        "schema_version": 1,
        "kind": "backtest_early_reversal_v2",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "venue": VENUE,
        "symbol": SYMBOL,
        "detector": {
            "path": "src/agent_analysis.py",
            "sha256": detector_sha,
            "note": "Empreinte du detecteur evalue. Le detecteur n'est pas modifie par le harnais.",
        },
        "protocol": PROTOCOL,
        "data": data_report,
        "results": results,
    }
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n-> {output}")
    return payload


BULKY_KEYS = ("episodes_detail", "missed_reversals_detail", "detected_reversals_detail")


def write_summary(payload: dict, path: Path) -> Path:
    """Version resume : on retire les tableaux de detail volumineux, qui sont
    regenerables a l'identique par run_backtest.py depuis le cache local.
    Tout ce qui fonde les affirmations du rapport est conserve."""
    summary = json.loads(json.dumps(payload))
    for res in summary.get("results", {}).values():
        for crit in res.get("criteria", {}).values():
            for key in BULKY_KEYS:
                crit.pop(key, None)
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="backtest_results_v2.json")
    parser.add_argument("--summary", default=None,
                        help="ecrit aussi une version resume (sans les tableaux de detail) a ce chemin")
    parser.add_argument("--timeframes", default=None)
    args = parser.parse_args()
    tfs = ([t.strip() for t in args.timeframes.split(",")] if args.timeframes else DEFAULT_TFS)
    payload = run(tfs, Path(args.output))
    if args.summary:
        path = write_summary(payload, Path(args.summary))
        print(f"resume -> {path} ({path.stat().st_size / 1024:.1f} Ko)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
