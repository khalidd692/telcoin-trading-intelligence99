"""One finite batch of public Kraken OHLC reads; no credentials or orders.

python -m scripts.terminal.collect --output /path/new_capture.json
The output is created exclusively: existing captures cannot be overwritten.
Kraken returns at most 720 recent bars; use this for monitoring, not to replace
long research histories. Feed to build --market-input; research stays pinned.
"""
import argparse
import concurrent.futures
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

CONFIG={'tel15m':('KRAKEN:TELUSD','15m',15),'tel1h':('KRAKEN:TELUSD','1h',60),
        'tel4h':('KRAKEN:TELUSD','4h',240),'tel1d':('KRAKEN:TELUSD','1D',1440),
        'btc4h':('KRAKEN:XBTUSD','4h',240),'eth4h':('KRAKEN:ETHUSD','4h',240)}
ALIASES={'KRAKEN:TELUSD':{'TELUSD'},'KRAKEN:XBTUSD':{'XXBTZUSD','XBTUSD'},
         'KRAKEN:ETHUSD':{'XETHZUSD','ETHUSD'}}

def normalize(payload,symbol,interval):
    if payload.get('error'):raise ValueError('Kraken error: '+str(payload['error']))
    result=payload.get('result',{})
    keys=set(result)-{'last'}
    if len(keys)!=1 or not keys.issubset(ALIASES[symbol]):raise ValueError('Unexpected Kraken pair')
    key=next(iter(keys));rows=result[key]
    if not rows:raise ValueError('Empty Kraken history')
    bars=[dict(t=int(r[0]),o=float(r[1]),h=float(r[2]),l=float(r[3]),c=float(r[4]),v=float(r[6])) for r in rows]
    return {'symbol':symbol,'interval':interval,'success':True,'bars':bars,
            'count':len(bars),'returned_pair':key,'notice':'Kraken public OHLC, recent 720-bar limit; final candle may be forming.'}

def fetch(config):
    symbol,interval,minutes=config
    url='https://api.kraken.com/0/public/OHLC?'+urllib.parse.urlencode({'pair':symbol.split(':')[1],'interval':minutes})
    with urllib.request.urlopen(url,timeout=20) as response:
        raw=response.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('Unexpected response size')
        payload=json.loads(raw)
    result=normalize(payload,symbol,interval)
    result.update(endpoint=url,received_at=dt.datetime.now(dt.timezone.utc).isoformat())
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise SystemExit('Capture already exists; choose a new filename')
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures={k:pool.submit(fetch,c) for k,c in CONFIG.items()}
        datasets={k:f.result() for k,f in futures.items()}
    data={'captured_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source':'Kraken public REST / OHLC',
          'datasets':datasets}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:json.dump(data,f,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    print(json.dumps({'output':str(args.output),'captured_at':data['captured_at'],'counts':{k:v['count'] for k,v in datasets.items()}}))
if __name__=='__main__':main()
