const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const modulePath = path.join(__dirname, '../site/terminal/smartwidgets.js');
function widgets() {
  assert.ok(fs.existsSync(modulePath), 'Le module des widgets doit exister');
  return require(modulePath);
}
const book = {error:[], result:{TELUSD:{
  bids:[['0.99','100',1],['0.98','100',1]],
  asks:[['1.01','100',1],['1.02','100',1]]
}}};
test('le carnet accepte uniquement la paire attendue et calcule son spread et sa profondeur', () => {
  const W = widgets(), out = W.readBook(book);
  assert.equal(out.bid, 0.99);
  assert.equal(out.ask, 1.01);
  assert.ok(Math.abs(out.spreadPct - 2) < 1e-9);
  assert.equal(out.bidDepth, 197);
  assert.equal(out.askDepth, 203);
  assert.equal(W.readBook({...book,result:{OTHER:book.result.TELUSD}}), null);
  assert.equal(W.readBook({...book,result:{TELUSD:{...book.result.TELUSD,asks:[['0.98','1',1]]}}}), null);
});
test('le glissement acheteur reste indisponible si la profondeur ne couvre pas le montant', () => {
  const W = widgets(), out = W.readBook(book);
  const estimate = W.buyImpact(out, 150, 1);
  assert.ok(estimate && estimate.average > out.ask && estimate.slippagePct > 0);
  assert.equal(W.buyImpact(out, 204, 1), null);
  assert.equal(W.buyImpact(out, 100, null), null);
});
test('les montants du suivi personnel restent séparés entre euros et dollars', () => {
  const W = widgets();
  assert.deepEqual(W.accumulation(1000, 100, 0.12, 1.2), {averageEur:0.1,valueUsd:120,valueEur:100,pnlEur:0});
  assert.equal(W.accumulation(-1, 100, 0.12, 1.2), null);
  assert.equal(W.accumulation(1000, 100, 0.12, null).valueEur, null);
});
test('la disposition conserve seulement les widgets connus et ajoute les nouveaux sans doublon', () => {
  const W = widgets();
  assert.deepEqual(W.layout(['b','b','inconnu','a'], ['a','b','c']), ['b','a','c']);
  assert.deepEqual(W.layout(null, ['a','b']), ['a','b']);
});
test('la distance d’un niveau est rapportée à la clôture observée', () => {
  const W = widgets();
  assert.equal(typeof W.distancePct,'function');
  assert.equal(W.distancePct(105,100),5);
  assert.equal(W.distancePct(95,100),-5);
  assert.equal(W.distancePct(95,0),null);
});
test('la fraîcheur multi-unités détecte l’expiration du 15 min même si le 4 h reste valide', () => {
  const W=widgets(), T=require('../site/terminal/core.js'), R=require('../site/terminal/radar.js');
  assert.equal(typeof W.gaugeFreshness,'function');
  assert.equal(typeof R.frameCheck,'function');
  assert.equal(typeof R.frameIntegrity,'function');
  const close=8640000, capture=close+700;
  const frames=Object.fromEntries(Object.entries(T.steps).map(([interval,step])=>[interval,{interval,symbol:'KRAKEN:TELUSD',ready:true,quality:{last_close:close,last_segment_bars:60},bars:Array.from({length:60},(_,i)=>({t:close-(60-i)*step,o:1,h:2,l:0.5,c:1,v:1}))}]));
  const before=W.gaugeFreshness(frames,capture,close+1100,R.frameCheck);
  const after=W.gaugeFreshness(frames,capture,close+1201,R.frameCheck);
  assert.equal(before['15m'],'Disponible');
  assert.equal(after['15m'],'Clôture périmée');
  assert.equal(after['4h'],'Disponible');
  assert.notDeepEqual(before,after);
  const bad={...frames,'15m':{...frames['15m'],bars:frames['15m'].bars.map((bar,i)=>i===59?{...bar,t:bar.t+900}:bar)}};
  assert.equal(W.gaugeFreshness(bad,capture,close+1100,R.frameCheck)['15m'],'Clôtures incohérentes');
  assert.equal(R.frameIntegrity(bad['15m'],'15m',capture),'Clôtures incohérentes');
});
test('un horizon absent reste indisponible et chaque méthode RSI apparaît une seule fois', () => {
  const W=widgets();
  assert.equal(typeof W.horizonGroups,'function');
  assert.deepEqual(W.horizonGroups(undefined),[{method:'méthode non indiquée',count:null,meanPct:null}]);
  assert.deepEqual(W.horizonGroups({count:2,mean_pct:1.25,rsi_method:'wilder',by_rsi_method:{wilder:{count:2,mean_pct:1.25},legacy:{count:1,mean_pct:-2}}}),[{method:'wilder',count:2,meanPct:1.25},{method:'legacy',count:1,meanPct:-2}]);
  assert.equal(W.horizonGroups({count:0,mean_pct:0})[0].meanPct,null);
  assert.equal(W.horizonGroups({count:1,mean_pct:'0.5'})[0].meanPct,null);
});
test('le graphique masque les bougies de provenance ou de clôture incohérente', () => {
  const W=widgets(), frame={bars:[{t:1},{t:2}]};
  assert.equal(typeof W.chartBars,'function');
  assert.deepEqual(W.chartBars(frame,'Clôtures incohérentes'),[]);
  assert.deepEqual(W.chartBars(frame,'Provenance incohérente'),[]);
  assert.equal(W.chartBars(frame,'Capture périmée').length,2);
});
test('le comparateur conserve la devise et la source de chaque paire Kraken', () => {
  const W=widgets();
  const ticker=(last,bid,ask,open,volume)=>({c:[String(last),'1'],b:[String(bid)],a:[String(ask)],o:String(open),v:['0',String(volume)]});
  const out=W.readMarketTickers({error:[],result:{TELUSD:ticker(1,0.99,1.01,0.8,100),TELEUR:ticker(0.9,0.89,0.91,0.8,200),XXBTZUSD:ticker(100,99,101,90,2),XETHZUSD:ticker(10,9.9,10.1,9,3)}});
  assert.equal(out.length,4);
  assert.equal(out[0].pair,'TEL/USD'); assert.equal(out[0].currency,'USD');
  assert.equal(out[1].pair,'TEL/EUR'); assert.equal(out[1].currency,'EUR');
  assert.equal(out[2].pair,'BTC/USD'); assert.equal(out[2].base,'BTC');
  assert.equal(out[0].volume,100); assert.ok(Math.abs(out[0].change-25)<1e-9);
  assert.ok(Math.abs(out[0].spread-2)<1e-9);
  const partial=W.readMarketTickers({error:[],result:{TELUSD:ticker(1,1.01,0.99,0,100)}});
  assert.equal(partial[0].price,1); assert.equal(partial[0].spread,null); assert.equal(partial[0].change,null);
  assert.equal(partial[1].price,null);
  assert.equal(W.readMarketTickers({error:['unknown pair'],result:{}}),null);
  const malformed=W.readMarketTickers({error:[],result:{TELUSD:{c:'12.34',b:'10',a:'19',o:true,v:[0,false]}}});
  assert.equal(malformed[0].price,null); assert.equal(malformed[0].spread,null);
  assert.equal(malformed[0].change,null); assert.equal(malformed[0].volume,null);
});
test('une cotation de comparaison future ou vieille de plus de deux minutes est refusée', () => {
  const W=widgets();
  assert.equal(W.marketFresh(1000,1120),true);
  assert.equal(W.marketFresh(1000,1121),false);
  assert.equal(W.marketFresh(1001,1000),false);
  assert.equal(W.marketFresh(0,1000),false);
});
