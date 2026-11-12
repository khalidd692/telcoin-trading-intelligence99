"""Forward-observation regression checks. Run: python -m unittest tests.test_tel99_forward_evaluation"""
import unittest
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
    def test_matured_return_not_future_leak(self):
        first={"observed_at":"1000","price":"0.001","data_valid":"true"}
        future={"observed_at":"4600","price":"0.0011","data_valid":"true"}
        rows=[first,future]
        update(rows,4500)
        self.assertNotIn("r_1h",first)
        update(rows,4600)
        self.assertEqual(first.get("r_1h"),"10.00000")
        self.assertNotIn("r_4h",first)
    def test_no_future_observation(self):
        first={"observed_at":"1000","price":"0.001","data_valid":"true"}
        update([first],5000)
        self.assertNotIn("r_1h",first)

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
