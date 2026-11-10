import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {handlePriceButtons} from './china_price_buttons.mjs';
import {handlePriceApproval,reportProposals} from './china_price_approvals.ts';
const CHAT=-1004342917488,BOT=8780468043,token='a'.repeat(24),day='2026-11-10';
const hash=s=>createHash('sha256').update(s).digest('hex');
const report='Повышение · A Продавец: 100 → 110 ¥\nПокупатель: 100 → 110 ₽\n\nСнижение · B Продавец: 130 → 100 ¥\nПокупатель: 130 → 100 ₽';
const config={active:true,chat_id:CHAT,bot_id:BOT};
function setup(){
 const p={status:'active',chat_id:CHAT,bot_id:BOT,report_date:day,expires_at:day+'T23:59:59+03:00',report_job_id:57,report_sha256:hash(report),allowed_modes:['all','up','down']};
 const b={status:'sent',chat_id:CHAT,bot_id:BOT,message_id:61,report_job_id:57,report_sha256:hash(report),report_date:day,expires_at:p.expires_at,receipt_key:'receipt'};
 const db=new Map([['china_agent:price_buttons:v1:'+token,p],['china_agent:price_report_message:v1:61',b],['receipt',{status:'sent',message_id:61,receipt:{chat:{id:CHAT}}}],['china_agent:prices:v1',{cabinet:'token_3',rows:[{nmID:111,vendorCode:'A',currencyIsoCode4217:'CNY',sizes:[{discountedPrice:100,price:200}],discount:50,clubDiscount:0,editableSizePrice:false},{nmID:222,vendorCode:'B',currencyIsoCode4217:'CNY',sizes:[{discountedPrice:130,price:260}],discount:50,clubDiscount:0,editableSizePrice:false}]}]]);
 let saved=report;const launches=[];
 const deps={digest:async s=>hash(s),same:(a,b)=>JSON.stringify(a)===JSON.stringify(b),now:()=>new Date(day+'T09:00:00+03:00'),handlePriceApproval,reportProposals,deferMembership:true,launchPrice:async k=>launches.push(k),telegram:async()=>{throw Error('No Telegram calls in validation');},database:async(path,method='GET',body)=>{
  const q=new URL('https://test/'+path).searchParams;
  if(path.startsWith('business_agent_jobs'))return [{id:57,answer:saved,tool_trace:[{name:'china_price_daily_report',report_date:day},{name:'china_report_delivery',sent_parts:1,message_ids:[61]}]}];
  if(method==='POST'){if(db.has(body.cache_key))return [];db.set(body.cache_key,body.payload);return [body];}
  const k=q.get('cache_key')?.slice(3);return db.has(k)?[{payload:db.get(k)}]:[];
 }};
 const callback=mode=>({id:'callback-'+mode,data:'cpb1:'+token+':'+mode,from:{id:307200273,is_bot:false,first_name:'Pavel'},message:{message_id:61,chat:{id:CHAT,type:'supergroup'},from:{id:BOT,is_bot:true}}});
 return {p,b,db,deps,callback,launches,setAnswer:s=>saved=s};
}
for(const [mode,directions]of [['all',['Повышение','Снижение']],['up',['Повышение']],['down',['Снижение']]]){
 const c=setup();const r=await handlePriceButtons(config,c.callback(mode),91,c.deps);const ack=await r.json();assert.equal(ack.method,'answerCallbackQuery');assert.equal(ack.show_alert,false);
 const approvals=[...c.db.entries()].filter(([k])=>k.startsWith('china_agent:price_recommendation_approval:v2:'));
 assert.equal(approvals.length,1);assert.deepEqual(approvals[0][1].selections.map(s=>s.action).sort(),directions.sort());assert.equal(approvals[0][1].callback_mode,mode);assert.equal(approvals[0][1].actor_user_id,307200273);assert.equal(approvals[0][1].wb_writes,0);
 await handlePriceButtons(config,c.callback(mode),91,c.deps);assert.equal([...c.db.keys()].filter(k=>k.startsWith('china_agent:price_recommendation_approval:v2:')).length,1);
}
for(const mutate of [c=>c.p.status='revoked',c=>c.p.expires_at='2026-11-09T20:00:00Z',c=>c.b.report_sha256='bad',c=>c.b.message_id=62,c=>c.setAnswer(report+'changed'),c=>c.db.delete('receipt'),c=>c.p.allowed_modes=['all']]){
 const c=setup();mutate(c);const r=await handlePriceButtons(config,c.callback('up'),91,c.deps);assert.equal((await r.json()).show_alert,true);assert.equal(c.launches.length,0);
}
for(const mutate of [b=>b.from.is_bot=true,b=>b.message.chat.id=-999,b=>b.message.from.id=99,b=>b.message.forward_origin={}]){
 const c=setup();const cb=c.callback('all');mutate(cb);assert.equal((await(await handlePriceButtons(config,cb,91,c.deps)).json()).show_alert,true);assert.equal(c.launches.length,0);
}
assert.equal(await handlePriceButtons(config,{data:'agent:ask'},91,{}),null);
console.log('Price callback directions, exact sent/hash/expiry binding, actor audit, replay and invalid-message cases passed; zero WB/TG calls');
