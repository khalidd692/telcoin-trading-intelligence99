/* Descriptive Smart View indicators, based exclusively on validated closed TEL99 bars. */
'use strict';
(function(root){
const steps={'15m':900,'1h':3600,'4h':14400,'1D':86400,'1W':604800};
const finite=Number.isFinite;
const avg=xs=>xs.reduce((a,b)=>a+b,0)/xs.length;
const last=xs=>xs.at(-1);
const tail=(xs,n)=>xs.slice(-n);
const sma=(xs,n)=>xs.length>=n&&tail(xs,n).every(finite)?avg(tail(xs,n)):null;
const wma=(xs,n)=>xs.length>=n&&tail(xs,n).every(finite)?tail(xs,n).reduce((a,b,i)=>a+b*(i+1),0)/(n*(n+1)/2):null;
function smooth(xs,n,alpha){
 const out=[];let run=[], value=null;
 for(const x of xs){
  if(!finite(x)){run=[];value=null;}
  else if(value!==null)value+=(x-value)*alpha;
  else{run.push(x);if(run.length===n)value=avg(run);}
  out.push(value);
 }
 return out;
}
const ema=(xs,n)=>smooth(xs,n,2/(n+1));
const wilder=(xs,n)=>smooth(xs,n,1/n);
const rolling=(xs,n,fn)=>xs.map((_,i)=>i+1<n?null:fn(xs.slice(i+1-n,i+1)));
const diff=(a,b)=>finite(a)&&finite(b)?a-b:null;
const dir=x=>finite(x)?Math.sign(x):null;
const band=(x,lo,hi)=>finite(x)?x<lo?1:x>hi?-1:0:null;
const compare=(a,b)=>dir(diff(a,b));
const sumVotes=rows=>rows.reduce((acc,r)=>{if(r.vote===1)acc.buy++;else if(r.vote===-1)acc.sell++;else if(r.vote===0)acc.neutral++;return acc;},{buy:0,sell:0,neutral:0});
function contiguous(frame,tf){
 const bars=frame?.bars??[];let first=bars.length-1;
 while(first>0&&bars[first].t-bars[first-1].t===steps[tf])first--;
 return first<0?[]:bars.slice(first);
}
function weekly(daily,asOf){
 const day=steps['1D'],week=steps['1W'],monday=4*day;
 const groups=new Map();
 for(const row of daily?.bars??[]){
  const t=Math.floor((row.t-monday)/week)*week+monday;
  if(t+week>asOf)continue;
  if(!groups.has(t))groups.set(t,[]);
  groups.get(t).push(row);
 }
 const bars=[];
 for(const [t,rows] of groups){
  if(rows.length!==7||rows.some((r,i)=>r.t!==t+i*day))continue;
  bars.push({t,o:rows[0].o,h:Math.max(...rows.map(r=>r.h)),l:Math.min(...rows.map(r=>r.l)),c:last(rows).c,v:rows.reduce((sum,r)=>sum+r.v,0)});
 }
 const series=[];
 let first=0;
 for(let i=1;i<=bars.length;i++){
  if(i<bars.length&&bars[i].t-bars[i-1].t===week)continue;
  const segment=bars.slice(first,i),closes=segment.map(r=>r.c);
  const e20=ema(closes,20),e50=ema(closes,50);
  const momentum=technical({bars:segment},'1W').momentum;
  segment.forEach((r,j)=>series.push({t:r.t,ema20:e20[j],ema50:e50[j],...momentum[j],sma200:sma(closes.slice(0,j+1),200)}));
  first=i;
 }
 const frame={symbol:'KRAKEN:TELUSD',interval:'1W',bars,series};
 const n=contiguous(frame,'1W').length,closeTime=bars.length?last(bars).t+week:null;
 const lastWeek=Math.floor((asOf-monday)/week)*week+monday;
 const fresh=Boolean(daily?.quality?.fresh&&closeTime===lastWeek);
 const end=last(series)??{};
 return {...frame,ready:fresh&&n>=1,latest:{...end,close:last(bars)?.c,trend:'INDÉTERMINÉ'},quality:{
  source_rows:daily?.bars?.length??0,valid_bars:bars.length,last_segment_bars:n,last_close:closeTime,fresh,
  excluded_rows:0,missing_bars:bars.length?Math.round((last(bars).t-bars[0].t)/week)+1-bars.length:0,
  segments:bars.length?1+bars.slice(1).filter((r,i)=>r.t-bars[i].t!==week).length:0}};
}
function technical(frame,tf){
 const b=contiguous(frame,tf),c=b.map(x=>x.c),h=b.map(x=>x.h),l=b.map(x=>x.l);
 const close=last(c),mid=b.map(x=>(x.h+x.l)/2),typical=b.map(x=>(x.h+x.l+x.c)/3);
 const changes=c.map((x,i)=>i?x-c[i-1]:null);
 const gains=wilder(changes.map(x=>x===null?null:Math.max(x,0)),14);
 const losses=wilder(changes.map(x=>x===null?null:Math.max(-x,0)),14);
 const rsi=gains.map((g,i)=>g===null?null:g+losses[i]?100*g/(g+losses[i]):50);
 const stoch=(x,lo,hi)=>finite(x)&&finite(lo)&&finite(hi)&&hi>lo?100*(x-lo)/(hi-lo):null;
 const rawK=b.map((x,i)=>i<13?null:stoch(x.c,Math.min(...l.slice(i-13,i+1)),Math.max(...h.slice(i-13,i+1))));
 const k=rolling(rawK,3,x=>sma(x,3)),d=rolling(k,3,x=>sma(x,3));
 const rawSR=rolling(rsi,14,x=>x.every(finite)?stoch(last(x),Math.min(...x),Math.max(...x)):null);
 const sr=rolling(rawSR,3,x=>sma(x,3)),sd=rolling(sr,3,x=>sma(x,3));
 const slow=ema(c,26),macd=ema(c,12).map((x,i)=>diff(x,slow[i])),signal=ema(macd,9);
 const tr=b.map((x,i)=>i?Math.max(x.h-x.l,Math.abs(x.h-c[i-1]),Math.abs(x.l-c[i-1])):null);
 const plus=h.map((x,i)=>i?x-h[i-1]>Math.max(0,l[i-1]-l[i])?x-h[i-1]:0:null);
 const minus=l.map((x,i)=>i?l[i-1]-x>Math.max(0,h[i]-h[i-1])?l[i-1]-x:0:null);
 const dp=wilder(plus,14),dm=wilder(minus,14);
 const adx=last(wilder(dp.map((x,i)=>x===null?null:x+dm[i]?100*Math.abs(x-dm[i])/(x+dm[i]):0),14));
 const tp=sma(typical,20),dev=tp===null?null:avg(tail(typical,20).map(x=>Math.abs(x-tp)));
 const cci=dev? (last(typical)-tp)/(.015*dev):null;
 const ao=diff(sma(mid,5),sma(mid,34));
 const will=finite(last(rawK))?last(rawK)-100:null;
 const e13=last(ema(c,13));
 const power=e13===null?null:last(h)+last(l)-2*e13;
 const pressure=b.map((x,i)=>i?x.c-Math.min(x.l,c[i-1]):null);
 const ult=[7,14,28].map(n=>{const denom=sma(tr,n),num=sma(pressure,n);return denom&&num!==null?num/denom:null;});
 const uo=ult.every(finite)?100*(4*ult[0]+2*ult[1]+ult[2])/7:null;
 const mom=c.length>=11?close-c.at(-11):null;
 const row=(name,period,value,vote,extra)=>({name,period,value:finite(value)?value:null,vote:finite(value)?vote:null,extra});
 const oscillators=[
  row('RSI','14 Wilder',last(rsi),band(last(rsi),30,70)),
  row('MACD','12 / 26 / 9',last(macd),compare(last(macd),last(signal)),last(signal)),
  row('Stochastique','14 / 3 / 3',last(k),compare(last(k),last(d)),last(d)),
  row('Stoch RSI','14 / 14 / 3 / 3',last(sr),compare(last(sr),last(sd)),last(sd)),
  row('ADX','14 Wilder',adx,finite(adx)?adx>=25?compare(last(dp),last(dm)):0:null),
  row('CCI','20',cci,band(cci,-100,100)),
  row('Momentum','10',mom,dir(mom)),
  row('Williams %R','14',will,band(will,-80,-20)),
  row('Awesome Oscillator','5 / 34',ao,dir(ao)),
  row('Bull Bear Power','13',power,dir(power)),
  row('Ultimate Oscillator','7 / 14 / 28',uo,band(uo,30,70)),
 ];
 const averages=[];
 for(const n of [10,20,30,50,100,200]){
  const e=last(ema(c,n)),s=sma(c,n);
  averages.push(row('EMA '+n,String(n),e,compare(close,e)),row('SMA '+n,String(n),s,compare(close,s)));
 }
 const volume=tail(b,20).reduce((a,x)=>a+x.v,0);
 const vwma=b.length>=20&&volume?tail(b,20).reduce((a,x)=>a+x.c*x.v,0)/volume:null;
 const hma=wma(rolling(c,9,x=>2*wma(x,4)-wma(x,9)),3);
 const kijun=b.length>=26?(Math.max(...tail(h,26))+Math.min(...tail(l,26)))/2:null;
 averages.push(row('VWMA','20',vwma,compare(close,vwma)),row('Hull MA','9',hma,compare(close,hma)),row('Ichimoku · Kijun','26',kijun,compare(close,kijun)));
 const counts=sumVotes(oscillators),averageCounts=sumVotes(averages);
 return {oscillators,averages,counts,averageCounts,total:Object.fromEntries(Object.keys(counts).map(k=>[k,counts[k]+averageCounts[k]])),pivots:pivots(b.at(-2),last(b)),momentum:rsi.map((rsi14,i)=>({rsi14,macd_hist:diff(macd[i],signal[i])}))};
}
function pivots(prev,current){
 if(!prev||!current)return [];
 const {h,l,c}=prev,r=h-l,p=(h+l+c)/3,w=(h+l+2*current.o)/4;
 const classic=[p+2*r,p+r,2*p-l,p,2*p-h,p-r,p-2*r];
 const fib=[p+r,p+.618*r,p+.382*r,p,p-.382*r,p-.618*r,p-r];
 const cam=[c+r*1.1/4,c+r*1.1/6,c+r*1.1/12,p,c-r*1.1/12,c-r*1.1/6,c-r*1.1/4];
 const wood=[h+2*(w-l),w+r,2*w-l,w,2*w-h,w-r,l-2*(h-w)];
 return ['R3','R2','R1','P','S1','S2','S3'].map((label,i)=>[label,classic[i],fib[i],cam[i],wood[i]]);
}
function marketLevels(frame,tf){
 const b=tail(contiguous(frame,tf),120),current=last(b);
 if(!current||b.length<5)return {profile:null};
 const highs=[],lows=[];
 for(let i=2;i<b.length-2;i++){
  const neighbors=[b[i-2],b[i-1],b[i+1],b[i+2]];
  if(neighbors.every(x=>b[i].h>x.h))highs.push(b[i].h);
  if(neighbors.every(x=>b[i].l<x.l))lows.push(b[i].l);
 }
 const resistance=last(highs),support=last(lows);
 const trend=highs.length>1&&lows.length>1?highs.at(-1)>highs.at(-2)&&lows.at(-1)>lows.at(-2)?'haussière':highs.at(-1)<highs.at(-2)&&lows.at(-1)<lows.at(-2)?'baissière':'mixte':'indéterminée';
 const previous=b.at(-2);
 const breaks=finite(resistance)&&previous.c<=resistance&&current.c>resistance?'Cassure haussière':finite(support)&&previous.c>=support&&current.c<support?'Cassure baissière':null;
 const fvgs=[];
 for(let i=Math.max(2,b.length-25);i<b.length;i++){
  if(b[i].l>b[i-2].h&&b.slice(i+1).every(r=>r.l>b[i-2].h))fvgs.push({low:b[i-2].h,high:b[i].l,side:'hausse'});
  if(b[i].h<b[i-2].l&&b.slice(i+1).every(r=>r.h<b[i-2].l))fvgs.push({low:b[i].h,high:b[i-2].l,side:'baisse'});
 }
 const min=Math.min(...b.map(r=>r.l)),max=Math.max(...b.map(r=>r.h));
 const fib=max>min?[.382,.5,.618,.786].map(x=>[x,max-x*(max-min)]):[];
 let profile=null;
 const step=(max-min)/24,total=b.reduce((a,r)=>a+r.v,0);
 if(total>0&&step>0){
  const bins=Array(24).fill(0);
  for(const r of b)bins[Math.min(23,Math.floor(((r.h+r.l+r.c)/3-min)/step))]+=r.v;
  const peak=bins.indexOf(Math.max(...bins));
  let lo=peak,hi=peak,weight=bins[peak];
  while(weight<total*.7&&(lo>0||hi<23)){
   if((bins[hi+1]??-1)>(bins[lo-1]??-1))weight+=bins[++hi];
   else weight+=bins[--lo];
  }
  profile={poc:min+(peak+.5)*step,val:min+lo*step,vah:min+(hi+1)*step,bins,min,step,peak,lo,hi,n:b.length};
 }
 return {profile,support,resistance,trend,breaks,fvgs:tail(fvgs,3),fib};
}
const api={technical,weekly,marketLevels,steps};
if(typeof module!=='undefined')module.exports=api;else root.TEL99SmartView=api;
})(typeof window==='undefined'?globalThis:window);
