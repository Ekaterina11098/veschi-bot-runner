const ok=()=>new Response('OK');
export function validMessage(update,config,members) {
  const m=update.message;
  return config?.active===true && config.bot_username==='veschi_owner_ai_bot' &&
    Number.isSafeInteger(update.update_id) && update.update_id>=0 &&
    Number.isSafeInteger(m?.message_id) && m.message_id>0 &&
    Number.isSafeInteger(m.chat?.id) && m.chat.id===Number(config.chat_id) && ['group','supergroup'].includes(m.chat.type) &&
    Number.isSafeInteger(m.from?.id) && !m.from.is_bot && !m.sender_chat &&
    members.some(x=>x.active===true && Number(x.user_id)===m.from.id) &&
    typeof m.text==='string' && m.text.trim().length>0 && m.text.trim().length<=4000 && !/^\//.test(m.text.trim());
}
export async function handle(request,{db,secret,dispatchJob}) {
  if(request.method!=='POST') return new Response('Method not allowed',{status:405});
  const provided=request.headers.get('X-Telegram-Bot-Api-Secret-Token');
  if(!provided || provided.length>256) return new Response('Unauthorized',{status:401});
  try {
    // Production uses a digest from its own private configuration; no bot token in Edge secrets.
    let config;
    if(secret) {
      if(provided!==secret)return new Response('Unauthorized',{status:401});
    } else {
      config=(await db.request('owner_agent_config?id=eq.1&select=*'))?.[0];
      const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(provided));
      const digest=Array.from(new Uint8Array(bytes)).map(x=>x.toString(16).padStart(2,'0')).join('');
      if(!config?.active || !config.secret_digest || digest!==config.secret_digest)return new Response('Unauthorized',{status:401});
    }
    const body=await request.text();
    if(body.length>32000) return new Response('Payload too large',{status:413});
    const update=JSON.parse(body);
    config??=(await db.request('owner_agent_config?id=eq.1&select=*'))?.[0];
    if(update.probe===true)return Response.json({authenticated:true,agent:'owner',active:config?.active===true});
    const members=await db.request('owner_agent_members?active=eq.true&select=user_id,active');
    const m=update.message??update.edited_message;
    // Edits are retained as new immutable revisions, not a second question/send.
    const raw=m?.text??m?.caption;
    if(typeof raw!=='string'||!raw.trim()||raw.length>4096)return ok();
    const candidate={...update,message:m?{...m,text:('Архив: '+raw).slice(0,4000)}:undefined};
    if(!validMessage(candidate,config,members)) return ok();
    const text=(m.text??m.caption).trim();
    await db.request('owner_agent_messages?on_conflict=chat_id,message_id,revision',{method:'POST',body:{chat_id:m.chat.id,message_id:m.message_id,revision:update.edited_message?(m.edit_date??update.update_id):0,sender_id:m.from.id,role:'user',thread_id:m.message_thread_id??null,reply_to_message_id:m.reply_to_message?.message_id??null,content:text,message_at:new Date((m.date??Math.floor(Date.now()/1000))*1000).toISOString(),correction:Boolean(update.edited_message)||/исправ|поправ|уточн|запомни|договор|на самом деле|ошиб|неверн|впредь|всегда|теперь счита|имей в виду/iu.test(text)},prefer:'resolution=ignore-duplicates'});
    if(update.edited_message||/^\//.test(text)||text.length>4000)return ok();
    await db.request('owner_agent_jobs?on_conflict=update_id',{method:'POST',body:{update_id:update.update_id,chat_id:m.chat.id,sender_id:m.from.id,message_id:m.message_id,thread_id:m.message_thread_id??null,request_text:text},prefer:'resolution=ignore-duplicates,return=representation'});
    const job=(await db.request('owner_agent_jobs?update_id=eq.'+update.update_id+'&select=id,status,chat_id,sender_id'))?.[0];
    if(job?.status==='pending' && Number(job.chat_id)===m.chat.id && Number(job.sender_id)===m.from.id) await dispatchJob(job.id);
    return ok();
  } catch {return new Response('Queue unavailable',{status:503});}
}
