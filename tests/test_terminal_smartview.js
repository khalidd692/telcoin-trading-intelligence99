const test = require('node:test');
const assert = require('node:assert/strict');
const {technical, weekly, marketLevels} = require('../site/terminal/smartview.js');
const day=86400, monday=Date.UTC(2026,0,5)/1000;
const bars=Array.from({length:220},(_,i)=>({t:monday+i*day,o:10+i,h:12+i,l:9+i,c:11+i,v:10}));
test('counts only computable indicators and resets after a gap',()=>{
 const r=technical({bars},'1D');
 assert.equal(r.averages.length,15);
 assert.equal(r.oscillators.length,11);
 assert.equal(r.averages.find(x=>x.name==='SMA 200').value,130.5);
 const short=technical({bars:[...bars,{...bars.at(-1),t:bars.at(-1).t+2*day}]},'1D');
 assert.equal(short.total.buy+short.total.sell+short.total.neutral,0);
});
test('weekly bars aggregate only seven complete consecutive UTC days',()=>{
 const frame=weekly({bars:bars.slice(0,13)},monday+13*day);
 assert.equal(frame.bars.length,1);
 assert.deepEqual(frame.bars[0],{t:monday,o:10,h:18,l:9,c:17,v:70});
 assert.equal(weekly({bars:bars.slice(0,13).filter((_,i)=>i!==3)},monday+13*day).bars.length,0);
});
test('profile ignores zero volume and bounds acceptance around POC',()=>{
 const r=marketLevels({bars},'1D');
 assert(r.profile.val<=r.profile.poc && r.profile.poc<=r.profile.vah);
 assert.equal(marketLevels({bars:bars.map(b=>({...b,v:0}))},'1D').profile,null);
});
test('structure markers only use confirmed swings and label relative highs',()=>{
 const swing=[10,11,15,11,10,11,16,12,10,11,17].map((price,i)=>({t:monday+i*day,h:price+1,l:price-1,c:price,o:price,v:10}));
 const markers=marketLevels({bars:swing},'1D').pivots;
 assert.deepEqual(markers.filter(p=>p.side==='high').map(p=>[p.time,p.label]),[[monday+2*day,'H'],[monday+6*day,'HH']]);
});
test('eight-day profile requires 192 contiguous hourly bars and uses 60 bins',()=>{
 const hourly=bars.map((r,i)=>({...r,t:monday+i*3600}));
 const {volumeProfile}=require('../site/terminal/smartview.js');
 assert.equal(volumeProfile({bars:hourly.slice(0,191)}),null);
 const p=volumeProfile({bars:hourly});
 assert.equal(p.n,192);assert.equal(p.bins.length,60);
 assert.equal(p.bins.reduce((a,b)=>a+b,0),1920);
 assert.equal(volumeProfile({bars:hourly.filter((_,i)=>i!==60)}),null);
});
test('structure uses closed confirmed pivots, then classifies continuation or reversal',()=>{
 const {structureEvents}=require('../site/terminal/smartview.js');
 const prices=[10,11,15,11,10,11,17,12,10,11,18,12,9,11,8,10,7];
 const bars=prices.map((c,i)=>({t:monday+i*day,c,o:c+.1,h:c+.3,l:c-.3,v:1}));
 const out=structureEvents({bars},'1D');
 assert.deepEqual(out.slice(0,3).map(e=>[e.time,e.label]),[[monday+6*day,'Cassure'],[monday+10*day,'BOS'],[monday+12*day,'CHoCH']]);
 assert.equal(structureEvents({bars:bars.slice(0,6)},'1D').length,0);
});
