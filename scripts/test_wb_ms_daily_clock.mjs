import fs from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
let source=await fs.readFile('supabase/functions/wb-ms-daily-clock/index.ts','utf8');
const key='unit-test-key';
const hash=Buffer.from(await webcrypto.subtle.digest('SHA-256',new TextEncoder().encode(key))).toString('hex');
source=source.replace(/const expectedHash="[a-f0-9]+";/,'const expectedHash="'+hash+'";');
async function scenario({hour=16,claimed=false,paused=false,probe=false,badKey=false,method='POST'}={}){
 let handler; const calls=[];const env={SUPABASE_URL:'https://private.example',SUPABASE_SERVICE_ROLE_KEY:'fake',GITHUB_WORKFLOW_DISPATCH_TOKEN:'fake'};
 const fixed=Date.UTC(2026,10,5,hour,0,0);
 class Clock extends Date{constructor(...args){super(...(args.length?args:[fixed]));}static now(){return fixed;}}
 const fetch=async(url,init={})=>{
  calls.push({url,init});
  if(url.startsWith(env.SUPABASE_URL)){
   if(!init.method)return Response.json(['ip','ooo','china'].map(c=>({cache_key:'fbs_document_chain:'+c+':config:v1',payload:{writes_enabled:!paused,status:'active'}})));
   if(init.headers.Prefer.includes('ignore-duplicates')&&claimed)return Response.json([]);
   return Response.json([JSON.parse(init.body)]);
  }
  assert(url.endsWith('/fbs-document-chain.yml/dispatches'));
  return new Response(null,{status:204});
 };
 vm.runInNewContext(source,{Deno:{env:{get:n=>env[n]},serve:h=>{handler=h;}},crypto:webcrypto,Date:Clock,TextEncoder,URL,Response,AbortSignal,fetch});
 const r=await handler(new Request('https://clock.example'+(probe?'/probe':''),{method,headers:{'x-stock-clock-key':badKey?'bad':key},body:method==='POST'?JSON.stringify({mode:'tick'}):undefined}));
 const body=await r.text();return {status:r.status,body:body.startsWith('{')?JSON.parse(body):body,calls};
}
let r=await scenario({badKey:true});assert.equal(r.status,401);assert.equal(r.calls.length,0);
r=await scenario({method:'GET'});assert.equal(r.status,405);assert.equal(r.calls.length,0);
r=await scenario({hour:15});assert.equal(r.body.status,'outside_daily_window');assert(!r.calls.some(x=>x.url.includes('api.github')));
r=await scenario({hour:17});assert.equal(r.body.status,'outside_daily_window');
r=await scenario({hour:16});assert.equal(r.body.status,'dispatched');assert.deepEqual(JSON.parse(r.calls.find(x=>x.url.includes('api.github')).init.body).inputs,{mode:'run',execution_kind:'daily'});
r=await scenario({claimed:true});assert.equal(r.body.status,'already_claimed');assert(!r.calls.some(x=>x.url.includes('api.github')));
r=await scenario({paused:true});assert.equal(r.body.status,'configuration_requires_attention');assert(!r.calls.some(x=>x.url.includes('api.github')));
r=await scenario({probe:true});assert.equal(r.body.status,'probe_verified');assert.equal(r.body.active_cabinets.length,3);assert(!r.calls.some(x=>x.url.includes('api.github')));
console.log('8 checks passed: auth, method, time boundaries, one daily dispatch, duplicate guard, paused state and read-only probe.');
