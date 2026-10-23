#!/usr/bin/env python3
"""Read-only public TEL/USDT market collector. Missing fields remain null."""
import argparse, os, json, time, math, hashlib, hmac, random, uuid
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import sys

# When executed as `python collector/tel_collector.py`, Python puts only
# the collector directory on sys.path. Add the repository root so `src.*`
# imports resolve consistently in GitHub Actions and local runs.
_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.tradingview_quality import diagnose_identical_cross_venue_data, validate_order_book

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
DEFAULT_ROUND_TRIP_AMOUNTS_USDT = (50.0, 100.0, 300.0, 500.0, 1000.0)
BOOK_ENDPOINTS = {
    "mexc": "/api/v3/depth",
    "kucoin": "/api/v1/market/orderbook/level2_100",
}
FEES_PROVENANCE_ENV = "FEES_PROVENANCE_KEY"

def now_ms(): return int(time.time() * 1000)
def iso(ms):
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
def paris(ms): return datetime.fromtimestamp(ms / 1000, PARIS).isoformat(timespec="seconds")
def num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError): return None

def remaining_tolerance(target):
    """Relative tolerance for a fully consumed amount, never an absolute 1e-8."""
    target=abs(target)
    return target*1e-12 if target else 0.0

def median(values):
    ordered=sorted(values)
    if not ordered: return None
    middle=len(ordered)//2
    return ordered[middle] if len(ordered)%2 else (ordered[middle-1]+ordered[middle])/2

def percentile_rank(values,value):
    """Percentile rank of value in values (0-100), or None without a sample."""
    if value is None: return None
    sample=sorted(v for v in (num(x) for x in (values or [])) if v is not None)
    if not sample: return None
    target=float(value)
    if not math.isfinite(target): return None
    below=sum(1 for v in sample if v<target)
    equal=sum(1 for v in sample if v==target)
    return (below+0.5*equal)/len(sample)*100

def normalize_amounts(amounts):
    """Return unique positive USDT amounts. Strings may be comma-separated."""
    if amounts is None:
        raw=list(DEFAULT_ROUND_TRIP_AMOUNTS_USDT)
    elif isinstance(amounts,str):
        raw=[part for part in amounts.split(",") if part.strip()]
    elif isinstance(amounts,(int,float)):
        raw=[amounts]
    else:
        raw=list(amounts)
    result=[]
    for item in raw:
        value=num(item)
        if value is None or value<=0:
            raise ValueError("amounts must contain positive finite USDT values")
        if not any(abs(value-existing)<=1e-12 for existing in result):
            result.append(value)
    if not result:
        raise ValueError("at least one positive USDT amount is required")
    return result

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

def book_transport_reason(c):
    """Classify the last order-book request: DNS, HTTP failure, or no transport error."""
    endpoint=BOOK_ENDPOINTS.get(getattr(c,"venue",None))
    entries=[e for e in (getattr(c,"log",None) or [])
      if isinstance(e,dict) and e.get("endpoint")==endpoint]
    if not entries: return None
    last=entries[-1]
    if last.get("error")=="DNS_RESOLUTION": return "DNS_RESOLUTION"
    status=last.get("http_status")
    error=last.get("error")
    if isinstance(status,int) and status>=400: return "HTTP_ERROR"
    if isinstance(error,str) and error.startswith("HTTP_"): return "HTTP_ERROR"
    if error: return "NETWORK_ERROR"
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
    asks=sorted(asks or []); best=asks[0][0] if asks else None
    target=num(notional) or 0.0
    tolerance=remaining_tolerance(target)
    remain=target; qty=spent=0.0; worst=None; used=0
    for p,q in asks:
        take=min(remain,p*q)
        if take<=0: continue
        qty+=take/p; spent+=take; remain-=take; worst=p; used+=1
        if remain<=tolerance: break
    avg=spent/qty if qty else None
    return {"target_usdt":target,"filled_usdt":spent,"remaining_usdt":max(0.0,remain),
      "complete":remain<=tolerance and spent>0,
      "qty_tel":qty if qty else None,"avg_price":avg,"worst_price":worst,"levels_used":used,"best_price":best,
      "slippage_vs_best_ask_pct":(avg/best-1)*100 if avg and best else None,
      "fees":"EXCLUDED_NOT_VERIFIED"}

def sell_proceeds(bids,qty_tel):
    """Sell an exact TEL quantity into observed bids; never infer missing depth."""
    bids=sorted(bids or [],reverse=True); best=bids[0][0] if bids else None
    target=max(0.0,num(qty_tel) or 0.0)
    tolerance=remaining_tolerance(target)
    remain=target; sold=proceeds=0.0; worst=None; used=0
    for p,q in bids:
        take=min(remain,q)
        if take<=0: continue
        sold+=take; proceeds+=take*p; remain-=take; worst=p; used+=1
        if remain<=tolerance: break
    avg=proceeds/sold if sold else None
    return {"target_qty_tel":target,"filled_qty_tel":sold,"remaining_qty_tel":max(0.0,remain),
      "proceeds_usdt":proceeds,"complete":target>0 and remain<=tolerance,
      "avg_price":avg,"worst_price":worst,"levels_used":used,"best_price":best,
      "slippage_vs_best_bid_pct":(1-avg/best)*100 if avg and best else None,
      "fees":"EXCLUDED_NOT_VERIFIED"}

def _hex64(value):
    return isinstance(value,str) and len(value)==64 and all(c in "0123456789abcdefABCDEF" for c in value)

def _fee_provenance_metadata(provenance):
    if not isinstance(provenance,dict): return False
    return (isinstance(provenance.get("source"),str) and bool(provenance["source"].strip())
      and isinstance(provenance.get("source_url"),str) and bool(provenance["source_url"].strip())
      and isinstance(provenance.get("retrieved_at"),str) and bool(provenance["retrieved_at"].strip())
      and _hex64(provenance.get("evidence_sha256"))
      and provenance.get("algorithm")=="HMAC-SHA256"
      and isinstance(provenance.get("key_id"),str) and bool(provenance["key_id"].strip()))

def _fee_provenance_payload(fees):
    provenance=fees.get("provenance") if isinstance(fees.get("provenance"),dict) else {}
    return {"verified":True,"pct_per_side":num(fees.get("pct")),"value":fees.get("value"),
      "source":provenance.get("source"),"source_url":provenance.get("source_url"),
      "retrieved_at":provenance.get("retrieved_at"),"evidence_sha256":provenance.get("evidence_sha256"),
      "algorithm":provenance.get("algorithm"),"key_id":provenance.get("key_id")}

def _fees_key(key=None):
    return key if key is not None else os.environ.get(FEES_PROVENANCE_ENV)

def sign_fees_provenance(fees,key=None):
    """Sign a fee claim with the trusted HMAC key; the key never enters the JSON."""
    if not isinstance(fees,dict): raise ValueError("fees must be a dict")
    pct=num(fees.get("pct"))
    if pct is None or pct<0: raise ValueError("fees.pct must be finite and >= 0")
    secret=_fees_key(key)
    if not secret: raise ValueError(FEES_PROVENANCE_ENV+" is required to sign fees")
    provenance=dict(fees.get("provenance") or {})
    provenance.setdefault("algorithm","HMAC-SHA256")
    provenance.setdefault("key_id","default")
    provenance.pop("signature",None)
    payload=_fee_provenance_payload({**fees,"pct":pct,"provenance":provenance})
    signature=hmac.new(secret.encode("utf-8"),
      json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8"),
      hashlib.sha256).hexdigest()
    return {**fees,"pct":pct,"provenance":{**provenance,"signature":signature}}

def verify_fees_provenance(fees,key=None):
    """Return VERIFIED only for an HMAC-signed fee claim; fail closed otherwise."""
    if not isinstance(fees,dict) or fees.get("verified") is not True: return "NOT_DECLARED"
    secret=_fees_key(key)
    if not secret: return "KEY_UNAVAILABLE"
    provenance=fees.get("provenance")
    if not isinstance(provenance,dict): return "MISSING_PROVENANCE"
    if not _fee_provenance_metadata(provenance): return "INVALID_PROVENANCE"
    if not _hex64(provenance.get("signature")): return "MISSING_SIGNATURE"
    # A raw claim carries `pct`; a normalized claim (as stored in a snapshot)
    # carries `pct_per_side`. Both must re-verify against the same payload, and
    # two different declared percentages are never accepted.
    pct=num(fees.get("pct")); side=num(fees.get("pct_per_side"))
    if pct is None: pct=side
    elif side is not None and side!=pct: return "INVALID_PCT"
    if pct is None or pct<0: return "INVALID_PCT"
    payload=_fee_provenance_payload({**fees,"pct":pct,"provenance":provenance})
    expected=hmac.new(secret.encode("utf-8"),
      json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8"),
      hashlib.sha256).hexdigest()
    return "VERIFIED" if hmac.compare_digest(expected,provenance["signature"]) else "INVALID_SIGNATURE"

def normalize_fees(fees=None):
    """Only a caller-declared, HMAC-provenanced fee value is ever applied."""
    if isinstance(fees,dict) and fees.get("verified") is True:
        pct=num(fees.get("pct"))
        if pct is not None and pct>=0:
            status=verify_fees_provenance(fees)
            if status=="VERIFIED":
                return {"verified":True,"pct_per_side":pct,"value":fees.get("value"),
                  "note":"frais vérifiés par provenance HMAC-SHA256",
                  "provenance":fees.get("provenance"),"provenance_status":"VERIFIED"}
            return {"verified":False,"pct_per_side":None,"provided_pct":pct,"value":None,
              "note":f"frais déclarés vérifiés mais provenance non authentifiée ({status}); ignorés; coût réel >= estimation hors frais",
              "provenance":fees.get("provenance") if isinstance(fees.get("provenance"),dict) else None,
              "provenance_status":status}
        return {"verified":False,"pct_per_side":None,"provided_pct":None,"value":None,
          "note":"frais déclarés vérifiés mais pourcentage invalide; ignorés; coût réel >= estimation hors frais",
          "provenance":fees.get("provenance") if isinstance(fees.get("provenance"),dict) else None,
          "provenance_status":"INVALID_PCT"}
    provided=num(fees.get("pct")) if isinstance(fees,dict) else None
    note="frais non vérifiés; coût réel >= estimation hors frais"
    if provided is not None:
        note="frais fournis mais non vérifiés; ignorés; coût réel >= estimation hors frais"
    return {"verified":False,"pct_per_side":None,"provided_pct":provided,"value":None,"note":note,
      "provenance":None,"provenance_status":"NOT_DECLARED"}

def round_trip_scenarios(bids,asks,amounts,fees=None):
    """Static round-trip estimate for any positive USDT amounts.

    Buys consume asks, then the acquired TEL is sold into observed bids. If
    either side lacks depth, the round trip is null (no extrapolation).
    """
    amounts=normalize_amounts(amounts)
    asks=sorted(asks or []); bids=sorted(bids or [],reverse=True)
    best_bid=bids[0][0] if bids else None; best_ask=asks[0][0] if asks else None
    initial=spread(best_bid,best_ask)
    fee_info=normalize_fees(fees)
    scenarios=[]
    for amount in amounts:
        buy=buy_cost(asks,amount)
        sell=None; round_trip=None
        if not bids and not asks:
            status="CARNET_VIDE"; reason="aucun niveau acheteur ni vendeur"
        elif not asks:
            status="PROFONDEUR_ACHAT_INSUFFISANTE"; reason="aucun niveau vendeur observé"
        elif not buy["complete"]:
            status="PROFONDEUR_ACHAT_INSUFFISANTE"
            reason=f"profondeur vendeuse insuffisante: {buy['filled_usdt']:.8g}/{amount:.8g} USDT"
        else:
            sell=sell_proceeds(bids,buy["qty_tel"])
            if not sell["complete"]:
                status="PROFONDEUR_VENTE_INSUFFISANTE"
                reason=f"profondeur acheteuse insuffisante: {sell['filled_qty_tel']:.8g}/{buy['qty_tel']:.8g} TEL"
            else:
                spent=buy["filled_usdt"]; proceeds=sell["proceeds_usdt"]
                cost=spent-proceeds
                cost_pct=cost/spent*100 if spent>0 else None
                round_trip={"cost_usdt":cost,"cost_pct":cost_pct,
                  "return_pct":-cost_pct if cost_pct is not None else None,
                  "fees_verified":fee_info["verified"],"fees_pct_per_side":fee_info["pct_per_side"],
                  "fees_usdt":None,"net_cost_usdt":None,"net_cost_pct":None,"net_return_pct":None}
                if fee_info["verified"]:
                    fee_usdt=spent*fee_info["pct_per_side"]/100+proceeds*fee_info["pct_per_side"]/100
                    net_proceeds=proceeds-fee_usdt
                    round_trip.update(fees_usdt=fee_usdt,net_cost_usdt=spent-net_proceeds,
                      net_cost_pct=(spent-net_proceeds)/spent*100 if spent>0 else None,
                      net_return_pct=(net_proceeds/spent-1)*100 if spent>0 else None)
                status="COMPLET"; reason=None
        scenarios.append({"amount_usdt":amount,"initial_spread_pct":initial["pct_mid"],
          "buy":buy,"sell":sell,"round_trip":round_trip,
          "depth_sufficient":status=="COMPLET","insufficient_depth":status!="COMPLET",
          "execution_status":status,"reason":reason,"fees":fee_info})
    return {"initial_spread":initial,"scenarios":scenarios,"fees":fee_info}

def liquidity_cost_report(bids,asks,amounts,*,calculated_at_ms=None,book_source_time_ms=None,
                          max_book_age_ms=10000,book_verdict=None,anomalies=None,
                          shape_problems=None,fees=None,history=None,transport_reason=None):
    """Fail-closed diagnostic wrapper around round_trip_scenarios.

    A stale, incomplete or unverified book yields no usable scenarios. Fresh
    books still flag each amount whose depth is insufficient.
    """
    amounts=normalize_amounts(amounts)
    calculated_at_ms=now_ms() if calculated_at_ms is None else int(calculated_at_ms)
    max_book_age_ms=max(0,int(max_book_age_ms))
    age_ms=(calculated_at_ms-int(book_source_time_ms)) if book_source_time_ms is not None else None
    bids=sorted(bids or [],reverse=True); asks=sorted(asks or [])
    initial=spread(bids[0][0] if bids else None,asks[0][0] if asks else None)
    anomalies=list(anomalies or []); shape_problems=list(shape_problems or [])
    reason=None
    if transport_reason=="DNS_RESOLUTION": reason="DNS_RESOLUTION"
    elif transport_reason=="HTTP_ERROR": reason="HTTP_ERROR"
    elif transport_reason=="NETWORK_ERROR": reason="NETWORK_ERROR"
    elif not bids and not asks: reason="CARNET_VIDE"
    elif not bids or not asks: reason="CARNET_INCOMPLET"
    elif anomalies: reason="CARNET_ANOMAL"
    elif shape_problems: reason="CARNET_INVALIDE"
    elif age_ms is None: reason="AGE_DU_CARNET_INCONNU"
    elif age_ms<0: reason="HORLOGE_DU_CARNET_INCOHERENTE"
    elif age_ms>max_book_age_ms: reason="STALE_DATA"
    elif book_verdict!="VÉRIFIÉ": reason="CARNET_NON_VERIFIE"
    elif initial["pct_mid"] is None: reason="SPREAD_INVALIDE"
    usable=reason is None
    mid=initial["mid"]
    reason_details={
      "DNS_RESOLUTION":"Résolution DNS du carnet impossible; aucun niveau reçu.",
      "HTTP_ERROR":"Erreur HTTP lors de la récupération du carnet; aucun niveau exploitable.",
      "NETWORK_ERROR":"Erreur réseau non HTTP lors de la récupération du carnet; aucun niveau exploitable.",
      "CARNET_VIDE":"Aucun niveau acheteur ni vendeur reçu.",
      "STALE_DATA":"Horodatage du carnet trop ancien; données périmées.",
    }
    result={"schema_version":1,"read_only":True,"orders_sent":0,
      "calculated_at_utc":iso(calculated_at_ms),
      "transport_reason":transport_reason,
      "book":{"source_time":iso(int(book_source_time_ms)) if book_source_time_ms is not None else None,
        "source_time_ms":int(book_source_time_ms) if book_source_time_ms is not None else None,
        "age_at_calculation_ms":age_ms,
        "age_at_calculation_seconds":round(age_ms/1000,3) if age_ms is not None else None,
        "max_age_seconds":max_book_age_ms/1000,"fresh":usable,"verdict":book_verdict,
        "anomalies":anomalies,"shape_problems":shape_problems},
      "initial_spread":initial,
      "depth_usdt_by_band":{"bids_0_5pct":sum(p*q for p,q in bids if mid and p>=mid*0.995) if mid else None,
        "asks_0_5pct":sum(p*q for p,q in asks if mid and p<=mid*1.005) if mid else None,
        "bids_1pct":sum(p*q for p,q in bids if mid and p>=mid*0.99) if mid else None,
        "asks_1pct":sum(p*q for p,q in asks if mid and p<=mid*1.01) if mid else None},
      "default_amounts_usdt":list(DEFAULT_ROUND_TRIP_AMOUNTS_USDT),
      "requested_amounts_usdt":amounts,"usable":usable,"reason":reason,
      "reason_detail":None if usable else reason_details.get(reason,"Estimation non utilisable: "+str(reason)),
      "scenarios":[],"fees":normalize_fees(fees),
      "limits":["Estimation statique sur les niveaux publics observés; aucun ordre réel n'est envoyé.",
        "Aucune extrapolation au-delà de la profondeur observée; un montant trop grand est signalé.",
        "Frais exclus sauf s'ils sont couverts par une provenance HMAC vérifiée; le coût réel est supérieur ou égal.",
        "Le carnet peut changer entre la collecte et l'exécution; latence et rejets non modélisés.",
        "Spread initial et slippages sont mesurés séparément; le total est recalculé sur les flux réels.",
        "La fraîcheur est évaluée à l'heure de calcul; la publication peut être plus tardive."]}
    if usable:
        result.update(round_trip_scenarios(bids,asks,amounts,fees=fees))
        result["all_scenarios_deep_enough"]=all(s["depth_sufficient"] for s in result["scenarios"])
    else:
        result["all_scenarios_deep_enough"]=False
    ranks={}
    if isinstance(history,dict):
        spread_rank=percentile_rank(history.get("spread_pct_mid"),initial["pct_mid"])
        depth_value=result["depth_usdt_by_band"]["bids_1pct"]
        depth_rank=percentile_rank(history.get("depth_1pct_bids_usdt"),depth_value)
        if spread_rank is not None: ranks["spread_pct_mid"]={"rank_pct":spread_rank,"sample_size":len(history.get("spread_pct_mid") or [])}
        if depth_rank is not None: ranks["depth_1pct_bids_usdt"]={"rank_pct":depth_rank,"sample_size":len(history.get("depth_1pct_bids_usdt") or [])}
    result["percentiles"]=({"status":"OK","ranks":ranks} if ranks else
      {"status":"UNAVAILABLE","reason":"historique non fourni ou insuffisant; aucun percentile calculé"})
    return result

def spread_passes(runs):
    entries=[]; values=[]
    for run in runs:
        best=run.get("best") or {}
        value=spread(best.get("bid"),best.get("ask"))
        entries.append({"observed_at":iso(run["local_mid_ms"]),"best_bid":best.get("bid"),
          "best_ask":best.get("ask"),"spread_pct_mid":value["pct_mid"],"valid":value["pct_mid"] is not None})
        if value["pct_mid"] is not None: values.append(value["pct_mid"])
    return {"count":len(entries),"valid_count":len(values),"complete":len(values)==len(entries),
      "min_pct":min(values) if values else None,"median_pct":median(values) if values else None,
      "max_pct":max(values) if values else None,"passes":entries}

def annotate_liquidity_publication(sources,publication_ms,max_book_age_ms):
    for source in sources.values():
        liquidity=source.get("liquidity_cost") if isinstance(source,dict) else None
        if not isinstance(liquidity,dict): continue
        book=liquidity.get("book") if isinstance(liquidity.get("book"),dict) else {}
        source_ms=book.get("source_time_ms")
        age=publication_ms-source_ms if source_ms is not None else None
        book["age_at_publication_ms"]=age
        book["fresh_at_publication"]=age is not None and 0<=age<=max_book_age_ms
        # The scenarios were measured when the book was fresh at calculation
        # time. Publication latency is reported separately; it must not erase
        # a valid measurement, but it must be visible to fail-closed consumers.
        liquidity["publication_stale"]=not book["fresh_at_publication"]
        liquidity["usable_at_publication"]=bool(liquidity.get("usable")) and book["fresh_at_publication"]
        if not book["fresh_at_publication"]:
            if age is None:
                warning="Âge du carnet inconnu à la publication; estimation non certifiée."
            elif age<0:
                warning="Horodatage du carnet incohérent à la publication; estimation non certifiée."
            else:
                warning="Carnet périmé au moment de la publication; ne pas utiliser comme estimation courante."
            liquidity["publication_warning"]=warning
            # Preserve an earlier, more specific failure (empty/invalid book).
            if liquidity.get("usable") and not liquidity.get("reason"):
                liquidity["reason_detail"]="Mesure valide au calcul, mais non utilisable à la publication: "+warning

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
    if v=="mexc" and isinstance(best,dict):
        best["last"]=tx[0]["price"] if tx else None
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
    return {"observed_at":iso(r["local_mid_ms"]),"observed_at_ms":r["local_mid_ms"],
      "server_time":iso(st) if st else None,"clock_skew_ms":st-r["local_mid_ms"] if st else None,
      "book_sequence":r["sequence"],"book_source_time":iso(book_ts) if book_ts else None,
      "book_source_time_ms":int(book_ts) if book_ts else None,
      "book_age_ms":st-book_ts if st and book_ts else None,"book_hash":hashlib.sha256(top.encode()).hexdigest()[:16],
      "best_bid":(r.get("best") or {}).get("bid"),"best_ask":(r.get("best") or {}).get("ask"),
      "spread_pct_mid":spread((r.get("best") or {}).get("bid"),(r.get("best") or {}).get("ask"))["pct_mid"],
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

def source_report(c,notional,passes,interval,max_book_age,max_trade_age,amounts=None,fees=None):
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
    # Independent shape validation catches unsorted depth levels; it does not
    # claim freshness when the exchange does not provide a usable timestamp.
    shape_quality=validate_order_book(last["bids"],asks)
    if shape_quality["problems"]:
        status["book"]={"verdict":"NON VÉRIFIÉ","reason":"contrôle qualité du carnet: "+", ".join(shape_quality["problems"])}
    liquidity=liquidity_cost_report(last["bids"],asks,amounts,calculated_at_ms=now_ms(),
      book_source_time_ms=obs[-1].get("book_source_time_ms"),max_book_age_ms=max_book_age*1000,
      book_verdict=status["book"]["verdict"],anomalies=anomalies,
      shape_problems=shape_quality["problems"],fees=fees,
      transport_reason=book_transport_reason(c))
    return {"status":status,"quality_diagnostics":{"order_book_shape":shape_quality},"server_time_utc":iso(st) if st else None,
      "mid":s["mid"],"best":last["best"],"spread":s,"spread_passes":spread_passes(runs),
      "book":{"bids":last["bids"][:50],"asks":last["asks"][:50],
      "bid_levels":len(last["bids"]),"ask_levels":len(asks),"depth_usdt_by_band":{f"{b}%":{"bids":sum(p*q for p,q in last["bids"] if p>=s["mid"]*(1-b/100)) if s["mid"] else None,
      "asks":sum(p*q for p,q in asks if p<=s["mid"]*(1+b/100)) if s["mid"] else None} for b in (.5,1,2,5)},
      "anomalies":anomalies},
      "buy_cost_300_usdt":buy_cost(asks,notional),"liquidity_cost":liquidity,
      "trades":last["trades"][:100] or None,
      "candles":cs,"fees":{"verified":False,"value":None,"note":"frais non vérifiés; exclus du coût simulé"},
      "observations":obs,"best_ask_source":c.venue}

def compute_snapshot_fingerprint(sources, cross_check):
    """
    Compute a deterministic SHA-256 fingerprint for the validated snapshot payload.

    Deterministic serialization used here: JSON with sort_keys=True and ensure_ascii=False,
    then SHA-256 over the UTF-8 bytes. This covers the stable source data and the
    derived cross-check summary used for provenance validation, while excluding volatile
    fields such as generated_at, collection timing and request_log metadata.

    Any missing, null or malformed source block is rejected explicitly instead of
    generating a misleading fingerprint over incomplete data.
    """
    if not isinstance(sources, dict):
        raise ValueError("sources must be a dict")
    if not isinstance(cross_check, dict):
        raise ValueError("cross_check must be a dict")

    def _finite_positive(value, label):
        number = num(value)
        if number is None or not math.isfinite(number) or number <= 0:
            raise ValueError(f"{label} missing or invalid")
        return float(number)

    normalized = {}
    for venue in ("mexc", "kucoin"):
        src = sources.get(venue)
        if src is None or not isinstance(src, dict):
            raise ValueError(f"sources.{venue} missing or malformed")
        mid = _finite_positive(src.get("mid"), f"sources.{venue}.mid")
        best = src.get("best")
        if not isinstance(best, dict):
            raise ValueError(f"sources.{venue}.best missing or malformed")
        bid = _finite_positive(best.get("bid"), f"sources.{venue}.best.bid")
        ask = _finite_positive(best.get("ask"), f"sources.{venue}.best.ask")
        if ask < bid:
            raise ValueError(f"sources.{venue}.best.ask below bid")
        book = src.get("book")
        if not isinstance(book, dict):
            raise ValueError(f"sources.{venue}.book missing or malformed")
        bids = book.get("bids")
        asks = book.get("asks")
        if not isinstance(bids, list) or not isinstance(asks, list):
            raise ValueError(f"sources.{venue}.book bids/asks must be lists")
        if not bids or not asks:
            raise ValueError(f"sources.{venue}.book bids/asks cannot be empty")
        normalized[venue] = {
            "mid": mid,
            "best": {"bid": bid, "ask": ask},
            "book_bids_top5": [[_finite_positive(level[0], f"sources.{venue}.book.bids[{i}][0]"), _finite_positive(level[1], f"sources.{venue}.book.bids[{i}][1]")] for i, level in enumerate(bids[:5])],
            "book_asks_top5": [[_finite_positive(level[0], f"sources.{venue}.book.asks[{i}][0]"), _finite_positive(level[1], f"sources.{venue}.book.asks[{i}][1]")] for i, level in enumerate(asks[:5])],
        }

    required_fields = ("mid_mexc", "mid_kucoin", "divergence_bps")
    for field in required_fields:
        if field not in cross_check or cross_check.get(field) is None:
            raise ValueError(f"cross_check.{field} missing or null")
        if field in ("mid_mexc", "mid_kucoin") and not math.isfinite(float(cross_check.get(field))):
            raise ValueError(f"cross_check.{field} invalid")
        if field == "divergence_bps" and not math.isfinite(float(cross_check.get(field))):
            raise ValueError(f"cross_check.{field} invalid")

    fingerprint_data = {
        "sources": normalized,
        "cross_check": {
            "mid_mexc": float(cross_check.get("mid_mexc")),
            "mid_kucoin": float(cross_check.get("mid_kucoin")),
            "divergence_bps": float(cross_check.get("divergence_bps")),
        },
    }
    fingerprint_json = json.dumps(fingerprint_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(fingerprint_json.encode("utf-8")).hexdigest()

def run(passes=3,interval=3,notional=300,max_book_age=10,max_trade_age=900,collection_id=None,amounts=None):
    amounts=normalize_amounts(amounts)
    started=now_ms(); clients={v:Client(v) for v in SYMBOLS}; sources={}
    for v,c in clients.items():
        try: sources[v]=source_report(c,notional,passes,interval,max_book_age,max_trade_age,amounts=amounts)
        except Exception as e: sources[v]={"status":{"book":{"verdict":"ERREUR","reason":type(e).__name__},"trades":{"verdict":"ERREUR","reason":type(e).__name__}},"error":str(e)[:200],"mid":None,"best":None,"book":None,"trades":None,"candles":{},"fees":{"verified":False,"value":None},
          "liquidity_cost":{"schema_version":1,"read_only":True,"orders_sent":0,"usable":False,"reason":"ERREUR_COLLECTE","scenarios":[],"requested_amounts_usdt":amounts}}
    m,k=sources["mexc"],sources["kucoin"]
    identical=bool(m.get("book") and k.get("book") and m["book"]["bids"][:5]==k["book"]["bids"][:5] and m["book"]["bids"][:5])
    mids=[m.get("mid"),k.get("mid")]
    venue_data_diagnostic=diagnose_identical_cross_venue_data(
      "MEXC:TELUSDT",
      {"mid":m.get("mid"),"bid":(m.get("best") or {}).get("bid"),"ask":(m.get("best") or {}).get("ask")},
      "KUCOIN:TEL-USDT",
      {"mid":k.get("mid"),"bid":(k.get("best") or {}).get("bid"),"ask":(k.get("best") or {}).get("ask")},
      ["mid","bid","ask"],
    )
    divergence=((mids[0]-mids[1])/mids[1]*10000) if all(x is not None and x>0 for x in mids) else None
    last_mexc=(m.get("best") or {}).get("last"); last_kucoin=(k.get("best") or {}).get("last")
    last_divergence=(abs(last_mexc-last_kucoin)/((last_mexc+last_kucoin)/2)*100
      if all(x is not None and x>0 for x in (last_mexc,last_kucoin)) else None)
    # A fresh book on each venue is not independent confirmation if their mids
    # disagree by more than the existing 1% cross-venue tolerance.
    both=(m["status"]["book"]["verdict"]=="VÉRIFIÉ" and k["status"]["book"]["verdict"]=="VÉRIFIÉ"
          and all(x is not None and x>0 for x in mids) and not identical
          and divergence is not None and abs(divergence)<=100)
    
    # Generate collection_id if not provided (for local runs)
    if collection_id is None:
        collection_id = str(uuid.uuid4())
    
    generated_ms=now_ms()
    annotate_liquidity_publication(sources,generated_ms,max_book_age*1000)
    # Compute snapshot fingerprint only for complete source data. Otherwise fail closed.
    cross_check_temp = {"mid_mexc":m.get("mid"),"mid_kucoin":k.get("mid"),"divergence_bps":divergence,
       "divergence_basis":"mid","divergence_mid_pct":divergence/100 if divergence is not None else None,
       "last_mexc":last_mexc,"last_kucoin":last_kucoin,"last_price_divergence_pct":last_divergence,
       "definitions":{"divergence_bps":"écart signé entre les mid(s) (MEXC - KuCoin), en points de base",
         "divergence_mid_pct":"écart signé entre les mid(s), en pourcentage",
         "last_price_divergence_pct":"écart absolu entre les derniers prix observés, en pourcentage"},
       "identical_top_bids_alert":identical,"venue_data_diagnostic":venue_data_diagnostic,"both_books_usable":both,"independent_confirmation":"OUI" if both else "NON ÉTABLIE"}
    try:
        snapshot_fingerprint = compute_snapshot_fingerprint(sources, cross_check_temp)
    except ValueError as exc:
        snapshot_fingerprint = None
        cross_check_temp["provenance_error"] = str(exc)

    publication_ages={v:(s.get("liquidity_cost",{}).get("book",{}).get("age_at_publication_ms") if isinstance(s.get("liquidity_cost"),dict) else None) for v,s in sources.items()}
    snapshot = {"schema_version":1,"symbol":"TELUSDT","mode":"READ_ONLY_PUBLIC_DATA","generated_at":iso(generated_ms),
      "collection_id": collection_id,
      # Marqueur de fiabilite de la collecte, exigé par la porte de publication
      # (src/publication_gate.py) : VALID uniquement lorsque l'empreinte
      # deterministe des sources a pu etre calculee, c'est-a-dire lorsque les
      # donnees des deux places sont presentes et coherentes. Sinon l'instantane
      # est marque FALLBACK et ne peut pas etre publie.
      "collection_status": "VALID" if snapshot_fingerprint is not None else "FALLBACK",
      "collector":{"name":"collector/tel_collector.py","read_only":True,"orders_sent":0,"github_actions":os.environ.get("GITHUB_ACTIONS")=="true",
       "passes":passes,"interval_seconds":interval,"buy_cost_notional_usdt":notional,
       "round_trip_amounts_usdt":amounts,"round_trip_default_amounts_usdt":list(DEFAULT_ROUND_TRIP_AMOUNTS_USDT)},
      "collection":{"start_utc":iso(started),"end_utc":iso(now_ms()),"start_paris":paris(started),"end_paris":paris(now_ms()),
       "book_age_at_publication_ms":publication_ages},
      "sources":sources,"cross_check":cross_check_temp,
      "request_log":sum((c.log for c in clients.values()),[]),
      "limits":["Les statuts PARTIEL/NON VÉRIFIÉ sont conservés tels quels.","Les frais sont inconnus et exclus sauf provenance HMAC vérifiée.",
       "Les transactions récentes ne prouvent pas à elles seules la fraîcheur absolue du carnet.",
       "Les scénarios de coût aller-retour sont statiques, hors frais non vérifiés, et ne sont pas des ordres.",
       "Un succès de collecte n'est pas un signal d'achat."]}
    if snapshot_fingerprint is not None:
        snapshot["snapshot_id"] = snapshot_fingerprint
    return snapshot

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--out",default="tel_snapshot.json"); p.add_argument("--passes",type=int,default=3)
    p.add_argument("--interval",type=float,default=3); p.add_argument("--notional",type=float,default=300,
      help="montant du champ historique buy_cost_300_usdt")
    p.add_argument("--amounts",default=None,
      help="scénarios de coût A/R en USDT, séparés par des virgules (défaut: 50,100,300,500,1000)")
    p.add_argument("--max-book-age-s",type=float,default=10); p.add_argument("--max-trade-age-s",type=float,default=900)
    p.add_argument("--collection-id",default=None,help="Collection ID for provenance tracking (UUID)")
    a=p.parse_args(argv)
    if a.passes<1 or a.interval<0 or a.notional<=0: p.error("invalid positive collection parameters")
    try: amounts=normalize_amounts(a.amounts)
    except ValueError as exc: p.error(str(exc))
    rep=run(a.passes,a.interval,a.notional,a.max_book_age_s,a.max_trade_age_s,a.collection_id,amounts)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)),exist_ok=True)
    with open(a.out,"w",encoding="utf-8") as f: json.dump(rep,f,ensure_ascii=False,indent=2)
    for v,s in rep["sources"].items(): print(f'{v}: book={s["status"]["book"]["verdict"]}; trades={s["status"]["trades"]["verdict"]}; mid={s.get("mid")}')
    print("confirmation indépendante:",rep["cross_check"]["independent_confirmation"])
    print("collection_id:",rep.get("collection_id"))
    print("snapshot_id:",rep.get("snapshot_id"))
    return 0 if any(s.get("mid") for s in rep["sources"].values()) else 2

if __name__=="__main__": raise SystemExit(main())
