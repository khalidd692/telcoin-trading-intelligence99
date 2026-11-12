"""Build a deterministic terminal snapshot from an explicitly captured MCP export.

Usage: python -m scripts.terminal.build [--input path] [--output site/terminal/data.json]
No network calls. No order APIs. No legacy result files rewritten.
"""
import argparse
import hashlib
import json
from pathlib import Path
from src.terminal import model as M
from scripts.terminal import research
ROOT=Path(__file__).resolve().parents[2]

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def event_view(row):
    """Expose the actual horizon of the existing floor-to-bars event study."""
    hours=M.STEPS[row['timeframe']]/3600
    effective=int(row['horizon_hours']/hours)*hours
    return {**row,'effective_horizon_hours':effective}

def build(source, market_source=None):
    historical=json.loads(source.read_text())
    historical_asof=M.dt.datetime.fromisoformat(historical['captured_at'].replace('Z','+00:00')).timestamp()
    historical_rows=M.validate_dataset(historical['datasets']['tel4h'],historical_asof)['bars']
    cache_path=ROOT/'results/terminal/experiments.json'
    cached=json.loads(cache_path.read_text()) if cache_path.exists() else {}
    study=cached if cached.get('fingerprint')==research.fingerprint(historical_rows) else research.run(historical_rows)
    source_for_market=market_source or source
    raw=json.loads(source_for_market.read_text());asof=M.dt.datetime.fromisoformat(raw['captured_at'].replace('Z','+00:00')).timestamp()
    analyzed={key:M.analyze(value,asof) for key,value in raw['datasets'].items()}
    frames={f['interval']:f for f in analyzed.values() if f['symbol']=='KRAKEN:TELUSD'}
    existing=json.loads((ROOT/'results/entry_research/results.json').read_text())
    frozen=json.loads((ROOT/'results/strategy_validation/results.json').read_text())
    # Ship only chart fields per bar; latest retains the complete indicator set.
    for frame in frames.values():
        frame['series']=[{k:r[k] for k in ('t','ema20','ema50','sma200','rsi14','macd_hist','vwap_session')}
                         for r in frame['series']]
    return {'schema_version':1,'market':'KRAKEN:TELUSD','captured_at':raw['captured_at'],
            'source':raw['source'],'source_path':source_for_market.relative_to(ROOT).as_posix() if source_for_market.is_relative_to(ROOT) else source_for_market.name,
            'source_sha256':digest(source_for_market),'research_source_sha256':digest(source),'as_of':asof,'frames':frames,
            'context':{k:{'symbol':analyzed[k]['symbol'],'latest':analyzed[k]['latest'],
                           'quality':analyzed[k]['quality'],
                           'correlation':M.correlation(frames['4h']['bars'],analyzed[k]['bars'])}
                       for k in ('btc4h','eth4h') if k in analyzed},
            'decision':M.decision(frames,asof),
            'lab':{'frozen':frozen,'events':[event_view(r) for r in existing['comparisons']],'event_protocol':existing['protocol'],
                   'event_conclusion':existing['conclusion'],'experiments':study},
            'safety':{'real_orders':False,'paper_orders':False,'capital_reference':1000,'risk_fraction':.0025,'min_rr':1.51},
            'code_sha256':{p:digest(ROOT/p) for p in ['src/terminal/model.py','scripts/terminal/build.py','scripts/terminal/research.py','scripts/strategy_backtest/engine.py','src/agent_analysis.py']},
            'limits':['Les fenêtres historiques ont déjà été explorées ; aucun holdout vierge.',
                      'Les trous peuvent correspondre à des périodes sans transactions : aucune interpolation.',
                      'RSI14 arithmétique glissant ; ATR Wilder ; VWAP limité à une session UTC entièrement observée.',
                      'Les coûts sont hypothétiques. Aucun carnet historique, aucune probabilité calibrée.',
                      'Les sources externes ne se rafraîchissent pas automatiquement quand cette page est fermée.']}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,default=ROOT/'research/terminal/raw/tradingview_2026-11-10.json')
    p.add_argument('--market-input',type=Path,help='Optional new market capture; research sample stays fixed')
    p.add_argument('--output',type=Path,default=ROOT/'site/terminal/data.json')
    p.add_argument('--no-study-write',action='store_true',help='Build a market snapshot without writing any laboratory result files')
    args=p.parse_args();data=build(args.input.resolve(),args.market_input.resolve() if args.market_input else None)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
    if not args.no_study_write:
        study_path=ROOT/'results/terminal/experiments.json';study_path.parent.mkdir(parents=True,exist_ok=True)
        study_path.write_text(json.dumps(data['lab']['experiments'],ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'output':str(args.output),'sha256':digest(args.output),'decision':data['decision']['status'],
        'frames':{k:{x:v['quality'][x] for x in ['valid_bars','missing_bars','last_segment_bars','fresh']} for k,v in data['frames'].items()},
        'experiments':{k:[r['costs']['central']['n'] for r in v] for k,v in data['lab']['experiments']['families'].items()}},indent=2))
if __name__=='__main__':main()
