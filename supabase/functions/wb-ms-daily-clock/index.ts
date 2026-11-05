// Dedicated WB daily trigger; no Ozon execution and no periodic polling.
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
 const now=new Date();
 const local=new Date(now.getTime()+3*3600000);
 const day=local.toISOString().slice(0,10);
 async function save(key,payload,ignore=false) {
  const r=await fetch(project+"/rest/v1/telegram_api_cache?on_conflict=cache_key",{method:"POST",headers:{...headers,Prefer:(ignore?"resolution=ignore-duplicates":"resolution=merge-duplicates")+",return=representation"},body:JSON.stringify({cache_key:key,payload,updated_at:new Date().toISOString(),expires_at:"2036-11-05T00:00:00Z"}),signal:AbortSignal.timeout(8000)});
  if(!r.ok)throw new Error("Private state unavailable");
  return r.json();
 }
 async function finish(status,detail={}) {
  const value={at:now.toISOString(),local_date:day,status,...detail};
  await save("wb_ms_daily_clock:last_tick:v1",value);
  return Response.json(value);
 }
 try {
  let body={};try{body=await req.json();}catch{return new Response("Invalid body",{status:400});}
  const mode=new URL(req.url).pathname.endsWith("/probe")?"probe":(body.mode??"tick");
  if(!["tick","probe"].includes(mode))return new Response("Invalid mode",{status:400});
  const cabinets=["ip","ooo","china"];
  const configKeys=cabinets.map(c=>"fbs_document_chain:"+c+":config:v1");
  const response=await fetch(project+"/rest/v1/telegram_api_cache?select=cache_key,payload&cache_key=in.("+configKeys.map(encodeURIComponent).join(",")+")",{headers,signal:AbortSignal.timeout(8000)});
  if(!response.ok)throw new Error("Private configuration unavailable");
  const configs=Object.fromEntries((await response.json()).map(x=>[x.cache_key,x.payload]));
  const active=cabinets.filter(c=>configs["fbs_document_chain:"+c+":config:v1"]?.writes_enabled===true&&configs["fbs_document_chain:"+c+":config:v1"]?.status==="active");
  if(mode==="probe")return finish("probe_verified",{active_cabinets:active,daily_time:"19:00",timezone:"Europe/Moscow",dispatches:0});
  if(local.getUTCHours()!==19)return finish("outside_daily_window",{dispatches:0});
  if(active.length!==3)return finish("configuration_requires_attention",{active_cabinets:active,dispatches:0});
  const claim="wb_ms_daily_clock:dispatch:v1:"+day;
  const inserted=await save(claim,{at:now.toISOString(),status:"submitting",cabinet_scope:cabinets},true);
  if(!inserted.length)return finish("already_claimed",{dispatches:0});
  let status=0;
  try{status=(await fetch("https://api.github.com/repos/Ekaterina11098/veschi-bot-runner/actions/workflows/fbs-document-chain.yml/dispatches",{method:"POST",headers:auth,body:JSON.stringify({ref:"main",inputs:{mode:"run",execution_kind:"daily"}}),signal:AbortSignal.timeout(8000)})).status;}catch{}
  await save(claim,{at:now.toISOString(),status:status===204?"dispatched":"uncertain",github_status:status,cabinet_scope:cabinets});
  return finish(status===204?"dispatched":"dispatch_uncertain",{github_status:status,dispatches:1});
 }catch{
  try{await save("wb_ms_daily_clock:last_tick:v1",{at:now.toISOString(),status:"clock_error"});}catch{}
  return new Response("Clock unavailable",{status:503});
 }
}
Deno.serve(handle);
