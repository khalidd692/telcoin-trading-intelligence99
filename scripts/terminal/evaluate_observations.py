"""TEL99 read-only forward observation journal. No orders, no simulated trades."""
import argparse
import csv
import copy
import datetime as dt
import hashlib
import io
import json
import math
import subprocess
from pathlib import Path
import urllib.request

FIELDS = ["observed_at","snapshot_at","market","decision","scenario","scenario_status","entry","stop","target","rr_net","price","price_source","price_at","data_valid","reason","r_1h","r_4h","r_24h","r_7d","outcome_1h","outcome_4h","outcome_24h","outcome_7d","factors","event"]
HORIZONS = {"1h":3600,"4h":14400,"24h":86400,"7d":604800}
URL = "https://raw.githubusercontent.com/khalidd692/telcoin-trading-intelligence99/tel99-live-data/site/terminal/data.json"
def finite(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def load(url):
    req=urllib.request.Request(url,headers={"User-Agent":"TEL99-readonly-evaluator/1","Cache-Control":"no-cache"})
    with urllib.request.urlopen(req,timeout=20) as resp:
        return json.load(resp)
def value(x):
    return x if finite(x) else ""

def read_journal(path):
    """Reject missing, truncated or incompatible history; never initialise it silently."""
    raw=path.read_bytes()
    if not raw or not raw.endswith(b'\n'):
        raise ValueError('missing or truncated observation journal')
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8'), newline=''), strict=True)
    if reader.fieldnames != FIELDS:
        raise ValueError('unexpected observation journal schema')
    rows=list(reader)
    previous=-math.inf
    for row in rows:
        if None in row or any(v is None for v in row.values()):
            raise ValueError('malformed observation row')
        try: timestamp=float(row['observed_at'])
        except (TypeError,ValueError): raise ValueError('invalid observation timestamp')
        if not math.isfinite(timestamp): raise ValueError('invalid observation timestamp')
        if timestamp<previous: raise ValueError('observation timestamps are not ordered')
        previous=timestamp
    return rows

def append_observation(path,row):
    read_journal(path)
    with path.open('a',newline='',encoding='utf-8') as f:
        csv.DictWriter(f,fieldnames=FIELDS).writerow({k:row.get(k,'') for k in FIELDS})

def record_id(*parts):
    return hashlib.sha256(json.dumps(parts,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def observation_id(row):
    return record_id(row.get('market'),row.get('snapshot_at'),row.get('observed_at'),
                     row.get('price_at'),row.get('data_valid'))

def append_records(path,records):
    seen=set()
    if path.exists():
        raw=path.read_bytes()
        if raw and not raw.endswith(b'\n'): raise ValueError('truncated evidence file')
        for line in raw.decode('utf-8').splitlines():
            record=json.loads(line)
            if not isinstance(record,dict) or not isinstance(record.get('id'),str):
                raise ValueError('malformed evidence record')
            seen.add(record['id'])
    new=[]
    for record in records:
        if record['id'] not in seen:
            new.append(record);seen.add(record['id'])
    if new:
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('a',encoding='utf-8') as f:
            for record in new:f.write(json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n')
    return new
def observe(d,now):
    stamp=d.get("as_of")
    frames=d.get("frames") or {}
    latest=(frames.get("15m") or {}).get("latest") or {}
    price=latest.get("close")
    valid=(d.get("schema_version")==1 and d.get("market")=="KRAKEN:TELUSD"
           and d.get("source")=="Kraken public REST / OHLC"
           and (d.get("safety") or {}).get("real_orders") is False
           and (d.get("safety") or {}).get("paper_orders") is False
           and finite(stamp) and 0<=now-stamp<=900 and finite(price) and price>0)
    for tf,step in [("15m",900),("1h",3600),("4h",14400),("1D",86400)]:
        f=frames.get(tf) or {}
        close=(f.get("quality") or {}).get("last_close")
        if (f.get("symbol")!="KRAKEN:TELUSD" or f.get("interval")!=tf
            or not f.get("ready") or not finite(close) or close>now or not finite(stamp) or close>stamp or now-close>step+300):
            valid=False
    radar = d.get("radar") or {}
    radar_valid = (radar.get("asOf") == stamp
                   and radar.get("closedAt") == (frames.get("15m") or {}).get("quality", {}).get("last_close"))
    if radar_valid and radar.get("status") == "DONNÉES INSUFFISANTES":
        valid = False
    dec = d.get("decision") or {}
    plan = dec.get("plan") or {}
    status = (radar.get("status") if radar_valid else dec.get("status")) or "ATTENDRE"
    event = radar.get("event") if valid and radar_valid else None
    factors = [f["id"] for f in radar.get("factors", []) if f.get("active") is True] if valid and radar_valid else []
    return dict(observed_at=now,snapshot_at=value(stamp),market=d.get("market",""),decision=status if valid else "DONNÉES INSUFFISANTES",scenario=plan.get("name",plan.get("id","")),scenario_status=plan.get("status",""),entry=value(plan.get("entry",plan.get("entry_usd"))),stop=value(plan.get("stop")),target=value(plan.get("target")),rr_net=value(plan.get("rr_net",plan.get("rrNet"))),price=value(price),price_source="Kraken OHLC 15m closed candle",price_at=value((frames.get("15m") or {}).get("quality",{}).get("last_close")),data_valid=str(bool(valid)).lower(),reason="" if valid else "STALE_OR_INCOMPLETE",factors=json.dumps(factors),event=json.dumps(event) if event else "")

def decision_history(rows):
    history, seen = [], set()
    previous = None
    for row in sorted(rows, key=lambda r: float(r["observed_at"])):
        valid = row.get("data_valid") == "true"
        status = row.get("decision") if valid else "DONNÉES INSUFFISANTES"
        factors = set(json.loads(row.get("factors") or "[]")) if valid else set()
        event = json.loads(row.get("event") or "null") if valid else None
        if event:
            if event["id"] in seen:
                event = None
            else:
                seen.add(event["id"])
        state = (status, valid, factors)
        if state != previous or event:
            old = previous[2] if previous else set()
            history.append({"observed_at": int(float(row["observed_at"])),
                            "previous_decision": previous[0] if previous else None,
                            "decision": status, "data_valid": valid,
                            "changed_factors": ["+ " + f for f in sorted(factors-old)] +
                                               ["− " + f for f in sorted(old-factors)],
                            "event": event})
        previous = state
    return history[-12:]

def update(rows,now,metadata=None):
    # Observation outcomes are price-to-price changes, NOT backtested fills, profit or trade results.
    for row in rows:
        if row.get("data_valid")!="true": continue
        try:
            observed=float(row["observed_at"]); start=float(row["price_at"]); base=float(row["price"])
        except (ValueError,TypeError,KeyError): continue
        if not all(math.isfinite(x) for x in (observed,start,base)) or base<=0 or start>observed or observed>now: continue
        method=(metadata or {}).get(observation_id(row),{}).get('outcome_method','closed_candle_time_v2')
        origin=observed if method=='observation_time_v3' else start
        for label,seconds in HORIZONS.items():
            key="r_"+label
            if row.get(key): continue
            # Select first valid observation at or after the horizon, within 2h tolerance.
            eligible=[]
            for later in rows:
                try:
                    observed_later=float(later["observed_at"]);t=float(later["price_at"]);p=float(later["price"])
                    if (later.get("data_valid")=="true" and all(math.isfinite(x) for x in (observed_later,t,p))
                        and origin+seconds<=t<=origin+seconds+7200 and t<=observed_later<=now and p>0):
                        eligible.append((t,observed_later,p))
                except (ValueError,TypeError,KeyError): pass
            if eligible:
                t,seen_at,p=min(eligible)
                row[key]=format((p/base-1)*100,".5f")
                row["outcome_"+label]="OBSERVED_PRICE_RETURN_ONLY"
                row["outcome_price_at_"+label]=t
                row["outcome_observed_at_"+label]=seen_at
                row["outcome_price_"+label]=p
            elif now>origin+seconds+7200:
                row["outcome_"+label]="MISSING_OBSERVATION"

def append_outcomes(path,rows,now,metadata_path=None):
    """Append price outcomes separately; never change prior observation rows."""
    metadata={}
    if metadata_path and metadata_path.exists():
        metadata={x['observation_id']:x for x in (json.loads(line) for line in metadata_path.read_text(encoding='utf-8').splitlines())}
    scored=copy.deepcopy(rows);update(scored,now,metadata)
    records=[]
    for original,row in zip(rows,scored):
        for horizon in HORIZONS:
            status=row.get('outcome_'+horizon)
            if not status or original.get('outcome_'+horizon):continue
            result=row.get('r_'+horizon)
            oid=observation_id(original)
            records.append({'id':record_id(oid,horizon),'observation_id':oid,'horizon':horizon,
                            'status':status,'price_return_pct':float(result) if result else None,
                            'outcome_price_at':row.get('outcome_price_at_'+horizon),
                            'outcome_observed_at':row.get('outcome_observed_at_'+horizon),
                            'outcome_close':row.get('outcome_price_'+horizon),
                            'rsi_method':metadata.get(oid,{}).get('rsi_method','legacy_or_unknown'),
                            'method':metadata.get(oid,{}).get('outcome_method','closed_candle_time_v2'),
                            'disclaimer':'Observed price return only; not a trade or profit.'})
    append_records(path,records)
    return scored

def append_transitions(path,rows):
    previous=None;records=[];seen_events=set()
    for row in sorted(rows,key=lambda r:float(r['observed_at'])):
        valid=row.get('data_valid')=='true'
        status=row.get('decision') if valid else 'DONNÉES INSUFFISANTES'
        factors=set(json.loads(row.get('factors') or '[]')) if valid else set()
        event=json.loads(row.get('event') or 'null') if valid else None
        if event and event.get('id') in seen_events:event=None
        if event:seen_events.add(event['id'])
        state=(status,valid,factors)
        if state!=previous or event:
            oid=observation_id(row);old=previous[2] if previous else set()
            records.append({'id':record_id('transition',oid),'observation_id':oid,
                            'observed_at':float(row['observed_at']),
                            'previous_decision':previous[0] if previous else None,'decision':status,
                            'changed_factors':['+ '+x for x in sorted(factors-old)]+['− '+x for x in sorted(old-factors)],
                            'event':event})
        previous=state
    append_records(path,records)
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--journal",default="evaluation/observations.csv")
    ap.add_argument("--report",default="evaluation/summary.json")
    ap.add_argument("--snapshot",help="Local JSON fixture for testing")
    ap.add_argument("--now",type=int)
    ap.add_argument("--radar", type=Path, help="Path to the shared product radar.js")
    args=ap.parse_args()
    now=args.now or int(dt.datetime.now(dt.timezone.utc).timestamp())
    path=Path(args.journal)
    rows=read_journal(path)
    outcomes_path=path.parent/'outcomes.jsonl'
    events_path=path.parent/'events.jsonl'
    metadata_path=path.parent/'observation_metadata.jsonl'
    # Validate existing sidecars before modifying any local evidence.
    for sidecar in (outcomes_path,events_path,metadata_path):append_records(sidecar,[])
    d=None
    try:
        d=json.loads(Path(args.snapshot).read_text()) if args.snapshot else load(URL+"?t="+str(now))
        if args.radar and not d.get("radar"):
            check = subprocess.run(["node", str(args.radar.resolve()), str(now)], input=json.dumps(d),
                                   text=True, capture_output=True, check=True, timeout=10)
            d["radar"] = json.loads(check.stdout)
        row=observe(d,now)
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
        row=dict(observed_at=now,snapshot_at="",market="KRAKEN:TELUSD",decision="DONNÉES INSUFFISANTES",scenario="",scenario_status="",entry="",stop="",target="",rr_net="",price="",price_source="",price_at="",data_valid="false",reason="FETCH_OR_PARSE_FAILED:"+type(exc).__name__)
    # Keep consecutive identical observations idempotent and retain validity transitions.
    if not rows or any(rows[-1].get(k)!=str(row.get(k,"")) for k in ("snapshot_at","decision","price","data_valid","factors","reason")):
        row={k:str(row.get(k,"")) for k in FIELDS}
        append_observation(path,row);rows.append(row)
        plan=(d or {}).get('decision',{}).get('plan') or {}
        oid=observation_id(row)
        append_records(metadata_path,[{'id':record_id('metadata',oid),'observation_id':oid,
          'product_commit':((d or {}).get('publication') or {}).get('product_commit'),
          'rsi_method':(((d or {}).get('frames') or {}).get('15m') or {}).get('indicator_methods',{}).get('rsi14','legacy_or_unknown'),
          'outcome_method':'observation_time_v3',
          'fee_per_side_hypothesis':plan.get('fee_per_side'),
          'slippage_per_side_hypothesis':plan.get('slippage_per_side'),
          'personal_fees_verified':False,'execution':'no trades or orders'}])
    scored=append_outcomes(outcomes_path,rows,now,metadata_path)
    append_transitions(events_path,rows)
    valid=[r for r in scored if r.get("data_valid")=="true"]
    report={"generated_at":now,"observations":len(rows),"valid_observations":len(valid),"latest_decision":row["decision"],"latest_valid":row["data_valid"],"horizons":{},"disclaimer":"Observational price changes only; NOT simulated trades, executed orders, strategy validation, or profitability."}
    report["recent_decisions"] = decision_history(rows)
    report["outcome_method"]="closed_candle_time_v2 for legacy; observation_time_v3 for new observations; original records preserved"
    outcomes=[json.loads(line) for line in outcomes_path.read_text(encoding='utf-8').splitlines()] if outcomes_path.exists() else []
    report["legacy_results_preserved"]=True
    for h in HORIZONS:
        available=[r for r in outcomes if r.get('horizon')==h and r.get('status')=='OBSERVED_PRICE_RETURN_ONLY' and finite(r.get('price_return_pct'))]
        relevant=[r for r in available if r.get('method','closed_candle_time_v2')=='closed_candle_time_v2']
        grouped={}
        for method in sorted({r.get('rsi_method','legacy_or_unknown') for r in relevant}):
            nums=[r['price_return_pct'] for r in relevant if r.get('rsi_method','legacy_or_unknown')==method]
            grouped[method]={"count":len(nums),"mean_pct":round(sum(nums)/len(nums),5),"positive_fraction":round(sum(x>0 for x in nums)/len(nums),4)}
        current=grouped.get('wilder_rma_14_sma_seed',{'count':0,'mean_pct':None,'positive_fraction':None})
        by_outcome_method={}
        for method in sorted({r.get('method','closed_candle_time_v2') for r in available}):
            subset=[r for r in available if r.get('method','closed_candle_time_v2')==method]
            per_rsi={}
            for rsi in sorted({r.get('rsi_method','legacy_or_unknown') for r in subset}):
                nums=[r['price_return_pct'] for r in subset if r.get('rsi_method','legacy_or_unknown')==rsi]
                per_rsi[rsi]={'count':len(nums),'mean_pct':round(sum(nums)/len(nums),5)}
            by_outcome_method[method]={'by_rsi_method':per_rsi}
        report["horizons"][h]={**current,'rsi_method':'wilder_rma_14_sma_seed','by_rsi_method':grouped,'by_outcome_method':by_outcome_method}
    rp=Path(args.report);rp.parent.mkdir(parents=True,exist_ok=True);rp.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report))
if __name__=="__main__":main()
