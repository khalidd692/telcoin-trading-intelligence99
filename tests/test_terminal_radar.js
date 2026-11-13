'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {steps}=require('../site/terminal/core.js');
const {readRadar}=require('../site/terminal/radar.js');
const now=8640000;
function fixture(){
 const frames=Object.fromEntries(Object.entries(steps).map(([interval,step])=>{
  const last=Math.floor(now/step)*step;
  const bars=Array.from({length:60},(_,i)=>({t:last-(60-i)*step,o:100,h:103,l:99,c:101,v:10}));
  return [interval,{interval,symbol:'KRAKEN:TELUSD',ready:true,quality:{last_close:last,last_segment_bars:60},bars,series:bars.map(b=>({t:b.t,ema20:100,rsi14:45})),latest:{trend:'MIXTE',rsi14:45,volume_ratio:1}}];
 }));
 return {market:'KRAKEN:TELUSD',source:'Kraken public REST / OHLC',as_of:now,frames,decision:{status:'ATTENDRE',invalidation:90}};
}
function supportBounce(d){
 const m=d.frames['15m'];
 m.bars.at(-4).l=95;
 m.bars.at(-8).h=104;
 Object.assign(m.bars.at(-1),{l:95,c:102,v:16});
 m.latest.volume_ratio=1.6;
 return d;
}
test('an early support bounce and volume produce a non-confirmed alert without quote or admissible RR',()=>{
 const result=readRadar(supportBounce(fixture()),[{id:'early',status:'REJETÉ',rrNet:0.8}],now);
 assert.equal(result.status,'ALERTE PRÉCOCE');
 assert.equal(result.invalidation.level,95);
 assert.equal(result.watch.level,104);
 assert.equal(result.event.type,'EARLY_ALERT');
 assert.equal(result.event.confirmed,false);
 assert.equal(result.event.candle_closed_at,now);
 assert.ok(result.factors.find(x=>x.id==='support').active);
});
test('momentum alone cannot trigger and favorable RR alone cannot confirm',()=>{
 const d=fixture();d.frames['15m'].latest.rsi_divergence=true;
 const r=readRadar(d,[{id:'reversal',status:'CONDITIONNEL',admissible:true,confirmed:false,rrNet:2,reasons:['Confirmation non observée']}],now);
 assert.equal(r.status,'ATTENDRE');assert.equal(r.event,null);
 assert.deepEqual(r.blockers,['Confirmation non observée']);
});
test('verified executable scenario alone may confirm, and source invalidation takes precedence',()=>{
 const d=fixture(),plan={id:'reversal',status:'PRÊT À ÉVALUER',confirmed:true,rrNet:1.5,entry:103,stop:95};
 assert.equal(readRadar(d,[plan],now).event.type,'CONFIRMATION');
 assert.equal(readRadar(d,[{...plan,rrNet:1.49}],now).status,'ATTENDRE');
 d.decision.status='INVALIDATION';d.frames['4h'].bars.at(-1).c=89;
 assert.equal(readRadar(d,[plan],now).event.type,'INVALIDATION');
});
test('stale, future, gapped or unproven data cannot alert or display actionable levels',()=>{
 for(const mutate of [d=>d.as_of-=901,d=>d.frames['15m'].bars.at(-1).t+=900,d=>d.frames['15m'].bars.at(-2).t-=900,d=>d.frames['1h'].symbol='OTHER',d=>d.frames['15m'].quality.invalid_tail=true]){
  const d=supportBounce(fixture());mutate(d);
  const r=readRadar(d,[],now);assert.equal(r.status,'DONNÉES INSUFFISANTES');assert.equal(r.event,null);assert.equal(r.watch,null);assert.equal(r.invalidation,null);
 }
});
test('a currently forming zone cannot count as a retest',()=>{
 const d=fixture(),m=d.frames['15m'];
 m.bars.at(-4).l=95;
 Object.assign(m.bars.at(-1),{o:106,l:104,h:108,c:107});m.latest.volume_ratio=1.6;
 const r=readRadar(d,[],now);assert.equal(r.factors.find(x=>x.id==='zone').active,false);
});
test('the next confirmed close can invalidate the previous early alert',()=>{
 const d=supportBounce(fixture()),m=d.frames['15m'];
 m.bars.shift();m.series.shift();
 m.bars.push({t:now,o:99,h:101,l:92,c:94,v:10});
 m.series.push({t:now,ema20:100,rsi14:40});
 d.as_of=now+900;m.quality.last_close=now+900;
 const r=readRadar(d,[],now+900);
 assert.equal(r.status,'INVALIDATION');assert.equal(r.event.type,'INVALIDATION');
 assert.equal(r.invalidation.unit,'15m');assert.equal(r.event.candle_closed_at,now+900);
});
test('convergence uses the higher-unit candle available at the 15m signal close',()=>{
 const d=supportBounce(fixture()),m=d.frames['15m'],h=d.frames['1h'];
 m.bars.pop();m.series.pop();m.quality.last_close=now-900;
 m.bars.at(-3).l=95;m.bars.at(-8).h=104;
 Object.assign(m.bars.at(-1),{l:95,c:102,v:10});
 h.series.at(-2).ema20=105;
 h.series.at(-1).ema20=100;
 h.latest.ema20=100;h.latest.close=101;
 const four=d.frames['4h'];four.latest.ema20=100;four.latest.close=101;
 const r=readRadar(d,[],now);
 assert.equal(r.factors.find(x=>x.id==='convergence').active,false);
 assert.equal(r.status,'ATTENDRE');
});
