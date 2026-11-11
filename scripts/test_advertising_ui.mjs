import {handleInlineSearch} from './china_inline_search.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {stableAdCache,advertisingMenu,handleAdvertisingPath,dailyPoints,hourlyRows,candidateRequest,conversionView,drrValue,metricHeadline} from './china_advertising_ui.mjs';
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
 cache.daily.push({date,campaign:'12345678',clicks:100,orders:2,carts:4,views:1000,spend:5,amount:200,expected_ids:[12345678],archived_missing:[],source_key:'daily-source',observed_at:'2026-11-11T05:00:00Z'});
 cache.general_days.push({date,nm:'1473245494',article:'143',metrics:{scope:'all_sources',period_from:date,period_to:date,clicks:200,orders:4,cart_count:10},source_key:'funnel-source',observed_at:'2026-11-11T05:00:00Z'});
}
for(const [offset,date] of [[0,'2026-11-11'],[1,'2026-11-10'],[7,'2026-11-04']])cache.hourly.push({offset,source_key:'hourly'+offset,slot_msk:date+'T13:00:00+03:00',observed_at:date+'T10:22:00Z',ad_observed_at:date+'T10:22:00Z',ad_status:'complete',ad_missing:[],ad_rows:[{campaign:12345678,clicks:100,orders:2,carts:4,views:1000,spend:5,amount:200}],general:{status:'complete',observed_at:date+'T10:22:00Z',rows:[{nm_id:1473245494,article:'143',selected:{scope:'all_sources',period_from:date,period_to:date,clicks:200,orders:4,cart_count:10}}]}});
const deps={now:()=>now,telegram:async(method,b)=>{
 calls.push({method,b});
 if(method==='answerInlineQuery')return true;
 if(method==='getChatMember')return{user:{id:b.user_id,is_bot:false},status:'member'};
 if(method==='editMessageReplyMarkup')return true;
 assert.ok(['sendMessage','editMessageText','sendPhoto','editMessageMedia'].includes(method));
 const id=b.message_id||next++,photo=['sendPhoto','editMessageMedia'].includes(method);
 const m={message_id:id,chat:{id:CHAT,type:'supergroup'},from:{id:BOT,is_bot:true},reply_markup:b.reply_markup,...(photo?{photo:[{file_id:'mock'}],caption:b.media?.caption||b.caption}:{text:b.text})};
 messages.set(id,m);return m;
},database:async(path,method='GET',body,prefer)=>{
 const [table,q]=path.split('?'),args=new URLSearchParams(q);
 if(table==='rpc/china_menu_inline_products')return {cabinet:'token_3',rows:[{nm:'1111111111',article:'204-test',campaigns:['12345678','87654321']}],truncated:false};
 if(table==='rpc/china_menu_product_lookup')return {cabinet:'token_3',rows:body.p_query.includes('204')?[{nm:'1111111111',article:'204-test'}]:[],truncated:false};
 if(table==='rpc/china_menu_product_ad_cache'){assert.equal(body.p_nm,1111111111);return {cabinet:'token_3',nm:'1111111111',daily:cache.daily.concat(cache.daily.map(r=>({...r,campaign:'87654321',spend:100,amount:1000}))),hourly:cache.hourly,current_campaigns:[{campaign:'12345678'},{campaign:'87654321'}]};}
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
const menu=advertisingMenu();assert.deepEqual(menu.reply_markup.inline_keyboard.map(r=>r[0].text),['Предложить кандидатов','Конверсии и воронка','ДРР','Кто вырос','Кто упал','‹ Главное меню']);
await raw('cmn1:growth');m=[...messages.values()].at(-1);assert.match(m.text,/Растёт/);assert.doesNotMatch(m.text,/Падает:/);assert.match(m.text,/К неделе/);
await click('К неделе');await click('По количеству');assert.match(m.text,/по количеству/);
await raw('cmn1:decline');m=[...messages.values()].at(-1);assert.match(m.text,/Падает/);assert.doesNotMatch(m.text,/Растёт:/);
await click('Падает');assert.match(m.text,/Падает/);assert.ok(m.reply_markup.inline_keyboard.flat().some(b=>b.text==='‹ Реклама'));
await raw('cmn1:conversions');m=[...messages.values()].at(-1);await click('Рекламная конверсия');await click('РК 12345678');await click('7 полных дней');assert.ok(m.photo);assert.match(m.caption,/CR/);assert.ok(calls.at(-1).b.photo_bytes instanceof Uint8Array);
fs.writeFileSync('work/advertising-menu11/conversion-test.png',calls.at(-1).b.photo_bytes);
await click('Таблица по дням');assert.ok(m.photo);assert.match(m.caption,/CR/);fs.writeFileSync('work/advertising-menu11/conversion-table-test.png',calls.at(-1).b.photo_bytes);
await click('Изменить период');await click('Сегодня к тому же часу');assert.match(m.text,/Вчера/);assert.match(m.text,/Неделю назад/);assert.match(m.text,/2%/);
await raw('cmn1:conversions');m=[...messages.values()].at(-1);await click('Общая воронка товара');await click('143');await click('Выбрать даты');await click('1');await click('3');await click('Показать');assert.match(m.caption,/2026-11-01 — 2026-11-03/);await click('Таблица по дням');assert.ok(m.photo);assert.match(m.caption,/Открытия/);
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

assert.equal(drrValue({spend:150,amount:0,orders:0}),null);
assert.equal(metricHeadline({spend:150,amount:0,orders:0},'ad','drr'),'Нет заказов · расход 150 CNY');
assert.equal(drrValue({spend:100,amount:100,orders:1}),100);
assert.equal(drrValue({spend:1,amount:null,orders:1}),null);
await raw('cmn1:drrview');m=[...messages.values()].at(-1);assert.match(m.text,/ДРР/);
await click('Найти товар по артикулу');const prompt=m;assert.equal(prompt.reply_markup.force_reply,true);
const reply={update_id:u++,message:{message_id:800,text:'204',from:{id:7,is_bot:false},chat:{id:CHAT,type:'supergroup'},reply_to_message:prompt}};
await handleAdvertisingPath(config,reply,deps);m=[...messages.values()].at(-1);await click('204-test');assert.match(m.text,/кампания показывается отдельно/);assert.equal(m.reply_markup.inline_keyboard.flat().filter(b=>b.text.startsWith('РК ')).length,2);
await click('РК 12345678');await click('7 полных дней');assert.match(m.caption,/204-test/);assert.match(m.caption,/ДРР 2,5%/);await click('Таблица по дням');assert.ok(m.photo);fs.writeFileSync('work/advertising-menu11/drr-table-test.png',calls.at(-1).b.photo_bytes);
const width=new DataView(calls.at(-1).b.photo_bytes.buffer).getUint32(16),height=new DataView(calls.at(-1).b.photo_bytes.buffer).getUint32(20);assert.ok(width>height,'Daily table must be landscape');
assert.equal(await handleAdvertisingPath(config,{...reply,update_id:u++,message:{...reply.message,reply_to_message:{...prompt,message_id:999999}}},deps),null,'Unbound reply must not consume arbitrary questions');
assert.equal(await handleAdvertisingPath(config,{...reply,update_id:u++,message:{...reply.message,from:{id:8,is_bot:false}}},deps),null,'Other actor cannot use search prompt');
await raw('cmn1:conversions');m=[...messages.values()].at(-1);await click('Рекламная конверсия');await click('Найти товар по артикулу');const cp=m;await handleAdvertisingPath(config,{update_id:u++,message:{message_id:801,text:'204',from:{id:7,is_bot:false},chat:{id:CHAT,type:'supergroup'},reply_to_message:cp}},deps);m=[...messages.values()].at(-1);await click('204-test');await click('РК 87654321');await click('7 полных дней');assert.match(m.caption,/CR 2%/);assert.doesNotMatch(m.caption,/ДРР 2,5%/);
console.log('PASS DRR navigation; zero orders shows no orders plus spend; numeric100 only for equal expense/order amount; article search is actor/prompt bound; separate campaign metrics; preserved product/period; horizontal PNG daily tables.');

c.set('china_agent:main_menu:v1:policy',{enabled:true,inline_search_enabled:true});
await raw('cmn1:drrview');m=[...messages.values()].at(-1);
const searchButton=m.reply_markup.inline_keyboard.flat().find(b=>b.text==='Найти товар по артикулу');assert.equal(searchButton.switch_inline_query_current_chat,'ДРР ');assert.equal(searchButton.callback_data,undefined);
const iq={update_id:u++,inline_query:{id:'inline1',from:{id:7,is_bot:false},chat_type:'supergroup',query:'ДРР 204 сумка',offset:''}};
await handleInlineSearch(config,iq,deps);const response=calls.at(-1);assert.equal(response.method,'answerInlineQuery');assert.equal(response.b.is_personal,true);assert.equal(response.b.cache_time,1);assert.equal(response.b.results[0].title,'204-test');
const result=response.b.results[0],button=result.reply_markup.inline_keyboard[0][0];assert.match(button.callback_data,/cai1:/);
const beforeSend=calls.filter(x=>x.method==='sendMessage').length;
await handleInlineSearch(config,{update_id:u++,callback_query:{id:'inlinePick',from:{id:7,is_bot:false},inline_message_id:'opaque-inline-id',data:button.callback_data}},deps);m=[...messages.values()].at(-1);assert.match(m.text,/ДРР.*204-test/);assert.equal(m.chat.id,CHAT);assert.equal(calls.filter(x=>x.method==='sendMessage').length,beforeSend+1,'Inline selection must continue only in work group');
const cross=await handleInlineSearch(config,{update_id:u++,callback_query:{id:'cross',from:{id:8,is_bot:false},inline_message_id:'opaque-inline-id',data:button.callback_data}},deps);assert.match(await cross.text(),/поиск заново/);
const inlineForeign=await handleInlineSearch(config,{...iq,update_id:u++,inline_query:{...iq.inline_query,id:'private',chat_type:'private'}},deps);assert.equal(calls.at(-1).b.results.length,0);
await handleInlineSearch(config,{...iq,update_id:u++,inline_query:{...iq.inline_query,id:'unknownActor',from:{id:8,is_bot:false}}},deps);assert.equal(calls.at(-1).b.results.length,0);
const record=c.get('china_agent:advertising_ui:v1:inline_result:'+result.id);record.expires_at='2026-11-10T00:00:00Z';const expired=await handleInlineSearch(config,{update_id:u++,callback_query:{id:'expired',from:{id:7,is_bot:false},inline_message_id:'opaque-inline-id',data:button.callback_data}},deps);assert.match(await expired.text(),/поиск заново/);
console.log('PASS native inline switch; personal per-actor results; section/period preserved; native campaign continuation only in bound work group; foreign chat, wrong actor and expired selection rejected; no ForceReply needed.');
