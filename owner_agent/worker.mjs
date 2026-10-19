import {randomUUID,createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {Database} from './data.mjs';
import {runDialog,modelRequest} from './dialog.mjs';
import {memoryReader,loadMemory} from './memory.mjs';

export function splitText(text,limit=3500) {
  const points=Array.from(text),parts=[];
  while(points.length) parts.push(points.splice(0,limit).join(''));
  return parts;
}
export function permitted(config,members,job) {
  return config?.active===true && config.bot_username==='veschi_owner_ai_bot' &&
    Number(config.chat_id)===Number(job.chat_id) && members.some(x=>x.active===true && Number(x.user_id)===Number(job.sender_id));
}
export async function telegram(token,method,body,fetcher=fetch) {
  if(!token) throw new Error('Telegram credential missing');
  if(!['getMe','getWebhookInfo','getUpdates','getChatMember','sendMessage'].includes(method)) throw new Error('Telegram method forbidden');
  const r=await fetcher('https://api.telegram.org/bot'+token+'/'+method,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(35000)});
  if(!r.ok) throw new Error('Telegram HTTP '+r.status);
  const data=await r.json();
  if(data.ok!==true) throw new Error('Telegram rejected request');
  return data.result;
}
export async function processJob(id,{db,token,model,request,send=telegram,dialog=runDialog}) {
  if(!Number.isSafeInteger(id)||id<=0) throw new Error('Exact positive job id required');
  const config=(await db.request('owner_agent_config?id=eq.1&select=*'))?.[0];
  const members=await db.request('owner_agent_members?active=eq.true&select=user_id,role,active');
  let job=(await db.request('owner_agent_jobs?id=eq.'+id+'&select=*'))?.[0];
  if(!job || !permitted(config,members,job)) return {status:'ignored'};
  if(job.status!=='pending') return {status:'already_claimed',job_id:id};
  const lease=randomUUID();
  const rows=await db.request('owner_agent_jobs?id=eq.'+id+'&status=eq.pending',{method:'PATCH',body:{status:'running',lease_token:lease},prefer:'return=representation'});
  if(rows?.length!==1) return {status:'already_claimed',job_id:id};
  job=rows[0];
  const save=async patch=>{
    const changed=await db.request('owner_agent_jobs?id=eq.'+id+'&status=eq.running&lease_token=eq.'+lease,{method:'PATCH',body:patch,prefer:'return=representation'});
    if(changed?.length!==1) throw new Error('Job lease lost');
    job={...job,...changed[0]};
  };
  let uncertain=false;
  try {
    const me=await send(token,'getMe',{});
    if(me.username!=='veschi_owner_ai_bot'||Number(me.id)!==Number(config.bot_id)) throw new Error('Wrong bot identity');
    const readMemory=memoryReader(db);
    const memory=await loadMemory(readMemory,job.request_text);
    const result=await dialog({question:job.request_text,history:memory.history,memoryContext:memory.context,readMemory,db,model,request});
    const answer=result.answer;
    await save({answer,evidence:result.evidence});
    const hash=createHash('sha256').update(answer).digest('hex');
    const parts=splitText(answer);
    if(parts.length>5) throw new Error('Answer too long');
    for(let index=0;index<parts.length;index++) {
      // Immediate revocation takes effect before every outbound message.
      const current=(await db.request('owner_agent_config?id=eq.1&select=*'))?.[0];
      const allowed=await db.request('owner_agent_members?active=eq.true&select=user_id,role,active');
      if(!permitted(current,allowed,job) || Number(current.bot_id)!==Number(me.id)) throw new Error('Access revoked');
      const delivery={...job.delivery,state:'uncertain',part:index,answer_sha256:hash};
      await save({delivery});
      uncertain=true;
      const message=await send(token,'sendMessage',{chat_id:job.chat_id,text:parts[index],reply_parameters:{message_id:job.message_id,allow_sending_without_reply:true},...(job.thread_id?{message_thread_id:job.thread_id}:{})});
      if(!Number.isSafeInteger(message?.message_id)||Number(message.chat?.id)!==Number(job.chat_id)) throw new Error('Receipt mismatch');
      await save({delivery:{...delivery,state:'confirmed',receipts:[...(job.delivery.receipts??[]),{part:index,message_id:message.message_id}]}});
      uncertain=false;
    }
    await save({status:'done',completed_at:new Date().toISOString(),lease_token:null});
    return {status:'done',job_id:id};
  } catch {
    // Unknown outbound result is never blindly repeated. A killed running worker is likewise not auto-reclaimed.
    try {await save({status:uncertain?'uncertain':'failed',error:uncertain?'Delivery outcome unknown; manual receipt check required.':'Analysis stopped; inspect configuration and evidence.',completed_at:new Date().toISOString(),lease_token:null});} catch {}
    return {status:uncertain?'uncertain':'failed',job_id:id};
  }
}
if(process.argv[1] && import.meta.url===pathToFileURL(process.argv[1]).href) {
  const raw=process.env.OWNER_AGENT_JOB_ID;
  if(!/^\d+$/.test(raw??'')) throw new Error('Job id missing');
  const db=new Database({url:process.env.SUPABASE_URL,key:process.env.SUPABASE_SECRET_KEY});
  const result=await processJob(Number(raw),{db,token:process.env.OWNER_TELEGRAM_BOT_TOKEN,model:process.env.OWNER_AI_MODEL||'gpt-4.1-mini',request:body=>modelRequest(body,{key:process.env.OPENAI_API_KEY})});
  console.log(JSON.stringify(result));
  if(!['done','already_claimed'].includes(result.status)) process.exitCode=1;
}
