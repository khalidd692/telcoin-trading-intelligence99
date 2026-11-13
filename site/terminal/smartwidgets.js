/* Read-only display helpers. None of these functions changes a radar decision. */
(function(root){
'use strict';
const positive = n => typeof n === 'number' && Number.isFinite(n) && n > 0;
function readBook(payload){
 if(!Array.isArray(payload?.error)||payload.error.length||!payload.result||typeof payload.result!=='object')return null;
 const keys=Object.keys(payload.result);
 if(keys.length!==1||!['TELUSD','XTELZUSD'].includes(keys[0]))return null;
 const raw=payload.result[keys[0]];
 function levels(side,descending){
  if(!Array.isArray(side)||!side.length)return null;
  const parsed=side.map(row=>Array.isArray(row)?[Number(row[0]),Number(row[1])]:[]);
  if(parsed.some(row=>!positive(row[0])||!positive(row[1])))return null;
  return parsed.sort((a,b)=>descending?b[0]-a[0]:a[0]-b[0]);
 }
 const bids=levels(raw?.bids,true),asks=levels(raw?.asks,false);
 if(!bids||!asks||bids[0][0]>=asks[0][0])return null;
 const bid=bids[0][0],ask=asks[0][0];
 const depth=side=>side.reduce((sum,[price,quantity])=>sum+price*quantity,0);
 const bidDepth=depth(bids),askDepth=depth(asks);
 if(!positive(bidDepth)||!positive(askDepth))return null;
 return {bids,asks,bid,ask,spread:ask-bid,spreadPct:100*(ask-bid)/((ask+bid)/2),bidDepth,askDepth,imbalance:100*(bidDepth-askDepth)/(bidDepth+askDepth)};
}
function buyImpact(book,amountEur,eurUsd){
 if(!book||!positive(amountEur)||!positive(eurUsd)||!positive(book.ask)||!Array.isArray(book.asks))return null;
 const budget=amountEur*eurUsd;
 let remaining=budget,quantity=0;
 for(const [price,available] of book.asks){
  const spent=Math.min(remaining,price*available);
  quantity+=spent/price;remaining-=spent;
  if(remaining<=budget*1e-12)break;
 }
 if(remaining>budget*1e-12||!positive(quantity))return null;
 const average=budget/quantity;
 return {average,quantity,slippagePct:100*(average/book.ask-1)};
}
function accumulation(quantity,investedEur,priceUsd,eurUsd){
 if(!positive(quantity)||typeof investedEur!=='number'||!Number.isFinite(investedEur)||investedEur<0)return null;
 const valueUsd=positive(priceUsd)?quantity*priceUsd:null;
 const valueEur=valueUsd!==null&&positive(eurUsd)?valueUsd/eurUsd:null;
 return {averageEur:investedEur/quantity,valueUsd,valueEur,pnlEur:valueEur===null?null:valueEur-investedEur};
}
function layout(saved,known){
 const seen=new Set(),out=[];
 for(const id of [...(Array.isArray(saved)?saved:[]),...known]){
  if(known.includes(id)&&!seen.has(id)){seen.add(id);out.push(id);}
 }
 return out;
}
function distancePct(level,reference){return positive(level)&&positive(reference)?100*(level-reference)/reference:null;}
function gaugeFreshness(frames,capture,now,frameStatus){
 return Object.fromEntries(['15m','1h','4h','1D'].map(unit=>[unit,frameStatus(frames?.[unit],unit,capture,now)]));
}
function horizonGroups(horizon){
 const count=x=>Number.isInteger(x)&&x>=0?x:null;
 const method=typeof horizon?.rsi_method==='string'&&horizon.rsi_method?horizon.rsi_method:'méthode non indiquée';
 const group=(name,value)=>{const n=count(value?.count);return {method:name,count:n,meanPct:n>0&&typeof value?.mean_pct==='number'&&Number.isFinite(value.mean_pct)?value.mean_pct:null};};
 if(horizon?.by_outcome_method&&Object.keys(horizon.by_outcome_method).length){
  const labels={closed_candle_time_v2:'Avant : depuis la clôture',observation_time_v3:'Depuis l’observation'};
  const separated=[];
  for(const [kind,entry] of Object.entries(horizon.by_outcome_method))
   for(const [name,value] of Object.entries(entry?.by_rsi_method??{}))separated.push(group((labels[kind]??kind)+' · '+name,value));
  if(separated.length)return separated;
 }
 const groups=[group(method,horizon)];
 if(horizon?.by_rsi_method&&typeof horizon.by_rsi_method==='object')for(const [name,value] of Object.entries(horizon.by_rsi_method))if(name!==method)groups.push(group(name,value));
 return groups;
}
function chartBars(frame,status){return ['Clôtures incohérentes','Provenance incohérente'].includes(status)?[]:Array.isArray(frame?.bars)?frame.bars:[];}
function readMarketTickers(payload){
 if(!Array.isArray(payload?.error)||payload.error.length||!payload.result||typeof payload.result!=='object')return null;
 const specs=[['TEL/USD','TEL','USD',['TELUSD','XTELZUSD']],['TEL/EUR','TEL','EUR',['TELEUR']],['BTC/USD','BTC','USD',['XXBTZUSD','XBTUSD']],['ETH/USD','ETH','USD',['XETHZUSD','ETHUSD']]];
 const number=x=>{
  if(typeof x==='number')return Number.isFinite(x)?x:NaN;
  if(typeof x!=='string'||!/^\s*(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?\s*$/i.test(x))return NaN;
  return Number(x);
 };
 const field=(row,key,index)=>Array.isArray(row?.[key])?number(row[key][index]):NaN;
 return specs.map(([pair,base,currency,keys])=>{
  const found=keys.filter(k=>Object.hasOwn(payload.result,k));
  const item=found.length===1?payload.result[found[0]]:null;
  const last=field(item,'c',0),bid=field(item,'b',0),ask=field(item,'a',0),open=number(item?.o),volume=field(item,'v',1);
  return {pair,base,currency,price:positive(last)?last:null,change:positive(last)&&positive(open)?100*(last/open-1):null,volume:Number.isFinite(volume)&&volume>=0?volume:null,spread:positive(bid)&&positive(ask)&&ask>=bid?100*(ask-bid)/((ask+bid)/2):null};
 });
}
function marketFresh(received,now){return positive(received)&&Number.isFinite(now)&&now>=received&&now-received<=120;}
const api={readBook,buyImpact,accumulation,layout,distancePct,gaugeFreshness,horizonGroups,chartBars,readMarketTickers,marketFresh};
if(typeof module==='object')module.exports=api;else root.TEL99Widgets=api;
})(typeof window==='object'?window:globalThis);
