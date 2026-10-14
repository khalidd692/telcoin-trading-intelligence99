"use strict";
const assert=require("node:assert/strict");
const rt=require("../site/realtime.js");
function vi(v){let n=BigInt(v),o=[];while(n>127n){o.push(Number(n&127n)|128);n>>=7n;}o.push(Number(n));return o;}
function fb(f,x){const b=typeof x==="string"?Array.from(Buffer.from(x)):x;return [...vi((f<<3)|2),...vi(b.length),...b];}
function fv(f,x){return [...vi(f<<3),...vi(x)];}
function deal(price,time){const item=[...fb(1,price),...fb(2,"12.5"),...fv(3,1),...fv(4,time)],d=[...fb(1,item),...fb(2,"deals")];return new Uint8Array([...fb(1,"spot@public.aggre.deals.v3.api.pb@100ms@TELUSDT"),...fb(314,d),...fb(3,"TELUSDT"),...fv(6,time)]);}
function book(bid,ask,time){const b=[...fb(1,bid),...fb(2,"4"),...fb(3,ask),...fb(4,"5")];return new Uint8Array([...fb(1,"spot@public.aggre.bookTicker.v3.api.pb@100ms@TELUSDT"),...fb(315,b),...fb(3,"TELUSDT"),...fv(6,time)]);}
const now=Date.now(),src=(last,bid,ask,t,connected=true)=>({last,bid,ask,eventAt:t,bookEventAt:t,receivedAt:now,connected}),sources={mexc:src(.00123,.001229,.001231,now),kucoin:src(.001231,.00123,.001232,now)};
const trade=rt.decodeMexcFrame(deal("0.00123",now));assert.equal(trade.symbol,"TELUSDT");assert.equal(trade.trades[0].price,.00123);assert.equal(trade.trades[0].eventAt,now);
const b=rt.decodeMexcFrame(book("0.001229","0.001231",now));assert.equal(b.bookTicker.bid,.001229);assert.equal(b.bookTicker.ask,.001231);
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
assert.equal(rt.isOutOfOrder(100,99),true);assert.equal(rt.isOutOfOrder(100,100),false);assert.equal(rt.reconnectDelay(1),1000);assert.equal(rt.reconnectDelay(2),2000);assert.equal(rt.reconnectDelay(10),30000);
process.stdout.write("Real-time stream protocol/fail-closed tests: OK\n");
