import json
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.terminal import collect
from scripts.terminal.build import build

class PublicCollection(unittest.TestCase):
    def test_public_payload_conversion(self):
        result={'error':[],'result':{'TELUSD':[[1794268800,'1','2','.5','1.5','1.1','42',3]],'last':1794268800}}
        d=collect.normalize(result,'KRAKEN:TELUSD','4h')
        self.assertEqual(d['bars'][0],dict(t=1794268800,o=1,h=2,l=.5,c=1.5,v=42))
        self.assertEqual(d['symbol'],'KRAKEN:TELUSD')

    def test_api_errors_and_wrong_pair_rejected(self):
        for obj in [{'error':['rate limit'],'result':{}},{'error':[],'result':{'ETHUSD':[],'last':0}}]:
            with self.assertRaises(ValueError):collect.normalize(obj,'KRAKEN:TELUSD','4h')

    def test_market_refresh_does_not_change_experiment_sample(self):
        source=Path('research/terminal/raw/tradingview_2026-11-10.json').resolve()
        first=build(source)
        second=build(source,market_source=source)
        self.assertEqual(first['lab']['experiments'],second['lab']['experiments'])
        self.assertEqual(second['research_source_sha256'],first['research_source_sha256'])
