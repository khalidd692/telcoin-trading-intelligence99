#!/usr/bin/env python3
"""Read-only public TEL/USDT market collector. Missing fields remain null."""
import argparse, hashlib, json, math, os, socket, ssl, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
PARIS = ZoneInfo("Europe/Paris")
SYMBOLS = {"mexc": ("https://api.mexc.com", "TELUSDT"), "kucoin": ("https://api.kucoin.com", "TEL-USDT")}
INTERVALS = {
    "15m": {"mexc": "15m", "kucoin": "15min", "seconds": 900},
    "1h": {"mexc": "60m", "kucoin": "1hour", "seconds": 3600},
    "4h": {"mexc": "4h", "kucoin": "4hour", "seconds": 14400},
    "1d": {"mexc": "1d", "kucoin": "1day", "seconds": 86400},
    "1w": {"mexc": "1W", "kucoin": "1week", "seconds": 604800},
    "1M": {"mexc": "1M", "kucoin": "1month", "seconds": None},
}
UA = "telcoin-trading-intelligence-read-only/1.0"

def now_ms(): return int(time.time() * 1000)
def iso(ms):
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
def paris(ms): return datetime.fromtimestamp(ms / 1000, PARIS).isoformat(timespec="seconds")
def num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError): return None

def classify(exc):
    e = getattr(exc, "reason", exc)
    if isinstance(e, socket.gaierror): return "DNS_RESOLUTION"
    if isinstance(e, (socket.timeout, TimeoutError)): return "TIMEOUT"
    if isinstance(e, ssl.SSLError): return "TLS"
    if isinstance(exc, json.JSONDecodeError): return "BAD_JSON"
    return "NETWORK_" + type(exc).__name__

class Client:
    def __init__(self, venue): self.venue=venue; self.base,self.symbol=SYMBOLS[venue]; self.log=[]
    def get(self, path, params=None):
        url=self.base+path+("?" + urllib.parse.urlencode(params) if params else "")
        start=now_ms(); entry={"source":self.venue,"endpoint":path,"params":params or {},
          "t_request_utc":iso(start),"t_request_paris":paris(start),"http_status":None,"error":None}
        try:
            req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json","Cache-Control":"no-cache"})
            with urllib.request.urlopen(req,timeout=10) as res:
                body=res.read(3_000_000); end=now_ms()
                entry.update(http_status=res.status,latency_ms=end-start,t_response_utc=iso(end),bytes=len(body),
                  body_sha256_16=hashlib.sha256(body).hexdigest()[:16],
                  cache_headers={k:v for k,v in res.headers.items() if k.lower() in ("date","age","cache-control","cf-cache-status","x-cache")})
                if res.status != 200: raise RuntimeError("HTTP_"+str(res.status))
                data=json.loads(body.decode("utf-8"))
                if self.venue=="kucoin":
                    if not isinstance(data,dict) or data.get("code")!="200000": raise RuntimeError("KUCOIN_BAD_RESPONSE")
                    data=data.get("data")
                return data
        except urllib.error.HTTPError as e:
            entry.update(http_status=e.code,error="HTTP_"+str(e.code),latency_ms=now_ms()-start)
        except Exception as e:
            entry.update(error=classify(e),error_detail=str(e)[:160],latency_ms=now_ms()-start)
        finally:
            self.log.append(entry)
        return None

def parse_levels(rows):
    out=[]
    for row in rows or []:
        try:
            p,q=num(row[0]),num(row[1])
            if p is not None and q is not None and p>0 and q>0: out.append([p,q])
        except (TypeError,IndexError): pass
    return out

def spread(bid,ask):
    if not bid or not ask or bid<=0 or ask<=0 or ask<bid: return {"absolute":None,"pct_mid":None,"mid":None}
    mid=(bid+ask)/2
    return {"absolute":ask-bid,"pct_mid":(ask-bid)/mid*100,"mid":mid}

def buy_cost(asks,notional):
    asks=sorted(asks); best=asks[0][0] if asks else None
    remain=notional; qty=spent=0.0; worst=None; used=0
    for p,q in asks:
        take=min(remain,p*q)
        if take<=0: continue
        qty+=take/p; spent+=take; remain-=take; worst=p; used+=1
        if remain<=1e-8: break
    avg=spent/qty if qty else None
    return {"target_usdt":notional,"filled_usdt":spent,"complete":remain<=1e-8 and spent>0,
      "qty_tel":qty if qty else None,"avg_price":avg,"worst_price":worst,"levels_used":used,
      "slippage_vs_best_ask_pct":(avg/best-1)*100 if avg and best else None,
      "fees":"EXCLUDED_NOT_VERIFIED"}

def server_time(c):
    d=c.get("/api/v3/time") if c.venue=="mexc" else c.get("/api/v1/timestamp")
    if c.venue == "mexc" and isinstance(d, dict):
        v = d.get("serverTime")
        return int(v) if isinstance(v, (int, float)) else None
    # Client.get unwraps KuCoin's response; timestamp data is an integer.
    if c.venue == "kucoin" and isinstance(d, (int, float)):
        return int(d)
    return None

def fast(c):
    v=c.venue; sym=c.symbol
    if v=="mexc":
        l1=c.get("/api/v3/ticker/bookTicker",{"symbol":sym})
        book=c.get("/api/v3/depth",{"symbol":sym,"limit":100})
        trades=c.get("/api/v3/trades",{"symbol":sym,"limit":100})
    else:
        l1=c.get("/api/v1/market/orderbook/level1",{"symbol":sym})
        book=c.get("/api/v1/market/orderbook/level2_100",{"symbol":sym})
        trades=c.get("/api/v1/market/histories",{"symbol":sym})
    t0=now_ms(); st=server_time(c); t1=now_ms()
    if v=="mexc":
        best={"bid":num(l1.get("bidPrice")),"bid_qty":num(l1.get("bidQty")),"ask":num(l1.get("askPrice")),"ask_qty":num(l1.get("askQty"))} if isinstance(l1,dict) else None
        bids=parse_levels(book.get("bids")) if isinstance(book,dict) else []
        asks=parse_levels(book.get("asks")) if isinstance(book,dict) else []
        seq=book.get("lastUpdateId") if isinstance(book,dict) else None
        book_ts=next((book.get(k) for k in ("timestamp","time","ts") if isinstance(book.get(k),(int,float))),None) if isinstance(book,dict) else None
        tx=[]
        for x in (trades if isinstance(trades,list) else []):
            tx.append({"time_ms":x.get("time"),"price":num(x.get("price")),"qty":num(x.get("qty")),"quote_qty":num(x.get("quoteQty")),
              "side":"sell" if x.get("isBuyerMaker") is True else ("buy" if x.get("isBuyerMaker") is False else None),"id":x.get("id")})
    else:
        best={"bid":num(l1.get("bestBid")),"bid_qty":num(l1.get("bestBidSize")),"ask":num(l1.get("bestAsk")),"ask_qty":num(l1.get("bestAskSize")),
          "last":num(l1.get("price")),"level1_time_ms":l1.get("time")} if isinstance(l1,dict) else None
        bids=parse_levels(book.get("bids")) if isinstance(book,dict) else []
        asks=parse_levels(book.get("asks")) if isinstance(book,dict) else []
        seq=book.get("sequence") if isinstance(book,dict) else None
        book_ts=book.get("time") if isinstance(book,dict) else None
        tx=[]
        for x in (trades if isinstance(trades,list) else []):
            raw=x.get("time"); tms=(int(raw)//1_000_000 if str(raw).isdigit() else None)
            tx.append({"time_ms":tms,"price":num(x.get("price")),"qty":num(x.get("size")),"quote_qty":None,"side":x.get("side"),"id":x.get("sequence")})
    tx.sort(key=lambda x: x.get("time_ms") or 0,reverse=True)
    return {"server_time_ms":st,"local_mid_ms":(t0+t1)//2,"best":best,"bids":bids,"asks":asks,"sequence":seq,
      "book_time_ms":book_ts,"trades":tx}

def month_end_ms(open_ms):
    d=datetime.fromtimestamp(open_ms/1000,UTC)
    y,m=(d.year+1,1) if d.month==12 else (d.year,d.month+1)
    return int(datetime(y,m,1,tzinfo=UTC).timestamp()*1000)

def candles(c,server_ms):
    out={}
    for iv,meta in INTERVALS.items():
        if c.venue=="mexc":
            raw=c.get("/api/v3/klines",{"symbol":c.symbol,"interval":meta["mexc"],"limit":500})
            rows=[]
            if isinstance(raw,list):
                for k in raw:
                    try: rows.append([int(k[0]),num(k[1]),num(k[2]),num(k[3]),num(k[4]),num(k[5])])
                    except (ValueError,TypeError,IndexError): pass
        else:
            end=server_ms//1000 if server_ms else int(time.time())
            seconds=meta["seconds"] or 2678400
            raw=c.get("/api/v1/market/candles",{"symbol":c.symbol,"type":meta["kucoin"],
              "startAt":end-500*seconds,"endAt":end})
            rows=[]
            if isinstance(raw,list):
                for k in raw:
                    try: rows.append([int(k[0])*1000,num(k[1]),num(k[3]),num(k[4]),num(k[2]),num(k[5])])
                    except (ValueError,TypeError,IndexError): pass
        rows.sort(key=lambda x:x[0])
        # Deduplicate by candle open time; retain the last row returned for a timestamp.
        unique={}
        for row in rows:
            unique[row[0]]=row
        duplicates_dropped=len(rows)-len(unique)
        rows=list(unique.values())
        rows.sort(key=lambda x:x[0])
        valid=[]
        for r in rows:
            if not (all(x is not None and math.isfinite(x) for x in r) and min(r[1:5])>0 and r[5]>=0 and r[2]>=max(r[1],r[4],r[3]) and r[3]<=min(r[1],r[4])):
                continue
            if iv=="1M":
                from datetime import datetime, timezone
                opened=datetime.fromtimestamp(r[0]/1000,timezone.utc)
                # Monthly candles must be anchored to 00:00 UTC on day one.
                if (opened.day,opened.hour,opened.minute,opened.second,r[0] % 1000) != (1,0,0,0,0):
                    continue
                close_ms=month_end_ms(r[0])
            else:
                close_ms=r[0]+meta["seconds"]*1000
            if server_ms and close_ms<=server_ms: valid.append(r)
        # Count the uninterrupted tail of closed candles. A large total count can
        # otherwise hide holes in the most recent data used by indicators.
        contiguous_tail_count=0
        if valid:
            contiguous_tail_count=1
            for prev,cur in zip(reversed(valid[:-1]),reversed(valid[1:])):
                if iv=="1M":
                    from datetime import datetime, timezone
                    py,pm=datetime.fromtimestamp(prev[0]/1000,timezone.utc).year,datetime.fromtimestamp(prev[0]/1000,timezone.utc).month
                    cy,cm=datetime.fromtimestamp(cur[0]/1000,timezone.utc).year,datetime.fromtimestamp(cur[0]/1000,timezone.utc).month
                    expected=(py+1,1) if pm==12 else (py,pm+1)
                    if (cy,cm)!=expected: break
                else:
                    if cur[0]-prev[0] != meta["seconds"]*1000: break
                contiguous_tail_count+=1
        gaps=[]
        for prev,cur in zip(valid,valid[1:]):
            if iv=="1M":
                from datetime import datetime, timezone
                py,pm=datetime.fromtimestamp(prev[0]/1000,timezone.utc).year,datetime.fromtimestamp(prev[0]/1000,timezone.utc).month
                cy,cm=datetime.fromtimestamp(cur[0]/1000,timezone.utc).year,datetime.fromtimestamp(cur[0]/1000,timezone.utc).month
                expected=(py+1,1) if pm==12 else (py,pm+1)
                if (cy,cm)!=expected: gaps.append({"after":iso(prev[0]),"before":iso(cur[0])})
            elif cur[0]-prev[0] > meta["seconds"]*1000:
                gaps.append({"after":iso(prev[0]),"before":iso(cur[0]),"missing_intervals":cur[0]//(meta["seconds"]*1000)-prev[0]//(meta["seconds"]*1000)-1})
        zero_volume_count=sum(1 for row in valid if row[5]==0)
        status="UNAVAILABLE" if not valid else ("PARTIEL" if gaps or zero_volume_count else "OK")
        week_anchor_utc=None
        if iv=="1w" and valid:
            from datetime import datetime, timezone
            anchor=datetime.fromtimestamp(valid[-1][0]/1000,timezone.utc)
            week_anchor_utc=anchor.strftime("%A")
        out[iv]={"status":status,"count_received":len(rows)+duplicates_dropped,"closed_count":len(valid),
          "duplicates_dropped":duplicates_dropped,"gaps":gaps,"zero_volume_count":zero_volume_count,"contiguous_tail_count":contiguous_tail_count,
          "week_anchor_utc":week_anchor_utc,
          "last_closed_at":iso((valid[-1][0]+(meta["seconds"]*1000 if meta["seconds"] else 0))) if valid and meta["seconds"] else (iso(month_end_ms(valid[-1][0])) if valid else None),
          "rows":[{"open_time":iso(r[0]),"open":r[1],"high":r[2],"low":r[3],"close":r[4],"volume":r[5]} for r in valid[-300:]],
          "sufficient_for":{"rsi14":contiguous_tail_count>=15,"macd_12_26_9":contiguous_tail_count>=35,"sma50":contiguous_tail_count>=50,"sma200":contiguous_tail_count>=200,"atr14":contiguous_tail_count>=15}}
    return out

def observe(r):
    top=json.dumps([r["bids"][:20],r["asks"][:20]],separators=(",",":"))
    newest=next((x for x in r["trades"] if x.get("time_ms") is not None),None)
    st=r["server_time_ms"]; book_ts=r["book_time_ms"]
    # MEXC order-book responses generally have no source timestamp; never infer absolute age.
    if book_ts and st and book_ts < 10**12: book_ts=int(book_ts)*1000
    return {"observed_at":iso(r["local_mid_ms"]),"server_time":iso(st) if st else None,"clock_skew_ms":st-r["local_mid_ms"] if st else None,
      "book_sequence":r["sequence"],"book_source_time":iso(book_ts) if book_ts else None,
      "book_age_ms":st-book_ts if st and book_ts else None,"book_hash":hashlib.sha256(top.encode()).hexdigest()[:16],
      "newest_trade_ms":newest.get("time_ms") if newest else None,
      "newest_trade_age_ms":st-newest["time_ms"] if st and newest and newest.get("time_ms") else None}

def verdict(obs,max_book_age,max_trade_age):
    last=obs[-1]
    # The published order book is from the final pass; earlier timestamps cannot
    # certify it when the final pass has no usable source timestamp.
    age_ms=last["book_age_ms"]
    if age_ms is not None:
        age=age_ms/1000
        bv="VÉRIFIÉ" if 0<=age<=max_book_age else ("PÉRIMÉ" if age>max_book_age else "NON VÉRIFIÉ")
        br=f"horodatage source de la dernière passe, âge {age:.1f}s"
    elif len({o["book_hash"] for o in obs})>1 or (len([o for o in obs if o["book_sequence"] is not None])>=2 and len({str(o["book_sequence"]) for o in obs if o["book_sequence"] is not None})>1):
        bv="PARTIEL"; br="carnet changé entre les passes, mais âge absolu non démontré"
    else: bv="NON VÉRIFIÉ"; br="carnet inchangé sans horodatage exploitable dans la dernière passe"
    age=last["newest_trade_age_ms"]
    if age is None: tv="NON VÉRIFIÉ"; tr="aucune transaction horodatée exploitable"
    elif age<0: tv="NON VÉRIFIÉ"; tr="horloge source incohérente"
    elif age/1000<=max_trade_age: tv="VÉRIFIÉ"; tr=f"dernière transaction il y a {age/1000:.0f}s"
    else: tv="NON VÉRIFIÉ"; tr=f"dernière transaction il y a {age/1000:.0f}s; activité récente non prouvée"
    return {"book":{"verdict":bv,"reason":br},"trades":{"verdict":tv,"reason":tr}}

def book_anomalies(bids,asks,best):
    anomalies=[]
    if not bids or not asks:
        anomalies.append("CARNET_VIDE" if not bids and not asks else "CARNET_INCOMPLET")
    if bids and asks and bids[0][0]>=asks[0][0]:
        anomalies.append("CARNET_CROISE")
    if not isinstance(best,dict) or best.get("bid") is None or best.get("ask") is None:
        anomalies.append("L1_ABSENT")
    return anomalies

def source_report(c,notional,passes,interval,max_book_age,max_trade_age):
    runs=[]
    for i in range(passes):
        if i: time.sleep(interval)
        runs.append(fast(c))
    last=runs[-1]; st=last["server_time_ms"]
    obs=[observe(r) for r in runs]
    # Re-query candles once using source time; each interval is explicitly separated.
    cs=candles(c,st)
    s=spread(last["best"]["bid"],last["best"]["ask"]) if last["best"] and last["best"].get("bid") and last["best"].get("ask") else spread(None,None)
    asks=last["asks"]
    status=verdict(obs,max_book_age,max_trade_age)
    anomalies=book_anomalies(last["bids"],asks,last["best"])
    if anomalies:
        status["book"]={"verdict":"NON VÉRIFIÉ","reason":"anomalies du carnet: "+", ".join(anomalies)}
    return {"status":status,"server_time_utc":iso(st) if st else None,
      "mid":s["mid"],"best":last["best"],"spread":s,"book":{"bids":last["bids"][:50],"asks":last["asks"][:50],
      "bid_levels":len(last["bids"]),"ask_levels":len(asks),"depth_usdt_by_band":{f"{b}%":{"bids":sum(p*q for p,q in last["bids"] if p>=s["mid"]*(1-b/100)) if s["mid"] else None,
      "asks":sum(p*q for p,q in asks if p<=s["mid"]*(1+b/100)) if s["mid"] else None} for b in (.5,1,2,5)},
      "anomalies":anomalies},
      "buy_cost_300_usdt":buy_cost(asks,notional),"trades":last["trades"][:100] or None,
      "candles":cs,"fees":{"verified":False,"value":None,"note":"frais non vérifiés; exclus du coût simulé"},
      "observations":obs,"best_ask_source":c.venue}

def run(passes=3,interval=3,notional=300,max_book_age=10,max_trade_age=900):
    started=now_ms(); clients={v:Client(v) for v in SYMBOLS}; sources={}
    for v,c in clients.items():
        try: sources[v]=source_report(c,notional,passes,interval,max_book_age,max_trade_age)
        except Exception as e: sources[v]={"status":{"book":{"verdict":"ERREUR","reason":type(e).__name__},"trades":{"verdict":"ERREUR","reason":type(e).__name__}},"error":str(e)[:200],"mid":None,"best":None,"book":None,"trades":None,"candles":{},"fees":{"verified":False,"value":None}}
    m,k=sources["mexc"],sources["kucoin"]
    identical=bool(m.get("book") and k.get("book") and m["book"]["bids"][:5]==k["book"]["bids"][:5] and m["book"]["bids"][:5])
    mids=[m.get("mid"),k.get("mid")]
    divergence=((mids[0]-mids[1])/mids[1]*10000) if all(x is not None and x>0 for x in mids) else None
    # A fresh book on each venue is not independent confirmation if their mids
    # disagree by more than the existing 1% cross-venue tolerance.
    both=(m["status"]["book"]["verdict"]=="VÉRIFIÉ" and k["status"]["book"]["verdict"]=="VÉRIFIÉ"
          and all(x is not None and x>0 for x in mids) and not identical
          and divergence is not None and abs(divergence)<=100)
    return {"schema_version":1,"symbol":"TELUSDT","mode":"READ_ONLY_PUBLIC_DATA","generated_at":iso(now_ms()),
      "collector":{"name":"collector/tel_collector.py","read_only":True,"orders_sent":0,"github_actions":os.environ.get("GITHUB_ACTIONS")=="true",
       "passes":passes,"interval_seconds":interval,"buy_cost_notional_usdt":notional},
      "collection":{"start_utc":iso(started),"end_utc":iso(now_ms()),"start_paris":paris(started),"end_paris":paris(now_ms())},
      "sources":sources,"cross_check":{"mid_mexc":m.get("mid"),"mid_kucoin":k.get("mid"),"divergence_bps":divergence,
       "identical_top_bids_alert":identical,"both_books_usable":both,"independent_confirmation":"OUI" if both else "NON ÉTABLIE"},
      "request_log":sum((c.log for c in clients.values()),[]),
      "limits":["Les statuts PARTIEL/NON VÉRIFIÉ sont conservés tels quels.","Les frais sont inconnus et exclus.",
       "Les transactions récentes ne prouvent pas à elles seules la fraîcheur absolue du carnet.",
       "Un succès de collecte n'est pas un signal d'achat."]}

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--out",default="tel_snapshot.json"); p.add_argument("--passes",type=int,default=3)
    p.add_argument("--interval",type=float,default=3); p.add_argument("--notional",type=float,default=300)
    p.add_argument("--max-book-age-s",type=float,default=10); p.add_argument("--max-trade-age-s",type=float,default=900)
    a=p.parse_args(argv)
    if a.passes<1 or a.interval<0 or a.notional<=0: p.error("invalid positive collection parameters")
    rep=run(a.passes,a.interval,a.notional,a.max_book_age_s,a.max_trade_age_s)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)),exist_ok=True)
    with open(a.out,"w",encoding="utf-8") as f: json.dump(rep,f,ensure_ascii=False,indent=2)
    for v,s in rep["sources"].items(): print(f'{v}: book={s["status"]["book"]["verdict"]}; trades={s["status"]["trades"]["verdict"]}; mid={s.get("mid")}')
    print("confirmation indépendante:",rep["cross_check"]["independent_confirmation"])
    return 0 if any(s.get("mid") for s in rep["sources"].values()) else 2

if __name__=="__main__": raise SystemExit(main())
