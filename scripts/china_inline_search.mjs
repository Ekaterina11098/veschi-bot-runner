import {handleAdvertisingPath} from './china_advertising_ui.mjs';
const ROOT='china_agent:advertising_ui:v1:',CHAT=-1004342917488,BOT=8780468043;
const nonce=()=>[...crypto.getRandomValues(new Uint8Array(8))].map(n=>n.toString(16).padStart(2,'0')).join('');
export async function handleInlineSearch(config,update,deps){
 const q=update.inline_query,cb=update.callback_query,match=/^cai1:([a-f0-9]{16}):(objects|period|cidAll|cid\d{5,12})$/.exec(cb?.data||'');
 if(!q&&!match)return null;
 const actor=q?.from||cb?.from,now=deps.now?deps.now():new Date();
 const empty=async()=>{if(q?.id)await deps.telegram('answerInlineQuery',{inline_query_id:q.id,results:[],cache_time:0,is_personal:true});return new Response('OK');};
 const alert=text=>Response.json({method:'answerCallbackQuery',callback_query_id:cb.id,text,show_alert:true});
 if(config.active!==true||config.chat_id!==CHAT||config.bot_id!==BOT||!Number.isSafeInteger(update.update_id)||update.update_id<0||!Number.isSafeInteger(actor?.id)||actor.id<=0||actor.is_bot!==false)return q?await empty():new Response('OK');
 const get=async k=>(await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(k)+'&select=payload&limit=1'))?.[0]?.payload;
 const policy=await get('china_agent:main_menu:v1:policy');
 if(policy?.enabled!==true||policy.inline_search_enabled!==true)return q?await empty():alert('Поиск временно недоступен.');
 const member=await deps.telegram('getChatMember',{chat_id:CHAT,user_id:actor.id});
 if(member?.user?.id!==actor.id||member.user.is_bot!==false||!(['creator','administrator','member'].includes(member.status)||member.status==='restricted'&&member.is_member===true))return q?await empty():alert('Поиск доступен участникам рабочей группы.');
 if(match){
  const result=await get(ROOT+'inline_result:'+match[1]);
  if(!result||result.actor!==actor.id||Date.parse(result.expires_at)<=now.getTime()||!cb.inline_message_id||result.source_message?.chat?.id!==CHAT||result.source_message.from?.id!==BOT||!['objects','period','cidAll'].includes(match[2])&&!result.campaigns.includes(match[2].slice(3)))return alert('Откройте поиск заново из меню «Реклама».');
  // The inline picker carries no financial data. Continue only in the bound work group,
  // using an actor-bound native session and a new bot-owned card.
  const synthetic={...update,callback_query:{...cb,data:'cam1:'+match[1]+':'+(match[2]==='objects'&&result.campaigns.length?'cidAll':match[2]),message:result.source_message}};
  return handleAdvertisingPath(config,synthetic,{...deps,forceNewMessage:true});
 }
 if(!q.id||!['group','supergroup'].includes(q.chat_type)||typeof q.query!=='string'||q.query.length>100||q.offset)return empty();
 const prefix=/^(ДРР|Конверсия|Воронка)\s+([\s\S]*)$/iu.exec(q.query);
 if(!prefix)return empty();
 const general=prefix[1].toLowerCase()==='воронка',metric=general?'general':prefix[1].toLowerCase()==='дрр'?'drr':'cr',text=prefix[2].trim();
 const context=await get(ROOT+'inline_context:'+actor.id+':'+metric);
 if(!context||context.actor!==actor.id||Date.parse(context.expires_at)<=now.getTime()||context.source_message?.chat?.id!==CHAT||context.source_message.from?.id!==BOT||!text||text.length>80)return empty();
 const lookup=await deps.database('rpc/china_menu_inline_products','POST',{p_query:text});
 if(lookup?.cabinet!=='token_3'||!Array.isArray(lookup.rows))return empty();
 const insert=async(k,p)=>(await deps.database('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:k,payload:p,expires_at:new Date(now.getTime()+3600000).toISOString()},'resolution=ignore-duplicates,return=representation'))?.length===1;
 const results=[];
 for(const row of lookup.rows.slice(0,20)){
  if(!/^\d{5,12}$/.test(row.nm)||typeof row.article!=='string')continue;
  const sid=nonce(),campaigns=(row.campaigns||[]).map(String).filter(cid=>/^\d{5,12}$/.test(cid)),ctx={...context.context,kind:general?'general':'ad',metric:general?'cr':metric,nm:row.nm,article:row.article,view:'objects',page:0};delete ctx.cid;delete ctx.matches;
  const expires_at=new Date(now.getTime()+900000).toISOString();
  if(!await insert(ROOT+'session:'+sid,{actor:actor.id,context:ctx,message_id:context.source_message.message_id,expires_at}))throw Error('Inline session unavailable');
  if(!await insert(ROOT+'inline_result:'+sid,{actor:actor.id,nm:row.nm,article:row.article,campaigns,source_message:context.source_message,expires_at}))throw Error('Inline result unavailable');
  const title=(general?'Общая воронка':metric==='drr'?'ДРР':'Рекламная конверсия')+' · '+row.article;
  const buttons=general?[]:campaigns.slice(0,8).map(cid=>[{text:'РК '+cid,callback_data:'cai1:'+sid+':cid'+cid}]);
  buttons.push([{text:general?'Выбрать период':campaigns.length?'Все РК товара':'Выбрать РК товара',callback_data:'cai1:'+sid+':'+(general?'period':campaigns.length?'cidAll':'objects')}]);
  results.push({type:'article',id:sid,title:row.article,description:general?'Общая воронка · выбрать период':(metric==='drr'?'ДРР':'Конверсия')+' · '+(campaigns.length?campaigns.length+' РК':'проверить сохранённые данные'),input_message_content:{message_text:title+(general?'\nВыберите период.':'\nВыберите РК товара:')},reply_markup:{inline_keyboard:buttons}});
 }
 const acknowledged=await deps.telegram('answerInlineQuery',{inline_query_id:q.id,results,cache_time:1,is_personal:true,next_offset:''});
 if(acknowledged!==true)throw Error('Inline answer not verified');
 return new Response('OK');
}
