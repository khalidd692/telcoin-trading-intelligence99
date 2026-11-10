import json
import hashlib
import subprocess
import sys
import tempfile
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

class MarketOnlyBuildRegression(unittest.TestCase):
    def test_market_only_build_preserves_frozen_experiments(self):
        study=Path('results/terminal/experiments.json')
        before=hashlib.sha256(study.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'market.json'
            subprocess.run([
                sys.executable,'-m','scripts.terminal.build',
                '--market-input','research/terminal/raw/kraken_2026-11-10_refresh.json',
                '--output',str(target),'--no-study-write',
            ],check=True,capture_output=True,text=True)
            result=json.loads(target.read_text())
            self.assertEqual(result['market'],'KRAKEN:TELUSD')
            self.assertEqual(result['safety']['real_orders'],False)
            self.assertEqual(result['safety']['paper_orders'],False)
        self.assertEqual(hashlib.sha256(study.read_bytes()).hexdigest(),before)
