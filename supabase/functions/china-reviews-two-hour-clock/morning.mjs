export const ACTIVE=['queued','in_progress','pending','waiting','requested'];
export const CONTROLLER='review-morning-watchdog.yml';
export const TARGETS=['reviews-morning.yml','questions-morning.yml'];
export function morningDecision(now,states,runs,claims){
 const local=new Date(now.getTime()+3*3600000),day=local.toISOString().slice(0,10);
 const minute=local.getUTCHours()*60+local.getUTCMinutes();
 if(minute<480||minute>=770)return {status:'outside_window',day};
 const complete=s=>s?.status==='complete'&&s.summary?.status==='confirmed'&&
 ['token_1','token_2','token_3'].every(c=>s.scopes?.[c]?.status==='complete');
 if(complete(states.reviews)&&complete(states.questions))return {status:'complete',day};
 const active=runs.find(r=>ACTIVE.includes(r.status));
 if(active)return {status:'active',day,active_run_id:active.id};
 const last=claims.at(-1);
 let suffix='initial';
 if(last){
  if(last.status==='observed_active'){
   const observed=runs.find(r=>r.id===last.observed_run_id);
   if(!observed||observed.status!=='completed')return {status:'awaiting_run',day};
   if(now-Date.parse(observed.updated_at)<5*60000)return {status:'cooldown',day};
   return {status:'dispatch',day,claim:day+':after-observed:'+observed.id};
  }
  if(last.status!=='dispatched')return {status:'uncertain',day};
  const matched=runs.filter(r=>r.path.endsWith('/'+CONTROLLER)&&r.event==='workflow_dispatch'&&Date.parse(r.created_at)>=Date.parse(last.created_at)-1000);
  if(!matched.length)return {status:'awaiting_run',day};
  if(matched.some(r=>r.status!=='completed'))return {status:'active',day};
  const latest=matched.sort((a,b)=>b.id-a.id)[0];
  if(!['success','failure','cancelled','timed_out'].includes(latest.conclusion))return {status:'uncertain',day};
  if(now-Date.parse(latest.updated_at)<5*60000)return {status:'cooldown',day};
  suffix='after:'+latest.id;
 }
 return {status:'dispatch',day,claim:day+':'+suffix};
}
export async function checkMorning(sql,auth,base,now,verify=false){
 const day=new Date(now.getTime()+3*3600000).toISOString().slice(0,10);
 const save=async result=>sql`insert into review_approval.events(id,payload) values ('morning-clock:health:v1',${JSON.stringify({...result,checked_at:now.toISOString(),version:1})}) on conflict(id) do update set payload=excluded.payload`;
 const read=async()=>{
  const rows=await sql`select id,payload from review_approval.events where id in (${'reviews-morning:'+day},${'questions-morning:'+day})`;
  const parse=v=>typeof v==='string'?JSON.parse(v):v;
  const states=Object.fromEntries(['reviews','questions'].map(k=>[k,parse(rows.find(r=>r.id===k+'-morning:'+day)?.payload??'{}')]));
  const runs=[];
  for(const name of [CONTROLLER,...TARGETS]){
   const r=await fetch(base+'/actions/workflows/'+name+'/runs?per_page=100',{headers:auth,signal:AbortSignal.timeout(10000)});
   if(!r.ok)throw Error('Morning runner status unavailable');
   runs.push(...(await r.json()).workflow_runs);
  }
  const claims=await sql`select payload from public.telegram_api_cache where starts_with(cache_key,${'morning-clock:v1:'+day+':'}) order by updated_at`;
  return morningDecision(now,states,runs,claims.map(r=>r.payload));
 };
 // No GitHub queries outside the morning window.
 const window=morningDecision(now,{},[],[]);
 if(window.status==='outside_window')return window;
 let result=await read();
 if(verify||result.status!=='dispatch'){await save(result);return result;}
 const key='morning-clock:v1:'+result.claim,payload={status:'submitting',created_at:now.toISOString(),day};
 const claimed=await sql`insert into public.telegram_api_cache(cache_key,payload,updated_at,expires_at) values (${key},${sql.json(payload)},now(),now()+interval '90 days') on conflict(cache_key) do nothing returning cache_key`;
 if(!claimed.length)return {status:'claimed',day};
 // The second decision includes our claim; read it only to inspect active/completed state.
 const fresh=await read();
 if(fresh.status==='active'||fresh.status==='complete'){
  await sql`update public.telegram_api_cache set payload=${sql.json({...payload,status:'observed_active',observed_run_id:fresh.active_run_id})},updated_at=now() where cache_key=${key}`;
  await save(fresh);return fresh;
 }
 let status=0;
 try{status=(await fetch(base+'/actions/workflows/'+CONTROLLER+'/dispatches',{method:'POST',headers:auth,body:JSON.stringify({ref:'main'}),signal:AbortSignal.timeout(10000)})).status;}catch{}
 result={status:status===204?'dispatched':'uncertain',day,http_status:status};
 await sql`update public.telegram_api_cache set payload=${sql.json({...payload,...result})},updated_at=now() where cache_key=${key}`;
 await save(result);return result;
}
