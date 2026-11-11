/* TEL99 terminal — static research snapshot + explicit public quote refresh. */
'use strict';
const T=window.TEL99, $=id=>document.getElementById(id), esc=T.escape, fmt=T.display;
const price=x=>fmt(x,6), pct=x=>T.finite(x)?`${x>=0?'+':''}${fmt(x,2)} %`:'—';
const date=t=>T.finite(t)?new Date(t*1000).toLocaleString('fr-FR',{timeZone:'UTC',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'—';
const money=x=>fmt(x,2)+' $';
const labels={breakout20:'Cassure 20',recovery30:'Reprise RSI30',divergence:'Divergence RSI',oversold:'Survente RSI',pullback:'Repli EMA20'};
let data,tf='4h',oscMode='rsi14',chart,osc,candles,vol,lines={},oscLine,liveQuote=null;
let rangeSync=false,quoteBusy=false,snapshotBusy=false;
function pref(key,fallback){try{return localStorage.getItem('tel99:'+key)??fallback;}catch{return fallback;}}
function save(key,v){try{localStorage.setItem('tel99:'+key,v);}catch{/* Privacy mode still usable. */}}
function download(name,obj){const a=document.createElement('a'),url=URL.createObjectURL(new Blob([JSON.stringify(obj,null,2)],{type:'application/json'}));a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function statusOf(frame){const last=frame.quality.last_close,age=Date.now()/1000-last;return frame.ready&&T.finite(data.as_of)&&Date.now()/1000-data.as_of<=900&&age>=0&&age<=T.steps[frame.interval]+300?'Disponible':frame.quality.last_segment_bars<50?'Série trop courte':'Périmé';}
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
 const missing=Object.values(data.frames).filter(f=>statusOf(f)!=='Disponible').map(f=>f.interval==='1D'?'1j':f.interval);
 $('freshness-banner').textContent=`Snapshot analytique : ${date(data.as_of)} UTC. ${missing.length?'Attention : '+missing.join(', ')+' indisponible ou périmé.':'Unités analysables à la clôture.'} ${liveQuote?'Le cours public reçu ne rafraîchit ni les indicateurs ni les signaux.':'Le bouton de cours interroge l’API publique Kraken, indépendamment de l’analyse.'}`;
}
function renderWidgets(){
 const f=data.frames[tf], l=f.latest, availability=statusOf(f);
 if(availability!=='Disponible') $('technical-widget').innerHTML=`<p class="amber-text">${esc(tf)} · ${esc(availability)} : indicateurs masqués jusqu’à réception d’un snapshot valide.</p>`;
 else $('technical-widget').innerHTML=`<p>${esc(tf)} · ${esc(availability)} · clôture ${date(f.quality.last_close)} UTC</p><dl><dt>Structure EMA20 / EMA50</dt><dd>${esc(l.trend)}</dd><dt>RSI 14</dt><dd>${fmt(l.rsi14,1)}</dd><dt>Histogramme MACD</dt><dd>${fmt(l.macd_hist,7)}</dd><dt>ADX 14</dt><dd>${fmt(l.adx14,1)}</dd><dt>Volume relatif</dt><dd>${fmt(l.volume_ratio,2)} ×</dd></dl><p class="footnote">Indicateurs descriptifs : aucune note ne représente une probabilité de réussite.</p>`;
 const d=T.safeDecision(data),p=d.plan;
 if(d.status==='DONNÉES INSUFFISANTES') $('tradeplan-widget').innerHTML='<p class="amber-text">Données insuffisantes ou périmées : plan masqué. Aucun ordre.</p>';
 else if(!p||![p.entry,p.stop,p.target,p.rr_net].every(T.finite)) $('tradeplan-widget').innerHTML='<p class="amber-text">Aucun plan chiffré disponible pour ce snapshot. Aucun ordre.</p>';
 else $('tradeplan-widget').innerHTML=`<p>Lecture : ${esc(d.status)} · snapshot ${date(data.as_of)} UTC</p><dl><dt>Entrée indicative</dt><dd>${price(p.entry)} $</dd><dt>Stop théorique</dt><dd>${price(p.stop)} $</dd><dt>Objectif théorique</dt><dd>${price(p.target)} $</dd><dt>Rendement / risque net estimé</dt><dd>${fmt(p.rr_net,2)} R</dd><dt>Perte planifiée</dt><dd>${money(p.planned_risk_usd)}</dd><dt>Quantité indicative</dt><dd>${fmt(p.quantity,2)} TEL</dd><dt>Frais / slippage hypothétiques par côté</dt><dd>${fmt(100*p.fee_per_side,2)} % / ${fmt(100*p.slippage_per_side,2)} %</dd></dl><p class="footnote">Calcul indicatif pour 1 000 $. RR net minimum : 1,5. Les frais réels et le slippage peuvent différer ; un gap peut dépasser la perte prévue. Aucune stratégie validée, aucun ordre.</p>`;
}
function renderFrames(){
 renderWidgets();
 $('timeframe-table').innerHTML=Object.values(data.frames).sort((a,b)=>T.steps[a.interval]-T.steps[b.interval]).map(f=>{const l=f.latest,q=f.quality;return `<tr><td>${esc(f.interval)}</td><td class="${statusOf(f)==='Disponible'?'positive':'amber-text'}">${statusOf(f)}</td><td>${esc(l.trend)}</td><td>${fmt(l.rsi14,1)}</td><td>${fmt(l.adx14,1)}</td><td>${fmt(l.volume_ratio,2)} ×</td><td>${date(q.last_close)}</td></tr>`;}).join('');
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
 chart.priceScale('right').applyOptions({scaleMargins:{top:.12,bottom:.23}});
 vol=chart.addSeries(L.HistogramSeries,{priceFormat:{type:'volume'},priceScaleId:'volume',lastValueVisible:false,priceLineVisible:false});vol.priceScale().applyOptions({scaleMargins:{top:.86,bottom:0}});
 for(const [key,color] of [['ema20','#e8ad62'],['ema50','#74a3ed'],['sma200','#b8a0eb']])lines[key]=chart.addSeries(L.LineSeries,{color,lineWidth:1,lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false});
 osc=L.createChart($('osc-chart'),{...common,width:$('osc-chart').clientWidth,height:$('osc-chart').clientHeight,timeScale:{...common.timeScale,visible:false}});
 oscLine=osc.addSeries(L.LineSeries,{color:'#b8a0eb',lineWidth:1,priceLineVisible:false,priceFormat:{type:'price',precision:2,minMove:.01}});
 chart.timeScale().subscribeVisibleLogicalRangeChange(range=>{if(range&&!rangeSync){rangeSync=true;osc.timeScale().setVisibleLogicalRange(range);rangeSync=false;}});
 osc.timeScale().subscribeVisibleLogicalRangeChange(range=>{if(range&&!rangeSync){rangeSync=true;chart.timeScale().setVisibleLogicalRange(range);rangeSync=false;}});
 chart.subscribeCrosshairMove(p=>{const r=p.seriesData?.get(candles);if(r?.open)showOHLC(r);else showOHLC(data.frames[tf].bars.at(-1));});
 new ResizeObserver(resizeCharts).observe($('chart'));
}
function resizeCharts(){if(!chart||!$('chart').clientWidth)return;chart.resize($('chart').clientWidth,$('chart').clientHeight);osc.resize($('osc-chart').clientWidth,$('osc-chart').clientHeight);}
function showOHLC(r){if(!r){$('ohlc').textContent='Aucune bougie disponible pour cette unité.';return;}$('ohlc').innerHTML=`O <b>${price(r.o??r.open)}</b> &nbsp; H <b>${price(r.h??r.high)}</b> &nbsp; L <b>${price(r.l??r.low)}</b> &nbsp; C <b>${price(r.c??r.close)}</b>`;}
function renderChart(){renderWidgets();const f=data.frames[tf];$('chart-meta').textContent=f.quality.valid_bars.toLocaleString('fr-FR')+' bougies · '+statusOf(f);showOHLC(f.bars.at(-1));renderFactors();
 document.querySelectorAll('[data-tf]').forEach(b=>b.classList.toggle('selected',b.dataset.tf===tf));
 if(!chart)return;
 // Whitespace creates visible time gaps; no artificial OHLC points.
 const cs=[],vs=[];let previous=null;
 for(const r of f.bars){if(previous!==null&&r.t-previous>T.steps[tf]){cs.push({time:previous+T.steps[tf]});vs.push({time:previous+T.steps[tf]});}cs.push({time:r.t,open:r.o,high:r.h,low:r.l,close:r.c});vs.push({time:r.t,value:r.v,color:r.c>=r.o?'#234e46':'#4c2c38'});previous=r.t;}
 candles.setData(cs);vol.setData(vs);
 for(const key of Object.keys(lines)){lines[key].setData(T.chartSeries(f.series,T.steps[tf],key));lines[key].applyOptions({visible:$(key).checked});}
 oscLine.setData(T.chartSeries(f.series,T.steps[tf],oscMode));
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
 $('quality-table').innerHTML=Object.values(data.frames).map(f=>{const q=f.quality;return `<tr><td>${f.interval}</td><td>${q.source_rows}</td><td>${q.valid_bars}</td><td class="amber-text">${q.excluded_rows}</td><td>${q.missing_bars}</td><td>${q.segments}</td><td class="${q.last_segment_bars<50?'amber-text':'positive'}">${q.last_segment_bars} bougies</td></tr>`;}).join('');
 const entries=[['Marché',data.market],['Fournisseur',data.source],['Capture UTC',data.captured_at],['Fichier source',data.source_path],['SHA-256 source',data.source_sha256],['Protocole expérimental',data.lab.experiments.protocol_sha256],['Exécution','Aucun ordre réel ou paper']];
 $('provenance').innerHTML=entries.map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
 $('limits').innerHTML=[...data.limits,'Pas de macro, de carnet live intégré, de portefeuille persistant ni d’alertes automatiques dans cet incrément.'].map(x=>`<li>${esc(x)}</li>`).join('');
 $('quarantine').textContent=JSON.stringify(Object.fromEntries(Object.entries(data.frames).map(([tf,f])=>[tf,{reasons:f.quality.reasons,rows:f.excluded}])),null,2);
}
function renderRisk(){const vals=['capital','entry','stop','target','fee','slip'].map(id=>$(id).value===''?NaN:Number($(id).value));vals[4]/=100;vals[5]/=100;const r=T.riskPlan(...vals);
 if(r.error){$('risk-output').innerHTML=`<div class="eyebrow">SIMULATION BLOQUÉE</div><h3>${esc(r.error)}</h3>`;return;}
 $('risk-output').innerHTML=`<div class="eyebrow">${r.admissible?'SCÉNARIO TECHNIQUEMENT ADMISSIBLE':'SCÉNARIO NON ADMISSIBLE'}</div><div class="big">${fmt(r.qty,2)} <span style="font-size:14px">TEL</span></div><p class="muted">Quantité théorique · Aucun ordre créé</p><dl><dt>Risque planifié</dt><dd>${money(r.risk)} / ${money(r.budget)}</dd><dt>Capital nécessaire</dt><dd>${money(r.cash)}</dd><dt>Rendement / risque brut</dt><dd class="${r.rr>=1.51?'positive':'negative'}">${fmt(r.rr,2)} R</dd><dt>Rendement / risque net</dt><dd>${fmt(r.rrNet,2)} R</dd><dt>Gain net si cible atteinte</dt><dd>${money(r.reward)}</dd></dl><p class="footnote" style="padding:24px 0 0">${r.admissible?'L’admissibilité mathématique ne valide pas la stratégie.':'RR net requis : au moins 1,5 après frais et slippage.'} Frais et slippage inclus. Un gap sous le stop peut dépasser ce budget. Quantité affichée arrondie ; calcul conservé à pleine précision.</p>`;
}
async function refreshSnapshot(){
 if(snapshotBusy||document.hidden)return;snapshotBusy=true;
 try{
  const feed='https://raw.githubusercontent.com/khalidd692/telcoin-trading-intelligence99/tel99-live-data/site/terminal/data.json';
  const r=await fetch(feed+'?t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(12000)});
  if(!r.ok)throw Error('Snapshot HTTP '+r.status);
  const next=await r.json();
  if(!T.acceptSnapshot(data,next))return;
  data=next;renderTickers();renderDecision();renderFrames();renderChart();renderLab();renderQuality();renderRisk();
 }catch(e){console.warn('TEL99: actualisation analytique indisponible; snapshot existant conservé',e.message);
 }finally{snapshotBusy=false;}
}
async function refreshQuote(){if(quoteBusy)return;quoteBusy=true;const b=$('refresh-quote');b.disabled=true;b.textContent='Connexion à Kraken…';
 try{const r=await fetch('https://api.kraken.com/0/public/Ticker?pair=TELUSD',{cache:'no-store',signal:AbortSignal.timeout(12000)});if(!r.ok)throw Error('HTTP '+r.status);const j=await r.json();if(j.error?.length)throw Error(j.error.join(', '));const p=T.parseTelTicker(j);if(p===null)throw Error('Paire Kraken ou cours invalide');liveQuote={price:p,received:Date.now()/1000};renderTickers();renderDecision();b.textContent='✓ Cours public reçu';
 }catch(e){liveQuote=null;renderTickers();renderDecision();b.textContent='↻ Réessayer le cours';$('freshness-banner').textContent='Cours public indisponible : '+e.message+'. Le snapshot historique reste affiché et conserve son horodatage.';}finally{quoteBusy=false;b.disabled=false;}}
function bind(){
 document.querySelectorAll('[data-widget]').forEach(input=>{const key=input.dataset.widget,panel=document.querySelector('[data-widget-panel="'+key+'"]');input.checked=pref('widget:'+key,'true')==='true';const apply=()=>{panel.classList.toggle('hidden',!input.checked);save('widget:'+key,String(input.checked));if(key==='chart'&&input.checked)resizeCharts();};apply();input.addEventListener('change',apply);});
 document.querySelectorAll('[data-view]').forEach(e=>e.addEventListener('click',()=>view(e.dataset.view)));
 document.querySelectorAll('[data-tf]').forEach(e=>e.addEventListener('click',()=>{tf=e.dataset.tf;save('tf',tf);renderChart();}));
 for(const key of ['ema20','ema50','sma200']){$(key).checked=pref(key,key==='sma200'?'false':'true')==='true';$(key).addEventListener('change',()=>{save(key,$(key).checked);renderChart();});}
 $('chart-window').addEventListener('change',renderChart);
 for(const [id,key] of [['rsi-mode','rsi14'],['macd-mode','macd_hist']])$(id).addEventListener('click',()=>{oscMode=key;$('rsi-mode').classList.toggle('selected',key==='rsi14');$('macd-mode').classList.toggle('selected',key==='macd_hist');renderChart();});
 $('cost-scenario').addEventListener('change',renderExperiments);$('event-tf').addEventListener('change',renderEvents);$('event-family').addEventListener('change',renderEvents);
 $('risk-form').addEventListener('submit',e=>e.preventDefault());$('risk-form').addEventListener('input',renderRisk);
 $('refresh-quote').addEventListener('click',refreshQuote);$('export-data').addEventListener('click',()=>download('TEL99_snapshot.json',data));$('export-lab').addEventListener('click',()=>download('TEL99_laboratoire.json',data.lab));
}
async function start(){try{
 const r=await fetch('data.json',{cache:'no-store'});if(!r.ok)throw Error('Snapshot HTTP '+r.status);data=await r.json();if(data.schema_version!==1||data.market!=='KRAKEN:TELUSD')throw Error('Schéma ou marché incorrect');
 tf=pref('tf','4h');if(!data.frames[tf])tf='4h';bind();setupCharts();renderTickers();renderDecision();renderFrames();renderChart();renderLab();renderQuality();
 const l=data.frames['4h'].latest,d=T.safeDecision(data),p=d.status==='DONNÉES INSUFFISANTES'?null:d.plan;$('entry').value=p?(l.close??''):'';$('stop').value=p?.stop??'';$('target').value=p?.target??'';renderRisk();
 $('loading').classList.add('hidden');view(location.hash.slice(1)||'market');
 setInterval(()=>{renderTickers();renderDecision();renderFrames();$('clock').textContent=new Date().toLocaleTimeString('fr-FR',{timeZone:'UTC'})+' UTC';},15000);
 // Public quote only: never relabel a static analytical snapshot as live.
 refreshQuote();
 setInterval(()=>{if(!document.hidden)refreshQuote();},60000);
 // Only accept a newer same-origin analytical snapshot with unchanged frozen research.
 refreshSnapshot();
 setInterval(refreshSnapshot,60000);
 $('clock').textContent=new Date().toLocaleTimeString('fr-FR',{timeZone:'UTC'})+' UTC';
 }catch(e){$('loading').classList.add('load-error');$('loading').textContent='Terminal indisponible : '+e.message+'. Servez le dossier avec HTTP et vérifiez data.json.';}}
start();
