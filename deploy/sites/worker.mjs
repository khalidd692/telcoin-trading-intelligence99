// Fixed public read-only routes. Bundler supplies assets as an in-memory constant.
const routes={
 '/api/quote':'https://api.kraken.com/0/public/Ticker?pair=TELUSD',
 '/api/depth':'https://api.kraken.com/0/public/Depth?pair=TELUSD&count=100',
 '/api/markets':'https://api.kraken.com/0/public/Ticker?pair=TELUSD,TELEUR,XBTUSD,ETHUSD',
 '/api/fx':'https://api.frankfurter.dev/v1/latest?base=EUR&symbols=USD',
 '/evaluation/summary.json':'https://raw.githubusercontent.com/khalidd692/telcoin-trading-intelligence99/refs/heads/tel99-evaluation-data/evaluation/summary.json',
 '/data.json':'https://raw.githubusercontent.com/khalidd692/telcoin-trading-intelligence99/tel99-live-data/site/terminal/data.json'
};
const reply=(body,type='application/json',status=200,extra={})=>new Response(body,{status,headers:{'Content-Type':type+'; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff',...extra}});
export function validSnapshot(d,baseline,now=Date.now()/1000){
 return d?.schema_version===1&&d.market==='KRAKEN:TELUSD'&&d.source==='Kraken public REST / OHLC'&&Number.isFinite(d.as_of)&&d.as_of<=now+60&&d.as_of>=baseline.as_of&&d.research_source_sha256===baseline.research_source_sha256&&JSON.stringify(d.lab)===JSON.stringify(baseline.lab)&&JSON.stringify(d.safety)===JSON.stringify(baseline.safety)&&d.safety.real_orders===false&&d.safety.paper_orders===false&&['15m','1h','4h','1D'].every(tf=>d.frames?.[tf]?.symbol==='KRAKEN:TELUSD'&&d.frames[tf].interval===tf&&Array.isArray(d.frames[tf].bars));
}
const branchRef=routes['/data.json'].replace('/tel99-live-data/','/refs/heads/tel99-live-data/');
async function readPublic(url,timeout){
 const response=await fetch(url,{headers:{Accept:'application/json'},signal:AbortSignal.timeout(timeout),cf:{cacheTtl:0}});
 if(!response.ok)throw Error('Public source unavailable');
 const text=await response.text();
 if(text.length>5000000)throw Error('Response too large');
 return {text,data:JSON.parse(text)};
}
export async function snapshotResponse(read,baseline,now=Date.now()/1000){
 const load=async url=>{
  try{const candidate=await read(url,5000);return validSnapshot(candidate.data,baseline,now)?candidate:null;}
  catch{return null;}
 };
 const primary=await load(routes['/data.json']);
 const close=primary?.data.frames['15m'].quality?.last_close;
 const expected=Math.floor(now/900)*900;
 const behind=now-expected>=120&&(!Number.isFinite(close)||close<expected);
 if(!primary||behind||now-primary.data.as_of>480){
  const alternate=await load(branchRef);
  const alternateClose=alternate?.data.frames['15m'].quality?.last_close;
  if(alternate&&(!primary||(alternate.data.as_of>primary.data.as_of&&(!Number.isFinite(close)||alternateClose>=close)))){
   return {...alternate,source:'github-branch-ref'};
  }
 }
 return primary;
}
export default {async fetch(request){
 if(!['GET','HEAD'].includes(request.method))return reply('{"error":"read-only"}',undefined,405);
 const path=new URL(request.url).pathname,assets=typeof ASSETS==='undefined'?{}:ASSETS;
 const head=request.method==='HEAD';
 if(path==='/data.json'&&assets[path]){
  const snapshot=await snapshotResponse(readPublic,JSON.parse(assets[path].body));
  if(snapshot)return reply(head?null:snapshot.text,undefined,200,snapshot.source?{'X-TEL99-Source':snapshot.source}:{});
  return reply(head?null:assets[path].body,undefined,200,{'X-TEL99-Source':'dated-deployment-fallback'});
 }
 if(routes[path]){
  try{const {text}=await readPublic(routes[path],12000);return reply(head?null:text);}
  catch{return reply('{"error":"public source unavailable"}',undefined,503);}
 }
 const a=assets[path==='/'?'/index.html':path];
 if(!a)return reply('{"error":"not found"}',undefined,404);
 return reply(head?null:a.body,a.type);
}};
