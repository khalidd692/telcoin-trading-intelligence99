/* Descriptive Kraken radar. Scenario admissibility remains in scenarios.js. */
(function(root){
'use strict';
const node=typeof module==='object';
const T=node?require('./core.js'):root.TEL99;
const S=node?require('./smartview.js'):root.TEL99SmartView;
const scenarios=node?require('./scenarios.js'):root.TEL99Scenarios;
const {finite,steps}=T;
const statusLabels={EARLY_ALERT:'ALERTE PRÉCOCE',CONFIRMATION:'ACHAT CONFIRMÉ',INVALIDATION:'INVALIDATION'};
function frameCheck(frame,unit,asOf,now){
 const status=T.frameStatus(frame,asOf,now,steps[unit]);
 if(status!=='Disponible')return status;
 if(frame.symbol!=='KRAKEN:TELUSD'||frame.interval!==unit)return 'Provenance incohérente';
 const bars=frame.bars?.slice(-50);
 if(bars?.length!==50||bars.at(-1).t+steps[unit]!==frame.quality.last_close||frame.quality.last_close>asOf||
    bars.some((bar,i)=>![bar.t,bar.o,bar.h,bar.l,bar.c,bar.v].every(finite)||bar.t%steps[unit]!==0||(i>0&&bar.t-bars[i-1].t!==steps[unit])))return 'Clôtures incohérentes';
 return status;
}
function divergence(bars,series){
 const closes=bars.slice(-10),readings=series.slice(-10);
 if(closes.length!==10||readings.length!==10||closes.some((b,i)=>b.t!==readings[i].t||!finite(readings[i].rsi14)))return null;
 const low=(from,to)=>closes.slice(from,to).reduce((lowest,b,i)=>b.c<closes[lowest].c?from+i:lowest,from);
 const old=low(0,5),recent=low(5,10);
 return closes[recent].c<closes[old].c&&readings[recent].rsi14>readings[old].rsi14;
}
function detect(frame,hour,four){
 const {bars,series=[]}=frame;
 const bar=bars.at(-1),prev=bars.at(-2),prevRead=series.at(-2),read=series.at(-1);
 const joined=read?.t===bar.t&&prevRead?.t===prev.t;
 const before={bars:bars.slice(0,-1)},levels=S.marketLevels(before,'15m');
 const priorEvents=S.structureEvents(before,'15m');
 const structure=S.structureEvents(frame,'15m').find(e=>e.time===bar.t&&e.side==='up');
 const held=finite(levels.support)&&bar.l<=levels.support&&bar.c>levels.support&&bar.c>prev.c;
 const levelsByName=[['VWAP','vwap_session'],['EMA20','ema20']].filter(([,key])=>joined&&finite(read[key])&&finite(prevRead[key])&&(key!=='vwap_session'||Math.floor(bar.t/86400)===Math.floor(prev.t/86400)));
 const reclaimed=levelsByName.filter(([,key])=>prev.c<=prevRead[key]&&bar.c>read[key]).map(([name])=>name);
 const bullZones=[...(levels.fvgs??[]).filter(z=>z.side==='hausse').map(z=>({...z,label:'FVG'})),
  ...priorEvents.filter(e=>e.side==='up'&&e.zone).map(e=>({...e.zone,label:'OB estimé'}))];
 const zone=bullZones.find(z=>prev.c>=z.high&&bar.l<=z.high&&bar.c>z.high);
 const vol=bars.slice(-21,-1).reduce((sum,b)=>sum+b.v,0)/20;
 const ratio=finite(vol)&&vol>0?bar.v/vol:null;
 const rsi=divergence(bars,series);
 const aligned=joined&&finite(read.ema20)&&[hour?.close,hour?.ema20,four?.close,four?.ema20].every(finite)?
  [bar.c>read.ema20,hour.close>hour.ema20,four.close>four.ema20]:null;
 const convergence=aligned?aligned[0]&&aligned[1]:null;
 const factors=[
  {id:'structure',label:structure?structure.label+' haussier 15 min':'Cassure de structure 15 min',active:!!structure},
  {id:'support',label:'Défense ou reprise du support 15 min',active:finite(levels.support)?held:null},
  {id:'rsi',label:'Divergence RSI haussière 15 min',active:rsi},
  {id:'volume',label:'Volume 15 min ≥ 1,5×',active:ratio===null?null:ratio>=1.5},
  {id:'convergence',label:'Clôtures au-dessus de leur EMA20 (15 min / 1 h / 4 h)',active:convergence,detail:aligned?.map((a,i)=>['15 min','1 h','4 h'][i]+' '+(a?'↑':'↓')).join(' · ')},
  {id:'reclaim',label:'Reprise '+(reclaimed.join(' / ')||'VWAP ou EMA20'),active:levelsByName.length?!!reclaimed.length:null},
  {id:'zone',label:zone?'Réaction '+zone.label:'Réaction FVG / OB estimé',active:!!zone}
 ];
 const context=structure||held||zone;
 const supporting=ratio>=1.5||rsi===true||convergence===true||reclaimed.length>0;
 return {early:!!(context&&supporting),factors,levels,structure,zone,held};
}
function readRadar(data,plans=[],now=Date.now()/1000){
 const units=Object.keys(steps);
 const frames=units.map(unit=>{
  const frame=data.frames?.[unit];
  const quality=frameCheck(frame,unit,data.as_of,now);
  return {unit,quality,direction:quality==='Disponible'?frame.latest?.trend:null,closedAt:frame?.quality?.last_close};
 });
 const issues=frames.filter(f=>f.quality!=='Disponible').map(f=>f.unit+' · '+f.quality);
 if(data.market!=='KRAKEN:TELUSD'||data.source!=='Kraken public REST / OHLC')issues.unshift('Source Kraken non vérifiée');
 if(now<data.as_of)issues.unshift('Capture datée dans le futur');
 const closedAt=frames[0].closedAt;
 const base={frames,closedAt,asOf:data.as_of,factors:[],watch:null,invalidation:null,blockers:issues,event:null,status:'DONNÉES INSUFFISANTES'};
 if(issues.length)return base;
 const [m,h,f]=units.map(unit=>data.frames[unit]);
 const latestAt=(frame,step,asOf)=>{
  const point=frame.series?.findLast(r=>r.t+step<=asOf);
  const candle=point&&frame.bars.find(b=>b.t===point.t);
  return candle?{ema20:point.ema20,close:candle.c}:null;
 };
 const {early,factors,levels,structure,zone,held}=detect(m,latestAt(h,steps['1h'],closedAt),latestAt(f,steps['4h'],closedAt));
 const previousClose=m.bars.at(-2).t+steps['15m'];
 const preceding=detect({bars:m.bars.slice(0,-1),series:m.series?.slice(0,-1)},
  latestAt(h,steps['1h'],previousClose),latestAt(f,steps['4h'],previousClose));
 const earlyStop=preceding.held?preceding.levels.support:preceding.zone?.low??preceding.levels.support;
 const earlyInvalidated=preceding.early&&finite(earlyStop)&&m.bars.at(-1).c<earlyStop;
 const {plan,reason}=plans.length?scenarios.summarize(plans):{};
 const technicalStop=data.decision?.invalidation;
 const swingInvalidated=data.decision?.status==='INVALIDATION'&&finite(technicalStop)&&f.bars.at(-1).c<technicalStop;
 const invalidated=swingInvalidated||earlyInvalidated;
 const confirmed=plans.find(p=>p.id!=='early'&&p.status==='PRÊT À ÉVALUER'&&p.confirmed&&finite(p.rrNet)&&p.rrNet>=1.5);
 const type=invalidated?'INVALIDATION':confirmed?'CONFIRMATION':early?'EARLY_ALERT':null;
 const watchLevel=confirmed?.entry??(early?(structure?.price??levels.resistance):plan?.entry??levels.resistance);
 const stopLevel=invalidated?(swingInvalidated?technicalStop:earlyStop):confirmed?.stop??(early?(held?levels.support:zone?.low??levels.support):plan?.stop??technicalStop);
 const shortInvalidation=(earlyInvalidated&&!swingInvalidated)||(early&&!confirmed&&!invalidated);
 const invalidation=finite(stopLevel)?{level:stopLevel,unit:shortInvalidation?'15m':'4h'}:null;
 const watch=!invalidated&&finite(watchLevel)?{level:watchLevel,unit:early&&!confirmed?'15m':plan||confirmed?'4h':'15m'}:null;
 const blockers=invalidated?[swingInvalidated?'Clôture 4 h sous le support structurel.':'Clôture 15 min sous l’invalidation de l’alerte de la bougie précédente.']:confirmed?[]:
  plan?.reasons?.length?plan.reasons:[reason||(plans.length?'Aucune confirmation technique et économique vérifiée.':'Confirmation : vérification manuelle nécessaire (cotation, frais personnels, spread et profondeur du carnet).')];
 const candle=swingInvalidated||(!invalidated&&confirmed)?f.quality.last_close:closedAt;
 const event=type?{schema_version:1,id:'KRAKEN:TELUSD:'+type+':'+candle,market:'KRAKEN:TELUSD',type,decision:statusLabels[type],
  confirmed:type==='CONFIRMATION',candle_closed_at:candle,snapshot_at:data.as_of,data_valid:true,watch,invalidation,
  ...(type==='CONFIRMATION'?{scenario_id:confirmed.id,rr_net:confirmed.rrNet,spread:confirmed.spread,fee_estimate:confirmed.feeEstimate}:{}),
  factors:factors.filter(x=>x.active===true).map(x=>x.id),blockers}:null;
 return {...base,status:statusLabels[type]??'ATTENDRE',factors,watch,invalidation,blockers,event};
}
const api={readRadar};
if(node){
 module.exports=api;
 if(require.main===module){
  const snapshot=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
  process.stdout.write(JSON.stringify(readRadar(snapshot,[],Number(process.argv[2]))));
 }
}else root.TEL99Radar=api;
})(typeof window==='object'?window:globalThis);
