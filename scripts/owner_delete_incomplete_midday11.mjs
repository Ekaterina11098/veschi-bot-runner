import {createHash} from 'node:crypto';
const URL=process.env.SUPABASE_URL,KEY=process.env.SUPABASE_SECRET_KEY,TOKEN=process.env.CHINA_TELEGRAM_BOT_TOKEN;
if(!URL||!KEY||!TOKEN)throw Error('Missing transport');
const CHAT=-1004342917488,BOT=8780468043,K='china_agent:owner_midday_delete_incomplete:2026-11-11:v1';
async function db(path,method='GET',body,prefer){const r=await fetch(URL+'/rest/v1/'+path,{method,headers:{apikey:KEY,...(!KEY.startsWith('sb_secret_')?{Authorization:'Bearer '+KEY}:{}),'Content-Type':'application/json',...(prefer?{Prefer:prefer}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('Private state unavailable '+r.status);return r.status===204?null:r.json();}
async function tg(method,body){const r=await fetch('https://api.telegram.org/bot'+TOKEN+'/'+method,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(20000)});const p=await r.json();if(!p.ok)throw Error('Telegram result unavailable');return p.result;}


const old=(await db('telegram_api_cache?cache_key=eq.'+K+'&select=payload'))?.[0]?.payload;
if(old?.status==='verified'){console.log('already deleted');process.exit(0);}
const k='china_agent:advertising_midday_delivery:2026-11-11:v1:diagnostic',state=(await db('telegram_api_cache?cache_key=eq.'+k+'&select=payload'))?.[0]?.payload;
const p=state?.parts?.find(p=>p.message_id===895&&p.status==='sent');
if(state?.status!=='delivered'||!p||p.receipt?.chat?.id!==CHAT)throw Error('Exact source receipt missing');
if(await tg('deleteMessage',{chat_id:CHAT,message_id:895})!==true)throw Error('Deletion unverified');
await db('telegram_api_cache?cache_key=eq.'+k,'PATCH',{payload:{...state,owner_deleted:true,deleted_message_ids:[895],deleted_at:new Date().toISOString(),owner_source:'Owner11Nov: удаляй тот и жду нормальный'},updated_at:new Date().toISOString()},'return=representation');
await db('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:K,payload:{status:'verified',deleted_message_id:895,telegram_result:true,wb_writes:0},expires_at:'2036-11-11T00:00:00Z'},'resolution=ignore-duplicates,return=representation');
console.log(JSON.stringify({status:'verified',deleted_message_id:895,wb_writes:0}));
