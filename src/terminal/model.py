"""Deterministic terminal analytics. Existing strategies remain unchanged.

CCI/stochastic/DMI/MACD reuse src.agent_analysis. Terminal RSI uses Wilder;
legacy research keeps its original arithmetic RSI and is not recomputed.
EMA and ATR reuse the frozen strategy engine. Indicators restart at every gap.
"""
from __future__ import annotations
import datetime as dt
import math
from collections import Counter
from decimal import Decimal, InvalidOperation
from src import agent_analysis as A
from scripts.strategy_backtest import engine as E

STEPS = {'15m':900,'1h':3600,'4h':14400,'1D':86400}
MARKETS = {'KRAKEN:TELUSD','KRAKEN:XBTUSD','KRAKEN:ETHUSD'}
UTC = dt.timezone.utc

def finite(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)

def iso(t):
    return dt.datetime.fromtimestamp(t,UTC).isoformat()

def validate_dataset(dataset, as_of):
    if dataset.get('symbol') not in MARKETS or not dataset.get('success'):
        raise ValueError('Unsupported market or failed source')
    step=STEPS[dataset['interval']]
    raw=dataset.get('bars',[])
    if isinstance(raw,dict):
        if set(raw) != set('tohlcv') or len({len(raw[k]) for k in raw}) != 1:
            raise ValueError('Inconsistent OHLCV columns')
        raw=[dict(zip(raw,values)) for values in zip(*raw.values())]
    if not isinstance(raw,list) or not finite(as_of):
        raise ValueError('Invalid bars or clock')
    records=[]; previous=None; bytime={}
    for i,row in enumerate(raw):
        if not isinstance(row,dict):
            raise ValueError('Each bar must be an object')
        reasons=[]
        valid_time=finite(row.get('t')) and row['t']>=0
        if not valid_time or row['t']%step: reasons.append('invalid_timestamp')
        if valid_time and row['t']+step>as_of: reasons.append('unclosed')
        if not all(finite(row.get(k)) for k in 'ohlcv'):
            reasons.append('nonfinite')
        elif min(row[k] for k in 'ohlc')<=0 or row['v']<0:
            reasons.append('nonpositive_price_or_negative_volume')
        elif not row['l']<=min(row['o'],row['c'])<=max(row['o'],row['c'])<=row['h']:
            reasons.append('inconsistent_ohlc')
        elif row['h']/max(row['o'],row['c'])>3 or min(row['o'],row['c'])/row['l']>3:
            reasons.append('price_wick')
        record={'index':i,'row':dict(row),'reasons':reasons}
        records.append(record)
        if valid_time:
            bytime.setdefault(row['t'],[]).append(record)
            if previous is not None and row['t']<previous['row']['t']:
                previous['reasons'].append('out_of_order');reasons.append('out_of_order')
            if previous and finite(row.get('c')) and finite(previous['row'].get('c')):
                pc=previous['row']['c']
                if row['t']-previous['row']['t']==step and min(pc,row['c'])>0 and max(pc/row['c'],row['c']/pc)>3:
                    reasons.append('price_jump')
            previous=record
    for copies in bytime.values():
        if len(copies)>1:
            for r in copies:r['reasons'].append('duplicate')
    # Quarantine every participant in an inversion, including non-adjacent ones.
    # Prefix maxima + suffix minima keep this linear in the number of bars.
    valid_times=[r['row']['t'] for r in records if finite(r['row'].get('t'))]
    suffix=[];minimum=math.inf
    for t in reversed(valid_times):
        suffix.append(minimum);minimum=min(minimum,t)
    suffix.reverse();maximum=-math.inf;time_index=0
    for r in records:
        t=r['row'].get('t')
        if not finite(t):continue
        if t<maximum or t>suffix[time_index]:
            if 'out_of_order' not in r['reasons']:r['reasons'].append('out_of_order')
        maximum=max(maximum,t);time_index+=1
    rows=[r['row'] for r in records if not r['reasons']]
    segments=[];gaps=[]
    for row in rows:
        if not segments or row['t']-segments[-1][-1]['t']!=step:
            if segments:
                prev=segments[-1][-1]['t']
                gaps.append({'after':prev,'before':row['t'],'missing':max(0,int((row['t']-prev)/step)-1)})
            segments.append([])
        segments[-1].append(row)
    excluded=[r for r in records if r['reasons']]
    last=rows[-1]['t']+step if rows else None
    last_raw=max((t+step for t in bytime if t+step<=as_of),default=None)
    missing=sum(g['missing'] for g in gaps)
    return {'bars':rows,'segments':segments,'excluded':excluded,'quality':{
        'source_rows':len(raw),'valid_bars':len(rows),'excluded_rows':len(excluded),
        'reasons':dict(Counter(reason for r in excluded for reason in set(r['reasons']))),
        'segments':len(segments),'last_segment_bars':len(segments[-1]) if segments else 0,
        'missing_bars':missing,'gaps':gaps,'last_close':last,
        'invalid_tail':(last_raw is not None and last!=last_raw) or any('invalid_timestamp' in r['reasons'] for r in records),
        'coverage_pct':100*len(rows)/(len(rows)+missing) if rows else 0}}

def _get(series,i):
    return series[i] if len(series)>i and finite(series[i]) else None

def rsi_wilder_series(values, period=14):
    """Wilder RSI with a simple-average seed; restart after invalid prices."""
    if not isinstance(period, int) or isinstance(period, bool) or period < 1:
        raise ValueError('period must be a positive integer')
    result=[float('nan')]*len(values)
    previous=None;gain=loss=0.0;count=0
    for i,price in enumerate(values):
        if not finite(price):
            previous=None;gain=loss=0.0;count=0
            continue
        if previous is None:
            previous=price
            continue
        change=price-previous;previous=price
        up=max(change,0.0);down=max(-change,0.0)
        if count<period:
            gain+=up;loss+=down;count+=1
            if count<period:continue
            gain/=period;loss/=period
        else:
            gain=(gain*(period-1)+up)/period
            loss=(loss*(period-1)+down)/period
        result[i]=100*gain/(gain+loss) if gain+loss else 50.0
    return result

def analyze(dataset, as_of):
    v=validate_dataset(dataset,as_of);step=STEPS[dataset['interval']]
    out=[]
    for rows in v['segments']:
        c=[r['c'] for r in rows];h=[r['h'] for r in rows];l=[r['l'] for r in rows]
        e20=E.ema(c,20);e50=E.ema(c,50)
        bars=[E.Bar(dt.datetime.fromtimestamp(r['t'],UTC),r['o'],r['h'],r['l'],r['c'],r['v']) for r in rows]
        atr=E.atr_wilder(bars);rsi=rsi_wilder_series(c);macd=A.macd_histogram(c)
        cci=A.cci_series(h,l,c);sk,sd=A.stochastic_series(h,l,c);dp,dm,adx=A.dmi_series(h,l,c)
        sma= A.sma_series(c,200)
        pv=vol=0;day=None;session_complete=False
        for i,r in enumerate(rows):
            thisday=r['t']//86400
            if day!=thisday:
                pv=vol=0;day=thisday;session_complete=r['t']%86400==0
            pv+=(r['h']+r['l']+r['c'])/3*r['v'];vol+=r['v']
            prior=rows[max(0,i-20):i]
            base=sum(x['v'] for x in prior)/len(prior) if prior else 0
            p={'t':r['t'],'ema20':_get(e20,i),'ema50':_get(e50,i),'sma200':_get(sma,i),
               'rsi14':_get(rsi,i),'macd_hist':_get(macd,i),'atr14':_get(atr,i),
               'cci20':_get(cci,i),'stoch_k':_get(sk,i),'stoch_d':_get(sd,i),
               'di_plus':_get(dp,i),'di_minus':_get(dm,i),'adx14':_get(adx,i),
               'vwap_session':pv/vol if vol and session_complete else None,
               'volume_ratio':r['v']/base if base and len(prior)==20 else None,
               'support20':min(x['l'] for x in prior) if len(prior)==20 else None,
               'resistance20':max(x['h'] for x in prior) if len(prior)==20 else None,
               'close':r['c'],'volume':r['v'],
               'rsi_divergence':A.has_rsi_divergence(rsi[:i+1],c[:i+1]) if i>=24 else False,
               'rsi_delta':rsi[i]-rsi[i-1] if i and finite(rsi[i]) and finite(rsi[i-1]) else None,
               'macd_improving':i>0 and _get(macd,i) is not None and _get(macd,i-1) is not None and macd[i]>macd[i-1]}
            p['trend']='INDETERMINE' if p['ema50'] is None else ('HAUSSIER' if r['c']>e20[i]>e50[i] else 'BAISSIER' if r['c']<e20[i]<e50[i] else 'MIXTE')
            out.append(p)
    latest=out[-1] if out else {}
    quality=v['quality'];last=quality['last_close']
    quality['fresh']=last is not None and 0<=as_of-last<=step+300 and not quality['invalid_tail']
    return {'symbol':dataset['symbol'],'interval':dataset['interval'],'as_of':as_of,
            'indicator_methods':{'rsi14':'wilder_rma_14_sma_seed'},
            'quality':quality,'bars':v['bars'],'series':out,'latest':latest,
            'excluded':v['excluded'],'ready':quality['last_segment_bars']>=50 and quality['fresh']}

def _to_decimal(value):
    # Inputs must be numeric scalars. Numeric strings and bool are rejected.
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return result if result.is_finite() else None


def _finite_decimal(value):
    return value is not None and value.is_finite()


def _to_float(value):
    # The public output is JSON-compatible: reject infinities and underflow,
    # even if the intermediate Decimal arithmetic was finite.
    if value is None:
        return None
    try:
        result = float(value)
    except (OverflowError, ValueError, TypeError):
        return None
    return result if math.isfinite(result) and (result != 0 or value == 0) else None


def risk_plan(capital,entry,stop,target,fee=.004,slip=.003):
    capital,entry,stop,target,fee,slip=(_to_decimal(v) for v in (capital,entry,stop,target,fee,slip))
    invalid={'admissible':False,'reason':'Prix, capital ou coûts invalides'}
    unrepresentable={'admissible':False,'reason':'Valeurs hors précision numérique'}
    if any(v is None for v in (capital,entry,stop,target,fee,slip)):
        return invalid
    if min(capital,entry,stop,target)<=0 or not 0<=fee<Decimal('0.1') or not 0<=slip<Decimal('0.1') or not stop<entry<target:
        return invalid
    try:
        gross=(target-entry)/(entry-stop)
        buy=entry*(1+slip);sellstop=stop*(1-slip);selltgt=target*(1-slip)
        loss=buy-sellstop+fee*(buy+sellstop)
        if not all(_finite_decimal(x) for x in (gross,buy,sellstop,selltgt,loss)) or loss<=0:
            return unrepresentable
        qty=min(Decimal('0.0025')*capital/loss,capital/(buy*(1+fee)))
        reward=selltgt-buy-fee*(buy+selltgt)
        if not all(_finite_decimal(x) for x in (qty,reward,qty*buy*(1+fee),qty*loss,qty*reward,reward/loss)) or qty<=0:
            return unrepresentable
        amounts={'quantity':_to_float(qty),'cash_required':_to_float(qty*buy*(1+fee)),
                 'planned_risk_usd':_to_float(qty*loss),
                 'risk_budget_usd':_to_float(capital*Decimal('0.0025')),
                 'rr_gross':_to_float(gross),'rr_net':_to_float(reward/loss),
                 'potential_net_usd':_to_float(qty*reward),
                 'fee_per_side':_to_float(fee),'slippage_per_side':_to_float(slip)}
        if any(v is None for v in amounts.values()):
            return unrepresentable
    except (ArithmeticError, OverflowError):
        return unrepresentable
    return {'admissible':bool(gross>=Decimal('1.51') and reward/loss>=Decimal('1.5')),
            'reason':'Simulation uniquement ; RR brut ≥ 1,51 et net ≥ 1,5',
            **amounts,
            'gap_risk':'Un gap sous le stop peut dépasser le risque planifié.'}

def decision(frames, as_of):
    result={'status':'DONNÉES INSUFFISANTES','experimental':True,'execution_allowed':False,
            'proofs':[],'contradictions':[],'limits':['Hypothèse de lecture non validée statistiquement.',
            'Liquidité et frais réels non vérifiés. Aucun ordre autorisé.'],
            'invalidation':None,'plan':None,'strategy_id':'terminal-confluence-v1'}
    for tf in ('4h','1h'):
        f=frames.get(tf,{})
        q=f.get('quality',{});last=q.get('last_close');step=STEPS[tf]
        if not f.get('ready') or last is None or not 0<=as_of-last<=step+300:
            result['contradictions'].append(f'{tf} : historique continu insuffisant ou périmé')
    if result['contradictions']:return result
    a=frames['4h']['latest'];b=frames['1h']['latest'];result['status']='ATTENDRE'
    support=a.get('support20');resistance=a.get('resistance20')
    result['invalidation']=support
    if support and a['close']<support:
        result['status']='INVALIDATION';result['proofs'].append('Clôture 4h sous le plus bas des 20 bougies précédentes.');return result
    trend=a['trend']=='HAUSSIER';momentum=a.get('macd_improving') and (a.get('rsi_delta') or 0)>0
    volume=(a.get('volume_ratio') or 0)>=1.5
    recovery=a.get('rsi_divergence') and momentum
    confirm=trend and momentum and b['trend']=='HAUSSIER'
    for yes,pos,neg in [(trend,'Structure : clôture > EMA20 > EMA50 en 4h.','Tendance 4h non alignée à la hausse.'),
        (momentum,'Momentum : RSI et histogramme MACD progressent.','Momentum non convergent.'),
        (volume,'Volume : au moins 1,5 × les 20 barres précédentes.','Pas d’expansion du volume ≥ 1,5 ×.'),
        (b['trend']=='HAUSSIER','Confirmation temporelle : tendance 1h haussière.','Tendance 1h contradictoire ou mixte.')]:
        result['proofs' if yes else 'contradictions'].append(pos if yes else neg)
    stop=support-.5*a['atr14'] if support and a.get('atr14') else None
    if stop and resistance:
        plan=risk_plan(1000,a['close'],stop,resistance)
        result['plan']={'entry':a['close'],'stop':stop,'target':resistance,**plan}
    if result['plan'] and result['plan']['admissible'] and volume:
        if confirm:result['status']='ACHAT CONFIRMÉ'
        elif recovery and b['trend']!='BAISSIER':result['status']='ACHAT PRÉCOCE'
    if not result['plan'] or not result['plan']['admissible']:
        result['contradictions'].append('Plan indicatif non admissible : niveaux ou RR brut ≥ 1,51 ou net ≥ 1,5 manquants.')
    if result['status'] in ('ACHAT PRÉCOCE','ACHAT CONFIRMÉ'):
        result['technical_signal']=result['status']
        result['status']='ATTENDRE'
        result['contradictions'].append('Frais Kraken personnels et slippage réels non vérifiés : signal non exploitable.')
    return result

def correlation(a,b,step=14400,window=90):
    ar={x['t']:x['c'] for x in a};br={x['t']:x['c'] for x in b}
    keys=sorted(t for t in ar if t in br and t-step in ar and t-step in br)[-window:]
    if len(keys)<30:return {'n':len(keys),'pearson':None}
    x=[math.log(ar[t]/ar[t-step]) for t in keys];y=[math.log(br[t]/br[t-step]) for t in keys]
    mx=sum(x)/len(x);my=sum(y)/len(y)
    den=math.sqrt(sum((v-mx)**2 for v in x)*sum((v-my)**2 for v in y))
    return {'n':len(keys),'pearson':sum((u-mx)*(v-my) for u,v in zip(x,y))/den if den else None,
            'last_t':keys[-1],'method':'Pearson, log-returns aligned on closed consecutive 4h bars'}
