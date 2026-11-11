/** Owner-approved Sales path: today -> daily graphs / products / periods. Cache-only. */
import {salesChart} from './china_sales_chart.mjs';
const ROOT='china_agent:sales_ui:v1:',DAILY='china_agent:sales_menu:v2:day:',CHAT=-1004342917488,BOT=8780468043;
const BASIS='FBS created units, all statuses, dedup id; native CNY buyer-discounted amount; not buyouts or all sales models';
const F=new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}),n=v=>F.format(v),ok=v=>typeof v==='number'&&Number.isFinite(v);
const iso=d=>d.toISOString().slice(0,10),today=now=>iso(new Date(now.getTime()+10800000));
const shift=(s,d)=>iso(new Date(Date.parse(s+'T00:00:00Z')+d*86400000));
const dates=(a,b)=>{const out=[];for(let s=a;s<=b&&out.length<62;s=shift(s,1))out.push(s);return out;};
const pct=(v,b)=>!ok(v)||!ok(b)?'н/д':b===0?'нет базы':(v>=b?'+':'')+n((v-b)*100/b)+'%';
const amounts=t=>t?n(t.count)+' шт. · '+n(t.amount_cny)+' CNY':'нет сопоставимых данных';
const change=(a,b)=>a&&b?'заказы '+pct(a.count,b.count)+' · сумма '+pct(a.amount_cny,b.amount_cny):'нет сопоставимых данных';
const good=t=>t&&Number.isInteger(t.count)&&t.count>=0&&ok(t.amount_cny)&&t.amount_cny>=0;
const summaryKeys=(sid)=>({inline_keyboard:[[{text:'Динамика по дням',callback_data:'csl1:'+sid+':days'}],[{text:'По товарам',callback_data:'csl1:'+sid+':products'}],[{text:'Другой период',callback_data:'csl1:'+sid+':period'}],[{text:'Главное меню',callback_data:'csl1:'+sid+':home'}]]});
export function aggregateRows(rows){
 if(!Array.isArray(rows))return null;const ids=new Set(),by={};let amount=0;
 for(const r of rows){if(!Number.isSafeInteger(r.id)||ids.has(r.id)||!Number.isSafeInteger(r.nmId)||r.convertedCurrencyCode!==156||!Number.isInteger(r.convertedPrice)||r.convertedPrice<0)return null;ids.add(r.id);amount+=r.convertedPrice;const k=String(r.nmId),x=by[k]||(by[k]={count:0,minor:0});x.count++;x.minor+=r.convertedPrice;}
 return {totals:{count:rows.length,amount_cny:amount/100},by_nm:Object.fromEntries(Object.entries(by).map(([k,x])=>[k,{count:x.count,amount_cny:x.minor/100}]))};
}
export function verifiedDaily(v,d,now){
 return v?.status==='complete'&&v.cabinet==='token_3'&&v.currency==='CNY'&&v.basis===BASIS&&v.date===d&&d<today(now)&&v.start_msk===d+'T00:00:00+03:00'&&v.end_msk===shift(d,1)+'T00:00:00+03:00'&&Date.parse(v.observed_at)>=Date.parse(v.end_msk)&&v.source?.pagination_complete===true&&good(v.totals)&&v.totals.unknown_amount_ids?.length===0&&v.by_nm;
}
function selected(v,nm){return nm?(v.by_nm[nm]||{count:0,amount_cny:0}):v.totals;}
export function periodTotal(dayMap,start,end,nm){
 const ds=dates(start,end);if(!ds.length||ds.length>31)return null;let count=0,minor=0;
 for(const d of ds){const v=dayMap.get(d);if(!v)return null;const t=selected(v,nm);if(!good(t))return null;count+=t.count;minor+=Math.round(t.amount_cny*100);}
 return {count,amount_cny:minor/100};
}
export async function source(deps,get,ctx,now){
 const catalog=await get('china_agent:prices:v1'),names=new Map();
 if(catalog?.cabinet==='token_3')for(const r of catalog.rows||[])if(Number.isSafeInteger(r.nmID)&&typeof r.vendorCode==='string')names.set(String(r.nmID),r.vendorCode);
 const records=await deps.database('telegram_api_cache?cache_key=like.'+DAILY+'*&select=cache_key,payload&order=cache_key.desc&limit=70');
 const days=new Map(),source_keys=[];
 for(const row of records||[]){const d=row.cache_key.slice(DAILY.length);if(/^\d{4}-\d{2}-\d{2}$/.test(d)&&verifiedDaily(row.payload,d,now)){days.set(d,row.payload);source_keys.push(row.cache_key);for(const nm of Object.keys(row.payload.by_nm))if(!names.has(nm))names.set(nm,'nmID '+nm);}}
 let hourly=null;
 if(ctx.period==='today'){
  const latest=await get('china_agent:hourly_sales_api:v1:latest');
  const key=ctx.source_key||latest?.source_key;
  if(typeof key==='string'&&/^china_agent:hourly_sales_api:v1:snapshot:\d{4}-\d{2}-\d{2}T\d{2}:MSK(?::attempt:\d+)?$/.test(key)){
   const p=await get(key),main=p?.orders?.['0'];
   if(p?.cabinet==='token_3'&&main?.status==='complete'&&main.basis===BASIS&&main.start_msk?.endsWith('T00:00:00+03:00')&&main.end_msk===p.slot_msk&&main.start_msk.slice(0,10)===main.end_msk.slice(0,10)&&good(main.totals)&&!main.totals.unknown_amount_ids?.length){
    const data={};for(const offset of [0,1,7]){const x=p.orders[String(offset)],agg=aggregateRows(x?.rows);if(x?.status==='complete'&&x.basis===BASIS&&agg&&good(x.totals)&&agg.totals.count===x.totals.count&&Math.abs(agg.totals.amount_cny-x.totals.amount_cny)<.005&&Date.parse(main.start_msk)-Date.parse(x.start_msk)===offset*86400000&&Date.parse(main.end_msk)-Date.parse(x.end_msk)===offset*86400000)data[offset]={...agg,last:x.last_completed_hour};}
    if(data[0]){hourly={p,data,key};ctx.source_key=key;source_keys.push(key);}
   }
  }
 }
 return {days,names,hourly,source_keys};
}
function contextTotals(ctx,data){
 if(ctx.period==='today'){
  const h=data.hourly;if(!h)return {current:null,previous:null,week:null,labels:['Вчера','Неделю назад'],window:'Сегодня: нет полного сопоставимого среза'};
  return {current:selected(h.data[0],ctx.nm),previous:h.data[1]?selected(h.data[1],ctx.nm):null,week:h.data[7]?selected(h.data[7],ctx.nm):null,labels:['Вчера','Неделю назад'],window:h.p.orders['0'].start_msk.slice(0,10)+' · 00:00–'+h.p.slot_msk.slice(11,16)+' МСК'};
 }
 const len=dates(ctx.start,ctx.end).length;
 return {current:periodTotal(data.days,ctx.start,ctx.end,ctx.nm),previous:periodTotal(data.days,shift(ctx.start,-len),shift(ctx.end,-len),ctx.nm),week:periodTotal(data.days,shift(ctx.start,-7),shift(ctx.end,-7),ctx.nm),labels:[len===1?'Предыдущий день':'Предыдущие '+len+' дней','Неделей ранее · те же даты со сдвигом7 дней'],window:ctx.start+' — '+ctx.end+' · полные дни МСК'};
}
function lines(ctx,data){
 const t=contextTotals(ctx,data),title=ctx.nm?(data.names.get(ctx.nm)||ctx.nm):'Продажи';
 const out=[title,'Созданные заказы FBS · CNY после скидок WB',t.window,'',amounts(t.current)];
 [t.previous,t.week].forEach((b,i)=>out.push(t.labels[i]+': '+amounts(b),'Изменение: '+change(t.current,b)));
 if(ctx.period==='today'&&data.hourly){const h=data.hourly,age=Date.now()-Date.parse(h.p.observed_at);out.push('Срез: '+h.p.observed_at.slice(0,10)+' '+new Date(Date.parse(h.p.observed_at)+10800000).toISOString().slice(11,16)+' МСК'+(age>80*60000?' · данные отстают':''));}
 return out;
}
const footer='Сумма заказов — не прибыль и не выкупы. Покрытие: FBS; не доказанно весь кабинет.';
export async function renderSales(ctx,data,sid,now=new Date()){
 const b=(text,op)=>({text,callback_data:'csl1:'+sid+':'+op}),home=[b('Главное меню','home')],back=[b('‹ К сводке','summary')];
 const nav=rows=>({inline_keyboard:[...rows,back,home]});
 if(ctx.view==='summary'){
  const text=lines(ctx,data);
  if(ctx.period==='today'&&data.hourly&&!ctx.nm){
   const h=data.hourly,slot=h.p.slot_msk.slice(11,16);
   text.push('','Последний завершённый час · до '+slot);
   const a=h.data[0].last;text.push('Сегодня: '+amounts(good(a)?a:null));
   for(const nday of [1,7]){const z=h.data[nday]?.last;text.push((nday===1?'Вчера':'Неделю назад')+': '+amounts(good(z)?z:null)+'; '+change(good(a)?a:null,good(z)?z:null));}
  }
  text.push('',footer);const markup=summaryKeys(sid);if(ctx.nm)markup.inline_keyboard.splice(2,0,[b('Другой товар','products'),b('Изменить период','period')]);return {text:text.join('\n'),reply_markup:markup};
 }
 if(ctx.view==='period')return {text:'Другой период\nПериод сохранится при переходе к товарам.',reply_markup:nav([[b('Сегодня к текущему часу','today')],[b('Вчера · полный день','yesterday')],[b('Последние 7 полных дней','range7')],[b('Последние 14 полных дней','range14')],[b('Выбрать даты','calendar')]])};
 if(ctx.view==='products')return {text:'По товарам\n'+contextTotals(ctx,data).window+'\nКоличество и сумма — с обеими базами.',reply_markup:nav([[b('Лидеры по сумме заказов','leaders')],[b('Кто дал рост','growth')],[b('Кто дал снижение','decline')],[b('Найти товар по артикулу','search')]])};
 if(ctx.view==='search')return {text:'Найти товар по артикулу\nОтветьте на это сообщение: введите артикул или его часть, например143.',reply_markup:{force_reply:true,selective:true,input_field_placeholder:'Артикул товара'}};
 if(ctx.view==='calendar'){
  const month=ctx.month||today(now).slice(0,7),first=month+'-01',end=shift((Number(month.slice(5))===12?String(Number(month.slice(0,4))+1)+'-01':month.slice(0,4)+'-'+String(Number(month.slice(5))+1).padStart(2,'0'))+'-01',-1);
  let row=[],rows=[],weekday=(new Date(first+'T00:00:00Z').getUTCDay()+6)%7;
  for(let i=0;i<weekday;i++)row.push(b('·','noop'));
  for(const d of dates(first,end)){const allowed=d<today(now)&&d>=shift(today(now),-60);row.push(b(allowed?String(Number(d.slice(8))):'·',allowed?'date'+d.replaceAll('-',''):'noop'));if(row.length===7){rows.push(row);row=[];}}
  if(row.length)rows.push(row);
  const prev=shift(first,-1).slice(0,7),next=shift(end,1).slice(0,7);
  rows.push([b('‹ '+prev,'month'+prev.replace('-','')),b(next+' ›','month'+next.replace('-',''))]);
  return {text:'Выберите '+(ctx.dateStart?'конец':'начало')+' периода · '+month+'\nПн Вт Ср Чт Пт Сб Вс'+(ctx.dateStart?'\nНачало: '+ctx.dateStart:''),reply_markup:nav(rows)};
 }
 if(ctx.view==='dateReview')return {text:'Период: '+ctx.dateStart+' — '+ctx.dateEnd+'\nПолные дни МСК.',reply_markup:nav([[b('Показать','showDates')],[b('Изменить даты','calendar')]])};
 if(ctx.view==='list'){
  const ids=[...data.names.keys()],computed=ids.map(nm=>{const t=contextTotals({...ctx,nm},data);return {nm,article:data.names.get(nm),...t,delta:t.current&&t.previous?t.current.amount_cny-t.previous.amount_cny:null};});
  let rows=ctx.query?computed.filter(x=>x.article.toLowerCase().includes(ctx.query.toLowerCase())):computed.filter(x=>x.current?.count||x.previous?.count||x.week?.count);
  if(ctx.sort==='growth')rows=rows.filter(x=>x.delta>0).sort((a,b)=>b.delta-a.delta);
  else if(ctx.sort==='decline')rows=rows.filter(x=>x.delta<0).sort((a,b)=>a.delta-b.delta);
  else rows.sort((a,b)=>(b.current?.amount_cny||0)-(a.current?.amount_cny||0));
  const page=Math.max(0,ctx.page||0),selectedRows=rows.slice(page*5,page*5+5),out=['По товарам · '+(ctx.query?'поиск «'+ctx.query+'»':ctx.sort==='growth'?'вклад в рост':ctx.sort==='decline'?'вклад в снижение':'лидеры по сумме'),contextTotals(ctx,data).window];
  for(const x of selectedRows)out.push('',x.article+': '+amounts(x.current),'К предыдущей базе: '+change(x.current,x.previous),'К неделе: '+change(x.current,x.week)+(x.delta!==null?'\nВклад к предыдущей базе: '+(x.delta>=0?'+':'')+n(x.delta)+' CNY; '+(x.current.count-x.previous.count>=0?'+':'')+(x.current.count-x.previous.count)+' шт.':''));
  if(!rows.length)out.push('Нет совпадений либо нет сопоставимых данных для выбранного списка.');
  const buttons=selectedRows.map(x=>[b(x.article,'item'+x.nm)]),paging=[];
  if(page>0)paging.push(b('‹ Назад','page'+(page-1)));if((page+1)*5<rows.length)paging.push(b('Далее ›','page'+(page+1)));if(paging.length)buttons.push(paging);
  buttons.push([b('Другой товар','products'),b('Изменить период','period')]);return {text:out.join('\n'),reply_markup:nav(buttons)};
 }
 if(['days','table'].includes(ctx.view)){
  if(!ctx.start||ctx.period==='today'){ctx.period='range';ctx.start=shift(today(now),-14);ctx.end=shift(today(now),-1);}
  const points=dates(ctx.start,ctx.end).map(date=>{const d=data.days.get(date),t=d?selected(d,ctx.nm):null;return {date,count:t?.count??null,amount_cny:t?.amount_cny??null};});
  const rows=[[b('7 дней','graph7'),b('14 дней','graph14'),b('Другие даты','calendar')],[b('Таблица по дням','table'),b('Сравнить периоды','compare')]];
  if(ctx.nm)rows.push([b('Другой товар','products'),b('Изменить период','period')]);
  if(ctx.view==='days'){
   const missing=points.filter(p=>p.count===null).length;
   return {text:((ctx.nm?data.names.get(ctx.nm)+'\n':'')+'Динамика по дням · '+ctx.start+' — '+ctx.end+'\nДва графика: количество и сумма созданных FBS-заказов, CNY после скидок WB.\n'+(missing?'Нет данных за '+missing+' дней; пропуски не заменены нулями.':'Все дни завершены, МСК.')+'\n'+footer).slice(0,950),photo:await salesChart(points),reply_markup:nav(rows)};
  }
  const page=ctx.page||0,out=['Таблица по дням · '+(ctx.nm?data.names.get(ctx.nm):'все товары')];
  for(const p of points.slice(page*5,page*5+5)){const a=data.days.get(p.date),prev=data.days.get(shift(p.date,-1)),week=data.days.get(shift(p.date,-7)),t=a?selected(a,ctx.nm):null;out.push('',p.date+': '+amounts(t),'К предыдущему дню: '+change(t,prev?selected(prev,ctx.nm):null),'К неделе: '+change(t,week?selected(week,ctx.nm):null));}
  const paging=[];if(page>0)paging.push(b('‹','tablepage'+(page-1)));if((page+1)*5<points.length)paging.push(b('›','tablepage'+(page+1)));if(paging.length)rows.unshift(paging);
  rows.push([b('‹ К графикам','days'),b('Сегодня','today')]);
  return {text:out.join('\n'),reply_markup:nav(rows)};
 }
 throw Error('Unknown sales view');
}
function transition(old,op,now){
 const c={...old};delete c.pending;const setRange=k=>{c.period='range';c.start=shift(today(now),-k);c.end=shift(today(now),-1);delete c.source_key;};
 if(op==='summary'||op==='compare'){c.view='summary';}
 else if(op==='today'){c.period='today';delete c.source_key;c.view='summary';}
 else if(op==='days'){c.view='days';if(c.period==='today')setRange(14);}
 else if(op==='table'){c.view='table';c.page=0;}
 else if(/^tablepage\d+$/.test(op)){c.view='table';c.page=Number(op.slice(9));}
 else if(op==='products'){delete c.nm;c.view='products';}
 else if(['leaders','growth','decline'].includes(op)){c.view='list';c.sort=op;c.page=0;delete c.query;}
 else if(/^page\d+$/.test(op)){c.view='list';c.page=Number(op.slice(4));}
 else if(/^item\d{5,12}$/.test(op)){c.nm=op.slice(4);c.view='summary';}
 else if(op==='period'){c.view='period';}
 else if(op==='yesterday'){setRange(1);c.view='summary';}
 else if(/^range(7|14)$/.test(op)){setRange(Number(op.slice(5)));c.view='summary';}
 else if(/^graph(7|14)$/.test(op)){setRange(Number(op.slice(5)));c.view='days';}
 else if(op==='calendar'){c.view='calendar';c.month=today(now).slice(0,7);delete c.dateStart;delete c.dateEnd;}
 else if(/^month\d{6}$/.test(op)){c.view='calendar';c.month=op.slice(5,9)+'-'+op.slice(9);if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(c.month))throw Error('Wrong month');}
 else if(/^date\d{8}$/.test(op)){const d=op.slice(4,8)+'-'+op.slice(8,10)+'-'+op.slice(10);if(d>=today(now)||d<shift(today(now),-60)||iso(new Date(d+'T00:00:00Z'))!==d)throw Error('Wrong date');if(!c.dateStart){c.dateStart=d;c.view='calendar';}else {if(d<c.dateStart||dates(c.dateStart,d).length>31)throw Error('Выберите конец не раньше начала, максимум31день.');c.dateEnd=d;c.view='dateReview';}}
 else if(op==='showDates'){if(!c.dateStart||!c.dateEnd)throw Error('Dates required');c.period='range';c.start=c.dateStart;c.end=c.dateEnd;delete c.source_key;c.view='summary';}
 else if(op==='search'){c.view='search';}
 else if(op==='home'){c.view='home';}
 else if(op==='noop')return old;
 else throw Error('Unknown navigation');
 return c;
}
export async function handleSalesPath(config,update,deps){
 const cb=update.callback_query,m=cb?.message||update.message,actor=cb?.from||m?.from;
 const text=update.message?.text?.trim(),initial=['📊 Продажи','Продажи'].includes(text)||cb?.data==='cmn1:sales'||cb?.data==='cmn1:dynamic';
 const match=/^csl1:([a-f0-9]{16}):([A-Za-z0-9]+)$/.exec(cb?.data||'');
 const possibleReply=!cb&&m?.reply_to_message?.from?.id===BOT&&typeof text==='string'&&text.length<=80;
 if(!initial&&!match&&!possibleReply)return null;
 if(!config.active||config.chat_id!==CHAT||config.bot_id!==BOT||!Number.isSafeInteger(update.update_id)||update.update_id<0||m?.chat?.id!==CHAT||!['group','supergroup'].includes(m.chat.type)||!Number.isSafeInteger(actor?.id)||actor.id<=0||actor.is_bot!==false||m.sender_chat||m.forward_origin||(cb&&m.from?.id!==BOT))return new Response('OK');
 const get=async k=>(await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(k)+'&select=payload&limit=1'))?.[0]?.payload;
 const insert=async(k,v)=>!!(await deps.database('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:k,payload:v,expires_at:'2036-11-11T00:00:00Z'},'resolution=ignore-duplicates,return=representation'))?.length;
 const put=async(k,v)=>{if((await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(k),'PATCH',{payload:v,updated_at:new Date().toISOString()},'return=representation'))?.length!==1)throw Error('Sales state unavailable');};
 if((await get('china_agent:main_menu:v1:policy'))?.enabled!==true)return null;
 const pending=possibleReply?await get(ROOT+'input:'+actor.id):null;
 if(!initial&&!match&&pending?.message_id!==m.reply_to_message.message_id)return null;
 const member=await deps.telegram('getChatMember',{chat_id:CHAT,user_id:actor.id});
 if(member.user?.id!==actor.id||member.user.is_bot!==false||!(['creator','administrator','member'].includes(member.status)||(member.status==='restricted'&&member.is_member===true)))return new Response('OK');
 const answer=t=>cb?Response.json({method:'answerCallbackQuery',callback_query_id:cb.id,text:t,show_alert:!!t}):new Response('OK');
 const key=ROOT+'delivery:'+update.update_id;if(await get(key))return answer('');
 let ctx={period:'today',view:'summary'},now=deps.now?deps.now():new Date();
 if(match){const s=await get(ROOT+'session:'+match[1]);if(!s||s.actor!==actor.id||s.message_id!==m.message_id||Date.parse(s.expires_at)<=now.getTime())return answer('Откройте «Продажи» своей кнопкой меню.');try{ctx=transition(s.context,match[2],now);}catch(e){return answer(e.message);}if(match[2]==='noop')return answer('');}
 else if(pending?.message_id===m.reply_to_message?.message_id&&!initial){if(Date.parse(pending.expires_at)<=now.getTime())return null;ctx={...pending.context,view:'list',query:text,sort:'leaders',page:0};}
 else if(cb?.data==='cmn1:dynamic'){ctx=transition(ctx,'days',now);}
 const data=await source(deps,get,ctx,now);
 if(ctx.nm&&!data.names.has(ctx.nm))return answer('Товар не найден в проверенном каталоге.');
 const sid=[...crypto.getRandomValues(new Uint8Array(8))].map(n=>n.toString(16).padStart(2,'0')).join('');
 let view=ctx.view==='home'?{text:'Главное меню\nВыберите раздел:',reply_markup:{inline_keyboard:[[{text:'📊 Продажи',callback_data:'cmn1:sales'}],[{text:'📣 Реклама',callback_data:'cmn1:ads'}]]}}:await renderSales(ctx,data,sid,now);
 if(!await insert(ROOT+'session:'+sid,{actor:actor.id,context:ctx,expires_at:new Date(now.getTime()+86400000).toISOString()}))throw Error('Sales session claimed');
 const entry={status:'sending',actor:actor.id,input_message_id:m.message_id,op:ctx.view,source_keys:data.source_keys,wb_writes:0};
 if(!await insert(key,entry))return answer('');
 let receipt;
 try{
  const markup=view.reply_markup,base={chat_id:CHAT,reply_markup:markup};
  if(view.photo)receipt=await deps.telegram(cb?'editMessageMedia':'sendPhoto',{...base,...(cb?{message_id:m.message_id,media:{type:'photo',media:'attach://chart',caption:view.text}}:{caption:view.text}),photo_bytes:view.photo});
  else if(cb&&!m.photo)receipt=await deps.telegram('editMessageText',{...base,message_id:m.message_id,text:view.text});
  else {const name=String(actor.first_name||'Участник');receipt=await deps.telegram('sendMessage',{...base,text:ctx.view==='search'?name+', '+view.text:view.text,...(ctx.view==='search'?{entities:[{type:'text_mention',offset:0,length:name.length,user:{id:actor.id,first_name:name,is_bot:false}}]}:{})});}
  if(receipt?.chat?.id!==CHAT||receipt?.from?.id!==BOT||!Number.isSafeInteger(receipt.message_id))throw Error('Sales delivery receipt mismatch');
 }catch(e){await put(key,{...entry,status:'uncertain'});throw e;}
 await put(ROOT+'session:'+sid,{actor:actor.id,context:ctx,message_id:receipt.message_id,expires_at:new Date(now.getTime()+86400000).toISOString()});
 await put(key,{...entry,status:'sent',message_id:receipt.message_id,receipt});
 if(cb&&m.photo&&!view.photo){try{await deps.telegram('editMessageReplyMarkup',{chat_id:CHAT,message_id:m.message_id,reply_markup:{inline_keyboard:[]}});}catch{}}
 if(ctx.view==='search'){const value={message_id:receipt.message_id,context:ctx,expires_at:new Date(now.getTime()+15*60000).toISOString()};const k=ROOT+'input:'+actor.id;if(await get(k))await put(k,value);else await insert(k,value);}
 return answer('');
}
