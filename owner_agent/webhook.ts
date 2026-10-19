import {Database} from './data.mjs';
import {handle} from './ingress.mjs';
const url=Deno.env.get('SUPABASE_URL')??'';
let key=Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')??'';
try {key=JSON.parse(Deno.env.get('SUPABASE_SECRET_KEYS')??'{}').default??key;} catch {}
Deno.serve((request:Request)=>handle(request,{
  db:new Database({url,key}),secret:'',
  dispatchJob:async(id:number)=>{
    const token=Deno.env.get('GITHUB_WORKFLOW_DISPATCH_TOKEN');
    if(!token)throw new Error('Dispatcher missing');
    const r=await fetch('https://api.github.com/repos/Ekaterina11098/veschi-bot-runner/actions/workflows/owner-agent.yml/dispatches',{
      method:'POST',headers:{Authorization:'Bearer '+token,Accept:'application/vnd.github+json','Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28'},
      body:JSON.stringify({ref:'main',inputs:{job_id:String(id)}}),signal:AbortSignal.timeout(8000)
    });
    if(!r.ok)throw new Error('Dispatch unavailable');
  }
}));
