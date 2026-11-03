import test from 'node:test';
import assert from 'node:assert/strict';
import {route,THREAD} from './codex-route.mjs';
import {acceptCodex} from './codex-inbox.mjs';
const p={enabled:true,chat_id:-1004342917488,bot_id:8780468043,thread_id:THREAD,allowed_sender_ids:[5122667182,307200273],expires_at:'2100-01-01T00:00:00Z'};
const m={chat:{id:p.chat_id},from:{id:307200273},message_id:700};
test('Legacy address migrates to cloud only after cutover',()=>{
 assert.equal(route('Агент, какой расход?',p,m).kind,'legacy_explicit');
 assert.deepEqual(route('Агент, какой расход?',{...p,legacy_analysis_enabled:false},m),{kind:'codex',text:'какой расход?'});
});
test('Expired cloud route never falls back to old analyst',()=>{
 assert.equal(route('Агент, вопрос',{...p,legacy_analysis_enabled:false,expires_at:'2000-01-01T00:00:00Z'},m).kind,'expired');
});
test('Actual reply confirmation reaches existing bound-plan verifier, no cloud job is fabricated',async()=>{
 const config={chat_id:p.chat_id,bot_id:p.bot_id};
 const db=async()=>[{payload:{...p,legacy_analysis_enabled:false}}];
 const v=await acceptCodex(config,{...m,reply_to_message:{message_id:665,from:{id:p.bot_id}}},'Сделай всё',123,db);
 assert.equal(v.execution_only,true);assert.equal(v.legacy_text,'Сделай всё');
});
test('A read request mentioning make does not bypass cloud as an execution',async()=>{
 const config={chat_id:p.chat_id,bot_id:p.bot_id};
 let posted=false;
 const db=async(path,method,body)=>{
  if(path.includes('policy'))return [{payload:{...p,legacy_analysis_enabled:false}}];
  if(method==='POST'&&path.startsWith('business_agent_jobs')){posted=true;return [{id:9,status:'pending',tool_trace:body.tool_trace}];}
  if(path.includes('select=payload'))return [{payload:{job_id:9,input_message_id:700,thread_id:THREAD,chat_id:p.chat_id}}];
  return [];
 };
 await acceptCodex(config,{...m,reply_to_message:{message_id:665,from:{id:p.bot_id}}},'Сделай таблицу расходов',124,db);
 assert.equal(posted,true);
});
