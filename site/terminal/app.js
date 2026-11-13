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
let rangeSync=false,quoteBusy=false,snapshotBusy=false,eurUsd=null,eurUsdFetched=0,fxReferenceDate=null;
const S=window.TEL99SmartView, W=window.TEL99Widgets;
let depthBook=null, depthReceived=0, depthBusy=false, historyBusy=false, latestJournalEntry=null;
let marketTickers=null, marketReceived=0, marketBusy=false, marketExpiryTimer=null;
let cardState, cardCategory='Tous';
const cardDefinitions=[
 ['chart','Graphique de prix','Techniques','Bougies, moyennes, niveaux et couches.',true],
 ['levels','Niveaux clés','Techniques','Supports, résistances et Fibonacci.',true],
 ['zones','Zones SMC','Techniques','Structure, blocs et déséquilibres estimés.',true],
 ['profile','Profil de volume','Techniques','Estimation du volume par classes de prix.',true],
 ['technical','Jauge technique','Techniques','Votes et indicateurs par unité.',true],
 ['tradeplan','Plan de trade','Techniques','Scénario conditionnel et risque net.',true],
 ['scenarios','Scénarios conditionnels','Techniques','Hypothèses de repli et de confirmation.',true],
 ['liquidity','Carnet Kraken','Marché','Spread, profondeur et impact indicatif.',true],
 ['price','Fiche TEL/USD','Marché','Prix et variations sur une période.',true],
 ['macro','Contexte BTC / ETH','Marché','Clôtures, volume et corrélation calculée.',true],
 ['markets','Comparateur de marchés','Marché','Prix, volume et spread des paires Kraken.',true],
 ['prospective','Statistiques prospectives','Marché','Observations et résultats futurs du journal.',true],
 ['fundamentals','Fondamentaux','Fondamentaux','Sources et recherches datées sur Telcoin.',true],
 ['accumulation','Accumulation personnelle','Personnel','Quantité et capital saisis localement.',true],
 ['decision','Centre de décision','Techniques','Détails de la décision swing.',true],
 ['factors','Carte des facteurs','Techniques','Indicateurs et contradictions.',true],
 ['frames','Convergence temporelle','Techniques','Qualité et données par unité.',true],
 ['guide','Guide du radar','Personnel','Signification des états du radar.',false],
 ['preview1h','Aperçu 1 h','Techniques','Graphique compact de structure.',false],
 ['preview4h','Aperçu 4 h','Techniques','Graphique compact de confirmation.',false],
 ['preview1d','Aperçu 1 jour','Techniques','Graphique compact de contexte.',false]
].map(([id,title,category,description,visible])=>({id,title,category,description,visible}));
const technicalCache=new WeakMap();
let renderedSmartFrame,renderedSmartAvailability,renderedSmartSignature;
let chartPriceLines=[], structureMarkers;
let technicalDetail=null;
let previousChartAvailability;
let priceDays=5;
const chartTitles={'15m':'Structure · 15 min','1h':'Structure · 1 h','4h':'Confirmation · 4 h','1D':'Contexte · 1 jour','1W':'Contexte · 1 semaine'};
function drawRadarCanvas(canvas,bars,{series=[],levels=[],asLine=false}={}){
 const width=canvas.clientWidth,height=canvas.clientHeight;
 if(!width||!height)return;
 const ratio=window.devicePixelRatio||1;
 canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);
 const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);
 if(!bars.length)return;
 const plot=width-67;
 const ticks=asLine?bars.map(r=>r.c):bars.flatMap(r=>[r.h,r.l]);
 const lo=Math.min(...ticks),hi=Math.max(...ticks),pad=(hi-lo||hi*.02)*.08;
 const step=(plot-8)/bars.length;
 const x=i=>4+(i+.5)*step,y=v=>8+(hi+pad-v)/(hi-lo+2*pad)*(height-16);
 const line=(a,b,c,d,color)=>{ctx.strokeStyle=color;ctx.beginPath();ctx.moveTo(a,b);ctx.lineTo(c,d);ctx.stroke();};
 ctx.font='10px system-ui';ctx.fillStyle='#acb9ca';
 for(const v of [hi,(hi+lo)/2,lo]){
  line(0,y(v),plot,y(v),'#273242');ctx.fillText(price(v),plot+5,y(v)+3);
 }
 if(asLine){
  bars.slice(1).forEach((r,i)=>line(x(i),y(bars[i].c),x(i+1),y(r.c),'#74a3ed'));
  return;
 }
 bars.forEach((r,i)=>{
  const color=r.c>=r.o?'#54c4ba':'#ee8990',body=Math.max(1,step*.63);
  line(x(i),y(r.h),x(i),y(r.l),color);
  ctx.fillStyle=color;ctx.fillRect(x(i)-body/2,Math.min(y(r.o),y(r.c)),body,Math.max(1,Math.abs(y(r.o)-y(r.c))));
 });
 for(const [value,color] of levels){
  if(!T.finite(value)||value<lo-pad||value>hi+pad)continue;
  ctx.setLineDash([4,3]);line(0,y(value),plot,y(value),color);ctx.setLineDash([]);
 }
 const indicators=new Map(series.map(r=>[r.t,r]));
 for(const [key,color] of [['ema20','#e8ad62'],['ema50','#74a3ed']]){
  bars.slice(1).forEach((r,i)=>{
   const before=indicators.get(bars[i].t)?.[key],after=indicators.get(r.t)?.[key];
   if(T.finite(before)&&T.finite(after)&&before>=lo-pad&&before<=hi+pad&&after>=lo-pad&&after<=hi+pad)line(x(i),y(before),x(i+1),y(after),color);
  });
 }
}
function renderRadarCanvas(canvas){
 if(!data)return;
 if(canvas.id==='radar-price-chart'){
  const unit=priceDays===1?'1h':'1D',frame=data.frames[unit];
  const count=priceDays===1?25:priceDays+1;
  const availability=chartStatus(frame,unit),bars=W.chartBars(frame,availability).slice(-count);
  const complete=bars.length===count&&bars.at(-1).t-bars[0].t===priceDays*86400;
  drawRadarCanvas(canvas,complete?bars:[],{asLine:true});
  $('radar-price-note').textContent=complete?`${pct(100*(bars.at(-1).c/bars[0].c-1))} sur ${priceDays} j · clôture ${date(frame.quality.last_close)} UTC · ${availability}`:`Historique indisponible : ${availability}.`;
  return;
 }
 const unit=canvas.dataset.preview,frame=data.frames[unit],availability=chartStatus(frame,unit);
 const slice=W.chartBars(frame,availability).slice(-55),cut=slice.findLastIndex((r,i)=>i>0&&r.t-slice[i-1].t!==S.steps[unit]);
 const bars=slice.slice(Math.max(0,cut));
 const m=availability==='Disponible'?S.marketLevels(frame,unit):{};
 drawRadarCanvas(canvas,bars,{series:frame.series,levels:[[m.support,'#54c4ba'],[m.resistance,'#ee8990']]});
 document.querySelector('[data-preview-caption="'+unit+'"]').textContent=`Kraken · ${date(frame.quality.last_close)} UTC · ${availability}`;
}
function renderRadar(){
 if(!data)return;
 const frame=data.frames['1h'];
 const m=chartStatus(frame,'1h')==='Disponible'?S.marketLevels(frame,'1h'):null;
 const profile=m?S.volumeProfile(frame):null;
 $('smart-profile').innerHTML=profile?`<p class="radar-values"><span>VAH <b>${price(profile.vah)}</b></span><span>POC <b>${price(profile.poc)}</b></span><span>VAL <b>${price(profile.val)}</b></span><span>Écart <b>${pct(100*(frame.latest.close/profile.poc-1))}</b></span></p><div class="smart-profile" aria-hidden="true">${profile.bins.map((v,i)=>`<i class="${i===profile.peak?'poc':i>=profile.lo&&i<=profile.hi?'accepted':''}" style="width:${100*v/Math.max(...profile.bins)}%"></i>`).reverse().join('')}</div><p class="radar-caption">8 jours · 60 classes · estimation HLC3 sur bougies 1h clôturées · zone de valeur à 70 % du volume.</p>`:'<p>Profil indisponible. Il faut 192 bougies horaires clôturées et consécutives.</p>';
 const structure=m?S.structureEvents(frame,'1h'):[];
 const zones=m?[...(m.fvgs??[]).map(z=>({...z,label:'FVG'})),...structure.filter(e=>e.zone).slice(-2).map(e=>({...e.zone,label:'OB estimé',side:e.side==='up'?'hausse':'baisse'}))]:[];
 $('radar-zones').innerHTML=m?(zones.length?`<ul class="radar-zones">${zones.map(z=>{
  const c=frame.latest.close,edge=c<z.low?z.low:c>z.high?z.high:null;
  return `<li><b>${z.label} · ${z.side}</b><span>${price(z.low)}–${price(z.high)} $</span><span>${edge===null?'Dans la zone':pct(100*(edge/c-1))}</span></li>`;
 }).join('')}</ul>`:'<p>Aucune zone détectée sur la fenêtre.</p>')+'<p class="radar-caption">BOS dans le sens de la cassure précédente, CHoCH en sens inverse. OB estimé sur la dernière bougie opposée avant cassure.</p>':'<p>Données horaires insuffisantes ou périmées.</p>';
 const quote=liveQuote&&T.freshQuote(liveQuote)?liveQuote:null;
 $('radar-price-value').textContent=price(quote?.price??data.frames['1h'].latest.close)+' $ · '+(quote?'cotation '+date(quote.received):'clôture 1h '+date(frame.quality.last_close))+' UTC';
 const context=['btc4h','eth4h'].map(k=>data.context[k]);
 const row=(label,fn)=>`<tr><th scope="row">${label}</th>${context.map(c=>`<td>${fn(c)}</td>`).join('')}</tr>`;
 $('radar-macro').innerHTML='<table class="radar-macro"><thead><tr><th>Kraken</th><th>BTC/USD</th><th>ETH/USD</th></tr></thead><tbody>'+row('Clôture 4h',c=>c?money(c.latest.close):'—')+row('Date UTC',c=>date(c?.quality.last_close))+row('Volume 4h',c=>fmt(c?.latest.volume,2))+row('Corrélation TEL',c=>fmt(c?.correlation?.pearson,2))+'</tbody></table><p class="radar-caption">Contexte à la clôture. Variations multi-périodes et capitalisation indisponibles dans ce flux.</p>';
 document.querySelectorAll('[data-preview],#radar-price-chart').forEach(renderRadarCanvas);
}
function withWeekly(snapshot){
 snapshot.frames['1W']=S.weekly(snapshot.frames['1D'],snapshot.as_of);
 return snapshot;
}
function scoreGauge(name,votes){
 const total=votes?votes.buy+votes.sell+votes.neutral:0;
 const score=total?(votes.buy-votes.sell)/total:0;
 const verdict=!total?'Indisponible':score>=.5?'Achat fort':score>.1?'Acheter':score<=-.5?'Vente forte':score<-.1?'Vendre':'Neutre';
 const theta=Math.PI*(1-score)/2;
 const colors=['#ff5f78','#ad354d','#a2adbe','#3874e5','#73a8ff'];
 const point=deg=>[50+40*Math.cos(deg*Math.PI/180),49-40*Math.sin(deg*Math.PI/180)].join(' ');
 const arcs=colors.map((color,i)=>`<path d="M ${point(180-i*36-3)} A40 40 0 0 1 ${point(180-(i+1)*36+3)}" stroke="${color}"/>`).join('');
 return `<article class="smart-gauge"><b>${name}</b><svg viewBox="0 0 100 53" aria-hidden="true"><g fill="none" stroke-width="5" stroke-linecap="round">${arcs}</g>${total?`<line x1="50" y1="49" x2="${50+31*Math.cos(theta)}" y2="${49-31*Math.sin(theta)}" stroke="#e8effa" stroke-width="3" stroke-linecap="round"/>`:''}</svg><strong>${verdict}</strong><dl class="smart-votes"><div><dt>Acheter</dt><dd>${total?votes.buy:'—'}</dd></div><div><dt>Neutre</dt><dd>${total?votes.neutral:'—'}</dd></div><div><dt>Vendre</dt><dd>${total?votes.sell:'—'}</dd></div></dl></article>`;

}
function technicalTable(rows){
 const action={1:'Acheter',0:'Neutre','-1':'Vendre'};
 return '<div class="table-scroll smart-table"><table><thead><tr><th>Indicateur</th><th>Valeur</th><th>Signal</th></tr></thead><tbody>'+rows.map(r=>`<tr><td>${r.name}<small>${r.period}</small></td><td>${fmt(r.value,8)}${T.finite(r.extra)?' / '+fmt(r.extra,8):''}</td><td class="${r.vote===1?'positive':r.vote===-1?'negative':''}">${action[r.vote]??'Indisponible'}</td></tr>`).join('')+'</tbody></table></div>';
}
function multiUnitGauges(){
 const quality=W.gaugeFreshness(data.frames,data.as_of,Date.now()/1000,window.TEL99Radar.frameCheck);
 return '<div class="multi-unit-gauges">'+['15m','1h','4h','1D'].map(unit=>{
  const frame=data.frames[unit];
  if(quality[unit]!=='Disponible')return `<div><b>${unit}</b><span>${esc(quality[unit])}</span></div>`;
  if(!technicalCache.has(frame))technicalCache.set(frame,{technical:S.technical(frame,unit),levels:S.marketLevels(frame,unit)});
  const r=technicalCache.get(frame).technical,total=r.total.buy+r.total.sell+r.total.neutral;
  if(!total)return `<div><b>${unit}</b><span>Indicateurs insuffisants</span></div>`;
  const score=(r.total.buy-r.total.sell)/total;
  const direction=score>.1?'Haussière':score<-.1?'Baissière':'Neutre';
  return `<div><b>${unit} · ${direction}</b><span class="vote-bar"><i style="left:${Math.max(0,Math.min(100,50+score*50))}%"></i></span><small>MM ${r.averageCounts.buy}↑ / ${r.averageCounts.sell}↓ · Osc. ${r.counts.buy}↑ / ${r.counts.sell}↓ · ADX ${fmt(frame.latest?.adx14,1)}</small></div>`;
 }).join('')+'</div><p class="radar-caption">Votes techniques descriptifs et ADX de tendance ; ce ne sont pas des probabilités.</p>';
}
function renderSmart(frame,availability){
 const node=$('technical-widget');
 const levels=$('smart-structure');
 const monthly=$('technical-month').getAttribute('aria-pressed')==='true';
 const signature=JSON.stringify(W.gaugeFreshness(data.frames,data.as_of,Date.now()/1000,window.TEL99Radar.frameCheck));
 if(renderedSmartFrame===frame&&renderedSmartAvailability===availability&&renderedSmartSignature===signature)return;
 renderedSmartFrame=frame;renderedSmartAvailability=availability;renderedSmartSignature=signature;
 if(availability!=='Disponible'){
  if(!monthly)node.innerHTML='<p class="amber-text">DONNÉES INSUFFISANTES · '+esc(availability)+'</p><div class="smart-gauges">'+['Oscillateurs','Résumé','Moyennes mobiles'].map(name=>scoreGauge(name,null)).join('')+'</div>';
  levels.textContent='Données insuffisantes pour des niveaux actuels.';
  return null;
 }
 if(!technicalCache.has(frame))technicalCache.set(frame,{technical:S.technical(frame,tf),levels:S.marketLevels(frame,tf)});
 const {technical:r,levels:m}=technicalCache.get(frame);
 const details=(id,name,body)=>`<section data-technical-panel="${id}" ${technicalDetail===id?'':'hidden'}><h3>${name}</h3>${body}</section>`;
 if(!monthly)node.innerHTML=multiUnitGauges()+`<p>${esc(tf)} · clôture ${date(frame.quality.last_close)} UTC</p><div class="smart-gauges">${scoreGauge('Oscillateurs',r.counts)}${scoreGauge('Résumé',r.total)}${scoreGauge('Moyennes mobiles',r.averageCounts)}</div>`+
  '<div class="technical-menu" aria-label="Tableaux techniques">'+[['osc','Oscillateurs'],['ma','Moyennes'],['piv','Pivots'],['method','Méthode']].map(([key,label])=>`<button type="button" data-technical="${key}" aria-pressed="${technicalDetail===key}">${label}</button>`).join('')+'</div>'+
  details('osc','Oscillateurs · valeurs et votes',technicalTable(r.oscillators))+
  details('ma','Moyennes mobiles · valeurs et votes',technicalTable(r.averages))+
  details('piv','Pivots · classique, Fibonacci, Camarilla et Woodie',r.pivots.length?'<div class="table-scroll smart-pivot-table"><table><thead><tr><th>Niveau</th><th>Classique</th><th>Fibonacci</th><th>Camarilla</th><th>Woodie</th></tr></thead><tbody>'+r.pivots.map(row=>'<tr><td>'+row[0]+'</td>'+row.slice(1).map(v=>'<td>'+price(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>':'<p>Données insuffisantes.</p>')+
  details('method','Méthode des votes',`<p>Une voix par indicateur disponible. Le score est (achats − ventes) ÷ votes. Verdict neutre entre −0,10 et +0,10, fort à partir de ±0,50. Les moyennes votent selon la position de la clôture. MACD et stochastiques votent selon la comparaison à leur signal. Momentum, AO et Bull Bear Power votent selon leur signe. ADX ≥ 25 utilise la direction DMI. RSI et Ultimate votent aux seuils 30 / 70, CCI −100 / +100 et Williams −80 / −20. Les indicateurs repartent après chaque interruption. Les pivots utilisent la période précédente et, pour Woodie, l’ouverture de la période analysée. Les jauges sont descriptives.</p>`);
 const reference=frame.latest?.close;
 const levelRows=[['Dernier pivot haut',m.resistance,'resistance'],['Clôture',reference,'current'],['Dernier pivot bas',m.support,'support']].map(([name,value,kind])=>`<div class="level-row ${kind}"><span>${name}</span><b>${price(value)} $</b><small>${kind==='current'?'Référence':pct(W.distancePct(value,reference))}</small></div>`).join('');
 levels.innerHTML=`<div class="level-rows">${levelRows}</div><p class="radar-caption">Distances par rapport à la clôture ${esc(tf)} · ${date(frame.quality.last_close)} UTC. Un pivot franchi n’est pas automatiquement une résistance ou un support actif.</p><p>Structure des pivots confirmés · ${esc(m.trend??'indisponible')}. ${esc(m.breaks??'Aucune cassure du dernier pivot sur la dernière clôture.')}</p><dl><dt>FVG récents non comblés</dt><dd>${m.fvgs?.map(z=>price(z.low)+'–'+price(z.high)+' $ · '+z.side).join(' / ')||'Aucun détecté'}</dd><dt>Retracements sur fenêtre</dt><dd>${m.fib?.map(([k,v])=>fmt(k*100,1)+' % · '+price(v)).join(' / ')||'—'}</dd></dl><p class="footnote">Pivots à deux bougies de chaque côté. Les niveaux sont des repères de structure. La carte Zones précise les heuristiques SMC.</p>`;
 return m;
}
function selectMarket(key){
 document.querySelectorAll('[data-market-panel]').forEach(panel=>{panel.hidden=key==='radar'?!panel.hasAttribute('data-radar-card'):panel.dataset.marketPanel!==key;});
 document.querySelectorAll('[data-market]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.market===key)));
 save('market-widget',key);
 if(key==='chart'||key==='radar')resizeCharts();
 if(data)renderRadar();
}
function pref(key,fallback){try{return localStorage.getItem('tel99:'+key)??fallback;}catch{return fallback;}}
function save(key,v){try{localStorage.setItem('tel99:'+key,v);}catch{/* Privacy mode still usable. */}}
function defaultCards(useLegacy=true){
 const visible={};
 for(const card of cardDefinitions){
  const old=useLegacy?pref('widget:'+card.id,''):'';
  visible[card.id]=old==='true'?true:old==='false'?false:card.visible;
 }
 return {order:cardDefinitions.map(x=>x.id),visible};
}
function applyCards(){
 let anchor=$('widget-catalog');
 cardState.order.forEach((id,index)=>{
  const panel=document.querySelector('[data-card-id="'+id+'"]');
  if(panel){anchor.after(panel);anchor=panel;panel.style.order=String(index+10);panel.classList.toggle('hidden',!cardState.visible[id]);}
 });
 save('cards-v1',JSON.stringify(cardState));
 if(chart)resizeCharts();
}
function renderCardCatalog(){
 const categories=['Tous','Techniques','Fondamentaux','Screening','Marché','Personnel'];
 $('widget-categories').innerHTML=categories.map(name=>`<button type="button" data-category="${name}" aria-pressed="${cardCategory===name}">${name}</button>`).join('');
 const query=$('widget-search').value.trim().toLocaleLowerCase('fr');
 const cards=cardState.order.map(id=>cardDefinitions.find(x=>x.id===id)).filter(card=>card&&(cardCategory==='Tous'||card.category===cardCategory)&&(!query||(card.title+' '+card.description).toLocaleLowerCase('fr').includes(query)));
 const views={chart:'Graphique',technical:'Note technique',levels:'Niveaux clés',plans:'Plan de trade',context:'Contexte'};
 $('widget-list').innerHTML=cards.length?cards.map(card=>{
  const panel=document.querySelector('[data-card-id="'+card.id+'"]'),viewName=views[panel?.dataset.marketPanel]??'Radar';
  return `<div class="widget-option"><label><input type="checkbox" data-card-toggle="${card.id}" ${cardState.visible[card.id]?'checked':''}><span><strong>${esc(card.title)}</strong><small>${esc(card.description)} · Vue ${esc(viewName)}</small></span></label><div class="widget-move"><button type="button" data-card-open="${card.id}" aria-label="Voir ${esc(card.title)}">Voir</button><button type="button" data-card-move="${card.id}" data-direction="-1" aria-label="Monter ${esc(card.title)}">↑</button><button type="button" data-card-move="${card.id}" data-direction="1" aria-label="Descendre ${esc(card.title)}">↓</button></div></div>`;
 }).join(''):'<p>Aucun widget dans cette catégorie.</p>';
}
function bindCardCatalog(){
 let saved;try{saved=JSON.parse(pref('cards-v1','null'));}catch{saved=null;}
 const defaults=defaultCards();
 cardState={order:W.layout(saved?.order,defaults.order),visible:{...defaults.visible}};
 if(saved?.visible&&typeof saved.visible==='object')for(const id of defaults.order)if(typeof saved.visible[id]==='boolean')cardState.visible[id]=saved.visible[id];
 applyCards();renderCardCatalog();
 $('widget-search').addEventListener('input',renderCardCatalog);
 $('widget-categories').addEventListener('click',event=>{const b=event.target.closest('[data-category]');if(b){cardCategory=b.dataset.category;renderCardCatalog();}});
 $('widget-list').addEventListener('change',event=>{const input=event.target.closest('[data-card-toggle]');if(input){const id=input.dataset.cardToggle,panel=document.querySelector('[data-card-id="'+id+'"]');cardState.visible[id]=input.checked;applyCards();if(input.checked&&panel?.hidden)selectMarket(panel.dataset.marketPanel);}});
 $('widget-list').addEventListener('click',event=>{
  const open=event.target.closest('[data-card-open]');
  if(open){const id=open.dataset.cardOpen,panel=document.querySelector('[data-card-id="'+id+'"]');if(panel){cardState.visible[id]=true;applyCards();selectMarket(panel.dataset.marketPanel);$('widget-catalog').open=false;panel.scrollIntoView({block:'start'});}return;}
  const button=event.target.closest('[data-card-move]');if(!button)return;
  const index=cardState.order.indexOf(button.dataset.cardMove),next=index+Number(button.dataset.direction);
  if(index<0||next<0||next>=cardState.order.length)return;
  [cardState.order[index],cardState.order[next]]=[cardState.order[next],cardState.order[index]];
  applyCards();renderCardCatalog();
  $('widget-list').querySelector('[data-card-move="'+button.dataset.cardMove+'"][data-direction="'+button.dataset.direction+'"]')?.focus();
 });
 $('widget-reset').addEventListener('click',()=>{cardState=defaultCards(false);cardCategory='Tous';$('widget-search').value='';applyCards();renderCardCatalog();});
}
function download(name,obj){const a=document.createElement('a'),url=URL.createObjectURL(new Blob([JSON.stringify(obj,null,2)],{type:'application/json'}));a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function statusOf(frame){return T.frameStatus(frame,data.as_of,Date.now()/1000,S.steps[frame?.interval]);}
function chartStatus(frame,unit){
 if(!(unit in T.steps))return statusOf(frame);
 const integrity=window.TEL99Radar.frameIntegrity(frame,unit,data.as_of);
 return integrity==='Disponible'?window.TEL99Radar.frameCheck(frame,unit,data.as_of,Date.now()/1000):integrity;
}
function requiredDataIssues(){
 const results=Object.keys(T.steps).map(unit=>[unit,statusOf(data.frames?.[unit])]);
 return results.filter(([,status])=>status!=='Disponible').map(([unit,status])=>unit+' · '+status);
}
function rowClass(n){return T.finite(n)?n>=0?'positive':'negative':'';}
function view(name){if(!['market','lab','risk','data'].includes(name))name='market';document.querySelectorAll('.view').forEach(e=>e.classList.toggle('hidden',e.id!=='view-'+name));document.querySelectorAll('.nav').forEach(e=>e.classList.toggle('active',e.dataset.view===name));$('view-title').textContent={market:'Centre de marché',lab:'Laboratoire quantitatif',risk:'Simulateur de risque',data:'Données & preuves'}[name];history.replaceState(null,'','#'+name);if(name==='market'&&chart)resizeCharts();$('sidebar-toggle').setAttribute('aria-expanded','false');$('app-sidebar').classList.remove('sidebar-open');}
function renderTickers(){
 if(liveQuote&&!T.freshQuote(liveQuote))liveQuote=null;
 const f=data.frames['4h'],last=f.bars.at(-1),earlier=last&&f.bars.find(x=>x.t===last.t-86400),change=earlier?100*(last.c/earlier.c-1):null;
 const btc=data.context.btc4h,eth=data.context.eth4h;
 $('tickers').innerHTML=`<article class="ticker"><div class="label"><span>TEL / USD</span><span class="amber-text">KRAKEN</span></div><div class="value">${price(liveQuote?.price??last?.c)} <span style="font-size:12px">$</span></div><small>${liveQuote?'Cours public reçu '+date(liveQuote.received)+' UTC':'Clôture 4h · '+date(f.quality.last_close)+' UTC'}</small></article><article class="ticker"><div class="label"><span>VARIATION 24H</span><span>CLÔTURES</span></div><div class="value ${rowClass(change)}">${pct(change)}</div><small>Deux clôtures 4h espacées de 24h</small></article><article class="ticker"><div class="label"><span>BITCOIN / USD</span><span>4H</span></div><div class="value">${fmt(btc?.latest.close,2)} <span style="font-size:11px">$</span></div><small>Clôture ${date(btc?.quality.last_close)} UTC</small></article><article class="ticker"><div class="label"><span>ETHEREUM / USD</span><span>4H</span></div><div class="value">${fmt(eth?.latest.close,2)} <span style="font-size:11px">$</span></div><small>Clôture ${date(eth?.quality.last_close)} UTC</small></article>`;
}
function renderDecision(){
 const d=T.safeDecision(data),list=(arr,cls='')=>`<ul class="evidence ${cls}">${arr.map(t=>`<li>${esc(t)}</li>`).join('')}</ul>`;
 const issues=requiredDataIssues();
 const current=d.status!=='DONNÉES INSUFFISANTES'&&!issues.length;
 $('decision').innerHTML=`<div class="eyebrow">${current?'LECTURE EXPÉRIMENTALE':'QUALITÉ DES DONNÉES'}</div><div class="decision-tag">${esc(current?d.status:'DONNÉES INSUFFISANTES')}</div><p class="decision-caption">${current?'Convergence de facteurs, sans avantage statistique démontré.':'Analyse bloquée. Les éléments ci-dessous décrivent le snapshot historique.'}<br>Aucun ordre réel ou paper.</p><div class="list-heading">ÉLÉMENTS FAVORABLES</div>${list(d.proofs?.length?d.proofs:['Aucun facteur favorable suffisamment documenté.'])}<div class="list-heading">CONTRADICTIONS & LIMITES</div>${list([...issues,...(d.staleReasons||[]),...(d.contradictions||[])],'conflicts')}<div class="invalidation"><span>Seuil structurel observé</span><b>${price(d.invalidation)} $</b></div><p class="footnote" style="padding:10px 0 0">Plus bas des 20 barres précédentes. Ce niveau n’est pas un ordre stop.</p>`;
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
 const f=data.frames[tf], l=f.latest, availability=chartStatus(f,tf);
 renderSmart(f,availability);
 const d=T.safeDecision(data),p=d.plan;
 if(d.status==='DONNÉES INSUFFISANTES'||requiredDataIssues().length) $('tradeplan-widget').innerHTML='<p class="amber-text">Données insuffisantes ou périmées : plan masqué. Aucun ordre.</p>';
 else if(!p||![p.entry,p.stop,p.target,p.rr_net].every(T.finite)) $('tradeplan-widget').innerHTML='<p class="amber-text">Aucun plan chiffré disponible pour ce snapshot. Aucun ordre.</p>';
 else $('tradeplan-widget').innerHTML=`<p>Lecture : ${esc(d.status)} · snapshot ${date(data.as_of)} UTC</p><dl><dt>Entrée indicative</dt><dd>${price(p.entry)} $</dd><dt>Stop théorique</dt><dd>${price(p.stop)} $</dd><dt>Objectif théorique</dt><dd>${price(p.target)} $</dd><dt>Rendement / risque net estimé</dt><dd>${fmt(p.rr_net,2)} R</dd><dt>Perte planifiée</dt><dd>${money(p.planned_risk_usd)}</dd><dt>Quantité</dt><dd>Non déterminée : frais personnels non vérifiés</dd><dt>Frais / slippage hypothétiques par côté</dt><dd>${fmt(100*p.fee_per_side,2)} % / ${fmt(100*p.slippage_per_side,2)} %</dd></dl><p class="footnote">Calcul indicatif pour 1 000 $. RR net minimum : 1,5. Frais Kraken personnels non vérifiés : aucune taille recommandée. Les coûts hypothétiques peuvent différer ; un gap peut dépasser la perte prévue. Aucune stratégie validée, aucun ordre.</p>`;
}
function renderFrames(){
 renderWidgets();
 $('timeframe-table').innerHTML=Object.values(data.frames).sort((a,b)=>S.steps[a.interval]-S.steps[b.interval]).map(f=>{const l=f.latest,q=f.quality;return `<tr><td>${esc(f.interval)}</td><td class="${statusOf(f)==='Disponible'?'positive':'amber-text'}">${statusOf(f)}</td><td>${esc(l.trend)}</td><td>${fmt(l.rsi14,1)}</td><td>${fmt(l.adx14,1)}</td><td>${fmt(l.volume_ratio,2)} ×</td><td>${date(q.last_close)}</td></tr>`;}).join('');
}
function renderFactors(){const f=data.frames[tf],l=f.latest,btc=data.context.btc4h?.correlation;
 const rsiMethod=f.indicator_methods?.rsi14==='wilder_rma_14_sma_seed'?'RSI14 Wilder':'RSI14 arithmétique (ancien snapshot)';
 $('factors').innerHTML=[['Structure · '+tf,l.trend??'INDISPONIBLE',!T.finite(l.ema50)?'EMA50 indisponible après la dernière interruption.':'EMA20 '+price(l.ema20)+' · EMA50 '+price(l.ema50),''],['Momentum · '+tf,fmt(l.rsi14,1),rsiMethod+' · MACD '+(l.macd_improving?'en amélioration':'sans amélioration'),l.rsi14>50?'positive':'amber-text'],['Volatilité · '+tf,T.finite(l.atr14)?fmt(100*l.atr14/l.close,2)+' %':'—','ATR14 / clôture · ADX '+fmt(l.adx14,1),''],['Corrélation TEL / BTC',fmt(btc?.pearson,2),(btc?.n??0)+' rendements 4h alignés. Corrélation ≠ causalité.','']].map(([title,value,desc,cls])=>`<div class="factor"><div class="label">${esc(title)}</div><div class="metric ${cls}" style="${value.length>11?'font-size:17px':''}">${esc(value)}</div><p>${esc(desc)}</p></div>`).join('');
}
function setupCharts(){
 const L=window.LightweightCharts;
 if(!L){$('chart').innerHTML='<p class="load-error">Bibliothèque de graphiques indisponible. Les tableaux restent accessibles.</p>';return;}
 const common={layout:{background:{color:'#111315'},textColor:'#a4a6ad',fontFamily:'ui-monospace,monospace',fontSize:10,attributionLogo:true},grid:{vertLines:{color:'#24262a'},horzLines:{color:'#24262a'}},rightPriceScale:{borderColor:'#34363a',minimumWidth:78},timeScale:{borderColor:'#34363a',timeVisible:true,secondsVisible:false},crosshair:{mode:L.CrosshairMode.Normal,vertLine:{color:'#777b82',labelBackgroundColor:'#35383d'},horzLine:{color:'#777b82',labelBackgroundColor:'#35383d'}},handleScroll:{vertTouchDrag:false},localization:{locale:'fr-FR'}};
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
 chart.subscribeCrosshairMove(p=>{const frame=data.frames[tf],bars=W.chartBars(frame,chartStatus(frame,tf)),r=p.seriesData?.get(candles);if(!bars.length)showOHLC(null);else if(r?.open)showOHLC(r);else showOHLC(bars.at(-1));});
 new ResizeObserver(resizeCharts).observe($('chart'));
}
function resizeCharts(){if(!chart||!$('chart').clientWidth)return;chart.resize($('chart').clientWidth,$('chart').clientHeight);osc.resize($('osc-chart').clientWidth,$('osc-chart').clientHeight);}
function showOHLC(r){if(!r){$('ohlc').textContent='Aucune bougie disponible pour cette unité.';return;}$('ohlc').innerHTML=`O <b>${price(r.o??r.open)}</b> &nbsp; H <b>${price(r.h??r.high)}</b> &nbsp; L <b>${price(r.l??r.low)}</b> &nbsp; C <b>${price(r.c??r.close)}</b>`;}
function renderChart(){renderWidgets();const f=data.frames[tf],quality=chartStatus(f,tf),bars=W.chartBars(f,quality);previousChartAvailability=quality;$('radar-chart-title').textContent=chartTitles[tf];$('chart-meta').textContent=f.quality.valid_bars.toLocaleString('fr-FR')+' bougies · '+quality;showOHLC(bars.at(-1));renderFactors();
 document.querySelectorAll('[data-tf]').forEach(b=>{b.classList.toggle('selected',b.dataset.tf===tf);b.setAttribute('aria-pressed',String(b.dataset.tf===tf));});
 if(!chart)return;
 // Whitespace creates visible time gaps; no artificial OHLC points.
 const cs=[],vs=[];let previous=null;
 for(const r of bars){if(previous!==null&&r.t-previous>S.steps[tf]){cs.push({time:previous+S.steps[tf]});vs.push({time:previous+S.steps[tf]});}cs.push({time:r.t,open:r.o,high:r.h,low:r.l,close:r.c});vs.push({time:r.t,value:r.v,color:r.c>=r.o?'#234e46':'#4c2c38'});previous=r.t;}
 candles.setData(cs);vol.setData(vs);
 for(const line of chartPriceLines)candles.removePriceLine(line);
 chartPriceLines=[];
 const marketStructure=quality==='Disponible'?technicalCache.get(f)?.levels??S.marketLevels(f,tf):null;
 const events=marketStructure?S.structureEvents(f,tf):[];
 const swings=$('smart-pivots').checked?(marketStructure?.pivots??[]).map(p=>({
  time:p.time,position:p.side==='high'?'aboveBar':'belowBar',shape:'circle',size:.45,text:p.label,color:p.side==='high'?'#f28b9a':'#54c4ba'
 })):[];
 const marks=$('smart-pivots').checked?events.map(e=>({time:e.time,position:e.side==='up'?'aboveBar':'belowBar',shape:e.side==='up'?'arrowUp':'arrowDown',size:.6,text:e.label,color:'#b8a0eb'})):[];
 structureMarkers?.setMarkers([...swings,...marks].sort((a,b)=>a.time-b.time));
 if(($('smart-levels').checked||$('smart-zones').checked)&&quality==='Disponible'){
  const m=marketStructure;
  const levels=$('smart-levels').checked?[[m.support,'Pivot bas','#54c4ba'],[m.resistance,'Pivot haut','#e96883'],[m.profile?.poc,'POC','#e8ad62'],...(m.fib??[]).map(([k,v])=>[v,'Fib '+fmt(k*100,1)+' %','#64748b']),]:[];
  if($('smart-zones').checked)for(const [label,zones] of [['FVG',m.fvgs??[]],['OB estimé',events.filter(e=>e.zone).slice(-2).map(e=>e.zone)]])for(const z of zones)levels.push([z.low,label,'#8a6bb0'],[z.high,'','#8a6bb0']);
  chartPriceLines=levels.filter(([p])=>T.finite(p)).map(([price,title,color])=>candles.createPriceLine({price,title,color,lineWidth:1,lineStyle:2,axisLabelVisible:!!title}));
 }

 $('vwap_session').disabled=S.steps[tf]>=86400;
 for(const key of Object.keys(lines)){lines[key].setData(T.chartSeries(bars.length?f.series:[],S.steps[tf],key));lines[key].applyOptions({visible:$(key).checked&&!$(key).disabled});}
 oscLine.setData(T.chartSeries(bars.length?f.series:[],S.steps[tf],oscMode));
 oscLine.applyOptions({color:oscMode==='rsi14'?'#b8a0eb':'#74a3ed',priceFormat:{type:'price',precision:oscMode==='rsi14'?2:7,minMove:oscMode==='rsi14'?.01:.0000001}});
 $('osc-value').textContent=bars.length?fmt(f.latest[oscMode],oscMode==='rsi14'?2:7):'—';
 if(!bars.length)return;
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
 $('limits').innerHTML=[...data.limits,'BTC et ETH sont des cotations de contexte. Le carnet Kraken est un instantané public distinct du moteur décisionnel ; flux institutionnels indisponibles.'].map(x=>`<li>${esc(x)}</li>`).join('');
 $('quarantine').textContent=JSON.stringify(Object.fromEntries(Object.entries(data.frames).map(([tf,f])=>[tf,{reasons:f.quality.reasons,rows:f.excluded}])),null,2);
}
async function refreshEurUsd(){
 try{
  const response=await fetch(hosted?'/api/fx':'https://api.frankfurter.dev/v1/latest?base=EUR&symbols=USD',{cache:'no-store',signal:AbortSignal.timeout(12000)});
  if(!response.ok)throw Error('FX HTTP '+response.status);
  const fx=T.parseFx(await response.json());if(!fx)throw Error('Taux FX périmé');
  const {rate,date:dateStr}=fx;
  eurUsd=rate;eurUsdFetched=Date.now();fxReferenceDate=dateStr;$('eur-usd').value=fmt(rate,5)+' USD (référence '+dateStr+')';
 }catch(e){eurUsd=null;fxReferenceDate=null;$('eur-usd').value='Indisponible';}
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
  data=withWeekly(next);renderTickers();renderDecision();renderRadar();renderFrames();renderChart();renderLab();renderQuality();renderRisk();
 }catch(e){console.warn('TEL99: actualisation analytique indisponible; snapshot existant conservé',e.message);
 }finally{snapshotBusy=false;}
}
async function refreshQuote(){if(quoteBusy)return;quoteBusy=true;const b=$('refresh-quote');b.disabled=true;b.textContent='Connexion à Kraken…';
 try{const r=await fetch(hosted?'/api/quote':'https://api.kraken.com/0/public/Ticker?pair=TELUSD',{cache:'no-store',signal:AbortSignal.timeout(12000)});if(!r.ok)throw Error('HTTP '+r.status);const j=await r.json();if(j.error?.length)throw Error(j.error.join(', '));const p=T.parseTelTicker(j);if(p===null)throw Error('Paire Kraken ou cours invalide');liveQuote={price:p,bid:Number(Object.values(j.result)[0].b?.[0]),ask:Number(Object.values(j.result)[0].a?.[0]),received:Date.now()/1000};renderTickers();renderDecision();renderRisk();b.textContent='✓ Cours public reçu';
 }catch(e){liveQuote=null;renderTickers();renderDecision();renderRisk();b.textContent='↻ Réessayer le cours';$('freshness-banner').textContent='Cours public indisponible : '+e.message+'. Le snapshot historique reste affiché et conserve son horodatage.';}finally{quoteBusy=false;b.disabled=false;}}
function renderRadarDecision(plans,watch){
 const detailOpen=$('radar-reading').querySelector('details')?.open;
 const reading=window.TEL99Radar.readRadar(data,plans);
 const quote=T.freshQuote(liveQuote)?liveQuote:null;
 const rr=T.finite(watch?.rrNet)?fmt(watch.rrNet,2)+' R':'indisponible';
 const point=p=>p?price(p.level)+' $ · '+esc(p.unit):'—';
 const factors=reading.factors.filter(f=>f.active===true).map(f=>f.id==='convergence'?'Convergence EMA20 15 min / 1 h':f.label);
 const directions=reading.frames.map(f=>`<span><b>${esc(f.unit)}</b> ${esc(f.direction??'—')}</span>`).join('');
 const evidence=reading.factors.map(f=>`<li>${f.active===null?'—':f.active?'✓':'○'} ${esc(f.label)}${f.detail?' · '+esc(f.detail):''}</li>`).join('');
 const execution=watch?.status==='PRÊT À ÉVALUER'?'Contrôles disponibles · évaluation humaine':'Exécution non validée';
 const spread=plans[0]?.spread;
 const liquidity=T.finite(spread)?'Spread '+fmt(spread*100,2)+' % · profondeur non intégrée au scénario':'Spread du scénario indisponible';
 const blockers=reading.blockers;
 renderAnnotated(reading);
 $('radar-reading').innerHTML=`<div class="decision-main"><b>${esc(reading.status)}</b>${reading.status==='ALERTE PRÉCOCE'?'<span class="chip">NON CONFIRMÉE</span>':''}<strong>TEL/USD · ${price(quote?.price??data.frames['15m'].bars.at(-1)?.c)} $</strong></div>
 <div class="decision-meta">Clôture 15 min ${date(reading.closedAt)} UTC · capture ${date(reading.asOf)} UTC · ${reading.factors.length?'données fraîches':'qualité insuffisante'}</div>
 <div class="decision-meta">${quote?'Cotation Kraken reçue '+date(quote.received)+' UTC':'Cours de la dernière clôture 15 min'}</div>
 <div class="radar-directions" aria-label="Directions par unité">${directions}</div>
 <div class="decision-prices"><span>Niveau à surveiller <strong>${point(reading.watch)}</strong></span><span>Invalidation en clôture <strong>${point(reading.invalidation)}</strong></span></div>
 <p class="radar-line"><strong>Facteurs favorables</strong> ${esc(factors.join(' · ')||'Aucun facteur actif vérifié.')}</p>
 <p class="radar-line"><strong>${reading.status==='INVALIDATION'?'Motif':'Confirmation bloquée par'}</strong> ${esc((blockers.find(x=>x==='Confirmation non observée')??blockers[0])||'Aucun blocage détecté par le scénario.')}</p>
 <details class="radar-reasons" ${detailOpen?'open':''}><summary>Facteurs, qualité et conditions</summary>
 <ul>${evidence||reading.frames.map(f=>`<li>${esc(f.unit+' · '+f.quality)}</li>`).join('')}</ul>
 <p>${esc(blockers.join(' · '))}</p>
 ${watch?`<p><strong>${esc(watch.name)}</strong> · ${esc(watch.status)}<br>${esc(watch.condition)}<br>Entrée ${price(watch.entry)} $ · stop ${price(watch.stop)} $ · objectif ${price(watch.target)} $</p>`:''}
 <p>RR net théorique ${rr} · ${execution}<br>Frais d’entrée estimés ${money(watch?.feeEstimate)} · frais personnels non vérifiés<br>${liquidity}</p></details>`;
}
function renderAnnotated(reading){
 const changes=Array.isArray(latestJournalEntry?.changed_factors)?latestJournalEntry.changed_factors:[];
 const changed=latestJournalEntry?`${changes.length?changes.map(esc).join(' · '):'Aucun facteur modifié dans cette observation'} · journal ${date(latestJournalEntry.observed_at)} UTC`:'Journal détaillé indisponible.';
 const blocked=reading.status==='DONNÉES INSUFFISANTES';
 const missing=blocked?'Données actuelles insuffisantes.':(reading.blockers??[]).map(esc).join(' · ')||'Aucun blocage indiqué.';
 const invalidation=!blocked&&reading.invalidation?`${price(reading.invalidation.level)} $ · ${esc(reading.invalidation.unit)}`:'Non disponible';
 $('annotated-summary').innerHTML=`<div><b>Ce qui change</b><span>${changed}</span></div><div><b>Ce qui manque</b><span>${missing}</span></div><div><b>Ce qui invalide</b><span>${invalidation}</span></div>`;
}
function renderLiquidity(){
 const target=$('liquidity-widget'),age=Date.now()/1000-depthReceived;
 if(!depthBook||!T.finite(age)||age<0||age>120){target.innerHTML='<p class="amber-text">Carnet indisponible ou périmé. Actualisez pour obtenir un nouvel instantané.</p>';return;}
 const b=depthBook,fx=T.finite(eurUsd)&&Date.now()-eurUsdFetched<86400000?eurUsd:null;
 const amounts=[100,250,500,1000].map(amount=>{const x=W.buyImpact(b,amount,fx);return `<tr><th scope="row">${amount} €</th><td>${x?price(x.average)+' $':'—'}</td><td>${x?pct(x.slippagePct):'Indisponible'}</td></tr>`;}).join('');
 target.innerHTML=`<p class="radar-caption">Kraken public · reçu ${date(depthReceived)} UTC · 100 niveaux maximum par côté.</p><div class="liquidity-metrics"><span>Meilleur bid <b>${price(b.bid)} $</b></span><span>Meilleur ask <b>${price(b.ask)} $</b></span><span>Spread <b>${price(b.spread)} $ · ${fmt(b.spreadPct,2)} %</b></span><span>Déséquilibre <b>${pct(b.imbalance)}</b></span><span>Profondeur bid <b>${money(b.bidDepth)}</b></span><span>Profondeur ask <b>${money(b.askDepth)}</b></span></div><h3>Impact indicatif à l’achat</h3><div class="table-scroll"><table class="liquidity-table"><thead><tr><th>Montant</th><th>Prix moyen</th><th>Au-delà du meilleur ask</th></tr></thead><tbody>${amounts}</tbody></table></div><p class="radar-caption">Spread rapporté au milieu bid/ask ; déséquilibre calculé sur la valeur en USD des niveaux visibles. Conversion EUR/USD : ${fx?'Frankfurter, référence '+esc(fxReferenceDate):'indisponible'}. Impact hors frais, conversion réelle et spread ; profondeur insuffisante = indisponible. Un carnet peut disparaître avant toute exécution.</p>`;
}
async function refreshDepth(){
 if(depthBusy)return;depthBusy=true;const button=$('liquidity-refresh');button.disabled=true;
 try{
  const response=await fetch(hosted?'/api/depth':'https://api.kraken.com/0/public/Depth?pair=TELUSD&count=100',{cache:'no-store',signal:AbortSignal.timeout(12000)});
  if(!response.ok)throw Error('HTTP '+response.status);
  const book=W.readBook(await response.json());if(!book)throw Error('Carnet invalide');
  depthBook=book;depthReceived=Date.now()/1000;
 }catch{depthBook=null;depthReceived=0;}finally{depthBusy=false;button.disabled=false;renderLiquidity();}
}
function renderMarkets(){
 const target=$('markets-widget');
 const fresh=marketTickers&&W.marketFresh(marketReceived,Date.now()/1000),key=fresh?String(marketReceived):'stale';
 if(target.dataset.rendered===key)return;
 target.dataset.rendered=key;
 if(!fresh){target.innerHTML='<p class="amber-text">Marchés Kraken indisponibles ou périmés. Actualisez pour réessayer.</p>';return;}
 target.innerHTML=`<p class="radar-caption">Réponse Kraken reçue ${date(marketReceived)} UTC. La date du dernier échange n’est pas fournie : sa fraîcheur est inconnue.</p><div class="market-comparison">${marketTickers.map(m=>`<article><h3>${esc(m.pair)}</h3><span>Dernier échange · date inconnue</span><strong>${m.price===null?'Indisponible':fmt(m.price,m.base==='TEL'?6:2)+' '+(m.currency==='EUR'?'€':'$')}</strong><span>Variation depuis 00:00 UTC : ${pct(m.change)}</span><span>Volume 24 h : ${fmt(m.volume,2)} ${esc(m.base)}</span><span>Spread bid/ask : ${m.spread===null?'—':m.spread>0&&m.spread<0.0001?'&lt; 0,0001 %':fmt(m.spread,m.spread<0.01?4:2)+' %'}</span></article>`).join('')}</div><p class="radar-caption">Paires et devises affichées séparément ; spread rapporté au milieu bid/ask. TEL/USDT sur d’autres plateformes : non disponible dans ce flux. Les cotations ne modifient pas le radar Kraken TEL/USD.</p>`;
}
async function refreshMarkets(){
 if(marketBusy)return;marketBusy=true;const button=$('markets-refresh');button.disabled=true;
 try{
  const url=hosted?'/api/markets':'https://api.kraken.com/0/public/Ticker?pair=TELUSD,TELEUR,XBTUSD,ETHUSD';
  const response=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(12000)});
  if(!response.ok)throw Error('HTTP '+response.status);
  const tickers=W.readMarketTickers(await response.json());if(!tickers)throw Error('Données de marché invalides');
  marketTickers=tickers;marketReceived=Date.now()/1000;
 }catch{marketTickers=null;marketReceived=0;}finally{clearTimeout(marketExpiryTimer);if(marketTickers)marketExpiryTimer=setTimeout(renderMarkets,120010);marketBusy=false;button.disabled=false;renderMarkets();}
}
async function showProductVersion(){
 try{const response=await fetch('/version.json',{cache:'no-store',signal:AbortSignal.timeout(8000)});if(!response.ok)throw Error('HTTP');const value=await response.json();if(!/^[a-f0-9]{40}$/.test(value.product_commit))throw Error('Version invalide');$('terminal-version').textContent='Version '+value.product_commit.slice(0,8);}catch{$('terminal-version').textContent='Version non identifiée';}
}
function renderPersonal(){
 const quantity=$('personal-tel').value, invested=$('personal-invested').value;
 const quote=T.freshQuote(liveQuote)?liveQuote.price:null;
 const fx=T.finite(eurUsd)&&Date.now()-eurUsdFetched<86400000?eurUsd:null;
 const result=quantity!==''&&invested!==''?W.accumulation(Number(quantity),Number(invested),quote,fx):null;
 $('personal-result').innerHTML=result?`<div class="personal-values"><span>Prix de revient <b>${fmt(result.averageEur,6)} € / TEL</b></span><span>Valorisation au dernier prix échangé <b>${result.valueUsd===null?'Cours indisponible':money(result.valueUsd)}</b></span><span>Valeur en euros <b>${result.valueEur===null?'Conversion indisponible':fmt(result.valueEur,2)+' €'}</b></span><span>Écart indicatif <b>${result.pnlEur===null?'—':fmt(result.pnlEur,2)+' €'}</b></span></div><p class="radar-caption">${quote?'Dernier prix échangé reçu de Kraken '+date(liveQuote.received)+' UTC ; heure de la transaction non fournie. ':''}Ce n’est pas un prix de vente garanti. Conversion indicative ; frais de vente et fiscalité non inclus.</p>`:'<p class="radar-caption">Saisissez une quantité positive et le total investi en euros.</p>';
}
function renderProspective(report){
 const target=$('prospective-widget');
 const horizons=['1h','4h','24h','7d'].map(key=>{
  const groups=W.horizonGroups(report.horizons?.[key]);
  return `<div><strong>${key}</strong>${groups.map(g=>`<span>${g.count===null?'Indisponible':g.count+' observation(s)'} · ${esc(g.method)}</span><small>${g.meanPct===null?'Variation non disponible':'Variation moyenne du prix : '+pct(g.meanPct)}</small>`).join('')}</div>`;
 }).join('');
 target.innerHTML=`<p><strong>${fmt(report.observations,0)} observations</strong> · ${fmt(report.valid_observations,0)} valides · résumé ${date(report.generated_at)} UTC</p><div class="prospective-horizons">${horizons}</div><p class="radar-caption">Le journal cloud observe le radar sur les captures, sans les paramètres de risque saisis sur cet appareil : il ne peut pas enregistrer une confirmation fondée sur ces paramètres et peut différer de l’écran.</p><p class="radar-caption">Les catégories d’alertes et les versions de stratégie ne sont pas détaillées dans le résumé actuel. Résultats : variations de prix observées, sans ordre ni gain exécuté. Un petit échantillon ne permet pas d’estimer un taux de réussite fiable.</p>`;
}
async function refreshRadarHistory(){
 if(historyBusy)return;historyBusy=true;
 const target=$('radar-history-rows');
 try{
  const response=await fetch('/evaluation/summary.json',{cache:'no-store',signal:AbortSignal.timeout(8000)});
  if(!response.ok)throw Error('HTTP '+response.status);
  const report=await response.json();
  renderProspective(report);
  const rows=Array.isArray(report.recent_decisions)?report.recent_decisions:[];
  latestJournalEntry=rows.reduce((latest,row)=>!latest||row.observed_at>latest.observed_at?row:latest,null);
  target.innerHTML=(rows.length?'<ol>'+rows.slice().reverse().map(r=>`<li><time>${date(r.observed_at)} UTC</time> · ${esc(r.previous_decision??'Première observation')} → <strong>${esc(r.decision)}</strong> · données ${r.data_valid?'valides':'insuffisantes'}${Array.isArray(r.changed_factors)&&r.changed_factors.length?'<br>'+esc(r.changed_factors.join(' · ')):''}</li>`).join('')+'</ol>':'<p>Le journal contient '+fmt(report.observations,0)+' observation(s). Les transitions détaillées apparaissent après les prochaines collectes.</p>')+'<p class="radar-caption">Radar cloud sans paramètres de risque locaux : les confirmations qui en dépendent ne sont pas enregistrées ici.</p>';
  if(data)renderAnnotated(window.TEL99Radar.readRadar(data,scenarioPlans));
 }catch{latestJournalEntry=null;target.textContent='Journal d’évaluation indisponible.';$('prospective-widget').textContent='Journal prospectif indisponible.';if(data)renderAnnotated(window.TEL99Radar.readRadar(data,scenarioPlans));}finally{historyBusy=false;}
}
function renderScenarios(){
 const node=$('conditional-scenarios');if(!node||!data)return;
 const fxOk=T.finite(eurUsd)&&Date.now()-eurUsdFetched<86400000;
 const budget=Number($('budget-eur').value),capital=Number($('capital').value),fee=Number($('fee').value)/100,slip=Number($('slip').value)/100;
 const options={quote:liveQuote,capital:fxOk?Math.min(capital,1000*eurUsd):capital,budgetUsd:fxOk?Math.min(budget,1000)*eurUsd:NaN,fee,slip,tv:data.independent_verification};
 scenarioPlans=window.TEL99Scenarios.generate(data,options);
 const a=window.TEL99Scenarios.allocate(scenarioPlans,options.capital,options.budgetUsd);
 const ready=scenarioPlans.filter(p=>p.status==='PRÊT À ÉVALUER');
 const {status,plan:watch}=window.TEL99Scenarios.summarize(scenarioPlans,requiredDataIssues());
 const blocked=status==='DONNÉES INSUFFISANTES';
 renderRadarDecision(scenarioPlans,watch);

 const expanded=new Set([...node.querySelectorAll('details[data-scenario][open]')].map(x=>x.dataset.scenario));
 node.innerHTML='<p><b>'+ (ready.length?'Scénario prêt à une vérification humaine.':blocked?'Évaluation bloquée par les données.':'Aucun plan admissible à l’exécution.')+'</b> Frais personnels et profondeur non vérifiés. Les niveaux restent des hypothèses ; aucune stratégie validée.</p>'+scenarioPlans.map((p,i)=>`<details class="scenario-card" data-scenario="${p.id}" ${expanded.has(p.id)?'open':''}><summary><b>${esc(p.name)}</b><span class="chip">${esc(p.status)}</span></summary><p>${esc(p.condition)}</p><dl><dt>Entrée limite envisagée</dt><dd>${price(p.entry)} $</dd><dt>Stop théorique</dt><dd>${price(p.stop)} $</dd><dt>Objectif observé</dt><dd>${price(p.target)} $</dd><dt>RR net hypothétique</dt><dd>${fmt(p.rrNet,2)} / minimum 1,5</dd><dt>Quantité individuelle indicative</dt><dd>${fmt(p.qty,2)} TEL</dd><dt>Cash / risque planifié</dt><dd>${money(p.cash)} / ${money(p.risk)}</dd><dt>Frais d’entrée hypothétiques</dt><dd>${money(p.feeEstimate)}</dd><dt>Calcul UTC</dt><dd>${date(p.calculatedAt)}</dd></dl><p>${esc(p.invalidation)}</p><p class="amber-text">${p.reasons.map(esc).join(' · ')}</p><button class="button" data-copy-scenario="${i}" ${p.status==='PRÊT À ÉVALUER'?'':'disabled'}>Copier les paramètres vérifiés</button></details>`).join('')+
 '<details class="plan-method" '+(node.querySelector('.plan-method')?.open?'open':'')+'><summary>Budget, frais et dimensionnement</summary><p>Budget sélectionné : '+fmt(budget,0)+' € · '+esc($('eur-usd').value)+'.</p><p>Hypothèses par côté : frais '+fmt(fee*100,2)+' %, slippage hors spread '+fmt(slip*100,2)+' %. Demi-spread ajouté à chaque côté dans le RR. Spread observé : '+fmt(T.finite(scenarioPlans[0]?.spread)?scenarioPlans[0].spread*100:null,2)+' %. Coûts de conversion EUR non inclus.</p>'+
 '<p><b>Si plusieurs scénarios sont retenus :</b> enveloppe agrégée plafonnée à '+money(options.capital*.0025)+' de perte planifiée et '+money(options.budgetUsd)+' de cash. '+(a.valid&&a.items.length?a.items.map(p=>esc(p.id)+': '+fmt(p.qty,2)+' TEL').join(' · ')+' ; risque total '+money(a.risk)+'.':'Aucune allocation calculable.')+' Ces tailles alternatives sont calculées sans accès aux positions ouvertes. Vérifier la perte latente cumulée sur le capital de travail avant toute utilisation.</p>'+
 '<div class="table-scroll"><table><thead><tr><th>Budget</th><th>USD</th><th>TEL au support*</th><th>Frais entrée*</th></tr></thead><tbody>'+[300,400,500].map(e=>{const p=window.TEL99Scenarios.generate(data,{...options,budgetUsd:fxOk?e*eurUsd:NaN})[0];return '<tr><td>'+e+' €</td><td>'+fmt(fxOk?e*eurUsd:null,2)+'</td><td>'+fmt(p.qty,2)+'</td><td>'+money(p.feeEstimate)+'</td></tr>';}).join('')+'</tbody></table></div><p class="footnote">* Dimensionnement hypothétique limité par le risque, pas investissement de tout le budget. Un stop ne garantit pas le prix de sortie ; une limite sous le marché ne protège pas d’une chute. Réserve long terme exclue.</p></details>';
}
function renderPricePeriod(){document.querySelectorAll('[data-price-days]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.priceDays)===priceDays)));renderRadarCanvas($('radar-price-chart'));}
function bind(){
 $('sidebar-toggle').addEventListener('click',()=>{$('sidebar-toggle').setAttribute('aria-expanded',String($('app-sidebar').classList.toggle('sidebar-open')));});
 bindCardCatalog();
 for(const [id,key] of [['personal-tel','personal-tel'],['personal-invested','personal-invested']]){
  $(id).value=pref(key,'');$(id).addEventListener('input',()=>{save(key,$(id).value);renderPersonal();});
 }
 $('personal-clear').addEventListener('click',()=>{for(const id of ['personal-tel','personal-invested']){$(id).value='';save(id,'');}renderPersonal();});
 $('liquidity-refresh').addEventListener('click',refreshDepth);
 $('markets-refresh').addEventListener('click',refreshMarkets);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden){renderMarkets();refreshMarkets();}});
 renderPersonal();
 $('technical-month').addEventListener('click',()=>{
  $('technical-widget').innerHTML='<p>Note mensuelle indisponible. Historique Kraken trop court pour les indicateurs requis.</p>';
  renderedSmartFrame=undefined;
  document.querySelectorAll('[data-market-panel="technical"] [data-tf]').forEach(b=>{b.classList.remove('selected');b.setAttribute('aria-pressed','false');});
  $('technical-month').setAttribute('aria-pressed','true');
 });
 document.querySelectorAll('[data-open-chart]').forEach(b=>b.addEventListener('click',()=>{tf=b.dataset.openChart;selectMarket('chart');renderChart();$('tel99-chart').scrollIntoView({block:'start'});}));
 document.querySelectorAll('[data-price-days]').forEach(b=>b.addEventListener('click',()=>{priceDays=Number(b.dataset.priceDays);renderPricePeriod();}));
 const resize=new ResizeObserver(entries=>entries.forEach(e=>renderRadarCanvas(e.target)));
 document.querySelectorAll('[data-preview],#radar-price-chart').forEach(c=>resize.observe(c));
 renderPricePeriod();

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
 document.querySelectorAll('[data-tf]').forEach(e=>e.addEventListener('click',()=>{tf=e.dataset.tf;$('technical-month').setAttribute('aria-pressed','false');save('tf',tf);renderChart();}));
 for(const id of ['smart-levels','smart-pivots','smart-zones'])$(id).addEventListener('change',renderChart);
 document.querySelectorAll('[data-market]').forEach(b=>b.addEventListener('click',()=>selectMarket(b.dataset.market)));
 selectMarket('radar');
 $('radar-history').addEventListener('toggle',()=>{if($('radar-history').open)refreshRadarHistory();});
 for(const key of ['ema20','ema50','sma200','vwap_session']){$(key).checked=pref(key,key==='sma200'?'false':'true')==='true';$(key).addEventListener('change',()=>{save(key,$(key).checked);renderChart();});}
 $('chart-window').addEventListener('change',renderChart);
 for(const [id,key] of [['rsi-mode','rsi14'],['macd-mode','macd_hist']])$(id).addEventListener('click',()=>{oscMode=key;$('rsi-mode').classList.toggle('selected',key==='rsi14');$('macd-mode').classList.toggle('selected',key==='macd_hist');renderChart();});
 $('cost-scenario').addEventListener('change',renderExperiments);$('event-tf').addEventListener('change',renderEvents);$('event-family').addEventListener('change',renderEvents);
 $('risk-form').addEventListener('submit',e=>e.preventDefault());$('risk-form').addEventListener('input',renderRisk);
 $('refresh-quote').addEventListener('click',refreshQuote);$('export-data').addEventListener('click',()=>download('TEL99_snapshot.json',data));$('export-lab').addEventListener('click',()=>download('TEL99_laboratoire.json',data.lab));
}
async function start(){try{
 const r=await fetch('data.json?t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('Snapshot HTTP '+r.status);data=await r.json();if(data.schema_version!==1||data.market!=='KRAKEN:TELUSD')throw Error('Schéma ou marché incorrect');
 data=withWeekly(data);
 tf='15m';bind();setupCharts();renderTickers();renderDecision();renderRadar();renderFrames();renderChart();renderLab();renderQuality();
 const l=data.frames['4h'].latest,d=T.safeDecision(data),p=d.status==='DONNÉES INSUFFISANTES'?null:d.plan;$('entry').value=p?(l.close??''):'';$('stop').value=p?.stop??'';$('target').value=p?.target??'';renderRisk();refreshEurUsd();
 $('loading').classList.add('hidden');view(location.hash.slice(1)||'market');
 setInterval(()=>{renderTickers();renderDecision();renderRadar();renderFrames();renderLiquidity();renderMarkets();renderPersonal();if(previousChartAvailability!==chartStatus(data.frames[tf],tf))renderChart();else if(renderedSmartSignature!==JSON.stringify(W.gaugeFreshness(data.frames,data.as_of,Date.now()/1000,window.TEL99Radar.frameCheck)))renderWidgets();$('clock').textContent=new Date().toLocaleTimeString('fr-FR',{timeZone:'UTC'})+' UTC';},15000);
 // Public quote only: never relabel a static analytical snapshot as live.
 refreshQuote();
 setInterval(()=>{if(!document.hidden)refreshQuote();},60000);
 refreshDepth();refreshMarkets();refreshRadarHistory();showProductVersion();
 setInterval(()=>{if(!document.hidden){refreshDepth();refreshMarkets();refreshRadarHistory();}},60000);
 // Only accept a newer same-origin analytical snapshot with unchanged frozen research.
 refreshSnapshot();
 setInterval(refreshSnapshot,60000);
  setInterval(()=>{if(!document.hidden)refreshEurUsd();},3600000);
 $('clock').textContent=new Date().toLocaleTimeString('fr-FR',{timeZone:'UTC'})+' UTC';
 }catch(e){$('loading').classList.add('load-error');$('loading').textContent='Terminal indisponible : '+e.message+'. Servez le dossier avec HTTP et vérifiez data.json.';}}
start();
