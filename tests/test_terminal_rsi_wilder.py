"""Regression checks for the terminal's Wilder RSI, independent of legacy studies."""
import math
import json
import shutil
import subprocess
import unittest
from src.terminal import model


class WilderRSI(unittest.TestCase):
    def test_wilder_seed_and_recurrence(self):
        closes = list(range(100, 115)) + [113, 112]
        values = model.rsi_wilder_series(closes)
        self.assertTrue(all(math.isnan(v) for v in values[:14]))
        self.assertEqual(values[14], 100.0)
        self.assertAlmostEqual(values[15], 100 * 13 / 14, places=10)
        self.assertAlmostEqual(values[16], 100 * (13 / 14) ** 2, places=10)

    def test_flat_and_downward_closes(self):
        self.assertEqual(model.rsi_wilder_series([10] * 20)[-1], 50.0)
        self.assertEqual(model.rsi_wilder_series(list(range(30, 10, -1)))[-1], 0.0)

    def test_invalid_close_restarts_warmup(self):
        values=model.rsi_wilder_series(list(range(20))+[float('nan')]+list(range(20)))
        self.assertTrue(math.isnan(values[21+13]))
        self.assertEqual(values[21+14],100.0)

    @unittest.skipUnless(shutil.which('node'), 'Node.js unavailable')
    def test_matches_smartview_panel_on_same_closed_bars(self):
        step=14400;start=1769126400
        bars=[dict(t=start+i*step,o=100+(i%7),h=102+(i%7),l=99+(i%7),c=101+(i%7),v=10)
              for i in range(80)]
        frame=model.analyze(dict(symbol='KRAKEN:TELUSD',interval='4h',bars=bars,success=True),start+80*step)
        code="const s=require('./site/terminal/smartview.js');let x='';process.stdin.on('data',c=>x+=c);process.stdin.on('end',()=>console.log(JSON.stringify(s.technical({bars:JSON.parse(x)},'4h').momentum)));"
        result=subprocess.run(['node','-e',code],input=json.dumps(bars),text=True,capture_output=True,check=True)
        panel=json.loads(result.stdout)
        for point,reference in zip(frame['series'],panel):
            if point['rsi14'] is None:self.assertIsNone(reference['rsi14'])
            else:self.assertAlmostEqual(point['rsi14'],reference['rsi14'],places=10)

    def test_method_is_recorded_on_each_frame(self):
        step = 14400
        start = 1769126400
        bars = [dict(t=start+i*step, o=100+i, h=102+i, l=99+i, c=101+i, v=10)
                for i in range(60)]
        frame = model.analyze(dict(symbol='KRAKEN:TELUSD', interval='4h', bars=bars, success=True), start+60*step)
        self.assertEqual(frame['indicator_methods']['rsi14'], 'wilder_rma_14_sma_seed')
