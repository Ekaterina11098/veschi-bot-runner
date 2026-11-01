export function chooseWork(jobs, watches, now) {
  const due = watches.filter(row => {
    const w = row.payload;
    return row.cache_key.startsWith('china_agent:conversion_watch:v1:') &&
      w?.agent_id === 'china' && w.chat_id === -1004342917488 &&
      w.owner_user_id === 5122667182 && w.status === 'active' &&
      (w.initial_pending === true || Number.isFinite(Date.parse(w.next_at)) && Date.parse(w.next_at) <= now.getTime());
  }).sort((a,b)=>Date.parse(a.payload.next_at)-Date.parse(b.payload.next_at));
  if (due.length) return {action:'reports', identity:due[0].payload.id, watch_key:due[0].cache_key};
  const eligible = jobs.filter(j=>(j.attempts??0)<3 && j.tool_trace?.some(x=>x.name==='china_saved_question'));
  return eligible.length ? {action:'dialog',identity:String(eligible[0].id),job_id:eligible[0].id} : null;
}
