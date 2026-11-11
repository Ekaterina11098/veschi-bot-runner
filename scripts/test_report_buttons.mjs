import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {handleReportButtons,keyboard}from './china_report_buttons.mjs';
const ROOT='china_agent:report_buttons:v1:',TOKEN='a'.repeat(24),CHAT=-1004342917488,BOT=8780468043;
function fixture(family='drr'){
 const cache=new Map(),jobs=[],calls=[];let mid=1000;
 const actual=[{id:'up',kind:'ad_set_bid',campaign_id:1,article:'A',old_minor:28,target_minor:30},{id:'add',kind:'ad_add_sku',campaign_id:2,article:'B',placement:'search',target_minor:11},{id:'fund',kind:'topup_campaign',campaign_id:1,amount_cny:100}];
 const items=actual.filter(i=>family==='budgets'?i.kind==='topup_campaign':i.kind!=='topup_campaign').map((i,index)=>({...i,index,group:i.id==='fund'?'budget':i.id,amount_cny:i.amount_cny||0}));
 const p={status:'active',chat_id:CHAT,bot_id:BOT,plan_id:'test',plan_sha256:'sha',family,items};
 cache.set(ROOT+'policy',{enabled:true});cache.set(ROOT+'plan:'+TOKEN,p);cache.set('china_agent:loss_plan:v1:test',{plan_id:'test',plan_sha256:'sha',family:'drr',items:actual,expires_at:'2099-01-01T00:00:00Z',validity_mode:'until_replaced',report_generation:'test'});cache.set('china_agent:daily_ad_current_report:v1:drr',{report_generation:'test'});
 cache.set(ROOT+'message:10',{status:'sent',token:TOKEN,plan_sha256:'sha',chat_id:CHAT,receipt:{message_id:10,chat:{id:CHAT}}});
 const deps={now:()=>new Date('2026-11-11T08:00:00Z'),digest:async s=>Buffer.from(await webcrypto.subtle.digest('SHA-256',new TextEncoder().encode(s))).toString('hex'),launch:async id=>calls.push({kind:'launch',id}),telegram:async(method,b)=>{calls.push({method,b});if(method==='getChatMember')return {user:{id:b.user_id,is_bot:false},status:'member'};if(method==='sendMessage')return {message_id:mid++,chat:{id:CHAT},from:{id:BOT,is_bot:true}};if(method==='editMessageReplyMarkup')return true;throw Error('Unapproved Telegram method');},database:async(path,method='GET',body)=>{
  const [table,q]=path.split('?');const args=new URLSearchParams(q);
  if(table==='business_agent_jobs'){
   if(method==='POST'){const existing=jobs.find(j=>j.update_id===body.update_id);if(existing)return [];const j={...body,id:300+jobs.length};jobs.push(j);return [j];}
   return jobs.filter(j=>String(j.update_id)===args.get('update_id')?.slice(3));
  }
  assert.equal(table,'telegram_api_cache');
  if(method==='POST'){if(cache.has(body.cache_key))return [];cache.set(body.cache_key,structuredClone(body.payload));return [{payload:body.payload}];}
  const key=args.get('cache_key').slice(3);const old=cache.get(key);
  if(method==='GET')return old===undefined?[]:[{payload:structuredClone(old)}];
  assert.equal(method,'PATCH');if(!old)return [];const cond=args.get('payload');if(cond&&JSON.stringify(old)!==cond.slice(3))return [];cache.set(key,structuredClone(body.payload));return [{payload:body.payload}];
 }};
 const config={active:true,chat_id:CHAT,bot_id:BOT};
 let update=1;const cb=(op,actor=7,message=10,id)=>({id:id||'cb'+update,data:'cab1:'+TOKEN+':'+op,from:{id:actor,is_bot:false},message:{message_id:message,chat:{id:CHAT,type:'supergroup'},from:{id:BOT,is_bot:true}}});
 async function click(op,actor=7,message=10,id){const c=cb(op,actor,message,id);update++;return (await handleReportButtons(config,c,update,deps)).json();}
 return {cache,jobs,calls,click,config,cb,deps,p};
}
{
 const w=fixture();await w.click('gup',7,10,'duplicate');await w.click('gup',7,10,'duplicate');assert.deepEqual(w.cache.get(ROOT+'selection:'+TOKEN+':7').selected_ids,['up']);assert.equal(w.jobs.length,0);
 await w.click('gadd');await w.click('review');const review=w.cache.get(ROOT+'review_message:1000');assert.deepEqual(review.selected_ids,['up','add']);assert.equal(w.jobs.length,0);
 await w.click('confirm'+review.selection_hash,7,1000);await w.click('confirm'+review.selection_hash,7,1000);assert.equal(w.jobs.length,1);assert.equal(w.jobs[0].tool_trace[0].report_button_confirmation,TOKEN+'-7');
 await w.click('all',8);await w.click('review',8);const other=w.cache.get(ROOT+'review_message:1001');const denied=await w.click('confirm'+other.selection_hash,8,1001);assert.match(denied.text,/уже подтверждена/);assert.equal(w.jobs.length,1);
}
{
 const w=fixture();await w.click('all');await w.click('review');const r=w.cache.get(ROOT+'review_message:1000');await w.click('clear');assert.match((await w.click('confirm'+r.selection_hash,7,1000)).text,/Выбор изменён/);assert.equal(w.jobs.length,0);
 w.cache.get('china_agent:daily_ad_current_report:v1:drr').report_generation='new';assert.match((await w.click('all')).text,/заменён/);
}
{
 const w=fixture('budgets');await w.click('i0');await w.click('review');const r=w.cache.get(ROOT+'review_message:1000');await w.click('confirm'+r.selection_hash,7,1000);assert.deepEqual(w.cache.get(ROOT+'confirmation:'+TOKEN+'-7').selected_ids,['fund']);assert.equal(w.jobs.length,1);assert.ok(w.calls.find(c=>c.method==='sendMessage').b.text.includes('100 CNY'));
}
{
 const w=fixture();w.cache.set('china_agent:daily_ad_execution:v2:test',{items:[{status:'uncertain'}]});assert.match((await w.click('all')).text,/повтор закрыт/i);assert.equal(w.jobs.length,0);
}
{
 const w=fixture();const cb=w.cb('all');cb.message.chat.id=-1;const r=await(await handleReportButtons(w.config,cb,1,w.deps)).json();assert.match(r.text,/недоступна/);assert.equal(w.calls.length,0);
 const page=keyboard(TOKEN,{family:'budgets',items:Array.from({length:13},(_,i)=>({id:String(i),campaign_id:i,amount_cny:100}))},[],1);assert.ok(page.inline_keyboard.flat().some(b=>b.callback_data.endsWith('p2')));
}
console.log('PASS: no execution on selection/review; exact scoped confirmation; duplicate callback; double confirm; competing actor; stale review/report; budget amount; uncertain root; foreign chat; pagination');
