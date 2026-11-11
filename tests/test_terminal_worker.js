const test=require('node:test'),assert=require('node:assert/strict');
let worker;
test('worker refuses writes and does not proxy arbitrary routes',async()=>{
 worker=(await import('../deploy/sites/worker.mjs')).default;
 assert.equal((await worker.fetch(new Request('https://test/api/quote',{method:'POST'}))).status,405);
 assert.equal((await worker.fetch(new Request('https://test/api/order'))).status,404);
});
test('snapshot proxy rejects older data and research mutations',async()=>{
 const {validSnapshot}=await import('../deploy/sites/worker.mjs');
 const base={schema_version:1,market:'KRAKEN:TELUSD',source:'Kraken public REST / OHLC',as_of:100,research_source_sha256:'abc',lab:{x:1},safety:{real_orders:false,paper_orders:false},frames:Object.fromEntries(['15m','1h','4h','1D'].map(tf=>[tf,{symbol:'KRAKEN:TELUSD',interval:tf,bars:[]}]))};
 assert.equal(validSnapshot({...base,as_of:101},base,110),true);
 assert.equal(validSnapshot({...base,as_of:99},base,110),false);
 assert.equal(validSnapshot({...base,lab:{x:2}},base,110),false);
});
