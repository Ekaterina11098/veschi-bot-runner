// Owner-authorized live gap collection + same dialogue, no Telegram credential or sends.
import {Database} from './data.mjs';
import {mpstatsReader,currentPeriod,previousPeriod,unverifiedProfitClaim} from './mpstats.mjs';
import {runDialog,modelRequest} from './dialog.mjs';
const db=new Database({url:process.env.SUPABASE_URL,key:process.env.SUPABASE_SECRET_KEY});
const results=[];
const save=async()=>{
 const fresh=(await db.request('owner_agent_setup?id=eq.1&select=payload'))[0];
 await db.request('owner_agent_setup?id=eq.1',{method:'PATCH',body:{payload:{...fresh.payload,mpstats_acceptance:{run_id:process.env.GITHUB_RUN_ID,results,telegram_sends:0,at:new Date().toISOString()}}}});
};
try{
 const yesterday=currentPeriod('вчера');
 const daily=await mpstatsReader(db)({...yesterday,limit:1});
 results.push({id:'yesterday_gap_recovery',pass:daily.rows?.length===3&&daily.rows.every(x=>x.available),refresh:daily.refresh,rows:daily.rows?.map(({products,...r})=>r)});
 await save();
 const question='Сравни ООО, ИП и Китай за последний период, по которому есть сопоставимые данные всех трёх кабинетов. Где ухудшились продажи и прибыль? Укажи даты и какие выводы нельзя сделать из имеющихся данных';
 const result=await runDialog({question,history:[{role:'assistant',content:'За 1–10 октября нет данных по всем трём кабинетам.'}],refreshMpstats:mpstatsReader(db),db,model:process.env.OWNER_AI_MODEL||'gpt-4.1-mini',request:body=>modelRequest(body,{key:process.env.OPENAI_API_KEY})});
 const period=currentPeriod(question);
 const previous=previousPeriod(period);
 const first=result.evidence.find(x=>x.name==='mpstats_products');
 const business=result.evidence.filter(x=>['mpstats_products','read_snapshot','order_snapshot_counts'].includes(x.name));
 const coverageOk=[period,previous].every(p=>['token_1','token_2','token_3'].every(c=>result.evidence.some(x=>x.name==='mpstats_products'&&x.args.from===p.from&&x.args.to===p.to&&x.coverage?.some(r=>r.cabinet===c&&r.available))));
 const pass=Boolean(first?.success&&coverageOk&&[period.from,period.to,previous.from,previous.to].every(d=>result.answer.includes(d))&&!unverifiedProfitClaim(result.answer)&&!business.some(x=>x.name==='order_snapshot_counts'));
 results.push({id:'real_owner_comparison',pass,question,answer:result.answer,evidence:result.evidence});
 await save();
}catch(e){results.push({id:'runtime',pass:false,error:e.message.slice(0,160),evidence:e.evidence});await save();}
console.log(JSON.stringify({checks:results.map(x=>({id:x.id,pass:x.pass})),telegram_sends:0}));
if(results.some(x=>!x.pass))process.exitCode=1;
