import {readFile} from 'node:fs/promises';
import {TOOLS,dispatch} from './data.mjs';
export function questionScope(question,history=[]) {
  for(const text of [question,...history.filter(x=>x.role==='user').map(x=>x.content).reverse()]) {
    if(/(?:все[хм]?|кажд\S*)[^.]{0,35}(?:три|тр[её]х|тр[её]м)|(?:три|тр[её]х|тр[её]м)[^.]{0,20}кабинет/iu.test(text))return null;
    const cabinets=[];
    if(/(?:^|[^а-яёa-z])ООО(?:$|[^а-яёa-z])/iu.test(text))cabinets.push('token_1');
    if(/(?:^|[^а-яёa-z])ИП(?:$|[^а-яёa-z])/iu.test(text))cabinets.push('token_2');
    if(/Кита[йяюе]/iu.test(text))cabinets.push('token_3');
    if(cabinets.length)return cabinets;
  }
  return null;
}
export function marketplace(question,history=[]) {
  for(const text of [question,...history.filter(x=>x.role==='user').map(x=>x.content).reverse()]) {
    if(/ozon|озон/iu.test(text))return 'ozon';
    if(/\bWB\b|wildberries|вайлдберриз|ВБ/iu.test(text))return 'wb';
  }
  return 'wb';
}
export function answerHasNumbers(answer) {
  try {
    const parsed=JSON.parse(answer.replace(/^```(?:json)?\s*|\s*```$/g,''));
    const numbers=x=>typeof x==='number'||(x&&typeof x==='object'&&Object.values(x).some(numbers));
    return Boolean(numbers(parsed));
  } catch {return /\d/.test(answer.replace(/\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4}/g,''));}
}
export function outputText(response) {
  return (response.output??[]).filter(x=>x.type==='message').flatMap(x=>x.content??[]).filter(x=>x.type==='output_text').map(x=>x.text).join('\n').trim();
}
export function referenceFor(name,args,result) {
  if(name==='calculate')return null;
  const known={orders:'WB: заказы',sales:'WB: продажи',stocks:'WB: остатки',cards:'WB: карточки',finance:'WB: финансы'};
  const raw=result.source??args.source??'';
  const label=name==='sources'?'Каталог сохранённых источников':name==='costs'?'Собственная себестоимость':name==='economics'?'Сохранённая экономика товаров':name==='ozon'?'Ozon':
    raw.startsWith('mpstats')?'MPStats':raw.startsWith('moysklad')?'МойСклад':known[raw]??'Сохранённая аналитика';
  return {label,cabinet:result.cabinet??args.cabinet??null,from:result.period_from??args.from??null,to:result.period_to??args.to??null,collected:result.collected_at??null,id:result.id??null};
}
export function groundedFooter(answer,evidence) {
  const labels={token_1:'ООО',token_2:'ИП',token_3:'Китай',shared:'общие данные'};
  const substantive=evidence.filter(x=>x.success&&x.reference&&x.name!=='sources'&&x.name!=='snapshots');
  const selected=substantive.length?substantive:evidence.filter(x=>x.success&&x.reference);
  const refs=[...new Set(selected.map(x=>{
    const r=x.reference;
    return [r.label,labels[r.cabinet]??r.cabinet,r.from&&r.to?`${r.from} — ${r.to}`:null,r.collected?`загрузка ${r.collected}`:null].filter(Boolean).join(', ');
  }))].slice(0,6);
  // Model may leave a placeholder or invent a provenance line: replace it with actual tool metadata.
  const text=answer.replace(/\n*Данные:[\s\S]*$/u,'').replace(/\*\*([^*]+)\*\*/g,'$1').trim();
  return text+'\n\nДанные: '+(refs.length?refs.join('; '):'источники не подтверждены')+'.';
}
export async function modelRequest(body,{key,fetcher=fetch}) {
  if(!key) throw new Error('Model credential missing');
  const r=await fetcher('https://api.openai.com/v1/responses',{method:'POST',headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(100000)});
  if(!r.ok) throw new Error('Model HTTP '+r.status); // no secret/raw bodies in logs
  return r.json();
}
export async function runDialog({question,history=[],db,model,request,maxRounds=18}) {
  if(!model || !request) throw new Error('Explicit model and transport required');
  const prompt=await readFile(new URL('./prompt.txt',import.meta.url),'utf8');
  const input=[{role:'developer',content:prompt+'\nТекущее время МСК: '+new Date().toLocaleString('sv-SE',{timeZone:'Europe/Moscow'})},
    ...history.slice(-12).map(x=>({role:x.role==='assistant'?'assistant':'user',content:String(x.content).slice(0,6000)})),
    {role:'user',content:question}];
  const evidence=[];
  const scope=questionScope(question,history);
  const market=marketplace(question,history);
  const allowed=TOOLS.filter(x=>x.name!=='ozon'||market==='ozon');
  const material=new Set(['read_snapshot','count_snapshot','order_snapshot_counts','aggregate_snapshot','economics','costs','ozon']);
  input[0].content+='\nОбласть текущего вопроса: '+JSON.stringify({marketplace:market,cabinets:scope??'all',source_ids:'Use exact IDs from sources. Empty search results are not zeros.'});
  let calls=0;
  const started=Date.now();
  for(let turn=0;turn<maxRounds;turn++) {
    if(Date.now()-started>8*60*1000)throw new Error('Analysis deadline exceeded');
    const response=await request({model,input,tools:allowed,tool_choice:turn===0?{type:'function',name:'sources'}:'auto',parallel_tool_calls:false,max_output_tokens:2400,store:false});
    if(response.status && response.status!=='completed') throw new Error('Model response incomplete');
    const output=response.output??[];
    const tools=output.filter(x=>x.type==='function_call');
    input.push(...output);
    if(!tools.length) {
      const answer=outputText(response);
      if(!answer) throw new Error('Empty answer');
      if(!evidence.some(x=>x.name!=='calculate' && x.success)) throw new Error('Answer has no database evidence');
      if(answerHasNumbers(answer) && /сколько|числ|сумм|заказ|отмен|прибыл|выруч|продаж|остат/iu.test(question) &&
         !evidence.some(x=>x.success&&x.has_data&&material.has(x.name))) {
        input.push({role:'developer',content:'Числовой ответ отклонён: нет прочитанных/подсчитанных фактических строк. Пустой поиск не0. Уточни source через sources и прочитай/подсчитай точный снимок правильного кабинета. При отсутствии факта верни null/неизвестно.'});
        continue;
      }
      return {answer:groundedFooter(answer,evidence),evidence};
    }
    for(const call of tools) {
      if(++calls>16) throw new Error('Tool budget exceeded');
      let args={},result,success=false;
      try {
        args=JSON.parse(call.arguments||'{}');
        if(!allowed.some(x=>x.name===call.name))throw new Error('Marketplace tool forbidden');
        if(scope && ['snapshots','economics','order_snapshot_counts'].includes(call.name) && (!args.cabinet || !scope.includes(args.cabinet))) {
          result={error:'Cabinet scope mismatch',required_cabinets:scope};
        } else {
        result=await dispatch(db,call.name,args);
        }
        if(scope && result.cabinet && result.cabinet!=='shared' && !scope.includes(result.cabinet))result={error:'Snapshot belongs to another cabinet',required_cabinets:scope};
        if(Array.isArray(result.rows)&&result.rows.length===0)result={...result,no_matching_data:true,note:'No matching saved data. Not zero. Check exact source ID via sources, cabinet, dates and pagination.'};
        if(JSON.stringify(result).length>65000) result={too_large:true,hint:'Narrow source, dates, JSON path, page or group filter. Nothing was returned.'};
        success=!result.error && !result.too_large;
      } catch {result={error:'Tool unavailable or invalid arguments; do not infer zero. Narrow request or report the gap.'};}
      // Persistent audit stores metadata, never a second full copy of raw source payloads.
      const hasData=success&&!result.no_matching_data;
      evidence.push({name:call.name,args,success,has_data:hasData,at:new Date().toISOString(),snapshot_id:result.id??null,source:result.source??null,period_from:result.period_from??null,period_to:result.period_to??null,status:result.status??null,has_more:result.has_more??null,reference:hasData?referenceFor(call.name,args,result):null});
      input.push({type:'function_call_output',call_id:call.call_id,output:JSON.stringify(result)});
    }
  }
  throw new Error('Analysis budget exceeded');
}
