/* Pure, testable browser guards. No account or order code. */
(function(root){
'use strict';
const finite=x=>typeof x==='number' && Number.isFinite(x);
const steps={'15m':900,'1h':3600,'4h':14400,'1D':86400};
function safeDecision(data,now=Date.now()/1000){
 const reasons=[];
 if(!finite(now)||!finite(data.as_of)||now<data.as_of-60)reasons.push('Horloge incohérente');
 for(const tf of ['1h','4h']){
  const f=data.frames?.[tf],t=f?.quality?.last_close;
  if(!f?.ready||!finite(t)||now<t||now-t>steps[tf]+300)reasons.push(tf+' : données périmées ou insuffisantes');
 }
 return reasons.length?{...data.decision,status:'DONNÉES INSUFFISANTES',staleReasons:reasons}:data.decision;
}
function freshQuote(quote,now=Date.now()/1000){
 return !!quote&&finite(quote.price)&&quote.price>0&&finite(quote.received)&&finite(now)&&now>=quote.received&&now-quote.received<=120;
}
function riskPlan(capital,entry,stop,target,fee,slip){
 if(![capital,entry,stop,target,fee,slip].every(finite)||Math.min(capital,entry,stop,target)<=0||!(stop<entry&&entry<target)||fee<0||fee>=.1||slip<0||slip>=.1)return {admissible:false,error:'Vérifiez les prix, le capital et les coûts.'};
 const buy=entry*(1+slip),ss=stop*(1-slip),st=target*(1-slip),loss=buy-ss+fee*(buy+ss),reward=st-buy-fee*(buy+st),qty=Math.min(capital*.0025/loss,capital/(buy*(1+fee))),rr=(target-entry)/(entry-stop);
 if(![buy,ss,st,loss,reward,qty,rr,qty*buy*(1+fee),qty*loss,qty*reward,reward/loss].every(finite)||loss<=0||qty<=0)return {admissible:false,error:'Valeurs hors précision numérique.'};
 return {admissible:rr>=1.51&&reward>0,qty,cash:qty*buy*(1+fee),risk:qty*loss,budget:capital*.0025,rr,rrNet:reward/loss,reward:qty*reward};
}
function display(value,digits=2){return finite(value)?new Intl.NumberFormat('fr-FR',{minimumFractionDigits:digits,maximumFractionDigits:digits}).format(value):'—';}
function escape(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function chartSeries(rows,step,key){
 const out=[];let prev=null;
 for(const r of rows){if(prev!==null&&r.t-prev>step)out.push({time:prev+step});out.push(finite(r[key])?{time:r.t,value:r[key]}:{time:r.t});prev=r.t;}return out;
}
const api={finite,steps,safeDecision,freshQuote,riskPlan,display,escape,chartSeries};
if(typeof module==='object')module.exports=api;else root.TEL99=api;
})(typeof window==='object'?window:globalThis);
