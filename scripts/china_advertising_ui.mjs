import {tablePng} from './china_table_png.mjs';
/** Advertising navigation: read-only conversion cache and explicitly requested analysis. */
import {salesChart} from './china_sales_chart.mjs';
const ROOT='china_agent:advertising_ui:v1:',CHAT=-1004342917488,BOT=8780468043;
const F=new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}),fmt=n=>F.format(n);
const day=d=>new Date(d.getTime()+10800000).toISOString().slice(0,10);
const shift=(d,n)=>new Date(Date.parse(d+'T00:00:00Z')+n*86400000).toISOString().slice(0,10);
const dates=(a,b)=>{const out=[];for(let d=a;d<=b&&out.length<32;d=shift(d,1))out.push(d);return out;};
const finite=v=>typeof v==='number'&&Number.isFinite(v)&&v>=0;
const valid=r=>r&&r.metrics_valid!==false&&finite(r.clicks)&&finite(r.orders);
const cr=r=>valid(r)&&r.clicks>0?r.orders*100/r.clicks:null;
const pct=v=>v===null?'нет знаменателя':fmt(v)+'%';
const stamp=v=>Number.isFinite(Date.parse(v))?new Date(Date.parse(v)+10800000).toISOString().slice(0,16).replace('T',' ')+' МСК':'время не подтверждено';
const home={text:'‹ Главное меню',callback_data:'cmn1:home'},ads={text:'‹ Реклама',callback_data:'cmn1:ads'};
export function advertisingMenu(){return {text:'Реклама\nЧто хотите посмотреть?',reply_markup:{inline_keyboard:[
 [{text:'Предложить кандидатов',callback_data:'cmn1:candidates'}],
 [{text:'Конверсии и воронка',callback_data:'cmn1:conversions'}],
 [{text:'ДРР',callback_data:'cmn1:drrview'}],
 [{text:'Кто вырос',callback_data:'cmn1:growth'}],
 [{text:'Кто упал',callback_data:'cmn1:decline'}],[home]]},source_keys:[]};}
export function candidateRequest(kind='all'){
 const scopes={all:'Все четыре направления: повышение ставок, добавление новых товаров, снижение ставок, исключение товаров / завершение РК.',add:'Новые товары для добавления в рекламу по всему каталогу.',raise:'Новые повышения ставок.',reduce:'Новые снижения ставок.',exclude:'Новые исключения товаров / завершения РК.'};
 const scope=Array.isArray(kind)?kind.map(k=>scopes[k]).join(' '):scopes[kind];
 if(!scope)throw Error('Unknown candidate filter');
 return 'Предложи новых кандидатов для рекламы китайского кабинета. '+scope+' Только анализ, grants_action_permission=false: никаких WB изменений. Используй завершённые дни после последнего verified изменения, текущие точные ставку/минимум/шаг/цену/COGS/собственный выкуп/МСК минус резерв/опубликованный WB остаток и трёхдневный резерв по фактическим расходам. 143 и 590 не трогать, уже повышенные сегодня ставки повторно не повышать даже в другой РК. Выполненное не предлагать заново. Краткие конкретные предложения с РК, размещением, точным изменением и условием оценки; больше 5 товаров — PNG. Проверка неполная — укажи конкретный пробел, не утверждай отсутствие кандидатов. Готовый план привяжи к фактическому сообщению, hash и сроку; выполнение только после отдельного подтверждения человеком штатным способом.';
}
function normalizedGeneral(r){return r?.scope==='all_sources'?{clicks:r.clicks,orders:r.orders,carts:r.cart_count}:null;}
export const drrValue=r=>finite(r?.spend)&&finite(r?.amount)&&finite(r?.orders)&&r.orders>0&&r.amount>0?r.spend*100/r.amount:null;
const metricsValid=(r,ctx)=>valid(r)&&(ctx.metric!=='drr'||finite(r.spend)&&finite(r.amount));
function sum(rows){if(!rows.length||rows.some(r=>!valid(r)))return null;return rows.reduce((a,r)=>({clicks:a.clicks+r.clicks,orders:a.orders+r.orders,carts:finite(a.carts)&&finite(r.carts)?a.carts+r.carts:null,views:finite(a.views)&&finite(r.views)?a.views+r.views:null,spend:finite(a.spend)&&finite(r.spend)?a.spend+r.spend:null,amount:finite(a.amount)&&finite(r.amount)?a.amount+r.amount:null}),{clicks:0,orders:0,carts:0,views:0,spend:0,amount:0});}
export function dailyPoints(cache,ctx){
 return dates(ctx.start,ctx.end).map(date=>{
  if(ctx.kind==='general'){
   const rows=(cache.general_days||[]).filter(r=>r.date===date&&r.nm===ctx.nm&&r.metrics?.period_from===date&&r.metrics?.period_to===date);
   return {date,...(rows.length===1?normalizedGeneral(rows[0].metrics):{}),source_keys:rows.map(r=>r.source_key),observed_at:rows[0]?.observed_at,missing:rows.length!==1};
  }
  const rows=(cache.daily||[]).filter(r=>r.date===date&&(!ctx.cid||r.campaign===ctx.cid));
  const total=sum(rows),expected=[...new Set(rows.flatMap(r=>r.expected_ids||[]).map(String))],seen=new Set(rows.map(r=>r.campaign));
  const missing=ctx.cid?!rows.length:!rows.length||expected.some(id=>!seen.has(id))||rows.some(r=>r.archived_missing?.length);
  return {date,...(total||{}),source_keys:[...new Set(rows.map(r=>r.source_key))],observed_at:rows.map(r=>r.observed_at).sort().at(-1),missing:missing||!metricsValid(total,ctx)};
 });
}
export function metricHeadline(r,kind,metric){if(metric==='drr'){if(!finite(r?.spend)||!finite(r?.amount)||!finite(r?.orders))return 'нет сопоставимых данных';if(r.orders===0)return 'Нет заказов · расход '+fmt(r.spend)+' CNY';return 'Расход: '+fmt(r.spend)+' CNY · рекламные заказы: '+fmt(r.orders)+' / '+fmt(r.amount)+' CNY · ДРР '+(drrValue(r)===null?'не определяется':pct(drrValue(r)));}return !valid(r)?'нет сопоставимых данных':(kind==='general'?'Открытия: ':'Клики: ')+fmt(r.clicks)+' · корзины: '+(finite(r.carts)?fmt(r.carts):'н/д')+' · заказы: '+fmt(r.orders)+' · CR '+pct(cr(r));}
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
  return {offset:off,...(metrics||{}),slot_msk:h.slot_msk,observed_at:observed,source_key:h.source_key,missing:missing||!metricsValid(metrics,ctx)};
 });
}
export function stableAdCache(cache,ctx){
 const days=dates(ctx.start,ctx.end),rows=(cache.daily||[]).filter(r=>days.includes(r.date));
 const expected=[...new Set(rows.flatMap(r=>r.expected_ids||[]).map(String))];
 const candidates=[...new Set(rows.map(r=>r.campaign))];
 const ids=candidates.filter(cid=>days.every(date=>{const matches=rows.filter(r=>r.date===date&&r.campaign===cid);return matches.length===1&&valid(matches[0]);}));
 if(!ids.length)return {cache,note:'Нет РК с подтверждённым рядом за все выбранные дни.'};
 const filtered={...cache,daily:(cache.daily||[]).filter(r=>ids.includes(r.campaign)).map(r=>({...r,expected_ids:ids,archived_missing:[]}))};
 const excluded=expected.filter(cid=>!ids.includes(cid));
 return {cache:filtered,ids,note:'Постоянная выборка: '+ids.length+' РК с данными за все '+days.length+' дней. Это не весь кабинет.'+(excluded.length?' Без полного ряда: '+excluded.join(', ')+'.':'')};
}
export async function conversionView(cache,ctx,sid,now){
 const b=(text,op)=>op==='search'&&ctx.inlineEnabled?{text,switch_inline_query_current_chat:ctx.kind==='general'?'Воронка ':ctx.metric==='drr'?'ДРР ':'Конверсия '}:{text,callback_data:'cam1:'+sid+':'+op},nav=rows=>({inline_keyboard:[...rows,...(['ad','general'].includes(ctx.kind)&&!['types','search','matches','objects'].includes(ctx.view)?[[b('Найти товар по артикулу','search')]]:[]),[ads],[home]]});
 if(ctx.view==='types')return {text:'Конверсии и воронка\nРекламная конверсия и общая воронка — отдельные источники.',reply_markup:nav([[b('Рекламная конверсия','ad')],[b('Общая воронка товара','general')]])};
 const general=ctx.kind==='general',metric=ctx.metric==='drr'?'drr':'cr',metricName=metric==='drr'?'ДРР':'CR';
 const objectLabel=ctx.nm&&!general?'Другой товар / РК':general?'Другой товар':'Другая РК';
 const products=[...new Map([...(cache.general_days||[]).map(r=>[r.nm,r.article]),...(cache.hourly||[]).flatMap(h=>(h.general?.rows||[]).map(r=>[String(r.nm_id),r.article]))]).entries()];
 if(ctx.view==='search'&&ctx.inlineEnabled)return {text:'Поиск товара\nНажмите кнопку и начните вводить артикул или название.',reply_markup:nav([[b('Ввести артикул или название','search')]])};
 if(ctx.view==='search')return {text:'Найти товар по артикулу\nОтветьте на это сообщение: введите артикул, его часть или nmID.',reply_markup:{force_reply:true,selective:true,input_field_placeholder:'Артикул или nmID'}};
 if(ctx.view==='matches'){const found=cache.matches||[];return {text:'Поиск «'+ctx.query+'»\n'+(found.length?'Выберите товар.'+(cache.truncated?' Показаны первые 20 совпадений; можно уточнить запрос.':''):'Совпадений в сохранённом каталоге нет. Уточните артикул.'),reply_markup:nav([...found.map(r=>[b(r.article.slice(0,60),'pick'+r.nm)]),[b('Уточнить артикул','search')]])};}
 if(ctx.view==='objects'){
  const campaignIds=[...new Set([...(cache.daily||[]).map(r=>r.campaign),...(cache.current_campaigns||[]).map(r=>r.campaign),...(cache.hourly||[]).flatMap(h=>(h.ad_rows||[]).map(r=>String(r.campaign)))])].sort();
  const rows=general?[[b('Найти товар по артикулу','search')]]:[...[[b(ctx.nm?'Все РК товара':'Все РК · доступное покрытие','cidAll')]],...campaignIds.slice((ctx.page||0)*8,(ctx.page||0)*8+8).map(cid=>[b('РК '+cid,'cid'+cid)])];
  if(!general){const count=campaignIds.length;if(ctx.page>0)rows.push([b('‹ Предыдущие','page'+(ctx.page-1))]);if(((ctx.page||0)+1)*8<count)rows.push([b('Следующие ›','page'+((ctx.page||0)+1))]);}
  return {text:general?'Общая воронка\nНайдите товар по артикулу, названию или nmID, затем выберите период.':(metric==='drr'?'ДРР':'Рекламная конверсия')+(ctx.nm?' · '+(ctx.article||ctx.nm)+'\nВыберите РК товара. Каждая кампания показывается отдельно; отсутствие строки статистики не означает ноль.':'\nВсе доступные РК или одна РК. Заказы — атрибутированные, не доказанно уникальные между РК.'),reply_markup:nav([...rows,...(!general?[[b('Найти товар по артикулу','search')],[b('Все РК кабинета','cabinetCampaigns')]]:[]),...(metric==='drr'?[]:[[b('‹ Источники','types')]])])};
 }
 if(ctx.view==='period')return {text:(general?'Общая воронка · '+(ctx.article||products.find(p=>p[0]===ctx.nm)?.[1]||ctx.nm):(metric==='drr'?'ДРР':'Рекламная конверсия')+' · '+(ctx.nm?(ctx.article||ctx.nm)+' · ':'')+(ctx.cid?'РК '+ctx.cid:'все доступные РК'))+'\nВыберите период.',reply_markup:nav([[b('7 полных дней','range7')],[b('14 полных дней','range14')],[b('Выбрать даты','calendar')],[b('Сегодня к тому же часу','today')],[b(objectLabel,'objects')]])};
 if(ctx.view==='calendar'){
  const month=ctx.month,first=month+'-01',last=shift((month.endsWith('-12')?String(+month.slice(0,4)+1)+'-01':month.slice(0,5)+String(+month.slice(5)+1).padStart(2,'0'))+'-01',-1),rows=[],row=[];
  for(let i=0;i<(new Date(first+'T00:00:00Z').getUTCDay()+6)%7;i++)row.push(b('·','noop'));
  for(const d of dates(first,last)){row.push(b(d<day(now)&&d>=shift(day(now),-60)?String(+d.slice(8)):'·',d<day(now)&&d>=shift(day(now),-60)?'date'+d.replaceAll('-',''):'noop'));if(row.length===7){rows.push(row.splice(0));}}
  if(row.length)rows.push(row);
  rows.push([b('‹ Месяц','month'+shift(first,-1).slice(0,7).replace('-','')),b('Месяц ›','month'+shift(last,1).slice(0,7).replace('-',''))]);
  return {text:'Выберите '+(ctx.dateStart?'конец':'начало')+' периода · '+month+'\nПн Вт Ср Чт Пт Сб Вс'+(ctx.dateStart?'\nНачало: '+ctx.dateStart:''),reply_markup:nav(rows)};
 }
 if(ctx.view==='dateReview')return {text:'Период '+ctx.dateStart+' — '+ctx.dateEnd,reply_markup:nav([[b('Показать','showDates')],[b('Изменить даты','calendar')]])};
 const title=general?'Общая воронка · '+(ctx.article||products.find(p=>p[0]===ctx.nm)?.[1]||ctx.nm):(metric==='drr'?'ДРР':'Рекламная конверсия')+' · '+(ctx.nm?(ctx.article||ctx.nm)+' · ':'')+(ctx.cid?'РК '+ctx.cid:'все доступные РК');
 if(ctx.period==='today'){
  const rows=hourlyRows(cache,ctx),out=[title,'Сегодня: сопоставимые сохранённые срезы.'];
  for(const r of rows)out.push('',(r.offset===0?'Сегодня':r.offset===1?'Вчера':'Неделю назад')+(r.slot_msk?' · 00:00–'+r.slot_msk.slice(11,16)+' МСК':''),r.missing?'Нет сопоставимых данных (неполное покрытие или время).':metricHeadline(r,ctx.kind,metric),'Срез: '+stamp(r.observed_at));
  out.push('',general?'API общей воронки может запаздывать до 2 часов. Полный вчера не подставляется вместо того же часа.':'Заказы атрибутированные; пересечения между РК возможны.','Текущий '+metricName+' — диагностический срез, не основание менять ставки.');
  const main=rows[0];if(main.observed_at&&(now.getTime()-Date.parse(main.observed_at)>4800000||main.slot_msk?.slice(0,13)!==new Date(now.getTime()+10800000).toISOString().slice(0,13)))out.push('Данные отстают; это последний сохранённый срез.');
  return {text:out.join('\n'),source_keys:rows.map(r=>r.source_key).filter(Boolean),reply_markup:nav([[b('Изменить период','period')],[b(objectLabel,'objects')],[b('Обновить из кэша','today')]])};
 }
 const cohort=!general&&!ctx.cid&&!ctx.nm?stableAdCache(cache,ctx):null;if(cohort)cache=cohort.cache;
 const points=dailyPoints(cache,ctx),missing=points.filter(p=>p.missing||!metricsValid(p,ctx)).length,full=points.filter(p=>!p.missing&&metricsValid(p,ctx)),total=full.length===points.length?sum(full):null;
 if(general&&full.length===0)return {text:title+'\n'+ctx.start+' — '+ctx.end+' · полные дни МСК\nНет данных общей воронки за выбранный период. Конверсия не рассчитана.',reply_markup:nav([[b('Изменить период','period')],[b('Другой товар','objects')]]),source_keys:[]};
 const out=[title,ctx.start+' — '+ctx.end+' · полные дни МСК',total?metricHeadline(total,ctx.kind,metric):'Итог за весь период недоступен: неполное покрытие.',metric==='drr'?'ДРР = сумма расхода / сумма рекламных заказов × 100%.':'CR = сумма заказов / сумма '+(general?'открытий':'кликов')+' × 100%.'];
 if(cohort)out.push(cohort.note);
 if(missing)out.push('Нет полного подтверждённого покрытия за '+missing+' дней; пропуски не заменены нулями.');
 const observed=points.map(p=>p.observed_at).filter(Boolean).sort();if(observed.length)out.push('Получено: '+stamp(observed[0])+(observed[0]!==observed.at(-1)?' — '+stamp(observed.at(-1)):''));
 out.push(general?'Все источники общей воронки; не складывается с рекламой.':'Рекламные заказы атрибутированные; это не общие продажи.');
 const paging=[];if(ctx.view==='table'){if(ctx.page>0)paging.push(b('‹','tablepage'+(ctx.page-1)));if(((ctx.page||0)+1)*12<points.length)paging.push(b('›','tablepage'+((ctx.page||0)+1)));}
 const markup=nav([...(paging.length?[paging]:[]),[b(ctx.view==='table'?'График':'Таблица по дням',ctx.view==='table'?'graph':'table')],[b('Изменить период','period')],[b(objectLabel,'objects')]]);
 let photo;
 if(ctx.view==='graph')photo=await salesChart(points.map(p=>({date:p.date,count:p.missing?null:metric==='drr'?p.spend:p.clicks,amount_cny:p.missing?null:metric==='drr'?drrValue(p):cr(p)})),[metric==='drr'?'РАСХОД CNY':general?'ОТКРЫТИЯ':'КЛИКИ',metric==='drr'?'ДРР %':'CR %']);
 else if(ctx.view==='table'){
  const renderNum=v=>finite(v)?fmt(v):'н/д',ratio=p=>!p||p.missing?'н/д':metric==='drr'?(p.orders===0?'Нет заказов':drrValue(p)===null?'н/д':pct(drrValue(p))):pct(cr(p));
  const columns=general?[['Дата',180],['Открытия',210],['Корзины',210],['Заказы',190],['CR',190],['CR день\nдо этого',260],['CR неделей\nранее',260]]:[['Дата',180],['Показы',170],['Клики',140],['Корзины',160],['Заказы',140],['Расход,\nCNY',190],['Сумма заказов,\nCNY',210],['CR',180],['ДРР',200],[metricName+' день\nдо этого',230],[metricName+' неделей\nранее',230]];
  const values=(p,label,previous,week)=>general?[label,renderNum(p?.clicks),renderNum(p?.carts),renderNum(p?.orders),p&&cr(p)!==null?pct(cr(p)):'н/д',previous,week]:[label,renderNum(p?.views),renderNum(p?.clicks),renderNum(p?.carts),renderNum(p?.orders),renderNum(p?.spend),renderNum(p?.amount),p&&cr(p)!==null?pct(cr(p)):'н/д',p?(p.orders===0?'Нет заказов':drrValue(p)===null?'н/д':pct(drrValue(p))):'н/д',previous,week];
  const rows=points.slice((ctx.page||0)*12,(ctx.page||0)*12+12).map(p=>{const previous=dailyPoints(cache,{...ctx,start:shift(p.date,-1),end:shift(p.date,-1)})[0],week=dailyPoints(cache,{...ctx,start:shift(p.date,-7),end:shift(p.date,-7)})[0];return values(p.missing?null:p,p.date.slice(8)+'.'+p.date.slice(5,7),ratio(previous),ratio(week));});
  photo=await tablePng({title,subtitle:ctx.start+' — '+ctx.end+' · таблица по дням'+(points.length>12?' · часть '+((ctx.page||0)+1)+'/'+Math.ceil(points.length/12):''),columns:columns.map(([label,width])=>({label,width})),rows,total:values(total,'ИТОГО','—','—'),footnotes:[general?'CR = сумма заказов / сумма открытий × 100%.':'CR = сумма заказов / сумма кликов × 100%. ДРР = сумма расхода / сумма рекламных заказов × 100%.',general?'н/д — нет данных общей воронки или сопоставимой базы.':'«Нет заказов» читается вместе с расходом. н/д — нет сопоставимых данных.',...(points.length>12?['ИТОГО — за весь выбранный период, включая строки на других страницах.']:[]),...(cohort?[cohort.note]:[]),general?'Источник — общая воронка WB, все источники трафика. Время получения — в подписи.':'Источник и время получения указаны в подписи. Рекламные заказы — атрибутированные.']});
 }
 if(metric==='drr'&&points.some(p=>!p.missing&&p.orders===0))out.push('Нет заказов: расход показан; на графике ДРР за такой день — пропуск.');
 return {text:out.join('\n'),reply_markup:markup,source_keys:[...new Set(points.flatMap(p=>p.source_keys))],...(photo?{photo}:{})};
}
function transition(ctx,op,now){
 const c={...ctx};c.page=0;
 if(op==='types')c.view='types';
 else if(op==='ad'||op==='general'){c.kind=op;if(op==='general')c.metric='cr';c.view='objects';delete c.nm;delete c.cid;}
 else if(op==='objects')c.view='objects';
 else if(op==='search'){c.view='search';}
 else if(op==='allCampaigns'){delete c.cid;c.view=c.nm?'period':'objects';}
 else if(op==='cabinetCampaigns'){delete c.nm;delete c.article;delete c.cid;c.view='objects';}
 else if(/^pick\d{5,12}$/.test(op)){c.nm=op.slice(4);delete c.cid;c.view='objects';}
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
 else if(/^cand(All|Add|Raise|Reduce|Exclude)$/.test(op)){c.view='candidates';c.submit=false;const k=op.slice(4).toLowerCase(),all=['add','raise','reduce','exclude'];c.directions=k==='all'?(c.directions?.length===4?[]:all):all.filter(x=>x===k?!c.directions?.includes(x):c.directions?.includes(x));}
 else if(op==='candRetry'){c.view='candidates';c.submit=true;c.directions=c.directions?.length?c.directions:c.kind==='all'?['add','raise','reduce','exclude']:c.kind.split('+');c.kind=c.directions.join('+');c.analysisRevision=String(now.getTime());}
 else if(op==='funnelRetry'){c.view='graph';c.funnelRevision=String(now.getTime());}
 else if(op==='candSubmit'){c.view='candidates';if(!c.directions?.length)throw Error('Выберите хотя бы одно направление.');c.submit=true;c.kind=c.directions.join('+');}
 else throw Error('Откройте раздел заново.');
 return c;
}
export async function handleAdvertisingPath(config,update,deps){
 const cb=update.callback_query,m=cb?.message||update.message,a=cb?.from||m?.from,match=/^cam1:([a-f0-9]{16}):([A-Za-z0-9]+)$/.exec(cb?.data||'');
 const input=update.message?.text?.trim(),possibleReply=!cb&&typeof input==='string'&&input.length<=80&&m?.reply_to_message?.from?.id===BOT;
 const initial=['cmn1:candidates','cmn1:conversions','cmn1:drrview'].includes(cb?.data);
 if(!initial&&!match&&!possibleReply)return null;
 if(config.active!==true||config.bot_id!==BOT||config.chat_id!==CHAT||!Number.isSafeInteger(update.update_id)||update.update_id<0||m?.chat?.id!==CHAT||!['supergroup','group'].includes(m.chat.type)||!Number.isSafeInteger(m.message_id)||!Number.isSafeInteger(a?.id)||a.id<=0||a.is_bot!==false||cb&&(m.from?.id!==BOT||!cb.id)||m.sender_chat||m.forward_origin)return new Response('OK');
 const get=async k=>(await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(k)+'&select=payload&limit=1'))?.[0]?.payload;
 const menuPolicy=await get('china_agent:main_menu:v1:policy');if(menuPolicy?.enabled!==true)return null;
 const pending=possibleReply?await get(ROOT+'input:'+a.id):null;
 if(!initial&&!match&&pending?.message_id!==m.reply_to_message?.message_id)return null;
 const member=await deps.telegram('getChatMember',{chat_id:CHAT,user_id:a.id});
 if(member?.user?.id!==a.id||member.user.is_bot!==false||!(['creator','administrator','member'].includes(member.status)||member.status==='restricted'&&member.is_member===true))return new Response('OK');
 const answer=text=>cb?Response.json({method:'answerCallbackQuery',callback_query_id:cb.id,...(text?{text,show_alert:true}:{})}):new Response('OK'),now=deps.now?deps.now():new Date();
 let ctx={view:cb?.data==='cmn1:candidates'?'candidates':cb?.data==='cmn1:drrview'?'objects':'types',kind:cb?.data==='cmn1:drrview'?'ad':'all',metric:cb?.data==='cmn1:drrview'?'drr':'cr',period:'range',start:shift(day(now),-7),end:shift(day(now),-1)};
 if(match){const session=await get(ROOT+'session:'+match[1]);if(!session||session.actor!==a.id||session.message_id!==m.message_id||Date.parse(session.expires_at)<=now.getTime())return answer('Откройте раздел своей кнопкой меню.');try{ctx=transition(session.context,match[2],now);if(ctx.view==='candidates'&&!ctx.analysisDay)ctx.analysisDay=day(new Date(Date.parse(session.expires_at)-86400000));if(match[2].startsWith('pick')){const picked=session.context.matches?.find(r=>r.nm===ctx.nm);if(!picked)return answer('Повторите поиск товара.');ctx.article=picked.article;}}catch(e){return answer(e.message);}if(match[2]==='noop')return answer('');}
 else if(pending&&possibleReply&&pending.message_id===m.reply_to_message?.message_id){ctx={...pending.context,view:Date.parse(pending.expires_at)>now.getTime()?'matches':'search',query:input};}
 if(ctx.view==='candidates'&&!ctx.analysisDay)ctx.analysisDay=day(now);
 ctx.inlineEnabled=menuPolicy.inline_search_enabled===true;
 const key=ROOT+'delivery:'+update.update_id;if(await get(key))return answer('');
 const insert=async(k,p)=>(await deps.database('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:k,payload:p,expires_at:'2036-11-11T00:00:00Z'},'resolution=ignore-duplicates,return=representation'))?.length===1;
 const put=async(k,p)=>{if((await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(k),'PATCH',{payload:p,updated_at:now.toISOString()},'return=representation'))?.length!==1)throw Error('Advertising state unavailable');};
 const sid=[...crypto.getRandomValues(new Uint8Array(8))].map(n=>n.toString(16).padStart(2,'0')).join(''),b=(text,op)=>({text,callback_data:'cam1:'+sid+':'+op});
 if(!await insert(key,{status:'preparing',actor:a.id,input_message_id:m.message_id,context:ctx,wb_writes:0}))return answer('');
 let view;
 try{
 if(ctx.view==='candidates'&&!ctx.submit){
 const selected=ctx.directions||[],choices=[['Add','add','Добавить товары'],['Raise','raise','Повысить ставки'],['Reduce','reduce','Снизить ставки'],['Exclude','exclude','Исключить / завершить']];
 view={text:'Предложить кандидатов\nОтметьте одно или несколько направлений, затем нажмите «Найти кандидатов».',reply_markup:{inline_keyboard:[[b((selected.length===4?'☑ ':'☐ ')+'Все направления','candAll')],...choices.map(([op,k,label])=>[b((selected.includes(k)?'☑ ':'☐ ')+label,'cand'+op)]),[b('Найти кандидатов'+(selected.length?' · '+selected.length:''),'candSubmit')],[ads],[home]]},source_keys:[]};
 }else if(ctx.view==='candidates'){
  const analysisKey=ROOT+'analysis:'+a.id+':'+ctx.analysisDay+':'+ctx.kind+(ctx.analysisRevision?':retry:'+ctx.analysisRevision:''),prior=await get(analysisKey);
  let job=prior?.job_id?await deps.database('business_agent_jobs?id=eq.'+prior.job_id+'&agent_id=eq.china&chat_id=eq.'+CHAT+'&sender_id=eq.'+a.id+'&select=id,status&limit=1'):null;
  if(!prior){
   if(!await insert(analysisKey,{status:'requesting',update_id:update.update_id,actor:a.id,created_at:now.toISOString(),grants_action_permission:false}))throw Error('Analysis already claimed');
   if(typeof deps.requestAnalysis!=='function')throw Error('Analysis route unavailable');
   const result=await deps.requestAnalysis(candidateRequest(ctx.directions||ctx.kind),update);
   if(result?.status!==200)throw Error('Analysis not accepted');
   job=await deps.database('business_agent_jobs?agent_id=eq.china&update_id=eq.'+update.update_id+'&chat_id=eq.'+CHAT+'&sender_id=eq.'+a.id+'&select=id,status&limit=1');
   if(job?.length!==1)throw Error('Analysis job not verified');
   await put(analysisKey,{status:'accepted',job_id:job[0].id,update_id:update.update_id,actor:a.id,created_at:now.toISOString(),grants_action_permission:false});
  }
  const state=job?.[0]?.status,jobId=job?.[0]?.id;
  const recovery=jobId?await get('china_agent:menu_result:v1:'+jobId):null,blocked=jobId?await get('china_agent:menu_analytics:v1:'+jobId):null,outbox=jobId?await get('china_agent:codex_bridge:v1:outbox:'+jobId):null;
  const delivered=recovery?.status==='sent'?recovery:outbox?.status==='delivered'&&blocked?.status!=='blocked'?outbox:null;
  const failed=!delivered&&(state==='failed'||blocked?.status==='blocked');
  const line=delivered?'Результат доставлен.':failed?'Расчёт не завершён. Можно повторить запрос. Изменения не выполнялись.':prior&&!job?.length?'Состояние запроса не подтверждено. Повтор автоматически не запускается.':'Запрос на анализ сохранён'+(jobId?' · №'+jobId:'')+'. Результат появится отдельным ответом после обработки; сейчас он ещё не доставлен.';
  const resultId=delivered?.message_ids?.at(-1)||delivered?.message_id;
  view={text:'Предложить кандидатов\n'+line+'\n\nТолько предложения: добавления, повышения, снижения и исключения. Исполнение — после отдельного подтверждения.',reply_markup:{inline_keyboard:[...(resultId?[[{text:'Открыть результат',url:'https://t.me/c/4342917488/'+resultId}]]:[]),...(failed?[[b('Повторить расчёт','candRetry')]]:[]),[b('Изменить направления','candAll')],[ads],[home]]},source_keys:[analysisKey]};
 }else{
  let cache;
  if(ctx.view==='search')cache={cabinet:'token_3'};
  else if(ctx.view==='matches'){
   const found=await deps.database('rpc/china_menu_product_lookup','POST',{p_query:ctx.query});
   if(found?.cabinet!=='token_3')throw Error('Product catalogue unavailable');
   ctx.matches=found.rows;cache={cabinet:'token_3',matches:found.rows,truncated:found.truncated};
  }else {
   const product=ctx.kind!=='general'&&!!ctx.nm;
   cache=await deps.database(product?'rpc/china_menu_product_ad_cache':'rpc/china_menu_conversion_cache','POST',{p_start:shift(ctx.start||shift(day(now),-7),-7),p_end:ctx.end||shift(day(now),-1),...(product?{p_nm:Number(ctx.nm)}:{})});
   if(cache?.cabinet!=='token_3'||product&&cache.nm!==ctx.nm)throw Error('Product or conversion source unavailable');
  }
  let requestedFunnel=false;
  if(ctx.kind==='general'&&ctx.nm&&ctx.period==='range'&&['graph','table'].includes(ctx.view)){
   const source='china_agent:menu_funnel:v1:'+ctx.nm+':'+ctx.start+':'+ctx.end,saved=await get(source);
   if(saved?.status==='complete'&&saved.cabinet==='token_3'&&saved.nm===ctx.nm)cache={...cache,general_days:saved.rows};
   if(!saved&&dailyPoints(cache,ctx).some(p=>p.missing)){
    const claim=ROOT+'funnel_request:'+a.id+':'+ctx.nm+':'+ctx.start+':'+ctx.end+(ctx.funnelRevision?':retry:'+ctx.funnelRevision:''),prior=await get(claim);
    let jobId=prior?.job_id;
    if(!prior){
     if(!await insert(claim,{status:'requesting',actor:a.id,created_at:now.toISOString(),wb_writes:0}))throw Error('Funnel request already claimed');
     const result=await deps.requestAnalysis('Общая воронка · запрос меню: '+ctx.nm+' '+ctx.start+' '+ctx.end,update);
     if(result?.status!==200)throw Error('Funnel request not accepted');
     const jobs=await deps.database('business_agent_jobs?agent_id=eq.china&update_id=eq.'+update.update_id+'&chat_id=eq.'+CHAT+'&sender_id=eq.'+a.id+'&select=id,status&limit=1');
     if(jobs?.length!==1)throw Error('Funnel job not verified');
     jobId=jobs[0].id;await put(claim,{status:'accepted',job_id:jobId,actor:a.id,created_at:now.toISOString(),wb_writes:0});
    }
    requestedFunnel=true;
    view={text:'Общая воронка · '+(ctx.article||ctx.nm)+'\n'+ctx.start+' — '+ctx.end+'\n'+(prior?'Запрос уже сохранён':'Запрос сохранён')+' · №'+jobId+'. Результат по выбранному товару придёт отдельной таблицей PNG. Сейчас он ещё не доставлен.',reply_markup:{inline_keyboard:[[b('Изменить период','period')],[b('Другой товар','objects')],[ads],[home]]},source_keys:[claim]};
   }
  }
  if(!requestedFunnel)view=await conversionView(cache,ctx,sid,now);
 }
 if(!await insert(ROOT+'session:'+sid,{actor:a.id,context:ctx,expires_at:new Date(now.getTime()+86400000).toISOString()}))throw Error('Advertising session claimed');
 const base={chat_id:CHAT,reply_markup:view.reply_markup};let receipt;
 if(deps.forceNewMessage)receipt=await deps.telegram('sendMessage',{...base,text:view.text});
 else if(view.photo)receipt=await deps.telegram(cb?'editMessageMedia':'sendPhoto',{...base,...(cb?{message_id:m.message_id,media:{type:'photo',media:'attach://chart',caption:view.text.slice(0,1024)}}:{caption:view.text.slice(0,1024)}),photo_bytes:view.photo});
 else if(cb&&!m.photo&&ctx.view!=='search')receipt=await deps.telegram('editMessageText',{...base,message_id:m.message_id,text:view.text});
 else {const name=String(a.first_name||'Участник');receipt=await deps.telegram('sendMessage',{...base,text:ctx.view==='search'?name+', '+view.text:view.text,...(ctx.view==='search'?{entities:[{type:'text_mention',offset:0,length:name.length,user:{id:a.id,first_name:name,is_bot:false}}],reply_parameters:{message_id:m.message_id,allow_sending_without_reply:true}}:{})});}
 if(receipt?.chat?.id!==CHAT||receipt.from?.id!==BOT||!Number.isSafeInteger(receipt.message_id))throw Error('Advertising receipt mismatch');
 await put(ROOT+'session:'+sid,{actor:a.id,context:ctx,message_id:receipt.message_id,expires_at:new Date(now.getTime()+86400000).toISOString()});
 await put(key,{status:'sent',actor:a.id,context:ctx,source_keys:view.source_keys||[],message_id:receipt.message_id,receipt,wb_writes:0});
 if(['ad','general'].includes(ctx.kind)&&ctx.view!=='candidates'){
  const metric=ctx.kind==='general'?'general':ctx.metric==='drr'?'drr':'cr',k=ROOT+'inline_context:'+a.id+':'+metric,context={...ctx};delete context.matches;delete context.query;
  const value={actor:a.id,context,source_message:{message_id:receipt.message_id,chat:{id:CHAT,type:'supergroup'},from:{id:BOT,is_bot:true},...(receipt.photo?{photo:receipt.photo}:{})},expires_at:new Date(now.getTime()+900000).toISOString()};
  if(await get(k))await put(k,value);else if(!await insert(k,value))throw Error('Inline context unavailable');
 }
 if(ctx.view==='search'){const k=ROOT+'input:'+a.id,value={actor:a.id,message_id:receipt.message_id,context:ctx,expires_at:new Date(now.getTime()+900000).toISOString()};if(await get(k))await put(k,value);else if(!await insert(k,value))throw Error('Search input binding unavailable');}
 if(!deps.forceNewMessage&&cb&&m.photo&&!view.photo){try{await deps.telegram('editMessageReplyMarkup',{chat_id:CHAT,message_id:m.message_id,reply_markup:{inline_keyboard:[]}});}catch{}}
 }catch(e){await put(key,{status:'uncertain',actor:a.id,context:ctx,error:'Menu preparation or Telegram result not verified',wb_writes:0});throw e;}
 return answer('');
}
