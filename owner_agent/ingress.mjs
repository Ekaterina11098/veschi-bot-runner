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
  if(!secret || request.headers.get('X-Telegram-Bot-Api-Secret-Token')!==secret) return new Response('Unauthorized',{status:401});
  try {
    const body=await request.text();
    if(body.length>32000) return new Response('Payload too large',{status:413});
    const update=JSON.parse(body);
    const config=(await db.request('owner_agent_config?id=eq.1&select=*'))?.[0];
    const members=await db.request('owner_agent_members?active=eq.true&select=user_id,active');
    if(!validMessage(update,config,members)) return ok();
    const m=update.message;
    await db.request('owner_agent_jobs?on_conflict=update_id',{method:'POST',body:{update_id:update.update_id,chat_id:m.chat.id,sender_id:m.from.id,message_id:m.message_id,thread_id:m.message_thread_id??null,request_text:m.text.trim()},prefer:'resolution=ignore-duplicates,return=representation'});
    const job=(await db.request('owner_agent_jobs?update_id=eq.'+update.update_id+'&select=id,status,chat_id,sender_id'))?.[0];
    if(job?.status==='pending' && Number(job.chat_id)===m.chat.id && Number(job.sender_id)===m.from.id) await dispatchJob(job.id);
    return ok();
  } catch {return new Response('Queue unavailable',{status:503});}
}
