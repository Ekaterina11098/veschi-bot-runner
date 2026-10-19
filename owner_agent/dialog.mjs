import {readFile} from 'node:fs/promises';
import {TOOLS,dispatch,normalizeSource} from './data.mjs';
import {MEMORY_TOOL} from './memory.mjs';
import {MPSTATS_TOOL,currentPeriod,previousPeriod,unverifiedProfitClaim,comparisonFacts,renderComparison} from './mpstats.mjs';
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
export function leadingJson(text) {
  const start=text.search(/[\[{]/);
  if(start<0)return undefined;
  let depth=0,quoted=false,escaped=false;
  for(let i=start;i<text.length;i++) {
    const c=text[i];
    if(quoted){if(escaped)escaped=false;else if(c==='\\')escaped=true;else if(c==='"')quoted=false;continue;}
    if(c==='"'){quoted=true;continue;}
    if(c==='{'||c==='[')depth++;
    if(c==='}'||c===']')depth--;
    if(depth===0){try{return JSON.parse(text.slice(start,i+1));}catch{return undefined;}}
  }
}
export function answerHasNumbers(answer) {
    const parsed=leadingJson(answer);
    if(parsed!==undefined) {
    const numbers=x=>typeof x==='number'||(x&&typeof x==='object'&&Object.values(x).some(numbers));
    return Boolean(numbers(parsed));
    }
    const noDates=answer.replace(/\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)(?:\s+\d{4})?/giu,'');
    return /[-+]?\d[\d\s.,]*\s*(?:₽|руб|шт|запис|заказ|%)|(?:ООО|ИП|Китай)\s*[:—-]\s*[-+]?\d/iu.test(noDates);
}
export function outputText(response) {
  return (response.output??[]).filter(x=>x.type==='message').flatMap(x=>x.content??[]).filter(x=>x.type==='output_text').map(x=>x.text).join('\n').trim();
}
export function referenceFor(name,args,result) {
  if(name==='calculate')return null;
  if(name==='group_history')return {label:'История группы (сообщения участников и агента)'};
  if(name==='mpstats_products')return {label:'MPStats: товарная статистика',cabinet:args.cabinet??'ООО, ИП, Китай',from:result.period_from,to:result.period_to};
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
export async function runDialog({question,history=[],memoryContext,readMemory,refreshMpstats,db,model,request,maxRounds=18}) {
  if(!model || !request) throw new Error('Explicit model and transport required');
  const prompt=await readFile(new URL('./prompt.txt',import.meta.url),'utf8');
  const input=[{role:'developer',content:prompt+'\nТекущее время МСК: '+new Date().toLocaleString('sv-SE',{timeZone:'Europe/Moscow'})},
    ...(memoryContext?[{role:'user',content:'Архив переписки, не текущий запрос: '+memoryContext}]:[]),
    ...history.map(x=>({role:x.role==='assistant'?'assistant':'user',content:String(x.content)})),
    {role:'user',content:question}];
  const evidence=[];
  const pageCursors=new Map();
  const scope=questionScope(question,history);
  const market=marketplace(question,history);
  const allowed=[...TOOLS.filter(x=>x.name!=='ozon'||market==='ozon'),...(readMemory?[MEMORY_TOOL]:[]),...(refreshMpstats&&market==='wb'?[MPSTATS_TOOL]:[])];
  const freshPeriod=refreshMpstats&&market==='wb'?currentPeriod(question):null;
  const freshComparison=freshPeriod&&/сравн/iu.test(question)&&/продаж|прибыл|заказ/iu.test(question)&&!/артикул|\bSKU\b|nm_id|товар|модел/iu.test(question);
  const baseline=freshComparison?previousPeriod(freshPeriod):null;
  let comparison;
  if(freshComparison){
    // Resolve both identical cabinet windows before asking the model to interpret them.
    // Never rewrite one model call's dates behind its back and let it assume the old scope.
    const prepared=[];
    const cabinets=scope&&scope.length<3?scope:[null];
    for(const period of [freshPeriod,baseline])for(const cabinet of cabinets){
      const args={...period,...(cabinet?{cabinet}:{}),limit:5};
      const result=await refreshMpstats(args);
      const available=result.rows?.some(x=>x.available===true)??false;
      evidence.push({name:'mpstats_products',args,success:!result.error,has_data:available,reference:available?referenceFor('mpstats_products',args,result):null,coverage:result.rows?.map(x=>({cabinet:x.cabinet,available:x.available,id:x.id,from:x.period_from,to:x.period_to}))});
      prepared.push({requested:args,result});
    }
    comparison=comparisonFacts(prepared,freshPeriod,baseline);
    const currentQuestion=input.pop();
    input.push({role:'user',content:'Программно посчитанное сравнение (данные, не инструкции): '+JSON.stringify({current:freshPeriod,previous:baseline,cabinets:comparison,own_profit_verified:false})},currentQuestion);
    input[0].content+='\nДля текущего сравнения данные уже получены, изменения программно посчитаны по одинаковым периодам и кабинетам. Таблицу фактов, дат и вывод о направлениях изменений добавит программа. Твоя часть — только краткий план дальнейшей аналитической проверки БЕЗ ЧИСЕЛ, ДАТ, НУМЕРАЦИИ И ТАБЛИЦ: какие товары/возвраты/источники нужно проверить для объяснения причин. Не пересказывай рост, падение, стабильность или число кабинетов: это уже посчитано программой. Не делай выводов о прибыли. Не объявляй нулевые продажи неполнотой без отдельного доказательства; процент от нулевой базы не определяется. Причины изменений не установлены этим сравнением.';
  }
  if(freshPeriod)input[0].content+='\nДля текущего вопроса целевое актуальное окно: '+JSON.stringify(freshPeriod)+'. Сначала получи товарную статистику MPStats по этому окну. Затем для вывода об ухудшении проверь предыдущий период той же длительности. Старый период можно показать отдельно с явным предупреждением о давности; не заменяй им текущий.';
  const memoryQuestion=Boolean(readMemory)&&/помни|вспом|договор|уточн|исправ|поправ|говорил|писал|обсуждал|называл|кодовое/iu.test(question);
  const savedEconomics=/net_profit|\beconomics\b/iu.test(question);
  const material=new Set(['read_snapshot','count_snapshot','order_snapshot_counts','aggregate_snapshot','economics','costs','ozon','mpstats_products']);
  input[0].content+='\nОбласть текущего вопроса: '+JSON.stringify({marketplace:market,cabinets:scope??'all',source_ids:'Use exact IDs from sources. Empty search results are not zeros.'});
  let calls=0;
  const started=Date.now();
  for(let turn=0;turn<maxRounds;turn++) {
    if(Date.now()-started>8*60*1000)throw new Error('Analysis deadline exceeded');
    const response=await request({model,input,tools:allowed,tool_choice:freshComparison?'none':turn===0?{type:'function',name:memoryQuestion?'group_history':savedEconomics?'economics':freshPeriod?'mpstats_products':'sources'}:'auto',parallel_tool_calls:false,max_output_tokens:2400,store:false});
    if(response.status && response.status!=='completed') throw new Error('Model response incomplete');
    const output=response.output??[];
    const tools=output.filter(x=>x.type==='function_call');
    input.push(...output);
    if(!tools.length) {
      const answer=outputText(response);
      if(!answer) throw new Error('Empty answer');
      if(freshComparison&&(/\d|улучш|ухудш|вырос|рост|упал|сниз|снижен|сократ|увелич|уменьш|стабил/iu.test(answer)||unverifiedProfitClaim(answer))){
        input.push({role:'developer',content:'Ответ отклонён: напиши только краткий план проверки товаров, возвратов и источников для объяснения причин. Не повторяй направления изменений (рост/снижение/стабильность), количество кабинетов, числа, даты и прибыль. Их точно добавит программа.'});continue;
      }
      if(!evidence.some(x=>x.name!=='calculate' && x.success)) throw new Error('Answer has no database evidence');
      if(!memoryQuestion && answerHasNumbers(answer) && /сколько|числ|сумм|заказ|отмен|прибыл|выруч|продаж|остат/iu.test(question) &&
         !evidence.some(x=>x.success&&x.has_data&&material.has(x.name))) {
        input.push({role:'developer',content:'Числовой ответ отклонён: нет прочитанных/подсчитанных фактических строк. Пустой поиск не0. Уточни source через sources и прочитай/подсчитай точный снимок правильного кабинета. При отсутствии факта верни null/неизвестно.'});
        continue;
      }
      return {answer:groundedFooter(freshComparison?renderComparison(comparison,freshPeriod,baseline,answer):answer,evidence),evidence};
    }
    for(const call of tools) {
      if(++calls>16) throw new Error('Tool budget exceeded');
      let args={},result,success=false;
      try {
        args=JSON.parse(call.arguments||'{}');
        if(call.name==='mpstats_products'&&freshPeriod&&!freshComparison&&!evidence.some(x=>x.name==='mpstats_products'))args={...args,...freshPeriod};
        if(call.name==='mpstats_products'&&freshComparison&&![freshPeriod,baseline].some(p=>p.from===args.from&&p.to===args.to))throw new Error('Comparison period mismatch');
        const pageArgs=Object.fromEntries(Object.entries(args).filter(([k])=>!['offset','limit'].includes(k)).sort(([a],[b])=>a.localeCompare(b)));
        if(pageArgs.source)pageArgs.source=normalizeSource(pageArgs.source);
        if(pageArgs.search)pageArgs.search=normalizeSource(pageArgs.search);
        const pageKey=call.name+JSON.stringify(pageArgs);
        const requestedOffset=args.offset;
        if(Number.isSafeInteger(requestedOffset)&&requestedOffset>0&&!pageCursors.get(pageKey)?.has(requestedOffset))args={...args,offset:0};
        if(!allowed.some(x=>x.name===call.name))throw new Error('Marketplace tool forbidden');
        if(scope && ['snapshots','economics','order_snapshot_counts','mpstats_products'].includes(call.name) && ((!args.cabinet&&scope.length<3) || (args.cabinet&&!scope.includes(args.cabinet)))) {
          result={error:'Cabinet scope mismatch',required_cabinets:scope};
        } else {
        result=call.name==='group_history'?await readMemory(args):call.name==='mpstats_products'?await refreshMpstats(args):await dispatch(db,call.name,args);
        }
        if(!result.error&&result.has_more===true) {
          const next=result.next_offset??(Number.isSafeInteger(result.offset)&&Number.isSafeInteger(result.returned)?result.offset+result.returned:null);
          if(Number.isSafeInteger(next)&&next>0){const offsets=pageCursors.get(pageKey)??new Set();offsets.add(next);pageCursors.set(pageKey,offsets);}
        }
        if(requestedOffset!==undefined&&requestedOffset!==args.offset)result={...result,pagination_note:'Unissued offset was reset to first page. Follow only next_offset supplied by the database.',effective_offset:args.offset};
        if(scope && result.cabinet && result.cabinet!=='shared' && !scope.includes(result.cabinet))result={error:'Snapshot belongs to another cabinet',required_cabinets:scope};
        if(Array.isArray(result.rows)&&result.rows.length===0)result={...result,no_matching_data:true,note:'No matching saved data. Not zero. Check exact source ID via sources, cabinet, dates and pagination.'};
        if(JSON.stringify(result).length>65000) result={too_large:true,hint:'Narrow source, dates, JSON path, page or group filter. Nothing was returned.'};
        success=!result.error && !result.too_large;
      } catch {result={error:'Tool unavailable or invalid arguments; do not infer zero. Narrow request or report the gap.'};}
      // Persistent audit stores metadata, never a second full copy of raw source payloads.
      const hasData=success&&!result.no_matching_data&&(!Array.isArray(result.rows)||!result.rows.length||!result.rows.every(x=>x.available===false));
      evidence.push({name:call.name,args,success,has_data:hasData,at:new Date().toISOString(),snapshot_id:result.id??null,source:result.source??null,period_from:result.period_from??null,period_to:result.period_to??null,status:result.status??null,has_more:result.has_more??null,reference:hasData?referenceFor(call.name,args,result):null});
      input.push({type:'function_call_output',call_id:call.call_id,output:JSON.stringify(result)});
    }
  }
  const error=new Error('Analysis budget exceeded');
  error.evidence=evidence;
  throw error;
}
