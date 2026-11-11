import assert from 'node:assert/strict';
import fs from 'node:fs';
import {stableAdCache,advertisingMenu,handleAdvertisingPath,dailyPoints,hourlyRows,candidateRequest,conversionView} from './china_advertising_ui.mjs';
import {handleSalesPath} from './china_sales_ui.mjs';
const CHAT=-1004342917488,BOT=8780468043,now=new Date('2026-11-11T10:30:00Z'),config={active:true,chat_id:CHAT,bot_id:BOT};
const c=new Map(),messages=new Map(),calls=[],jobs=new Map();let u=10,next=1000,requests=0;
c.set('china_agent:main_menu:v1:policy',{enabled:true});
c.set('china_agent:prices:v1',{cabinet:'token_3',rows:[{nmID:1111111111,vendorCode:'Растёт'},{nmID:2222222222,vendorCode:'Падает'}]});
const BASIS='FBS created units, all statuses, dedup id; native CNY buyer-discounted amount; not buyouts or all sales models';
const key='china_agent:hourly_sales_api:v1:snapshot:2026-11-11T13:MSK',snapshot={cabinet:'token_3',slot_msk:'2026-11-11T13:00:00+03:00',observed_at:'2026-11-11T10:22:00Z',orders:{}};
for(const [offset,date,first,second] of [[0,'2026-11-11',20000,5000],[1,'2026-11-10',10000,10000],[7,'2026-11-04',9000,9000]]){
 const rows=[{id:1,nmId:1111111111,convertedCurrencyCode:156,convertedPrice:first},{id:2,nmId:2222222222,convertedCurrencyCode:156,convertedPrice:second}];
 snapshot.orders[offset]={status:'complete',basis:BASIS,start_msk:date+'T00:00:00+03:00',end_msk:date+'T13:00:00+03:00',rows,totals:{count:2,amount_cny:(first+second)/100,unknown_amount_ids:[]}};
}
c.set(key,snapshot);c.set('china_agent:hourly_sales_api:v1:latest',{source_key:key});
const cache={cabinet:'token_3',daily:[],general_days:[],hourly:[]};
for(let day=21;day<=41;day++){
 const date=new Date(Date.parse('2026-10-01T00:00:00Z')+(day-1)*86400000).toISOString().slice(0,10);
 cache.daily.push({date,campaign:'12345678',clicks:100,orders:2,carts:4,expected_ids:[12345678],archived_missing:[],source_key:'daily-source',observed_at:'2026-11-11T05:00:00Z'});
 cache.general_days.push({date,nm:'1473245494',article:'143',metrics:{scope:'all_sources',period_from:date,period_to:date,clicks:200,orders:4,cart_count:10},source_key:'funnel-source',observed_at:'2026-11-11T05:00:00Z'});
}
for(const [offset,date] of [[0,'2026-11-11'],[1,'2026-11-10'],[7,'2026-11-04']])cache.hourly.push({offset,source_key:'hourly'+offset,slot_msk:date+'T13:00:00+03:00',observed_at:date+'T10:22:00Z',ad_observed_at:date+'T10:22:00Z',ad_status:'complete',ad_missing:[],ad_rows:[{campaign:12345678,clicks:100,orders:2,carts:4}],general:{status:'complete',observed_at:date+'T10:22:00Z',rows:[{nm_id:1473245494,article:'143',selected:{scope:'all_sources',period_from:date,period_to:date,clicks:200,orders:4,cart_count:10}}]}});
const deps={now:()=>now,telegram:async(method,b)=>{
 calls.push({method,b});
 if(method==='getChatMember')return{user:{id:b.user_id,is_bot:false},status:'member'};
 if(method==='editMessageReplyMarkup')return true;
 assert.ok(['sendMessage','editMessageText','sendPhoto','editMessageMedia'].includes(method));
 const id=b.message_id||next++,photo=['sendPhoto','editMessageMedia'].includes(method);
 const m={message_id:id,chat:{id:CHAT,type:'supergroup'},from:{id:BOT,is_bot:true},reply_markup:b.reply_markup,...(photo?{photo:[{file_id:'mock'}],caption:b.media?.caption||b.caption}:{text:b.text})};
 messages.set(id,m);return m;
},database:async(path,method='GET',body,prefer)=>{
 const [table,q]=path.split('?'),args=new URLSearchParams(q);
 if(table==='rpc/china_menu_conversion_cache'){assert.equal(method,'POST');assert.ok(body.p_start<body.p_end);return structuredClone(cache);}
 if(table==='business_agent_jobs'){assert.equal(method,'GET','No executions or direct job insertion in UI');const id=args.get('id')?.slice(3),update=args.get('update_id')?.slice(3);return [...jobs.values()].filter(j=>id?j.id===+id:j.update_id===+update);}
 assert.equal(table,'telegram_api_cache');
 if(method==='POST'){if(c.has(body.cache_key))return[];c.set(body.cache_key,structuredClone(body.payload));return[body];}
 const filter=args.get('cache_key');
 if(filter.startsWith('like.'))return[];
 const k=filter.slice(3);
 if(method==='GET')return c.has(k)?[{payload:structuredClone(c.get(k))}]:[];
 assert.equal(method,'PATCH');assert.ok(c.has(k));c.set(k,structuredClone(body.payload));return[body];
},requestAnalysis:async(text,update)=>{requests++;assert.match(text,/никаких WB изменений/);assert.match(text,/143 и 590/);jobs.set(requests,{id:requests,status:'pending',update_id:update.update_id});return new Response('OK');}};
let m={message_id:5,chat:{id:CHAT,type:'supergroup'},from:{id:BOT,is_bot:true},text:'Реклама'};
async function raw(data,actor=7,updateId=null){const up={update_id:updateId??u++,callback_query:{id:'cb'+u,data,from:{id:actor,is_bot:false},message:m}};const r=await handleAdvertisingPath(config,up,deps)||await handleSalesPath(config,up,deps);return r;}
async function click(text){const b=m.reply_markup.inline_keyboard.flat().find(b=>b.text===text);assert.ok(b,'Missing '+text);const r=await raw(b.callback_data);assert.ok(r);assert.doesNotMatch(await r.text(),/"show_alert":true/);m=[...messages.values()].at(-1);return m;}
const menu=advertisingMenu();assert.deepEqual(menu.reply_markup.inline_keyboard.map(r=>r[0].text),['Предложить кандидатов','Конверсии и воронка','Кто вырос','Кто упал','‹ Главное меню']);
await raw('cmn1:growth');m=[...messages.values()].at(-1);assert.match(m.text,/Растёт/);assert.doesNotMatch(m.text,/Падает:/);assert.match(m.text,/К неделе/);
await click('К неделе');await click('По количеству');assert.match(m.text,/по количеству/);
await raw('cmn1:decline');m=[...messages.values()].at(-1);assert.match(m.text,/Падает/);assert.doesNotMatch(m.text,/Растёт:/);
await click('Падает');assert.match(m.text,/Падает/);assert.ok(m.reply_markup.inline_keyboard.flat().some(b=>b.text==='‹ Реклама'));
await raw('cmn1:conversions');m=[...messages.values()].at(-1);await click('Рекламная конверсия');await click('РК 12345678');await click('7 полных дней');assert.ok(m.photo);assert.match(m.caption,/CR/);assert.ok(calls.at(-1).b.photo_bytes instanceof Uint8Array);
fs.writeFileSync('work/advertising-menu11/conversion-test.png',calls.at(-1).b.photo_bytes);
await click('Таблица по дням');assert.match(m.text,/CR вчера/);assert.match(m.text,/неделей ранее/);
await click('Изменить период');await click('Сегодня к тому же часу');assert.match(m.text,/Вчера/);assert.match(m.text,/Неделю назад/);assert.match(m.text,/2%/);
await raw('cmn1:conversions');m=[...messages.values()].at(-1);await click('Общая воронка товара');await click('143');await click('Выбрать даты');await click('1');await click('3');await click('Показать');assert.match(m.caption,/2026-11-01 — 2026-11-03/);await click('Таблица по дням');assert.match(m.text,/Открытия/);
const foreign=await raw(m.reply_markup.inline_keyboard[0][0].callback_data,8);assert.match(await foreign.text(),/своей кнопкой/);
await raw('cmn1:candidates');m=[...messages.values()].at(-1);assert.equal(requests,1);assert.match(m.text,/ещё не доставлен/);await raw('cmn1:candidates');m=[...messages.values()].at(-1);assert.equal(requests,1,'Repeated request must reuse same daily actor/filter job');
await click('Добавить товары');assert.equal(requests,2);await click('Все направления');assert.equal(requests,2);
const count=calls.length;const data=m.reply_markup.inline_keyboard[0][0].callback_data;await raw(data,7,9999);const after=calls.length;await raw(data,7,9999);assert.equal(calls.length,after+1,'Retry only rechecks membership, no send');assert.ok(after>count);
const partial=structuredClone(cache);partial.hourly[1].general.observed_at='2026-11-10T11:00:00Z';assert.equal(hourlyRows(partial,{kind:'general',nm:'1473245494'})[1].missing,true);
partial.hourly[1].slot_msk='2026-11-10T23:00:00+03:00';assert.equal(hourlyRows(partial,{kind:'ad'})[1].missing,true);
assert.equal(dailyPoints({...cache,daily:[]},{start:'2026-11-10',end:'2026-11-10',kind:'ad'})[0].missing,true);
const point=dailyPoints(cache,{start:'2026-11-10',end:'2026-11-10',kind:'ad',cid:'12345678'})[0];assert.equal(point.orders,2);
assert.match(candidateRequest(),/Все четыре направления/);
const bad={...cache,daily:[{...cache.daily[0],expected_ids:[12345678,99999999]}]};assert.equal(dailyPoints(bad,{start:cache.daily[0].date,end:cache.daily[0].date,kind:'ad'})[0].missing,true);
console.log('PASS four Advertising buttons; direct growth/decline; actor-bound sessions; amount/count and both bases; conversion graph/table/calendar; separate general funnel; same-hour/coverage guards; candidate requests once per actor/day/filter, no WB commands; duplicate delivery.');


const cohortFixture=structuredClone(cache);cohortFixture.daily.push({date:'2026-11-04',campaign:'99999999',clicks:500,orders:50,expected_ids:[12345678,99999999],source_key:'partial-campaign',observed_at:'2026-11-11T05:00:00Z'});
const stable=stableAdCache(cohortFixture,{start:'2026-11-04',end:'2026-11-10'});assert.deepEqual(stable.ids,['12345678']);assert.match(stable.note,/не весь кабинет/);
const stableView=await conversionView(cohortFixture,{view:'graph',kind:'ad',period:'range',start:'2026-11-04',end:'2026-11-10'},'a'.repeat(16),now);assert.match(stableView.text,/Постоянная выборка/);assert.match(stableView.text,/2%/);assert.doesNotMatch(stableView.text,/Итог за весь период недоступен/);
console.log('PASS stable campaign intersection preserves real graph despite incomplete other campaigns; no fabricated zero or changing cohort.');
