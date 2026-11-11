'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),T=require('../site/terminal/core.js');
// Regression: a normal ISO FX reference must be accepted, future/missing rejected.
test('FX accepts dated EUR/USD and rejects invalid references',()=>{
 assert.equal(typeof T.parseFx,'function');
 assert.equal(T.parseFx({base:'EUR',date:'2026-11-10',rates:{USD:1.12}},Date.parse('2026-11-11T10:00Z')).rate,1.12);
 assert.equal(T.parseFx({base:'EUR',date:'2026-11-12',rates:{USD:1.12}},Date.parse('2026-11-11T10:00Z')),null);
});
const S=()=>require('../site/terminal/scenarios.js');
const now=1794394000;
function fixture(){const latest={close:100,ema20:98,ema50:95,atr14:2,support20:96,resistance20:120,rsi14:55,macd_improving:true,volume_ratio:1.2,trend:'HAUSSIER'};return {as_of:now,frames:Object.fromEntries(Object.keys(T.steps).map(tf=>[tf,{ready:true,quality:{last_close:now},latest:{...latest},bars:[{t:now-2*T.steps[tf],c:100,h:101,l:97},{t:now-T.steps[tf],c:101,h:102,l:97}],series:[{ema20:98,resistance20:120}]}])),context:{}};}
const options={now,quote:{price:102,bid:101.9,ask:102,received:now},capital:1000,budgetUsd:450,fee:.004,slip:.003};
test('three scenarios keep unknown fees blocked and costs in RR',()=>{
 assert.equal(typeof S().generate,'function');const plans=S().generate(fixture(),options);assert.equal(plans.length,3);
 assert.ok(plans.every(p=>p.status!=='PRÊT À ÉVALUER'&&p.reasons.some(r=>r.includes('Frais'))));
 assert.ok(plans[0].rrNet<plans[0].rr);assert.ok(plans[0].risk<=2.5&&plans[0].cash<=450);
});
test('stale quote, snapshot, missing 15m, broken support and TV contradiction block readiness',()=>{
 for(const mutate of [d=>d.as_of-=901,d=>delete d.frames['15m'],d=>d.frames['4h'].latest.close=90]){let d=fixture();mutate(d);assert.notEqual(S().generate(d,options)[0].status,'PRÊT À ÉVALUER');}
 assert.ok(S().generate(fixture(),{...options,quote:null})[0].reasons.some(r=>r.includes('Cotation')));
 assert.ok(S().generate(fixture(),{...options,tv:{contradictory:true,observedAt:now}})[0].reasons.some(r=>r.includes('TradingView')));
});
test('allocation respects aggregate loss and cash instead of splitting budget blindly',()=>{
 const p=S().generate(fixture(),options);const a=S().allocate(p,1000,450);
 assert.ok(a.risk<=2.50000001&&a.cash<=450.00000001);assert.equal(S().allocate(p,1000,NaN).valid,false);
});
test('copy refuses hypothetical or expired scenarios',()=>{
 const p=S().generate(fixture(),options)[0];assert.throws(()=>S().copyText(p,now));
 assert.throws(()=>S().copyText({...p,status:'PRÊT À ÉVALUER',expiresAt:now-1},now));
});
test('stale analytics hide all indicative quantities even with a fresh quote',()=>{
 const d=fixture();d.as_of=now-901;assert.ok(S().generate(d,options).every(p=>p.qty===null));
});
test('verified fresh confirmation can be copied but never sends an order',()=>{
 const p=S().generate(fixture(),{...options,feesVerified:true,feesVerifiedAt:now,liquidityVerified:true,tv:{observedAt:now,contradictory:false}})[1];
 assert.equal(p.status,'PRÊT À ÉVALUER');assert.match(S().copyText(p,now),/AUCUN ORDRE/);
});
