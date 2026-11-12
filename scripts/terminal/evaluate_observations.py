"""TEL99 read-only forward observation journal. No orders, no simulated trades."""
import argparse
import csv
import datetime as dt
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
    ap.add_argument("--radar", type=Path, help="Path to the shared product radar.js")
    args=ap.parse_args()
    now=args.now or int(dt.datetime.now(dt.timezone.utc).timestamp())
    path=Path(args.journal)
    rows=list(csv.DictReader(io.StringIO(path.read_text()))) if path.exists() else []
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
    if not rows or not row["snapshot_at"] or any(rows[-1].get(k)!=str(row[k]) for k in ("snapshot_at","decision","price","data_valid","factors")):
        rows.append({k:str(row.get(k,"")) for k in FIELDS})
    update(rows,now)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows([{k:r.get(k,"") for k in FIELDS} for r in rows])
    valid=[r for r in rows if r.get("data_valid")=="true"]
    report={"generated_at":now,"observations":len(rows),"valid_observations":len(valid),"latest_decision":row["decision"],"latest_valid":row["data_valid"],"horizons":{},"disclaimer":"Observational price changes only; NOT simulated trades, executed orders, strategy validation, or profitability."}
    report["recent_decisions"] = decision_history(rows)
    for h in HORIZONS:
        nums=[float(r["r_"+h]) for r in valid if r.get("r_"+h)]
        report["horizons"][h]={"count":len(nums),"mean_pct":round(sum(nums)/len(nums),5) if nums else None,"positive_fraction":round(sum(x>0 for x in nums)/len(nums),4) if nums else None}
    rp=Path(args.report);rp.parent.mkdir(parents=True,exist_ok=True);rp.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report))
if __name__=="__main__":main()
