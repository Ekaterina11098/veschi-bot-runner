// Synthetic archive + real production model/dialog. No Telegram token or writes to group memory.
import assert from 'node:assert/strict';
import {Database} from './data.mjs';
import {memoryReader,loadMemory} from './memory.mjs';
import {runDialog,modelRequest,leadingJson} from './dialog.mjs';
const db=new Database({url:process.env.SUPABASE_URL,key:process.env.SUPABASE_SECRET_KEY});
const archive=[
 {message_id:1,role:'user',author_role:'owner',content:'Запомни: условное имя кабинета ООО — Север, ИП — Запад, Китай — Восток.',correction:true},
 ...Array.from({length:40},(_,i)=>({message_id:i+2,role:i%2?'assistant':'user',content:'Обсудили упаковку партии номер '+i,correction:false})),
 {message_id:50,role:'user',author_role:'observer',content:'Поправка к условным именам: Север теперь означает ИП, Запад означает ООО. Восток по-прежнему Китай.',correction:true},
 {message_id:51,role:'assistant',content:'Север означает Китай.',correction:false},
 ...Array.from({length:40},(_,i)=>({message_id:i+60,role:i%2?'assistant':'user',content:'Обсудили доставку партии номер '+i,correction:false})),
 {message_id:101,revision:1792400000,role:'user',author_role:'owner',content:'Отредактированное уточнение: кодовое название поставки — Ласточка.',correction:true}
].map((r,i)=>({...r,sender_id:r.role==='user'?12:44,message_at:new Date(Date.UTC(2026,9,1,0,i)).toISOString()}));
let reads=0;
const read=memoryReader({request:async(path,{body})=>{
 assert.equal(path,'rpc/owner_agent_history');reads++;
 const a=body.args,q=(a.query??'').toLowerCase().replaceAll('"','');
 const terms=q.split(/\s+or\s+/).filter(Boolean);
 const rows=archive.filter(r=>(!a.corrections_only||r.correction)&&(!terms.length||terms.some(t=>r.content.toLowerCase().includes(t)))).reverse();
 const offset=a.offset??0,limit=Math.min(30,a.limit??20);
 return {source:'group_history',rows:rows.slice(offset,offset+limit),total:rows.length,has_more:rows.length>offset+limit,next_offset:offset+limit};
}});
const cases=[
 {id:'old_agreement_after_40_messages',question:'Вспомни условное название кабинета Китай, о котором договорились давно. Ответь только JSON {"name":"название"}.',expected:{name:'Восток'}},
 {id:'later_human_correction_beats_assistant',question:'Вспомни, какие кабинеты сейчас называем Север и Запад, с учётом последних человеческих поправок. Ответь только JSON {"north":"кабинет","west":"кабинет"}.',expected:{north:'ИП',west:'ООО'}},
 {id:'edited_message_recall',question:'Какое кодовое название поставки мы уточнили в отредактированном сообщении? Ответь только JSON {"name":"название"}.',expected:{name:'Ласточка'}}
];
const results=[];
for(const item of cases){
 try{
  const memory=await loadMemory(read,item.question);
  const result=await runDialog({question:item.question,history:memory.history,memoryContext:memory.context,readMemory:read,db,model:process.env.OWNER_AI_MODEL||'gpt-4.1-mini',request:body=>modelRequest(body,{key:process.env.OPENAI_API_KEY})});
  const parsed=leadingJson(result.answer);
  results.push({id:item.id,pass:Boolean(parsed&&Object.entries(item.expected).every(([k,v])=>parsed[k]===v)),parsed,tools:result.evidence.map(x=>x.name)});
 }catch(e){results.push({id:item.id,pass:false,error:e.message.slice(0,120)});}
}
const fresh=(await db.request('owner_agent_setup?id=eq.1&select=payload'))[0];
await db.request('owner_agent_setup?id=eq.1',{method:'PATCH',body:{payload:{...fresh.payload,memory_acceptance:{results,reads,synthetic_messages:archive.length,telegram_sends:0,run_id:process.env.GITHUB_RUN_ID,at:new Date().toISOString()}}}});
console.log(JSON.stringify({results,reads,telegram_sends:0}));
if(results.some(x=>!x.pass))process.exitCode=1;
