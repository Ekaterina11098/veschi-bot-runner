import assert from 'node:assert/strict';
import {mainKeyboard,salesView,advertisingView,handleMainMenu,ROOT}from './china_main_menu.mjs';
const CHAT=-1004342917488,BOT=8780468043,NOW=new Date('2026-11-11T09:10:00Z');
const basis='FBS created units, all statuses, dedup id; native CNY buyer-discounted amount; not buyouts or all sales models';
function order(d,h,count,amount){return {status:'complete',basis,start_msk:d+'T00:00:00+03:00',end_msk:d+'T'+h+':00:00+03:00',totals:{count,amount_cny:amount,unknown_amount_ids:[]}};}
function fixture(){
 const c=new Map(),calls=[],config={active:true,chat_id:CHAT,bot_id:BOT,bot_username:'veschi_china_agent_bot'};
 const key='china_agent:hourly_sales_api:v1:snapshot:2026-11-11T12:MSK:attempt:123';
 c.set(ROOT+'policy',{enabled:true});c.set('china_agent:hourly_sales_api:v1:latest',{source_key:key,slot_msk:'2026-11-11T12:00:00+03:00'});
 c.set(key,{cabinet:'token_3',slot_msk:'2026-11-11T12:00:00+03:00',observed_at:'2026-11-11T09:08:00Z',status:'partial',orders:{'0':order('2026-11-11','12',100,20000),'1':order('2026-11-10','12',80,16000),'7':order('2026-11-04','12',50,12000)}});
 const get=async k=>structuredClone(c.get(k));
 const deps={now:()=>NOW,telegram:async(method,body)=>{
 calls.push({method,body});if(method==='getChatMember')return {user:{id:body.user_id,is_bot:false},status:'member'};
 assert.ok(['sendMessage','editMessageText'].includes(method));
 return {message_id:body.message_id||999,chat:{id:CHAT},from:{id:BOT},reply_markup:body.reply_markup,text:body.text};
 },database:async(path,method='GET',body)=>{
 const [table,q]=path.split('?');assert.equal(table,'telegram_api_cache','Menu must not create jobs');const a=new URLSearchParams(q);
 if(method==='POST'){if(c.has(body.cache_key))return [];c.set(body.cache_key,structuredClone(body.payload));return [body];}
 const key=a.get('cache_key').slice(3);
 if(method==='GET')return c.has(key)?[{payload:await get(key)}]:[];
 assert.equal(method,'PATCH');assert.ok(c.has(key));c.set(key,structuredClone(body.payload));return [body];}};
 const message={message_id:10,text:'📊 Продажи',chat:{id:CHAT,type:'supergroup'},from:{id:7,is_bot:false}};
 return {c,key,get,deps,config,message,calls};
}
{
 const w=fixture(),v=await salesView(w.get,NOW);assert.match(v.text,/100 шт/);assert.match(v.text,/25%/);assert.match(v.text,/Неделю назад/);assert.match(v.text,/66,67%/);assert.match(v.text,/FBS/);assert.doesNotMatch(v.text,/данные отстают/);assert.deepEqual(v.source_keys,[w.key]);
 w.c.get(w.key).orders['7'].end_msk='2026-11-04T23:00:00+03:00';
 assert.match((await salesView(w.get,NOW)).text,/Неделю назад: нет сопоставимых данных/);
 w.c.get(w.key).orders['0'].totals.unknown_amount_ids=['unknown'];
 assert.match((await salesView(w.get,NOW)).text,/неполные/);
}
{
 const w=fixture();w.c.get(w.key).observed_at='2026-11-11T06:00:00Z';assert.match((await salesView(w.get,NOW)).text,/данные отстают/);
 w.c.get(w.key).cabinet='other';assert.match((await salesView(w.get,NOW)).text,/Нет подтверждённого среза/);
}
{
 const w=fixture(),v=await salesView(w.get,NOW,true);assert.match(v.text,/Динамика/);assert.match(v.text,/накопительные/);assert.match(v.text,/05:00 · нет данных/);
}
{
 const w=fixture(),receipt={message_id:50,date:1794380000,chat:{id:CHAT},from:{id:BOT},photo:[{file_id:'test-photo'}]};
 w.c.set('china_agent:daily_ad_current_report:v1:drr',{plan_id:'p'});
 w.c.set('china_agent:loss_plan:v1:p',{plan_id:'p',plan_sha256:'hash',report_message_ids:[50]});
 w.c.set(ROOT+'report:drr',{status:'sent',family:'drr',chat_id:CHAT,bot_id:BOT,plan_id:'p',plan_sha256:'hash',message_id:50,report_day:'2026-11-11',receipt});
 assert.equal((await advertisingView(w.get,'drr',NOW)).photos[0].photo,'test-photo');
 w.c.get('china_agent:loss_plan:v1:p').invalidated_at=NOW.toISOString();
 assert.match((await advertisingView(w.get,'drr',NOW)).text,/недоступен/);
}
{
 const w=fixture(),u={update_id:1,message:w.message};
 await handleMainMenu(w.config,u,w.deps);await handleMainMenu(w.config,u,w.deps);
 assert.equal(w.calls.filter(x=>x.method==='sendMessage').length,1);
 assert.equal(w.c.get(ROOT+'delivery:1').status,'sent');
 assert.equal(await handleMainMenu(w.config,{update_id:2,message:{...w.message,text:'Сделай всё'}},w.deps),null);
 assert.equal(await handleMainMenu(w.config,{update_id:3,message:{...w.message,text:'__proto__'}},w.deps),null);
 await handleMainMenu(w.config,{update_id:4,message:{...w.message,chat:{id:-123,type:'supergroup'}}},w.deps);
 assert.equal(w.calls.filter(x=>x.method==='sendMessage').length,1);
 const cb={id:'c',data:'cmn1:ads',from:{id:7,is_bot:false},message:{...w.message,message_id:999,from:{id:BOT,is_bot:true}}};
 await handleMainMenu(w.config,{update_id:5,callback_query:cb},w.deps);
 assert.equal(w.calls.at(-1).method,'editMessageText');assert.equal(w.calls.at(-1).body.message_id,999);
 assert.match(w.calls.at(-1).body.text,/Реклама/);
}
assert.deepEqual(mainKeyboard.keyboard.map(r=>r[0].text),['📊 Продажи','📣 Реклама']);
console.log('PASS: same-window both bases, incomplete/unknown/stale data, exact attempt, hourly dynamics gaps, revoked reports, no worker dispatch, duplicate input, foreign chat, preserved callback identity, two-button keyboard.');
