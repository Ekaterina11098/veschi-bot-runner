import {readFile} from 'node:fs/promises';
import {TOOLS,dispatch} from './data.mjs';
export function outputText(response) {
  return (response.output??[]).filter(x=>x.type==='message').flatMap(x=>x.content??[]).filter(x=>x.type==='output_text').map(x=>x.text).join('\n').trim();
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
  let calls=0;
  const started=Date.now();
  for(let turn=0;turn<maxRounds;turn++) {
    if(Date.now()-started>8*60*1000)throw new Error('Analysis deadline exceeded');
    const response=await request({model,input,tools:TOOLS,tool_choice:turn===0?'required':'auto',parallel_tool_calls:false,max_output_tokens:2400,store:false});
    if(response.status && response.status!=='completed') throw new Error('Model response incomplete');
    const output=response.output??[];
    const tools=output.filter(x=>x.type==='function_call');
    input.push(...output);
    if(!tools.length) {
      const answer=outputText(response);
      if(!answer) throw new Error('Empty answer');
      if(!evidence.some(x=>x.name!=='calculate' && x.success)) throw new Error('Answer has no database evidence');
      return {answer,evidence};
    }
    for(const call of tools) {
      if(++calls>16) throw new Error('Tool budget exceeded');
      let args={},result,success=false;
      try {
        args=JSON.parse(call.arguments||'{}');
        result=await dispatch(db,call.name,args);
        if(JSON.stringify(result).length>65000) result={too_large:true,hint:'Narrow source, dates, JSON path, page or group filter. Nothing was returned.'};
        success=!result.error && !result.too_large;
      } catch {result={error:'Tool unavailable or invalid arguments; do not infer zero. Narrow request or report the gap.'};}
      // Persistent audit stores metadata, never a second full copy of raw source payloads.
      evidence.push({name:call.name,args,success,at:new Date().toISOString(),snapshot_id:result.id??null,source:result.source??null,period_from:result.period_from??null,period_to:result.period_to??null,status:result.status??null,has_more:result.has_more??null});
      input.push({type:'function_call_output',call_id:call.call_id,output:JSON.stringify(result)});
    }
  }
  throw new Error('Analysis budget exceeded');
}
