import unittest
import tempfile
import json
from pathlib import Path

from scripts.terminal import rebounds


def candles(values, start=90000):
    return [{'close_at': start+i*900, 'close': v} for i,v in enumerate(values)]


class ReboundsTest(unittest.TestCase):
    def test_episode_requires_full_future_and_does_not_double_count_overlaps(self):
        prices = candles([100]*4+[105]+[106]*193)
        result = rebounds.evaluate(prices, [], start_at=90000, now=prices[-1]['close_at'])
        self.assertEqual(result['thresholds']['5']['episodes'], 1)
        self.assertEqual(result['thresholds']['5']['unknown'], 1)
        self.assertEqual(result['thresholds']['5']['missed'], 0)

    def test_early_alert_is_credited_only_if_observed_before_start(self):
        prices = candles([100]+[105]*96)
        event = {'id':'a','type':'EARLY_ALERT','observed_at':89900,'candle_closed_at':89100}
        result = rebounds.evaluate(prices, [event], start_at=90000, now=prices[-1]['close_at'])
        self.assertEqual(result['thresholds']['5']['detected'], 1)
        self.assertEqual(result['thresholds']['5']['missed'], 0)

    def test_missing_future_candle_cannot_produce_rebound_or_false_positive(self):
        prices = candles([100]+[106]*96)
        del prices[20]
        event = {'id':'a','type':'EARLY_ALERT','observed_at':90000,'candle_closed_at':90000,'price':100}
        result = rebounds.evaluate(prices,[event],start_at=90000,now=prices[-1]['close_at'])
        self.assertEqual(result['thresholds']['5']['episodes'],0)
        self.assertEqual(result['false_positives']['evaluable'],0)

    def test_late_alert_is_missed_only_with_prior_radar_coverage(self):
        prices=candles([100,100,105]+[105]*94)
        coverage=[{'price_at':t,'observed_at':t,'radar_covered':True} for t in range(86400,90000,900)]
        event={'id':'late','type':'EARLY_ALERT','observed_at':90900,'candle_closed_at':90900,'price':100}
        r=rebounds.evaluate(prices,[event],90000,prices[-1]['close_at'],coverage)
        self.assertEqual(r['thresholds']['5']['missed'],1)
        self.assertEqual(r['thresholds']['5']['late_alerts'],1)
        self.assertEqual(r['thresholds']['5']['median_late_minutes'],15)

    def test_coverage_from_after_start_cannot_prove_a_miss(self):
        prices=candles([100]+[105]*96)
        coverage=[{'price_at':t,'observed_at':90001,'radar_covered':True} for t in range(86400,90000,900)]
        r=rebounds.evaluate(prices,[],90000,prices[-1]['close_at'],coverage)
        self.assertEqual(r['thresholds']['5']['unknown'],1)

    def test_four_thresholds_and_unmatured_alerts_are_separate(self):
        prices = candles([100]+[103]*96)
        event = {'id':'a','type':'EARLY_ALERT','observed_at':90000,'candle_closed_at':90000,'price':100}
        result = rebounds.evaluate(prices,[event],start_at=90000,now=prices[-1]['close_at'])
        self.assertEqual(result['thresholds']['2']['episodes'],1)
        self.assertEqual(result['thresholds']['3']['episodes'],1)
        self.assertEqual(result['thresholds']['5']['episodes'],0)
        self.assertEqual(result['false_positives']['count'],1)

    def test_protocol_is_registered_before_future_candles_and_kept_on_retry(self):
        from scripts.terminal.evaluate_observations import record_rebounds
        from test_tel99_forward_evaluation import fixture
        now=2000000; data=fixture(now); close=now-now%900
        data['frames']['15m']['quality']['last_close']=close
        data['frames']['15m']['bars']=[{'t':close-900,'o':1,'h':1,'l':1,'c':1,'v':1}]
        data['radar']={'asOf':data['as_of'],'closedAt':close,'status':'ATTENDRE'}
        row={'data_valid':'true','observed_at':str(now),'price_at':str(close),'event':''}
        with tempfile.TemporaryDirectory() as d:
            first=record_rebounds(data,row,[row],now,Path(d))
            protocol=Path(d,'rebound_protocol.jsonl').read_bytes()
            self.assertGreater(first['start_at'],now)
            self.assertFalse(Path(d,'rebound_candles.jsonl').exists())
            second=record_rebounds(data,row,[row],now+1,Path(d))
            self.assertEqual(second['start_at'],first['start_at'])
            self.assertEqual(Path(d,'rebound_protocol.jsonl').read_bytes(),protocol)

    def test_unverified_snapshot_cannot_preregister(self):
        from scripts.terminal.evaluate_observations import record_rebounds
        with tempfile.TemporaryDirectory() as d:
            result=record_rebounds({}, {'data_valid':'false'}, [], 2000000, Path(d))
            self.assertIsNone(result)
            self.assertFalse(Path(d,'rebound_protocol.jsonl').exists())

    def test_cloud_workflow_persists_all_versioned_evidence(self):
        workflow=Path('.github/workflows/tel99-forward-evaluation.yml').read_text()
        for name in ('rebound_protocol.jsonl','rebound_candles.jsonl','rebound_coverage.jsonl'):
            self.assertGreaterEqual(workflow.count(name),2)

    def test_scheduled_capture_is_not_a_twelve_minute_sleeping_job(self):
        workflow=Path('.github/workflows/tel99-live-publication.yml').read_text()
        self.assertIn("TEL99_CYCLES: '1'",workflow)
        self.assertIn("2-57/5",workflow)


if __name__=='__main__': unittest.main()
