"""One-time model settings migration only: never submits input or starts a turn."""
import json,os
from urllib.request import Request,urlopen
from china_codex_cloud import DB,stamp
MODEL='gpt-6.1-sol'
KEYS=('china_agent:codex_cloud:v1:session','china_agent:codex_cloud:v2:session')
def api(path,body=None):
 if not(path=='/agents' or path.startswith('/agents/')):raise ValueError('Configuration endpoint only')
 req=Request('https://api.openai.com/v1'+path,data=None if body is None else json.dumps(body).encode(),
             method='GET'if body is None else'POST',headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY'],'OpenAI-Beta':'agents=v1','Content-Type':'application/json'})
 with urlopen(req,timeout=40)as r:return json.load(r)
def main():
 db=DB();results=[]
 for key in KEYS:
  state=db.get(key)
  if not state:continue
  sid=state['session_id']
  if not sid.startswith('sess_')or not sid.replace('_','').isalnum():raise ValueError('Invalid session')
  before=api('/agents/sessions/'+sid)
  old=before['agent']['model']
  if old!=MODEL:api('/agents/sessions/'+sid,{'agent':{'model':MODEL}})
  after=api('/agents/sessions/'+sid)
  if after['agent']['model']!=MODEL:raise RuntimeError('Provider model readback mismatch')
  updated=dict(state,model=MODEL,model_verified_at=stamp(),previous_model=state.get('previous_model',old))
  if not db.update(key,updated):raise RuntimeError('Session receipt update failed')
  results.append(dict(key=key,previous_model=old,model=MODEL,turns_submitted=0))
 agents=api('/agents?limit=100') if False else api('/agents')
 if agents.get('has_more'):raise RuntimeError('Agent list requires further pagination')
 saved=[]
 for agent in agents['data']:
  if 'astra'not in agent.get('model',''):continue
  aid=agent['id']
  if not aid.replace('_','').isalnum():raise ValueError('Invalid agent id')
  api('/agents/'+aid,{'model':MODEL})
  if api('/agents/'+aid)['model']!=MODEL:raise RuntimeError('Saved agent readback mismatch')
  saved.append(dict(id=aid,model=MODEL))
 receipt=dict(status='verified',at=stamp(),sessions=results,saved_agents_checked=len(agents['data']),saved_agents_changed=saved,model_generations=0,wb_calls=0,telegram_calls=0)
 db.once('ai_model_policy:sol_migration:2026-11-07:v1',receipt) if not db.get('ai_model_policy:sol_migration:2026-11-07:v1')else None
 print(json.dumps(receipt))
if __name__=='__main__':main()
