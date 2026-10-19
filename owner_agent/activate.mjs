// Explicit one-time activation of the NEW bot only. Existing webhooks/agents untouched.
import {createHash} from 'node:crypto';
import {Database} from './data.mjs';
const hash=x=>createHash('sha256').update(x).digest('hex');
const token=process.env.OWNER_TELEGRAM_BOT_TOKEN;
const db=new Database({url:process.env.SUPABASE_URL,key:process.env.SUPABASE_SECRET_KEY});
async function tg(method,body) {
  if(!['getMe','getWebhookInfo','setWebhook','getChat'].includes(method))throw new Error('Forbidden method');
  const r=await fetch('https://api.telegram.org/bot'+token+'/'+method,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(30000)});
  const data=await r.json();
  if(!r.ok||data.ok!==true)throw new Error('Telegram setup HTTP '+r.status);
  return data.result;
}
try {
  const c=(await db.request('owner_agent_config?id=eq.1&select=*'))?.[0];
  const members=await db.request('owner_agent_members?active=eq.true&select=user_id,role,active');
  if(!c || c.bot_username!=='veschi_owner_ai_bot'||!members.some(x=>x.role==='owner'))throw new Error('Explicit group/owner configuration required');
  const me=await tg('getMe',{});
  if(me.username!==c.bot_username||Number(me.id)!==Number(c.bot_id)||me.can_read_all_group_messages!==true)throw new Error('New bot identity/privacy mismatch');
  const chat=await tg('getChat',{chat_id:c.chat_id});
  if(!['group','supergroup'].includes(chat.type)||chat.username)throw new Error('Private group required');
  const url=new URL('/functions/v1/owner-agent-webhook',process.env.SUPABASE_URL).href;
  const current=await tg('getWebhookInfo',{});
  if(current.url && current.url!==url)throw new Error('Unexpected webhook; refusing to replace');
  const secret=hash('veschi-owner-webhook-v1:'+token);
  const digest=hash(secret);
  const ready=await db.request('owner_agent_config?id=eq.1&bot_id=eq.'+c.bot_id+'&chat_id=eq.'+c.chat_id,{method:'PATCH',body:{secret_digest:digest,active:true},prefer:'return=representation'});
  if(ready?.length!==1)throw new Error('Configuration changed');
  const probe=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-Telegram-Bot-Api-Secret-Token':secret},body:'{"probe":true}',signal:AbortSignal.timeout(20000)});
  const proof=await probe.json();
  if(!probe.ok||proof.agent!=='owner'||proof.authenticated!==true||proof.active!==true)throw new Error('New ingress probe failed');
  await tg('setWebhook',{url,secret_token:secret,allowed_updates:['message','edited_message'],drop_pending_updates:false});
  const after=await tg('getWebhookInfo',{});
  if(after.url!==url)throw new Error('Webhook readback mismatch');
  console.log(JSON.stringify({active:true,bot_username:me.username,webhook_verified:true,telegram_sends:0}));
} catch {
  // Fail closed for this agent alone. Never remove another bot's webhook.
  try {await db.request('owner_agent_config?id=eq.1',{method:'PATCH',body:{active:false}});}catch{}
  console.error('Owner agent setup stopped; owner config disabled. Check token, private group, ingress and runner readiness.');
  process.exitCode=1;
}
