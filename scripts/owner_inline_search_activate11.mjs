import {createHash} from 'node:crypto';
const URL=process.env.SUPABASE_URL,KEY=process.env.SUPABASE_SECRET_KEY,TOKEN=process.env.CHINA_TELEGRAM_BOT_TOKEN;
if(!URL||!KEY||!TOKEN)throw Error('Missing transport');
const CHAT=-1004342917488,BOT=8780468043,K='china_agent:owner_inline_search_activation:2026-11-11:v1';
async function db(path,method='GET',body,prefer){const r=await fetch(URL+'/rest/v1/'+path,{method,headers:{apikey:KEY,...(!KEY.startsWith('sb_secret_')?{Authorization:'Bearer '+KEY}:{}),'Content-Type':'application/json',...(prefer?{Prefer:prefer}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('Private state unavailable '+r.status);return r.status===204?null:r.json();}
async function tg(method,body){const r=await fetch('https://api.telegram.org/bot'+TOKEN+'/'+method,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(20000)});const p=await r.json();if(!p.ok)throw Error('Telegram result unavailable');return p.result;}
const hash=s=>createHash('sha256').update(s).digest('hex'),transitionKey='china_agent:inline_ingress_transition:v1';
const existing=(await db('telegram_api_cache?cache_key=eq.'+K+'&select=payload'))?.[0]?.payload;
if(existing?.status==='sent'){console.log(JSON.stringify({status:'sent',message_id:existing.message_id,replayed:false}));process.exit(0);}
const me=await tg('getMe',{}),hook=await tg('getWebhookInfo',{}),config=(await db('business_agent_config?agent_id=eq.china&select=agent_id,chat_id,bot_id,owner_user_id,active,secret_digest&limit=1'))?.[0];
if(me.id!==BOT||!me.supports_inline_queries||config?.bot_id!==BOT||config.chat_id!==CHAT||config.active!==true||config.owner_user_id!==5122667182)throw Error('Inline capability or identity not verified');
const expected=new globalThis.URL('/functions/v1/china-agent-webhook',URL).href;if(hook.url!==expected||hook.has_custom_certificate)throw Error('Unexpected ingress configuration');
const secret=hash('china-native-inline-webhook-v1:'+TOKEN),newDigest=hash(secret),oldDigest=config.secret_digest;
const put=async(k,p)=>db('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:k,payload:p,expires_at:'2036-11-11T00:00:00Z'},'resolution=merge-duplicates,return=representation');
const probe=async()=>{const r=await fetch(expected,{method:'POST',headers:{'Content-Type':'application/json','X-Telegram-Bot-Api-Secret-Token':secret},body:'{"probe":true}',signal:AbortSignal.timeout(15000)});const p=await r.json();if(!r.ok||p.authenticated!==true||p.agent_id!=='china')throw Error('Ingress probe not verified');};
if(oldDigest!==newDigest)await put(transitionKey,{status:'prepared',bot_id:BOT,chat_id:CHAT,old_digest:oldDigest,new_digest:newDigest,valid_until:new Date(Date.now()+600000).toISOString(),owner_source:'Owner11Nov native inline search; bounded seamless ingress transition'});
await probe();
const allowed=[...new Set([...(hook.allowed_updates?.length?hook.allowed_updates:['message','callback_query']),'inline_query'])];
await tg('setWebhook',{url:hook.url,secret_token:secret,allowed_updates:allowed,drop_pending_updates:false,max_connections:hook.max_connections||40});
const after=await tg('getWebhookInfo',{});
if(after.url!==hook.url||!allowed.every(t=>after.allowed_updates?.includes(t)))throw Error('Inline subscription not verified');
if(oldDigest!==newDigest){const saved=await db('business_agent_config?agent_id=eq.china&bot_id=eq.'+BOT+'&chat_id=eq.'+CHAT+'&secret_digest=eq.'+oldDigest,'PATCH',{secret_digest:newDigest,updated_at:new Date().toISOString()},'return=representation');if(saved.length!==1)throw Error('Canonical ingress changed concurrently');}
await probe();
await put(transitionKey,{status:'completed',bot_id:BOT,chat_id:CHAT,completed_at:new Date().toISOString(),valid_until:new Date().toISOString(),pending_updates_dropped:false});
const policyKey='china_agent:main_menu:v1:policy',policy=(await db('telegram_api_cache?cache_key=eq.'+policyKey+'&select=payload'))?.[0]?.payload;
await put(policyKey,{...policy,inline_search_enabled:true,inline_queries_personal:true,owner_inline_source:'Codex11Nov: давай так, как ты предлагаешь; BotFather inline enabled by owner'});
await put(K,{status:'activated',bot_id:BOT,allowed_updates:after.allowed_updates,inline_enabled:true,ingress_verified:true,pending_updates_dropped:false,telegram_sends:0,wb_writes:0});
const claimKey=K+':menu',claim=await db('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:claimKey,payload:{status:'sending'},expires_at:'2036-11-11T00:00:00Z'},'resolution=ignore-duplicates,return=representation');
if(claim.length!==1){console.log('Inline activated; existing menu outcome retained without blind resend');process.exit(0);}
try{
 const receipt=await tg('sendMessage',{chat_id:CHAT,text:'Поиск товара\nНажмите раздел и введите артикул или название, например «454 сумка».',reply_markup:{inline_keyboard:[[{text:'Найти для ДРР',switch_inline_query_current_chat:'ДРР '}],[{text:'Найти для конверсии',switch_inline_query_current_chat:'Конверсия '}],[{text:'‹ Реклама',callback_data:'cmn1:ads'}]]}});
 if(receipt?.chat?.id!==CHAT||receipt.from?.id!==BOT||!Number.isSafeInteger(receipt.message_id))throw Error('Search menu receipt mismatch');
 for(const metric of ['drr','cr']){
  const k='china_agent:advertising_ui:v1:inline_context:'+config.owner_user_id+':'+metric,old=(await db('telegram_api_cache?cache_key=eq.'+k+'&select=payload'))?.[0]?.payload;
  const day=new Date(Date.now()+10800000).toISOString().slice(0,10),shift=n=>new Date(Date.parse(day+'T00:00:00Z')+n*86400000).toISOString().slice(0,10);
  await put(k,{actor:config.owner_user_id,context:{...(old?.context||{period:'range',start:shift(-7),end:shift(-1)}),kind:'ad',metric,inlineEnabled:true},source_message:{message_id:receipt.message_id,chat:{id:CHAT,type:'supergroup'},from:{id:BOT,is_bot:true}},expires_at:new Date(Date.now()+900000).toISOString()});
 }
 await put(claimKey,{status:'sent',message_id:receipt.message_id,receipt});
 await put(K,{status:'sent',message_id:receipt.message_id,receipt,bot_id:BOT,allowed_updates:after.allowed_updates,inline_enabled:true,ingress_verified:true,pending_updates_dropped:false,wb_writes:0});
 console.log(JSON.stringify({status:'sent',message_id:receipt.message_id,inline_enabled:true,allowed_updates:after.allowed_updates,ingress_verified:true,wb_writes:0}));
}catch(e){await put(claimKey,{status:'uncertain'});throw e;}
