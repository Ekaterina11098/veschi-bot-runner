import assert from 'node:assert/strict';import fs from 'node:fs';import {inflateSync}from'node:zlib';
import {handleSalesPath,renderSales,aggregateRows,verifiedDaily,periodTotal}from './china_sales_ui.mjs';
const ROOT='china_agent:sales_ui:v1:',D='china_agent:sales_menu:v2:day:',CHAT=-1004342917488,BOT=8780468043,now=new Date('2026-11-11T09:20:00Z');
const BASIS='FBS created units, all statuses, dedup id; native CNY buyer-discounted amount; not buyouts or all sales models';
const c=new Map(),calls=[],msgs=new Map();let id=100,update=1;
c.set('china_agent:main_menu:v1:policy',{enabled:true});c.set('china_agent:prices:v1',{cabinet:'token_3',rows:[{nmID:1473243824,vendorCode:'50-NoelBag-yellow'},{nmID:1473245494,vendorCode:'143-Bag'}]});
for(let i=1;i<=28;i++){const date=new Date(Date.parse('2026-11-11T00:00:00Z')-i*86400000).toISOString().slice(0,10),end=new Date(Date.parse(date+'T00:00:00Z')+86400000).toISOString().slice(0,10);
 c.set(D+date,{date,cabinet:'token_3',currency:'CNY',status:'complete',basis:BASIS,start_msk:date+'T00:00:00+03:00',end_msk:end+'T00:00:00+03:00',observed_at:'2026-11-11T09:00:00Z',source:{pagination_complete:true},totals:{count:i*2,amount_cny:i*300,unknown_amount_ids:[]},by_nm:{'1473243824':{count:i,amount_cny:i*100},'1473245494':{count:i,amount_cny:i*200}}});}
const snap='china_agent:hourly_sales_api:v1:snapshot:2026-11-11T12:MSK',p={cabinet:'token_3',slot_msk:'2026-11-11T12:00:00+03:00',observed_at:'2026-11-11T09:07:00Z',orders:{}};
for(const [k,date,amount]of [['0','2026-11-11',20000],['1','2026-11-10',18000],['7','2026-11-04',10000]])p.orders[k]={status:'complete',basis:BASIS,start_msk:date+'T00:00:00+03:00',end_msk:date+'T12:00:00+03:00',rows:[{id:Number(k)+1,nmId:1473243824,convertedPrice:amount,convertedCurrencyCode:156}],totals:{count:1,amount_cny:amount/100,unknown_amount_ids:[]},last_completed_hour:{count:1,amount_cny:amount/100,unknown_amount_ids:[]}};
c.set(snap,p);c.set('china_agent:hourly_sales_api:v1:latest',{source_key:snap});
const deps={now:()=>now,telegram:async(method,b)=>{
 calls.push({method,b});if(method==='getChatMember')return{user:{id:b.user_id,is_bot:false},status:'member'};
 if(method==='editMessageReplyMarkup')return true;
 assert.ok(['sendMessage','editMessageText','sendPhoto','editMessageMedia'].includes(method),'Only Telegram UI methods');
 const mid=b.message_id||id++,photo=method==='editMessageMedia'||method==='sendPhoto',m={message_id:mid,chat:{id:CHAT,type:'supergroup'},from:{id:BOT,is_bot:true},reply_markup:b.reply_markup,...(photo?{photo:[{file_id:'fake'}],caption:b.media?.caption||b.caption}:{text:b.text})};msgs.set(mid,m);return m;
},database:async(path,method='GET',body)=>{
 const [table,q]=path.split('?'),a=new URLSearchParams(q);assert.equal(table,'telegram_api_cache','No jobs, orders or marketplace writes');
 if(method==='POST'){if(c.has(body.cache_key))return[];c.set(body.cache_key,structuredClone(body.payload));return[body];}
 const filter=a.get('cache_key');
 if(filter.startsWith('like.'))return[...c].filter(([k])=>k.startsWith(D)).map(([cache_key,payload])=>({cache_key,payload:structuredClone(payload)}));
 const key=filter.slice(3);if(method==='GET')return c.has(key)?[{payload:structuredClone(c.get(key))}]:[];
 assert.equal(method,'PATCH');assert.ok(c.has(key));c.set(key,structuredClone(body.payload));return[body];}};
const config={active:true,chat_id:CHAT,bot_id:BOT};
const initial={update_id:update++,message:{message_id:1,text:'📊 Продажи',chat:{id:CHAT,type:'supergroup'},from:{id:7,is_bot:false}}};
await handleSalesPath(config,initial,deps);let m=msgs.get(100);
assert.deepEqual(m.reply_markup.inline_keyboard.map(r=>r[0].text),['Динамика по дням','По товарам','Другой период','Главное меню']);assert.match(m.text,/Неделю назад/);
await handleSalesPath(config,initial,deps);assert.equal(msgs.size,1);
async function click(text){const button=m.reply_markup.inline_keyboard.flat().find(b=>b.text===text);assert.ok(button,'Button '+text);const r=await handleSalesPath(config,{update_id:update++,callback_query:{id:'c'+update,data:button.callback_data,from:{id:7,is_bot:false},message:m}},deps);const j=await r.clone().text();assert.doesNotMatch(j,/"show_alert":true/);m=[...msgs.values()].at(-1);return m;}
await click('Динамика по дням');assert.ok(m.photo);const photoCall=calls.find(x=>x.method==='editMessageMedia');const bytes=photoCall.b.photo_bytes;assert.deepEqual([...bytes.slice(0,8)],[137,80,78,71,13,10,26,10]);
let pos=8,idats=[];while(pos<bytes.length){const v=new DataView(bytes.buffer,bytes.byteOffset+pos),len=v.getUint32(0);const type=new TextDecoder().decode(bytes.slice(pos+4,pos+8));if(type==='IDAT')idats.push(bytes.slice(pos+8,pos+8+len));pos+=12+len;}assert.equal(inflateSync(Buffer.concat(idats)).length,780*(1+800*3));
fs.writeFileSync('work/main-menu11/sales-path-test-chart.png',bytes);assert.match(m.caption,/2026-10-28 — 2026-11-10/);
await click('7 дней');assert.match(m.caption,/2026-11-04 — 2026-11-10/);await click('Таблица по дням');assert.ok(m.text);assert.match(m.text,/К неделе/);await click('‹ К сводке');await click('По товарам');await click('Лидеры продаж');await click('По сумме заказов');assert.match(m.text,/Доля в сумме: 66,67%/);assert.match(m.text,/в количестве: 50%/);await click('По количеству');assert.match(m.text,/по количеству заказов/);await click('50-NoelBag-yellow');assert.match(m.text,/50-NoelBag-yellow/);assert.match(m.text,/2026-11-04 — 2026-11-10/);await click('‹ К лидерам');assert.match(m.text,/по количеству заказов/);await click('50-NoelBag-yellow');
await click('Другой период');await click('Выбрать даты');await click('1');await click('3');await click('Показать');assert.match(m.text,/2026-11-01 — 2026-11-03/);
await click('По товарам');await click('Найти товар по артикулу');assert.equal(m.reply_markup.force_reply,true);const searchMsg=m;
await handleSalesPath(config,{update_id:update++,message:{message_id:5,text:'143',chat:{id:CHAT,type:'supergroup'},from:{id:7,is_bot:false},reply_to_message:searchMsg}},deps);m=[...msgs.values()].at(-1);await click('143-Bag');assert.match(m.text,/2026-11-01 — 2026-11-03/);assert.match(m.text,/143-Bag/);
assert.equal(aggregateRows([{id:1,nmId:1,convertedCurrencyCode:643,convertedPrice:3}]),null);
assert.equal(verifiedDaily({...c.get(D+'2026-11-10'),source:{pagination_complete:false}},'2026-11-10',now),false);
assert.equal(periodTotal(new Map(),'2026-11-01','2026-11-03'),null);
const before=calls.length;await handleSalesPath(config,{update_id:update++,message:{...initial.message,chat:{id:-1,type:'supergroup'}}},deps);assert.equal(calls.length,before);
{
 const data={names:new Map([['111111','A'],['222222','B']]),days:new Map([['2026-11-10',{totals:{count:10,amount_cny:1000},by_nm:{'111111':{count:9,amount_cny:90},'222222':{count:1,amount_cny:910}},observed_at:'2026-11-11T09:00:00Z'}]])};
 const ctx={view:'list',sort:'leaders',period:'range',start:'2026-11-10',end:'2026-11-10'};
 const sum=await renderSales({...ctx,metric:'amount_cny'},data,'a'.repeat(16),now);assert.ok(sum.text.indexOf('1. B:')<sum.text.indexOf('2. A:'));assert.match(sum.text,/Доля в сумме: 91% · в количестве: 10%/);
 const count=await renderSales({...ctx,metric:'count'},data,'a'.repeat(16),now);assert.ok(count.text.indexOf('1. A:')<count.text.indexOf('2. B:'));assert.match(count.text,/Доля в сумме: 9% · в количестве: 90%/);assert.match(count.text,/нет сопоставимых данных/);assert.doesNotMatch(count.text,/Вклад к выбранной базе/);
 data.days.set('2026-11-10',{totals:{count:0,amount_cny:0},by_nm:{},observed_at:'2026-11-11T09:00:00Z'});const empty=await renderSales(ctx,data,'a'.repeat(16),now);assert.match(empty.text,/созданных заказов нет/);assert.doesNotMatch(empty.text,/Доля.*0%/);
}
console.log('PASS Sales full path, both leader rankings and whole-period shares; return preserves metric/period; unknown bases and zero totals stay explicit; no jobs/WB calls.');
