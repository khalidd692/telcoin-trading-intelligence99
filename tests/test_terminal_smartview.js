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
