// Backend clock: dispatches the existing idempotent FBS worker only.
const expectedHash="ff4ec4efb56b5ec3f8c515ec644de13c172bffde13d6f2b028e6852aa66a636e";
async function handle(req) {
 if(req.method!=="POST")return new Response("Method",{status:405});
 const key=req.headers.get("x-stock-clock-key")??"";
 if(!key||key.length>200)return new Response("Unauthorized",{status:401});
 const hash=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(key)))).map(x=>x.toString(16).padStart(2,"0")).join("");
 if(hash!==expectedHash)return new Response("Unauthorized",{status:401});
 const project=Deno.env.get("SUPABASE_URL")??"";
 const github=Deno.env.get("GITHUB_WORKFLOW_DISPATCH_TOKEN")??"";
 let service=Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")??"";
 try{service=Object.values(JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS")??"{}"))[0]||service;}catch{}
 if(!project||!github||!service)return new Response("Configuration",{status:503});
 const headers={apikey:service,"Content-Type":"application/json"};
 const auth={Authorization:"Bearer "+github,Accept:"application/vnd.github+json","Content-Type":"application/json","X-GitHub-Api-Version":"2022-11-28"};
 const repo="https://api.github.com/repos/Ekaterina11098/veschi-bot-runner";
 const now=new Date();
 async function save(key,payload,ignore=false) {
  const r=await fetch(project+"/rest/v1/telegram_api_cache?on_conflict=cache_key",{method:"POST",headers:{...headers,Prefer:(ignore?"resolution=ignore-duplicates":"resolution=merge-duplicates")+",return=representation"},body:JSON.stringify({cache_key:key,payload,updated_at:new Date().toISOString(),expires_at:new Date(Date.now()+7*86400000).toISOString()}),signal:AbortSignal.timeout(8000)});
  if(!r.ok)throw new Error("Private state unavailable");
  return r.json();
 }
 async function finish(status,detail={}) {
  const value={at:new Date().toISOString(),status,...detail};
  await save("fbs_document_clock:last_tick:v1",value);
  return Response.json(value);
 }
 try {
  let body={};try{body=await req.json();}catch{return new Response("Invalid body",{status:400});}
  const mode=body.mode??"tick";
  if(!["tick","probe"].includes(mode))return new Response("Invalid mode",{status:400});
  const cabinets=["china","ip","ooo","ozon"];
  const keys=cabinets.flatMap(c=>["fbs_document_chain:"+c+":config:v1","fbs_document_chain:"+c+":last_run:v1"]);
  const state=await fetch(project+"/rest/v1/telegram_api_cache?select=cache_key,payload&cache_key=in.("+keys.map(encodeURIComponent).join(",")+")",{headers,signal:AbortSignal.timeout(8000)});
  if(!state.ok)throw new Error("Private state unavailable");
  const data=Object.fromEntries((await state.json()).map(x=>[x.cache_key,x.payload]));
  const active=cabinets.filter(c=>data["fbs_document_chain:"+c+":config:v1"]?.writes_enabled===true&&data["fbs_document_chain:"+c+":config:v1"]?.status==="active");
  const checks=Object.fromEntries(active.map(c=>[c,data["fbs_document_chain:"+c+":last_run:v1"]?.at??null]));
  if(mode==="probe")return finish("probe_verified",{active_cabinets:active,last_checks:checks});
  if(!active.length)return finish("paused");
  if(active.every(c=>checks[c]&&now.getTime()-new Date(checks[c]).getTime()<60000))return finish("fresh",{last_checks:checks});
  const response=await fetch(repo+"/actions/workflows/fbs-document-chain.yml/runs?per_page=10",{headers:auth,signal:AbortSignal.timeout(8000)});
  if(!response.ok)throw new Error("Runner status unavailable");
  const runs=(await response.json()).workflow_runs;
  if(runs.some(r=>["queued","pending","waiting","requested"].includes(r.status)))return finish("worker_queued");
  for(const run of runs.filter(r=>r.status==="in_progress")){
   const jobs=await fetch(repo+"/actions/runs/"+run.id+"/jobs",{headers:auth,signal:AbortSignal.timeout(8000)});
   if(!jobs.ok)throw new Error("Worker status unavailable");
   if((await jobs.json()).jobs.some(j=>j.name==="chain"&&j.status!=="completed"))return finish("worker_active",{run_id:run.id});
  }
  const claim="fbs_document_clock:dispatch:v1:"+Math.floor(now.getTime()/300000);
  const inserted=await save(claim,{status:"submitting",at:now.toISOString()},true);
  if(!inserted.length)return finish("already_claimed");
  let status=0;
  try{status=(await fetch(repo+"/actions/workflows/fbs-document-chain.yml/dispatches",{method:"POST",headers:auth,body:JSON.stringify({ref:"main",inputs:{mode:"run"}}),signal:AbortSignal.timeout(8000)})).status;}catch{}
  await save(claim,{status:status===204?"dispatched":"uncertain",github_status:status,at:now.toISOString()});
  return finish(status===204?"dispatched":"dispatch_uncertain",{github_status:status,last_checks:checks});
 }catch{
  try{await save("fbs_document_clock:last_tick:v1",{at:new Date().toISOString(),status:"clock_error"});}catch{}
  return new Response("Clock unavailable",{status:503});
 }
}
Deno.serve(handle);
