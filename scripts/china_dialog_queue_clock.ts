const expected='3af262a9e683f61e876fcbe7cf076db728d4b4f1515c7f554f702303990638db';
Deno.serve(async(req)=>{
 if(req.method!=='POST')return new Response('Method',{status:405});
 const k=req.headers.get('x-china-clock-key')??'';
 const h=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(k)))).map(x=>x.toString(16).padStart(2,'0')).join('');
 if(!k||h!==expected)return new Response('Unauthorized',{status:401});
 const url=Deno.env.get('SUPABASE_URL')??'';let service=Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')??'';
 try{service=Object.values(JSON.parse(Deno.env.get('SUPABASE_SECRET_KEYS')??'{}'))[0] as string||service;}catch{}
 const gh=Deno.env.get('GITHUB_WORKFLOW_DISPATCH_TOKEN')??'';
 if(!url||!service||!gh)return new Response('Configuration',{status:503});
 const headers={apikey:service,'Content-Type':'application/json'};

 const t=new Date();
 const pending=await fetch(url+'/rest/v1/business_agent_jobs?agent_id=eq.china&chat_id=eq.-1004342917488&status=eq.pending&retry_at=lte.'+encodeURIComponent(t.toISOString())+'&select=id,tool_trace,attempts&order=id.asc&limit=10',{headers});
 if(!pending.ok)return new Response('Queue unavailable',{status:503});
 const jobs=(await pending.json()).filter((j:any)=>(j.attempts??0)<3&&j.tool_trace?.some((x:any)=>x.name==='china_saved_question'));
 if(!jobs.length)return Response.json({status:'idle',wb_requests:0,telegram_sends:0});
 const auth={Authorization:'Bearer '+gh,Accept:'application/vnd.github+json','Content-Type':'application/json'};
 const active=await fetch('https://api.github.com/repos/Ekaterina11098/veschi-bot-runner/actions/runs?per_page=100',{headers:auth});
 if(!active.ok)return new Response('Runner unavailable',{status:503});
 const runs=(await active.json()).workflow_runs;
 if(runs.some((r:any)=>r.path==='.github/workflows/china-conversion-watches.yml'&&['queued','in_progress','waiting','requested','pending'].includes(r.status)))return Response.json({status:'dialog_run_active'});
 const claim='china_agent:dialog_queue_dispatch:v1:'+jobs[0].id+':'+Math.floor(t.getTime()/300000);
 const row={cache_key:claim,payload:{status:'submitting',job_id:jobs[0].id,created_at:t.toISOString()},updated_at:t.toISOString(),expires_at:'2036-10-26T00:00:00Z'};
 const create=await fetch(url+'/rest/v1/telegram_api_cache?on_conflict=cache_key',{method:'POST',headers:{...headers,Prefer:'resolution=ignore-duplicates,return=representation'},body:JSON.stringify(row)});
 if(!create.ok)return new Response('Claim unavailable',{status:503});
 if(!(await create.json()).length)return Response.json({status:'claimed'});
 let status=0;
 try{status=(await fetch('https://api.github.com/repos/Ekaterina11098/veschi-bot-runner/actions/workflows/china-conversion-watches.yml/dispatches',{method:'POST',headers:auth,body:JSON.stringify({ref:'main',inputs:{action:'dialog',job_id:String(jobs[0].id)}}),signal:AbortSignal.timeout(10000)})).status;}catch{}
 row.payload={...row.payload,status:status===204?'dispatched':'uncertain'};
 await fetch(url+'/rest/v1/telegram_api_cache?on_conflict=cache_key',{method:'POST',headers:{...headers,Prefer:'resolution=merge-duplicates'},body:JSON.stringify(row)});
 return Response.json({status:row.payload.status,job_id:jobs[0].id,wb_requests:0,telegram_sends:0},{status:status===204?200:503});
});