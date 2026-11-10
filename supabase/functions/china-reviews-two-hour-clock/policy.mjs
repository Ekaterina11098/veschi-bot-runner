export const WORKFLOW = '.github/workflows/reviews-china-two-hour.yml';
export const ACTIVE = ['queued','in_progress','pending','waiting','requested'];
export function dueSlot(now) {
 const ms=now.getTime()-17*60000;
 const local=new Date(ms+3*3600000);
 local.setUTCHours(Math.floor(local.getUTCHours()/2)*2,0,0,0);
 return local.toISOString().slice(0,10)+':'+String(local.getUTCHours()).padStart(2,'0');
}
export function complete(state, receipt, slot) {
 return state?.cycle_slot===slot && state.status==='complete' &&
 state.scopes?.token_3?.status==='complete' &&
 state.summary?.cycle_slot===slot && state.summary.status==='confirmed' &&
 receipt?.cycle_slot===slot && receipt.status==='confirmed';
}
export function completeBoth(state,receipt,questions,questionReceipt,slot) {
 return complete(state,receipt,slot)&&complete(questions,questionReceipt,slot);
}
export function decision(now,state,receipt,runs,claims,questions,questionReceipt) {
 const slot=dueSlot(now);
 if(completeBoth(state,receipt,questions,questionReceipt,slot))return {status:'complete',slot};
 if(runs.some(r=>r.path===WORKFLOW && ACTIVE.includes(r.status)))return {status:'active',slot};
 const last=claims.at(-1);
 if(!last)return {status:'dispatch',slot,claim:slot+':initial'};
 // Never repeat an unknown dispatch. Retry only after a positively identified failed run.
 if(last.status!=='dispatched')return {status:'uncertain',slot};
 const matched=runs.filter(r=>r.path===WORKFLOW && r.event==='workflow_dispatch' &&
 Date.parse(r.created_at)>=Date.parse(last.created_at)-1000);
 if(!matched.length)return {status:'awaiting_run',slot};
 if(matched.some(r=>r.status!=='completed'))return {status:'active',slot};
 const latest=matched.sort((a,b)=>b.id-a.id)[0];
 if(!['failure','cancelled','timed_out','success'].includes(latest.conclusion))
 return {status:'uncertain',slot};
 // A successful but incomplete run can be a lock-busy/no-op; wait before native continuation.
 if(now.getTime()-Date.parse(latest.updated_at)<10*60000)return {status:'cooldown',slot};
 return {status:'dispatch',slot,claim:slot+':after:'+latest.id};
}
