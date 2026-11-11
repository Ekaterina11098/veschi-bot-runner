/** Cache-only Telegram navigation. Never dispatches workers or accesses marketplace APIs. */
export const ROOT='china_agent:main_menu:v1:';
export const mainKeyboard={keyboard:[[{text:'📊 Продажи'}],[{text:'📣 Реклама'}]],resize_keyboard:true,is_persistent:true,one_time_keyboard:false,input_field_placeholder:'Выберите раздел или напишите вопрос'};
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
export async function advertisingView(get,family,now=new Date()){
 if(!family)return {text:'Реклама\nВыберите отчёт:',reply_markup:{inline_keyboard:[[{text:'Рекламные кампании',callback_data:'cmn1:drr'}],[{text:'Бюджеты',callback_data:'cmn1:budgets'}],[{text:'‹ Главное меню',callback_data:'cmn1:home'}]]},source_keys:[]};
 const pointer=await get('china_agent:daily_ad_current_report:v1:'+family);
 const index=await get(ROOT+'report:'+family);
 const p=pointer?.plan_id?await get('china_agent:loss_plan:v1:'+pointer.plan_id):null;
 const nav=[[{text:'‹ Реклама',callback_data:'cmn1:ads'}],[{text:'‹ Главное меню',callback_data:'cmn1:home'}]];
 const title=family==='drr'?'Рекламные кампании':'Бюджеты';
 const valid=index?.status==='sent'&&index.chat_id===CHAT&&index.bot_id===BOT&&index.family===family&&index.plan_id===p?.plan_id&&index.plan_sha256===p?.plan_sha256&&!p.invalidated_at&&!['revoked','invalidated'].includes(p.status)&&p.report_message_ids?.includes(index.message_id)&&index.receipt?.message_id===index.message_id&&index.receipt?.chat?.id===CHAT&&index.receipt?.from?.id===BOT;
 if(!valid)return {text:title+'\nАктуальный доставленный отчёт пока недоступен. Старые рекомендации не подставляю.',reply_markup:{inline_keyboard:nav},source_keys:[]};
 const mids=Array.isArray(index.message_ids)?index.message_ids:[index.message_id];
 const links=mids.filter(Number.isSafeInteger).map((mid,i)=>[{text:'Открыть отчёт'+(mids.length>1?' · часть '+(i+1):''),url:'https://t.me/c/4342917488/'+mid}]);
 const execution=await get('china_agent:daily_ad_execution:v2:'+p.plan_id);
 const done=execution?.status==='verified';
 return {text:title+'\nОтчёт: '+(index.report_day||day(index.receipt.date*1000))+
  (done?'\nДействия этого плана уже выполнены. Итог доступен под отчётом.':'\nВыбор и подтверждение действий — под исходным отчётом.')+
  (index.report_day&&index.report_day!==day(now.toISOString())?'\nЭто последний доставленный отчёт за указанную дату.':''),
  reply_markup:{inline_keyboard:[...links,...nav]},source_keys:[ROOT+'report:'+family,'china_agent:loss_plan:v1:'+p.plan_id]};
}
export async function handleMainMenu(config,update,deps){
 const cb=update.callback_query,m=cb?.message||update.message,text=update.message?.text?.trim();
 const commands={'📊 Продажи':'sales','Продажи':'sales','📣 Реклама':'ads','Реклама':'ads','Главное меню':'home','/menu':'home','/start':'home'};
 const match=cb?/^cmn1:(home|sales|dynamic|ads|drr|budgets)$/.exec(cb.data||''):null;
 const op=cb?match?.[1]:(Object.hasOwn(commands,text)?commands[text]:null)||(/^\/(?:menu|start)@[a-z0-9_]+$/i.test(text||'')&&text.split('@')[1].toLowerCase()===config.bot_username?.toLowerCase()?'home':null);
 if(!op)return null;
 const actor=cb?.from||m?.from;
 if(config.active!==true||config.chat_id!==CHAT||config.bot_id!==BOT||!Number.isSafeInteger(update.update_id)||update.update_id<0||!Number.isSafeInteger(actor?.id)||actor.id<=0||actor.is_bot!==false||m?.chat?.id!==CHAT||!['supergroup','group'].includes(m.chat.type)||!Number.isSafeInteger(m.message_id)||m.sender_chat||m.forward_origin||(cb&&(m.from?.id!==BOT||!cb.id)))return new Response('OK');
 const get=async k=>(await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(k)+'&select=payload&limit=1'))?.[0]?.payload;
 if((await get(ROOT+'policy'))?.enabled!==true)return null;
 const member=await deps.telegram('getChatMember',{chat_id:CHAT,user_id:actor.id});
 if(member?.user?.id!==actor.id||member.user.is_bot!==false||!(['creator','administrator','member'].includes(member.status)||(member.status==='restricted'&&member.is_member===true)))return new Response('OK');
 const now=deps.now?deps.now():new Date(),key=ROOT+'delivery:'+update.update_id;
 if(await get(key))return cb?Response.json({method:'answerCallbackQuery',callback_query_id:cb.id}):new Response('OK');
 const view=op==='home'?{text:'Главное меню\nВыберите раздел:',reply_markup:cb?{inline_keyboard:[[{text:'📊 Продажи',callback_data:'cmn1:sales'}],[{text:'📣 Реклама',callback_data:'cmn1:ads'}]]}:mainKeyboard,source_keys:[]}:['sales','dynamic'].includes(op)?await salesView(get,now,op==='dynamic'):await advertisingView(get,op==='ads'?null:op,now);
 const entry={status:'sending',chat_id:CHAT,actor_id:actor.id,input_message_id:m.message_id,update_id:update.update_id,op,source_keys:view.source_keys,started_at:now.toISOString(),wb_writes:0};
 const inserted=await deps.database('telegram_api_cache?on_conflict=cache_key','POST',{cache_key:key,payload:entry,expires_at:'2036-11-11T00:00:00Z'},'resolution=ignore-duplicates,return=representation');
 if(!inserted?.length)return new Response('OK');
 let receipt;
 try{
  receipt=cb&&m.text===view.text&&JSON.stringify(m.reply_markup)===JSON.stringify(view.reply_markup)?m:await deps.telegram(cb?'editMessageText':'sendMessage',{chat_id:CHAT,...(cb?{message_id:m.message_id}:{}),text:view.text,reply_markup:view.reply_markup});
  if(receipt?.chat?.id!==CHAT||receipt?.from?.id!==BOT||!Number.isSafeInteger(receipt.message_id))throw Error('Menu receipt mismatch');
 }catch(error){
  await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(key),'PATCH',{payload:{...entry,status:'uncertain',error:'Telegram menu outcome not verified'}},'return=representation');
  throw error;
 }
 const saved=await deps.database('telegram_api_cache?cache_key=eq.'+encodeURIComponent(key),'PATCH',{payload:{...entry,status:'sent',message_id:receipt.message_id,receipt}},'return=representation');
 if(saved?.length!==1)throw Error('Menu receipt journal unavailable');
 return cb?Response.json({method:'answerCallbackQuery',callback_query_id:cb.id}):new Response('OK');
}
