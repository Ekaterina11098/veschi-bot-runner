import { checkMorning } from './morning.mjs';
import postgres from 'https://deno.land/x/postgresjs@v3.4.5/mod.js';
import { dueSlot, decision, completeBoth, WORKFLOW } from './policy.mjs';
const expected='3af262a9e683f61e876fcbe7cf076db728d4b4f1515c7f554f702303990638db';
Deno.serve(async req=>{
 if(req.method!=='POST')return new Response('Method',{status:405});
 const key=req.headers.get('x-china-clock-key')??'';
 const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(key)))).map(x=>x.toString(16).padStart(2,'0')).join('');
 if(!key||hash!==expected)return new Response('Unauthorized',{status:401});
 const db=Deno.env.get('SUPABASE_DB_URL'),gh=Deno.env.get('GITHUB_WORKFLOW_DISPATCH_TOKEN');
 if(!db||!gh)return new Response('Configuration',{status:503});
 const sql=postgres(db,{max:1,prepare:false,idle_timeout:1,connect_timeout:10});
 try{
 const now=new Date(),slot=dueSlot(now),day=slot.slice(0,10);
 let body={};try{body=await req.json();}catch{}
 const morningAuth={Authorization:'Bearer '+gh,Accept:'application/vnd.github+json','Content-Type':'application/json'};
 try{await checkMorning(sql,morningAuth,'https://api.github.com/repos/Ekaterina11098/veschi-bot-runner',now,body.verify===true);}catch{
 await sql`insert into review_approval.events(id,payload) values ('morning-clock:health:v1',${JSON.stringify({status:'check_failed',checked_at:now.toISOString()})}) on conflict(id) do update set payload=excluded.payload`;
 }

 const rows=await sql`select id,payload from review_approval.events where id in (${'reviews-china-two-hour:'+day},${'reviews-china-two-hour:'+day+':summary:'+slot},${'questions-china-two-hour:'+day},${'questions-china-two-hour:'+day+':summary:'+slot})`;
 const parse=(v)=>typeof v==='string'?JSON.parse(v):v;
 const state=parse(rows.find(r=>r.id==='reviews-china-two-hour:'+day)?.payload??'{}');
 const receipt=parse(rows.find(r=>r.id==='reviews-china-two-hour:'+day+':summary:'+slot)?.payload??'{}');
 const questions=parse(rows.find(r=>r.id==='questions-china-two-hour:'+day)?.payload??'{}');
 const questionReceipt=parse(rows.find(r=>r.id==='questions-china-two-hour:'+day+':summary:'+slot)?.payload??'{}');
 const auth={Authorization:'Bearer '+gh,Accept:'application/vnd.github+json','Content-Type':'application/json'};
 const base='https://api.github.com/repos/Ekaterina11098/veschi-bot-runner';
 // Workflow-specific endpoint covers all active statuses, independent of unrelated repository activity.
 const response=await fetch(base+'/actions/workflows/reviews-china-two-hour.yml/runs?per_page=100',{headers:auth,signal:AbortSignal.timeout(10000)});
 if(!response.ok)return new Response('Runner status unavailable',{status:503});
 const runs=(await response.json()).workflow_runs;
 const prefix='china-reviews-clock:v1:'+slot+':';
 const claims=await sql`select payload from public.telegram_api_cache where starts_with(cache_key,${prefix}) order by updated_at`;
 const result=decision(now,state,receipt,runs,claims.map(r=>r.payload),questions,questionReceipt);
 const save=async value=>sql`insert into review_approval.events(id,payload) values ('china-reviews-clock:health:v1',${JSON.stringify({...value,checked_at:now.toISOString(),version:2})}) on conflict(id) do update set payload=excluded.payload`;
 if(body.verify===true){await save({...result,verify:true});return Response.json({...result,verify:true,wb_requests:0,telegram_sends:0,github_dispatches:0});}
 if(result.status!=='dispatch'){await save(result);return Response.json(result);}
 const claimKey='china-reviews-clock:v1:'+result.claim;
 const payload={status:'submitting',slot,created_at:now.toISOString()};
 const claimed=await sql`insert into public.telegram_api_cache(cache_key,payload,updated_at,expires_at) values (${claimKey},${sql.json(payload)},now(),now()+interval '90 days') on conflict(cache_key) do nothing returning cache_key`;
 if(!claimed.length)return Response.json({status:'claimed',slot});
 // Recheck completion and active runs immediately before dispatch; collector itself also holds the shared lock.
 const fresh=await sql`select id,payload from review_approval.events where id in (${'reviews-china-two-hour:'+day},${'reviews-china-two-hour:'+day+':summary:'+slot},${'questions-china-two-hour:'+day},${'questions-china-two-hour:'+day+':summary:'+slot})`;
 const readFresh=id=>parse(fresh.find(r=>r.id===id)?.payload??'{}');
 if(completeBoth(readFresh('reviews-china-two-hour:'+day),readFresh('reviews-china-two-hour:'+day+':summary:'+slot),readFresh('questions-china-two-hour:'+day),readFresh('questions-china-two-hour:'+day+':summary:'+slot),slot)){
 await sql`update public.telegram_api_cache set payload=${sql.json({...payload,status:'complete'})},updated_at=now() where cache_key=${claimKey}`;
 await save({status:'complete',slot});return Response.json({status:'complete',slot});
 }
 const queueCheck=await fetch(base+'/actions/workflows/reviews-china-two-hour.yml/runs?per_page=100',{headers:auth,signal:AbortSignal.timeout(10000)});
 if(!queueCheck.ok)return new Response('Queue recheck unavailable; claim retained',{status:503});
 if((await queueCheck.json()).workflow_runs.some(r=>r.path===WORKFLOW&&['queued','in_progress','pending','waiting','requested'].includes(r.status))){
 await sql`update public.telegram_api_cache set payload=${sql.json({...payload,status:'dispatched'})},updated_at=now() where cache_key=${claimKey}`;
 await save({status:'active',slot});return Response.json({status:'active',slot});
 }
 let status=0;
 try{status=(await fetch(base+'/actions/workflows/reviews-china-two-hour.yml/dispatches',{method:'POST',headers:auth,body:JSON.stringify({ref:'main'}),signal:AbortSignal.timeout(10000)})).status;}catch{}
 const outcome=status===204?'dispatched':'uncertain';
 await sql`update public.telegram_api_cache set payload=${sql.json({...payload,status:outcome,http_status:status})},updated_at=now() where cache_key=${claimKey}`;
 await save({status:outcome,slot});
 return Response.json({status:outcome,slot},{status:status===204?200:503});
 }catch{return new Response('Clock check failed; no blind retry',{status:503});}
 finally{await sql.end({timeout:1});}
});
