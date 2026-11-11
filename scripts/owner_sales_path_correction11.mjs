/** Correct the existing delivered Sales screen to the approved path. No WB calls. */
import assert from 'node:assert/strict';
import {source,renderSales}from './china_sales_ui.mjs';
const ROOT='china_agent:sales_ui:v1:',K='china_agent:owner_sales_path_correction:2026-11-11:v1',CHAT=-1004342917488,BOT=8780468043;
const url=process.env.SUPABASE_URL,key=process.env.SUPABASE_SECRET_KEY,token=process.env.CHINA_TELEGRAM_BOT_TOKEN;
assert.ok(url&&key&&token);
async function database(path,method='GET',body,prefer){
 const r=await fetch(url+'/rest/v1/'+path,{method,headers:{apikey:key,...(!key.startsWith('sb_secret_')?{Authorization:'Bearer '+key}:{}),'Content-Type':'application/json',...(prefer?{Prefer:prefer}:{})},...(body===undefined?{}:{body:JSON.stringify(body)})});
 if(!r.ok)throw Error('Private state HTTP '+r.status);return r.status===204?null:await r.json();
}
async function get(k){return(await database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(k)+'&select=payload&limit=1'))?.[0]?.payload;}
async function create(k,v){return(await database('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:k,payload:v,expires_at:'2036-11-11T00:00:00Z'},'resolution=ignore-duplicates,return=representation')).length===1;}
async function put(k,v){assert.equal((await database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(k),'PATCH',{payload:v},'return=representation')).length,1);}
async function tg(method,body){const r=await fetch('https://api.telegram.org/bot'+token+'/'+method,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await r.json();if(!r.ok||j.ok!==true)throw Error('Telegram correction HTTP '+r.status);return j.result;}
const old=await get(K);if(old){assert.equal(old.status,'sent');console.log('Corrected Sales screen already delivered');process.exit(0);}
assert.equal((await tg('getMe',{})).id,BOT);
const input=await get('china_agent:main_menu:v1:delivery:532552888');assert.equal(input.status,'sent');assert.equal(input.message_id,874);assert.equal(input.receipt.chat.id,CHAT);
const ctx={period:'today',view:'summary'},now=new Date(),data=await source({database},get,ctx,now);
assert.ok(data.hourly);assert.equal(data.days.size>=28,true);
const sid=[...crypto.getRandomValues(new Uint8Array(8))].map(x=>x.toString(16).padStart(2,'0')).join('');
const view=await renderSales(ctx,data,sid,now);
assert.deepEqual(view.reply_markup.inline_keyboard.map(r=>r[0].text),['Динамика по дням','По товарам','Другой период','Главное меню']);
const session={actor:5122667182,context:ctx,message_id:874,expires_at:new Date(now.getTime()+86400000).toISOString()};
assert.ok(await create(ROOT+'session:'+sid,session));
assert.ok(await create(K,{status:'editing',original_receipt:input.receipt,source_keys:data.source_keys,wb_writes:0}));
const receipt=await tg('editMessageText',{chat_id:CHAT,message_id:874,text:view.text,reply_markup:view.reply_markup});
assert.equal(receipt.message_id,874);assert.equal(receipt.chat.id,CHAT);assert.deepEqual(receipt.reply_markup,view.reply_markup);
await put(K,{status:'sent',message_id:874,receipt,original_receipt:input.receipt,source_keys:data.source_keys,wb_writes:0});
console.log(JSON.stringify({status:'edited_verified',message_id:874,buttons:4,completed_days:data.days.size,wb_writes:0}));
