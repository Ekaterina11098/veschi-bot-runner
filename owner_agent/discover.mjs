// Only the NEW bot; writes metadata to isolated private setup table. No model/webhook changes/sends.
import {telegram} from './worker.mjs';
import {Database} from './data.mjs';
const token=process.env.OWNER_TELEGRAM_BOT_TOKEN;
try {
  const me=await telegram(token,'getMe',{});
  if(me.username!=='veschi_owner_ai_bot') throw new Error('Unexpected bot');
  const info=await telegram(token,'getWebhookInfo',{});
  if(info.url) throw new Error('New bot already has webhook; discovery stopped without changes');
  // No offset/confirmation: messages remain available. Do not print text or tokens.
  const updates=await telegram(token,'getUpdates',{timeout:0,limit:100,allowed_updates:['message','my_chat_member']});
  const groups=new Map();
  const privatePeople=new Map();
  for(const u of updates) {
    const m=u.message??u.my_chat_member;
    if(m?.chat?.type==='private' && m.from && !m.from.is_bot)privatePeople.set(m.from.id,{user_id:m.from.id,username:m.from.username??null,first_name:m.from.first_name??null});
    if(!m || !['group','supergroup'].includes(m.chat?.type))continue;
    const group=groups.get(m.chat.id)??{chat_id:m.chat.id,title:m.chat.title,participants:[]};
    if(m.from && !m.from.is_bot && !group.participants.some(x=>x.user_id===m.from.id))group.participants.push({user_id:m.from.id,username:m.from.username??null,first_name:m.from.first_name??null});
    groups.set(m.chat.id,group);
  }
  const db=new Database({url:process.env.SUPABASE_URL,key:process.env.SUPABASE_SECRET_KEY});
  const payload={bot_username:me.username,bot_id:me.id,privacy_disabled:me.can_read_all_group_messages===true,groups:[...groups.values()],private_participants:[...privatePeople.values()]};
  await db.request('owner_agent_setup?on_conflict=id',{method:'POST',body:{id:1,payload,observed_at:new Date().toISOString()},prefer:'resolution=merge-duplicates'});
  console.log(JSON.stringify({identified:true,groups:groups.size,telegram_sends:0,model_calls:0}));
}catch {console.error('Discovery failed. Check new bot identity, webhook absence, pending messages and private setup table. No Telegram sends or model calls.');process.exitCode=1;}
