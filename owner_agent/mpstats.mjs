import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
const execute=promisify(execFile);
export const MPSTATS_TOOL={type:'function',name:'mpstats_products',description:'Primary MPStats exact-period product statistics: all three cabinets by default. Reuses validated cache, automatically fetches missing reports from MPStats and saves them. Includes complete returned-catalog pagination, totals and paged product rows. Read missing reasons per cabinet. Never treat for_pay as own net profit, orders as sales, or catalog completeness as excluded-product coverage. Use another equal-length period for deterioration comparison.',strict:false,parameters:{type:'object',properties:{from:{type:'string'},to:{type:'string'},cabinet:{type:'string',enum:['token_1','token_2','token_3']},offset:{type:'integer'},limit:{type:'integer'}},required:['from','to'],additionalProperties:false}};
export function currentPeriod(question,now=new Date()) {
 if(!/последн|актуаль|свеж|сегодня|вчера/iu.test(question)||/\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}|\d{1,2}\s+(?:январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр)/iu.test(question))return null;
 const day=now.toLocaleDateString('sv-SE',{timeZone:'Europe/Moscow'});
 const end=new Date(day+'T00:00:00Z');end.setUTCDate(end.getUTCDate()-1);
 const start=new Date(end);if(!/вчера/iu.test(question)||/недел|семь|7\s*дн/iu.test(question))start.setUTCDate(start.getUTCDate()-6);
 return {from:start.toISOString().slice(0,10),to:end.toISOString().slice(0,10)};
}
export function previousPeriod(period) {
 const a=new Date(period.from+'T00:00:00Z'),b=new Date(period.to+'T00:00:00Z');
 const length=(b-a)/86400000+1;
 return {from:new Date(+a-length*86400000).toISOString().slice(0,10),to:new Date(+a-86400000).toISOString().slice(0,10)};
}
export function unverifiedProfitClaim(answer) {
 return answer.split(/[.!?\n]+/u).some(s=>/прибыл/iu.test(s)&&/for_pay|рост|росл|сниж|увелич|улучш|ухудш|паден|упал|руб|₽|\d/iu.test(s)&&!/нельзя|недостат|неизвест|подтвержд|рассчит|провер|требу|себестоим|не являет|не установлен/iu.test(s));
}
export function comparisonFacts(prepared,current,previous) {
 const labels={token_1:'ООО',token_2:'ИП',token_3:'Китай'};
 const periods=p=>prepared.filter(x=>x.requested.from===p.from&&x.requested.to===p.to).flatMap(x=>x.result.rows??[]);
 const nowRows=periods(current),beforeRows=periods(previous);
 return [...new Set([...nowRows,...beforeRows].map(x=>x.cabinet))].map(cabinet=>{
  const after=nowRows.find(x=>x.cabinet===cabinet),before=beforeRows.find(x=>x.cabinet===cabinet);
  const metrics={};
  for(const field of ['sales_count','orders_count','orders','returns_count']){
   const a=before?.available?before.totals?.[field]?.value:null,b=after?.available?after.totals?.[field]?.value:null;
   const known=typeof a==='number'&&Number.isFinite(a)&&typeof b==='number'&&Number.isFinite(b);
   metrics[field]={previous:a??null,current:b??null,delta:known?b-a:null,change_pct:known&&a!==0?(b/a-1)*100:null,zero_baseline:known&&a===0};
  }
  return {cabinet,label:labels[cabinet],current_available:after?.available===true,previous_available:before?.available===true,metrics};
 });
}
export function renderComparison(facts,current,previous,analysis) {
 const labels={sales_count:'Продажи',orders_count:'Статистические заказы',orders:'Заказы воронки',returns_count:'Возвраты'};
 const f=x=>x==null?'нет данных':Number(x.toFixed(1)).toLocaleString('ru-RU');
 const rows=facts.map(row=>row.label+':\n'+Object.entries(row.metrics).map(([k,m])=>{
  const delta=m.delta==null?'':`; изменение ${m.delta>0?'+':''}${f(m.delta)} шт.`;
  const pct=m.change_pct==null?(m.zero_baseline?'; процент не определён при нулевой базе':''):`; ${m.change_pct>0?'+':''}${f(m.change_pct)}%`;
  return `${labels[k]}: ${f(m.previous)} → ${f(m.current)} шт.${delta}${pct}`;
 }).join('\n')).join('\n\n');
 const directions=[['sales_count','Продажи'],['orders_count','Статистические заказы'],['returns_count','Возвраты']].map(([key,label])=>{
  const names=sign=>facts.filter(x=>x.metrics[key].delta!=null&&Math.sign(x.metrics[key].delta)===sign).map(x=>x.label).join(', ');
  const missing=facts.filter(x=>x.metrics[key].delta==null).map(x=>x.label).join(', ');
  return `${label}: снижение — ${names(-1)||'не выявлено'}; рост — ${names(1)||'не выявлен'}${names(0)?'; без изменений — '+names(0):''}${missing?'; недостаточно данных — '+missing:''}.`;
 }).join('\n');
 return `Сравнение ${current.from} — ${current.to} с ${previous.from} — ${previous.to}. В строках: предыдущий период → текущий.\n\n${rows}\n\n${directions}\n\nЧто проверить дальше: ${analysis}\n\nСобственная чистая прибыль не подтверждена. Выплата for_pay не заменяет прибыль: нужны проверенная денежная база, собственная себестоимость и резерв. Итоги относятся к выданному каталогу MPStats; покрытие исключённых карточек и причины изменений отдельно не подтверждены.`;
}
export function mpstatsReader(db,{collect=async scope=>{
 const {stdout}=await execute(process.env.OWNER_PYTHON||'python',[new URL('./mpstats_collect.py',import.meta.url).pathname.replace(/^\/(\w:)/,'$1'),JSON.stringify(scope)],{timeout:240000,maxBuffer:100000,windowsHide:true});
 return JSON.parse(stdout.trim());
}}={}) {
 let refreshed=0;
 return async args=>{
  if(!args||typeof args!=='object')throw new Error('Invalid MPStats scope');
  const clean=Object.fromEntries(Object.entries(args).filter(([k])=>Object.hasOwn(MPSTATS_TOOL.parameters.properties,k)));
  const a=new Date(clean.from+'T00:00:00Z'),b=new Date(clean.to+'T00:00:00Z');
  const today=new Date().toLocaleDateString('sv-SE',{timeZone:'Europe/Moscow'});
  if(!/^\d{4}-\d{2}-\d{2}$/.test(clean.from??'')||!/^\d{4}-\d{2}-\d{2}$/.test(clean.to??'')||!Number.isFinite(+a)||!Number.isFinite(+b)||b<a||b-a>30*86400000||clean.to>=today)throw new Error('Exact completed period of up to31 days required');
  if(clean.cabinet&&!['token_1','token_2','token_3'].includes(clean.cabinet))throw new Error('Unknown cabinet');
  const read=()=>db.request('rpc/owner_agent_mpstats_products',{method:'POST',body:{args:clean}});
  let result=await read();
  const missing=(result.rows??[]).filter(r=>!r.available).map(r=>r.cabinet);
  if(missing.length){
   if(refreshed+missing.length>6)return {...result,refresh:{status:'dialogue_collection_budget_reached'}};
   refreshed+=missing.length;
   let refresh;
   try{refresh=await collect({from:clean.from,to:clean.to,cabinets:missing});}catch{refresh={status:'collection_transport_unavailable'};}
   result=await read();result.refresh=refresh;
  }
  return result;
 };
}
