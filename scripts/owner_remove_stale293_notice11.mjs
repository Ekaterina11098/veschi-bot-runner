import {createHash} from 'node:crypto';
const URL=process.env.SUPABASE_URL,KEY=process.env.SUPABASE_SECRET_KEY,TOKEN=process.env.CHINA_TELEGRAM_BOT_TOKEN;
if(!URL||!KEY||!TOKEN)throw Error('Missing transport');
const CHAT=-1004342917488,BOT=8780468043,K='china_agent:owner_remove_stale293_notice:2026-11-11:v1';
async function db(path,method='GET',body,prefer){const r=await fetch(URL+'/rest/v1/'+path,{method,headers:{apikey:KEY,...(!KEY.startsWith('sb_secret_')?{Authorization:'Bearer '+KEY}:{}),'Content-Type':'application/json',...(prefer?{Prefer:prefer}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('Private state unavailable '+r.status);return r.status===204?null:r.json();}
async function tg(method,body){const r=await fetch('https://api.telegram.org/bot'+TOKEN+'/'+method,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(20000)});const p=await r.json();if(!p.ok)throw Error('Telegram result unavailable');return p.result;}


const old=(await db('telegram_api_cache?cache_key=eq.'+K+'&select=payload'))?.[0]?.payload;
if(old?.status==='verified'){console.log('already removed');process.exit(0);}
const r=(await db('telegram_api_cache?cache_key=eq.china_agent:conversion_watch_delivery:v1:question:293:0&select=payload'))?.[0]?.payload;
if(r?.status!=='sent'||r.message_id!==898)throw Error('Exact stale notice not verified');
if(await tg('deleteMessage',{chat_id:CHAT,message_id:898})!==true)throw Error('Deletion unverified');
await db('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:K,payload:{status:'verified',message_id:898,deleted:true,job_id:293,owner_source:'Owner11Nov screenshot: stale report answer after current confirmation; remove misleading duplicate',telegram_result:true,wb_writes:0},expires_at:'2036-11-11T00:00:00Z'},'resolution=ignore-duplicates,return=representation');
console.log(JSON.stringify({status:'verified',deleted_message_id:898,wb_writes:0}));
