/** All current human group members may approve exact saved price recommendations.
 * Future explicit decisions authorize exact WB seller prices through an isolated worker.
 */
export function priceApprovalIntent(text:string):null|{all:boolean,articles:string[]} {
 const s=text.trim();
 if (/^(?:(?:да|хорошо|ок|ладно)[, ]+)?(?:сделай(?:\s+вс[её])?|делай|выполни(?:\s+вс[её])?|выполняй|примени(?:\s+вс[её])?|применяй|подтверждаю|согласен|согласна|запускай|да)[.!]?$/iu.test(s))return {all:true,articles:[]};
 if (/^\/(?:price_confirm|confirm)(?:@[a-z0-9_]+)?(?:\s+(?:все|all))?[.!]?$/iu.test(s) ||
     /^подтверждаю\s+все\s+(?:изменения|цены)[.!]?$/iu.test(s) ||
     /^да[,]?\s+давай\s+изменим\s+цен[ыуа]\s+как\s+ты\s+предлагаешь[.!]?$/iu.test(s))
  return {all:true,articles:[]};
 const subset=/^(?:подтверждаю|\/price_confirm(?:@[a-z0-9_]+)?)\s*:\s*(.+)$/iu.exec(s);
 if(subset){
  const articles=subset[1].split(/[,;\n]/).map(a=>a.trim()).filter(Boolean);
  if(!articles.length||articles.length>100||new Set(articles.map(a=>a.toLowerCase())).size!==articles.length)return {all:false,articles:[]};
  return {all:false,articles};
 }
 if(/^подтверждаю(?:\s|$)/iu.test(s)||/^\/(?:price_confirm|confirm)\b/iu.test(s))return {all:false,articles:[]};
 return null;
}

export function reportProposals(answer:string) {
 const rows:any[]=[];
 const pattern=/^(Повышение|Снижение) · (.+?) Продавец: ([0-9]+(?:[.,][0-9]+)?) → ([0-9]+(?:[.,][0-9]+)?) ¥$/gmu;
 for(const match of answer.matchAll(pattern)){
  const current=Number(match[3].replace(',','.')),target=Number(match[4].replace(',','.'));
  if(!Number.isFinite(current)||!Number.isFinite(target)||current<=0||target<=0||
     (match[1]==='Повышение'?target<=current:target>=current))throw Error('Invalid recommendation');
  rows.push({action:match[1],article:match[2],current_cny:String(current),target_cny:String(target)});
 }
 if(!rows.length||rows.length>100||new Set(rows.map(r=>r.article.toLowerCase())).size!==rows.length)throw Error('Ambiguous recommendations');
 return rows;
}

export async function handlePriceApproval(config:any,message:any,text:string,updateId:number,deps:any):Promise<Response|null>{
 const natural=/^(?:(?:да|хорошо|ок|ладно)[, ]+)?(?:сделай(?:\s+вс[её])?|делай|выполни(?:\s+вс[её])?|выполняй|примени(?:\s+вс[её])?|применяй|подтверждаю|согласен|согласна|запускай|да)[.!]?$/iu.test(text.trim());
 if(natural && (message?.reply_to_message?.from?.id!==config.bot_id || !/^(?:Повышение|Снижение) · .+ Продавец:/mu.test(message?.reply_to_message?.text??'')))return null;
 const intent=priceApprovalIntent(text);
 if(!intent)return null;
 const answer=(t:string)=>Response.json({method:'sendMessage',chat_id:config.chat_id,text:t});
 if(!config.active||message?.chat?.id!==config.chat_id||!['group','supergroup'].includes(message.chat.type)||
    !Number.isSafeInteger(message?.from?.id)||message.from.id<=0||message.from.is_bot||message.sender_chat||
    message.forward_origin||!Number.isSafeInteger(updateId)||updateId<0||!Number.isSafeInteger(message.message_id))return new Response('OK');
 if(!intent.all&&!intent.articles.length)return answer('Ответьте на ценовой отчёт: «Подтверждаю все изменения» или «Подтверждаю: артикул1, артикул2».');
 const quoted=message.reply_to_message;
 if(quoted?.from?.id!==config.bot_id||!Number.isSafeInteger(quoted.message_id)||typeof quoted.text!=='string')
  return answer('Подтверждение нужно отправить через «Ответить» на сегодняшний ценовой отчёт бота.');
 if(!deps.deferMembership){
 const member=await deps.telegram('getChatMember',{chat_id:config.chat_id,user_id:message.from.id});
 if(member.user?.id!==message.from.id||member.user?.is_bot||!(['creator','administrator','member'].includes(member.status)||(member.status==='restricted'&&member.is_member===true)))
  return answer('Подтверждать рекомендации могут текущие участники этой группы.');
 }
 const now=deps.now?deps.now():new Date();
 const day=new Date(now.getTime()+3*3600000).toISOString().slice(0,10);
 const start=new Date(day+'T00:00:00+03:00').toISOString();
 const jobs=await deps.database('business_agent_jobs?agent_id=eq.china&chat_id=eq.'+config.chat_id+'&status=eq.done&request_text=in.(/china_morning_pair_candidates,/china_price_intraday_raise)&created_at=gte.'+encodeURIComponent(start)+'&select=id,request_text,answer,tool_trace,created_at&order=id.desc&limit=20');
 const matching=jobs.filter((j:any)=>j.answer===quoted.text&&j.tool_trace?.some((t:any)=>t.name==='china_price_daily_report'&&t.report_date===day)&&j.tool_trace.some((t:any)=>t.name==='china_report_delivery'&&t.sent_parts>0));
 if(matching.length!==1)return answer('Не удалось однозначно связать ответ с полным сегодняшним ценовым отчётом. Ответьте на актуальный краткий отчёт бота.');
 const job=matching[0];
 let proposals:any[];
 try{proposals=reportProposals(job.answer);}catch{return answer('В этом сообщении нет однозначного списка цен для подтверждения. Ответьте на новый краткий отчёт.');}
 const chosen=intent.all?proposals:proposals.filter(p=>intent.articles.some(a=>a.toLowerCase()===p.article.toLowerCase()));
 if(!chosen.length||(!intent.all&&chosen.length!==intent.articles.length))return answer('Не все указанные артикулы найдены в этом отчёте. Проверьте список; подтверждение не сохранено.');
 const catalogue=(await deps.database('telegram_api_cache?cache_key=eq.china_agent:prices:v1&select=payload'))?.[0]?.payload;
 if(catalogue?.cabinet!=='token_3')throw Error('China catalogue unavailable');
 const selected=[];
 for(const row of chosen){
  const variants=catalogue.rows.filter((p:any)=>p.vendorCode?.toLowerCase()===row.article.toLowerCase());
  if(variants.length!==1)return answer('Артикул неоднозначен в каталоге; подтверждение не сохранено.');
  const p=variants[0];const prices=new Set(p.sizes?.map((s:any)=>Number(s.discountedPrice)));
  if(!Number.isSafeInteger(p.nmID)||p.nmID<=0||p.currencyIsoCode4217!=='CNY'||prices.size!==1||!prices.has(Number(row.current_cny)))
   return answer('Сохранённая цена отличается от отчёта или не подтверждена. Нужен обновлённый отчёт; подтверждение не сохранено.');
  selected.push({...row,nm_id:String(p.nmID),seller_discount:p.discount,base_cny:p.sizes[0].price,club_discount:p.clubDiscount,editable_size_price:p.editableSizePrice});
 }
 selected.sort((a,b)=>a.nm_id.localeCompare(b.nm_id));
 const reportHash=await deps.digest(job.answer);
 const selectionHash=await deps.digest(JSON.stringify(selected));
 const key='china_agent:price_recommendation_approval:v2:'+config.chat_id+':'+job.id+':'+message.from.id+':'+selectionHash;
 const payload={schema_version:2,agent_id:'china',chat_id:config.chat_id,bot_id:config.bot_id,report_date:day,
  report_job_id:job.id,report_message_id:quoted.message_id,report_sha256:reportHash,
  actor_user_id:message.from.id,actor_username:message.from.username??null,actor_first_name:message.from.first_name??null,
  update_id:updateId,input_message_id:message.message_id,input_text:text,scope:'price_recommendations',
  approval_policy:'all_current_human_group_members',decision:'approved_recommendation',status:'recorded',
  selections:selected,created_at:now.toISOString(),membership_verified:!deps.deferMembership,execution_authorized:true,execution_policy:'confirmed_exact_seller_price_v1',wb_writes:0};
 const inserted=await deps.database('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:key,payload,expires_at:'2036-10-19T00:00:00Z'},'resolution=ignore-duplicates,return=representation');
 const retained=(await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(key)+'&select=payload'))?.[0]?.payload;
 if(!retained||retained.actor_user_id!==message.from.id||retained.report_sha256!==reportHash||!deps.same(retained.selections,selected)||retained.execution_authorized!==true)throw Error('Approval readback mismatch');
 await deps.launchPrice(key);
 const listing=selected.map(p=>p.article+': '+p.current_cny.replace('.',',')+' → '+p.target_cny.replace('.',',')+' ¥').join('\n');
 return answer((inserted?.length?'Подтверждение принято':'Это подтверждение уже принято')+
  '.\nАвтор: '+(message.from.first_name??'участник')+' ('+message.from.id+').\n'+listing+
  '\n\nПроверка и применение в WB запущены. Результат придёт отдельным сообщением; повторно подтверждать не нужно.');
}
