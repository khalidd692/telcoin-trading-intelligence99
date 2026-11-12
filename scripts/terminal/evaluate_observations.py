"""TEL99 read-only forward observation journal. No orders, no simulated trades."""
import argparse
import csv
import datetime as dt
import io
import json
import math
from pathlib import Path
import urllib.request

FIELDS = ["observed_at","snapshot_at","market","decision","scenario","scenario_status","entry","stop","target","rr_net","price","price_source","price_at","data_valid","reason","r_1h","r_4h","r_24h","r_7d","outcome_1h","outcome_4h","outcome_24h","outcome_7d"]
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
            or not f.get("ready") or not finite(close) or close>now or now-close>step+300):
            valid=False
    dec=d.get("decision") or {}
    plan=dec.get("plan") or {}
    return dict(observed_at=now,snapshot_at=value(stamp),market=d.get("market",""),decision=dec.get("status",""),scenario=plan.get("name",plan.get("id","")),scenario_status=plan.get("status",""),entry=value(plan.get("entry",plan.get("entry_usd"))),stop=value(plan.get("stop")),target=value(plan.get("target")),rr_net=value(plan.get("rr_net",plan.get("rrNet"))),price=value(price),price_source="Kraken OHLC 15m closed candle",price_at=value((frames.get("15m") or {}).get("quality",{}).get("last_close")),data_valid=str(bool(valid)).lower(),reason="" if valid else "STALE_OR_INCOMPLETE")
def update(rows,now):
    # Observation outcomes are price-to-price changes, NOT backtested fills, profit or trade results.
    for row in rows:
        if row.get("data_valid")!="true": continue
        try: start=float(row["observed_at"]); base=float(row["price"])
        except (ValueError,TypeError,KeyError): continue
        if base<=0: continue
        for label,seconds in HORIZONS.items():
            key="r_"+label
            if row.get(key): continue
            # Select first valid observation at or after the horizon, within 2h tolerance.
            eligible=[]
            for later in rows:
                try:
                    t=float(later["observed_at"]);p=float(later["price"])
                    if later.get("data_valid")=="true" and start+seconds<=t<=min(now,start+seconds+7200) and p>0:
                        eligible.append((t,p))
                except (ValueError,TypeError,KeyError): pass
            if eligible:
                t,p=min(eligible)
                row[key]=format((p/base-1)*100,".5f")
                row["outcome_"+label]="OBSERVED_PRICE_RETURN_ONLY"
            elif now>start+seconds+7200:
                row["outcome_"+label]="MISSING_OBSERVATION"
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--journal",default="evaluation/observations.csv")
    ap.add_argument("--report",default="evaluation/summary.json")
    ap.add_argument("--snapshot",help="Local JSON fixture for testing")
    ap.add_argument("--now",type=int)
    args=ap.parse_args()
    now=args.now or int(dt.datetime.now(dt.timezone.utc).timestamp())
    path=Path(args.journal)
    rows=list(csv.DictReader(io.StringIO(path.read_text()))) if path.exists() else []
    try:
        d=json.loads(Path(args.snapshot).read_text()) if args.snapshot else load(URL+"?t="+str(now))
        row=observe(d,now)
    except (OSError,ValueError,KeyError) as exc:
        row=dict(observed_at=now,snapshot_at="",market="KRAKEN:TELUSD",decision="DONNÉES INSUFFISANTES",scenario="",scenario_status="",entry="",stop="",target="",rr_net="",price="",price_source="",price_at="",data_valid="false",reason="FETCH_OR_PARSE_FAILED:"+type(exc).__name__)
    # Preserve append-only observations; idempotent per snapshot + decision + price.
    if not any(r.get("snapshot_at")==str(row["snapshot_at"]) and r.get("decision")==row["decision"] and r.get("price")==str(row["price"]) for r in rows if row["snapshot_at"]):
        rows.append({k:str(row.get(k,"")) for k in FIELDS})
    update(rows,now)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows([{k:r.get(k,"") for k in FIELDS} for r in rows])
    valid=[r for r in rows if r.get("data_valid")=="true"]
    report={"generated_at":now,"observations":len(rows),"valid_observations":len(valid),"latest_decision":row["decision"],"latest_valid":row["data_valid"],"horizons":{},"disclaimer":"Observational price changes only; NOT simulated trades, executed orders, strategy validation, or profitability."}
    for h in HORIZONS:
        nums=[float(r["r_"+h]) for r in valid if r.get("r_"+h)]
        report["horizons"][h]={"count":len(nums),"mean_pct":round(sum(nums)/len(nums),5) if nums else None,"positive_fraction":round(sum(x>0 for x in nums)/len(nums),4) if nums else None}
    rp=Path(args.report);rp.parent.mkdir(parents=True,exist_ok=True);rp.write_text(json.dumps(report,indent=2)+String.fromCharCode(92)+"n")
    print(json.dumps(report))
if __name__=="__main__":main()
