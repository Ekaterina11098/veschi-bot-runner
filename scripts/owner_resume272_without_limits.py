"""Continue accepted job272, removing only the expressly cancelled daily-limit step."""
import copy,json
from datetime import datetime,timezone
from china_loss_execute import IO
from china_new_ads import execute,Transport,EXEC,BIND
from china_loss_control import PLAN
io=IO();pid='new-ad-test-270-final-v3';p=io.get(PLAN+pid);a=io.get('china_agent:loss_plan_approval:v1:272')
override=io.get('china_agent:owner_no_daily_limits:2026-11-08:v1')or{}
if override.get('existing_approved_plan_id')!=pid or override.get('prohibit_setting')is not True or override.get('existing_approval_job_id')!=272:raise ValueError('Exact current owner no-limit instruction missing')
if not p or not a or a.get('plan_sha256')!=p['plan_sha256']:raise ValueError('Current accepted plan mismatch')
io.validate_owner(a)
key=EXEC+pid;e=io.get(key)
if not e:raise ValueError('Existing partial execution journal missing')
if e.get('status')=='uncertain':
 if len(e.get('campaigns',[]))!=1 or e['campaigns'][0].get('campaign_id')!=41680341:raise ValueError('Unexpected partial scope')
 state=e['campaigns'][0]
 unknown=[name for name,step in state.get('steps',{}).items()if step.get('status')not in('verified','cancelled_by_owner')]
 if unknown!=['limit']:raise ValueError('Other uncertain mutation; no resume')
 t=Transport(io);current=t.campaign(41680341);budget=t.budget(41680341)
 if current.get('status')!=4 or budget!=0 or any(name in state['steps']for name in('deposit','start')):raise ValueError('Current draft/budget not safe for scoped resume')
 archive=key+':archive:before-owner-no-limits'
 if not io.get(archive):io.create(archive,copy.deepcopy(e))
 state['steps']['limit'].update(status='cancelled_by_owner',previous_status='uncertain',owner_override_key='china_agent:owner_no_daily_limits:2026-11-08:v1')
 e.update(status='running',owner_override_key='china_agent:owner_no_daily_limits:2026-11-08:v1',effective_daily_limits='prohibited',resume_readback=dict(campaign=current,budget=budget,observed_at=datetime.now(timezone.utc).isoformat()))
 e.pop('reason',None);io.put(key,e)
elif e.get('status')not in('running','readback_pending','done'):raise ValueError('Other blocked execution; no implicit retry')
e=execute(io,a,p)
if e.get('status')=='done':
 registry=io.get('china_agent:verified_campaign_state:v1')or{}
 for state in e['campaigns']:
  if state.get('status')!='launched' or (state.get('verified_after')or{}).get('status')!=9:raise ValueError('Actual launch readback incomplete')
  cid=state['campaign_id'];child=key+':campaign:'+str(cid)
  value=dict(status='verified',before=state.get('verified_before'),after=state['verified_after'],source_execution=key,approval_job_id=272,owner_override_key='china_agent:owner_no_daily_limits:2026-11-08:v1',verified_at=state['verified_at'])
  if not io.get(child):io.create(child,value)
  registry[str(cid)]=child
 io.put('china_agent:verified_campaign_state:v1',registry)if io.get('china_agent:verified_campaign_state:v1')else io.create('china_agent:verified_campaign_state:v1',registry)
 a['status']='completed';a['execution_key']=key;io.put('china_agent:loss_plan_approval:v1:272',a)
print(json.dumps({'status':e.get('status'),'campaigns':[dict(id=s.get('campaign_id'),status=s.get('status'))for s in e.get('campaigns',[])],'reason':e.get('reason'),'daily_limit_calls':0,'wb_writes':e.get('wb_writes')}))
if e.get('status')not in('done','readback_pending'):raise RuntimeError('Resume blocked; do not retry uncertain mutations')
