"""
Tests du module d'etat des alertes (src/alert_state.py).

Couverture demandee :
  - deduplication d'un setup persistant (REPETITION) ;
  - nouvelle alerte vs evolution de statut (ALERTE -> CONFIRMATION -> INVALIDATION) ;
  - resolution exigeant des donnees exploitables (une panne de flux ne resout rien) ;
  - persistance et reprise apres redemarrage ;
  - fichier d'etat corrompu : recuperation sans exception ;
  - ecriture atomique ;
  - historique borne ;
  - aucune donnee de marche fabriquee.

Stdlib uniquement (contrainte CI : aucun requirements.txt).
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import src.agent_analysis as agent
import src.alert_state as alerts


def _load_reference_helpers():
    """Reutilise les helpers canoniques du test du moteur (meme construction)."""
    import importlib.util
    path = Path(__file__).resolve().parents[1] / "tests" / "test_reversal_engine.py"
    spec = importlib.util.spec_from_file_location("reference_reversal_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REF = _load_reference_helpers()


def make_report(signal_status="ALERTE_PRÉCOCE", direction="HAUSSIER", anchor=0.002,
                setup=True, usable=True, exploitable=False, confidence=40):
    """Rapport d'analyse minimal, conforme a la forme publiee."""
    early = {
        "signal_status": signal_status,
        "direction": direction,
        "reason": "raisons de test",
        "confidence": confidence,
        "exploitable": exploitable,
        "exploitable_reason": "raison de test",
    }
    if setup:
        early["setup"] = {"direction": direction, "anchor": anchor, "age_bars": 3}
    return {
        "schema_version": 1,
        "symbol": "TELUSDT",
        "mode": "READ_ONLY_ANALYSIS",
        "status": "SURVEILLER" if usable else "ATTENDRE",
        "collection_status": "VALID" if usable else "FALLBACK",
        "timeframes": {"15m": {"status": "OK" if usable else "PARTIEL"}},
        "early_reversal": early,
    }


def make_state(open_alert=None, history=None, counters=None):
    state = alerts.default_state()
    if open_alert is not None:
        state["open_alert"] = open_alert
    if history is not None:
        state["history"] = history
    if counters is not None:
        state["counters"].update(counters)
    return state


class TestEventExtraction(unittest.TestCase):
    def test_no_event_when_signal_is_neutral(self):
        report = make_report(signal_status="ATTENDRE", setup=False)
        self.assertIsNone(alerts.event_from_report(report))

    def test_no_event_when_report_has_no_early_reversal(self):
        report = make_report()
        report.pop("early_reversal")
        self.assertIsNone(alerts.event_from_report(report))

    def test_no_event_on_malformed_report(self):
        self.assertIsNone(alerts.event_from_report(None))
        self.assertIsNone(alerts.event_from_report("texte"))
        self.assertIsNone(alerts.event_from_report([]))

    def test_event_carries_report_values_only(self):
        report = make_report(anchor=0.002, confidence=40)
        event = alerts.event_from_report(report)
        self.assertEqual(event["symbol"], "TELUSDT")
        self.assertEqual(event["direction"], "HAUSSIER")
        self.assertEqual(event["anchor"], 0.002)
        self.assertEqual(event["signal_status"], "ALERTE_PRÉCOCE")
        self.assertEqual(event["confidence"], 40)

    def test_usable_report_rules(self):
        self.assertTrue(alerts.report_is_usable(make_report()))
        fallback = make_report(usable=False)
        self.assertFalse(alerts.report_is_usable(fallback))
        no_15m = make_report()
        no_15m["timeframes"] = {"1h": {"status": "OK"}}
        self.assertFalse(alerts.report_is_usable(no_15m))
        self.assertFalse(alerts.report_is_usable(None))

    def test_anchor_rounding_absorbs_float_noise(self):
        first = alerts.setup_identity("TELUSDT", "HAUSSIER", 0.0020000000001)
        second = alerts.setup_identity("TELUSDT", "HAUSSIER", 0.002)
        self.assertEqual(first, second)

    def test_identity_changes_with_anchor_and_direction(self):
        base = alerts.setup_identity("TELUSDT", "HAUSSIER", 0.002)
        self.assertNotEqual(base, alerts.setup_identity("TELUSDT", "HAUSSIER", 0.003))
        self.assertNotEqual(base, alerts.setup_identity("TELUSDT", "BAISSIER", 0.002))


class TestDeduplication(unittest.TestCase):
    def test_new_alert_is_detected(self):
        state, decision = alerts.advance(alerts.default_state(), make_report())
        self.assertEqual(decision["action"], "NOUVELLE_ALERTE")
        self.assertEqual(state["open_alert"]["seen_count"], 1)
        self.assertEqual(state["counters"]["alerts"], 1)

    def test_same_alert_is_deduplicated(self):
        report = make_report()
        state, first = alerts.advance(alerts.default_state(), report)
        state, second = alerts.advance(state, report)
        self.assertEqual(second["action"], "REPETITION")
        self.assertEqual(state["open_alert"]["seen_count"], 2)
        self.assertEqual(state["counters"]["alerts"], 1)

    def test_escalation_is_an_evolution_not_a_new_alert(self):
        report = make_report(signal_status="ALERTE_PRÉCOCE")
        state, _ = alerts.advance(alerts.default_state(), report)
        state, decision = alerts.advance(state, make_report(signal_status="CONFIRMATION",
                                                            exploitable=True))
        self.assertEqual(decision["action"], "EVOLUTION")
        self.assertEqual(state["counters"]["alerts"], 1)
        self.assertEqual(state["open_alert"]["signal_status"], "CONFIRMATION")

    def test_invalidation_is_an_evolution(self):
        state, _ = alerts.advance(alerts.default_state(), make_report())
        state, decision = alerts.advance(state, make_report(signal_status="INVALIDATION"))
        self.assertEqual(decision["action"], "EVOLUTION")
        self.assertEqual(state["open_alert"]["signal_status"], "INVALIDATION")
        self.assertEqual(state["counters"]["alerts"], 1)

    def test_new_anchor_is_a_new_alert(self):
        state, _ = alerts.advance(alerts.default_state(), make_report(anchor=0.002))
        state, decision = alerts.advance(state, make_report(anchor=0.0025))
        self.assertEqual(decision["action"], "NOUVELLE_ALERTE")
        self.assertEqual(state["counters"]["alerts"], 2)
        self.assertIsNotNone(decision["resolved"])

    def test_opposite_direction_is_a_new_alert(self):
        state, _ = alerts.advance(alerts.default_state(), make_report(direction="HAUSSIER"))
        state, decision = alerts.advance(state, make_report(direction="BAISSIER"))
        self.assertEqual(decision["action"], "NOUVELLE_ALERTE")

    def test_no_alert_when_nothing_is_open(self):
        state, decision = alerts.advance(alerts.default_state(),
                                         make_report(signal_status="ATTENDRE", setup=False))
        self.assertEqual(decision["action"], "AUCUNE_ALERTE")
        self.assertIsNone(state["open_alert"])


class TestResolution(unittest.TestCase):
    def test_resolution_when_data_is_usable(self):
        state, _ = alerts.advance(alerts.default_state(), make_report())
        state, decision = alerts.advance(state, make_report(signal_status="ATTENDRE", setup=False))
        self.assertEqual(decision["action"], "RESOLUTION")
        self.assertIsNone(state["open_alert"])
        self.assertEqual(state["counters"]["resolutions"], 1)

    def test_missing_data_never_resolves(self):
        state, _ = alerts.advance(alerts.default_state(), make_report())
        broken = make_report(usable=False)
        broken.pop("early_reversal")
        state, decision = alerts.advance(state, broken)
        self.assertEqual(decision["action"], "INDISPONIBLE")
        self.assertIsNotNone(state["open_alert"])
        self.assertEqual(state["counters"]["resolutions"], 0)

    def test_stale_data_does_not_resolve(self):
        state, _ = alerts.advance(alerts.default_state(), make_report())
        stale = make_report(signal_status="DONNÉES INSUFFISANTES", setup=False)
        stale["collection_status"] = "VALID"
        stale["timeframes"] = {"15m": {"status": "PARTIEL"}}
        state, decision = alerts.advance(state, stale)
        self.assertEqual(decision["action"], "INDISPONIBLE")
        self.assertIsNotNone(state["open_alert"])

    def test_resolution_is_recorded_in_history(self):
        state, _ = alerts.advance(alerts.default_state(), make_report())
        state, _ = alerts.advance(state, make_report(signal_status="ATTENDRE", setup=False))
        actions = [entry["action"] for entry in state["history"]]
        self.assertIn("NOUVELLE_ALERTE", actions)
        self.assertIn("RESOLUTION", actions)


class TestPersistence(unittest.TestCase):
    def test_state_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "alert_state.json"
            report = make_report()
            state, first, written = alerts.decide(report, path)
            self.assertTrue(written)
            self.assertTrue(state["open_alert"])
            # "redemarrage" : on relit le fichier et on continue
            reloaded = alerts.load_state(path)
            self.assertEqual(reloaded["open_alert"]["setup_id"], state["open_alert"]["setup_id"])
            state, second = alerts.advance(reloaded, report)
            self.assertEqual(second["action"], "REPETITION")
            self.assertEqual(state["counters"]["alerts"], 1)

    def test_state_file_is_created_on_first_run(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sous" / "alert_state.json"
            state, decision, written = alerts.decide(make_report(), path)
            self.assertTrue(written)
            self.assertTrue(path.is_file())
            self.assertTrue(json.loads(path.read_text(encoding="utf-8"))["open_alert"])

    def test_corrupt_state_file_is_recovered(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "alert_state.json"
            path.write_text("{ ceci n'est pas du json", encoding="utf-8")
            state = alerts.load_state(path)
            self.assertIsNone(state["open_alert"])
            self.assertEqual(state["counters"].get("recovered"), 1)
            state, decision = alerts.advance(state, make_report())
            self.assertEqual(decision["action"], "NOUVELLE_ALERTE")

    def test_missing_state_file_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as folder:
            state = alerts.load_state(Path(folder) / "absent.json")
            self.assertIsNone(state["open_alert"])
            self.assertEqual(state["history"], [])

    def test_atomic_write_leaves_no_temporary_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "alert_state.json"
            self.assertTrue(alerts.save_state(path, alerts.default_state()))
            leftovers = [p for p in Path(folder).iterdir() if p.name != path.name]
            self.assertEqual(leftovers, [])

    def test_history_is_bounded(self):
        state = alerts.default_state()
        for index in range(alerts.MAX_HISTORY + 25):
            state, _ = alerts.advance(state, make_report(anchor=0.002 + index * 0.0001))
        self.assertLessEqual(len(state["history"]), alerts.MAX_HISTORY)

    def test_state_file_is_readable_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "alert_state.json"
            alerts.decide(make_report(), path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], alerts.SCHEMA_VERSION)
            self.assertIn("open_alert", payload)
            self.assertIn("counters", payload)


class TestCommandLine(unittest.TestCase):
    def test_cli_writes_state_and_decision(self):
        with tempfile.TemporaryDirectory() as folder:
            report_path = Path(folder) / "report.json"
            state_path = Path(folder) / "state.json"
            decision_path = Path(folder) / "decision.json"
            report_path.write_text(json.dumps(make_report()), encoding="utf-8")
            code = alerts.main(["--input", str(report_path), "--state", str(state_path),
                                "--output", str(decision_path)])
            self.assertEqual(code, 0)
            self.assertTrue(state_path.is_file())
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
            self.assertEqual(decision["action"], "NOUVELLE_ALERTE")

    def test_cli_never_fails_on_unreadable_report(self):
        with tempfile.TemporaryDirectory() as folder:
            report_path = Path(folder) / "absent.json"
            state_path = Path(folder) / "state.json"
            code = alerts.main(["--input", str(report_path), "--state", str(state_path)])
            self.assertEqual(code, 0)

    def test_cli_on_fallback_report_does_not_create_an_alert(self):
        with tempfile.TemporaryDirectory() as folder:
            report_path = Path(folder) / "report.json"
            state_path = Path(folder) / "state.json"
            broken = make_report(usable=False)
            broken.pop("early_reversal")
            report_path.write_text(json.dumps(broken), encoding="utf-8")
            alerts.main(["--input", str(report_path), "--state", str(state_path)])
            state = alerts.load_state(state_path)
            self.assertIsNone(state["open_alert"])


class TestEngineIntegration(unittest.TestCase):
    """Le module consomme la sortie reelle du moteur de retournement."""

    def _report_from_engine(self):
        """Construit un rapport depuis la sortie reelle du moteur.

        La construction est celle du test canonique du moteur (tests/test_reversal_engine.py) :
        meme serie, meme pic de volume, memes unites de temps.
        """
        closes = REF.declining_then_low(40)
        series = REF.build_series(closes, macd=REF.rising_macd(40),
                                  volumes=[1000.0] * 39 + [3000.0])
        timeframes = REF.timeframes()
        early = REF.call(series, timeframes)
        return {
            "symbol": "TELUSDT",
            "collection_status": "VALID",
            "timeframes": timeframes,
            "early_reversal": early,
        }

    def test_engine_output_produces_an_alert_event(self):
        report = self._report_from_engine()
        self.assertIn(report["early_reversal"]["signal_status"],
                      ("ALERTE_PRÉCOCE", "CONFIRMATION", "INVALIDATION"))
        event = alerts.event_from_report(report)
        self.assertIsNotNone(event)
        self.assertEqual(event["direction"], "HAUSSIER")
        self.assertIsNotNone(event["anchor"])

    def test_engine_output_is_deduplicated_across_runs(self):
        report = self._report_from_engine()
        state, first = alerts.advance(alerts.default_state(), report)
        state, second = alerts.advance(state, report)
        self.assertEqual(first["action"], "NOUVELLE_ALERTE")
        self.assertEqual(second["action"], "REPETITION")

    def test_module_never_invents_values(self):
        """Toutes les valeurs de l'evenement proviennent du rapport."""
        report = self._report_from_engine()
        event = alerts.event_from_report(report)
        early = report["early_reversal"]
        self.assertEqual(event["signal_status"], early["signal_status"])
        self.assertEqual(event["confidence"], early["confidence"])
        self.assertEqual(event["exploitable"], early["exploitable"])
        self.assertEqual(event["symbol"], report["symbol"])


class TestProspectiveLedger(unittest.TestCase):
    """Le journal prospectif distingue un resultat historique d'un resultat mesure
    sur les signaux emis en avant. Il est strictement append-only."""

    def test_ledger_appends_one_line_per_run(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Path(folder) / "prospective.jsonl"
            report = make_report()
            for _ in range(3):
                state, decision = alerts.advance(alerts.default_state(), report)
                alerts.append_ledger(ledger, alerts.ledger_row(report, decision, state))
            lines = [l for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(len(lines), 3)
            first = json.loads(lines[0])
            self.assertEqual(first["action"], "NOUVELLE_ALERTE")
            self.assertEqual(first["signal_status"], "ALERTE_PRÉCOCE")
            self.assertEqual(first["symbol"], "TELUSDT")

    def test_ledger_never_erases_previous_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Path(folder) / "prospective.jsonl"
            ledger.write_text('{"at": "2026-10-20T00:00:00+00:00", "action": "NOUVELLE_ALERTE"}\n',
                              encoding="utf-8")
            state, decision = alerts.advance(alerts.default_state(), make_report())
            alerts.append_ledger(ledger, alerts.ledger_row(make_report(), decision, state))
            lines = [l for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["at"], "2026-10-20T00:00:00+00:00")

    def test_ledger_row_contains_only_report_values(self):
        report = make_report()
        state, decision = alerts.advance(alerts.default_state(), report)
        row = alerts.ledger_row(report, decision, state)
        self.assertEqual(row["signal_status"], report["early_reversal"]["signal_status"])
        self.assertEqual(row["confidence"], report["early_reversal"]["confidence"])
        self.assertEqual(row["exploitable"], report["early_reversal"]["exploitable"])
        self.assertEqual(row["symbol"], report["symbol"])
        self.assertIn("action", row)
        self.assertIn("at", row)
        # champs du protocole Phase 10 section 2E
        for key in ("time_ms", "status", "regime", "fees_appliquees", "period_type",
                    "returns_24h_bruts", "returns_24h_net", "ci95", "pct_up", "segment",
                    "evidence", "contradictions", "reason"):
            self.assertIn(key, row)
        # fraicheur : sans ces champs, on ne pourrait pas distinguer une
        # observation recente d'une observation perimee
        for key in ("report_status", "collection_status", "snapshot_age_seconds",
                    "source_generated_at", "close_15m", "tf_15m_status"):
            self.assertIn(key, row)

    def test_ledger_row_labels_the_nature_of_the_observation(self):
        report = make_report()
        state, decision = alerts.advance(alerts.default_state(), report)
        # par defaut, la fonction reste "historical" (rejeu de donnees d'historique)
        self.assertEqual(alerts.ledger_row(report, decision, state)["period_type"], "historical")
        # la CLI, elle, consigne des observations reellement collectees
        self.assertEqual(
            alerts.ledger_row(report, decision, state, period_type="live")["period_type"], "live")

    def test_cli_labels_its_rows_as_live(self):
        with tempfile.TemporaryDirectory() as folder:
            report_path = Path(folder) / "report.json"
            state_path = Path(folder) / "state.json"
            ledger_path = Path(folder) / "prospective.jsonl"
            report_path.write_text(json.dumps(make_report()), encoding="utf-8")
            alerts.main(["--input", str(report_path), "--state", str(state_path),
                         "--ledger", str(ledger_path)])
            row = json.loads(ledger_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(row["period_type"], "live")

    def test_fees_are_declared_as_a_protocol_hypothesis(self):
        report = make_report()
        state, decision = alerts.advance(alerts.default_state(), report)
        row = alerts.ledger_row(report, decision, state)
        self.assertAlmostEqual(row["fees_appliquees"], 0.0057)
        self.assertIn("hypothese", row["fees_note"].lower())

    def test_ledger_row_handles_a_fallback_report(self):
        report = make_report(usable=False)
        report.pop("early_reversal")
        state, decision = alerts.advance(alerts.default_state(), report)
        row = alerts.ledger_row(report, decision, state)
        self.assertEqual(row["action"], "INDISPONIBLE")
        self.assertNotIn("signal_status", row)

    def test_cli_writes_the_ledger(self):
        with tempfile.TemporaryDirectory() as folder:
            report_path = Path(folder) / "report.json"
            state_path = Path(folder) / "state.json"
            ledger_path = Path(folder) / "prospective.jsonl"
            report_path.write_text(json.dumps(make_report()), encoding="utf-8")
            code = alerts.main(["--input", str(report_path), "--state", str(state_path),
                                "--ledger", str(ledger_path)])
            self.assertEqual(code, 0)
            lines = [l for l in ledger_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(len(lines), 1)


if __name__ == "__main__":
    unittest.main()
