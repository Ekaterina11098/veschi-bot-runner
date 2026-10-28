"""Recover job150 through the exact selected-action executor, WB scope fixed to one exclusion."""
import copy,json,os
from datetime import datetime,timezone
from china_loss_execute import IO
from china_daily_selected import prepare
from china_daily_ad_actions import execute,EXEC
from china_loss_control import PLAN,APPROVAL
ROOT='china_agent:owner_exclude98:2026-10-28:v1:41055480:execution'
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 io=IO();old=io.get(ROOT)
 if old:
  print(json.dumps(dict(status=old['status'],duplicate_prevented=True)));return
 jobs=io.db('business_agent_jobs?id=eq.150&agent_id=eq.china&select=*')
 if len(jobs)!=1:raise ValueError('Original job missing')
 job=jobs[0]
 if job['request_text']!='Выполни только 3 по списку предложение. Сумка 98' or job['sender_id']!=307200273:raise ValueError('Command changed')
 a,p=prepare(io,job)
 if len(p['items'])!=1 or p['items'][0]['kind']!='ad_exclude_sku' or p['items'][0]['campaign_id']!=41055480 or p['items'][0]['nm_id']!=1473242754 or p['items'][0]['old_minor']!=28:raise ValueError('Only exclusion98 allowed')
 e=execute(io,a,p);state=e['items'][0]
 if state['status']!='verified' or not state.get('before') or not state.get('after'):raise ValueError('WB exclusion not verified; inspect journal, no replay')
 before=state['before'];after=state['after'];expected=copy.deepcopy(before['nm_settings']);expected=[x for x in expected if x['nm_id']!=1473242754]
 if after['id']!=41055480 or after['status']!=before['status'] or after['settings']!=before['settings'] or sorted(after['nm_settings'],key=lambda n:n['nm_id'])!=sorted(expected,key=lambda n:n['nm_id']):raise ValueError('Unexpected WB difference')
 receipt=dict(status='verified',before=before,after=after,verified_at=datetime.now(timezone.utc).isoformat(),approval_key=APPROVAL+'150',execution_key=EXEC+p['plan_id'],job_id=150,wb_writes=e['wb_writes'],telegram_sends=0,action=p['items'][0],authorization='Pavel original command150 and owner explicit Codex28Oct fix-and-execute-only98')
 if not io.create(ROOT,receipt):raise ValueError('Canonical receipt race')
 registry=io.get('china_agent:verified_campaign_state:v1') or {};registry['41055480']=ROOT;io.put('china_agent:verified_campaign_state:v1',registry)
 a.update(status='completed',result_status='verified',execution_key=EXEC+p['plan_id']);io.put(APPROVAL+'150',a)
 print(json.dumps(dict(status='verified',campaign_id=41055480,nm_id=1473242754,before_count=len(before['nm_settings']),after_count=len(after['nm_settings']),wb_writes=e['wb_writes'],other_bids_preserved=True)))
if __name__=='__main__':run()

