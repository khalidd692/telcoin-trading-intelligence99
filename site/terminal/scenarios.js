/* Read-only proposals. No broker, account, execution, or paper-trading API. */
(function(root){
'use strict';
const T=typeof module==='object'?require('./core.js'):root.TEL99;
function generate(data,o={}){
 const now=o.now??Date.now()/1000,f=data.frames?.['4h'],l=f?.latest||{},day=data.frames?.['1D']?.latest||{},h=data.frames?.['1h']?.latest||{},m=data.frames?.['15m']?.latest||{};
 const bad=[];
 if(!T.finite(data.as_of)||now<data.as_of||now-data.as_of>900)bad.push('Snapshot périmé ou incohérent');
 for(const [tf,step] of Object.entries(T.steps)){const v=data.frames?.[tf],t=v?.quality?.last_close;if(!v?.ready||!T.finite(t)||now<t||now-t>step+300)bad.push(tf+' indisponible ou périmé');}
 const quoteOk=T.freshQuote(o.quote,now);if(!quoteOk)bad.push('Cotation Kraken indisponible ou périmée');
 const spread=quoteOk&&T.finite(o.quote.bid)&&T.finite(o.quote.ask)&&o.quote.bid>0&&o.quote.ask>=o.quote.bid?(o.quote.ask-o.quote.bid)/o.quote.ask:null;
 if(spread===null||spread>.01)bad.push('Spread absent ou supérieur à 1 %');
 const feesOk=o.feesVerified===true&&T.finite(o.feesVerifiedAt)&&now>=o.feesVerifiedAt&&now-o.feesVerifiedAt<86400;
 const common=[];if(!feesOk)common.push('Frais personnels non vérifiés : hypothèse uniquement');
 if(!o.liquidityVerified)common.push('Profondeur du carnet non vérifiée pour cette taille');
 if(o.tv?.contradictory)common.push('TradingView contradictoire : contrôle humain requis');
 if(!o.tv||!T.finite(o.tv.observedAt)||now-o.tv.observedAt>900||now<o.tv.observedAt)common.push('Vérification TradingView datée indisponible');
 if(day.trend==='BAISSIER')common.push('Tendance journalière baissière');
 const bars=f?.bars||[],last=bars.at(-1),prior=bars.at(-2),atr=l.atr14;
 const near=level=>last&&prior&&prior.c>level&&last.l<=level+atr*.25&&last.c>level;
 const supportHeld=last&&last.l<=l.support20+atr*.25&&last.c>l.support20&&h.close>h.ema20&&m.close>m.ema20&&m.volume_ratio>0;
 const oldResistance=bars.length>22?Math.max(...bars.slice(-22,-2).map(b=>b.h)):l.resistance20;
 // A breakout target must be a higher observed resistance, never invented to force RR.
 const defs=[
  {id:'support',name:'Défense du support',entry:l.support20,stop:l.support20-.5*atr,target:l.ema20,confirmed:supportHeld,condition:'Défense du support sur bougie 4h clôturée, puis 1h et 15m au-dessus de leur EMA20, volume 15m non nul.'},
  {id:'reversal',name:'Retournement confirmé',entry:l.ema20,stop:l.ema20-atr,target:l.resistance20,confirmed:near(l.ema20)&&l.rsi14>50&&l.macd_improving&&h.close>h.ema20,condition:'Clôture 4h au-dessus de l’EMA20, puis retest tenu sur la clôture suivante ; RSI4h > 50, MACD en amélioration, 1h > EMA20.'},
  {id:'breakout',name:'Cassure puis retest',entry:oldResistance,stop:oldResistance-atr,target:day.resistance20,confirmed:near(oldResistance)&&l.volume_ratio>=1,condition:'Clôture 4h au-dessus de la résistance des 20 bougies précédant la cassure, puis retest tenu ; volume relatif ≥ 1.'},
  {id:'early',name:'Achat précoce · reprise courte',entry:m.close,stop:l.support20-.5*atr,target:l.ema20,confirmed:l.macd_improving&&l.close<l.ema20&&m.close>m.ema20&&m.volume_ratio>=1.5&&h.close>h.ema20,condition:'Sous EMA20 4h, MACD 4h en amélioration, clôtures 15m et 1h au-dessus de leurs EMA20 et volume 15m ≥ 1,5× sa référence.'}
 ];
 return defs.map(d=>{
  // Kraken TELUSD AssetPairs observed 2026-11-11: tick_size 0.000001.
  // Keep displayed and calculated proposal prices identical; recheck rules before execution.
  for(const key of ['entry','stop','target'])if(T.finite(d[key]))d[key]=Number((Math.floor(d[key]*1e6+1e-9)/1e6).toFixed(6));
  const executionSlip=o.slip+(spread??0)/2;
  const r=T.riskPlan(o.capital,d.entry,d.stop,d.target,o.fee,executionSlip),reasons=[...bad,...common];
  const invalidated=T.finite(d.entry)&&T.finite(l.close)&&(d.id==='support'?l.close<d.entry:d.confirmed&&l.close<d.stop);
  if(invalidated)reasons.push('Support ou seuil d’invalidation cassé sur clôture 4h');
  if(!r.admissible)reasons.push(r.error||'RR net inférieur à 1,5');
  if(quoteOk&&d.entry>o.quote.ask)reasons.push('Entrée au-dessus du marché : attendre la confirmation, limite immédiatement négociable aujourd’hui');
  if(!d.confirmed)reasons.push('Confirmation non observée');
  const budgetOk=T.finite(o.budgetUsd)&&o.budgetUsd>0;
  if(!budgetOk)reasons.push('Budget EUR/USD indisponible');
  const ratio=budgetOk&&T.finite(r.cash)?Math.min(1,o.budgetUsd/r.cash):0;
  const qty=!bad.length&&quoteOk&&budgetOk&&T.finite(r.qty)?Math.floor(r.qty*ratio*1e6)/1e6:null;
  const scale=qty!==null&&r.qty>0?qty/r.qty:0;
  const status=bad.length||invalidated||!r.admissible?'REJETÉ':!d.confirmed?'CONDITIONNEL':reasons.length?'CONDITIONNEL':'PRÊT À ÉVALUER';
  return {...d,...r,qty,cash:qty===null?null:r.cash*scale,risk:qty===null?null:r.risk*scale,status,reasons,invalidated,calculatedAt:data.as_of,expiresAt:Math.min(data.as_of+900,(o.quote?.received||0)+120),fee:o.fee,slip:o.slip,executionSlip,spread,feeEstimate:qty===null?null:qty*d.entry*(1+executionSlip)*o.fee,invalidation:'Clôture 4h sous '+(T.finite(d.stop)?d.stop.toFixed(6):'niveau indisponible')+' USD ; stop non garanti en cas de gap.',hypothetical:!feesOk};
 });
}
function allocate(plans,capital,budgetUsd){
 if(![capital,budgetUsd].every(T.finite)||capital<=0||budgetUsd<=0)return {valid:false,items:[],risk:null,cash:null};
 const eligible=plans.filter(p=>p.admissible&&!p.invalidated&&T.finite(p.qty)&&p.qty>0);
 const loss=eligible.reduce((s,p)=>s+p.risk,0),cash=eligible.reduce((s,p)=>s+p.cash,0);
 const scale=Math.min(1,loss?capital*.0025/loss:1,cash?budgetUsd/cash:1);
 const items=eligible.map(p=>{const qty=Math.floor(p.qty*scale*1e6)/1e6,k=qty/p.qty;return {id:p.id,qty,risk:p.risk*k,cash:p.cash*k};});
 return {valid:true,items,risk:items.reduce((s,p)=>s+p.risk,0),cash:items.reduce((s,p)=>s+p.cash,0)};
}
function copyText(p,now=Date.now()/1000){
 if(p.status!=='PRÊT À ÉVALUER'||p.hypothetical||now>p.expiresAt||now<p.calculatedAt||!p.admissible||!T.finite(p.qty)||p.qty<=0)throw Error('Scénario non vérifié ou périmé : copie bloquée.');
 return `TEL99 — PROPOSITION À VÉRIFIER HUMAINEMENT — AUCUN ORDRE\nKRAKEN:TELUSD spot long, sans levier\n${p.name}\nEntrée limite ${p.entry} USD; stop ${p.stop}; objectif ${p.target}\n${p.condition}\nQuantité indicative ${p.qty} TEL; RR net ${p.rrNet}; risque planifié ${p.risk} USD\nCalcul ${new Date(p.calculatedAt*1000).toISOString()}\n${p.invalidation}\nUn ordre limite passif ne protège pas d’une chute. Réserve de 2 000 000 TEL exclue. Ne pas cumuler ces tailles individuelles.`;
}
const api={generate,allocate,copyText};if(typeof module==='object')module.exports=api;else root.TEL99Scenarios=api;
})(typeof window==='object'?window:globalThis);
