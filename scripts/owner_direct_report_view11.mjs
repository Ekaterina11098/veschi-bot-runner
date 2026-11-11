/** Correct exact delivered navigation card to direct report PNG, not a link. No WB calls. */
import assert from 'node:assert/strict';
import {advertisingView,bindDirectReport}from './china_main_menu.mjs';
const CHAT=-1004342917488,BOT=8780468043,K='china_agent:owner_direct_report_view:2026-11-11:v1';
const url=process.env.SUPABASE_URL,key=process.env.SUPABASE_SECRET_KEY,token=process.env.CHINA_TELEGRAM_BOT_TOKEN;
assert.ok(url&&key&&token);
async function database(path,method='GET',body,prefer){
 const r=await fetch(url+'/rest/v1/'+path,{method,headers:{apikey:key,...(!key.startsWith('sb_secret_')?{Authorization:'Bearer '+key}:{}),'Content-Type':'application/json',...(prefer?{Prefer:prefer}:{})},...(body===undefined?{}:{body:JSON.stringify(body)})});
 if(!r.ok)throw Error('Private state HTTP '+r.status);return r.status===204?null:await r.json();
}
const get=async k=>(await database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(k)+'&select=payload&limit=1'))?.[0]?.payload;
async function create(k,p){return(await database('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:k,payload:p,expires_at:'2036-11-11T00:00:00Z'},'resolution=ignore-duplicates,return=representation')).length===1;}
async function put(k,p){assert.equal((await database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(k),'PATCH',{payload:p},'return=representation')).length,1);}
async function tg(method,body){const r=await fetch('https://api.telegram.org/bot'+token+'/'+method,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await r.json();if(!r.ok||j.ok!==true)throw Error('Telegram direct report HTTP '+r.status);return j.result;}
const prior=await get(K);if(prior){assert.equal(prior.status,'sent');console.log('Direct report correction already delivered');process.exit(0);}
assert.equal((await tg('getMe',{})).id,BOT);
const original=await get('china_agent:main_menu:v1:delivery:532552896');assert.equal(original.status,'sent');assert.equal(original.message_id,878);assert.equal(original.op,'drr');
const view=await advertisingView(get,'drr',new Date(),original.actor_id);
assert.equal(view.photos?.length,1);
const part=view.photos[0],v=part.page_view||view;
assert.ok(!v.reply_markup.inline_keyboard.flat().some(b=>b.text==='Открыть отчёт'));
assert.ok(await create(K,{status:'editing',original_receipt:original.receipt,source_keys:view.source_keys,wb_writes:0}));
const receipt=await tg('editMessageMedia',{chat_id:CHAT,message_id:878,media:{type:'photo',media:part.photo,caption:v.text},reply_markup:v.reply_markup});
assert.equal(receipt.message_id,878);assert.equal(receipt.chat.id,CHAT);assert.ok(receipt.photo?.length);assert.deepEqual(receipt.reply_markup,v.reply_markup);
await put(K,{status:'binding',receipt,original_receipt:original.receipt,wb_writes:0});
await bindDirectReport(v,receipt,{database});
await put(K,{status:'sent',message_id:878,mode:v.direct.mode,receipt,original_receipt:original.receipt,source_keys:view.source_keys,wb_writes:0});
console.log(JSON.stringify({status:'edited_verified',message_id:878,photo:true,mode:v.direct.mode,wb_writes:0}));
