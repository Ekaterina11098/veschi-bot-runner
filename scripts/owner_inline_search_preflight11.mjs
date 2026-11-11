
const URL=process.env.SUPABASE_URL,KEY=process.env.SUPABASE_SECRET_KEY,TOKEN=process.env.CHINA_TELEGRAM_BOT_TOKEN;
if(!URL||!KEY||!TOKEN)throw Error('Missing transport');
const CHAT=-1004342917488,BOT=8780468043,K='china_agent:inline_search_preflight:2026-11-11:v1';
async function db(path,method='GET',body,prefer){const r=await fetch(URL+'/rest/v1/'+path,{method,headers:{apikey:KEY,...(!KEY.startsWith('sb_secret_')?{Authorization:'Bearer '+KEY}:{}),'Content-Type':'application/json',...(prefer?{Prefer:prefer}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('Private state unavailable '+r.status);return r.status===204?null:r.json();}
async function tg(method,body){const r=await fetch('https://api.telegram.org/bot'+TOKEN+'/'+method,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(20000)});const p=await r.json();if(!p.ok)throw Error('Telegram result unavailable');return p.result;}
const me=await tg('getMe',{}),hook=await tg('getWebhookInfo',{});
if(me.id!==BOT)throw Error('Wrong bot');
const payload={status:'checked',bot_id:me.id,username:me.username,supports_inline_queries:me.supports_inline_queries===true,allowed_updates:hook.allowed_updates||[],pending_update_count:hook.pending_update_count,checked_at:new Date().toISOString(),wb_writes:0,telegram_sends:0};
await db('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:K,payload,expires_at:'2036-11-11T00:00:00Z'},'resolution=merge-duplicates,return=representation');
console.log(JSON.stringify(payload));
