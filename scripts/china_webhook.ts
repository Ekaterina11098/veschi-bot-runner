// Separate bots and queues; shared knowledge does not grant shared permissions.
const AGENT = "china"; // Deployment substitutes "china" for its separate function.
const PROJECT = Deno.env.get("SUPABASE_URL") ?? "";
let KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
try { KEY = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") ?? "{}").default ?? KEY; } catch {}
const LEGACY_SECRET = Deno.env.get("TELEGRAM_WEBHOOK_SECRET") ?? "";
const LEGACY_CHAT = Deno.env.get("TELEGRAM_ALLOWED_CHAT_ID") ?? "";
const GITHUB = Deno.env.get("GITHUB_WORKFLOW_DISPATCH_TOKEN") ?? "";
const LEGACY: Record<string,string> = {"остатки":"остатки","новинки":"новинки","аудит":"аудит",
  "инвентаризация":"инвентаризация","inventory":"инвентаризация","отзывы":"отзывы"};

async function database(path: string, method = "GET", body?: unknown, prefer?: string) {
  const r = await fetch(PROJECT+"/rest/v1/"+path, {method,
    headers: {apikey:KEY,...(!KEY.startsWith("sb_secret_")?{Authorization:"Bearer "+KEY}:{}),
      "Content-Type":"application/json",...(prefer?{Prefer:prefer}:{})},
    ...(body === undefined ? {} : {body:JSON.stringify(body)}),signal:AbortSignal.timeout(8000)});
  if (!r.ok) throw new Error("State unavailable");
  return r.status === 204 ? null : await r.json();
}

async function digest(text: string) {
  const bytes = await crypto.subtle.digest("SHA-256",new TextEncoder().encode(text));
  return Array.from(new Uint8Array(bytes)).map(x=>x.toString(16).padStart(2,"0")).join("");
}

function reply(chat: number,text: string,markup?: unknown) {
  return Response.json({method:"sendMessage",chat_id:chat,text,...(markup?{reply_markup:markup}:{})});
}

function same(a:any,b:any):boolean { const sorted=(x:any):any=>Array.isArray(x)?x.map(sorted):x&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,sorted(x[k])])):x;return JSON.stringify(sorted(a))===JSON.stringify(sorted(b)); }

async function telegram(method: string, body: unknown) {
  const token=Deno.env.get('CHINA_TELEGRAM_BOT_TOKEN');
  if(!token)throw new Error('Bot unavailable');
  const r=await fetch('https://api.telegram.org/bot'+token+'/'+method,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(8000)});
  const value=await r.json();if(!value.ok)throw new Error('Telegram verification failed');return value.result;
}

async function migration(config: any, old: number, target: number, evidence: unknown) {
  if(!Number.isSafeInteger(old)||!Number.isSafeInteger(target)||old>=0||target>=0||old===target||![old,target].includes(config.chat_id))throw new Error('Migration scope');
  const me=await telegram('getMe',{});
  const member=await telegram('getChatMember',{chat_id:target,user_id:config.bot_id});
  const chat=await telegram('getChat',{chat_id:target});
  if(me.id!==config.bot_id||member.user?.id!==config.bot_id||member.status!=='administrator'||chat.type!=='supergroup')throw new Error('Migration bot scope');
  const conflicts=await database('business_agent_config?agent_id=neq.china&chat_id=eq.'+target+'&select=agent_id');
  const ads=await database('advertising_telegram_chat?is_active=eq.true&chat_id=eq.'+target+'&select=chat_id');
  if(conflicts?.length||ads?.length)throw new Error('Destination occupied');
  const key='china_agent:chat_migration:v1:'+target;
  const existing=await database('telegram_api_cache?cache_key=eq.'+key+'&select=payload');
  const oldLine=existing?.[0]?.payload;
  if(config.chat_id===target && (!oldLine||oldLine.from_chat_id!==old||oldLine.bot_id!==config.bot_id||oldLine.owner_user_id!==config.owner_user_id))throw new Error('Missing migration lineage');
  if(oldLine && (oldLine.from_chat_id!==old||oldLine.to_chat_id!==target||oldLine.bot_id!==config.bot_id||oldLine.owner_user_id!==config.owner_user_id))throw new Error('Conflicting lineage');
  const prior=await database('telegram_api_cache?cache_key=eq.'+'china_agent:chat_migration:v1:'+old+'&select=payload');
  const previous=prior?.[0]?.payload;
  const ancestors=previous?.verified===true&&previous.bot_id===config.bot_id&&previous.owner_user_id===config.owner_user_id?previous.previous_chat_ids:[];
  const line={agent_id:'china',from_chat_id:old,to_chat_id:target,previous_chat_ids:[...new Set([old,...ancestors])],bot_id:config.bot_id,owner_user_id:config.owner_user_id,verified:true,evidence,verified_at:oldLine?.verified_at??new Date().toISOString()};
  if(!oldLine)await database('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:key,payload:line,expires_at:'2036-10-17T00:00:00Z'},'resolution=ignore-duplicates,return=representation');
  const retained=await database('telegram_api_cache?cache_key=eq.'+key+'&select=payload');
  if(!retained?.[0]?.payload?.verified||retained[0].payload.bot_id!==config.bot_id||retained[0].payload.owner_user_id!==config.owner_user_id||!same(retained[0].payload.previous_chat_ids,line.previous_chat_ids))throw new Error('Lineage readback');
  // Keep cache keys, IDs, revisions, next_at and all old receipts unchanged.
  for(const before of line.previous_chat_ids){
    const watches=await database('telegram_api_cache?cache_key=like.china_agent:conversion_watch:v1:'+before+':'+config.owner_user_id+':*&select=cache_key,payload&limit=100');
    if(watches.length>=100)throw new Error('Watch list incomplete');
    for(const row of watches){
      const p=row.payload;
      if(p.agent_id!=='china'||p.owner_user_id!==config.owner_user_id||![before,target].includes(p.chat_id))throw new Error('Watch scope');
      if(p.chat_id===target)continue;
      await database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(row.cache_key)+'&payload->>chat_id=eq.'+before,'PATCH',{payload:{...p,chat_id:target},updated_at:new Date().toISOString()},'return=representation');
      const after=await database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(row.cache_key)+'&select=payload');
      if(!same({...after[0].payload,chat_id:before},p))throw new Error('Watch readback');
    }
  }
  if(config.chat_id===old)await database('business_agent_config?agent_id=eq.china&chat_id=eq.'+old+'&bot_id=eq.'+config.bot_id+'&owner_user_id=eq.'+config.owner_user_id,'PATCH',{chat_id:target,updated_at:new Date().toISOString()},'return=representation');
  const result=(await database('business_agent_config?agent_id=eq.china&limit=1'))[0];
  if(result.chat_id!==target||result.bot_id!==config.bot_id||result.owner_user_id!==config.owner_user_id)throw new Error('Registration readback');
  return result;
}

async function launch(job: number) {
  if(!GITHUB)throw new Error('Dispatch unavailable');
  const r=await fetch('https://api.github.com/repos/Ekaterina11098/veschi-bot-runner/actions/workflows/china-conversion-watches.yml/dispatches',{method:'POST',headers:{Authorization:'Bearer '+GITHUB,Accept:'application/vnd.github+json','Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28'},body:JSON.stringify({ref:'main',inputs:{action:'dialog',job_id:String(job)}}),signal:AbortSignal.timeout(8000)});
  if(!r.ok)throw new Error('Dispatch pending');
}

Deno.serve(async(request:Request):Promise<Response>=>{
  if(request.method!=='POST')return new Response('Method not allowed',{status:405});
  const secret=request.headers.get('X-Telegram-Bot-Api-Secret-Token');
  if(!secret||secret.length>200)return new Response('Unauthorized',{status:401});
  try{
    let config=(await database('business_agent_config?agent_id=eq.china&limit=1'))?.[0];
    if(!config?.active||!config.secret_digest||await digest(secret)!==config.secret_digest)return new Response('Unauthorized',{status:401});
    const update=await request.json();
    if(update.probe===true)return Response.json({authenticated:true,queue_ready:true,agent_id:'china'});
    let message=update.message;
    // An authenticated maintenance call carries the previously verified Telegram 400 proof.
    // Reconfirm that proof live before applying it, never trust supplied target IDs alone.
    if(update.reconcile_migration){
      const old=config.chat_id,token=Deno.env.get('CHINA_TELEGRAM_BOT_TOKEN');
      const r=await fetch('https://api.telegram.org/bot'+token+'/getChatAdministrators',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chat_id:old}),signal:AbortSignal.timeout(8000)});
      const proof=await r.json();const target=proof.parameters?.migrate_to_chat_id;
      if(proof.ok||proof.error_code!==400||!Number.isSafeInteger(target))throw new Error('Migration proof unavailable');
      config=await migration(config,old,target,{method:'getChatAdministrators',error_code:400,migrate_to_chat_id:target});
      return Response.json({migrated:true,chat_id:config.chat_id,telegram_sends:0});
    }
    if(message?.migrate_to_chat_id||message?.migrate_from_chat_id){
      const old=message.migrate_from_chat_id??message.chat?.id;
      const target=message.migrate_to_chat_id??message.chat?.id;
      if(!Number.isSafeInteger(update.update_id))return new Response('Invalid update',{status:400});
      await migration(config,old,target,{update_id:update.update_id,message_id:message.message_id});return new Response('OK');
    }
    const callback=update.callback_query;
    if(callback){
      if(callback.data!=='agent:ask'||callback.message?.chat?.id!==config.chat_id||callback.message?.from?.id!==config.bot_id||callback.from?.is_bot)return new Response('OK');
      return Response.json({method:'answerCallbackQuery',callback_query_id:callback.id,text:'Напишите вопрос обычным сообщением в группе.'});
    }
    if(!Number.isSafeInteger(message?.chat?.id)||!Number.isSafeInteger(message?.from?.id)||message.from.id<=0||message.from.is_bot||message.sender_chat||message.chat.id!==config.chat_id||!['group','supergroup'].includes(message.chat.type))return new Response('OK');
    let text=typeof message.text==='string'?message.text.trim():'';
    if(!text)return new Response('OK');
    const first=text.split(/\s+/,1)[0];const parsed=/^\/(\S+?)(?:@([a-z0-9_]+))?$/i.exec(first);const cmd=parsed?.[1].toLowerCase();
    if(parsed?.[2]&&parsed[2].toLowerCase()!==config.bot_username?.toLowerCase())return new Response('OK');
    if(cmd==='confirm')return reply(config.chat_id,'Изменения WB здесь не выполняются.');
    if(['help','start','ask'].includes(cmd??'')||(cmd==='agent'&&text===first))return reply(config.chat_id,'Задавайте вопрос обычным сообщением. Вопросы доступны всем участникам, управление заданиями — владельцу.');
    if(cmd==='agent')text=text.slice(first.length).trim();
    if(text.length>4000)return reply(config.chat_id,'Разделите вопрос на сообщения до 4000 символов.');
    if(!Number.isSafeInteger(update.update_id)||update.update_id<0||!Number.isSafeInteger(message.message_id))return new Response('Invalid update',{status:400});
    const quoted=message.reply_to_message;
    const marker:any={name:'china_saved_question',message_id:message.message_id,bot_id:config.bot_id,thread_id:message.message_thread_id??null};
    if(quoted?.from?.id===config.bot_id&&Number.isSafeInteger(quoted.message_id)){
      marker.reply_message_id=quoted.message_id;marker.reply_text=typeof quoted.text==='string'?quoted.text.slice(0,4000):'';
      const receipt=await database('telegram_api_cache?cache_key=like.china_agent:conversion_watch_delivery:v1:question:*&payload->>message_id=eq.'+quoted.message_id+'&payload->>chat_id=eq.'+config.chat_id+'&select=cache_key,payload&limit=2');
      if(receipt.length===1&&receipt[0].payload.status==='sent'){
        const m=/:question:(\d+):\d+$/.exec(receipt[0].cache_key);
        if(m){const parent=await database('business_agent_jobs?id=eq.'+m[1]+'&agent_id=eq.china&chat_id=eq.'+config.chat_id+'&sender_id=eq.'+message.from.id+'&status=eq.done&select=id&limit=1');if(parent.length===1)marker.parent_job_id=parent[0].id;}
      }
    }
    const inserted=await database('business_agent_jobs?on_conflict=agent_id,update_id','POST',{agent_id:'china',update_id:update.update_id,chat_id:config.chat_id,sender_id:message.from.id,request_text:text,tool_trace:[marker]},'resolution=ignore-duplicates,return=representation');
    if(inserted.length){await launch(inserted[0].id);return new Response('OK');}
    // Telegram retry after a dispatch timeout may safely redispatch the same durable job.
    const existing=await database('business_agent_jobs?agent_id=eq.china&update_id=eq.'+update.update_id+'&chat_id=eq.'+config.chat_id+'&sender_id=eq.'+message.from.id+'&select=id,status&limit=1');
    if(existing?.[0]?.status==='pending')await launch(existing[0].id);
    return new Response('OK');
  }catch{return new Response('Queue unavailable',{status:503});}
});
