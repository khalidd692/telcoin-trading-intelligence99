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
test('lagging branch cache retries its qualified ref and keeps provenance guards',async()=>{
 const {snapshotResponse}=await import('../deploy/sites/worker.mjs');
 const base={schema_version:1,market:'KRAKEN:TELUSD',source:'Kraken public REST / OHLC',as_of:9500,research_source_sha256:'abc',lab:{x:1},safety:{real_orders:false,paper_orders:false},frames:Object.fromEntries(['15m','1h','4h','1D'].map(tf=>[tf,{symbol:'KRAKEN:TELUSD',interval:tf,bars:[],quality:{last_close:9000}}]))};
 const current={...base,as_of:10020,frames:{...base.frames,'15m':{...base.frames['15m'],quality:{last_close:9900}}}};
 let calls=[];
 const read=async url=>{calls.push(url);return {text:JSON.stringify(calls.length===1?base:current),data:calls.length===1?base:current};};
 const fallback=await snapshotResponse(read,base,10100);
 assert.equal(fallback.data.as_of,10020);assert.equal(fallback.source,'github-branch-ref');
 assert.equal(calls.length,2);
 calls=[];
 const invalid={...current,lab:{x:2}};
 const safe=await snapshotResponse(async url=>{calls.push(url);return {text:'',data:calls.length===1?base:invalid};},base,10100);
 assert.equal(safe.data.as_of,9500);
 calls=[];
 await snapshotResponse(read,base,9960);
 assert.equal(calls.length,1);
});
