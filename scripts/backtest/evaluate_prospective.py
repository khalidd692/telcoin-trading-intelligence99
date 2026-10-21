"""
Evaluation prospective : mesure des rendements a 24 h des observations consignees.

Pourquoi ce module existe
-------------------------
`alerts/prospective.jsonl` consigne une ligne par execution : l'etat du signal,
le regime, l'exploitabilite, le cout applique. Les champs `returns_24h_bruts`,
`returns_24h_net`, `ci95` et `pct_up` y restent **inconnus** tant que l'echeance
de 24 h n'est pas atteinte : les renseigner avant l'echeance serait fabriquer un
resultat.

Ce module fait le travail **quand l'echeance est atteinte** : il lit le journal, y
croise une serie de prix 15 m, et produit un fichier d'evaluation **distinct**
(le journal n'est jamais modifie). Le cout applique est celui du protocole fige
`OOS-1.2` (scenario S1_slippage_AR) ; les frais restent des hypotheses.

Aucune donnee de marche n'est fabriquee : si la serie ne couvre pas l'echeance
d'une observation, cette observation reste simplement non evaluable.

Stdlib uniquement (contrainte CI : aucun requirements.txt).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

#: Horizon d'evaluation, en heures.
HORIZON_HOURS = 24

#: Cout aller-retour applique, conformement au protocole fige OOS-1.2
#: (scenario S1_slippage_AR = 2 x 0,285 % de slippage observe sur le carnet).
COST_ROUND_TRIP = 0.0057


def parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse un horodatage ISO. Retourne None si illisible."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def load_series(path: Any) -> list[tuple[datetime, float]]:
    """Charge une serie de prix 15 m.

    Formats acceptes :
      - JSONL : un objet par ligne avec "time" (ou "open_time") et "close" ;
      - JSON  : une liste d'objets memes cles.
    Les prix non finis ou non positifs sont ignores.
    """
    points: list[tuple[datetime, float]] = []
    raw = Path(path).read_text(encoding="utf-8")
    rows: list[Any] = []
    if raw.lstrip().startswith("["):
        payload = json.loads(raw)
        rows = payload if isinstance(payload, list) else []
    else:
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    for row in rows:
        if not isinstance(row, dict):
            continue
        stamp = None
        for field in ("time", "open_time", "timestamp", "ts"):
            if field in row:
                value = row[field]
                if isinstance(value, (int, float)):
                    seconds = value / 1000 if value > 1e11 else value
                    stamp = datetime.fromtimestamp(seconds, tz=timezone.utc)
                else:
                    stamp = parse_timestamp(value)
                break
        close = row.get("close")
        if stamp is None or close is None:
            continue
        try:
            price = float(close)
        except (TypeError, ValueError):
            continue
        if price != price or price <= 0:
            continue
        points.append((stamp, price))
    points.sort(key=lambda item: item[0])
    return points


def price_at(series: list[tuple[datetime, float]], when: datetime) -> Optional[float]:
    """Dernier prix connu a l'instant `when` (ou avant)."""
    best: Optional[float] = None
    for stamp, price in series:
        if stamp <= when:
            best = price
        else:
            break
    return best


def evaluate_row(row: dict, series: list[tuple[datetime, float]],
                 now: datetime, horizon_hours: int = HORIZON_HOURS) -> dict:
    """Evalue une observation du journal.

    Retourne l'observation complete, augmentee des champs de rendement. Les
    champs restent `None` (inconnus) tant que l'echeance n'est pas atteinte ou
    que la serie ne couvre pas l'echeance.
    """
    result = dict(row)
    result.setdefault("returns_24h_bruts", None)
    result.setdefault("returns_24h_net", None)
    result.setdefault("ci95", None)
    result.setdefault("pct_up", None)
    result["evaluated_at"] = now.isoformat()
    result["cost_applied"] = COST_ROUND_TRIP

    stamp = parse_timestamp(row.get("at") or row.get("time_ms"))
    if stamp is None:
        result["evaluation_status"] = "HORODATAGE_ILLISIBLE"
        return result
    entry_price = row.get("close_15m")
    if entry_price is None or not isinstance(entry_price, (int, float)) or entry_price <= 0:
        result["evaluation_status"] = "PRIX_ENTREE_ABSENT"
        return result
    entry = float(entry_price)

    deadline = stamp + timedelta(hours=horizon_hours)
    if now < deadline:
        result["evaluation_status"] = "ECHEANCE_NON_ATTEINTE"
        result["evaluation_due_at"] = deadline.isoformat()
        return result

    exit_price = price_at(series, deadline)
    if exit_price is None:
        result["evaluation_status"] = "SERIE_INSUFFISANTE"
        result["evaluation_due_at"] = deadline.isoformat()
        return result

    brut = (exit_price / entry) - 1.0
    net = brut - COST_ROUND_TRIP
    result["returns_24h_bruts"] = brut
    result["returns_24h_net"] = net
    result["pct_up"] = net > 0
    result["exit_price_24h"] = exit_price
    result["evaluation_due_at"] = deadline.isoformat()
    result["evaluation_status"] = "EVALUEE"
    return result


def evaluate_journal(rows: list[dict], series: list[tuple[datetime, float]],
                     now: datetime, horizon_hours: int = HORIZON_HOURS) -> dict:
    """Evalue toutes les observations du journal. Ne modifie jamais le journal."""
    evaluated = [evaluate_row(row, series, now, horizon_hours) for row in rows]
    done = [r for r in evaluated if r.get("evaluation_status") == "EVALUEE"]
    pending = [r for r in evaluated if r.get("evaluation_status") == "ECHEANCE_NON_ATTEINTE"]
    unusable = [r for r in evaluated
                if r.get("evaluation_status") not in ("EVALUEE", "ECHEANCE_NON_ATTEINTE")]
    brut_values = [r["returns_24h_bruts"] for r in done]
    net_values = [r["returns_24h_net"] for r in done]
    summary = {
        "generated_at": now.isoformat(),
        "horizon_hours": horizon_hours,
        "cost_round_trip": COST_ROUND_TRIP,
        "observations": len(evaluated),
        "evaluated": len(done),
        "pending": len(pending),
        "not_evaluable": len(unusable),
        "mean_returns_24h_bruts": (sum(brut_values) / len(brut_values)) if brut_values else None,
        "mean_returns_24h_net": (sum(net_values) / len(net_values)) if net_values else None,
        "wins_net": sum(1 for v in net_values if v > 0),
        "losses_net": sum(1 for v in net_values if v <= 0),
    }
    return {"summary": summary, "observations": evaluated}


def main(argv: Optional[list] = None) -> int:
    """Point d'entree : produit un fichier d'evaluation, jamais modifie le journal."""
    parser = argparse.ArgumentParser(description="Evaluation prospective a 24 h")
    parser.add_argument("--journal", default="alerts/prospective.jsonl")
    parser.add_argument("--series", default=None,
                        help="serie de prix 15 m (JSONL ou JSON) ; sans elle, rien n'est evaluable")
    parser.add_argument("--output", default="alerts/prospective_evaluation.json")
    parser.add_argument("--horizon-hours", type=int, default=HORIZON_HOURS)
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    try:
        raw = Path(args.journal).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Journal illisible : {exc}")
        return 1
    rows = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    series: list[tuple[datetime, float]] = []
    if args.series:
        try:
            series = load_series(args.series)
        except OSError as exc:
            print(f"Serie illisible : {exc}")

    report = evaluate_journal(rows, series, now, args.horizon_hours)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = report["summary"]
    print(f"Observations : {summary['observations']} | evaluees : {summary['evaluated']} | "
          f"en attente : {summary['pending']} | non evaluables : {summary['not_evaluable']}")
    if summary["evaluated"]:
        print(f"Rendement 24 h moyen : brut {summary['mean_returns_24h_bruts']*100:+.3f} % | "
              f"net {summary['mean_returns_24h_net']*100:+.3f} % "
              f"(cout {summary['cost_round_trip']*100:.2f} % aller-retour)")
        print(f"Gains nets : {summary['wins_net']} | pertes nettes : {summary['losses_net']}")
    else:
        print("Aucune observation n'a encore atteint l'echeance de 24 h : "
              "aucun resultat n'est annonce.")
    print(f"Ecrit : {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
