import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {Database,calculate,dispatch,TOOLS} from './data.mjs';
import {runDialog} from './dialog.mjs';
import {validMessage,handle} from './ingress.mjs';
import {processJob,splitText} from './worker.mjs';

const config={active:true,chat_id:-1001,bot_id:44,bot_username:'veschi_owner_ai_bot'};
const members=[{user_id:12,role:'owner',active:true},{user_id:13,role:'observer',active:true}];
const update={update_id:9,message:{message_id:21,chat:{id:-1001,type:'supergroup'},from:{id:12,is_bot:false},text:'Где снизилась прибыль?'}};
test('plain questions accepted for owner and observer; strangers and other groups denied',()=>{
  assert.equal(validMessage(update,config,members),true);
  for(const id of [13,99])assert.equal(validMessage({...update,message:{...update.message,from:{id}}},config,members),id===13);
  assert.equal(validMessage(update,{...config,chat_id:-2000},members),false);
  assert.equal(validMessage(update,{...config,active:false},members),false);
  assert.equal(validMessage({...update,message:{...update.message,from:{id:12,is_bot:true}}},config,members),false);
  assert.equal(validMessage({...update,message:{...update.message,sender_chat:{id:-1001}}},config,members),false);
});
test('invalid, edited, anonymous and huge messages do not enter queue',()=>{
  assert.equal(validMessage({...update,message:{...update.message,text:'/confirm anything'}},config,members),false);
  assert.equal(validMessage({...update,update_id:-1},config,members),false);
  assert.equal(validMessage({...update,message:undefined},config,members),false);
  assert.equal(validMessage({...update,message:{...update.message,text:'a'.repeat(4001)}},config,members),false);
});
test('unauthenticated webhook never touches database',async()=>{
  const r=await handle(new Request('https://example.test',{method:'POST',body:'{}'}),{secret:'abc',db:{request(){throw new Error('must not read');}}});
  assert.equal(r.status,401);
});
test('only fixed database endpoints, never an operational agent queue',async()=>{
  const db=new Database({url:'https://example.supabase.co',key:'sb_secret_test',fetcher:async(url,init)=>{
    assert.ok(url.endsWith('/rpc/owner_agent_read'));assert.equal(init.headers.Authorization,undefined);
    return Response.json({rows:[]});
  }});
  await db.read('sources',{});
  await assert.rejects(db.request('advertising_agent_jobs',{method:'PATCH',body:{status:'pending'}}),/forbidden/);
  await assert.rejects(dispatch(db,'execute_sql',{sql:'delete from anything'}),/forbidden/);
});
test('finite arithmetic, zero baseline and unknown handling',()=>{
  assert.equal(calculate({operation:'subtract',values:[1000,200,150]}).result,650);
  assert.equal(calculate({operation:'change_pct',values:[100,80]}).result.toFixed(2),'-20.00');
  for(const values of [[null],[Infinity],[]])assert.throws(()=>calculate({operation:'sum',values}));
  assert.throws(()=>calculate({operation:'divide',values:[1,0]}));
});
test('successful empty PostgREST insert response is accepted',async()=>{
  const db=new Database({url:'https://example.supabase.co',key:'test',fetcher:async()=>new Response(null,{status:201})});
  assert.equal(await db.request('owner_agent_setup',{method:'POST',body:{id:1}}),null);
});
test('no execution tools exposed to model',()=>{
  assert.deepEqual(TOOLS.map(x=>x.name),['sources','snapshots','read_snapshot','aggregate_snapshot','economics','costs','ozon','calculate']);
});
test('model chooses reads, receives evidence, keeps followup context',async()=>{
  const bodies=[];
  const responses=[{output:[{type:'function_call',name:'sources',arguments:'{}',call_id:'c1'}]},
    {output:[{type:'message',content:[{type:'output_text',text:'Есть три кабинета. Данные: проверенный каталог.'}]}]}];
  const result=await runDialog({question:'А по всем кабинетам?',history:[{role:'user',content:'Какие источники есть?'}],db:{read:async()=>({rows:[{cabinet:'token_1'}]})},model:'test',request:async body=>{bodies.push(structuredClone(body));return responses.shift();}});
  assert.equal(result.evidence[0].success,true);
  assert.equal(bodies[0].store,false);assert.equal(bodies[0].tool_choice,'required');
  assert.ok(bodies[1].input.some(x=>x.type==='function_call_output'));
  assert.ok(bodies[0].input.some(x=>x.content==='Какие источники есть?'));
});
test('ungrounded model answer and exhausted loop fail closed',async()=>{
  await assert.rejects(runDialog({question:'Прибыль?',db:{},model:'test',request:async()=>({output:[{type:'message',content:[{type:'output_text',text:'Миллион'}]}]})}),/no database evidence/);
  await assert.rejects(runDialog({question:'test',db:{},model:'test',maxRounds:1,request:async()=>({output:[{type:'function_call',name:'delete',arguments:'{}',call_id:'c'}]})}),/budget/);
});
function fakeDatabase() {
  const job={id:1,update_id:9,status:'pending',chat_id:-1001,sender_id:12,message_id:21,request_text:'Вопрос',delivery:{}};
  let queries=[];
  return {job,queries,async request(path,opts={}) {
    queries.push({path,opts});
    if(path.startsWith('owner_agent_config'))return [{...config}];
    if(path.startsWith('owner_agent_members'))return members;
    if(path.startsWith('owner_agent_jobs?chat_id='))return [];
    if(path.startsWith('owner_agent_jobs?')){
      if(opts.method==='PATCH'){
        if(path.includes('status=eq.pending')&&job.status!=='pending')return [];
        if(path.includes('status=eq.running')&&(job.status!=='running'||!path.endsWith(job.lease_token)))return [];
        Object.assign(job,structuredClone(opts.body));return [structuredClone(job)];
      }
      return [structuredClone(job)];
    }
    throw new Error('Unexpected path');
  }};
}
const dialog=async()=>({answer:'Подтверждённый ответ',evidence:[{name:'sources',success:true}]});
test('duplicate dispatch cannot produce duplicate sends',async()=>{
  const db=fakeDatabase();let sends=0;
  const send=async(token,method)=>method==='getMe'?{id:44,username:'veschi_owner_ai_bot'}:(sends++,{message_id:31,chat:{id:-1001}});
  const first=await processJob(1,{db,token:'test',model:'test',send,dialog});
  const second=await processJob(1,{db,token:'test',model:'test',send,dialog});
  assert.equal(first.status,'done');assert.equal(second.status,'already_claimed');assert.equal(sends,1);
});
test('unknown Telegram outcome persisted before send and never retried',async()=>{
  const db=fakeDatabase();let sends=0;
  const send=async(token,method)=>{
    if(method==='getMe')return {id:44,username:'veschi_owner_ai_bot'};
    assert.equal(db.job.delivery.state,'uncertain');sends++;throw new Error('timeout after send');
  };
  assert.equal((await processJob(1,{db,token:'test',model:'test',send,dialog})).status,'uncertain');
  await processJob(1,{db,token:'test',model:'test',send,dialog});assert.equal(sends,1);
});
test('wrong token identity blocks model call and delivery',async()=>{
  const db=fakeDatabase();
  const result=await processJob(1,{db,token:'test',send:async()=>({id:99,username:'other_bot'}),dialog:async()=>{throw new Error('must not call');}});
  assert.equal(result.status,'failed');assert.equal(db.job.answer,undefined);
});
test('Unicode messages split without damaged surrogate pairs',()=>{
  const text='😀'.repeat(5000)+' текст';const parts=splitText(text);
  assert.equal(parts.join(''),text);assert.equal(Array.from(parts[0]).length,3500);
});
test('SQL is additive, invoker-only and denies anonymous API access',async()=>{
  const sql=await readFile(new URL('./schema.sql',import.meta.url),'utf8');
  assert.ok(sql.includes('security invoker'));
  assert.ok(sql.includes('from public,anon,authenticated'));
  assert.ok(!/security definer|drop table|alter table public\.(?!owner_agent_)/i.test(sql));
  assert.ok(!/\bexecute\s+(format|query|sql)/i.test(sql));
});
