"""
Evaluation prospective : mesure des rendements des observations consignees.

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

Regles de mesure (corrigees)
----------------------------
- **Sens** : un signal BAISSIER est evalue comme une position courte
  (`1 - sortie/entree`) ; un signal sans direction n'a pas de rendement et n'est
  donc pas evaluable. Compter un short comme une perte etait un biais de mesure.
- **Fraicheur** : un prix de sortie anterieur a l'echeance de plus de
  `EXIT_STALENESS_SECONDS` n'est pas utilise. Sans cette borne, un prix vieux de
  douze heures pouvait etre presente comme un rendement a 24 h.
- **Horizons** : 4 h, 24 h et 72 h sont mesures separement. Un signal peut
  preceder le mouvement sans que le rendement a 24 h soit positif.
- **Calibration** : le rendement net moyen est agrege par tranche de confiance et
  par statut de signal, sans jamais transformer la confiance en probabilite.

Stdlib uniquement (contrainte CI : aucun requirements.txt).
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

#: Horizon principal d'evaluation, en heures (champs de protocole `returns_24h_*`).
HORIZON_HOURS = 24

#: Horizons mesures. Le premier sert de reference aux champs de protocole.
HORIZONS_HOURS = (4, 24, 72)

#: Cout aller-retour applique, conformement au protocole fige OOS-1.2
#: (scenario S1_slippage_AR = 2 x 0,285 % de slippage observe sur le carnet).
#: Ce cout est un MINORANT : les frais de courtage (0,10 % a 0,20 % par cote)
#: ne sont pas inclus car non authentifies par HMAC. Le cout reel est
#: superieur ou egal. Voir COST_SCENARIOS_COMPLET.
COST_ROUND_TRIP = 0.0057

#: Scenarios de cout complets, pour reference. S1 est le scenario applique
#: par defaut (minorant). S2 inclut des frais de courtage hypothetiques.
COST_SCENARIOS_COMPLET = {
    "S1_slippage_AR": 0.0057,
    "S2_frais_0.10_AR": 0.0077,
    "S3_frais_0.15_AR": 0.0087,
}
COST_NOTE = (
    "Le cout applique (S1 = 0,57 %) est un MINORANT : il couvre le slippage "
    "observe sur un carnet calme a 300 USDT mais exclut les frais de "
    "courtage. Le cout reel d'un compte de trading est plus proche de "
    "S2 (0,77 % avec frais 0,10 %) ou S3 (0,87 % avec frais 0,15 %). "
    "Les frais ne sont pas mesures sur ce signal : ce sont des hypotheses "
    "du protocole, jamais des observations.")

#: Age maximal du dernier prix utilise comme prix de sortie. Une bougie 15 m
#: couvre 900 s ; deux bougies de tolerance absorbent une collecte manquee sans
#: jamais faire passer un prix vieux de plusieurs heures pour le prix de l'echeance.
EXIT_STALENESS_SECONDS = 30 * 60

#: Statuts de signal pour lesquels un rendement est une mesure de signal.
#: `ATTENDRE`/`AUCUNE_ALERTE` restent evaluables comme contre-factuel mais ne
#: sont pas comptes dans les statistiques de signal.
SIGNAL_STATUSES = ("ALERTE_PRÉCOCE", "ALERTE_PRECOCE", "CONFIRMATION", "INVALIDATION")

#: Tranches de confiance utilisees pour la calibration (bornes incluses a gauche).
CONFIDENCE_BUCKETS = ((0, 19), (20, 39), (40, 59), (60, 79), (80, 100))


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


def _candle_rows(payload: Any, timeframe: str = "15m") -> list:
    """Extrait les bougies d'une charge utile JSON de formes variables.

    Formes acceptees :
      - liste de bougies ;
      - objet portant directement `rows` ;
      - objet portant `candles.<timeframe>.rows` ;
      - instantane complet `sources.<venue>.candles.<timeframe>.rows`.

    L'instantane du collecteur est la forme reellement produite en production :
    ne pas la lire rendait le journal impossible a evaluer.
    """
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    rows = payload.get("rows")
    if isinstance(rows, list):
        return rows
    candles = payload.get("candles")
    if isinstance(candles, dict):
        section = candles.get(timeframe)
        if isinstance(section, dict) and isinstance(section.get("rows"), list):
            return section["rows"]
    sources = payload.get("sources")
    if isinstance(sources, dict):
        for venue in ("mexc", "kucoin"):
            source = sources.get(venue)
            if isinstance(source, dict):
                rows = _candle_rows(source, timeframe)
                if rows:
                    return rows
        for source in sources.values():
            rows = _candle_rows(source, timeframe)
            if rows:
                return rows
    return []


def series_from_rows(rows: list) -> list[tuple[datetime, float]]:
    """Convertit des bougies en points (horodatage, cloture) tries.

    Les prix non finis ou non positifs sont ignores : aucune valeur n'est
    remplacee ni extrapolee.
    """
    points: list[tuple[datetime, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        stamp = None
        for field in ("time", "open_time", "timestamp", "ts"):
            if field in row:
                value = row[field]
                if isinstance(value, (int, float)) and not isinstance(value, bool):
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
        if price != price or price in (float("inf"), float("-inf")) or price <= 0:
            continue
        points.append((stamp, price))
    points.sort(key=lambda item: item[0])
    return points


def load_series(path: Any, timeframe: str = "15m") -> list[tuple[datetime, float]]:
    """Charge une serie de prix depuis un JSONL, un JSON ou un instantane collecteur.

    Formats acceptes :
      - JSONL : un objet par ligne avec "time" (ou "open_time") et "close" ;
      - JSON  : une liste d'objets memes cles ;
      - JSON  : un instantane `site/tel_snapshot.json` (sources.*.candles.*.rows).
    """
    raw = Path(path).read_text(encoding="utf-8")
    if not raw.strip():
        return []
    rows: list[Any] = []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None
    if payload is not None:
        rows = _candle_rows(payload, timeframe)
    # Un fichier JSONL d'une seule ligne est aussi un objet JSON valide : il faut
    # alors relire ligne par ligne, sinon un point unique serait perdu.
    if not rows and not (isinstance(payload, dict) and
                         ("sources" in payload or "candles" in payload)):
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return series_from_rows(rows)


def last_point(series: list[tuple[datetime, float]],
               when: datetime) -> Optional[tuple[datetime, float]]:
    """Dernier point connu a l'instant `when` (ou avant), sans contrainte d'age."""
    best: Optional[tuple[datetime, float]] = None
    for stamp, price in series:
        if stamp <= when:
            best = (stamp, price)
        else:
            break
    return best


def quote_at(series: list[tuple[datetime, float]], when: datetime,
             max_staleness_seconds: Optional[float] = EXIT_STALENESS_SECONDS) -> Optional[tuple[datetime, float]]:
    """Prix de sortie utilisable a l'echeance, ou None si trop ancien/absent.

    `max_staleness_seconds=None` desactive la borne d'age : reserve aux appels
    qui veulent explicitement le dernier prix connu, jamais a une evaluation.
    """
    point = last_point(series, when)
    if point is None:
        return None
    stamp, _ = point
    if max_staleness_seconds is not None and (when - stamp).total_seconds() > max_staleness_seconds:
        return None
    return point


def price_at(series: list[tuple[datetime, float]], when: datetime,
             max_staleness_seconds: Optional[float] = EXIT_STALENESS_SECONDS) -> Optional[float]:
    """Prix de sortie a l'echeance (voir `quote_at`)."""
    point = quote_at(series, when, max_staleness_seconds)
    return None if point is None else point[1]


def direction_sign(direction: Any) -> int:
    """+1 pour une position longue, -1 pour une position courte, 0 si inconnue."""
    if not isinstance(direction, str):
        return 0
    normalized = direction.strip().upper()
    if normalized.startswith(("HAUSSIER", "HAUSSIÈRE", "LONG", "BULL")):
        return 1
    if normalized.startswith(("BAISSIER", "BAISSIÈRE", "SHORT", "BEAR")):
        return -1
    return 0


def _horizon_detail(row_stamp: datetime, entry: float, sign: int,
                    series: list[tuple[datetime, float]], now: datetime,
                    hours: int, staleness: Optional[float]) -> dict[str, Any]:
    """Mesure un horizon unique. Ne renseigne un rendement que s'il est mesurable."""
    deadline = row_stamp + timedelta(hours=hours)
    detail: dict[str, Any] = {"due_at": deadline.isoformat()}
    if now < deadline:
        detail.update(status="ECHEANCE_NON_ATTEINTE")
        return detail
    point = last_point(series, deadline)
    if point is None:
        detail.update(status="SERIE_INSUFFISANTE",
                      detail="aucun point de prix avant l'echeance")
        return detail
    exit_stamp, exit_price = point
    age_seconds = (deadline - exit_stamp).total_seconds()
    if exit_stamp <= row_stamp:
        detail.update(status="PRIX_SORTIE_ANTERIEUR",
                      detail="le dernier prix connu precede ou egale l'entree",
                      last_point_age_seconds=round(age_seconds))
        return detail
    if staleness is not None and age_seconds > staleness:
        detail.update(status="SERIE_INSUFFISANTE",
                      detail=f"dernier point anterieur de {round(age_seconds)} s a l'echeance",
                      last_point_age_seconds=round(age_seconds))
        return detail
    brut = sign * ((exit_price / entry) - 1.0)
    net = brut - COST_ROUND_TRIP
    detail.update(status="EVALUEE", exit_price=exit_price, exit_at=exit_stamp.isoformat(),
                  brut=brut, net=net, win=net > 0, last_point_age_seconds=round(age_seconds))
    return detail


def evaluate_row(row: dict, series: list[tuple[datetime, float]],
                 now: datetime, horizon_hours: int = HORIZON_HOURS,
                 horizons: Optional[tuple[int, ...]] = None,
                 exit_staleness_seconds: Optional[float] = EXIT_STALENESS_SECONDS) -> dict:
    """Evalue une observation du journal.

    Retourne l'observation complete, augmentee des champs de rendement. Les
    champs de protocole restent `None` (inconnus) tant que l'echeance n'est pas
    atteinte ou que la serie ne couvre pas l'echeance avec un prix assez frais.
    """
    result = dict(row)
    result.setdefault("returns_24h_bruts", None)
    result.setdefault("returns_24h_net", None)
    result.setdefault("ci95", None)
    result.setdefault("pct_up", None)
    result["evaluated_at"] = now.isoformat()
    result["cost_applied"] = COST_ROUND_TRIP
    result["exit_staleness_seconds"] = exit_staleness_seconds
    result["horizons"] = {}

    stamp = parse_timestamp(row.get("at") or row.get("time_ms"))
    if stamp is None:
        result["evaluation_status"] = "HORODATAGE_ILLISIBLE"
        result["evaluation_detail"] = "horodatage de l'observation illisible"
        return result
    entry_price = row.get("close_15m")
    if entry_price is None or not isinstance(entry_price, (int, float)) or isinstance(entry_price, bool) or entry_price <= 0:
        result["evaluation_status"] = "PRIX_ENTREE_ABSENT"
        result["evaluation_detail"] = "prix d'entree absent ou invalide dans le journal"
        return result
    entry = float(entry_price)

    # Distinction entre le prix observe (close_15m, cours de cloture de la bougie
    # du signal) et le prix d'execution reel. En l'absence de donnee d'execution,
    # le rendement est SIMULE : on suppose une execution instantanee au close,
    # ce qui introduit un biais d'execution favorable. Le champ
    # execution_price_real est None si aucune execution reel n'est disponible.
    result["entry_price_observed"] = entry
    result["entry_price_source"] = "close_15m (cours de cloture de la bougie du signal)"
    result["execution_price_real"] = row.get("execution_price_real")
    result["execution_lag_seconds"] = row.get("execution_lag_seconds")
    result["execution_note"] = (
        "SIMULE : pas de prix d'execution reel disponible. Le rendement est "
        "calcule avec le close_15m comme prix d'entree, ce qui suppose une "
        "execution instantanee au cours de cloture (biais favorable)."
        if result["execution_price_real"] is None else
        "REEL : prix d'execution observe disponible.")

    sign = direction_sign(row.get("direction"))
    result["direction_sign"] = sign
    if sign == 0:
        result["evaluation_status"] = "DIRECTION_INDETERMINEE"
        result["evaluation_detail"] = ("aucune direction mesurable : un rendement "
                                       "n'aurait pas de sens economique")
        return result

    horizons = tuple(horizons) if horizons else HORIZONS_HOURS
    details = {hours: _horizon_detail(stamp, entry, sign, series, now, hours,
                                      exit_staleness_seconds)
               for hours in horizons}
    result["horizons"] = {f"{hours}h": detail for hours, detail in details.items()}

    primary_hours = horizon_hours if horizon_hours in details else horizons[0]
    primary = details[primary_hours]
    result["evaluation_status"] = primary["status"]
    result["evaluation_detail"] = primary.get("detail")
    result["evaluation_due_at"] = primary["due_at"]
    result["evaluation_horizon_hours"] = primary_hours
    if primary["status"] == "EVALUEE":
        result["returns_24h_bruts"] = primary["brut"]
        result["returns_24h_net"] = primary["net"]
        result["pct_up"] = primary["win"]
        result["exit_price_24h"] = primary["exit_price"]
        result["exit_at_24h"] = primary["exit_at"]
        result["exit_age_seconds_24h"] = primary.get("last_point_age_seconds")
    return result


def _mean(values: list[float]) -> Optional[float]:
    return (sum(values) / len(values)) if values else None


def _bucket(confidence: Any) -> str:
    try:
        value = int(confidence)
    except (TypeError, ValueError):
        return "inconnue"
    for low, high in CONFIDENCE_BUCKETS:
        if low <= value <= high:
            return f"{low}-{high}"
    return "hors_bornes"


def _aggregate(rows: list[dict]) -> dict:
    """Agrege des observations deja evaluees (rendement net principal)."""
    net_values = [r["returns_24h_net"] for r in rows
                  if isinstance(r.get("returns_24h_net"), (int, float))]
    brut_values = [r["returns_24h_bruts"] for r in rows
                   if isinstance(r.get("returns_24h_bruts"), (int, float))]
    return {
        "evaluated": len(net_values),
        "mean_brut": _mean(brut_values),
        "mean_net": _mean(net_values),
        "wins_net": sum(1 for v in net_values if v > 0),
        "losses_net": sum(1 for v in net_values if v <= 0),
        "win_rate_net": (sum(1 for v in net_values if v > 0) / len(net_values))
        if net_values else None,
    }


def evaluate_journal(rows: list[dict], series: list[tuple[datetime, float]],
                     now: datetime, horizon_hours: int = HORIZON_HOURS,
                     horizons: Optional[tuple[int, ...]] = None,
                     exit_staleness_seconds: Optional[float] = EXIT_STALENESS_SECONDS) -> dict:
    """Evalue toutes les observations du journal. Ne modifie jamais le journal."""
    evaluated = [evaluate_row(row, series, now, horizon_hours, horizons,
                              exit_staleness_seconds) for row in rows]
    done = [r for r in evaluated if r.get("evaluation_status") == "EVALUEE"]
    pending = [r for r in evaluated if r.get("evaluation_status") == "ECHEANCE_NON_ATTEINTE"]
    not_evaluable = [r for r in evaluated
                     if r.get("evaluation_status") not in ("EVALUEE", "ECHEANCE_NON_ATTEINTE")]
    statuses: dict[str, int] = {}
    for row in not_evaluable:
        key = str(row.get("evaluation_status"))
        statuses[key] = statuses.get(key, 0) + 1

    horizons_used = tuple(horizons) if horizons else HORIZONS_HOURS
    by_horizon: dict[str, dict] = {}
    for hours in horizons_used:
        key = f"{hours}h"
        completed = [r["horizons"][key] for r in evaluated
                     if isinstance(r.get("horizons"), dict)
                     and isinstance(r["horizons"].get(key), dict)
                     and r["horizons"][key].get("status") == "EVALUEE"]
        nets = [item["net"] for item in completed]
        by_horizon[key] = {
            "evaluated": len(nets),
            "mean_net": _mean(nets),
            "wins_net": sum(1 for v in nets if v > 0),
            "win_rate_net": (sum(1 for v in nets if v > 0) / len(nets)) if nets else None,
        }

    signals = [r for r in done if str(r.get("status")).upper() in
               {s.upper() for s in SIGNAL_STATUSES}]
    by_status: dict[str, dict] = {}
    for row in done:
        key = str(row.get("status"))
        by_status.setdefault(key, []).append(row)
    by_direction: dict[str, dict] = {}
    for row in done:
        key = str(row.get("direction"))
        by_direction.setdefault(key, []).append(row)
    by_confidence: dict[str, dict] = {}
    for row in signals:
        by_confidence.setdefault(_bucket(row.get("confidence")), []).append(row)
    by_economic: dict[str, dict] = {}
    for row in done:
        by_economic.setdefault(str(row.get("economic_validity") or "INCONNUE"), []).append(row)

    headline = _aggregate(done)
    evaluated_any = sum(
        1 for row in evaluated
        if isinstance(row.get("horizons"), dict)
        and any(isinstance(item, dict) and item.get("status") == "EVALUEE"
                for item in row["horizons"].values())
    )
    signal_statuses = {s.upper() for s in SIGNAL_STATUSES}
    signals_any = sum(
        1 for row in evaluated
        if str(row.get("status")).upper() in signal_statuses
        and isinstance(row.get("horizons"), dict)
        and any(isinstance(item, dict) and item.get("status") == "EVALUEE"
                for item in row["horizons"].values())
    )
    summary = {
        "generated_at": now.isoformat(),
        "horizon_hours": horizon_hours,
        "horizons_hours": list(horizons_used),
        "exit_staleness_seconds": exit_staleness_seconds,
        "cost_round_trip": COST_ROUND_TRIP,
        "observations": len(evaluated),
        "evaluated": len(done),
        "evaluated_any_horizon": evaluated_any,
        "pending": len(pending),
        "not_evaluable": len(not_evaluable),
        "not_evaluable_by_status": statuses,
        "signals_evaluated": len(signals),
        "signals_measured_any_horizon": signals_any,
        "mean_returns_24h_bruts": headline["mean_brut"],
        "mean_returns_24h_net": headline["mean_net"],
        "wins_net": headline["wins_net"],
        "losses_net": headline["losses_net"],
        "win_rate_net": headline["win_rate_net"],
        "by_horizon": by_horizon,
        "by_status": {key: _aggregate(value) for key, value in sorted(by_status.items())},
        "by_direction": {key: _aggregate(value) for key, value in sorted(by_direction.items())},
        "calibration_by_confidence": {
            key: _aggregate(value) for key, value in sorted(by_confidence.items())
        },
        "by_economic_validity": {
            key: _aggregate(value) for key, value in sorted(by_economic.items())
        },
        "signals": _aggregate(signals),
        "measurement_notes": [
            "Un signal BAISSIER est evalue comme une position courte (1 - sortie/entree).",
            "Un prix de sortie plus vieux que la tolerance n'est pas utilise : l'observation reste non evaluable.",
            "Le cout applique est l'hypothese S1_slippage_AR du protocole OOS-1.2, pas une mesure.",
            "La confiance n'est pas une probabilite : les tranches servent a detecter un desaccord, pas a predire.",
            "Les ventilations by_status, by_direction, by_economic_validity et la calibration portent sur l'horizon principal ; by_horizon donne les autres echeances.",
        ],
    }
    return {"summary": summary, "observations": evaluated}


def merge_series(existing: list[tuple[datetime, float]],
                 incoming: list[tuple[datetime, float]]) -> list[tuple[datetime, float]]:
    """Fusionne deux series par horodatage. `incoming` gagne en cas de doublon."""
    merged: dict[datetime, float] = {stamp: price for stamp, price in existing}
    for stamp, price in incoming:
        merged[stamp] = price
    return sorted(merged.items(), key=lambda item: item[0])


def update_series_store(path: Any, incoming: list[tuple[datetime, float]]) -> list[tuple[datetime, float]]:
    """Met a jour un magasin de serie append-only (JSONL) et retourne la serie fusionnee.

    Le magasin existe parce qu'un instantane ne contient que la fenetre 15 m
    recente : sans accumulation, aucune echeance de 24 h ne serait jamais
    couverte et la boucle de mesure resterait ouverte. Seuls des points
    reellement collectes sont ecrits.
    """
    target = Path(path)
    existing: list[tuple[datetime, float]] = []
    if target.is_file():
        try:
            existing = load_series(target)
        except OSError:
            existing = []
    merged = merge_series(existing, incoming)
    if merged == existing:
        return merged
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps({"time": stamp.isoformat(), "close": price}, ensure_ascii=False) + "\n"
        for stamp, price in merged
    )
    handle, temp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".series-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return merged


def _summary_markdown(summary: dict) -> list[str]:
    lines = ["", "### Evaluation prospective (mesuree, jamais devinee)", ""]
    lines.append(f"- observations : {summary['observations']} | evaluees a {summary['horizon_hours']} h : "
                 f"{summary['evaluated']} | en attente : {summary['pending']} | "
                 f"non evaluables a cet horizon : {summary['not_evaluable']}")
    if summary["evaluated"]:
        lines.append(f"- rendement net moyen ({summary['horizon_hours']} h) : "
                     f"{summary['mean_returns_24h_net'] * 100:+.3f} % "
                     f"(brut {summary['mean_returns_24h_bruts'] * 100:+.3f} %, "
                     f"cout {summary['cost_round_trip'] * 100:.2f} % A/R)")
        lines.append(f"- gagnants nets : {summary['wins_net']} | perdants nets : {summary['losses_net']}")
    else:
        lines.append(f"- aucun resultat a {summary['horizon_hours']} h : aucune observation "
                     "n'a atteint cette echeance avec un prix de sortie assez frais.")
        if summary["not_evaluable_by_status"]:
            lines.append(f"- motifs de non-evaluabilite : {summary['not_evaluable_by_status']}")
    measured = [(key, block) for key, block in summary["by_horizon"].items()
                if block["evaluated"]]
    if measured:
        lines.append("- par horizon : "
                     + " | ".join(f"{key} n={block['evaluated']} "
                                  f"net moyen {block['mean_net'] * 100:+.3f} % "
                                  f"gagnants {block['wins_net']}"
                                  for key, block in measured))
    lines.append("- rappel : ces chiffres ne mesurent que les observations deja echeues ; "
                 "aucune extrapolation au-dela.")
    return lines


def main(argv: Optional[list] = None) -> int:
    """Point d'entree : produit un fichier d'evaluation, jamais modifie le journal."""
    parser = argparse.ArgumentParser(description="Evaluation prospective multi-horizons")
    parser.add_argument("--journal", default="alerts/prospective.jsonl")
    parser.add_argument("--series", default=None,
                        help="serie de prix 15 m (JSONL, JSON ou instantane collecteur)")
    parser.add_argument("--snapshot", default="site/tel_snapshot.json",
                        help="instantane utilise si --series est absent")
    parser.add_argument("--series-store", default=None,
                        help="magasin JSONL accumule des prix 15 m (cree si absent)")
    parser.add_argument("--output", default="alerts/prospective_evaluation.json")
    parser.add_argument("--horizon-hours", type=int, default=HORIZON_HOURS)
    parser.add_argument("--exit-tolerance-minutes", type=float,
                        default=EXIT_STALENESS_SECONDS / 60,
                        help="age maximal du prix de sortie")
    parser.add_argument("--summary", action="store_true",
                        help="ajoute un resume markdown a GITHUB_STEP_SUMMARY (ou stdout)")
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
    source = args.series or args.snapshot
    if source:
        try:
            series = load_series(source)
        except (OSError, UnicodeError) as exc:
            print(f"Serie illisible ({source}) : {exc}")
    if args.series_store:
        try:
            series = update_series_store(args.series_store, series)
        except OSError as exc:
            print(f"Magasin de serie non ecrit : {exc}")

    tolerance = (None if args.exit_tolerance_minutes is None
                 else args.exit_tolerance_minutes * 60)
    report = evaluate_journal(rows, series, now, args.horizon_hours,
                              exit_staleness_seconds=tolerance)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = report["summary"]
    lines = _summary_markdown(summary)
    print("\n".join(lines))
    for label, block in summary["by_horizon"].items():
        if block["evaluated"]:
            print(f"  horizon {label} : n={block['evaluated']} | net moyen "
                  f"{block['mean_net'] * 100:+.3f} % | gagnants {block['wins_net']}")
    if summary["calibration_by_confidence"]:
        print("  calibration par confiance : "
              + " | ".join(f"{key}: n={block['evaluated']}, net moyen "
                           f"{(block['mean_net'] * 100):+.3f} %"
                           for key, block in summary["calibration_by_confidence"].items()
                           if block["evaluated"]))
    print(f"Ecrit : {target}")
    if args.summary:
        destination = os.environ.get("GITHUB_STEP_SUMMARY")
        text = "\n".join(lines) + "\n"
        if destination:
            try:
                with open(destination, "a", encoding="utf-8") as stream:
                    stream.write(text)
            except OSError:
                pass
        else:
            print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
