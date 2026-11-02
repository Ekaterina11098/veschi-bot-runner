import {route,THREAD} from './codex-route.mjs';
export async function acceptCodex(config,message,text,updateId,database) {
 const policy=(await database('telegram_api_cache?cache_key=eq.china_agent:codex_bridge:v1:policy&select=payload'))?.[0]?.payload;
 const selected=route(text,policy,message);
 if(selected.kind==='legacy')return {};
 if(selected.kind==='legacy_explicit')return {legacy_text:selected.text};
 if(selected.kind==='expired')return {response:Response.json({method:'sendMessage',chat_id:config.chat_id,text:'Тест прямой связи с Codex приостановлен. Вопрос не передан старому агенту. Для него используйте «Агент, …».'})};
 if(!Number.isSafeInteger(updateId)||updateId<0||!Number.isSafeInteger(message.message_id)||selected.text.length>4000||!selected.text)return {response:new Response('Invalid update',{status:400})};
 if(config.bot_id!==policy.bot_id||config.chat_id!==policy.chat_id)throw Error('Bridge configuration mismatch');
 const marker={name:'china_saved_question',message_id:message.message_id,bot_id:config.bot_id,thread_id:message.message_thread_id??null,codex_bridge:true,codex_thread_id:THREAD,bridge_request_text:selected.text,original_request_text:text};
 if(message.reply_to_message?.from?.id===config.bot_id){marker.reply_message_id=message.reply_to_message.message_id;marker.reply_text=(message.reply_to_message.text||message.reply_to_message.caption||'').slice(0,3500)}
 let jobs=await database('business_agent_jobs?on_conflict=agent_id,update_id','POST',{agent_id:'china',update_id:updateId,chat_id:config.chat_id,sender_id:message.from.id,request_text:'/codex '+selected.text,tool_trace:[marker]},'resolution=ignore-duplicates,return=representation');
 if(!jobs?.length)jobs=await database('business_agent_jobs?agent_id=eq.china&update_id=eq.'+updateId+'&chat_id=eq.'+config.chat_id+'&sender_id=eq.'+message.from.id+'&select=id,status,request_text,tool_trace&limit=1');
 if(jobs?.length!==1)throw Error('Bridge job readback mismatch');
 const job=jobs[0];const retained=job.tool_trace?.find(x=>x.name==='china_saved_question');
 if(!retained?.codex_bridge||retained.message_id!==message.message_id||retained.codex_thread_id!==THREAD)throw Error('Bridge job conflict');
 const key='china_agent:codex_bridge:v1:inbox:'+job.id;
 const payload={status:'queued',job_id:job.id,update_id:updateId,chat_id:config.chat_id,bot_id:config.bot_id,sender_id:message.from.id,input_message_id:message.message_id,thread_id:THREAD,request_text:selected.text,created_at:new Date().toISOString(),origin:'telegram',pilot:true,wb_action_permission:false};
 await database('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:key,payload,expires_at:'2036-11-02T00:00:00Z'},'resolution=ignore-duplicates,return=representation');
 const proof=(await database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(key)+'&select=payload'))?.[0]?.payload;
 if(proof?.job_id!==job.id||proof.input_message_id!==message.message_id||proof.thread_id!==THREAD||proof.chat_id!==config.chat_id)throw Error('Bridge inbox readback mismatch');
 return {response:new Response('OK')};
}
