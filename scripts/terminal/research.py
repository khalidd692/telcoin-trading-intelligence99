"""Two predeclared experimental families, reusing the unchanged simulator."""
import dataclasses
import datetime as dt
import hashlib
import json
from pathlib import Path
from src.terminal import model as M
from src import agent_analysis as A
from scripts.strategy_backtest import engine as E
ROOT=Path(__file__).resolve().parents[2]
PROTOCOL=ROOT/'research/terminal/EXPERIMENT_PROTOCOL.json'

def bars(rows):
    return [E.Bar(dt.datetime.fromtimestamp(r['t'],M.UTC),r['o'],r['h'],r['l'],r['c'],r['v']) for r in rows]

def signals(rows, family):
    if family not in ('breakout20','recovery30'):raise ValueError('Unknown experiment')
    out=[]
    for seg in E.build_segments(bars(rows),E.Params()):
        rsi=A.rsi_series([b.c for b in seg.bars])
        for i in range(50,seg.n):
            b=seg.bars[i];prior=seg.bars[i-20:i]
            if family=='breakout20':
                volume=sum(x.v for x in prior)/20
                signal=b.c>max(x.h for x in prior) and seg.e_fast[i]>seg.e_slow[i] and volume>0 and b.v>=1.5*volume
            else:signal=rsi[i-1]<=30<rsi[i] and b.c>seg.bars[i-1].h
            if signal:
                out.append({'index':seg.offset+i,'signal_ts':b.close_ts.isoformat(),
                            'stop':min(x.l for x in seg.bars[i-9:i+1])-.5*seg.atr[i]})
    return out

def orders(rows,family):
    p=E.Params();segs=E.build_segments(bars(rows),p);out=[]
    for s in signals(rows,family):
        seg=next(seg for seg in segs if seg.offset<=s['index']<seg.offset+seg.n)
        i=s['index']-seg.offset
        if i+1+p.expiry_bars>=seg.n:continue
        entry=seg.bars[i+1].o;stop=s['stop']
        c=E.Candidate(s['index'],family,seg,entry=entry,stop=stop,target=entry+2*(entry-stop),rr_gross=2)
        c.status='ok' if 0<stop<entry else 'rejet:stop_invalide'
        out.append(c)
    return out

def evaluate(rows,family,start,end):
    p=E.Params();all_orders=[c for c in orders(rows,family) if start<=c.t<end]
    # A fully closed holding window must remain inside the evaluation fold.
    eligible=[c for c in all_orders if c.t+1+p.expiry_bars<end]
    result={'start':M.iso(rows[start]['t']),'end_exclusive':M.iso(rows[end-1]['t']+14400),
            'candidates':len(all_orders),'boundary_excluded':len(all_orders)-len(eligible),'costs':{}}
    for name,cost in E.COSTS.items():
        trades,log=E.run(eligible,p,cost,start,end,state=E.RunState(p,cost))
        metrics=E.metrics(trades,1000)
        metrics={k:(v if not isinstance(v,float) or M.finite(v) else None) for k,v in metrics.items()}
        metrics.update(ending_equity=trades[-1].equity_after if trades else 1000,
                       trades=[dataclasses.asdict(t) for t in trades],candidate_log=log)
        for key in ('expectancy_R','profit_factor','max_drawdown_pct'):metrics.setdefault(key,None)
        # Equal time window, unequal risk budget; comparison is descriptive only.
        buy=rows[start]['o']*(1+cost.slip)*(1+cost.fee)
        sell=rows[end-1]['c']*(1-cost.slip)*(1-cost.fee)
        metrics['buy_hold_return_pct']=100*(sell/buy-1)
        metrics['cash_return_pct']=0
        result['costs'][name]=metrics
    return result

def fingerprint(rows):
    paths=[PROTOCOL,Path(__file__),ROOT/'scripts/strategy_backtest/engine.py',ROOT/'src/agent_analysis.py']
    return {'data_sha256':hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest(),
            'code_and_protocol_sha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}

def run(rows):
    n=len(rows);edges=[int(n*x) for x in (.5,2/3,5/6,1)]
    return {'fingerprint':fingerprint(rows),'protocol':json.loads(PROTOCOL.read_text()),
            'protocol_sha256':hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
            'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'rows':n,'verdict':'EXPLORATOIRE — AUCUNE STRATÉGIE VALIDÉE',
            'families':{family:[evaluate(rows,family,a,b) for a,b in zip(edges,edges[1:])]
                        for family in ('breakout20','recovery30')}}
