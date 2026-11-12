/** Selection only until explicit confirm. No WB requests, credentials or model calls. */
const ROOT='china_agent:report_buttons:v1:',PLAN='china_agent:loss_plan:v1:',GATE='china_agent:daily_action_claim:v1:';
const GROUPS=[['up','Повысить ставки'],['add','Добавить товары'],['down','Снизить ставки'],['exclude','Исключить товары'],['archive','Завершить РК']];
export function keyboard(token,p,selected=[],page=0){
 const set=new Set(selected),pre='cab1:'+token+':';let rows=[];
 if(p.family==='budgets'){
  const start=page*6;rows=p.items.slice(start,start+6).map((i,k)=>[{text:(set.has(i.id)?'[x] ':'[ ] ')+'РК '+i.campaign_id+' · +'+i.amount_cny+' CNY',callback_data:pre+'i'+(start+k)}]);
  const nav=[];if(page>0)nav.push({text:'‹ Назад',callback_data:pre+'p'+(page-1)});if(start+6<p.items.length)nav.push({text:'Далее ›',callback_data:pre+'p'+(page+1)});if(nav.length)rows.push(nav);
 }else for(const[g,label]of GROUPS){const all=p.items.filter(i=>i.group===g);if(all.length){const n=all.filter(i=>set.has(i.id)).length;rows.push([{text:(n===all.length?'[x] ':n?'[−] ':'[ ] ')+label+' · '+n+'/'+all.length,callback_data:pre+'g'+g}]);}}
 rows.push([{text:'Выбрать всё',callback_data:pre+'all'},{text:'Сбросить',callback_data:pre+'clear'}]);
 const money=p.items.filter(i=>set.has(i.id)).reduce((n,i)=>n+(i.amount_cny||0),0);
 rows.push([{text:'Посмотреть выбранное · '+selected.length+(money?' · '+money+' CNY':''),callback_data:pre+'review'}]);rows.push([{text:'‹ Главное меню',callback_data:'cmn1:home'}]);return {inline_keyboard:rows};
}
export async function handleReportButtons(config,cb,updateId,deps){
 const match=/^cab1:([a-f0-9]{24}):(all|clear|review|g(?:up|add|down|exclude|archive)|i\d+|p\d+|confirm[a-f0-9]{12}|back)$/.exec(cb?.data??'');if(!match)return null;
 const answer=(text,alert=false)=>Response.json({method:'answerCallbackQuery',callback_query_id:cb.id,text:text.slice(0,190),show_alert:alert});
 const m=cb.message,actor=cb.from,token=match[1],op=match[2];
 if(!config.active||config.chat_id!==-1004342917488||config.bot_id!==8780468043||!Number.isSafeInteger(updateId)||updateId<0||!cb.id||!Number.isSafeInteger(actor?.id)||actor.id<=0||actor.is_bot!==false||m?.chat?.id!==config.chat_id||!['supergroup','group'].includes(m.chat.type)||m.from?.id!==config.bot_id||m.from.is_bot!==true||!Number.isSafeInteger(m.message_id)||m.forward_origin||m.sender_chat)return answer('Кнопка недоступна в этом сообщении.',true);
 const get=async k=>(await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(k)+'&select=payload&limit=1'))?.[0]?.payload;
 const insert=async(k,v)=>!!(await deps.database('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:k,payload:v,expires_at:'2036-11-11T00:00:00Z'},'resolution=ignore-duplicates,return=representation'))?.length;
 const put=async(k,v)=>{const r=await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(k),'PATCH',{payload:v,updated_at:new Date().toISOString()},'return=representation');if(r?.length!==1)throw Error('Button state unavailable');};
 const cas=async(k,old,v)=>!!(await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(k)+'&payload=eq.'+encodeURIComponent(JSON.stringify(old)),'PATCH',{payload:v},'return=representation'))?.length;
 const policy=await get(ROOT+'policy');if(policy?.enabled!==true)return answer('Кнопки временно отключены. Используйте текстовое подтверждение отчёта.',true);
 const p=await get(ROOT+'plan:'+token);if(!p||p.status!=='active'||p.chat_id!==config.chat_id||p.bot_id!==config.bot_id)return answer('Этот план недоступен.',true);
 const original=await get(PLAN+p.plan_id),now=deps.now?deps.now():new Date();
 if(!original||original.plan_sha256!==p.plan_sha256||original.invalidated_at||['revoked','invalidated'].includes(original.status)||original.owner_budget_resolution||!Number.isFinite(Date.parse(original.expires_at))||Date.parse(original.expires_at)<=now.getTime())return answer('Отчёт заменён, отозван или истёк.',true);
 if(original.validity_mode==='until_replaced'){const cur=await get('china_agent:daily_ad_current_report:v1:'+original.family);if(cur?.report_generation!==(original.report_generation||original.parent_plan_id||original.plan_id))return answer('Отчёт заменён новым.',true);}
 const parentExec=await get('china_agent:daily_ad_execution:v2:'+p.plan_id);if(parentExec?.items?.length)return answer('План уже обрабатывался. Смотрите итог; повтор закрыт.',true);
 const member=await deps.telegram('getChatMember',{chat_id:config.chat_id,user_id:actor.id});
 if(member?.user?.id!==actor.id||member.user.is_bot!==false||!(['creator','administrator','member'].includes(member.status)||(member.status==='restricted'&&member.is_member===true)))return answer('Подтверждение доступно участникам этой группы.',true);
 const sk=ROOT+'selection:'+token+':'+actor.id;
 let s=await get(sk);if(!s){const initial={status:'selecting',revision:0,selected_ids:[],actor_id:actor.id,token,plan_sha256:p.plan_sha256};await insert(sk,initial);s=await get(sk);}
 if(!s||s.actor_id!==actor.id||s.plan_sha256!==p.plan_sha256)return answer('Состав плана изменился.',true);
 const binding=await get(ROOT+'message:'+m.message_id),review=await get(ROOT+'review_message:'+m.message_id);
 const onReport=binding?.status==='sent'&&binding.token===token&&binding.plan_sha256===p.plan_sha256&&binding.chat_id===config.chat_id&&binding.receipt?.message_id===m.message_id&&binding.receipt.chat?.id===config.chat_id;
 const onReview=review?.status==='sent'&&review.token===token&&review.actor_id===actor.id&&review.plan_sha256===p.plan_sha256;
 const sharedReview=review?.status==='sent'&&review.token===token&&review.plan_sha256===p.plan_sha256&&review.receipt?.message_id===m.message_id&&review.receipt.chat?.id===config.chat_id;
 if(sharedReview){
  const confirmed=await get(ROOT+'confirmation:'+token+'-'+review.actor_id);
  if(confirmed?.status==='confirmed'&&confirmed.plan_sha256===p.plan_sha256){
   const executed=await get('china_agent:daily_ad_execution:v2:'+p.plan_id+'-buttons-'+token+'-'+review.actor_id);
   if(executed?.status==='done'&&review.selected_ids?.every(id=>executed.items?.some(i=>i.id===id&&i.status==='verified')))return answer('Уже выполнено. Итог — в этой карточке. Повторных изменений не будет.',true);
   if(executed?.status==='done')return answer('Обработка завершена. Смотрите итог в этой карточке.',true);
   return answer('Этот выбор уже подтверждён. Повтор закрыт; итог появится в этой карточке.',true);
  }
  if(review.actor_id!==actor.id)return answer('Это выбор другого участника. Под исходным PNG соберите свой выбор и нажмите «Посмотреть выбранное».',true);
 }
 if(!onReport&&!onReview)return answer('Откройте свой выбор кнопкой «Посмотреть выбранное» под исходным PNG.',true);
 if(original.visible_from&&Date.parse(original.visible_from)>Date.parse(binding?.receipt?.date?new Date(binding.receipt.date*1000).toISOString():review?.created_at||'')){
  if(onReport)return answer('Отчёт обновлён после создания кнопок.',true);
 }
 const confirmationKey=ROOT+'confirmation:'+token+'-'+actor.id;
 if(op.startsWith('confirm')){
  if(!onReview||review.selection_hash!==op.slice(7)||review.revision!==s.revision||JSON.stringify(review.selected_ids)!==JSON.stringify(s.selected_ids)||!s.selected_ids.length)return answer('Выбор изменён. Откройте выбранное снова.',true);
  const selected=p.items.filter(i=>s.selected_ids.includes(i.id));if(selected.length!==s.selected_ids.length)return answer('Пункты выбора изменились.',true);
  const owner='button:'+token+'-'+actor.id,gateKey=GATE+p.plan_id;let acquired=false;
  for(let n=0;n<4;n++){let g=await get(gateKey);if(!g){await insert(gateKey,{domains:{}});g=await get(gateKey);}if(g.domains?.[p.family]&&g.domains[p.family]!==owner)return answer('Эта часть плана уже подтверждена. Повтор закрыт.',true);if(g.domains?.[p.family]===owner){acquired=true;break;}const next={...g,domains:{...g.domains,[p.family]:owner}};if(await cas(gateKey,g,next)){acquired=true;break;}}
  if(!acquired)return answer('Одновременное подтверждение. Откройте выбор снова.',true);
  const old=await get(confirmationKey);
  if(old&&JSON.stringify(old.selected_ids)!==JSON.stringify(s.selected_ids))return answer('Первый подтверждённый набор уже зафиксирован.',true);
  if(!old)await insert(confirmationKey,{status:'confirmed',plan_id:p.plan_id,plan_sha256:p.plan_sha256,selected_ids:s.selected_ids,sender_id:actor.id,chat_id:config.chat_id,bot_id:config.bot_id,report_message_id:review.report_message_id,review_message_id:m.message_id,callback_query_id:cb.id,update_id:updateId,confirmed_at:now.toISOString()});
  let c=await get(confirmationKey);
  if(!c.job_id){
   const marker={name:'china_saved_question',message_id:review.report_message_id,reply_message_id:review.report_message_id,bot_id:config.bot_id,report_button_confirmation:token+'-'+actor.id};
   const rows=await deps.database('business_agent_jobs?on_conflict=agent_id,update_id','POST',{agent_id:'china',update_id:c.update_id,chat_id:config.chat_id,sender_id:actor.id,request_text:'сделай все',tool_trace:[marker]},'resolution=ignore-duplicates,return=representation');
   const job=rows?.[0]||(await deps.database('business_agent_jobs?agent_id=eq.china&update_id=eq.'+c.update_id+'&select=id,sender_id,chat_id&limit=1'))?.[0];
   if(!job||job.sender_id!==actor.id||job.chat_id!==config.chat_id)throw Error('Confirmation job missing');c={...c,job_id:job.id};await put(confirmationKey,c);
  }
  await put(sk,{...s,status:'confirmed',confirmation_key:confirmationKey});await deps.launch(c.job_id,'dialog');
  return answer('Подтверждено. Итог появится в этой карточке.');
 }
 if(s.status==='confirmed')return answer('Уже подтверждено. Повторное выполнение закрыто.',true);
 if(op==='back')return answer('Выбор сохранён. Вернитесь к исходному PNG отчёта.');
 if(!onReport)return answer('Менять выбор нужно под исходным PNG отчёта.',true);
 if(op==='review'){
  if(!s.selected_ids.length)return answer('Сначала выберите хотя бы один пункт.',true);
  const selected=p.items.filter(i=>s.selected_ids.includes(i.id)),sha=(await deps.digest(JSON.stringify(s.selected_ids))).slice(0,12),rk=ROOT+'review:'+token+':'+actor.id+':'+s.revision;
  const old=await get(rk);if(old)return answer(old.status==='sent'?'Ваш выбор уже показан ниже в чате.':'Доставка карточки проверяется; повтор не отправляю.',old.status!=='sent');
  let text='Выбрано '+selected.length+' '+(p.family==='budgets'?'пополнений':'изменений')+':\n';
  for(const item of selected){const actual=original.items.find(i=>i.id===item.id);if(!actual)return answer('Состав плана изменился.',true);const label=(item.article?item.article+' · ':'')+'РК '+item.campaign_id;
   const detail=item.group==='budget'?'+'+item.amount_cny+' CNY':item.group==='up'||item.group==='down'?actual.old_minor/100+' → '+actual.target_minor/100+' CNY':item.group==='add'?'добавить в '+(actual.placement==='search'?'поиск':'рекомендации')+' по '+actual.target_minor/100+' CNY':item.group==='exclude'?'исключить товар':'завершить РК';text+=label+': '+detail+'\n';}
  const amount=selected.reduce((n,i)=>n+(i.amount_cny||0),0);if(amount)text+='\nИтого: '+amount+' CNY.';text+='\nНевыбранные пункты не выполняются.';
  if(text.length>4000)return answer('Слишком большой выбор для одной карточки. Выберите меньше категорий.',true);
  const state={status:'sending',token,actor_id:actor.id,plan_sha256:p.plan_sha256,revision:s.revision,selection_hash:sha,selected_ids:s.selected_ids,report_message_id:m.message_id,created_at:now.toISOString()};if(!await insert(rk,state))return answer('Карточка уже подготавливается.');
  try{const receipt=await deps.telegram('sendMessage',{chat_id:config.chat_id,text,reply_parameters:{message_id:m.message_id,allow_sending_without_reply:true},reply_markup:{inline_keyboard:[[{text:'Подтвердить '+selected.length+(amount?' · '+amount+' CNY':' изменений'),callback_data:'cab1:'+token+':confirm'+sha}],[{text:'‹ Изменить выбор',callback_data:'cab1:'+token+':back'}]]}});if(receipt?.chat?.id!==config.chat_id||receipt.from?.id!==config.bot_id||!receipt.message_id)throw Error('Review receipt mismatch');const done={...state,status:'sent',message_id:receipt.message_id,receipt};await put(rk,done);if(!await insert(ROOT+'review_message:'+receipt.message_id,done))throw Error('Review binding collision');}catch(e){await put(rk,{...state,status:'uncertain'});throw e;}
  return answer('Выбранные действия показаны ниже.');
 }
 const event=ROOT+'callback:'+cb.id;if(!await insert(event,{status:'claimed',actor_id:actor.id,token,op}))return answer('Этот клик уже обработан.');
 let selected=[...s.selected_ids],page=0;
 if(op==='all')selected=p.items.map(i=>i.id);else if(op==='clear')selected=[];
 else if(op.startsWith('i')){if(p.family!=='budgets')return answer('Неверный тип кнопки.',true);const item=p.items[Number(op.slice(1))];if(!item)return answer('Пункт не найден.',true);selected=selected.includes(item.id)?selected.filter(id=>id!==item.id):[...selected,item.id];page=Math.floor(Number(op.slice(1))/6);}
 else if(op.startsWith('g')){const group=p.items.filter(i=>i.group===op.slice(1));if(!group.length)return answer('Таких рекомендаций нет.',true);selected=group.every(i=>selected.includes(i.id))?selected.filter(id=>!group.some(i=>i.id===id)):[...new Set([...selected,...group.map(i=>i.id)])];}
 else if(op.startsWith('p')){page=Number(op.slice(1));if(p.family!=='budgets'||page<0||page*6>=p.items.length)return answer('Страница не найдена.',true);}
 selected=p.items.filter(i=>selected.includes(i.id)).map(i=>i.id);
 const next={...s,revision:s.revision+1,selected_ids:selected};if(!await cas(sk,s,next))return answer('Выбор изменился одновременно. Нажмите ещё раз.',true);
 await deps.telegram('editMessageReplyMarkup',{chat_id:config.chat_id,message_id:m.message_id,reply_markup:keyboard(token,p,selected,page)});
 await put(event,{status:'applied',actor_id:actor.id,token,op});return answer('Выбрано: '+selected.length+'.');
}
