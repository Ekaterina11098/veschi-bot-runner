import {createHash} from 'node:crypto';
const URL=process.env.SUPABASE_URL,KEY=process.env.SUPABASE_SECRET_KEY,TOKEN=process.env.CHINA_TELEGRAM_BOT_TOKEN;
if(!URL||!KEY||!TOKEN)throw Error('Missing transport');
const CHAT=-1004342917488,BOT=8780468043,K='china_agent:owner_three_report_fixes:2026-11-11:v1';
async function db(path,method='GET',body,prefer){const r=await fetch(URL+'/rest/v1/'+path,{method,headers:{apikey:KEY,...(!KEY.startsWith('sb_secret_')?{Authorization:'Bearer '+KEY}:{}),'Content-Type':'application/json',...(prefer?{Prefer:prefer}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('Private state unavailable '+r.status);return r.status===204?null:r.json();}
async function tg(method,body){const r=await fetch('https://api.telegram.org/bot'+TOKEN+'/'+method,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(20000)});const p=await r.json();if(!p.ok)throw Error('Telegram result unavailable');return p.result;}

const old=(await db('telegram_api_cache?cache_key=eq.'+K+'&select=payload'))?.[0]?.payload;
if(old?.status==='verified'){console.log(JSON.stringify({status:'verified',message_id:889}));process.exit(0);}
if((await tg('getMe',{})).id!==BOT)throw Error('Identity mismatch');
const contextKey='china_agent:advertising_ui:v1:inline_context:5122667182:drr';
const context=(await db('telegram_api_cache?cache_key=eq.'+contextKey+'&select=payload'))?.[0]?.payload;
if(!context||context.actor!==5122667182||context.context?.metric!=='drr')throw Error('DRR context missing');
const receipt=await tg('editMessageText',{chat_id:CHAT,message_id:889,text:'ДРР · Поиск товара\nНажмите «Найти товар» и введите артикул или название, например «454 сумка».',reply_markup:{inline_keyboard:[[{text:'Найти товар',switch_inline_query_current_chat:'ДРР '}],[{text:'‹ Реклама',callback_data:'cmn1:ads'}]]}});
if(receipt?.message_id!==889||receipt.chat?.id!==CHAT||receipt.from?.id!==BOT)throw Error('Edit not verified');
await db('telegram_api_cache?cache_key=eq.'+contextKey,'PATCH',{payload:{...context,source_message:{message_id:889,chat:{id:CHAT,type:'supergroup'},from:{id:BOT,is_bot:true}},expires_at:new Date(Date.now()+900000).toISOString()},updated_at:new Date().toISOString()},'return=representation');
const price=await tg('editMessageText',{chat_id:CHAT,message_id:888,text:'Цены · промежуточная проверка · 11.11.2026, 15:00 МСК\n\nПовышение: новых готовых предложений нет.\nСнижение: рекомендации не готовы — недостаточно подтверждённых данных.\n\nИз 59 предварительных вариантов: у 32 не подтверждена экономически обоснованная целевая цена; у 27 недостаточно данных о собственном выкупе. Это не означает, что возможностей нет.\n\nЦены этим отчётом не изменялись.'});
if(price?.message_id!==888||price.chat?.id!==CHAT)throw Error('Price correction unverified');
await db('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:K,payload:{status:'verified',search_receipt:receipt,price_receipt:price,wb_writes:0,verified_at:new Date().toISOString()},expires_at:'2036-11-11T00:00:00Z'},'resolution=merge-duplicates,return=representation');
console.log(JSON.stringify({status:'verified',search_message_id:889,price_message_id:888,wb_writes:0}));
