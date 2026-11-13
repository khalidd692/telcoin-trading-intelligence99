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
 const groups=[{method,count:count(horizon?.count)}];
 if(horizon?.by_rsi_method&&typeof horizon.by_rsi_method==='object')for(const [name,value] of Object.entries(horizon.by_rsi_method))if(name!==method)groups.push({method:name,count:count(value?.count)});
 return groups;
}
function chartBars(frame,status){return ['Clôtures incohérentes','Provenance incohérente'].includes(status)?[]:Array.isArray(frame?.bars)?frame.bars:[];}
const api={readBook,buyImpact,accumulation,layout,distancePct,gaugeFreshness,horizonGroups,chartBars};
if(typeof module==='object')module.exports=api;else root.TEL99Widgets=api;
})(typeof window==='object'?window:globalThis);
