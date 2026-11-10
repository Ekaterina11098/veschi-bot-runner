/** Exact price report callbacks. No marketplace transport or model access. */
export async function handlePriceButtons(config,callback,updateId,deps){
 const match=/^cpb1:([a-f0-9]{24}):(all|up|down)$/.exec(callback?.data??'');
 if(!match)return null;
 const answer=(text,alert=false)=>Response.json({method:'answerCallbackQuery',callback_query_id:callback.id,text:text.slice(0,190),show_alert:alert});
 const m=callback.message;const actor=callback.from;
 if(!config.active||config.chat_id!==-1004342917488||config.bot_id!==8780468043||
    !Number.isSafeInteger(updateId)||updateId<0||!Number.isSafeInteger(actor?.id)||actor.id<=0||actor.is_bot!==false||
    !callback.id||m?.chat?.id!==config.chat_id||!['group','supergroup'].includes(m.chat.type)||
    m.from?.id!==config.bot_id||m.from.is_bot!==true||!Number.isSafeInteger(m.message_id)||m.forward_origin||m.sender_chat)
  return answer('Эта кнопка недоступна в данном сообщении.',true);
 const fetchValue=async key=>(await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(key)+'&select=payload&limit=1'))?.[0]?.payload;
 const [p,b]=await Promise.all([fetchValue('china_agent:price_buttons:v1:'+match[1]),fetchValue('china_agent:price_report_message:v1:'+m.message_id)]);
 const now=deps.now?deps.now():new Date();const day=new Date(now.getTime()+3*3600000).toISOString().slice(0,10);
 if(!p||p.status!=='active'||p.chat_id!==config.chat_id||p.bot_id!==config.bot_id||p.report_date!==day||
    !Number.isFinite(Date.parse(p.expires_at))||Date.parse(p.expires_at)<=now.getTime()||
    b?.status!=='sent'||b.message_id!==m.message_id||b.report_job_id!==p.report_job_id||b.report_sha256!==p.report_sha256||
    b.chat_id!==config.chat_id||b.bot_id!==config.bot_id||b.report_date!==day||!p.allowed_modes?.includes(match[2]))
  return answer('Отчёт устарел, отозван или кнопка не связана с доставленным планом.',true);
 const receipt=await fetchValue(b.receipt_key);
 if(receipt?.status!=='sent'||receipt.message_id!==m.message_id||receipt.receipt?.chat?.id!==config.chat_id)
  return answer('Доставка этого отчёта не подтверждена.',true);
 const jobs=await deps.database('business_agent_jobs?id=eq.'+p.report_job_id+'&agent_id=eq.china&chat_id=eq.'+config.chat_id+'&status=eq.done&select=id,answer&limit=1');
 if(jobs?.length!==1||typeof jobs[0].answer!=='string'||await deps.digest(jobs[0].answer)!==p.report_sha256)
  return answer('Состав отчёта изменился. Нужен новый отчёт.',true);
 let rows;try{rows=deps.reportProposals(jobs[0].answer);}catch{return answer('В отчёте нет точного списка цен.',true);}
 const selected=rows.filter(r=>match[2]==='all'||r.action===(match[2]==='up'?'Повышение':'Снижение'));
 if(!selected.length)return answer('В этом отчёте нет таких рекомендаций.',true);
 // Reuse the exact established price approval path and worker membership/preflight guards.
 const text=match[2]==='all'?'Сделай всё':'Подтверждаю: '+selected.map(r=>r.article).join(', ');
 const message={message_id:m.message_id,chat:m.chat,from:actor,reply_to_message:m};
 const wrapped={...deps,database:async(path,method='GET',body,...rest)=>{
  if(method==='POST'&&body?.cache_key?.startsWith('china_agent:price_recommendation_approval:v2:')){
   body={...body,payload:{...body.payload,confirmation_source:'telegram_callback',callback_query_id:callback.id,callback_mode:match[2],callback_report_message_id:m.message_id}};
  }
  return deps.database(path,method,body,...rest);
 }};
 const result=await deps.handlePriceApproval(config,message,text,updateId,wrapped);
 if(!result)return answer('Не удалось подтвердить цены этого отчёта.',true);
 const payload=await result.json();const ok=/Проверка и применение в WB запущены/.test(payload.text??'');
 return answer(ok?'Подтверждение принято: '+selected.length+' изменений. Результат проверки WB придёт отдельно.':payload.text??'Подтверждение не принято.',!ok);
}
