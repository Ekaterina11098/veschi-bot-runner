import assert from 'node:assert/strict';
import {advertisingView,handleMainMenu,ROOT}from './china_main_menu.mjs';
import {handleReportButtons}from './china_report_buttons.mjs';
const CHAT=-1004342917488,BOT=8780468043,TOKEN='a'.repeat(24),NOW=new Date('2026-11-11T10:00:00Z');
function fixture(family='drr'){
 const c=new Map(),calls=[],messages=new Map();let next=500;
 const actual=family==='budgets'?[{id:'fund',kind:'topup_campaign',campaign_id:1,amount_cny:100}]:[{id:'raise',kind:'ad_set_bid',campaign_id:1,old_minor:28,target_minor:30,article:'A'}];
 const p={plan_id:'p',plan_sha256:'hash',family,report_generation:'g',validity_mode:'until_replaced',expires_at:'2099-01-01T00:00:00Z',items:actual,report_message_ids:[10]};
 const original={message_id:10,chat:{id:CHAT,type:'supergroup'},from:{id:BOT,is_bot:true},date:1794380000,photo:[{file_id:'saved-photo'}]};
 c.set(ROOT+'policy',{enabled:true});c.set('china_agent:report_buttons:v1:policy',{enabled:true});c.set('china_agent:loss_plan:v1:p',p);
 c.set('china_agent:daily_ad_current_report:v1:'+family,{plan_id:'p',report_generation:'g'});
 c.set(ROOT+'report:'+family,{status:'sent',family,chat_id:CHAT,bot_id:BOT,plan_id:'p',plan_sha256:'hash',message_id:10,message_ids:[10],report_day:'2026-11-11',receipt:original});
 const b={status:'sent',token:TOKEN,plan_id:'p',plan_sha256:'hash',family,chat_id:CHAT,bot_id:BOT,message_id:10,receipt:original};
 c.set('china_agent:report_buttons:v1:message:10',b);
 c.set('china_agent:report_buttons:v1:plan:'+TOKEN,{status:'active',token:TOKEN,plan_id:'p',plan_sha256:'hash',family,chat_id:CHAT,bot_id:BOT,items:actual.map(i=>({...i,group:family==='budgets'?'budget':'up',amount_cny:i.amount_cny||0}))});
 const get=async k=>structuredClone(c.get(k));
 const deps={now:()=>NOW,launch:()=>{throw Error('Navigation must not launch')},telegram:async(method,body)=>{
 calls.push({method,body});if(method==='getChatMember')return{user:{id:body.user_id,is_bot:false},status:'member'};
 assert.ok(['sendMessage','editMessageText','sendPhoto','editMessageMedia','editMessageReplyMarkup'].includes(method));
 if(method==='editMessageReplyMarkup')return true;
 const mid=body.message_id||next++,m={message_id:mid,chat:{id:CHAT,type:'supergroup'},from:{id:BOT,is_bot:true},date:1794389000,reply_markup:body.reply_markup,...(method==='sendPhoto'||method==='editMessageMedia'?{caption:body.media?.caption||body.caption,photo:[{file_id:body.media?.media||body.photo}]}:{text:body.text})};messages.set(mid,m);return m;
 },database:async(path,method='GET',body,prefer)=>{
 const [table,q]=path.split('?');assert.equal(table,'telegram_api_cache','No jobs or marketplace writes allowed');
 const args=new URLSearchParams(q);if(method==='POST'){if(c.has(body.cache_key)&&!prefer?.includes('merge-duplicates'))return[];c.set(body.cache_key,structuredClone(body.payload));return[body];}
 const k=args.get('cache_key').slice(3);if(method==='GET')return c.has(k)?[{payload:await get(k)}]:[];
 assert.equal(method,'PATCH');if(!c.has(k))return[];const cond=args.get('payload');if(cond&&JSON.stringify(c.get(k))!==cond.slice(3))return[];c.set(k,structuredClone(body.payload));return[body];
 }};
 const config={active:true,chat_id:CHAT,bot_id:BOT},m={message_id:88,chat:{id:CHAT,type:'supergroup'},from:{id:BOT,is_bot:true},text:'Рекламные кампании'};
 const update={update_id:1,callback_query:{id:'open',data:'cmn1:'+family,from:{id:7,is_bot:false},message:m}};
 return{c,calls,get,deps,config,update,messages,p,original};
}
{
 const w=fixture();const v=await advertisingView(w.get,'drr',NOW,7);assert.equal(v.photos[0].photo,'saved-photo');assert.equal(v.direct.mode,'active');assert.match(v.reply_markup.inline_keyboard[0][0].callback_data,/gup$/);assert.ok(!v.reply_markup.inline_keyboard.flat().some(b=>b.text==='Открыть отчёт'));
 await handleMainMenu(w.config,w.update,w.deps);assert.equal(w.calls.find(x=>x.method==='editMessageMedia').body.message_id,88);assert.equal(w.c.get('china_agent:report_buttons:v1:message:88').token,TOKEN);assert.ok(w.c.get('china_agent:loss_plan:v1:p').report_message_ids.includes(88));
 await handleMainMenu(w.config,w.update,w.deps);assert.equal(w.calls.filter(x=>x.method==='editMessageMedia').length,1);
 const shown=w.messages.get(88),cb={id:'select',data:'cab1:'+TOKEN+':gup',from:{id:7,is_bot:false},message:shown};
 await handleReportButtons(w.config,cb,2,w.deps);assert.deepEqual(w.c.get('china_agent:report_buttons:v1:selection:'+TOKEN+':7').selected_ids,['raise']);
 assert.equal([...w.c.keys()].some(k=>k.startsWith('china_agent:report_buttons:v1:confirmation:')),false);
}
{
 const w=fixture('budgets');const v=await advertisingView(w.get,'budgets',NOW,7);assert.match(v.reply_markup.inline_keyboard[0][0].text,/\+100 CNY/);await handleMainMenu(w.config,w.update,w.deps);assert.equal(w.c.get('china_agent:report_buttons:v1:message:88').family,'budgets');
}
{
 const w=fixture();w.c.set('china_agent:daily_ad_execution:v2:p',{status:'done',items:[{status:'verified'}]});w.c.set('china_agent:daily_ad_result:v2:p',{status:'sent',chat_id:CHAT,message_id:77,receipt:{message_id:77,chat:{id:CHAT}}});
 const v=await advertisingView(w.get,'drr',NOW);assert.equal(v.direct.mode,'complete');assert.match(v.text,/выполнены и проверены/);assert.equal(v.reply_markup.inline_keyboard.flat().some(b=>b.callback_data?.startsWith('cab1:')),false);
 await handleMainMenu(w.config,w.update,w.deps);assert.equal(w.c.has('china_agent:daily_ad_message:v2:88'),false);
 await handleMainMenu(w.config,{update_id:3,message:{message_id:89,chat:{id:CHAT,type:'supergroup'},from:{id:7,is_bot:false},text:'Сделай всё',reply_to_message:w.messages.get(88)}},w.deps);
 assert.match(w.calls.at(-1).body.text,/Повторное подтверждение не принято/);
 const photo=w.messages.get(88);await handleMainMenu(w.config,{update_id:4,callback_query:{id:'back',data:'cmn1:ads',from:{id:7,is_bot:false},message:photo}},w.deps);assert.ok(w.calls.some(x=>x.method==='sendMessage'&&x.body.text.startsWith('Реклама')));assert.equal(w.calls.at(-1).method,'editMessageReplyMarkup');
}
{
 const w=fixture();w.c.set('china_agent:daily_ad_execution:v2:p',{status:'uncertain',items:[]});const v=await advertisingView(w.get,'drr',NOW);assert.equal(v.direct.mode,'processed');assert.equal(v.reply_markup.inline_keyboard.flat().some(b=>b.callback_data?.startsWith('cab1:')),false);
 w.p.invalidated_at=NOW.toISOString();w.c.set('china_agent:loss_plan:v1:p',w.p);assert.equal((await advertisingView(w.get,'drr',NOW)).photos,undefined);
}
{
 const w=fixture(),p2={...w.p,plan_id:'p2',plan_sha256:'hash2',report_message_ids:[11]},r2={...w.original,message_id:11,photo:[{file_id:'second-page'}]};
 w.c.set('china_agent:loss_plan:v1:p2',p2);w.c.set('china_agent:daily_ad_current_report:v1:drr',{plan_id:'p2',report_generation:'g'});
 const index=w.c.get(ROOT+'report:drr');index.plan_id='p2';index.plan_sha256='hash2';index.message_id=11;index.receipt=r2;index.message_ids=[10,11];index.pages=[{plan_id:'p',plan_sha256:'hash',message_id:10,receipt:w.original},{plan_id:'p2',plan_sha256:'hash2',message_id:11,receipt:r2}];
 w.c.set('china_agent:report_buttons:v1:message:11',{...w.c.get('china_agent:report_buttons:v1:message:10'),token:'b'.repeat(24),plan_id:'p2',plan_sha256:'hash2',message_id:11,receipt:r2});
 w.c.set('china_agent:report_buttons:v1:plan:'+'b'.repeat(24),{...w.c.get('china_agent:report_buttons:v1:plan:'+TOKEN),token:'b'.repeat(24),plan_id:'p2',plan_sha256:'hash2'});
 const v=await advertisingView(w.get,'drr',NOW);assert.equal(v.photos.length,2);
 await handleMainMenu(w.config,w.update,w.deps);assert.equal(w.c.get('china_agent:report_buttons:v1:message:88').plan_id,'p');assert.equal(w.c.get('china_agent:report_buttons:v1:message:500').plan_id,'p2');
}
console.log('PASS direct PNG no link screen; bound active selection no execution; exact budgets; completed/uncertain no action revival; duplicate navigation; photo back path; multi-page generation retains exact per-page plans.');
