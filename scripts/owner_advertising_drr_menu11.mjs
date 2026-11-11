import {advertisingMenu} from './china_advertising_ui.mjs';
const URL=process.env.SUPABASE_URL,KEY=process.env.SUPABASE_SECRET_KEY,TOKEN=process.env.CHINA_TELEGRAM_BOT_TOKEN;
if(!URL||!KEY||!TOKEN)throw Error('Missing transport');
const CHAT=-1004342917488,BOT=8780468043,K='china_agent:owner_advertising_drr_search:2026-11-11:v1';
async function db(path,method='GET',body,prefer){const r=await fetch(URL+'/rest/v1/'+path,{method,headers:{apikey:KEY,...(!KEY.startsWith('sb_secret_')?{Authorization:'Bearer '+KEY}:{}),'Content-Type':'application/json',...(prefer?{Prefer:prefer}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('Private state unavailable '+r.status);return r.status===204?null:r.json();}
async function tg(method,body){const r=await fetch('https://api.telegram.org/bot'+TOKEN+'/'+method,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(20000)});const p=await r.json();if(!p.ok)throw Error('Telegram result unavailable');return p.result;}
const existing=(await db('telegram_api_cache?cache_key=eq.'+K+'&select=payload'))?.[0]?.payload;
if(existing){console.log(JSON.stringify({status:existing.status,message_id:existing.message_id||null,replayed:false}));process.exit(0);}
const me=await tg('getMe',{});if(me.id!==BOT)throw Error('Bot identity mismatch');
const projection=await db('rpc/china_menu_conversion_cache','POST',{p_start:'2026-10-28',p_end:'2026-11-10'});
if(projection.cabinet!=='token_3'||!projection.daily?.length||!projection.general_days?.length)throw Error('Conversion cache not verified');
const draft={status:'sending',owner_source:'Codex11Nov: Добавляй кнопку ДРР и поиск товара по артикулу. PNG горизонтальный с показателями одобрен; Нет заказов и расход.',wb_writes:0,created_at:new Date().toISOString()};
const claim=await db('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:K,payload:draft,expires_at:'2036-11-11T00:00:00Z'},'resolution=ignore-duplicates,return=representation');
if(claim.length!==1)throw Error('Already claimed');
try{
 const v=advertisingMenu(),receipt=await tg('sendMessage',{chat_id:CHAT,text:v.text,reply_markup:v.reply_markup});
 if(receipt?.chat?.id!==CHAT||receipt.from?.id!==BOT||!Number.isSafeInteger(receipt.message_id))throw Error('Recipient mismatch');
 const payload={...draft,status:'sent',message_id:receipt.message_id,receipt,buttons:v.reply_markup.inline_keyboard.map(r=>r[0].text)};
 await db('telegram_api_cache?cache_key=eq.'+K,'PATCH',{payload,updated_at:new Date().toISOString()},'return=representation');
 const proof=(await db('telegram_api_cache?cache_key=eq.'+K+'&select=payload'))?.[0]?.payload;
 if(proof?.status!=='sent'||proof.message_id!==receipt.message_id)throw Error('Delivery readback mismatch');
 console.log(JSON.stringify({status:'sent',message_id:receipt.message_id,buttons:payload.buttons,conversion_daily_rows:projection.daily.length,wb_writes:0}));
}catch(e){await db('telegram_api_cache?cache_key=eq.'+K,'PATCH',{payload:{...draft,status:'uncertain',error:'Transport result not verified'}},'return=representation');throw e;}


