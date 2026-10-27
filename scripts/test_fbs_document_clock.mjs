import fs from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
const source=await fs.readFile('supabase/functions/fbs-document-clock/index.ts','utf8');
const key='test-only-clock-key';
const hash=Buffer.from(await webcrypto.subtle.digest('SHA-256',new TextEncoder().encode(key))).toString('hex');
const code=source.replace(/const expectedHash="[a-f0-9]+";/,'const expectedHash="'+hash+'";');
async function scenario(options={}){
 let handler;const calls=[];const claims=new Set();
 const env={SUPABASE_URL:'https://private.example',GITHUB_WORKFLOW_DISPATCH_TOKEN:'fake',SUPABASE_SERVICE_ROLE_KEY:'fake'};
 const cabinets=['china','ip','ooo','ozon'];
 const rows=cabinets.flatMap(c=>[{cache_key:'fbs_document_chain:'+c+':config:v1',payload:{status:'active',writes_enabled:!options.paused}},{cache_key:'fbs_document_chain:'+c+':last_run:v1',payload:{at:new Date(Date.now()-(options.fresh?0:3600000)).toISOString()}}]);
 const fetch=async(url,init={})=>{
  calls.push({url,init});
  if(url.startsWith(env.SUPABASE_URL+'/rest/v1/telegram_api_cache')){
   if(!init.method)return Response.json(rows);
   const value=JSON.parse(init.body);
   if(init.headers.Prefer.includes('ignore-duplicates')){
    if(claims.has(value.cache_key)||options.claimed)return Response.json([]);
    claims.add(value.cache_key);
   }
   return Response.json([value]);
  }
  if(url.endsWith('/runs?per_page=10'))return Response.json({workflow_runs:options.runs??[]});
  if(url.endsWith('/jobs'))return Response.json({jobs:options.jobs??[]});
  if(url.endsWith('/dispatches'))return new Response(null,{status:204});
  throw new Error('Unexpected destination');
 };
 vm.runInNewContext(code,{Deno:{env:{get:n=>env[n]},serve:h=>{handler=h;}},crypto:webcrypto,TextEncoder,Response,AbortSignal,fetch,console});
 const request=new Request('https://clock.example',{method:options.method??'POST',headers:{'x-stock-clock-key':options.badKey?'wrong':key,'Content-Type':'application/json'},body:(options.method==='GET'?undefined:JSON.stringify({mode:options.mode??'tick'}))});
 const response=await handler(request);const text=await response.text();
 return {status:response.status,body:text.startsWith('{')?JSON.parse(text):text,calls};
}
let r=await scenario({badKey:true});assert.equal(r.status,401);assert.equal(r.calls.length,0);
r=await scenario({method:'GET'});assert.equal(r.status,405);assert.equal(r.calls.length,0);
r=await scenario({mode:'probe'});assert.equal(r.body.status,'probe_verified');assert.equal(r.body.active_cabinets.length,4);assert(!r.calls.some(x=>x.url.endsWith('/dispatches')));
r=await scenario({fresh:true});assert.equal(r.body.status,'fresh');assert(!r.calls.some(x=>x.url.includes('api.github')));
r=await scenario({paused:true});assert.equal(r.body.status,'paused');
r=await scenario({runs:[{id:1,status:'queued'}]});assert.equal(r.body.status,'worker_queued');
r=await scenario({runs:[{id:1,status:'in_progress'}],jobs:[{name:'chain',status:'in_progress'}]});assert.equal(r.body.status,'worker_active');
r=await scenario({runs:[{id:1,status:'in_progress'}],jobs:[{name:'chain',status:'completed'},{name:'audit_comments',status:'in_progress'}]});assert.equal(r.body.status,'dispatched');assert.equal(r.calls.filter(x=>x.url.endsWith('/dispatches')).length,1);
r=await scenario({claimed:true});assert.equal(r.body.status,'already_claimed');assert(!r.calls.some(x=>x.url.endsWith('/dispatches')));
r=await scenario({runs:[{id:1,status:'pending'}],jobs:[{name:'chain',status:'completed'},{name:'audit_comments',status:'pending'}]});assert.equal(r.body.status,'dispatched');
console.log('10 clock checks passed: auth, fresh state, pause, queue, worker lock, separate audit, deduplication.');