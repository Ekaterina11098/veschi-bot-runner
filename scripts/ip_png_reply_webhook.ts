// Dedicated advertising bot. Accepts addressed requests from the registered owner only.
const PROJECT = Deno.env.get("SUPABASE_URL") ?? "";
let KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
try { KEY = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") ?? "{}").default ?? KEY; }
catch { /* legacy service key */ }
const GITHUB = Deno.env.get("GITHUB_WORKFLOW_DISPATCH_TOKEN") ?? "";
const STATE = "advertising:agent_webhook";

async function database(path: string, method = "GET", body?: unknown, prefer?: string) {
  const response = await fetch(PROJECT + "/rest/v1/" + path, {
    method, headers: {apikey: KEY, ...(!KEY.startsWith("sb_secret_") ? {Authorization: "Bearer "+KEY} : {}), "Content-Type": "application/json", ...(prefer ? {Prefer: prefer} : {})},
    ...(body === undefined ? {} : {body: JSON.stringify(body)}), signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) throw new Error("Private database unavailable");
  return response.status === 204 ? null : await response.json();
}

async function digest(text: string) {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(bytes)).map(x => x.toString(16).padStart(2,"0")).join("");
}

function reply(chat: number,text: string) {
  return Response.json({method: "sendMessage",chat_id: chat,text});
}

function ack(id: string,text: string,alert = false) {
  return Response.json({method:"answerCallbackQuery",callback_query_id:id,text,show_alert:alert});
}


async function queueSavedDialog(update: any, message: any, text: string) {
  const rows = await database("telegram_api_cache?cache_key=eq.advertising:dialog_rollout:v1&select=payload,expires_at&limit=1");
  const rollout = rows?.[0]?.payload;
  if (!rollout?.enabled || rollout.chat_id !== message.chat.id || !rollout.source_sha ||
      !rows[0]?.expires_at || new Date(rows[0].expires_at) <= new Date()) return null;
  if (!Number.isSafeInteger(update.update_id) || update.update_id < 0) return new Response("Invalid update",{status:400});
  const reply = message.reply_to_message;
  const metadata: any = {route:"saved-dialog-v1",incoming_message_id:message.message_id,
    message_thread_id:message.message_thread_id ?? null,dispatch_attempts:0};
  if (reply) metadata.reply_context={message_id:reply.message_id,
    text:String(reply.text ?? reply.caption ?? "").slice(0,2000),sender_id:reply.from?.id ?? null,is_bot:reply.from?.is_bot === true};
  const key="dialog-v1:"+message.chat.id+":"+update.update_id;
  let queued = await database("advertising_agent_jobs?on_conflict=update_id","POST",{
    update_id:update.update_id,idempotency_key:key,chat_id:message.chat.id,sender_id:message.from.id,
    request_text:text,reply_to_message_id:message.message_id,origin:"telegram",delivery:metadata,
  },"resolution=ignore-duplicates,return=representation");
  if (!Array.isArray(queued) || !queued.length) {
    queued=await database("advertising_agent_jobs?update_id=eq."+update.update_id+
      "&chat_id=eq."+message.chat.id+"&sender_id=eq."+message.from.id+"&idempotency_key=eq."+encodeURIComponent(key)+"&select=*&limit=1");
  }
  const job=queued?.[0];
  if (!job || job.delivery?.route!=="saved-dialog-v1" || job.status && job.status!=="pending") return new Response("OK");
  const delivery=job.delivery ?? metadata;
  if (["dispatched","unknown"].includes(delivery.dispatch_status)) return new Response("OK");
  const attempts=Number(delivery.dispatch_attempts ?? 0);
  if (attempts>=2) return new Response("OK");
  const claimed=await database("advertising_agent_jobs?id=eq."+job.id+"&status=eq.pending&delivery->>dispatch_attempts=eq."+attempts,
    "PATCH",{delivery:{...delivery,dispatch_attempts:attempts+1,dispatch_status:"unknown"}},"return=representation");
  if (!Array.isArray(claimed) || claimed.length!==1) return new Response("OK");
  if (!GITHUB) {
    await database("advertising_agent_jobs?id=eq."+job.id,"PATCH",
      {delivery:{...delivery,dispatch_attempts:attempts+1,dispatch_status:"failed"},error:"Dedicated dialog dispatcher token missing"});
    return new Response("Dialog dispatcher unavailable",{status:503});
  }
  try {
    const response=await fetch("https://api.github.com/repos/Ekaterina11098/veschi-bot-runner/actions/workflows/advertising-dialog.yml/dispatches",{
      method:"POST",headers:{Authorization:"Bearer "+GITHUB,Accept:"application/vnd.github+json","Content-Type":"application/json","X-GitHub-Api-Version":"2022-11-28"},
      body:JSON.stringify({ref:"main",inputs:{job_id:String(job.id)}}),signal:AbortSignal.timeout(8000),
    });
    // PATCH only if the worker has not claimed the job; never overwrite its delivery receipt.
    await database("advertising_agent_jobs?id=eq."+job.id+"&status=eq.pending&delivery->>dispatch_attempts=eq."+(attempts+1),"PATCH",
      {delivery:{...delivery,dispatch_attempts:attempts+1,dispatch_status:response.ok?"dispatched":"failed"},
       ...(response.ok?{}:{error:"Dedicated dialog dispatch HTTP "+response.status})});
    return response.ok?new Response("OK"):new Response("Dialog dispatch unavailable",{status:503});
  } catch {
    // Outcome may be unknown. Job remains durable; no blind dispatch/send repetition.
    return new Response("OK");
  }
}



async function exactPngApproval(update: any, message: any, config: any) {
  if (!/^сделай\s+вс[её][.!]?$/iu.test(String(message.text ?? "").trim())) return null;
  const planKey="advertising:ip:png_plan:20261023:five:v1";
  const rows=await database("telegram_api_cache?cache_key=eq."+encodeURIComponent(planKey)+"&select=payload&limit=1");
  const p=rows?.[0]?.payload, r=message.reply_to_message;
  if (!p || p.delivery_status!=="sent" || message.chat.id!==-1004378639510 || config.bot_id!==8987327588 ||
      !r || r.from?.id!==8987327588 || r.from?.is_bot!==true || r.message_id!==p.message_id ||
      r.forward_origin || message.forward_origin || message.sender_chat ||
      (message.message_thread_id ?? null)!==(p.message_thread_id ?? null) ||
      !r.photo?.some((x:any)=>x.file_unique_id===p.file_unique_id))
    return reply(message.chat.id,"Ответьте «Сделай всё» именно на PNG с пятью рекомендациями ИП. Ничего не изменено.");
  if (new Date(p.expires_at)<=new Date())return reply(message.chat.id,"Срок подтверждения PNG истёк. Нужен обновлённый план; изменений нет.");
  if (!Number.isSafeInteger(update.update_id) || update.update_id<0 || !Number.isSafeInteger(message.message_id))return new Response("Invalid update",{status:400});
  if (!GITHUB)return reply(message.chat.id,"Исполнитель недоступен. Изменений нет.");
  const key=planKey+":approval";
  const a={chat_id:message.chat.id,bot_id:config.bot_id,sender_id:message.from.id,update_id:update.update_id,
    input_message_id:message.message_id,reply_message_id:r.message_id,plan_sha256:p.plan_sha256,
    command:"Сделай всё",created_at:new Date().toISOString(),dispatch_status:"unknown"};
  const inserted=await database("telegram_api_cache?on_conflict=cache_key","POST",
    {cache_key:key,payload:a,expires_at:p.expires_at},"resolution=ignore-duplicates,return=representation");
  if (!inserted?.length)return new Response("OK");
  try {
    const response=await fetch("https://api.github.com/repos/Ekaterina11098/veschi-bot-runner/actions/workflows/ip-png-apply.yml/dispatches",{
      method:"POST",headers:{Authorization:"Bearer "+GITHUB,Accept:"application/vnd.github+json","Content-Type":"application/json"},
      body:JSON.stringify({ref:"main",inputs:{approval_key:key}}),signal:AbortSignal.timeout(8000)});
    await database("telegram_api_cache?cache_key=eq."+encodeURIComponent(key),"PATCH",{payload:{...a,dispatch_status:response.ok?"dispatched":"failed"}});
    return reply(message.chat.id,response.ok?"Подтверждение сохранено. Проверю участие в группе и текущее состояние WB перед применением пяти исключений.":"Подтверждение сохранено, запуск не подтверждён. Повтор автоматически не выполняется.");
  }catch{return new Response("OK");}
}

Deno.serve(async (request: Request): Promise<Response> => {
  if (request.method !== "POST") return new Response("Method not allowed",{status:405});
  const secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
  if (!secret) return new Response("Unauthorized",{status:401});
  if (!PROJECT || !KEY) return new Response("Configuration unavailable",{status:503});
  try {
    const cache = await database("telegram_api_cache?cache_key=eq." + encodeURIComponent(STATE) + "&select=payload,expires_at&limit=1");
    const config = cache?.[0]?.payload;
    if (!config?.secret_digest || new Date(cache[0].expires_at) <= new Date() || await digest(secret) !== config.secret_digest) {
      return new Response("Unauthorized",{status:401});
    }
    // Recheck current registration, so revocation takes effect immediately.
    const rows = await database("advertising_telegram_chat?is_active=eq.true&select=chat_id,registered_by_user_id&limit=2");
    if (rows.length !== 1 || !rows[0].registered_by_user_id) return new Response("Registration unavailable",{status:503});
    const registration = rows[0];
    const update = await request.json();
    if (update.probe === true) return Response.json({authenticated:true,queue_ready:true});
    if (update.dialog_probe === true) return Response.json({authenticated:true,dialog_contract:"saved-dialog-v1",dispatcher_token_present:!!GITHUB});
    const callback = update.callback_query;
    let message = update.message;
    if (callback) {
      if (typeof callback.id !== "string") return new Response("OK");
      if (callback.from?.id !== registration.registered_by_user_id || callback.from?.is_bot ||
          callback.message?.chat?.id !== registration.chat_id || callback.message?.from?.id !== config.bot_id) {
        return ack(callback.id,"Эта кнопка доступна только владельцу в рабочей группе.",true);
      }
      let text = "";
      if (callback.data === "agent:ask") text = "/ask";
      else {
        const approved = /^ok:([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}):([a-f0-9]{12})$/.exec(callback.data ?? "");
        if (!approved) return ack(callback.id,"Кнопка не распознана.",true);
        const actions = await database("advertising_agent_actions?id=eq."+approved[1]+
          "&chat_id=eq."+registration.chat_id+"&sender_id=eq."+registration.registered_by_user_id+
          "&select=id,status,digest,expires_at&limit=1");
        const action = actions?.[0];
        if (!action || typeof action.digest !== "string" || !action.digest.startsWith(approved[2])) return ack(callback.id,"Предложение не найдено или изменилось.",true);
        if (action.status !== "proposed") return ack(callback.id,"Предложение уже обработано. Повторно не выполняю.",true);
        if (!action.expires_at || !(new Date(action.expires_at) > new Date())) return ack(callback.id,"Срок согласования истёк. Запроси новое предложение.",true);
        text = "/confirm " + approved[1] + " " + approved[2];
      }
      message = {...callback.message,from:callback.from,text};
    }
    if (!message || !Number.isSafeInteger(message.chat?.id) || !Number.isSafeInteger(message.from?.id)) return new Response("OK");
    if (message.chat.id !== registration.chat_id || message.from.is_bot) {
      return new Response("OK");
    }
    let text = typeof message.text === "string" ? message.text.trim() : "";
    if (!text) return new Response("OK");
    if (!callback) { const approved=await exactPngApproval(update,message,config); if (approved)return approved; }
    // Questions are open to every human in this one registered group. Commands keep their own authorization route.
    const incomingFirst=text.split(/\s+/,1)[0];
    const askCommand=/^\/(agent|ask|help|start)(?:@([a-z0-9_]+))?$/i.exec(incomingFirst);
    if (askCommand?.[2] && askCommand[2].toLowerCase()!==String(config.bot_username).toLowerCase()) return new Response("OK");
    if (!callback && (!text.startsWith("/") || askCommand)) {
      const originalText=text;
      if (askCommand) {
        text=askCommand[1].toLowerCase()==="agent"?text.slice(incomingFirst.length).trim():("/"+askCommand[1].toLowerCase());
        if (!text)text="/help";
      } else {
        const mentionPrefix=new RegExp("^@"+String(config.bot_username).replace(/[^a-z0-9_]/gi,"")+"(?:\\s+|$)","i");
        text=text.replace(mentionPrefix,"").trim();
      }
      if (!text)text="/help";
      if (text.length>4000)return reply(message.chat.id,"Сократите вопрос до 4000 символов.");
      const routed=await queueSavedDialog(update,message,text);
      if (routed)return routed;
      text=originalText; // Preserve legacy explicit commands when isolated dialogue is disabled.
    }
    if (message.from.id !== registration.registered_by_user_id) {
      const requested = /^\/ip_(status|done|confirm|reject)(?:\s|$)/i.exec(text);
      if (!requested) return new Response("OK");
      const accessRows = await database("telegram_api_cache?cache_key=eq.advertising:ip:employee_access:v1&select=payload,expires_at&limit=1");
      const access = accessRows?.[0]?.payload;
      const role = access?.users?.[String(message.from.id)];
      if (access?.owner_id !== registration.registered_by_user_id || access?.chat_id !== registration.chat_id ||
          !accessRows[0]?.expires_at || new Date(accessRows[0].expires_at) <= new Date() ||
          !((role === "approver") || (role === "operator" && ["status","done"].includes(requested[1].toLowerCase())) || (role === "viewer" && requested[1].toLowerCase() === "status"))) return new Response("OK");
    }
    const first = text.split(/\s+/,1)[0];
    const command = /^\/(agent|confirm|help|start|ip_status|ip_done|ip_confirm|ip_reject|ip_access)(?:@([a-z0-9_]+))?$/i.exec(first);
    const mention = new RegExp("^@" + String(config.bot_username).replace(/[^a-z0-9_]/gi,"") + "(?:\\s+|$)","i");
    const isReply = message.reply_to_message?.from?.id === config.bot_id;
    if (command?.[2] && command[2].toLowerCase() !== String(config.bot_username).toLowerCase()) return new Response("OK");
    if (!callback && !command && !mention.test(text) && !isReply) return new Response("OK");
    if (command) {
      text = text.replace(first,"/" + command[1].toLowerCase());
      if (command[1].toLowerCase() === "agent" && text.length > 6) text = text.slice(6).trim();
    } else if (mention.test(text)) text = text.replace(mention,"").trim();
    if (!text) text = "/help";
    if (text.length > 4000) return reply(message.chat.id,"Сократи поручение до4000символов или раздели его на несколько запросов.");
    if (!Number.isSafeInteger(update.update_id) || update.update_id < 0) return new Response("Invalid update",{status:400});
    const inserted = await database("advertising_agent_jobs?on_conflict=update_id","POST",{
      update_id: update.update_id,chat_id: message.chat.id,sender_id: message.from.id,request_text: text,
      reply_to_message_id: message.message_id,
    },"resolution=ignore-duplicates,return=representation");
    if (!Array.isArray(inserted) || inserted.length === 0) return callback ? ack(callback.id,"Запрос уже сохранён.") : new Response("OK");
    if (GITHUB) {
      try {
        const run = await fetch("https://api.github.com/repos/Ekaterina11098/veschi-bot-runner/actions/workflows/run.yml/dispatches",{
          method:"POST",headers:{Authorization:"Bearer " + GITHUB,Accept:"application/vnd.github+json",
            "Content-Type":"application/json","X-GitHub-Api-Version":"2022-11-28"},
          body:JSON.stringify({ref:"main",inputs:{task:"agent"}}),signal:AbortSignal.timeout(8000),
        });
        if (run.ok) return callback ? ack(callback.id,callback.data === "agent:ask" ? "Сейчас открою поле для вопроса." : "Команда сохранена отдельно. Автоматическое исполнение выключено.") : reply(message.chat.id,"Поручение принято, разбираю.");
      } catch { /* scheduled worker will claim the same durable job */ }
    }
    return callback ? ack(callback.id,"Запрос сохранён. Исполнение выключено; команда сохранена отдельно.") : reply(message.chat.id,"Поручение сохранено. Команда сохранена отдельно; автоматическое исполнение выключено.");
  } catch { return new Response("Queue unavailable",{status:503}); }
});
