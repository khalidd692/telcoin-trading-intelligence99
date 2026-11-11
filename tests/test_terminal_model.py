import copy
import math
import unittest
from src.terminal import model as M

STEP = 14400
BASE = 1769126400

def dataset(n=90, step=STEP):
    rows=[dict(t=BASE+i*step,o=100+i,h=102+i,l=99+i,c=101+i,v=1000+i) for i in range(n)]
    return dict(symbol='KRAKEN:TELUSD',interval='4h',bars=rows,success=True)

class Quality(unittest.TestCase):
    def test_forming_bar_excluded(self):
        d=dataset(3)
        r=M.validate_dataset(d, BASE+2*STEP+10)
        self.assertEqual([x['t'] for x in r['bars']],[BASE,BASE+STEP])
        self.assertEqual(r['excluded'][0]['reasons'],['unclosed'])

    def test_duplicate_copies_quarantined(self):
        d=dataset(3); d['bars'].insert(2,copy.deepcopy(d['bars'][1]))
        r=M.validate_dataset(d,BASE+4*STEP)
        self.assertEqual(len(r['bars']),2)
        self.assertEqual(len(r['excluded']),2)

    def test_inversion_quarantines_both(self):
        d=dataset(4);d['bars'][1],d['bars'][2]=d['bars'][2],d['bars'][1]
        r=M.validate_dataset(d,BASE+5*STEP)
        self.assertEqual([r['t'] for r in r['bars']],[BASE,BASE+3*STEP])

    def test_ohlc_and_nonfinite_quarantined(self):
        for field,value in [('h',0),('c',float('nan')),('v',-1),('h',10000)]:
            d=dataset(3);d['bars'][1][field]=value
            self.assertEqual(len(M.validate_dataset(d,BASE+4*STEP)['bars']),2)

    def test_unknown_final_timestamp_blocks_freshness(self):
        d=dataset();d['bars'].append(dict(t=None,o=190,h=192,l=189,c=191,v=100))
        a=M.analyze(d,BASE+90*STEP)
        self.assertFalse(a['ready'])
        self.assertTrue(a['quality']['invalid_tail'])

    def test_nested_inversions_cannot_leave_unsorted_output(self):
        d=dataset(6);order=[0,1,4,5,2,3]
        d['bars']=[d['bars'][i] for i in order]
        q=M.validate_dataset(d,BASE+7*STEP)
        times=[r['t'] for r in q['bars']]
        self.assertEqual(times,sorted(set(times)))
        self.assertFalse(any(g['before']<=g['after'] for g in q['quality']['gaps']))

    def test_invalid_row_type_rejected_cleanly(self):
        d=dataset();d['bars'].append(None)
        with self.assertRaises(ValueError):M.validate_dataset(d,BASE+100*STEP)

    def test_gap_restarts_indicators(self):
        d=dataset(); del d['bars'][60]
        a=M.analyze(d,BASE+90*STEP)
        self.assertIsNone(a['latest']['ema50'])
        self.assertEqual(a['quality']['last_segment_bars'],29)
        self.assertEqual(a['quality']['missing_bars'],1)

    def test_unknown_market_rejected(self):
        d=dataset();d['symbol']='MEXC:TELUSDT'
        with self.assertRaises(ValueError): M.validate_dataset(d,BASE+100*STEP)

    def test_column_length_mismatch_rejected(self):
        d=dataset(3);d['bars']={k:[r[k] for r in d['bars']] for k in ('t','o','h','l','c','v')}
        d['bars']['c'].pop()
        with self.assertRaises(ValueError):M.validate_dataset(d,BASE+4*STEP)

    def test_indicator_prefix_invariance(self):
        d=dataset(100)
        a=M.analyze(d,BASE+90*STEP)
        d['bars']=d['bars'][:90]
        b=M.analyze(d,BASE+90*STEP)
        self.assertEqual(a['series'],b['series'])
        self.assertEqual(a['latest'],b['latest'])

    def test_vwap_constant_and_rsi_flat(self):
        d=dataset(60)
        for r in d['bars']: r.update(o=10,h=10,l=10,c=10,v=2)
        a=M.analyze(d,BASE+60*STEP)
        self.assertEqual(a['latest']['vwap_session'],10)
        self.assertEqual(a['latest']['rsi14'],50)

    def test_expired_data_fails_closed(self):
        a=M.analyze(dataset(),BASE+100*STEP)
        r=M.decision({'4h':a},BASE+100*STEP)
        self.assertEqual(r['status'],'DONNÉES INSUFFISANTES')

    def test_missing_secondary_timeframe_blocks_buy(self):
        a=M.analyze(dataset(),BASE+90*STEP)
        self.assertEqual(M.decision({'4h':a},BASE+90*STEP)['status'],'DONNÉES INSUFFISANTES')

    def test_future_clock_rejected(self):
        a=M.analyze(dataset(),BASE+90*STEP)
        self.assertEqual(M.decision({'4h':a,'1h':a},BASE)['status'],'DONNÉES INSUFFISANTES')

    def test_buy_signal_blocked_without_actual_costs(self):
        n=100000
        a={'trend':'HAUSSIER','close':100,'support20':90,'resistance20':150,'atr14':2,'macd_improving':True,'rsi_delta':2,'volume_ratio':2,'rsi_divergence':False}
        f={'ready':True,'quality':{'last_close':n},'latest':a}
        r=M.decision({'4h':f,'1h':f},n)
        self.assertEqual(r['technical_signal'],'ACHAT CONFIRMÉ')
        self.assertEqual(r['status'],'ATTENDRE')

class Risk(unittest.TestCase):
    def test_risk_fee_and_cash_cap(self):
        r=M.risk_plan(1000,100,98,110,.004,.003)
        self.assertTrue(r['admissible'])
        self.assertLessEqual(r['planned_risk_usd'],2.5+1e-9)
        self.assertLessEqual(r['cash_required'],1000)
        self.assertLess(r['rr_net'],r['rr_gross'])

    def test_gross_rr_strictly_greater_than_1_5(self):
        self.assertFalse(M.risk_plan(1000,100,98,103,0,0)['admissible'])
        self.assertFalse(M.risk_plan(1000,100,90,116,.02,0)['admissible'])

    def test_invalid_input_rejected(self):
        for x in [0,-1,float('nan'),float('inf')]:
            self.assertFalse(M.risk_plan(1000,x,98,105,0,0)['admissible'])
        self.assertFalse(M.risk_plan(1000,100,101,105,0,0)['admissible'])
        self.assertFalse(M.risk_plan(1000,100,98,105,-.1,0)['admissible'])

    def test_cash_limited_sizing(self):
        r=M.risk_plan(1000,100,99.999,101,0,0)
        self.assertEqual(r['quantity'],10)
        self.assertLess(r['planned_risk_usd'],2.5)

    def test_unrepresentable_arithmetic_fails_closed(self):
        for args in [(1000,1e-320,5e-321,2e-320,0,0),
                     (1e308,1e308,9e307,1.7e308,.09,.09)]:
            self.assertFalse(M.risk_plan(*args)['admissible'])

    def test_does_not_round_quantity_up(self):
        r=M.risk_plan(1000,.0015,.0014,.0018,.004,.003)
        self.assertLessEqual(r['planned_risk_usd'],2.5+1e-9)
