/** Advertising navigation: read-only conversion cache and explicitly requested analysis. */
import {salesChart} from './china_sales_chart.mjs';
const ROOT='china_agent:advertising_ui:v1:',CHAT=-1004342917488,BOT=8780468043;
const F=new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}),fmt=n=>F.format(n);
const day=d=>new Date(d.getTime()+10800000).toISOString().slice(0,10);
const shift=(d,n)=>new Date(Date.parse(d+'T00:00:00Z')+n*86400000).toISOString().slice(0,10);
const dates=(a,b)=>{const out=[];for(let d=a;d<=b&&out.length<32;d=shift(d,1))out.push(d);return out;};
const finite=v=>typeof v==='number'&&Number.isFinite(v)&&v>=0;
const valid=r=>r&&finite(r.clicks)&&finite(r.orders);
const cr=r=>valid(r)&&r.clicks>0?r.orders*100/r.clicks:null;
const pct=v=>v===null?'нет знаменателя':fmt(v)+'%';
const stamp=v=>Number.isFinite(Date.parse(v))?new Date(Date.parse(v)+10800000).toISOString().slice(0,16).replace('T',' ')+' МСК':'время не подтверждено';
const home={text:'‹ Главное меню',callback_data:'cmn1:home'},ads={text:'‹ Реклама',callback_data:'cmn1:ads'};
export function advertisingMenu(){return {text:'Реклама\nЧто хотите посмотреть?',reply_markup:{inline_keyboard:[
 [{text:'Предложить кандидатов',callback_data:'cmn1:candidates'}],
 [{text:'Конверсии и воронка',callback_data:'cmn1:conversions'}],
 [{text:'Кто вырос',callback_data:'cmn1:growth'}],
 [{text:'Кто упал',callback_data:'cmn1:decline'}],[home]]},source_keys:[]};}
export function candidateRequest(kind='all'){
 const scope={all:'Все четыре направления: повышение ставок, добавление новых товаров, снижение ставок, исключение товаров / завершение РК.',add:'Новые товары для добавления в рекламу по всему каталогу.',raise:'Новые повышения ставок.',reduce:'Новые снижения ставок.',exclude:'Новые исключения товаров / завершения РК.'}[kind];
 if(!scope)throw Error('Unknown candidate filter');
 return 'Предложи новых кандидатов для рекламы китайского кабинета. '+scope+' Только анализ, grants_action_permission=false: никаких WB изменений. Используй завершённые дни после последнего verified изменения, текущие точные ставку/минимум/шаг/цену/COGS/собственный выкуп/МСК минус резерв/опубликованный WB остаток и трёхдневный резерв по фактическим расходам. 143 и 590 не трогать, уже повышенные сегодня ставки повторно не повышать даже в другой РК. Выполненное не предлагать заново. Краткие конкретные предложения с РК, размещением, точным изменением и условием оценки; больше 5 товаров — PNG. Проверка неполная — укажи конкретный пробел, не утверждай отсутствие кандидатов. Готовый план привяжи к фактическому сообщению, hash и сроку; выполнение только после отдельного подтверждения человеком штатным способом.';
}
function normalizedGeneral(r){return r?.scope==='all_sources'?{clicks:r.clicks,orders:r.orders,carts:r.cart_count}:null;}
function sum(rows){if(!rows.length||rows.some(r=>!valid(r)))return null;return rows.reduce((a,r)=>({clicks:a.clicks+r.clicks,orders:a.orders+r.orders,carts:finite(a.carts)&&finite(r.carts)?a.carts+r.carts:null}),{clicks:0,orders:0,carts:0});}
export function dailyPoints(cache,ctx){
 return dates(ctx.start,ctx.end).map(date=>{
  if(ctx.kind==='general'){
   const rows=(cache.general_days||[]).filter(r=>r.date===date&&r.nm===ctx.nm&&r.metrics?.period_from===date&&r.metrics?.period_to===date);
   return {date,...(rows.length===1?normalizedGeneral(rows[0].metrics):{}),source_keys:rows.map(r=>r.source_key),observed_at:rows[0]?.observed_at,missing:rows.length!==1};
  }
  const rows=(cache.daily||[]).filter(r=>r.date===date&&(!ctx.cid||r.campaign===ctx.cid));
  const total=sum(rows),expected=[...new Set(rows.flatMap(r=>r.expected_ids||[]).map(String))],seen=new Set(rows.map(r=>r.campaign));
  const missing=ctx.cid?!rows.length:!rows.length||expected.some(id=>!seen.has(id))||rows.some(r=>r.archived_missing?.length);
  return {date,...(total||{}),source_keys:[...new Set(rows.map(r=>r.source_key))],observed_at:rows.map(r=>r.observed_at).sort().at(-1),missing:missing||!total};
 });
}
function headline(r,kind){return !valid(r)?'нет сопоставимых данных':(kind==='general'?'Открытия: ':'Клики: ')+fmt(r.clicks)+' · корзины: '+(finite(r.carts)?fmt(r.carts):'н/д')+' · заказы: '+fmt(r.orders)+' · CR '+pct(cr(r));}
export function hourlyRows(cache,ctx){
 const current=(cache.hourly||[]).find(r=>r.offset===0);
 return [0,1,7].map(off=>{
  const h=(cache.hourly||[]).find(r=>r.offset===off);
  if(!h||!current||Date.parse(current.slot_msk)-Date.parse(h.slot_msk)!==off*86400000)return {offset:off,missing:true};
  const observed=ctx.kind==='general'?h.general?.observed_at:h.ad_observed_at;
  const curObserved=ctx.kind==='general'?current.general?.observed_at:current.ad_observed_at;
  const compatible=off===0||Math.abs(Date.parse(curObserved)-Date.parse(observed)-off*86400000)<=600000;
  let metrics=null,missing=!compatible;
  if(ctx.kind==='general'){
   const row=h.general?.status==='complete'?h.general.rows?.find(r=>String(r.nm_id)===ctx.nm):null;
   const selected=row?.selected,date=h.slot_msk.slice(0,10);
   if(selected?.period_from===date&&selected.period_to===date)metrics=normalizedGeneral(selected);
   else missing=true;
  }else{
   const rows=(h.ad_rows||[]).filter(r=>!ctx.cid||String(r.campaign)===ctx.cid);metrics=sum(rows);
   missing ||= ctx.cid?!rows.length:h.ad_status!=='complete'||h.ad_missing?.length>0;
  }
  return {offset:off,...(metrics||{}),slot_msk:h.slot_msk,observed_at:observed,source_key:h.source_key,missing:missing||!valid(metrics)};
 });
}
export async function conversionView(cache,ctx,sid,now){
 const b=(text,op)=>({text,callback_data:'cam1:'+sid+':'+op}),nav=rows=>({inline_keyboard:[...rows,[ads],[home]]});
 if(ctx.view==='types')return {text:'Конверсии и воронка\nРекламная конверсия и общая воронка — отдельные источники.',reply_markup:nav([[b('Рекламная конверсия','ad')],[b('Общая воронка товара','general')]])};
 const general=ctx.kind==='general';
 const products=[...new Map([...(cache.general_days||[]).map(r=>[r.nm,r.article]),...(cache.hourly||[]).flatMap(h=>(h.general?.rows||[]).map(r=>[String(r.nm_id),r.article]))]).entries()];
 if(ctx.view==='objects'){
  const rows=general?products.map(([nm,article])=>[b(article||nm,'nm'+nm)]):[[b('Все РК · доступное покрытие','cidAll')],...[...new Set([...(cache.daily||[]).map(r=>r.campaign),...(cache.hourly||[]).flatMap(h=>(h.ad_rows||[]).map(r=>String(r.campaign)))])].sort().slice((ctx.page||0)*8,(ctx.page||0)*8+8).map(cid=>[b('РК '+cid,'cid'+cid)])];
  if(!general){const count=new Set((cache.daily||[]).map(r=>r.campaign)).size;if(ctx.page>0)rows.push([b('‹ Предыдущие','page'+(ctx.page-1))]);if(((ctx.page||0)+1)*8<count)rows.push([b('Следующие ›','page'+((ctx.page||0)+1))]);}
  return {text:general?'Общая воронка\nВыберите товар. Доступно только сохранённое покрытие; недоступные товары не считаются нулевыми.':'Рекламная конверсия\nВсе доступные РК или одна РК. Заказы — атрибутированные, не доказанно уникальные между РК.',reply_markup:nav([...rows,[b('‹ Источники','types')]])};
 }
 if(ctx.view==='period')return {text:(general?'Общая воронка · '+(products.find(p=>p[0]===ctx.nm)?.[1]||ctx.nm):'Рекламная конверсия · '+(ctx.cid?'РК '+ctx.cid:'все доступные РК'))+'\nВыберите период.',reply_markup:nav([[b('7 полных дней','range7')],[b('14 полных дней','range14')],[b('Выбрать даты','calendar')],[b('Сегодня к тому же часу','today')],[b('Другой товар / РК','objects')]])};
 if(ctx.view==='calendar'){
  const month=ctx.month,first=month+'-01',last=shift((month.endsWith('-12')?String(+month.slice(0,4)+1)+'-01':month.slice(0,5)+String(+month.slice(5)+1).padStart(2,'0'))+'-01',-1),rows=[],row=[];
  for(let i=0;i<(new Date(first+'T00:00:00Z').getUTCDay()+6)%7;i++)row.push(b('·','noop'));
  for(const d of dates(first,last)){row.push(b(d<day(now)&&d>=shift(day(now),-60)?String(+d.slice(8)):'·',d<day(now)&&d>=shift(day(now),-60)?'date'+d.replaceAll('-',''):'noop'));if(row.length===7){rows.push(row.splice(0));}}
  if(row.length)rows.push(row);
  rows.push([b('‹ Месяц','month'+shift(first,-1).slice(0,7).replace('-','')),b('Месяц ›','month'+shift(last,1).slice(0,7).replace('-',''))]);
  return {text:'Выберите '+(ctx.dateStart?'конец':'начало')+' периода · '+month+'\nПн Вт Ср Чт Пт Сб Вс'+(ctx.dateStart?'\nНачало: '+ctx.dateStart:''),reply_markup:nav(rows)};
 }
 if(ctx.view==='dateReview')return {text:'Период '+ctx.dateStart+' — '+ctx.dateEnd,reply_markup:nav([[b('Показать','showDates')],[b('Изменить даты','calendar')]])};
 const title=general?'Общая воронка · '+(products.find(p=>p[0]===ctx.nm)?.[1]||ctx.nm):'Рекламная конверсия · '+(ctx.cid?'РК '+ctx.cid:'все доступные РК');
 if(ctx.period==='today'){
  const rows=hourlyRows(cache,ctx),out=[title,'Сегодня: сопоставимые сохранённые срезы.'];
  for(const r of rows)out.push('',(r.offset===0?'Сегодня':r.offset===1?'Вчера':'Неделю назад')+(r.slot_msk?' · 00:00–'+r.slot_msk.slice(11,16)+' МСК':''),r.missing?'Нет сопоставимых данных (неполное покрытие или время).':headline(r,ctx.kind),'Срез: '+stamp(r.observed_at));
  out.push('',general?'API общей воронки может запаздывать до 2 часов. Полный вчера не подставляется вместо того же часа.':'Заказы атрибутированные; пересечения между РК возможны.','Текущий CR — диагностический срез, не основание менять ставки.');
  const main=rows[0];if(main.observed_at&&(now.getTime()-Date.parse(main.observed_at)>4800000||main.slot_msk?.slice(0,13)!==new Date(now.getTime()+10800000).toISOString().slice(0,13)))out.push('Данные отстают; это последний сохранённый срез.');
  return {text:out.join('\n'),source_keys:rows.map(r=>r.source_key).filter(Boolean),reply_markup:nav([[b('Изменить период','period')],[b('Другой товар / РК','objects')],[b('Обновить из кэша','today')]])};
 }
 const points=dailyPoints(cache,ctx),missing=points.filter(p=>p.missing||!valid(p)).length,full=points.filter(p=>!p.missing&&valid(p)),total=full.length===points.length?sum(full):null;
 const out=[title,ctx.start+' — '+ctx.end+' · полные дни МСК',total?headline(total,ctx.kind):'Итог за весь период недоступен: неполное покрытие.','CR = сумма заказов / сумма '+(general?'открытий':'кликов')+' × 100%.'];
 if(missing)out.push('Нет полного подтверждённого покрытия за '+missing+' дней; пропуски не заменены нулями.');
 const selected=points.slice((ctx.page||0)*5,(ctx.page||0)*5+5);
 if(ctx.view==='table')for(const p of selected){const previous=dailyPoints(cache,{...ctx,start:shift(p.date,-1),end:shift(p.date,-1)})[0],week=dailyPoints(cache,{...ctx,start:shift(p.date,-7),end:shift(p.date,-7)})[0];out.push('',p.date+': '+(p.missing?'нет полного покрытия':headline(p,ctx.kind)),'CR вчера: '+(previous.missing?'нет сопоставимых данных':pct(cr(previous)))+' · CR неделей ранее: '+(week.missing?'нет сопоставимых данных':pct(cr(week))));}
 const observed=points.map(p=>p.observed_at).filter(Boolean).sort();if(observed.length)out.push('Получено: '+stamp(observed[0])+(observed[0]!==observed.at(-1)?' — '+stamp(observed.at(-1)):''));
 out.push(general?'Все источники общей воронки; не складывается с рекламой.':'Рекламные заказы атрибутированные; это не общие продажи.');
 const paging=[];if(ctx.view==='table'){if(ctx.page>0)paging.push(b('‹','tablepage'+(ctx.page-1)));if(((ctx.page||0)+1)*5<points.length)paging.push(b('›','tablepage'+((ctx.page||0)+1)));}
 const markup=nav([...(paging.length?[paging]:[]),[b(ctx.view==='table'?'График':'Таблица по дням',ctx.view==='table'?'graph':'table')],[b('Изменить период','period')],[b('Другой товар / РК','objects')]]);
 return {text:out.join('\n'),reply_markup:markup,source_keys:[...new Set(points.flatMap(p=>p.source_keys))],...(ctx.view==='graph'?{photo:await salesChart(points.map(p=>({date:p.date,count:p.missing?null:p.clicks,amount_cny:p.missing?null:cr(p)})),[general?'ОТКРЫТИЯ':'КЛИКИ','CR %'])}:{})};
}
function transition(ctx,op,now){
 const c={...ctx};c.page=0;
 if(op==='types')c.view='types';
 else if(op==='ad'||op==='general'){c.kind=op;c.view='objects';delete c.nm;delete c.cid;}
 else if(op==='objects')c.view='objects';
 else if(op==='cidAll'){delete c.cid;c.view='period';}
 else if(/^cid\d{5,12}$/.test(op)){c.cid=op.slice(3);c.view='period';}
 else if(/^nm\d{5,12}$/.test(op)){c.nm=op.slice(2);c.view='period';}
 else if(op==='period')c.view='period';
 else if(op==='today'){c.period='today';c.view='table';}
 else if(/^range(7|14)$/.test(op)){c.period='range';c.start=shift(day(now),-Number(op.slice(5)));c.end=shift(day(now),-1);c.view='graph';}
 else if(op==='graph'||op==='table')c.view=op;
 else if(/^tablepage\d+$/.test(op)){c.view='table';c.page=Number(op.slice(9));}
 else if(/^page\d+$/.test(op)){c.view='objects';c.page=Number(op.slice(4));}
 else if(op==='calendar'){c.view='calendar';c.month=day(now).slice(0,7);delete c.dateStart;delete c.dateEnd;}
 else if(/^month\d{6}$/.test(op)){c.view='calendar';c.month=op.slice(5,9)+'-'+op.slice(9);if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(c.month))throw Error('Неверный месяц');}
 else if(/^date\d{8}$/.test(op)){const date=op.slice(4,8)+'-'+op.slice(8,10)+'-'+op.slice(10);if(date>=day(now)||date<shift(day(now),-60)||shift(date,0)!==date)throw Error('Выберите завершённый день.');if(!c.dateStart){c.dateStart=date;c.view='calendar';}else {if(date<c.dateStart||dates(c.dateStart,date).length>31)throw Error('Период: не более 31 дня, конец не раньше начала.');c.dateEnd=date;c.view='dateReview';}}
 else if(op==='showDates'){if(!c.dateStart||!c.dateEnd)throw Error('Выберите даты.');c.start=c.dateStart;c.end=c.dateEnd;c.period='range';c.view='graph';}
 else if(op==='noop')return ctx;
 else if(/^cand(All|Add|Raise|Reduce|Exclude)$/.test(op)){c.view='candidates';c.kind=op.slice(4).toLowerCase();}
 else throw Error('Откройте раздел заново.');
 return c;
}
export async function handleAdvertisingPath(config,update,deps){
 const cb=update.callback_query,m=cb?.message,a=cb?.from,match=/^cam1:([a-f0-9]{16}):([A-Za-z0-9]+)$/.exec(cb?.data||'');
 const initial=['cmn1:candidates','cmn1:conversions'].includes(cb?.data);
 if(!initial&&!match)return null;
 if(config.active!==true||config.bot_id!==BOT||config.chat_id!==CHAT||!Number.isSafeInteger(update.update_id)||update.update_id<0||m?.chat?.id!==CHAT||!['supergroup','group'].includes(m.chat.type)||m.from?.id!==BOT||!Number.isSafeInteger(m.message_id)||!Number.isSafeInteger(a?.id)||a.id<=0||a.is_bot!==false||!cb.id||m.sender_chat||m.forward_origin)return new Response('OK');
 const get=async k=>(await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(k)+'&select=payload&limit=1'))?.[0]?.payload;
 if((await get('china_agent:main_menu:v1:policy'))?.enabled!==true)return null;
 const member=await deps.telegram('getChatMember',{chat_id:CHAT,user_id:a.id});
 if(member?.user?.id!==a.id||member.user.is_bot!==false||!(['creator','administrator','member'].includes(member.status)||member.status==='restricted'&&member.is_member===true))return new Response('OK');
 const answer=text=>Response.json({method:'answerCallbackQuery',callback_query_id:cb.id,...(text?{text,show_alert:true}:{})}),now=deps.now?deps.now():new Date();
 let ctx={view:cb.data==='cmn1:candidates'?'candidates':'types',kind:'all',period:'range',start:shift(day(now),-7),end:shift(day(now),-1)};
 if(match){const session=await get(ROOT+'session:'+match[1]);if(!session||session.actor!==a.id||session.message_id!==m.message_id||Date.parse(session.expires_at)<=now.getTime())return answer('Откройте раздел своей кнопкой меню.');try{ctx=transition(session.context,match[2],now);}catch(e){return answer(e.message);}if(match[2]==='noop')return answer('');}
 const key=ROOT+'delivery:'+update.update_id;if(await get(key))return answer('');
 const insert=async(k,p)=>(await deps.database('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:k,payload:p,expires_at:'2036-11-11T00:00:00Z'},'resolution=ignore-duplicates,return=representation'))?.length===1;
 const put=async(k,p)=>{if((await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(k),'PATCH',{payload:p,updated_at:now.toISOString()},'return=representation'))?.length!==1)throw Error('Advertising state unavailable');};
 const sid=[...crypto.getRandomValues(new Uint8Array(8))].map(n=>n.toString(16).padStart(2,'0')).join(''),b=(text,op)=>({text,callback_data:'cam1:'+sid+':'+op});
 if(!await insert(key,{status:'preparing',actor:a.id,input_message_id:m.message_id,context:ctx,wb_writes:0}))return answer('');
 let view;
 try{
 if(ctx.view==='candidates'){
  const analysisKey=ROOT+'analysis:'+a.id+':'+day(now)+':'+ctx.kind,prior=await get(analysisKey);
  let job=prior?.job_id?await deps.database('business_agent_jobs?id=eq.'+prior.job_id+'&agent_id=eq.china&chat_id=eq.'+CHAT+'&sender_id=eq.'+a.id+'&select=id,status&limit=1'):null;
  if(!prior){
   if(!await insert(analysisKey,{status:'requesting',update_id:update.update_id,actor:a.id,created_at:now.toISOString(),grants_action_permission:false}))throw Error('Analysis already claimed');
   if(typeof deps.requestAnalysis!=='function')throw Error('Analysis route unavailable');
   const result=await deps.requestAnalysis(candidateRequest(ctx.kind),update);
   if(result?.status!==200)throw Error('Analysis not accepted');
   job=await deps.database('business_agent_jobs?agent_id=eq.china&update_id=eq.'+update.update_id+'&chat_id=eq.'+CHAT+'&sender_id=eq.'+a.id+'&select=id,status&limit=1');
   if(job?.length!==1)throw Error('Analysis job not verified');
   await put(analysisKey,{status:'accepted',job_id:job[0].id,update_id:update.update_id,actor:a.id,created_at:now.toISOString(),grants_action_permission:false});
  }
  const state=job?.[0]?.status;
  const line=state==='done'?'Анализ завершён. Ответ проверяйте в сообщении с результатом; завершение задания само по себе не подтверждает доставку.':state==='failed'?'Подготовить ответ не удалось. Изменения не выполнялись.':prior&&!job?.length?'Состояние запроса не подтверждено. Повтор автоматически не запускается.':'Запрос на анализ сохранён'+(job?.[0]?.id?' · №'+job[0].id:'')+'. Результат появится отдельным ответом после обработки; сейчас он ещё не доставлен.';
  view={text:'Предложить кандидатов\n'+line+'\n\nТолько предложения: добавления, повышения, снижения и исключения. Исполнение — после отдельного подтверждения.',reply_markup:{inline_keyboard:[[b('Все направления','candAll')],[b('Добавить товары','candAdd')],[b('Повысить ставки','candRaise')],[b('Снизить ставки','candReduce')],[b('Исключить / завершить','candExclude')],[ads],[home]]},source_keys:[analysisKey]};
 }else{
  const cache=await deps.database('rpc/china_menu_conversion_cache','POST',{p_start:shift(ctx.start||shift(day(now),-7),-7),p_end:ctx.end||shift(day(now),-1)});
  if(cache?.cabinet!=='token_3')throw Error('Conversion source unavailable');
  view=await conversionView(cache,ctx,sid,now);
 }
 if(!await insert(ROOT+'session:'+sid,{actor:a.id,context:ctx,expires_at:new Date(now.getTime()+86400000).toISOString()}))throw Error('Advertising session claimed');
 const base={chat_id:CHAT,reply_markup:view.reply_markup};let receipt;
 if(view.photo)receipt=await deps.telegram('editMessageMedia',{...base,message_id:m.message_id,media:{type:'photo',media:'attach://chart',caption:view.text.slice(0,1024)},photo_bytes:view.photo});
 else if(!m.photo)receipt=await deps.telegram('editMessageText',{...base,message_id:m.message_id,text:view.text});
 else receipt=await deps.telegram('sendMessage',{...base,text:view.text});
 if(receipt?.chat?.id!==CHAT||receipt.from?.id!==BOT||!Number.isSafeInteger(receipt.message_id))throw Error('Advertising receipt mismatch');
 await put(ROOT+'session:'+sid,{actor:a.id,context:ctx,message_id:receipt.message_id,expires_at:new Date(now.getTime()+86400000).toISOString()});
 await put(key,{status:'sent',actor:a.id,context:ctx,source_keys:view.source_keys||[],message_id:receipt.message_id,receipt,wb_writes:0});
 if(m.photo&&!view.photo){try{await deps.telegram('editMessageReplyMarkup',{chat_id:CHAT,message_id:m.message_id,reply_markup:{inline_keyboard:[]}});}catch{}}
 }catch(e){await put(key,{status:'uncertain',actor:a.id,context:ctx,error:'Menu preparation or Telegram result not verified',wb_writes:0});throw e;}
 return answer('');
}
