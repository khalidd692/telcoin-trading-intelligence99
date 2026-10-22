"use strict";
const assert=require("node:assert/strict");
const rt=require("../site/realtime.js");
function vi(v){let n=BigInt(v),o=[];while(n>127n){o.push(Number(n&127n)|128);n>>=7n;}o.push(Number(n));return o;}
function fb(f,x){const b=typeof x==="string"?Array.from(Buffer.from(x)):x;return [...vi((f<<3)|2),...vi(b.length),...b];}
function fv(f,x){return [...vi(f<<3),...vi(x)];}
function deal(price,time){const item=[...fb(1,price),...fb(2,"12.5"),...fv(3,1),...fv(4,time)],d=[...fb(1,item),...fb(2,"deals")];return new Uint8Array([...fb(1,"spot@public.aggre.deals.v3.api.pb@100ms@TELUSDT"),...fb(314,d),...fb(3,"TELUSDT"),...fv(4,time)]);}
function book(bid,ask,time){const b=[...fb(1,bid),...fb(2,"4"),...fb(3,ask),...fb(4,"5")];return new Uint8Array([...fb(1,"spot@public.aggre.bookTicker.v3.api.pb@100ms@TELUSDT"),...fb(315,b),...fb(3,"TELUSDT"),...fv(6,time)]);}
const now=Date.now(),src=(last,bid,ask,t,connected=true)=>({last,bid,ask,eventAt:t,bookEventAt:t,receivedAt:now,connected}),sources={mexc:src(.00123,.001229,.001231,now),kucoin:src(.001231,.00123,.001232,now)};
const trade=rt.decodeMexcFrame(deal("0.00123",now));assert.equal(trade.symbol,"TELUSDT");assert.equal(trade.trades[0].price,.00123);assert.equal(trade.trades[0].eventAt,now);
const b=rt.decodeMexcFrame(book("0.001229","0.001231",now));assert.equal(b.bookTicker.bid,.001229);assert.equal(b.bookTicker.ask,.001231);assert.equal(b.bookTicker.eventAt,now,"MEXC book timestamp must come from wrapper sendTime field 6");
assert.throws(()=>rt.decodeMexcFrame(new Uint8Array([255,255])),/protobuf|field/i);
assert.throws(()=>rt.decodeMexcFrame(deal("0",now)),/price/i);
assert.throws(()=>rt.decodeMexcFrame(book("0.002","0.001",now)),/below bid/i);
const ku=rt.parseKucoinTicker({type:"message",topic:"/market/ticker:TEL-USDT",data:{sequence:"42",price:"0.001231",bestBid:"0.001230",bestAsk:"0.001232",Time:now}});assert.equal(ku.last,.001231);assert.equal(ku.sequence,42);
assert.throws(()=>rt.parseKucoinTicker({type:"message",topic:"/market/ticker:OTHER-USDT",data:{}}),/Unexpected/i);
assert.throws(()=>rt.parseKucoinTicker({type:"message",topic:"/market/ticker:TEL-USDT",data:{sequence:"42",price:"0",bestBid:"1",bestAsk:"2",Time:now}}),/last price/i);
const good=rt.assess(sources,now,{fresh:true,status:"SURVEILLER",checksPass:true});assert.equal(good.ok,true);assert.ok(good.spreadPct>0&&good.divergencePct>0);
assert.equal(rt.assess({...sources,kucoin:{...sources.kucoin,connected:false}},now,{fresh:true,status:"SURVEILLER",checksPass:true}).ok,false);
assert.equal(rt.assess({...sources,mexc:{...sources.mexc,eventAt:now-31000,bookEventAt:now}},now,{fresh:true,status:"SURVEILLER",checksPass:true}).ok,false);
assert.equal(rt.assess(sources,now,{fresh:false,status:"SURVEILLER",checksPass:true}).ok,false);
assert.equal(rt.assess(sources,now,{fresh:true,status:"ATTENDRE",checksPass:false}).ok,false);
assert.equal(rt.assess({...sources,mexc:{...sources.mexc,ask:.00124}},now,{fresh:true,status:"SURVEILLER",checksPass:true}).ok,false);
assert.equal(rt.assess({...sources,kucoin:{...sources.kucoin,last:.0013}},now,{fresh:true,status:"SURVEILLER",checksPass:true}).ok,false);
const kucoinOldTrade={...sources.kucoin,eventAt:now-31000,bookEventAt:now,receivedAt:now};
const kucoinOldResult=rt.assess({...sources,kucoin:kucoinOldTrade},now,{fresh:true,status:"SURVEILLER",checksPass:true});
assert.equal(kucoinOldResult.ok,false,"a stale KuCoin last trade must still fail closed");
assert.ok(kucoinOldResult.reasons.some(x=>x.includes("dernier trade périmé")),"stale last trade must be explicit");
assert.ok(!kucoinOldResult.reasons.some(x=>x.includes("KUCOIN : bid/ask périmé")),"fresh KuCoin book must not be judged by last-trade timestamp");
assert.equal(kucoinOldResult.spreadPct!==null,true,"fresh MEXC book spread remains measurable");
assert.equal(kucoinOldResult.divergencePct,null,"cross-exchange divergence must be suppressed when KuCoin last trade is stale");
const oldBookResult=rt.assess({...sources,kucoin:{...sources.kucoin,bookEventAt:now-31001}},now,{fresh:true,status:"SURVEILLER",checksPass:true});
assert.ok(oldBookResult.reasons.some(x=>x.includes("KUCOIN : bid/ask périmé")),"stale book must still fail closed");
assert.equal(rt.isOutOfOrder(100,99),true);assert.equal(rt.isOutOfOrder(100,100),false);assert.equal(rt.reconnectDelay(1),1000);assert.equal(rt.reconnectDelay(2),2000);assert.equal(rt.reconnectDelay(10),30000);

function fakeEnvironment(WebSocketImpl) {
  const elements = Object.create(null), timeouts = new Map(), intervals = new Map();
  let nextId = 0;
  const root = {
    document: { getElementById(id) { return elements[id] || (elements[id] = { textContent: "", className: "", style: {}, innerHTML: "" }); } },
    WebSocket: WebSocketImpl,
    URL,
    telcoinReportIsFresh: false,
    telcoinReportStatus: "ATTENDRE",
    telcoinReportChecksPass: false,
    addEventListener() {},
    setTimeout(fn, delay) { const id = ++nextId; timeouts.set(id, { fn, delay }); return id; },
    clearTimeout(id) { timeouts.delete(id); },
    setInterval(fn, delay) { const id = ++nextId; intervals.set(id, { fn, delay }); return id; },
    clearInterval(id) { intervals.delete(id); },
    fetch: async () => ({ ok: true, json: async () => ({
      code: "200000", data: { token: "test-public-token", instanceServers: [{ endpoint: "wss://unit.invalid/", pingInterval: 18000, pingTimeout: 10000 }] }
    }) }),
    runTimeout(delay) { const found = Array.from(timeouts.entries()).find(([, value]) => value.delay === delay); assert.ok(found, "scheduled reconnect exists"); timeouts.delete(found[0]); found[1].fn(); },
    elements
  };
  return root;
}
function FakeSocket(url) {
  this.url = url; this.readyState = 0; this.sent = [];
  FakeSocket.instances.push(this);
}
FakeSocket.instances = [];
FakeSocket.prototype.send = function (data) { this.sent.push(data); };
FakeSocket.prototype.open = function () { this.readyState = 1; this.onopen(); };
FakeSocket.prototype.message = function (data) { this.onmessage({ data }); };
FakeSocket.prototype.close = function () { this.readyState = 3; if (this.onclose) this.onclose(); };

(async () => {
  const absentRoot = fakeEnvironment(undefined);
  const absentController = rt.mount(absentRoot);
  assert.match(absentController.state.mexc.status, /RECONNEXION/);
  assert.match(absentRoot.elements["realtime-status"].textContent, /ATTENDRE/);
  absentController.stop();

  FakeSocket.instances = [];
  const root = fakeEnvironment(FakeSocket);
  const controller = rt.mount(root);
  await Promise.resolve(); await Promise.resolve();
  assert.equal(FakeSocket.instances.length, 2, "both public feeds attempt a connection");
  const mexcSocket = FakeSocket.instances[0], kucoinSocket = FakeSocket.instances[1];
  mexcSocket.open(); kucoinSocket.open();
  assert.equal(kucoinSocket.sent.length, 0, "KuCoin must not subscribe before welcome");
  kucoinSocket.message(JSON.stringify({ type: "welcome" }));
  assert.equal(kucoinSocket.sent.length, 1, "KuCoin subscribes after welcome");
  assert.equal(controller.state.kucoin.connected, true, "KuCoin welcome is not treated as a malformed ticker");
  assert.equal(controller.state.kucoin.status, "ABONNEMENT");
  mexcSocket.close();
  assert.equal(controller.state.mexc.connected, false);
  assert.match(controller.state.mexc.status, /RECONNEXION/);
  assert.match(root.elements["realtime-status"].textContent, /ATTENDRE/);
  root.runTimeout(1000);
  assert.equal(FakeSocket.instances.length, 3, "closed MEXC socket reconnects after backoff");
  controller.stop();
  FakeSocket.instances = [];
  const relayRoot = fakeEnvironment(FakeSocket);
  relayRoot.TELCOIN_REALTIME_RELAY_URL = "wss://relay.invalid/";
  let relayFetches = 0;
  relayRoot.fetch = async () => { relayFetches++; throw new Error("browser token fetch must be bypassed when relay is configured"); };
  const relayController = rt.mount(relayRoot);
  await Promise.resolve(); await Promise.resolve();
  assert.equal(FakeSocket.instances.length, 2, "relay mode still opens both venue sockets");
  assert.equal(new URL(FakeSocket.instances[0].url).searchParams.get("venue"), "mexc");
  assert.equal(new URL(FakeSocket.instances[1].url).searchParams.get("venue"), "kucoin");
  assert.equal(relayFetches, 0, "relay mode must not fetch KuCoin token from the browser");
  relayController.stop();
  process.stdout.write("Real-time stream protocol/fail-closed tests: OK\n");
})().catch(error => { console.error(error); process.exitCode = 1; });
