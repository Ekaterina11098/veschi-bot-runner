import {advertisingMenu} from './china_advertising_ui.mjs';
import {keyboard as reportKeyboard} from './china_report_buttons.mjs';
/** Cache-only Telegram navigation. Never dispatches workers or accesses marketplace APIs. */
export const ROOT='china_agent:main_menu:v1:';
export const mainKeyboard={keyboard:[[{text:'☰ Меню'}],[{text:'📊 Продажи'},{text:'📣 Реклама'}]],resize_keyboard:true,is_persistent:true,one_time_keyboard:false,input_field_placeholder:'Выберите раздел или напишите вопрос'};
const CHAT=-1004342917488,BOT=8780468043;
const fmt=new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2});
const finite=n=>typeof n==='number'&&Number.isFinite(n);
const day=t=>new Date((typeof t==='number'?t:Date.parse(t))+10800000).toISOString().slice(0,10);
const clock=t=>new Date(Date.parse(t)+10800000).toISOString().slice(11,16);
const diff=(n,b)=>finite(n)&&finite(b)?(b===0?'нет базы':((n-b)/b*100>=0?'+':'')+fmt.format((n-b)/b*100)+'%'):'нет сопоставимых данных';
function total(o){const t=o?.totals;return o?.status==='complete'&&finite(t?.count)&&Number.isInteger(t.count)&&t.count>=0&&finite(t.amount_cny)&&t.amount_cny>=0&&Array.isArray(t.unknown_amount_ids)&&!t.unknown_amount_ids.length?t:null;}
function compatible(a,b,n){return a&&b&&a.basis===b.basis&&Date.parse(a.end_msk)-Date.parse(a.start_msk)===Date.parse(b.end_msk)-Date.parse(b.start_msk)&&Date.parse(a.start_msk)-Date.parse(b.start_msk)===n*86400000;}
export async function salesView(get,now=new Date(),dynamics=false){
 const latest=await get('china_agent:hourly_sales_api:v1:latest');
 const key=latest?.source_key;
 const validKey=typeof key==='string'&&/^china_agent:hourly_sales_api:v1:snapshot:\d{4}-\d{2}-\d{2}T\d{2}:MSK(?::attempt:\d+)?$/.test(key);
 const p=validKey?await get(key):null;
 const nav={inline_keyboard:[[{text:dynamics?'Текущие продажи':'Динамика по часам',callback_data:dynamics?'cmn1:sales':'cmn1:dynamic'}],[{text:'Обновить из кэша',callback_data:dynamics?'cmn1:dynamic':'cmn1:sales'}],[{text:'‹ Главное меню',callback_data:'cmn1:home'}]]};
 if(!p||p.cabinet!=='token_3'||p.slot_msk!==latest.slot_msk||!finite(Date.parse(p.observed_at))||!p.orders?.['0']?.basis?.startsWith('FBS created units'))
  return {text:'Продажи\nНет подтверждённого среза. Сбор данных выполняется по штатному расписанию.',reply_markup:nav,source_keys:[]};
 const a=p.orders['0'],t=total(a),slot=p.slot_msk;
 if(!t||!finite(Date.parse(a.start_msk))||!finite(Date.parse(a.end_msk))||a.end_msk!==slot||!a.start_msk.endsWith('T00:00:00+03:00')||day(a.start_msk)!==day(a.end_msk))
  return {text:'Продажи\nДанные о заказах неполные; неизвестные значения не заменены нулями.',reply_markup:nav,source_keys:[key]};
 const age=now.getTime()-Date.parse(p.observed_at),currentHour=new Date(now.getTime()+10800000).toISOString().slice(0,13);
 const stale=age>80*60000||age< -60000||slot.slice(0,13)!==currentHour;
 let lines=['Продажи · '+day(slot)+' · 00:00–'+clock(slot)+' МСК', 'Срез получен: '+day(p.observed_at)+' '+clock(p.observed_at)+' МСК'+(stale?' · данные отстают':''),'',
 'Созданные заказы FBS: '+fmt.format(t.count)+' шт. · '+fmt.format(t.amount_cny)+' CNY'];
 for(const [n,label]of [[1,'Вчера'],[7,'Неделю назад']]){
  const b=p.orders[String(n)],bt=total(b);
  if(!bt||!compatible(a,b,n))lines.push(label+': нет сопоставимых данных');
  else lines.push(label+' · 00:00–'+clock(b.end_msk)+': '+fmt.format(bt.count)+' шт. · '+fmt.format(bt.amount_cny)+' CNY\nК этой базе: заказы '+diff(t.count,bt.count)+' · сумма '+diff(t.amount_cny,bt.amount_cny));
 }
 const sources=[key];
 if(dynamics){
  lines.push('','Динамика суммы заказов с начала дня:');
  const hour=Number(slot.slice(11,13)),from=Math.max(1,hour-7);
  for(let h=from;h<=hour;h++){
   const prefix='china_agent:hourly_sales_api:v1:snapshot:'+day(slot)+'T'+String(h).padStart(2,'0')+':MSK';
   const pointer=await get(prefix+':latest'),k=h===hour?key:typeof pointer?.source_key==='string'&&pointer.source_key.startsWith(prefix+':attempt:')?pointer.source_key:prefix;
   const s=h===hour?p:await get(k),x=s?.orders?.['0'],v=total(x);
   if(!v||s.cabinet!=='token_3'||s.slot_msk!==day(slot)+'T'+String(h).padStart(2,'0')+':00:00+03:00'||x.basis!==a.basis||x.start_msk!==a.start_msk||x.end_msk!==s.slot_msk){lines.push(String(h).padStart(2,'0')+':00 · нет данных');continue;}
   sources.push(k);lines.push(String(h).padStart(2,'0')+':00 · '+fmt.format(v.count)+' шт. · '+fmt.format(v.amount_cny)+' CNY');
  }
  lines.push('Это накопительные суммы, не продажи за отдельный час.');
 }
 lines.push('','Сумма заказов после скидок WB, не прибыль и не выкупы. Покрытие — FBS; полнота всего кабинета не подтверждена.');
 return {text:lines.join('\n'),reply_markup:nav,source_keys:[...new Set(sources)]};
}
export async function advertisingView(get,family,now=new Date(),actorId=null){
 if(!family)return advertisingPage(get,family,now,actorId);
 const pointer=await get('china_agent:daily_ad_current_report:v1:'+family),index=await get(ROOT+'report:'+family);
 if(!index?.pages?.length)return advertisingPage(get,family,now,actorId);
 const views=[],keys=[];
 for(const page of index.pages){
  const p=await get('china_agent:loss_plan:v1:'+page.plan_id);
  if(!p||p.plan_sha256!==page.plan_sha256||p.report_generation!==pointer?.report_generation||index.family!==family)return {text:'Отчёт обновляется. Полный подтверждённый набор страниц пока недоступен.',reply_markup:{inline_keyboard:[[{text:'‹ Реклама',callback_data:'cmn1:ads'}]]},source_keys:[]};
  const one={...index,plan_id:p.plan_id,plan_sha256:p.plan_sha256,message_id:page.message_id,message_ids:[page.message_id],receipt:page.receipt,pages:[page]};
  const v=await advertisingPage(get,family,now,actorId,{pointer,index:one,plan:p});
  if(!v.photos?.length)return v;
  views.push(v);keys.push(...v.source_keys);
 }
 const out={...views[0],source_keys:[...new Set(keys)]};
 out.photos=views.flatMap(v=>v.photos.map(photo=>({...photo,page_view:{text:v.text,reply_markup:v.reply_markup,direct:v.direct}})));
 return out;
}

async function advertisingPage(get,family,now=new Date(),actorId=null,provided=null){
 if(!family)return advertisingMenu();
 const pointer=provided?.pointer||await get('china_agent:daily_ad_current_report:v1:'+family),index=provided?.index||await get(ROOT+'report:'+family);
 const p=provided?.plan||(pointer?.plan_id?await get('china_agent:loss_plan:v1:'+pointer.plan_id):null);
 const nav=[[{text:'‹ Реклама',callback_data:'cmn1:ads'}],[{text:'‹ Главное меню',callback_data:'cmn1:home'}]],title=family==='drr'?'Рекламные кампании':'Бюджеты';
 const valid=index?.status==='sent'&&index.chat_id===CHAT&&index.bot_id===BOT&&index.family===family&&index.plan_id===p?.plan_id&&index.plan_sha256===p?.plan_sha256&&!p.invalidated_at&&!['revoked','invalidated'].includes(p.status)&&p.report_message_ids?.includes(index.message_id)&&index.receipt?.message_id===index.message_id&&index.receipt?.chat?.id===CHAT&&index.receipt?.from?.id===BOT;
 if(!valid)return {text:title+'\nАктуальный доставленный отчёт пока недоступен. Старые рекомендации не подставляю.',reply_markup:{inline_keyboard:nav},source_keys:[]};
 const ids=index.message_ids||[index.message_id],parts=index.pages?.length?index.pages:[{message_id:index.message_id,receipt:index.receipt}];
 if(ids.some(id=>!parts.some(x=>x.message_id===id)))return {text:title+'\nНе все части доставленного отчёта доступны для показа. Неполный отчёт не выдаю за полный.',reply_markup:{inline_keyboard:nav},source_keys:[]};
 const photos=ids.map(id=>{const page=parts.find(x=>x.message_id===id),r=page?.receipt;return r?.chat?.id===CHAT&&r.from?.id===BOT&&p.report_message_ids.includes(id)&&r.message_id===id&&r.photo?.at(-1)?.file_id?{source_message_id:id,photo:r.photo.at(-1).file_id}:null;});
 if(photos.some(x=>!x))return {text:title+'\nНет подтверждённого изображения отчёта.',reply_markup:{inline_keyboard:nav},source_keys:[]};
 const execution=await get('china_agent:daily_ad_execution:v2:'+p.plan_id),result=await get('china_agent:daily_ad_result:v2:'+p.plan_id);
 const allDone=['done','verified'].includes(execution?.status)&&execution.items?.length>0&&execution.items.every(x=>x.status==='verified');
 const started=!!execution&&(execution.items?.length>0||['submitting','submitted','uncertain','running','done','verified'].includes(execution.status));
 const expired=p.validity_mode!=='until_replaced'&&(!Number.isFinite(Date.parse(p.expires_at))||Date.parse(p.expires_at)<=now.getTime());
 let mode=allDone?'complete':started?'processed':expired?'expired':!p.items?.length?'empty':'unavailable',binding=null,actionRows=[];
 const verifiedResult=result?.status==='sent'&&result.chat_id===CHAT&&Number.isSafeInteger(result.message_id)&&result.receipt?.message_id===result.message_id&&result.receipt.chat?.id===CHAT;
 if(allDone||started){
  if(verifiedResult)actionRows=[[{text:allDone?'Все действия выполнены · открыть итог':'Открыть результат',url:'https://t.me/c/4342917488/'+result.message_id}]];
 }else if(!expired&&p.items?.length&&(await get('china_agent:report_buttons:v1:policy'))?.enabled===true){
  const b=await get('china_agent:report_buttons:v1:message:'+index.message_id);
  const reg=b?.token?await get('china_agent:report_buttons:v1:plan:'+b.token):null;
  if(b?.status==='sent'&&b.plan_id===p.plan_id&&b.plan_sha256===p.plan_sha256&&b.family===family&&b.chat_id===CHAT&&b.receipt?.message_id===index.message_id&&reg?.status==='active'&&reg.plan_id===p.plan_id&&reg.plan_sha256===p.plan_sha256&&reg.family===family){
   const state=actorId?await get('china_agent:report_buttons:v1:selection:'+b.token+':'+actorId):null;
   actionRows=reportKeyboard(b.token,reg,state?.selected_ids||[]).inline_keyboard.filter(row=>!row.some(button=>button.callback_data==='cmn1:home'));mode='active';binding={token:b.token,family,source_message_id:index.message_id};
  }
 }
 const status={complete:'Все действия этого плана выполнены и проверены WB. Повторный запуск закрыт.',processed:'Этот план уже обрабатывался. Повторное подтверждение закрыто; смотрите результат.',expired:'Срок действия плана истёк. Изменения недоступны.',empty:'Готовых новых действий нет.',active:'Отметьте нужные действия под PNG. Первое нажатие ничего не исполняет.',unavailable:'Кнопки действий для этого отчёта не подтверждены; изменения недоступны.'}[mode];
 return {text:title+' · '+(index.report_day||day(index.receipt.date*1000))+'\n'+status,photos,reply_markup:{inline_keyboard:[...actionRows,...nav]},direct:{mode,plan_id:p.plan_id,plan_sha256:p.plan_sha256,family,binding,source_message_ids:ids},source_keys:[ROOT+'report:'+family,'china_agent:loss_plan:v1:'+p.plan_id]};
}
export async function bindDirectReport(view,receipt,deps){
 const d=view.direct;if(!d)return;
 const get=async k=>(await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(k)+'&select=payload&limit=1'))?.[0]?.payload;
 const write=async(k,v)=>{
  const old=await get(k);
  if(old&&JSON.stringify(old)!==JSON.stringify(v)){
   const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(old))))].map(x=>x.toString(16).padStart(2,'0')).join('');
   await deps.database('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:ROOT+'archive:'+receipt.message_id+':'+digest,payload:{key:k,payload:old},expires_at:'2036-11-11T00:00:00Z'},'resolution=ignore-duplicates,return=representation');
  }
  const result=await deps.database('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:k,payload:v,expires_at:'2036-11-11T00:00:00Z'},'resolution=merge-duplicates,return=representation');
  if(result?.length!==1)throw Error('Direct report binding unavailable');
 };
 if(receipt?.chat?.id!==CHAT||receipt.from?.id!==BOT||!Number.isSafeInteger(receipt.message_id))throw Error('Direct report recipient mismatch');
 const p=await get('china_agent:loss_plan:v1:'+d.plan_id),pointer=await get('china_agent:daily_ad_current_report:v1:'+d.family);
 if(!p||p.plan_sha256!==d.plan_sha256||p.invalidated_at||(pointer?.plan_id!==p.plan_id&&pointer?.report_generation!==p.report_generation))throw Error('Report replaced during navigation');
 await write(ROOT+'direct_message:'+receipt.message_id,{...d,status:'sent',chat_id:CHAT,bot_id:BOT,message_id:receipt.message_id,receipt,wb_writes:0});
 if(d.mode!=='active')return;
 const oldRoot=await get('china_agent:daily_ad_execution:v2:'+p.plan_id);
 if(oldRoot&&(oldRoot.items?.length||['submitting','submitted','uncertain','running','done','verified'].includes(oldRoot.status)))throw Error('Report started during navigation');
 const donor=await get('china_agent:report_buttons:v1:message:'+d.binding.source_message_id);
 if(donor?.token!==d.binding.token||donor.plan_sha256!==p.plan_sha256||donor.family!==d.family)throw Error('Original button binding changed');
 await write('china_agent:loss_plan:v1:'+p.plan_id,{...p,report_message_ids:[...new Set([...(p.report_message_ids||[]),receipt.message_id])].sort((a,b)=>a-b)});
 await write('china_agent:daily_ad_message:v2:'+receipt.message_id,{plan_id:p.plan_id,plan_sha256:p.plan_sha256,chat_id:CHAT,family:d.family});
 await write('china_agent:report_buttons:v1:message:'+receipt.message_id,{...donor,message_id:receipt.message_id,receipt,menu_source_message_id:d.binding.source_message_id});
}

export async function handleMainMenu(config,update,deps){
 const cb=update.callback_query,m=cb?.message||update.message,text=update.message?.text?.trim();
 const commands={'☰ Меню':'home','Меню':'home','📊 Продажи':'sales','Продажи':'sales','📣 Реклама':'ads','Реклама':'ads','Главное меню':'home','/menu':'home','/start':'home'};
 const match=cb?/^cmn1:(home|sales|dynamic|ads|drr|budgets)$/.exec(cb.data||''):null;
 let op=cb?match?.[1]:(Object.hasOwn(commands,text)?commands[text]:null)||(/^\/(?:menu|start)@[a-z0-9_]+$/i.test(text||'')&&text.split('@')[1].toLowerCase()===config.bot_username?.toLowerCase()?'home':null);
 const processedReply=!cb&&/^(?:сделай(?:\s+вс[её])?|делай|выполни(?:\s+вс[её])?)[.!]?$/iu.test(text||'')&&m?.reply_to_message?.from?.id===BOT;
 if(!op&&!processedReply)return null;
 const actor=cb?.from||m?.from;
 if(config.active!==true||config.chat_id!==CHAT||config.bot_id!==BOT||!Number.isSafeInteger(update.update_id)||update.update_id<0||!Number.isSafeInteger(actor?.id)||actor.id<=0||actor.is_bot!==false||m?.chat?.id!==CHAT||!['supergroup','group'].includes(m.chat.type)||!Number.isSafeInteger(m.message_id)||m.sender_chat||m.forward_origin||(cb&&(m.from?.id!==BOT||!cb.id)))return new Response('OK');
 const get=async k=>(await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(k)+'&select=payload&limit=1'))?.[0]?.payload;
 if((await get(ROOT+'policy'))?.enabled!==true)return null;
 if(!op&&processedReply){const original=await get(ROOT+'direct_message:'+m.reply_to_message.message_id);if(!original||original.mode==='active')return null;op='processed_reply';}
 const member=await deps.telegram('getChatMember',{chat_id:CHAT,user_id:actor.id});
 if(member?.user?.id!==actor.id||member.user.is_bot!==false||!(['creator','administrator','member'].includes(member.status)||(member.status==='restricted'&&member.is_member===true)))return new Response('OK');
 const now=deps.now?deps.now():new Date(),key=ROOT+'delivery:'+update.update_id;
 if(await get(key))return cb?Response.json({method:'answerCallbackQuery',callback_query_id:cb.id}):new Response('OK');
 const view=op==='processed_reply'?{text:'Этот план уже обработан либо недоступен для исполнения. Повторное подтверждение не принято.',reply_markup:{inline_keyboard:[[{text:'‹ Реклама',callback_data:'cmn1:ads'}]]},source_keys:[]}:op==='home'?{text:'Главное меню\nВыберите раздел:',reply_markup:cb?{inline_keyboard:[[{text:'📊 Продажи',callback_data:'cmn1:sales'}],[{text:'📣 Реклама',callback_data:'cmn1:ads'}]]}:mainKeyboard,source_keys:[]}:['sales','dynamic'].includes(op)?await salesView(get,now,op==='dynamic'):await advertisingView(get,op==='ads'?null:op,now,actor.id);
 const entry={status:'sending',chat_id:CHAT,actor_id:actor.id,input_message_id:m.message_id,update_id:update.update_id,op,source_keys:view.source_keys,started_at:now.toISOString(),wb_writes:0};
 const inserted=await deps.database('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:key,payload:entry,expires_at:'2036-11-11T00:00:00Z'},'resolution=ignore-duplicates,return=representation');
 if(!inserted?.length)return new Response('OK');
 let receipt;
 try{
  const all=[];
  if(view.photos?.length){
   for(let i=0;i<view.photos.length;i++){
    const part=view.photos[i],pageView=part.page_view||view,caption=pageView.text+(view.photos.length>1?'\nЧасть '+(i+1)+'/'+view.photos.length:'');
    const markup=pageView.reply_markup;
    const unchanged=i===0&&cb&&m.photo?.at(-1)?.file_id===part.photo&&m.caption===caption&&JSON.stringify(m.reply_markup)===JSON.stringify(markup);
    const r=unchanged?m:await deps.telegram(i===0&&cb?'editMessageMedia':'sendPhoto',{chat_id:CHAT,...(i===0&&cb?{message_id:m.message_id,media:{type:'photo',media:part.photo,caption}}:{photo:part.photo,caption}),reply_markup:markup});
    if(r?.chat?.id!==CHAT||r.from?.id!==BOT||!Number.isSafeInteger(r.message_id))throw Error('Menu photo receipt mismatch');
    all.push(r);entry.sent_parts=all.map(x=>({message_id:x.message_id,receipt:x}));
    await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(key),'PATCH',{payload:{...entry,status:'sending',sent_parts:entry.sent_parts}},'return=representation');
    await bindDirectReport(pageView,r,deps);
   }
   receipt=all[0];
  }else{
   receipt=cb&&!m.photo&&m.text===view.text&&JSON.stringify(m.reply_markup)===JSON.stringify(view.reply_markup)?m:await deps.telegram(cb&&!m.photo?'editMessageText':'sendMessage',{chat_id:CHAT,...(cb&&!m.photo?{message_id:m.message_id}:{}),text:view.text,reply_markup:view.reply_markup});
  }
  if(receipt?.chat?.id!==CHAT||receipt?.from?.id!==BOT||!Number.isSafeInteger(receipt.message_id))throw Error('Menu receipt mismatch');
  if(cb&&m.photo&&!view.photos?.length){try{await deps.telegram('editMessageReplyMarkup',{chat_id:CHAT,message_id:m.message_id,reply_markup:{inline_keyboard:[]}});}catch{}}
  entry.message_ids=all.length?all.map(x=>x.message_id):[receipt.message_id];
 }catch(error){
  await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(key),'PATCH',{payload:{...entry,status:'uncertain',error:'Telegram menu outcome not verified'}},'return=representation');
  throw error;
 }
 const saved=await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(key),'PATCH',{payload:{...entry,status:'sent',message_id:receipt.message_id,receipt}},'return=representation');
 if(saved?.length!==1)throw Error('Menu receipt journal unavailable');
 return cb?Response.json({method:'answerCallbackQuery',callback_query_id:cb.id}):new Response('OK');
}
