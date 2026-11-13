"""Forward-observation regression checks. Run: python -m unittest tests.test_tel99_forward_evaluation"""
import unittest
import tempfile
from pathlib import Path
from scripts.terminal.evaluate_observations import observe, update

def fixture(now=2000000):
    frames={}
    for tf,step in (("15m",900),("1h",3600),("4h",14400),("1D",86400)):
        frames[tf]={"interval":tf,"symbol":"KRAKEN:TELUSD","ready":True,"quality":{"last_close":now-120},"latest":{"close":0.0014}}
    return {"schema_version":1,"market":"KRAKEN:TELUSD","source":"Kraken public REST / OHLC","safety":{"real_orders":False,"paper_orders":False},"as_of":now-60,"frames":frames,"decision":{"status":"ATTENDRE UNE CONFIRMATION"}}

class EvaluationTests(unittest.TestCase):
    def test_fresh_snapshot_is_valid(self):
        self.assertEqual(observe(fixture(),2000000)["data_valid"],"true")
    def test_stale_snapshot_rejected(self):
        self.assertEqual(observe(fixture(),2001000)["data_valid"],"false")
    def test_wrong_market_rejected(self):
        d=fixture();d["market"]="OTHER"
        self.assertEqual(observe(d,2000000)["data_valid"],"false")
    def test_order_safety_rejected(self):
        d=fixture();d["safety"]["paper_orders"]=True
        self.assertEqual(observe(d,2000000)["data_valid"],"false")
    def test_candle_after_snapshot_is_rejected(self):
        d=fixture();d['frames']['15m']['quality']['last_close']=d['as_of']+1
        self.assertEqual(observe(d,2000000)['data_valid'],'false')
    def test_matured_return_not_future_leak(self):
        first={"observed_at":"1000","price_at":"1000","price":"0.001","data_valid":"true"}
        future={"observed_at":"4600","price_at":"4600","price":"0.0011","data_valid":"true"}
        rows=[first,future]
        update(rows,4500)
        self.assertNotIn("r_1h",first)
        update(rows,4600)
        self.assertEqual(first.get("r_1h"),"10.00000")
        self.assertNotIn("r_4h",first)
    def test_no_future_observation(self):
        first={"observed_at":"1000","price_at":"1000","price":"0.001","data_valid":"true"}
        update([first],5000)
        self.assertNotIn("r_1h",first)

    def test_new_observation_horizon_starts_when_signal_was_observed(self):
        from scripts.terminal.evaluate_observations import observation_id
        first={"observed_at":"1000","price_at":"900","price":"0.001","data_valid":"true"}
        too_early={"observed_at":"4500","price_at":"4500","price":"0.0011","data_valid":"true"}
        valid={"observed_at":"4600","price_at":"4600","price":"0.0012","data_valid":"true"}
        metadata={observation_id(first):{'outcome_method':'observation_time_v3'}}
        update([first,too_early],4500,metadata)
        self.assertNotIn('r_1h',first)
        update([first,too_early,valid],4600,metadata)
        self.assertEqual(first['r_1h'],'20.00000')

    def test_outcome_never_uses_candle_before_horizon_or_after_observation(self):
        first={"observed_at":"1000","price_at":"900","price":"0.001","data_valid":"true"}
        early={"observed_at":"4600","price_at":"4499","price":"0.0011","data_valid":"true"}
        impossible={"observed_at":"4700","price_at":"4800","price":"0.0012","data_valid":"true"}
        update([first,early,impossible],5000)
        self.assertNotIn("r_1h",first)

    def test_missing_or_corrupt_existing_journal_is_not_treated_as_new(self):
        from scripts.terminal.evaluate_observations import read_journal
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'observations.csv'
            with self.assertRaises(FileNotFoundError): read_journal(path)
            path.write_text('')
            with self.assertRaises(ValueError): read_journal(path)
            path.write_text('observed_at,broken\n1,2\n')
            with self.assertRaises(ValueError): read_journal(path)

    def test_observations_are_append_only_and_outcomes_are_separate_and_deduplicated(self):
        import csv
        from scripts.terminal.evaluate_observations import FIELDS, read_journal, append_observation, append_outcomes
        with tempfile.TemporaryDirectory() as d:
            journal=Path(d)/'observations.csv'; outcomes=Path(d)/'outcomes.jsonl'
            with journal.open('w',newline='') as f: csv.DictWriter(f,fieldnames=FIELDS).writeheader()
            first={"observed_at":"1000","snapshot_at":"999","market":"KRAKEN:TELUSD","price_at":"900","price":"0.001","data_valid":"true"}
            later={"observed_at":"4600","snapshot_at":"4599","market":"KRAKEN:TELUSD","price_at":"4500","price":"0.0011","data_valid":"true"}
            append_observation(journal, first)
            before=journal.read_bytes()
            append_observation(journal, later)
            self.assertTrue(journal.read_bytes().startswith(before))
            original=journal.read_bytes()
            rows=read_journal(journal)
            append_outcomes(outcomes, rows, 4600)
            once=outcomes.read_text()
            append_outcomes(outcomes, rows, 4600)
            self.assertEqual(outcomes.read_text(),once)
            self.assertEqual(journal.read_bytes(),original)
            self.assertEqual(len(once.splitlines()),1)
            import json
            outcome=json.loads(once)
            self.assertEqual(outcome['outcome_price_at'],4500)
            self.assertEqual(outcome['outcome_observed_at'],4600)

    def test_versioned_outcome_keeps_old_data_and_records_new_method(self):
        import json
        from scripts.terminal.evaluate_observations import append_outcomes, observation_id
        first={'observed_at':'1000','snapshot_at':'999','market':'KRAKEN:TELUSD','price_at':'900','price':'1','data_valid':'true'}
        early={'observed_at':'4500','snapshot_at':'4499','market':'KRAKEN:TELUSD','price_at':'4500','price':'1.1','data_valid':'true'}
        later={'observed_at':'4600','snapshot_at':'4599','market':'KRAKEN:TELUSD','price_at':'4600','price':'1.2','data_valid':'true'}
        with tempfile.TemporaryDirectory() as d:
            outcomes=Path(d)/'outcomes.jsonl'; meta=Path(d)/'metadata.jsonl'
            meta.write_text(json.dumps({'id':'m','observation_id':observation_id(first),'outcome_method':'observation_time_v3'})+'\n')
            append_outcomes(outcomes,[first,early],4500,meta)
            self.assertFalse(outcomes.exists())
            append_outcomes(outcomes,[first,early,later],4600,meta)
            original=outcomes.read_bytes()
            record=json.loads(original)
            self.assertEqual(record['method'],'observation_time_v3')
            self.assertEqual(record['outcome_price_at'],4600)
            append_outcomes(outcomes,[first,early,later],4600,meta)
            self.assertEqual(outcomes.read_bytes(),original)

    def test_transitions_are_append_only_and_deduplicated(self):
        import json
        from scripts.terminal.evaluate_observations import append_transitions
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'events.jsonl'
            rows=[dict(observed_at='100',snapshot_at='99',market='KRAKEN:TELUSD',price_at='90',data_valid='true',decision='ATTENDRE',factors='[]'),
                  dict(observed_at='200',snapshot_at='199',market='KRAKEN:TELUSD',price_at='190',data_valid='true',decision='ALERTE PRÉCOCE',factors='["volume"]',event='{"id":"early-1","type":"EARLY_ALERT"}')]
            append_transitions(path,rows);before=path.read_bytes()
            append_transitions(path,rows)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(len({json.loads(line)['id'] for line in before.splitlines()}),2)

if __name__=="__main__":unittest.main()

class RadarJournalTests(unittest.TestCase):
    def test_transitions_include_validity_and_factor_changes_without_duplicate_events(self):
        from scripts.terminal.evaluate_observations import decision_history
        rows = [
            dict(observed_at="100", decision="ATTENDRE", data_valid="true", factors="[]"),
            dict(observed_at="200", decision="ALERTE PRÉCOCE", data_valid="true",
                 factors='["volume"]', event='{"id":"early-1","type":"EARLY_ALERT"}'),
            dict(observed_at="201", decision="ALERTE PRÉCOCE", data_valid="true",
                 factors='["volume"]', event='{"id":"early-1","type":"EARLY_ALERT"}'),
            dict(observed_at="300", decision="ATTENDRE", data_valid="false", factors="[]"),
        ]
        changes = decision_history(rows)
        self.assertEqual(len(changes), 3)
        self.assertEqual(changes[1]["previous_decision"], "ATTENDRE")
        self.assertEqual(changes[1]["changed_factors"], ["+ volume"])
        self.assertEqual(changes[1]["event"]["type"], "EARLY_ALERT")
        self.assertEqual(changes[2]["decision"], "DONNÉES INSUFFISANTES")
        self.assertIsNone(changes[2]["event"])

    def test_dated_radar_event_is_ignored_when_observation_expires(self):
        d = fixture()
        d["radar"] = {"status":"ALERTE PRÉCOCE", "asOf":d["as_of"], "closedAt":1999880,
                      "event":{"id":"abc","type":"EARLY_ALERT","data_valid":True}}
        self.assertEqual(observe(d,2001000)["decision"],"DONNÉES INSUFFISANTES")
        self.assertEqual(observe(d,2001000)["event"],"")
