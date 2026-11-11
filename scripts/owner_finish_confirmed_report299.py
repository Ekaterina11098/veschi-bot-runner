"""Finish only the already human-confirmed report299, using canonical executor and receipts."""
import json,os
from china_loss_execute import IO
from china_daily_ad_actions import process_and_deliver
from china_loss_control import APPROVAL,PLAN
if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main required')
io=IO();a=io.get(APPROVAL+'299')
if not a or a.get('job_id')!=299 or a.get('button_confirmation')!='323d404750bc541ee303bfbe-5122667182':raise ValueError('Exact confirmed approval299 missing')
p=io.get(PLAN+a['plan_id'])
if not p or p.get('parent_plan_id')!='daily-2026-11-11-midday-full-v3-drr-0' or len(p.get('items',[]))!=1:raise ValueError('Exact parent selection changed')
item=p['items'][0]
if (item.get('campaign_id'),item.get('nm_id'),item.get('old_minor'),item.get('target_minor'))!=(41155909,1473243898,23,25):raise ValueError('Unexpected selected action')
if a.get('status')=='completed':
 print(json.dumps(dict(status='already_completed',job_id=299,execution_key=a.get('execution_key'))))
else:
 if a.get('status')!='approved':raise ValueError('Approval not executable')
 e=process_and_deliver(io,a,p)
 print(json.dumps(dict(status=e['status'],job_id=299,items=[dict(id=x['id'],status=x['status'])for x in e['items']],wb_writes=e['wb_writes'])))
