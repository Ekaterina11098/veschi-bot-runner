import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {priceApprovalIntent,reportProposals,handlePriceApproval} from './china_price_approvals.ts';
const digest=async text=>Buffer.from(await webcrypto.subtle.digest('SHA-256',Buffer.from(text))).toString('hex');
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const config={active:true,chat_id:-123,owner_user_id:5,bot_id:9};
const report='Повышение · A-bag Продавец: 100 → 110 ¥\nПокупатель: 1 000 → 1 100 ₽\n\nСнижение · B-bag Продавец: 130 → 100 ¥\nПокупатель: 1 300 → 1 000 ₽';
const catalog={cabinet:'token_3',rows:[{nmID:111,vendorCode:'A-bag',currencyIsoCode4217:'CNY',sizes:[{discountedPrice:100}],discount:50},{nmID:222,vendorCode:'B-bag',currencyIsoCode4217:'CNY',sizes:[{discountedPrice:130}],discount:50}]};
function context(){
 const cache=new Map();const calls=[];let membership='member';let catalogue=structuredClone(catalog);let saved=report;
 const deps={digest,same,now:()=>new Date('2026-10-19T13:00:00Z'),
  telegram:async(method,body)=>{assert.equal(method,'getChatMember');return {status:membership,user:{id:body.user_id,is_bot:false}};},
  database:async(path,method='GET',body)=>{
   calls.push({path,method,body});const p=new URL('https://db/'+path).searchParams;
   if(path.startsWith('business_agent_jobs')){assert.equal(method,'GET');return [{id:57,answer:saved,tool_trace:[{name:'china_price_daily_report',report_date:'2026-10-19'},{name:'china_report_delivery',sent_parts:1}]}];}
   assert.ok(path.startsWith('telegram_api_cache'));
   if(p.get('cache_key')==='eq.china_agent:prices:v1')return [{payload:catalogue}];
   if(method==='POST'){assert.equal(body.payload.execution_authorized,false);if(cache.has(body.cache_key))return [];cache.set(body.cache_key,body);return [body];}
   const key=p.get('cache_key').slice(3);return cache.has(key)?[cache.get(key)]:[];
  }};
 return {deps,cache,calls,setMember:s=>membership=s,setSaved:s=>saved=s,setCatalogue:c=>catalogue=c};
}
function message(actor=6){
 return {message_id:70,chat:{id:-123,type:'supergroup'},from:{id:actor,first_name:'Test'},reply_to_message:{from:{id:9},message_id:61,text:report}};
}
const run=async(c,m=message(),text='Подтверждаю все изменения',id=90)=>handlePriceApproval(config,m,text,id,c.deps);
assert.equal(priceApprovalIntent('Почему снизилась конверсия?'),null);
assert.equal(priceApprovalIntent('Подтверждаю все изменения').all,true);
assert.equal(priceApprovalIntent('Да, давай изменим цена как ты предлагаешь').all,true);
assert.equal(priceApprovalIntent('/price_confirm').all,true);
assert.equal(reportProposals(report).length,2);
for(const actor of [5,6,77]){
 const c=context();const response=await run(c,message(actor));assert.equal(response.status,200);
 const ack=await response.json();assert.ok(ack.text.includes('Подтверждение сохранено'));
 const decision=[...c.cache.values()][0].payload;assert.equal(decision.actor_user_id,actor);assert.equal(decision.selections.length,2);
 assert.equal(decision.execution_authorized,false);assert.equal(decision.wb_writes,0);assert.equal(decision.report_message_id,61);
 assert.equal(c.calls.filter(x=>x.method==='POST').length,1);
}
{
 const c=context();await run(c);await run(c);assert.equal(c.cache.size,1);
 const reply=await (await run(c,message(),'Подтверждаю: B-bag',91)).json();assert.ok(reply.text.includes('B-bag'));assert.equal(c.cache.size,2);
}
for(const state of ['left','kicked']){
 const c=context();c.setMember(state);await run(c);assert.equal(c.cache.size,0);
}
for(const mutate of [
 m=>m.from.is_bot=true,m=>m.sender_chat={id:-123},m=>m.forward_origin={type:'user'},
 m=>m.chat.id=-999,m=>delete m.reply_to_message,m=>m.reply_to_message.from.id=88,m=>m.reply_to_message.text='Поддельный отчёт'
]){
 const c=context();const m=message();mutate(m);await run(c,m);assert.equal(c.cache.size,0);
}
{
 const c=context();c.setSaved(report+'\nДругая версия');await run(c);assert.equal(c.cache.size,0);
}
{
 const c=context();await run(c,message(),'Подтверждаю: UNKNOWN');assert.equal(c.cache.size,0);
}
{
 const c=context();const changed=structuredClone(catalog);changed.rows[0].sizes[0].discountedPrice=101;c.setCatalogue(changed);await run(c);assert.equal(c.cache.size,0);
}
{
 const c=context();await run(c,message(),'Подтверждаю');assert.equal(c.cache.size,0);
}
{
 const c=context();const response=await run(c,message(),'Покажи продажи');assert.equal(response,null);assert.equal(c.calls.length,0);
}
console.log('All-member recommendation decisions: owner/non-owner, exact reply/selection, idempotency, membership and zero execution passed');
