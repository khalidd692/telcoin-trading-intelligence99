// Fixed public read-only routes. Bundler supplies assets as an in-memory constant.
const routes={
 '/api/quote':'https://api.kraken.com/0/public/Ticker?pair=TELUSD',
 '/api/fx':'https://api.frankfurter.dev/v1/latest?base=EUR&symbols=USD',
 '/data.json':'https://raw.githubusercontent.com/khalidd692/telcoin-trading-intelligence99/tel99-live-data/site/terminal/data.json'
};
const reply=(body,type='application/json',status=200,extra={})=>new Response(body,{status,headers:{'Content-Type':type+'; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff',...extra}});
export function validSnapshot(d,baseline,now=Date.now()/1000){
 return d?.schema_version===1&&d.market==='KRAKEN:TELUSD'&&d.source==='Kraken public REST / OHLC'&&Number.isFinite(d.as_of)&&d.as_of<=now+60&&d.as_of>=baseline.as_of&&d.research_source_sha256===baseline.research_source_sha256&&JSON.stringify(d.lab)===JSON.stringify(baseline.lab)&&JSON.stringify(d.safety)===JSON.stringify(baseline.safety)&&d.safety.real_orders===false&&d.safety.paper_orders===false&&['15m','1h','4h','1D'].every(tf=>d.frames?.[tf]?.symbol==='KRAKEN:TELUSD'&&d.frames[tf].interval===tf&&Array.isArray(d.frames[tf].bars));
}
export default {async fetch(request){
 if(!['GET','HEAD'].includes(request.method))return reply('{"error":"read-only"}',undefined,405);
 const path=new URL(request.url).pathname,assets=typeof ASSETS==='undefined'?{}:ASSETS;
 if(routes[path]){
  try{
   const response=await fetch(routes[path],{headers:{Accept:'application/json'},signal:AbortSignal.timeout(12000),cf:{cacheTtl:0}});
   if(!response.ok)throw Error('Public source unavailable');
   const text=await response.text();if(text.length>5000000)throw Error('Response too large');
   const data=JSON.parse(text);
   if(path==='/data.json'){
    const baseline=JSON.parse(assets['/data.json'].body);
    if(!validSnapshot(data,baseline))throw Error('Snapshot provenance rejected');
   }
   return reply(request.method==='HEAD'?null:text);
  }catch{
   if(path==='/data.json'&&assets[path])return reply(request.method==='HEAD'?null:assets[path].body,undefined,200,{'X-TEL99-Source':'dated-deployment-fallback'});
   return reply('{"error":"public source unavailable"}',undefined,503);
  }
 }
 const a=assets[path==='/'?'/index.html':path];
 if(!a)return reply('{"error":"not found"}',undefined,404);
 return reply(request.method==='HEAD'?null:a.body,a.type);
}};
