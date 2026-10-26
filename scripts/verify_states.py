#!/usr/bin/env python3
"""
Controle operationnel des quatre etats du detecteur de retournement.

Verifie, etat par etat, la chaine complete :
    moteur (src/agent_analysis.py)  ->  rapport publie  ->  etat d'alerte
    (src/alert_state.py)           ->  contrat du tableau de bord

Etats verifies :
    ALERTE PRÉCOCE, CONFIRMATION, INVALIDATION, ATTENDRE

Le controle est en lecture seule : aucun fichier du depot n'est ecrit, aucune
donnee de marche n'est fabriquee. Les series utilisees sont synthetiques et
construites de la meme facon que les tests du moteur (tests/test_reversal_engine.py),
afin d'obtenir un etat donne de maniere deterministe.

Stdlib uniquement (contrainte CI : aucun requirements.txt).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import src.agent_analysis as agent  # noqa: E402
import src.alert_state as alerts  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(label: str, condition: bool, detail: str = "") -> bool:
    global CHECKS
    CHECKS += 1
    if condition:
        print(f"  OK   {label}" + (f"  [{detail}]" if detail else ""))
    else:
        print(f"  ECHEC {label}" + (f"  [{detail}]" if detail else ""))
        FAILURES.append(label)
    return bool(condition)


def load_reference():
    path = ROOT / "tests" / "test_reversal_engine.py"
    spec = importlib.util.spec_from_file_location("reference_reversal_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REF = load_reference()


def report_for(early: dict, timeframes: dict | None = None) -> dict:
    """Rapport publie minimal, conforme a la forme reelle."""
    timeframes = timeframes if timeframes is not None else REF.timeframes()
    return {
        "schema_version": 1,
        "symbol": "TELUSDT",
        "mode": "READ_ONLY_ANALYSIS",
        "status": "SURVEILLER",
        "collection_status": "VALID",
        "snapshot_age_seconds": 0,
        "source_generated_at": "2026-10-21T11:59:30+00:00",
        "timeframes": timeframes,
        "early_reversal": early,
    }


def build_early_alert() -> dict:
    closes = REF.declining_then_low(40)
    series = REF.build_series(closes, macd=REF.rising_macd(40),
                              volumes=[1000.0] * 39 + [3000.0])
    return REF.call(series, REF.timeframes())


def build_early_confirmation() -> dict:
    """ALERTE PRÉCOCE puis CONFIRMATION quand la structure se casse.

    Construction identique a celle du test canonique du moteur
    (tests/test_reversal_engine.py::test_alert_then_confirmation).
    """
    closes = REF.declining_then_low(41)
    closes[39] = closes[38] * 1.004
    closes[40] = closes[39] * 1.004
    macd = REF.rising_macd(41)
    macd[39] = -0.0002
    macd[40] = -0.0002
    volumes = [1000.0] * 38 + [3000.0, 1200.0, 1200.0]
    series = REF.build_series(closes, macd=macd, volumes=volumes)
    return REF.call(series, REF.timeframes(), up_to=41)


def build_early_invalidation() -> dict:
    """Setup casse : l'ancre est rompue, le scenario doit etre invalide.

    Construction identique a celle du test canonique du moteur
    (tests/test_reversal_engine.py::test_invalidation_when_the_anchor_is_broken).
    """
    closes = REF.declining_then_low(39)
    closes[38] = closes[37] * 0.99
    macd = REF.rising_macd(39)
    macd[38] = -0.0003
    volumes = [1000.0] * 37 + [3000.0, 1500.0]
    series = REF.build_series(closes, macd=macd, volumes=volumes)
    return REF.call(series, REF.timeframes())


def build_early_attendre() -> dict:
    """Marche haussier regulier : aucun retournement structurel."""
    closes = [0.0020 + 0.00001 * i for i in range(40)]
    series = REF.build_series(closes, macd=[0.0001 * i for i in range(40)])
    return REF.call(series, REF.timeframes())


def check_state(label: str, early: dict, expected_status: str,
                expected_alert_action: str) -> dict:
    print()
    print(f"--- {label} ---")
    report = report_for(early)
    status = early.get("signal_status")
    check(f"{label} : le moteur produit {expected_status}", status == expected_status,
          f"obtenu {status}")
    for key in ("regime", "exploitable", "exploitable_reason"):
        check(f"{label} : le rapport expose '{key}'", key in early, str(early.get(key))[:40])
    check(f"{label} : exploitable est un booleen", isinstance(early.get("exploitable"), bool),
          repr(early.get("exploitable")))
    # contrat du tableau de bord : les cles lues par site/index.html
    check(f"{label} : le tableau de bord peut lire regime.state",
          isinstance(early.get("regime"), dict) and bool(early["regime"].get("state")),
          str((early.get("regime") or {}).get("state")))
    # etat d'alerte
    state, decision = alerts.advance(alerts.default_state(), report)
    check(f"{label} : l'etat d'alerte est {expected_alert_action}",
          decision["action"] == expected_alert_action, decision["action"])
    return decision


def main() -> int:
    print("=" * 78)
    print("CONTROLE OPERATIONNEL DES QUATRE ETATS")
    print("=" * 78)
    print(f"  moteur     : {ROOT/'src'/'agent_analysis.py'}")
    print(f"  etat       : {ROOT/'src'/'alert_state.py'}")
    print(f"  tableau    : {ROOT/'site'/'index.html'}")

    print()
    print("=" * 78)
    print("1. LES QUATRE ETATS")
    print("=" * 78)
    check_state("ALERTE PRÉCOCE", build_early_alert(), "ALERTE_PRÉCOCE", "NOUVELLE_ALERTE")
    check_state("ATTENDRE", build_early_attendre(), "ATTENDRE", "AUCUNE_ALERTE")
    check_state("INVALIDATION", build_early_invalidation(), "INVALIDATION", "NOUVELLE_ALERTE")
    check_state("CONFIRMATION", build_early_confirmation(), "CONFIRMATION", "NOUVELLE_ALERTE")

    # evolution de statut : ALERTE PRÉCOCE -> CONFIRMATION sur le meme setup
    print()
    print("--- EVOLUTION DE STATUT (ALERTE PRÉCOCE -> CONFIRMATION) ---")
    early_alert = build_early_alert()
    report = report_for(early_alert)
    state, decision = alerts.advance(alerts.default_state(), report)
    check("evolution : premiere execution = NOUVELLE_ALERTE",
          decision["action"] == "NOUVELLE_ALERTE", decision["action"])
    evolved = dict(early_alert)
    evolved["signal_status"] = "CONFIRMATION"
    state2, decision2 = alerts.advance(state, report_for(evolved))
    check("evolution : le statut change n'est pas une nouvelle alerte",
          decision2["action"] == "EVOLUTION" and state2["counters"]["alerts"] == 1,
          f"{decision2['action']} / alertes={state2['counters']['alerts']}")
    check("evolution : l'alerte ouverte porte le nouveau statut",
          state2["open_alert"]["signal_status"] == "CONFIRMATION",
          str(state2["open_alert"]["signal_status"]))

    print()
    print("=" * 78)
    print("2. DONNEES ABSENTES, PERIMEES OU INCOHERENTES")
    print("=" * 78)
    missing = agent.build_analysis({})
    check("snapshot absent : fail-closed", missing.get("status") == "ATTENDRE",
          str(missing.get("status")))
    check("snapshot absent : collection_status FALLBACK",
          missing.get("collection_status") == "FALLBACK", str(missing.get("collection_status")))
    check("snapshot absent : aucun signal de retournement",
          "early_reversal" not in missing)
    check("snapshot absent : l'etat d'alerte refuse de conclure",
          alerts.report_is_usable(missing) is False)
    state, decision = alerts.advance(alerts.default_state(), missing)
    check("snapshot absent : aucune resolution n'est emise",
          decision["action"] in ("INDISPONIBLE", "AUCUNE_ALERTE"), decision["action"])

    # une alerte ouverte ne doit pas etre resolue par une panne de flux
    opened, _ = alerts.advance(alerts.default_state(), report_for(build_early_alert()))
    state, decision = alerts.advance(opened, missing)
    check("panne de flux : l'alerte ouverte n'est pas resolue",
          decision["action"] == "INDISPONIBLE" and state["open_alert"] is not None,
          decision["action"])
    check("panne de flux : le compteur de resolutions n'augmente pas",
          state["counters"]["resolutions"] == 0, str(state["counters"]["resolutions"]))

    print()
    print("=" * 78)
    print("3. DEDUPLICATION ET REPRISE")
    print("=" * 78)
    report = report_for(build_early_alert())
    state, first = alerts.advance(alerts.default_state(), report)
    state, second = alerts.advance(state, report)
    check("deuxieme execution : l'alerte n'est pas re-emise",
          second["action"] == "REPETITION", second["action"])
    check("deuxieme execution : une seule alerte comptee",
          state["counters"]["alerts"] == 1, str(state["counters"]["alerts"]))

    print()
    print("=" * 78)
    print("BILAN")
    print("=" * 78)
    print(f"  controles : {CHECKS} | reussis : {CHECKS - len(FAILURES)} | echecs : {len(FAILURES)}")
    for failure in FAILURES:
        print(f"    - {failure}")
    if FAILURES:
        return 1
    print("  Les quatre etats, le comportement fail-closed, la deduplication et")
    print("  la reprise sont conformes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
