// Live model/read acceptance only. No Telegram token or sending transport available.
import {Database} from './data.mjs';
import {runDialog,modelRequest,leadingJson} from './dialog.mjs';
const db=new Database({url:process.env.SUPABASE_URL,key:process.env.SUPABASE_SECRET_KEY});
const setup=(await db.request('owner_agent_setup?id=eq.1&select=payload,observed_at'))?.[0];
const fixtures=setup?.payload?.acceptance_fixtures;
if(!fixtures)throw new Error('Independent SQL fixtures missing');
const common=' Для контрольной проверки ответь только JSON без ограждений кода; строку источников добавит программа. ';
const cases=[
 {id:'all_rows',question:'По сохранённому источнику WB orders за 11 сентября — 10 октября 2026 включительно назови число записей заказов в каждом из трёх кабинетов. Считай все строки, включая отменённые, из последнего завершённого снимка ровно за этот период; повторные снимки не складывай.'+common+'Формат {"ooo":число,"ip":число,"china":число}.'},
 {id:'cancel_ip',question:'Теперь только ИП: сколько из этих записей отменено (isCancel=true)? Период тот же.'+common+'Формат {"cabinet":"ИП","count":число}.'},
 {id:'cancel_china',question:'А для Китая?'+common+'Формат {"cabinet":"Китай","count":число}. Сохрани показатель и период предыдущего вопроса.'},
 {id:'cancel_ooo',question:'Теперь аналогично для ООО.'+common+'Формат {"cabinet":"ООО","count":число}.'},
 {id:'remaining_ooo',question:'Сколько тогда осталось неотменённых в последнем кабинете за тот же период?'+common+'Формат {"cabinet":"название","count":число}.'},
 {id:'unknown_profit',question:'Какова точная подтверждённая чистая прибыль за сегодняшний завершённый день 19 октября 2026 по всем трём кабинетам? Не строй прогноз. Если день не завершён или нет полного факта, ставь null, не ноль.'+common+'Формат {"ooo":число_или_null,"ip":число_или_null,"china":число_или_null}.'},
 {id:'mpstats_coverage',question:'До какой последней даты есть завершённые рекламные отчёты MPStats (источник mpstats_campaign_report) по каждому из трёх кабинетов? Нужна дата периода period_to, а не collected_at. Не используй дату одного кабинета для другого.'+common+'Формат {"ooo":"YYYY-MM-DD","ip":"YYYY-MM-DD","china":"YYYY-MM-DD"}.'}
];
const results=[],history=[];
for(const item of fixtures.additional_cases??[])cases.push({id:item.id,question:item.question+common});
const request=body=>modelRequest(body,{key:process.env.OPENAI_API_KEY});
async function save() {
 const fresh=(await db.request('owner_agent_setup?id=eq.1&select=payload,observed_at'))?.[0];
 const past=fresh.payload.acceptance;
 const history=[...(fresh.payload.acceptance_history??[])];
 if(past?.run_id && past.run_id!==process.env.GITHUB_RUN_ID && !history.some(x=>x.run_id===past.run_id))history.push(past);
 await db.request('owner_agent_setup?id=eq.1',{method:'PATCH',body:{payload:{...fresh.payload,acceptance_history:history.slice(-5),acceptance:{run_id:process.env.GITHUB_RUN_ID,model:process.env.OWNER_AI_MODEL||'gpt-4.1-mini',results,finished:results.length===cases.length,telegram_sends:0,at:new Date().toISOString()}}}});
}
for(const item of cases) {
 let result={id:item.id,question:item.question,pass:false};
 try {
  const value=await runDialog({question:item.question,history,db,model:process.env.OWNER_AI_MODEL||'gpt-4.1-mini',request});
  const raw=value.answer.split(/\n\nДанные:/)[0].replace(/^```(?:json)?\s*|\s*```$/g,'').trim();
  const parsed=leadingJson(raw);
  const expected=fixtures[item.id];
  const exact=parsed && Object.keys(expected).every(k=>parsed[k]===expected[k]);
  const scopedReads=value.evidence.filter(x=>['read_snapshot','aggregate_snapshot','economics'].includes(x.name));
  const expectedScope={cancel_ip:'token_2',cancel_china:'token_3',cancel_ooo:'token_1',remaining_ooo:'token_1'}[item.id];
  const scopeOk=!expectedScope || scopedReads.every(x=>!x.reference?.cabinet || x.reference.cabinet===expectedScope);
  result={...result,pass:Boolean(exact&&scopeOk),numeric_match:Boolean(exact),scope_ok:scopeOk,parsed,answer:value.answer,evidence:value.evidence};
  history.push({role:'user',content:item.question},{role:'assistant',content:value.answer});
 }catch(error){result.error=error?.message?.replace(/https?:\/\/\S+/g,'[url]').slice(0,160)??'unknown';if(error.evidence)result.evidence=error.evidence;}
 results.push(result);await save();
 console.log(JSON.stringify({case:item.id,pass:result.pass,tool_calls:result.evidence?.length??0}));
}
console.log(JSON.stringify({passed:results.filter(x=>x.pass).length,total:results.length,telegram_sends:0}));
if(results.some(x=>!x.pass))process.exitCode=1;
