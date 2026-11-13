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
  assert.deepEqual(W.horizonGroups(undefined),[{method:'méthode non indiquée',count:null}]);
  assert.deepEqual(W.horizonGroups({count:2,rsi_method:'wilder',by_rsi_method:{wilder:{count:2},legacy:{count:1}}}),[{method:'wilder',count:2},{method:'legacy',count:1}]);
});
test('le graphique masque les bougies de provenance ou de clôture incohérente', () => {
  const W=widgets(), frame={bars:[{t:1},{t:2}]};
  assert.equal(typeof W.chartBars,'function');
  assert.deepEqual(W.chartBars(frame,'Clôtures incohérentes'),[]);
  assert.deepEqual(W.chartBars(frame,'Provenance incohérente'),[]);
  assert.equal(W.chartBars(frame,'Capture périmée').length,2);
});
