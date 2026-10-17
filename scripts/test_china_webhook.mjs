import {stripTypeScriptTypes} from 'node:module';
import vm from 'node:vm';import fs from 'node:fs';import assert from 'node:assert/strict';import {webcrypto} from 'node:crypto';
const secret='test-secret';const digest=Buffer.from(await webcrypto.subtle.digest('SHA-256',Buffer.from(secret))).toString('hex');
let cfg={agent_id:'china',chat_id:-123,owner_user_id:5,bot_id:9,bot_username:'china_test_bot',active:true,secret_digest:digest};
let handler,jobs=[],dispatches=[],line=null;
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
  if(b?.cache_key?.includes('chat_migration')||p.get('cache_key')?.includes('chat_migration')){
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
assert.equal((await call(msg(1))).status,200);assert.equal(jobs.length,1);assert.equal(jobs[0].sender_id,6);assert.equal(dispatches[0].inputs.action,'dialog');assert.equal(dispatches[0].inputs.job_id,'1');
await call(msg(1));assert.equal(jobs.length,1);
await call(msg(2,5));assert.equal(jobs.length,2);
await call(msg(3,6,-99));assert.equal(jobs.length,2);
const bot=msg(4);bot.message.from.is_bot=true;await call(bot);assert.equal(jobs.length,2);
const quoted=msg(5);quoted.message.reply_to_message={from:{id:9},message_id:42,text:'Ответ о товаре 52'};await call(quoted);assert.equal(jobs[2].tool_trace[0].reply_message_id,42);
const migrate={update_id:6,message:{message_id:6,chat:{id:-123,type:'group'},migrate_to_chat_id:-456}};
assert.equal((await call(migrate)).status,200);assert.equal(cfg.chat_id,-456);assert.equal(line.payload.verified,true);
assert.equal((await call(migrate)).status,200);assert.equal(cfg.chat_id,-456);
const bad={update_id:7,message:{message_id:7,chat:{id:-999,type:'group'},migrate_to_chat_id:-888}};assert.equal((await call(bad)).status,503);assert.equal(cfg.chat_id,-456);
console.log('Webhook auth, all-member input, exact dispatch, duplicate, reply and migration checks passed');

