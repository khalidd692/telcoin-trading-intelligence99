/* Pure, testable browser guards. No account or order code. */
(function(root){
'use strict';
const finite=x=>typeof x==='number' && Number.isFinite(x);
const steps={'15m':900,'1h':3600,'4h':14400,'1D':86400};
function safeDecision(data,now=Date.now()/1000){
 const reasons=[];
 if(!finite(now)||!finite(data.as_of)||now<data.as_of-60)reasons.push('Horloge incohérente');
 if(finite(now)&&finite(data.as_of)&&now-data.as_of>900)reasons.push('Snapshot analytique périmé (plus de 15 minutes)');
 for(const tf of ['1h','4h']){
  const f=data.frames?.[tf],t=f?.quality?.last_close;
  if(!f?.ready||!finite(t)||now<t||now-t>steps[tf]+300)reasons.push(tf+' : données périmées ou insuffisantes');
 }
 if(reasons.length)return {...data.decision,status:'DONNÉES INSUFFISANTES',staleReasons:reasons};
 const d=data.decision; if(['ACHAT PRÉCOCE','ACHAT CONFIRMÉ'].includes(d?.status)&&(!finite(d?.plan?.rr_net)||d.plan.rr_net<1.5))return {...d,status:'ATTENDRE',contradictions:[...(d.contradictions||[]),'Rendement/risque net inférieur à 1,5 ou non disponible.']};
 return d;
}
function acceptSnapshot(current,next,now=Date.now()/1000){
 if(!current||!next||next.schema_version!==1||next.market!=='KRAKEN:TELUSD'||next.source!=='Kraken public REST / OHLC')return false;
 if(!finite(next.as_of)||!finite(current.as_of)||next.as_of<=current.as_of||next.as_of>now+60||now-next.as_of>900)return false;
 if(next.research_source_sha256!==current.research_source_sha256||!next.research_source_sha256)return false;
 if(JSON.stringify(next.lab)!==JSON.stringify(current.lab)||JSON.stringify(next.safety)!==JSON.stringify(current.safety))return false;
 if(next.safety?.real_orders!==false||next.safety?.paper_orders!==false)return false;
 for(const tf of ['15m','1h','4h','1D']){
  const f=next.frames?.[tf];
  if(!f||f.interval!==tf||f.symbol!=='KRAKEN:TELUSD'||!Array.isArray(f.bars)||!f.bars.length||!Array.isArray(f.series)||!f.latest||!f.quality||!finite(f.quality.last_close))return false;
 }
 return true;
}
function freshQuote(quote,now=Date.now()/1000){
 return !!quote&&finite(quote.price)&&quote.price>0&&finite(quote.received)&&finite(now)&&now>=quote.received&&now-quote.received<=120;
}
function parseTelTicker(payload){
 if(!payload||!Array.isArray(payload.error)||payload.error.length||!payload.result||typeof payload.result!=='object')return null;
 const keys=Object.keys(payload.result);
 if(keys.length!==1||!['TELUSD','XTELZUSD'].includes(keys[0]))return null;
 const p=Number(payload.result[keys[0]]?.c?.[0]);
 return finite(p)&&p>0?p:null;
}
function riskPlan(capital,entry,stop,target,fee,slip){
 if(![capital,entry,stop,target,fee,slip].every(finite)||Math.min(capital,entry,stop,target)<=0||!(stop<entry&&entry<target)||fee<0||fee>=.1||slip<0||slip>=.1)return {admissible:false,error:'Vérifiez les prix, le capital et les coûts.'};
 const buy=entry*(1+slip),ss=stop*(1-slip),st=target*(1-slip),loss=buy-ss+fee*(buy+ss),reward=st-buy-fee*(buy+st),qty=Math.min(capital*.0025/loss,capital/(buy*(1+fee))),rr=(target-entry)/(entry-stop);
 if(![buy,ss,st,loss,reward,qty,rr,qty*buy*(1+fee),qty*loss,qty*reward,reward/loss].every(finite)||loss<=0||qty<=0)return {admissible:false,error:'Valeurs hors précision numérique.'};
 return {admissible:reward/loss>=1.5&&reward>0,qty,cash:qty*buy*(1+fee),risk:qty*loss,budget:capital*.0025,rr,rrNet:reward/loss,reward:qty*reward};
}
function display(value,digits=2){return finite(value)?new Intl.NumberFormat('fr-FR',{minimumFractionDigits:digits,maximumFractionDigits:digits}).format(value):'—';}
function escape(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function chartSeries(rows,step,key){
 const out=[];let prev=null;
 for(const r of rows){if(prev!==null&&r.t-prev>step)out.push({time:prev+step});out.push(finite(r[key])?{time:r.t,value:r[key]}:{time:r.t});prev=r.t;}return out;
}
const api={finite,steps,safeDecision,acceptSnapshot,freshQuote,parseTelTicker,riskPlan,display,escape,chartSeries};
if(typeof module==='object')module.exports=api;else root.TEL99=api;
})(typeof window==='object'?window:globalThis);
