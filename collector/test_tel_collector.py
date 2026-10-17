"""Offline logic tests; they do not prove exchange connectivity."""
import json, unittest
from unittest.mock import patch
from collector import tel_collector as tc

class CollectorTests(unittest.TestCase):
    def test_spread(self):
        s=tc.spread(1.0,1.02)
        self.assertAlmostEqual(s["pct_mid"],(0.02/1.01)*100)
        self.assertIsNone(tc.spread(None,1.0)["mid"])

    def test_buy_cost_walks_asks_and_marks_fees_excluded(self):
        r=tc.buy_cost([[1.0,100],[2.0,100]],150)
        self.assertTrue(r["complete"])
        self.assertAlmostEqual(r["qty_tel"],125)
        self.assertAlmostEqual(r["avg_price"],1.2)
        self.assertEqual(r["fees"],"EXCLUDED_NOT_VERIFIED")

    def test_partial_depth_is_not_reported_complete(self):
        r=tc.buy_cost([[1.0,10]],300)
        self.assertFalse(r["complete"])
        self.assertEqual(r["filled_usdt"],10)

    def test_recent_mexc_trade_order_is_sorted_by_timestamp(self):
        class C:
            venue="mexc"; symbol="TELUSDT"
            def __init__(self): self.log=[]
            def get(self,path,params=None):
                if path=="/api/v3/ticker/bookTicker": return {"bidPrice":"1","bidQty":"2","askPrice":"1.1","askQty":"3"}
                if path=="/api/v3/depth": return {"lastUpdateId":2,"bids":[["1","2"]],"asks":[["1.1","3"]]}
                if path=="/api/v3/trades": return [{"time":1000,"price":"1","qty":"1"},{"time":3000,"price":"1.1","qty":"1"}]
                if path=="/api/v3/time": return {"serverTime":4000}
        r=tc.fast(C())
        self.assertEqual(r["trades"][0]["time_ms"],3000)

    def test_missing_book_timestamp_never_claims_verified(self):
        obs=[{"book_age_ms":None,"book_hash":"same","book_sequence":5,"newest_trade_age_ms":1000},
             {"book_age_ms":None,"book_hash":"same","book_sequence":5,"newest_trade_age_ms":1000}]
        v=tc.verdict(obs,10,900)
        self.assertEqual(v["book"]["verdict"],"NON VÉRIFIÉ")

    def test_changed_book_without_timestamp_is_partial(self):
        obs=[{"book_age_ms":None,"book_hash":"a","book_sequence":5,"newest_trade_age_ms":1000},
             {"book_age_ms":None,"book_hash":"b","book_sequence":6,"newest_trade_age_ms":1000}]
        self.assertEqual(tc.verdict(obs,10,900)["book"]["verdict"],"PARTIEL")

    def test_stale_trade_not_verified(self):
        obs=[{"book_age_ms":None,"book_hash":"a","book_sequence":None,"newest_trade_age_ms":3600000}]
        self.assertEqual(tc.verdict(obs,10,900)["trades"]["verdict"],"NON VÉRIFIÉ")

    def test_kucoin_server_timestamp_is_unwrapped_integer(self):
        class C:
            venue = "kucoin"
            def get(self, path):
                self.path = path
                return 1792257123456
        c = C()
        self.assertEqual(tc.server_time(c), 1792257123456)
        self.assertEqual(c.path, "/api/v1/timestamp")

    def test_month_end(self):
        from datetime import datetime, timezone
        start=int(datetime(2026,9,1,tzinfo=timezone.utc).timestamp()*1000)
        end=int(datetime(2026,10,1,tzinfo=timezone.utc).timestamp()*1000)
        self.assertEqual(tc.month_end_ms(start),end)

if __name__=="__main__": unittest.main(verbosity=2)
