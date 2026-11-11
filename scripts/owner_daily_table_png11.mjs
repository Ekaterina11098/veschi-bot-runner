import {conversionView} from './china_advertising_ui.mjs';
const URL=process.env.SUPABASE_URL,KEY=process.env.SUPABASE_SECRET_KEY,TOKEN=process.env.CHINA_TELEGRAM_BOT_TOKEN;
if(!URL||!KEY||!TOKEN)throw Error('Missing transport');
const CHAT=-1004342917488,BOT=8780468043,K='china_agent:owner_daily_table_png:2026-11-11:v1';
async function db(path,method='GET',body,prefer){const r=await fetch(URL+'/rest/v1/'+path,{method,headers:{apikey:KEY,...(!KEY.startsWith('sb_secret_')?{Authorization:'Bearer '+KEY}:{}),'Content-Type':'application/json',...(prefer?{Prefer:prefer}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('Private state unavailable '+r.status);return r.status===204?null:r.json();}
async function tg(method,body){const r=await fetch('https://api.telegram.org/bot'+TOKEN+'/'+method,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(20000)});const p=await r.json();if(!p.ok)throw Error('Telegram result unavailable');return p.result;}
const existing=(await db('telegram_api_cache?cache_key=eq.'+K+'&select=payload'))?.[0]?.payload;
if(existing){console.log(JSON.stringify({status:existing.status,replayed:false}));process.exit(0);}
const rows=await db('telegram_api_cache?or=(cache_key.like.china_agent:advertising_ui:v1:delivery:*,cache_key.like.china_agent:sales_ui:v1:delivery:*,cache_key.like.china_agent:main_menu:v1:delivery:*)&select=cache_key,payload,updated_at&order=updated_at.desc&limit=1');
const record=rows[0],p=record?.payload,ctx=p?.context,r=p?.receipt;
if(!record?.cache_key?.startsWith('china_agent:advertising_ui:v1:delivery:')||p.status!=='sent'||ctx?.kind!=='ad'||ctx?.view!=='table'||p.actor!==5122667182||r?.message_id!==883||r.chat?.id!==CHAT||r.from?.id!==BOT){console.log('Skipped: user has navigated elsewhere; next click uses fixed handler');process.exit(0);}
const sid=/^cam1:([a-f0-9]{16}):/.exec(r.reply_markup?.inline_keyboard?.flat()?.find(b=>b.callback_data?.startsWith('cam1:'))?.callback_data||'')?.[1];
if(!sid)throw Error('Source session unavailable');
const cache=await db('rpc/china_menu_conversion_cache','POST',{p_start:'2026-10-28',p_end:'2026-11-10'});
const view=await conversionView(cache,ctx,sid,new Date());
if(!view.photo)throw Error('Daily table unavailable');
const draft={status:'sending',source_delivery:record.cache_key,original_receipt:r,context:ctx,wb_writes:0};
const claim=await db('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:K,payload:draft,expires_at:'2036-11-11T00:00:00Z'},'resolution=ignore-duplicates,return=representation');if(claim.length!==1)throw Error('Already claimed');
try{
 const form=new FormData();form.append('chat_id',String(CHAT));form.append('message_id','883');form.append('media',JSON.stringify({type:'photo',media:'attach://chart',caption:view.text}));form.append('reply_markup',JSON.stringify(view.reply_markup));form.append('chart',new Blob([view.photo],{type:'image/png'}),'conversion.png');
 const response=await fetch('https://api.telegram.org/bot'+TOKEN+'/editMessageMedia',{method:'POST',body:form,signal:AbortSignal.timeout(20000)}),body=await response.json(),receipt=body.result;
 if(!body.ok||receipt?.message_id!==883||receipt.chat?.id!==CHAT||receipt.from?.id!==BOT)throw Error('Edit outcome not verified');
 await db('telegram_api_cache?cache_key=eq.'+K,'PATCH',{payload:{...draft,status:'sent',message_id:883,receipt},updated_at:new Date().toISOString()},'return=representation');
 console.log(JSON.stringify({status:'sent',message_id:883,caption:receipt.caption,wb_writes:0}));
}catch(e){await db('telegram_api_cache?cache_key=eq.'+K,'PATCH',{payload:{...draft,status:'uncertain'}},'return=representation');throw e;}
