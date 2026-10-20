// Replay the actual owner question privately; no Telegram credential or delivery transport.
import {Database} from './data.mjs';
import {runDialog,modelRequest} from './dialog.mjs';
import {mpstatsReader} from './mpstats.mjs';
import {recommendationPeriod} from './recommendations.mjs';
const db=new Database({url:process.env.SUPABASE_URL,key:process.env.SUPABASE_SECRET_KEY});
const jobs=await db.request('owner_agent_jobs?order=id.asc&select=id,request_text,answer&limit=200');
const target=[...jobs].reverse().find(x=>/Предложи что нужно сделать конкретно/iu.test(x.request_text));
if(!target)throw new Error('Actual owner acceptance question missing');
const history=jobs.filter(x=>x.id<target.id).flatMap(x=>[{role:'user',content:x.request_text},...(x.answer?[{role:'assistant',content:x.answer}]:[])]);
const results=[];
async function save(){
 const fresh=(await db.request('owner_agent_setup?id=eq.1&select=payload'))[0];
 await db.request('owner_agent_setup?id=eq.1',{method:'PATCH',body:{payload:{...fresh.payload,recommendation_acceptance:{run_id:process.env.GITHUB_RUN_ID,results,telegram_sends:0,at:new Date().toISOString()}}}});
}
const request=body=>modelRequest(body,{key:process.env.OPENAI_API_KEY});
for(const item of [{id:'actual_owner_concrete_actions',question:target.request_text},{id:'same_month_lag_china_followup',question:'А для Китая?'}]){
 try{
  const expected=recommendationPeriod(item.question,history);
  const result=await runDialog({question:item.question,history,db,refreshMpstats:mpstatsReader(db),model:process.env.OWNER_AI_MODEL||'gpt-4.1-mini',request});
  const candidates=result.evidence.find(x=>x.name==='product_candidates');
  const structured=result.evidence.find(x=>x.name==='structured_recommendation_selection');
  const samePeriod=result.evidence.filter(x=>x.name==='mpstats_products')[0]?.args;
  const scopeOk=item.id!=='same_month_lag_china_followup'||candidates?.coverage?.every(x=>x.cabinet==='token_3');
  const pass=Boolean(candidates?.scanned_records>20&&structured?.success&&samePeriod.from===expected.from&&samePeriod.to===expected.to&&scopeOk&&result.answer.includes('nmID')&&result.answer.includes('Проверка результата:')&&!result.answer.includes('Если хотите'));
  results.push({id:item.id,pass,expected_period:expected,question:item.question,answer:result.answer,evidence:result.evidence});
  history.push({role:'user',content:item.question},{role:'assistant',content:result.answer});
 }catch(e){results.push({id:item.id,pass:false,error:e.message.slice(0,140)});}
 await save();console.log(JSON.stringify({case:item.id,pass:results.at(-1).pass}));
}
if(results.some(x=>!x.pass))process.exitCode=1;

