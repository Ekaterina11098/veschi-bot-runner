export const ROOT='china_agent:hourly_sales_api:v1';
export function slot(now){
 const local=new Date(now.getTime()+10800000).toISOString();const hour=local.slice(0,13);
 return {key:ROOT+':snapshot:'+hour+':MSK',slot_msk:hour+':00:00+03:00',minute:Number(local.slice(14,16)),identity:hour};
}
export function complete(value,policy){
 return value?.status==='complete'&&value.cabinet==='token_3'&&[0,1,7].every(n=>value.orders?.[String(n)]?.status==='complete')&&value.advertising?.status==='complete'&&value.budgets?.status==='complete'&&(!(policy.funnel_nm_ids?.length)||value.general_funnel?.status==='complete');
}
export async function tick({db,github,now=new Date(),verify=false}){
 const s=slot(now),p=(await db.get(ROOT+':policy'))??{};
 const result=(status,extra={})=>({status,slot_msk:s.slot_msk,wb_requests:0,wb_writes:0,telegram_sends:0,grants_action_permission:false,...extra});
 async function health(value){if(!verify)await db.put(ROOT+':clock:health',{...value,checked_at:now.toISOString()});return value;}
 if(p.enabled!==true||p.cabinet!=='token_3'||p.read_only!==true||p.wb_writes!==0)return health(result('disabled'));
 if(s.minute<7)return health(result('not_due'));
 const pointer=await db.get(s.key+':latest');const source=pointer?.source_key??s.key;
 if(source!==s.key&&!source.startsWith(s.key+':attempt:'))throw Error('Hourly source pointer crosses slot');
 const value=await db.get(source,true);
 if(value&&(value.cabinet!=='token_3'||value.slot_msk!==s.slot_msk))throw Error('Hourly source identity mismatch');
 if(complete(value,p)){
  if(!verify){
   const globalKey=ROOT+':latest',old=await db.row(globalKey);
   if(!old||(!old.payload.slot_msk||old.payload.slot_msk<=s.slot_msk)&&(old.payload.source_key!==source||old.payload.status!=='complete')){
    const pointer={source_key:source,status:'complete',slot_msk:s.slot_msk,observed_at:value.observed_at,completed_at:value.completed_at,wb_writes:0};
    if(!await db.claim(globalKey,old,pointer))throw Error('Latest pointer CAS conflict');
   }
  }
  return health(result('complete',{source_key:source,observed_at:value.observed_at}));
 }
 const lease=await db.get(s.key+':lease');
 if(lease&&Date.parse(lease.until??new Date(Date.parse(lease.created_at)+720000).toISOString())>now.getTime())return health(result('collector_active',{attempt:lease.attempt}));
 if((lease?.attempt??0)>=3)return health(result('collector_attempts_exhausted',{attempt:lease.attempt,needs_attention:true}));
 const claimKey=ROOT+':clock:dispatch:'+s.identity;const old=await db.row(claimKey);
 if(old&&Date.parse(old.payload.until)>now.getTime())return health(result('dispatch_lease_active',{dispatch_status:old.payload.status}));
 if((old?.payload?.attempt??0)>=3)return health(result('dispatch_attempts_exhausted',{needs_attention:true}));
 if(verify)return result('would_dispatch',{github_dispatches:0});
 const runs=await github.runs();
 if(runs.some(r=>['queued','in_progress','waiting','requested','pending'].includes(r.status)))return health(result('runner_active'));
 const claim={status:'submitting',slot_msk:s.slot_msk,created_at:now.toISOString(),until:new Date(now.getTime()+720000).toISOString(),attempt:(old?.payload?.attempt??0)+1,read_only:true,workflow:'china-hourly-sales-read.yml',wb_writes:0,telegram_calls:0};
 if(!await db.claim(claimKey,old,claim))return health(result('claim_race_lost'));
 let code=0;try{code=await github.dispatch();}catch{}
 const state=code===204?'dispatched':'dispatch_uncertain';claim.status=state;claim.http_status=code;
 await db.put(claimKey,claim);await db.put(claimKey+':attempt:'+claim.attempt,claim,true);
 return health(result(state,{attempt:claim.attempt,github_dispatches:1,http_status:code}));
}

