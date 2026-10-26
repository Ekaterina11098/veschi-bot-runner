import {stripTypeScriptTypes} from 'node:module';
import vm from 'node:vm';import fs from 'node:fs';import assert from 'node:assert/strict';import {webcrypto} from 'node:crypto';
const secret='test-secret';const digest=Buffer.from(await webcrypto.subtle.digest('SHA-256',Buffer.from(secret))).toString('hex');
let cfg={agent_id:'china',chat_id:-123,owner_user_id:5,bot_id:9,bot_username:'china_test_bot',active:true,secret_digest:digest};
let adsBound=false;
let handler,jobs=[],dispatches=[],line=null;const acknowledgements=new Map();
const env={SUPABASE_URL:'https://test.supabase.co',SUPABASE_SERVICE_ROLE_KEY:'test',CHINA_TELEGRAM_BOT_TOKEN:'test',GITHUB_WORKFLOW_DISPATCH_TOKEN:'test'};
const ctx={Response,Request,AbortSignal,TextEncoder,crypto:webcrypto,console,Deno:{env:{get:k=>env[k]},serve:f=>handler=f},fetch:async(url,opt)=>{
 const u=new URL(url),p=u.searchParams,b=opt.body?JSON.parse(opt.body):null;
 let result=[];
 if(u.hostname==='api.github.com'){dispatches.push(b);return new Response(null,{status:204});}
 if(u.hostname==='api.telegram.org'){
  if(u.pathname.endsWith('/getMe'))result={id:9};
  else if(u.pathname.endsWith('/getChatMember'))result={status:'administrator',user:{id:9}};
  else if(u.pathname.endsWith('/getChat'))result={type:'supergroup'};
  else throw Error('Unexpected Telegram action');
  return Response.json({ok:true,result});
 }
 const table=u.pathname.split('/').pop();
 if(table==='business_agent_config'){
  if(p.get('agent_id')==='neq.china')result=[];
  else if(opt.method==='PATCH'){cfg={...cfg,...b};result=[cfg];}
  else result=[cfg];
 }else if(table==='telegram_api_cache'){
  if(adsBound && p.get('cache_key')?.includes('advertising_dialog_message:v1:71'))return Response.json([{payload:{chat_id:cfg.chat_id,plan_id:'dialog-ads-1-raise'}}]);
  if(b?.cache_key?.includes('question_ack')){if(!acknowledgements.has(b.cache_key)){acknowledgements.set(b.cache_key,b);result=[b];}}
  else if(b?.cache_key?.includes('chat_migration')||p.get('cache_key')?.includes('chat_migration')){
   if(opt.method==='POST'){line=b;result=[line];}else result=line?[line]:[];
  }
 }else if(table==='business_agent_jobs'){
  if(opt.method==='POST'){if(!jobs.some(j=>j.update_id===b.update_id)){const j={id:jobs.length+1,status:'pending',...b};jobs.push(j);result=[j];}}
  else result=jobs.filter(j=>'eq.'+j.update_id===p.get('update_id'));
 }else if(table!=='advertising_telegram_chat')throw Error('Unexpected table '+table);
 return Response.json(result);
}};
vm.createContext(ctx);vm.runInContext(stripTypeScriptTypes(fs.readFileSync('scripts/china_webhook.ts','utf8').replace("}catch{return new Response('Queue unavailable',{status:503});}","}catch(e){ console.log('TEST ERROR',e.message);return new Response('Queue unavailable',{status:503});}")),ctx);
const call=(update,s=secret)=>handler(new Request('https://edge.test',{method:'POST',headers:{'X-Telegram-Bot-Api-Secret-Token':s},body:JSON.stringify(update)}));
const msg=(id,sender=6,chat=-123)=>({update_id:id,message:{message_id:id,chat:{id:chat,type:'supergroup'},from:{id:sender},text:'Покажи сохранённые данные Китая'}});
assert.equal((await call(msg(1),'wrong')).status,401);assert.equal(jobs.length,0);
const firstAck=await call(msg(1));assert.equal(firstAck.status,200);const ack=await firstAck.json();assert.equal(ack.method,'sendMessage');assert.equal(ack.reply_parameters.message_id,1);assert.match(ack.text,/Принял в работу/);assert.equal(jobs.length,1);assert.equal(jobs[0].sender_id,6);assert.equal(dispatches[0].inputs.action,'dialog');assert.equal(dispatches[0].inputs.job_id,'1');
const duplicateAck=await call(msg(1));assert.equal(await duplicateAck.text(),'OK');assert.equal(jobs.length,1);assert.equal(acknowledgements.size,1);assert.equal([...acknowledgements.values()][0].payload.telegram_receipt_verified,false);
await call(msg(2,5));assert.equal(jobs.length,2);
await call(msg(3,6,-99));assert.equal(jobs.length,2);
const bot=msg(4);bot.message.from.is_bot=true;await call(bot);assert.equal(jobs.length,2);
const quoted=msg(5);quoted.message.reply_to_message={from:{id:9},message_id:42,text:'Ответ о товаре 52'};await call(quoted);assert.equal(jobs[2].tool_trace[0].reply_message_id,42);
const migrate={update_id:6,message:{message_id:6,chat:{id:-123,type:'group'},migrate_to_chat_id:-456}};
assert.equal((await call(migrate)).status,200);assert.equal(cfg.chat_id,-456);assert.equal(line.payload.verified,true);
assert.equal((await call(migrate)).status,200);assert.equal(cfg.chat_id,-456);
const bad={update_id:7,message:{message_id:7,chat:{id:-999,type:'group'},migrate_to_chat_id:-888}};assert.equal((await call(bad)).status,503);assert.equal(cfg.chat_id,-456);
console.log('Webhook auth, all-member input, exact dispatch, duplicate, reply and migration checks passed');




adsBound=true;const beforeAds=jobs.length;const ad=msg(99,6,cfg.chat_id);ad.message.text='Подтверждаю';ad.message.reply_to_message={from:{id:9},message_id:71,text:'Точный план рекламы'};const resultAds=await call(ad);assert.equal(resultAds.status,200);assert.equal(jobs.length,beforeAds+1);assert.equal(jobs.at(-1).request_text,'Подтверждаю');console.log('Advertising confirmation bypasses price routing only with actual bound message');
vm.runInContext('globalThis.priceHandler=handlePriceApproval;globalThis.priceParser=priceApprovalIntent;globalThis.webSame=same;',ctx);
for(const alias of ['делай','сделай все','Сделай всё','примени','меняй цены'])assert.equal(ctx.priceParser(alias).all,true);
for(const negative of ['не делай','не меняй цены'])assert.equal(ctx.priceParser(negative),null);
const report='Повышение · 022-AlessiaBag-grey Продавец: 117,25 → 123,2 ¥\nПокупатель: 1 231 → 1 293 ₽';
const retainedPrices=new Map();const priceDispatch=[];
const priceDeps={deferMembership:true,now:()=>new Date('2026-10-26T14:00:00Z'),same:ctx.webSame,digest:async text=>Buffer.from(await webcrypto.subtle.digest('SHA-256',Buffer.from(text))).toString('hex'),launchPrice:async key=>priceDispatch.push(key),database:async(path,method='GET',body)=>{
if(path.startsWith('business_agent_jobs?'))return [{id:126,request_text:'/china_morning_pair_candidates',answer:report,tool_trace:[{name:'china_price_daily_report',report_date:'2026-10-26'},{name:'china_report_delivery',sent_parts:1}]}];
if(path.includes('eq.china_agent:prices:v1'))return [{payload:{cabinet:'token_3',rows:[{nmID:1473245499,vendorCode:'022-AlessiaBag-grey',currencyIsoCode4217:'CNY',discount:50,clubDiscount:0,editableSizePrice:false,sizes:[{price:234.5,discountedPrice:117.25}]}]}}];
if(method==='POST'){retainedPrices.set(body.cache_key,body.payload);return [body];}
const key=decodeURIComponent(path.match(/cache_key=eq.([^&]+)/)?.[1]??'');return retainedPrices.has(key)?[{payload:retainedPrices.get(key)}]:[];
}};
const priceMessage={message_id:304,chat:{id:-123,type:'supergroup'},from:{id:6,is_bot:false},reply_to_message:{from:{id:9},message_id:300,text:report}};
const priceResult=await ctx.priceHandler({active:true,chat_id:-123,bot_id:9},priceMessage,'сделай все',12345,priceDeps);
assert.match((await priceResult.json()).text,/Подтверждение принято/);assert.equal(priceDispatch.length,1);assert.equal([...retainedPrices.values()][0].selections[0].target_cny,'123.2');
console.log('Natural price approval binds exact report and dispatches exact target; negations rejected');

