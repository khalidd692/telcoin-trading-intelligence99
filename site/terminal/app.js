/* TEL99 terminal — static research snapshot + explicit public quote refresh. */
'use strict';
const T=window.TEL99, $=id=>document.getElementById(id), esc=T.escape, fmt=T.display;
const price=x=>fmt(x,6), pct=x=>T.finite(x)?`${x>=0?'+':''}${fmt(x,2)} %`:'—';
const date=t=>T.finite(t)?new Date(t*1000).toLocaleString('fr-FR',{timeZone:'UTC',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'—';
const hosted=location.hostname.endsWith('.chatgpt.site');
const money=x=>fmt(x,2)+' $';
const labels={breakout20:'Cassure 20',recovery30:'Reprise RSI30',divergence:'Divergence RSI',oversold:'Survente RSI',pullback:'Repli EMA20'};
let scenarioPlans=[];
let data,tf='4h',oscMode='rsi14',chart,osc,candles,vol,lines={},oscLine,liveQuote=null;
let rangeSync=false,quoteBusy=false,snapshotBusy=false,eurUsd=null,eurUsdFetched=0;
const S=window.TEL99SmartView;
const technicalCache=new WeakMap();
let renderedSmartFrame,renderedSmartAvailability;
let chartPriceLines=[], structureMarkers;
let technicalDetail=null;
let previousChartAvailability;
function withWeekly(snapshot){
 snapshot.frames['1W']=S.weekly(snapshot.frames['1D'],snapshot.as_of);
 return snapshot;
}
function scoreGauge(name,votes){
 const total=votes.buy+votes.sell+votes.neutral;
 const score=total?(votes.buy-votes.sell)/total:0;
 const verdict=!total?'Indisponible':score>=.5?'Achat fort':score>.1?'Acheter':score<=-.5?'Vente forte':score<-.1?'Vendre':'Neutre';
 const theta=Math.PI*(1-score)/2;
 const colors=['#ff5f78','#ad354d','#a2adbe','#3874e5','#73a8ff'];
 const point=deg=>[50+40*Math.cos(deg*Math.PI/180),49-40*Math.sin(deg*Math.PI/180)].join(' ');
 const arcs=colors.map((color,i)=>`<path d="M ${point(180-i*36-3)} A40 40 0 0 1 ${point(180-(i+1)*36+3)}" stroke="${color}"/>`).join('');
 return `<article class="smart-gauge"><b>${name}</b><svg viewBox="0 0 100 53" aria-hidden="true"><g fill="none" stroke-width="5" stroke-linecap="round">${arcs}</g>${total?`<line x1="50" y1="49" x2="${50+31*Math.cos(theta)}" y2="${49-31*Math.sin(theta)}" stroke="#e8effa" stroke-width="3" stroke-linecap="round"/>`:''}</svg><strong>${verdict}</strong><dl class="smart-votes"><div><dt>Acheter</dt><dd>${votes.buy}</dd></div><div><dt>Neutre</dt><dd>${votes.neutral}</dd></div><div><dt>Vendre</dt><dd>${votes.sell}</dd></div></dl></article>`;

}
function technicalTable(rows){
 const action={1:'Acheter',0:'Neutre','-1':'Vendre'};
 return '<div class="table-scroll smart-table"><table><thead><tr><th>Indicateur</th><th>Valeur</th><th>Signal</th></tr></thead><tbody>'+rows.map(r=>`<tr><td>${r.name}<small>${r.period}</small></td><td>${fmt(r.value,8)}${T.finite(r.extra)?' / '+fmt(r.extra,8):''}</td><td class="${r.vote===1?'positive':r.vote===-1?'negative':''}">${action[r.vote]??'Indisponible'}</td></tr>`).join('')+'</tbody></table></div>';
}
function renderSmart(frame,availability){
 const node=$('technical-widget');
 const levels=$('smart-structure'), profile=$('smart-profile');
 if(renderedSmartFrame===frame&&renderedSmartAvailability===availability)return;
 renderedSmartFrame=frame;renderedSmartAvailability=availability;
 if(availability!=='Disponible'){
  node.innerHTML='<p class="amber-text">DONNÉES INSUFFISANTES · '+esc(availability)+'</p><div class="smart-gauges">'+['Résumé','Oscillateurs','Moyennes mobiles'].map(name=>scoreGauge(name,{buy:0,sell:0,neutral:0})).join('')+'</div>';
  levels.textContent='Données insuffisantes pour des niveaux actuels.';
  profile.textContent='Profil indisponible pour cette unité.';
  return null;
 }
 if(!technicalCache.has(frame))technicalCache.set(frame,{technical:S.technical(frame,tf),levels:S.marketLevels(frame,tf)});
 const {technical:r,levels:m}=technicalCache.get(frame);
 const details=(id,name,body)=>`<section data-technical-panel="${id}" ${technicalDetail===id?'':'hidden'}><h3>${name}</h3>${body}</section>`;
 node.innerHTML=`<p>${esc(tf)} · clôture ${date(frame.quality.last_close)} UTC</p><div class="smart-gauges">${scoreGauge('Oscillateurs',r.counts)}${scoreGauge('Résumé',r.total)}${scoreGauge('Moyennes mobiles',r.averageCounts)}</div>`+
  '<div class="technical-menu" aria-label="Tableaux techniques">'+[['osc','Oscillateurs'],['ma','Moyennes'],['piv','Pivots'],['method','Méthode']].map(([key,label])=>`<button type="button" data-technical="${key}" aria-pressed="${technicalDetail===key}">${label}</button>`).join('')+'</div>'+
  details('osc','Oscillateurs · valeurs et votes',technicalTable(r.oscillators))+
  details('ma','Moyennes mobiles · valeurs et votes',technicalTable(r.averages))+
  details('piv','Pivots · classique, Fibonacci, Camarilla et Woodie',r.pivots.length?'<div class="table-scroll smart-pivot-table"><table><thead><tr><th>Niveau</th><th>Classique</th><th>Fibonacci</th><th>Camarilla</th><th>Woodie</th></tr></thead><tbody>'+r.pivots.map(row=>'<tr><td>'+row[0]+'</td>'+row.slice(1).map(v=>'<td>'+price(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>':'<p>Données insuffisantes.</p>')+
  details('method','Méthode des votes',`<p>Une voix par indicateur disponible. Le score est (achats − ventes) ÷ votes. Verdict neutre entre −0,10 et +0,10, fort à partir de ±0,50. Les moyennes votent selon la position de la clôture. MACD et stochastiques votent selon la comparaison à leur signal. Momentum, AO et Bull Bear Power votent selon leur signe. ADX ≥ 25 utilise la direction DMI. RSI et Ultimate votent aux seuils 30 / 70, CCI −100 / +100 et Williams −80 / −20. Les indicateurs repartent après chaque interruption. Les pivots utilisent la période précédente et, pour Woodie, l’ouverture de la période analysée. Les jauges sont descriptives.</p>`);
 levels.innerHTML=`<p>Structure des pivots confirmés · ${esc(m.trend??'indisponible')}. ${esc(m.breaks??'Aucune cassure du dernier pivot sur la dernière clôture.')}</p><dl><dt>Support pivot</dt><dd>${price(m.support)} $</dd><dt>Résistance pivot</dt><dd>${price(m.resistance)} $</dd><dt>FVG récents non comblés</dt><dd>${m.fvgs?.map(z=>price(z.low)+'–'+price(z.high)+' $ · '+z.side).join(' / ')||'Aucun détecté'}</dd><dt>Retracements sur fenêtre</dt><dd>${m.fib?.map(([k,v])=>fmt(k*100,1)+' % · '+price(v)).join(' / ')||'—'}</dd></dl><p class="footnote">Pivots à deux bougies de chaque côté. Les niveaux sont des repères de structure. Order blocks, liquidité réelle et classification BOS / CHoCH indisponibles.</p>`;
 const p=m.profile;
 profile.innerHTML=p?`<p>POC <b>${price(p.poc)} $</b> · VAH ${price(p.vah)} $ · VAL ${price(p.val)} $</p><div class="smart-profile" aria-hidden="true">${p.bins.map((v,i)=>`<i class="${i===p.peak?'poc':i>=p.lo&&i<=p.hi?'accepted':''}" style="width:${100*v/Math.max(...p.bins)}%"></i>`).reverse().join('')}</div><p class="footnote">Estimation sur ${p.n} bougies, 24 classes, 70 % du volume. Chaque volume est placé au prix typique HLC3 de sa bougie. La répartition des transactions par prix reste inconnue.</p>`:'<p>Volume insuffisant.</p>';
 return m;
}
function selectMarket(key){
 document.querySelectorAll('[data-market-panel]').forEach(panel=>{panel.hidden=panel.dataset.marketPanel!==key;});
 document.querySelectorAll('[data-market]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.market===key)));
 save('market-widget',key);
 if(key==='chart')resizeCharts();
}
function pref(key,fallback){try{return localStorage.getItem('tel99:'+key)??fallback;}catch{return fallback;}}
function save(key,v){try{localStorage.setItem('tel99:'+key,v);}catch{/* Privacy mode still usable. */}}
function download(name,obj){const a=document.createElement('a'),url=URL.createObjectURL(new Blob([JSON.stringify(obj,null,2)],{type:'application/json'}));a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function statusOf(frame){const now=Date.now()/1000,last=frame.quality.last_close,age=now-last,min=frame.interval==='1W'?1:50;return frame.ready&&T.finite(data.as_of)&&now>=data.as_of-60&&now-data.as_of<=900&&T.finite(last)&&age>=0&&age<=S.steps[frame.interval]+300?'Disponible':frame.quality.last_segment_bars<min?'Série trop courte':'Périmé';}
function rowClass(n){return T.finite(n)?n>=0?'positive':'negative':'';}
function view(name){if(!['market','lab','risk','data'].includes(name))name='market';document.querySelectorAll('.view').forEach(e=>e.classList.toggle('hidden',e.id!=='view-'+name));document.querySelectorAll('.nav').forEach(e=>e.classList.toggle('active',e.dataset.view===name));$('view-title').textContent={market:'Centre de marché',lab:'Laboratoire quantitatif',risk:'Simulateur de risque',data:'Données & preuves'}[name];history.replaceState(null,'','#'+name);if(name==='market'&&chart)resizeCharts();}
function renderTickers(){
 if(liveQuote&&!T.freshQuote(liveQuote))liveQuote=null;
 const f=data.frames['4h'],last=f.bars.at(-1),earlier=last&&f.bars.find(x=>x.t===last.t-86400),change=earlier?100*(last.c/earlier.c-1):null;
 const btc=data.context.btc4h,eth=data.context.eth4h;
 $('tickers').innerHTML=`<article class="ticker"><div class="label"><span>TEL / USD</span><span class="amber-text">KRAKEN</span></div><div class="value">${price(liveQuote?.price??last?.c)} <span style="font-size:12px">$</span></div><small>${liveQuote?'Cours public reçu '+date(liveQuote.received)+' UTC':'Clôture 4h · '+date(f.quality.last_close)+' UTC'}</small></article><article class="ticker"><div class="label"><span>VARIATION 24H</span><span>CLÔTURES</span></div><div class="value ${rowClass(change)}">${pct(change)}</div><small>Deux clôtures 4h espacées de 24h</small></article><article class="ticker"><div class="label"><span>BITCOIN / USD</span><span>4H</span></div><div class="value">${fmt(btc?.latest.close,0)} <span style="font-size:11px">$</span></div><small>Clôture ${date(btc?.quality.last_close)} UTC</small></article><article class="ticker"><div class="label"><span>ETHEREUM / USD</span><span>4H</span></div><div class="value">${fmt(eth?.latest.close,2)} <span style="font-size:11px">$</span></div><small>Clôture ${date(eth?.quality.last_close)} UTC</small></article>`;
}
function renderDecision(){
 const d=T.safeDecision(data),list=(arr,cls='')=>`<ul class="evidence ${cls}">${arr.map(t=>`<li>${esc(t)}</li>`).join('')}</ul>`;
 const current=d.status!=='DONNÉES INSUFFISANTES';
 $('decision').innerHTML=`<div class="eyebrow">${current?'LECTURE EXPÉRIMENTALE':'QUALITÉ DES DONNÉES'}</div><div class="decision-tag">${esc(d.status)}</div><p class="decision-caption">${current?'Convergence de facteurs, sans avantage statistique démontré.':'Analyse bloquée. Les éléments ci-dessous décrivent le snapshot historique.'}<br>Aucun ordre réel ou paper.</p><div class="list-heading">ÉLÉMENTS FAVORABLES</div>${list(d.proofs?.length?d.proofs:['Aucun facteur favorable suffisamment documenté.'])}<div class="list-heading">CONTRADICTIONS & LIMITES</div>${list([...(d.staleReasons||[]),...(d.contradictions||[])],'conflicts')}<div class="invalidation"><span>Seuil structurel observé</span><b>${price(d.invalidation)} $</b></div><p class="footnote" style="padding:10px 0 0">Plus bas des 20 barres précédentes. Ce niveau n’est pas un ordre stop.</p>`;
 // Conditional watch levels are not executable orders: confirmation and costs remain mandatory.
 const four=data.frames?.['4h']?.latest,day=data.frames?.['1D']?.latest;
 if(current&&statusOf(data.frames['4h'])==='Disponible'&&statusOf(data.frames['1D'])==='Disponible'&&four&&day&&T.finite(four.support20)&&T.finite(four.ema20)&&T.finite(day.ema20)){
  const watch=[['Repli sur support',four.support20,'Attendre une défense du support et un rebond confirmé en 15 min / 1h'],['Reprise 4h',four.ema20,'Attendre une clôture 4h au-dessus, puis un retest tenu'],['Reprise journalière',day.ema20,'Attendre une clôture 1D au-dessus et une confirmation']];
  $('decision').innerHTML+='<div class="list-heading">ZONES À SURVEILLER · PAS D’ORDRES ACTIFS</div><dl>'+watch.map(([name,level,condition])=>'<dt>'+esc(name)+'</dt><dd>'+price(level)+' $ · '+esc(condition)+'</dd>').join('')+'</dl><p class="footnote">Niveaux recalculés depuis le snapshot analytique. Avant tout ordre limite : nouvelle cotation, confirmation, spread, frais personnels, stop et risque net vérifiés. Aucun ordre créé.</p>';
 }
 renderScenarios();
 const missing=Object.values(data.frames).filter(f=>statusOf(f)!=='Disponible').map(f=>f.interval==='1D'?'1j':f.interval);
 $('freshness-banner').textContent=`Snapshot analytique : ${date(data.as_of)} UTC. ${missing.length?'Attention : '+missing.join(', ')+' indisponible ou périmé.':'Unités analysables à la clôture.'} ${liveQuote?'Le cours public reçu ne rafraîchit ni les indicateurs ni les signaux.':'Le bouton de cours interroge l’API publique Kraken, indépendamment de l’analyse.'}`;
}
function renderWidgets(){
 const f=data.frames[tf], l=f.latest, availability=statusOf(f);
 renderSmart(f,availability);
 const d=T.safeDecision(data),p=d.plan;
 if(d.status==='DONNÉES INSUFFISANTES') $('tradeplan-widget').innerHTML='<p class="amber-text">Données insuffisantes ou périmées : plan masqué. Aucun ordre.</p>';
 else if(!p||![p.entry,p.stop,p.target,p.rr_net].every(T.finite)) $('tradeplan-widget').innerHTML='<p class="amber-text">Aucun plan chiffré disponible pour ce snapshot. Aucun ordre.</p>';
 else $('tradeplan-widget').innerHTML=`<p>Lecture : ${esc(d.status)} · snapshot ${date(data.as_of)} UTC</p><dl><dt>Entrée indicative</dt><dd>${price(p.entry)} $</dd><dt>Stop théorique</dt><dd>${price(p.stop)} $</dd><dt>Objectif théorique</dt><dd>${price(p.target)} $</dd><dt>Rendement / risque net estimé</dt><dd>${fmt(p.rr_net,2)} R</dd><dt>Perte planifiée</dt><dd>${money(p.planned_risk_usd)}</dd><dt>Quantité</dt><dd>Non déterminée : frais personnels non vérifiés</dd><dt>Frais / slippage hypothétiques par côté</dt><dd>${fmt(100*p.fee_per_side,2)} % / ${fmt(100*p.slippage_per_side,2)} %</dd></dl><p class="footnote">Calcul indicatif pour 1 000 $. RR net minimum : 1,5. Frais Kraken personnels non vérifiés : aucune taille recommandée. Les coûts hypothétiques peuvent différer ; un gap peut dépasser la perte prévue. Aucune stratégie validée, aucun ordre.</p>`;
}
function renderFrames(){
 renderWidgets();
 $('timeframe-table').innerHTML=Object.values(data.frames).sort((a,b)=>S.steps[a.interval]-S.steps[b.interval]).map(f=>{const l=f.latest,q=f.quality;return `<tr><td>${esc(f.interval)}</td><td class="${statusOf(f)==='Disponible'?'positive':'amber-text'}">${statusOf(f)}</td><td>${esc(l.trend)}</td><td>${fmt(l.rsi14,1)}</td><td>${fmt(l.adx14,1)}</td><td>${fmt(l.volume_ratio,2)} ×</td><td>${date(q.last_close)}</td></tr>`;}).join('');
}
function renderFactors(){const f=data.frames[tf],l=f.latest,btc=data.context.btc4h?.correlation;
 $('factors').innerHTML=[['Structure · '+tf,l.trend??'INDISPONIBLE',!T.finite(l.ema50)?'EMA50 indisponible après la dernière interruption.':'EMA20 '+price(l.ema20)+' · EMA50 '+price(l.ema50),''],['Momentum · '+tf,fmt(l.rsi14,1),'RSI14 arithmétique · MACD '+(l.macd_improving?'en amélioration':'sans amélioration'),l.rsi14>50?'positive':'amber-text'],['Volatilité · '+tf,T.finite(l.atr14)?fmt(100*l.atr14/l.close,2)+' %':'—','ATR14 / clôture · ADX '+fmt(l.adx14,1),''],['Corrélation TEL / BTC',fmt(btc?.pearson,2),(btc?.n??0)+' rendements 4h alignés. Corrélation ≠ causalité.','']].map(([title,value,desc,cls])=>`<div class="factor"><div class="label">${esc(title)}</div><div class="metric ${cls}" style="${value.length>11?'font-size:17px':''}">${esc(value)}</div><p>${esc(desc)}</p></div>`).join('');
}
function setupCharts(){
 const L=window.LightweightCharts;
 if(!L){$('chart').innerHTML='<p class="load-error">Bibliothèque de graphiques indisponible. Les tableaux restent accessibles.</p>';return;}
 const common={layout:{background:{color:'#10151d'},textColor:'#7e8da3',fontFamily:'ui-monospace,monospace',fontSize:10,attributionLogo:true},grid:{vertLines:{color:'#1a2330'},horzLines:{color:'#1a2330'}},rightPriceScale:{borderColor:'#283343',minimumWidth:78},timeScale:{borderColor:'#283343',timeVisible:true,secondsVisible:false},crosshair:{mode:L.CrosshairMode.Normal,vertLine:{color:'#677b91',labelBackgroundColor:'#344458'},horzLine:{color:'#677b91',labelBackgroundColor:'#344458'}},handleScroll:{vertTouchDrag:false},localization:{locale:'fr-FR'}};
 chart=L.createChart($('chart'),{...common,width:$('chart').clientWidth,height:$('chart').clientHeight});
 candles=chart.addSeries(L.CandlestickSeries,{upColor:'#65cdb0',downColor:'#da7985',borderVisible:false,wickUpColor:'#65cdb0',wickDownColor:'#da7985',priceFormat:{type:'price',precision:6,minMove:.000001}});
 structureMarkers=L.createSeriesMarkers(candles,[]);
 chart.priceScale('right').applyOptions({scaleMargins:{top:.12,bottom:.23}});
 vol=chart.addSeries(L.HistogramSeries,{priceFormat:{type:'volume'},priceScaleId:'volume',lastValueVisible:false,priceLineVisible:false});vol.priceScale().applyOptions({scaleMargins:{top:.86,bottom:0}});
 for(const [key,color] of [['ema20','#e8ad62'],['ema50','#74a3ed'],['sma200','#b8a0eb'],['vwap_session','#54c4ba']])lines[key]=chart.addSeries(L.LineSeries,{color,lineWidth:1,lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false});
 osc=L.createChart($('osc-chart'),{...common,width:$('osc-chart').clientWidth,height:$('osc-chart').clientHeight,timeScale:{...common.timeScale,visible:false}});
 oscLine=osc.addSeries(L.LineSeries,{color:'#b8a0eb',lineWidth:1,priceLineVisible:false,priceFormat:{type:'price',precision:2,minMove:.01}});
 chart.timeScale().subscribeVisibleLogicalRangeChange(range=>{if(range&&!rangeSync){rangeSync=true;osc.timeScale().setVisibleLogicalRange(range);rangeSync=false;}});
 osc.timeScale().subscribeVisibleLogicalRangeChange(range=>{if(range&&!rangeSync){rangeSync=true;chart.timeScale().setVisibleLogicalRange(range);rangeSync=false;}});
 chart.subscribeCrosshairMove(p=>{const r=p.seriesData?.get(candles);if(r?.open)showOHLC(r);else showOHLC(data.frames[tf].bars.at(-1));});
 new ResizeObserver(resizeCharts).observe($('chart'));
}
function resizeCharts(){if(!chart||!$('chart').clientWidth)return;chart.resize($('chart').clientWidth,$('chart').clientHeight);osc.resize($('osc-chart').clientWidth,$('osc-chart').clientHeight);}
function showOHLC(r){if(!r){$('ohlc').textContent='Aucune bougie disponible pour cette unité.';return;}$('ohlc').innerHTML=`O <b>${price(r.o??r.open)}</b> &nbsp; H <b>${price(r.h??r.high)}</b> &nbsp; L <b>${price(r.l??r.low)}</b> &nbsp; C <b>${price(r.c??r.close)}</b>`;}
function renderChart(){renderWidgets();const f=data.frames[tf];previousChartAvailability=statusOf(f);$('chart-meta').textContent=f.quality.valid_bars.toLocaleString('fr-FR')+' bougies · '+statusOf(f);showOHLC(f.bars.at(-1));renderFactors();
 document.querySelectorAll('[data-tf]').forEach(b=>{b.classList.toggle('selected',b.dataset.tf===tf);b.setAttribute('aria-pressed',String(b.dataset.tf===tf));});
 if(!chart)return;
 // Whitespace creates visible time gaps; no artificial OHLC points.
 const cs=[],vs=[];let previous=null;
 for(const r of f.bars){if(previous!==null&&r.t-previous>S.steps[tf]){cs.push({time:previous+S.steps[tf]});vs.push({time:previous+S.steps[tf]});}cs.push({time:r.t,open:r.o,high:r.h,low:r.l,close:r.c});vs.push({time:r.t,value:r.v,color:r.c>=r.o?'#234e46':'#4c2c38'});previous=r.t;}
 candles.setData(cs);vol.setData(vs);
 for(const line of chartPriceLines)candles.removePriceLine(line);
 chartPriceLines=[];
 const marketStructure=statusOf(f)==='Disponible'?technicalCache.get(f).levels:null;
 structureMarkers?.setMarkers($('smart-pivots').checked?(marketStructure?.pivots??[]).map(p=>({
  time:p.time,position:p.side==='high'?'aboveBar':'belowBar',shape:'circle',size:.45,text:p.label,color:p.side==='high'?'#f28b9a':'#54c4ba'
 })):[]);
 if($('smart-levels').checked&&statusOf(f)==='Disponible'){
  const m=marketStructure;
  const levels=[[m.support,'Support','#54c4ba'],[m.resistance,'Résistance','#e96883'],[m.profile?.poc,'POC','#e8ad62'],...(m.fib??[]).map(([k,v])=>[v,'Fib '+fmt(k*100,1)+' %','#64748b']),...(m.fvgs??[]).flatMap(z=>[[z.low,'FVG','#8a6bb0'],[z.high,'','#8a6bb0']])];
  chartPriceLines=levels.filter(([p])=>T.finite(p)).map(([price,title,color])=>candles.createPriceLine({price,title,color,lineWidth:1,lineStyle:2,axisLabelVisible:!!title}));
 }

 $('vwap_session').disabled=S.steps[tf]>=86400;
 for(const key of Object.keys(lines)){lines[key].setData(T.chartSeries(f.series,S.steps[tf],key));lines[key].applyOptions({visible:$(key).checked&&!$(key).disabled});}
 oscLine.setData(T.chartSeries(f.series,S.steps[tf],oscMode));
 oscLine.applyOptions({color:oscMode==='rsi14'?'#b8a0eb':'#74a3ed',priceFormat:{type:'price',precision:oscMode==='rsi14'?2:7,minMove:oscMode==='rsi14'?.01:.0000001}});
 $('osc-value').textContent=fmt(f.latest[oscMode],oscMode==='rsi14'?2:7);
 if(!f.bars.length)return;
 const count=$('chart-window').value;if(count==='all')chart.timeScale().fitContent();else chart.timeScale().setVisibleLogicalRange({from:Math.max(0,cs.length-Number(count)),to:cs.length+3});
}
function renderLab(){const f=data.lab.frozen;
 $('lab-summary').innerHTML=`<div class="summary-card"><span>Stratégies validées</span><b class="amber-text">0</b><small>Les preuves priment</small></div><div class="summary-card"><span>Candidats primaires</span><b>${f.candidates_total}</b><small>Tous rejetés par RR</small></div><div class="summary-card"><span>Études prédictives</span><b>${data.lab.events.length}</b><small>Résultats conservés</small></div>`;
 $('frozen-results').innerHTML=`<div class="table-scroll"><table><thead><tr><th>Phase exposée</th><th>Candidats</th><th>Rejets RR</th><th>Trades</th><th>Équité</th></tr></thead><tbody>${Object.entries(f.phase_diagnostics).map(([name,v])=>`<tr><td>${esc(name)}</td><td>${v.candidates}</td><td>${v.statuses['rejet:rr_inferieur_au_minimum']??0}</td><td>${f.results.central[name].n}</td><td>${money(v.ending_equity)}</td></tr>`).join('')}</tbody></table></div><p class="footnote">RR maximal : ${fmt(f.rr_gross_max,4)} · Seuil : 1,51 · ${f.n_bars} bougies retenues. Capital inchangé faute de position ; expectancy et profit factor non calculables.</p>`;
 renderExperiments();renderEvents();
}
function renderExperiments(){const cost=$('cost-scenario').value;let rows=[],trades=[];
 for(const [family,folds] of Object.entries(data.lab.experiments.families))folds.forEach((f,i)=>{const r=f.costs[cost];rows.push(`<tr><td>${labels[family]} · F${i+1}<br><small class="muted">${esc(f.start.slice(0,10))} → ${esc(f.end_exclusive.slice(0,10))}</small></td><td>${r.n}</td><td class="${rowClass(r.ending_equity-1000)}">${money(r.ending_equity)}</td><td class="${rowClass(r.expectancy_R)}">${fmt(r.expectancy_R,3)}</td><td>${fmt(r.profit_factor,2)}</td><td>${T.finite(r.max_drawdown_pct)?fmt(r.max_drawdown_pct,2)+' %':'—'}</td><td class="${rowClass(r.buy_hold_return_pct)}">${pct(r.buy_hold_return_pct)}</td></tr>`);for(const t of r.trades)trades.push(`<tr><td>${labels[family]} · F${i+1}</td><td>${esc(t.entry_ts.slice(0,16).replace('T',' '))}</td><td>${esc(t.exit_ts.slice(0,16).replace('T',' '))}</td><td>${esc(t.exit_reason)}</td><td class="${rowClass(t.r_multiple)}">${fmt(t.r_multiple,3)}</td><td class="${rowClass(t.pnl_usd)}">${money(t.pnl_usd)}</td></tr>`);});
 $('experiment-table').innerHTML=rows.join('');$('trade-table').innerHTML=trades.join('')||'<tr><td colspan="6">Aucun trade simulé.</td></tr>';
}
function renderEvents(){const tfFilter=$('event-tf').value,fam=$('event-family').value;
 $('events-table').innerHTML=data.lab.events.filter(r=>(tfFilter==='all'||r.timeframe===tfFilter)&&(fam==='all'||r.hypothesis===fam)).map(r=>`<tr><td>${labels[r.hypothesis]}</td><td>${r.timeframe}</td><td>${r.effective_horizon_hours} h${r.effective_horizon_hours!==r.horizon_hours?` <span class="amber-text">(demandé : ${r.horizon_hours}h)</span>`:''}</td><td>${r.n}</td><td class="${rowClass(r.mean_return_pct)}">${pct(r.mean_return_pct)}</td><td>${pct(r.mean_excess_pct)}</td><td>${r.inference.p===null?'N/A · effectif faible':fmt(r.inference.holm_p,3)}</td></tr>`).join('');
}
function renderQuality(){
 $('quality-table').innerHTML=Object.values(data.frames).map(f=>{const q=f.quality;return `<tr><td>${f.interval}</td><td>${(q.source_rows??q.valid_bars)}</td><td>${q.valid_bars}</td><td class="amber-text">${q.excluded_rows}</td><td>${q.missing_bars}</td><td>${q.segments}</td><td class="${q.last_segment_bars<50?'amber-text':'positive'}">${q.last_segment_bars} bougies</td></tr>`;}).join('');
 const entries=[['Marché',data.market],['Fournisseur',data.source],['Capture UTC',data.captured_at],['Fichier source',data.source_path],['SHA-256 source',data.source_sha256],['Protocole expérimental',data.lab.experiments.protocol_sha256],['Exécution','Aucun ordre réel ou paper']];
 $('provenance').innerHTML=entries.map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
 $('limits').innerHTML=[...data.limits,'BTC et ETH sont des cotations de contexte. Carnet L2 et flux institutionnels live indisponibles.'].map(x=>`<li>${esc(x)}</li>`).join('');
 $('quarantine').textContent=JSON.stringify(Object.fromEntries(Object.entries(data.frames).map(([tf,f])=>[tf,{reasons:f.quality.reasons,rows:f.excluded}])),null,2);
}
async function refreshEurUsd(){
 try{
  const response=await fetch(hosted?'/api/fx':'https://api.frankfurter.dev/v1/latest?base=EUR&symbols=USD',{cache:'no-store',signal:AbortSignal.timeout(12000)});
  if(!response.ok)throw Error('FX HTTP '+response.status);
  const fx=T.parseFx(await response.json());if(!fx)throw Error('Taux FX périmé');
  const {rate,date:dateStr}=fx;
  eurUsd=rate;eurUsdFetched=Date.now();$('eur-usd').value=fmt(rate,5)+' USD (référence '+dateStr+')';
 }catch(e){eurUsd=null;$('eur-usd').value='Indisponible';}
 renderRisk();
}
function renderEuroBudget(){
 const node=$('budget-eur-result');if(!node)return;
 const eur=Number($('budget-eur').value),p=T.freshQuote(liveQuote)?liveQuote.price:null;
 if(!T.finite(eur)||eur<=0){node.textContent='Saisissez un montant positif en euros.';return;}
 if(!T.finite(eurUsd)||Date.now()-eurUsdFetched>86400000){node.textContent='Conversion EUR/USD indisponible ou périmée : estimation bloquée.';return;}
 const usd=eur*eurUsd;
 if(!T.finite(p)||p<=0){node.textContent='≈ '+fmt(usd,2)+' USD. Cours Kraken récent indisponible : quantité bloquée. Le dernier snapshot analytique ne remplace pas une cotation actuelle.';return;}
 const fee=Number($('fee').value)/100,slip=Number($('slip').value)/100;
 if(!T.finite(fee)||!T.finite(slip)||fee<0||slip<0||fee>=.1||slip>=.1){node.textContent='Coûts hypothétiques invalides : quantité bloquée.';return;}
 const gross=usd/p,net=usd/(p*(1+slip)*(1+fee));
 node.textContent=fmt(eur,2)+' € ≈ '+fmt(usd,2)+' USD · '+fmt(gross,0)+' TEL bruts · environ '+fmt(net,0)+' TEL après frais/slippage HYPOTHÉTIQUES ('+fmt(fee*100,2)+' % + '+fmt(slip*100,2)+' % par côté). Spread réel et frais Kraken personnels non vérifiés : estimation NON EXPLOITABLE, aucun ordre.';
}
function renderRisk(){renderEuroBudget();if(data)renderScenarios();const vals=['capital','entry','stop','target','fee','slip'].map(id=>$(id).value===''?NaN:Number($(id).value));vals[4]/=100;vals[5]/=100;const r=T.riskPlan(...vals);
 if(r.error){$('risk-output').innerHTML=`<div class="eyebrow">SIMULATION BLOQUÉE</div><h3>${esc(r.error)}</h3>`;return;}
 $('risk-output').innerHTML=`<div class="eyebrow">${r.admissible?'SCÉNARIO TECHNIQUEMENT ADMISSIBLE':'SCÉNARIO NON ADMISSIBLE'}</div><div class="big">${fmt(r.qty,2)} <span style="font-size:14px">TEL</span></div><p class="muted">Quantité théorique · Aucun ordre créé</p><dl><dt>Risque planifié</dt><dd>${money(r.risk)} / ${money(r.budget)}</dd><dt>Capital nécessaire</dt><dd>${money(r.cash)}</dd><dt>Rendement / risque brut</dt><dd class="${r.rr>=1.51?'positive':'negative'}">${fmt(r.rr,2)} R</dd><dt>Rendement / risque net</dt><dd>${fmt(r.rrNet,2)} R</dd><dt>Gain net si cible atteinte</dt><dd>${money(r.reward)}</dd></dl><p class="footnote" style="padding:24px 0 0">${r.admissible?'L’admissibilité mathématique ne valide pas la stratégie.':'RR net requis : au moins 1,5 après frais et slippage.'} Frais et slippage inclus. Un gap sous le stop peut dépasser ce budget. Quantité affichée arrondie ; calcul conservé à pleine précision.</p>`;
}
async function refreshSnapshot(){
 if(snapshotBusy||document.hidden)return;snapshotBusy=true;
 try{
  const feeds=hosted?['/data.json']:['data.json?t='+Date.now(),'https://raw.githubusercontent.com/khalidd692/telcoin-trading-intelligence99/tel99-live-data/site/terminal/data.json?t='+Date.now()];
  let next=null,lastErr=null;
  for(const feed of feeds){
   try{
    const r=await fetch(feed,{cache:'no-store',signal:AbortSignal.timeout(12000)});
    if(!r.ok)throw Error('Snapshot HTTP '+r.status);
    const candidate=await r.json();
    if(T.acceptSnapshot(data,candidate)){next=candidate;break;}
   }catch(e){lastErr=e;}
  }
  if(!next){if(lastErr)console.warn('TEL99: actualisation analytique indisponible; snapshot existant conservé',lastErr.message);return;}
  data=withWeekly(next);renderTickers();renderDecision();renderFrames();renderChart();renderLab();renderQuality();renderRisk();
 }catch(e){console.warn('TEL99: actualisation analytique indisponible; snapshot existant conservé',e.message);
 }finally{snapshotBusy=false;}
}
async function refreshQuote(){if(quoteBusy)return;quoteBusy=true;const b=$('refresh-quote');b.disabled=true;b.textContent='Connexion à Kraken…';
 try{const r=await fetch(hosted?'/api/quote':'https://api.kraken.com/0/public/Ticker?pair=TELUSD',{cache:'no-store',signal:AbortSignal.timeout(12000)});if(!r.ok)throw Error('HTTP '+r.status);const j=await r.json();if(j.error?.length)throw Error(j.error.join(', '));const p=T.parseTelTicker(j);if(p===null)throw Error('Paire Kraken ou cours invalide');liveQuote={price:p,bid:Number(Object.values(j.result)[0].b?.[0]),ask:Number(Object.values(j.result)[0].a?.[0]),received:Date.now()/1000};renderTickers();renderDecision();renderRisk();b.textContent='✓ Cours public reçu';
 }catch(e){liveQuote=null;renderTickers();renderDecision();renderRisk();b.textContent='↻ Réessayer le cours';$('freshness-banner').textContent='Cours public indisponible : '+e.message+'. Le snapshot historique reste affiché et conserve son horodatage.';}finally{quoteBusy=false;b.disabled=false;}}
function renderScenarios(){
 const node=$('conditional-scenarios');if(!node||!data)return;
 const fxOk=T.finite(eurUsd)&&Date.now()-eurUsdFetched<86400000;
 const budget=Number($('budget-eur').value),capital=Number($('capital').value),fee=Number($('fee').value)/100,slip=Number($('slip').value)/100;
 const options={quote:liveQuote,capital:fxOk?Math.min(capital,1000*eurUsd):capital,budgetUsd:fxOk?Math.min(budget,1000)*eurUsd:NaN,fee,slip,tv:data.independent_verification};
 scenarioPlans=window.TEL99Scenarios.generate(data,options);
 const a=window.TEL99Scenarios.allocate(scenarioPlans,options.capital,options.budgetUsd);
 const ready=scenarioPlans.filter(p=>p.status==='PRÊT À ÉVALUER');
 const d=T.safeDecision(data);
 const stale=d.status==='DONNÉES INSUFFISANTES'||['15m','1h','4h','1D'].some(key=>statusOf(data.frames[key])!=='Disponible');
 const plans=scenarioPlans.filter(p=>[p.entry,p.stop,p.target].every(T.finite));
 const watch=ready[0]??plans.find(p=>p.id==='reversal')??plans[0];
 const status=stale?'DONNÉES INSUFFISANTES':ready.length?'ACHETER · PLAN À VÉRIFIER':watch&&/repli|pullback|support/i.test(watch.id)?'ATTENDRE REPLI':watch?'ATTENDRE CONFIRMATION':'NE PAS ACHETER';
 const reason=stale?'La capture analytique ou une unité requise est indisponible.':watch?.reasons?.[0]??watch?.condition??'Aucun scénario chiffré admissible.';
 const quote=liveQuote&&T.freshQuote(liveQuote)?liveQuote:null;
 const f=data.frames['4h'];
 const note=quote?'Kraken · reçu '+date(quote.received)+' UTC':'Dernière clôture 4 h · '+date(f.quality.last_close)+' UTC';
 $('decision-quick').innerHTML=`<div class="decision-main"><b>${esc(status)}</b><strong>TEL/USD · ${price(quote?.price??f.latest.close)} $</strong></div><div class="decision-meta">${esc(note)} · Analyse ${date(data.as_of)} UTC</div><div class="decision-prices"><span>Entrée ${price(stale?null:watch?.entry)} $</span><span>Invalidation ${price(stale?null:watch?.stop)} $</span><span>Objectif ${price(stale?null:watch?.target)} $</span></div><span>${stale?'Confiance indéterminée':'Confiance limitée · avantage statistique non démontré'}. ${esc(reason)}</span>`;
 const expanded=new Set([...node.querySelectorAll('details[data-scenario][open]')].map(x=>x.dataset.scenario));
 node.innerHTML='<p><b>'+ (ready.length?'Scénario prêt à une vérification humaine.':'Aucun scénario prêt à évaluer.')+'</b> Frais personnels et profondeur non vérifiés. Les niveaux restent des hypothèses ; aucune stratégie validée.</p>'+scenarioPlans.map((p,i)=>`<details class="scenario-card" data-scenario="${p.id}" ${expanded.has(p.id)?'open':''}><summary><b>${esc(p.name)}</b><span class="chip">${esc(p.status)}</span></summary><p>${esc(p.condition)}</p><dl><dt>Entrée limite envisagée</dt><dd>${price(p.entry)} $</dd><dt>Stop théorique</dt><dd>${price(p.stop)} $</dd><dt>Objectif observé</dt><dd>${price(p.target)} $</dd><dt>RR net hypothétique</dt><dd>${fmt(p.rrNet,2)} / minimum 1,5</dd><dt>Quantité individuelle indicative</dt><dd>${fmt(p.qty,2)} TEL</dd><dt>Cash / risque planifié</dt><dd>${money(p.cash)} / ${money(p.risk)}</dd><dt>Frais d’entrée hypothétiques</dt><dd>${money(p.feeEstimate)}</dd><dt>Calcul UTC</dt><dd>${date(p.calculatedAt)}</dd></dl><p>${esc(p.invalidation)}</p><p class="amber-text">${p.reasons.map(esc).join(' · ')}</p><button class="button" data-copy-scenario="${i}" ${p.status==='PRÊT À ÉVALUER'?'':'disabled'}>Copier les paramètres vérifiés</button></details>`).join('')+
 '<details class="plan-method" '+(node.querySelector('.plan-method')?.open?'open':'')+'><summary>Budget, frais et dimensionnement</summary><p>Budget sélectionné : '+fmt(budget,0)+' € · '+esc($('eur-usd').value)+'.</p><p>Hypothèses par côté : frais '+fmt(fee*100,2)+' %, slippage hors spread '+fmt(slip*100,2)+' %. Demi-spread ajouté à chaque côté dans le RR. Spread observé : '+fmt(T.finite(scenarioPlans[0]?.spread)?scenarioPlans[0].spread*100:null,2)+' %. Coûts de conversion EUR non inclus.</p>'+
 '<p><b>Si plusieurs scénarios sont retenus :</b> enveloppe agrégée plafonnée à '+money(options.capital*.0025)+' de perte planifiée et '+money(options.budgetUsd)+' de cash. '+(a.valid&&a.items.length?a.items.map(p=>esc(p.id)+': '+fmt(p.qty,2)+' TEL').join(' · ')+' ; risque total '+money(a.risk)+'.':'Aucune allocation calculable.')+' Ces tailles alternatives sont calculées sans accès aux positions ouvertes. Vérifier la perte latente cumulée sur le capital de travail avant toute utilisation.</p>'+
 '<div class="table-scroll"><table><thead><tr><th>Budget</th><th>USD</th><th>TEL au support*</th><th>Frais entrée*</th></tr></thead><tbody>'+[300,400,500].map(e=>{const p=window.TEL99Scenarios.generate(data,{...options,budgetUsd:fxOk?e*eurUsd:NaN})[0];return '<tr><td>'+e+' €</td><td>'+fmt(fxOk?e*eurUsd:null,2)+'</td><td>'+fmt(p.qty,2)+'</td><td>'+money(p.feeEstimate)+'</td></tr>';}).join('')+'</tbody></table></div><p class="footnote">* Dimensionnement hypothétique limité par le risque, pas investissement de tout le budget. Un stop ne garantit pas le prix de sortie ; une limite sous le marché ne protège pas d’une chute. Réserve long terme de 2 000 000 TEL exclue.</p></details>';
}
function bind(){
 document.querySelectorAll('[data-eur-budget]').forEach(b=>b.addEventListener('click',()=>{$('budget-eur').value=b.dataset.eurBudget;renderRisk();}));
 $('show-decision').addEventListener('click',()=>{$('decision-quick').focus({preventScroll:true});$('decision-quick').scrollIntoView({block:'start'});});
 $('technical-widget').addEventListener('click',event=>{
  const button=event.target.closest('[data-technical]');
  if(!button)return;
  technicalDetail=technicalDetail===button.dataset.technical?null:button.dataset.technical;
  $('technical-widget').querySelectorAll('[data-technical]').forEach(x=>x.setAttribute('aria-pressed',String(x.dataset.technical===technicalDetail)));
  $('technical-widget').querySelectorAll('[data-technical-panel]').forEach(x=>{x.hidden=x.dataset.technicalPanel!==technicalDetail;});
 });
 $('conditional-scenarios').addEventListener('click',async e=>{const b=e.target.closest('[data-copy-scenario]');if(!b)return;try{const index=Number(b.dataset.copyScenario);renderScenarios();const text=window.TEL99Scenarios.copyText(scenarioPlans[index]);await navigator.clipboard.writeText(text);$('copy-result').textContent='Paramètres copiés. Aucun ordre envoyé.';}catch(err){$('copy-result').textContent=err.message;}});

 document.querySelectorAll('[data-widget]').forEach(input=>{const key=input.dataset.widget,panel=document.querySelector('[data-widget-panel="'+key+'"]');input.checked=pref('widget:'+key,'true')==='true';const apply=()=>{panel.classList.toggle('hidden',!input.checked);save('widget:'+key,String(input.checked));if(key==='chart'&&input.checked)resizeCharts();};apply();input.addEventListener('change',apply);});
 document.querySelectorAll('[data-view]').forEach(e=>e.addEventListener('click',()=>view(e.dataset.view)));
 document.querySelectorAll('[data-tf]').forEach(e=>e.addEventListener('click',()=>{tf=e.dataset.tf;save('tf',tf);renderChart();}));
 for(const id of ['smart-levels','smart-pivots'])$(id).addEventListener('change',renderChart);
 document.querySelectorAll('[data-market]').forEach(b=>b.addEventListener('click',()=>selectMarket(b.dataset.market)));
 selectMarket(['chart','technical','levels','plans','context'].includes(pref('market-widget','chart'))?pref('market-widget','chart'):'chart');
 for(const key of ['ema20','ema50','sma200','vwap_session']){$(key).checked=pref(key,['sma200','vwap_session'].includes(key)?'false':'true')==='true';$(key).addEventListener('change',()=>{save(key,$(key).checked);renderChart();});}
 $('chart-window').addEventListener('change',renderChart);
 for(const [id,key] of [['rsi-mode','rsi14'],['macd-mode','macd_hist']])$(id).addEventListener('click',()=>{oscMode=key;$('rsi-mode').classList.toggle('selected',key==='rsi14');$('macd-mode').classList.toggle('selected',key==='macd_hist');renderChart();});
 $('cost-scenario').addEventListener('change',renderExperiments);$('event-tf').addEventListener('change',renderEvents);$('event-family').addEventListener('change',renderEvents);
 $('risk-form').addEventListener('submit',e=>e.preventDefault());$('risk-form').addEventListener('input',renderRisk);
 $('refresh-quote').addEventListener('click',refreshQuote);$('export-data').addEventListener('click',()=>download('TEL99_snapshot.json',data));$('export-lab').addEventListener('click',()=>download('TEL99_laboratoire.json',data.lab));
}
async function start(){try{
 const r=await fetch('data.json?t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('Snapshot HTTP '+r.status);data=await r.json();if(data.schema_version!==1||data.market!=='KRAKEN:TELUSD')throw Error('Schéma ou marché incorrect');
 data=withWeekly(data);
 tf=pref('tf','4h');if(!data.frames[tf])tf='4h';bind();setupCharts();renderTickers();renderDecision();renderFrames();renderChart();renderLab();renderQuality();
 const l=data.frames['4h'].latest,d=T.safeDecision(data),p=d.status==='DONNÉES INSUFFISANTES'?null:d.plan;$('entry').value=p?(l.close??''):'';$('stop').value=p?.stop??'';$('target').value=p?.target??'';renderRisk();refreshEurUsd();
 $('loading').classList.add('hidden');view(location.hash.slice(1)||'market');
 setInterval(()=>{renderTickers();renderDecision();renderFrames();if(previousChartAvailability!==statusOf(data.frames[tf]))renderChart();$('clock').textContent=new Date().toLocaleTimeString('fr-FR',{timeZone:'UTC'})+' UTC';},15000);
 // Public quote only: never relabel a static analytical snapshot as live.
 refreshQuote();
 setInterval(()=>{if(!document.hidden)refreshQuote();},60000);
 // Only accept a newer same-origin analytical snapshot with unchanged frozen research.
 refreshSnapshot();
 setInterval(refreshSnapshot,60000);
  setInterval(()=>{if(!document.hidden)refreshEurUsd();},3600000);
 $('clock').textContent=new Date().toLocaleTimeString('fr-FR',{timeZone:'UTC'})+' UTC';
 }catch(e){$('loading').classList.add('load-error');$('loading').textContent='Terminal indisponible : '+e.message+'. Servez le dossier avec HTTP et vérifiez data.json.';}}
start();
