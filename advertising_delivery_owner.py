"""Complete approved PR19 delivery from exactly one saved analysis; no collection."""
import os,sys,json,copy,contextlib,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from stock_deploy_support import seal,error
report=dict(wb_writes=0,source_calls=0,telegram_calls=0)
hidden=io.StringIO()
try:
 with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
  from advertising_agent import agent_store as store
  from analytics.stage_one import read
  from analytics.ip_daily_recommendations import KEY,POLICY_VERSION,significant_notification_change,deliver_runtime
  reg=store.registration();approval=store.cache_get('advertising:ip:limited_rollout:v1') or {}
  if approval.get('owner_rollout_approved_head')!='2d2ccf6f7ebdfb4729fd728a61db93a219b58a0b':raise RuntimeError('Explicit exact-head owner approval missing')
  if approval.get('owner_new_delivery_approved') is not True:raise RuntimeError('New delivery approval missing')
  rows=read('analytics_snapshots',dict(source='eq.ip_limited_working_review',cabinet='eq.token_2',run_id='eq.'+os.environ['APPROVED_ANALYSIS_RUN_ID'],select='payload,id',order='id.desc',limit=1)) or []
  if not rows:raise RuntimeError('Exact approved live analytical result unavailable')
  review=rows[0]['payload'][0];daily=review['daily']
  if daily.get('wb_writes_enabled') is not False:raise RuntimeError('WB mutation guard missing')
  state=store.cache_get(KEY) or {};before=copy.deepcopy(state)
  old=(approval.get('original_decision_state') or {}).get('records',{})
  for key,record in state.get('records',{}).items():
   previous=old.get(key)
   if not previous or record.get('stage')=='confirmed':continue
   current=record.get('latest_proposal') or record.get('proposal')
   prior=previous.get('latest_proposal') or previous.get('proposal')
   if record.get('stage')==previous.get('stage') and not significant_notification_change(prior,current):
    record.update(last_notified_stage=record.get('stage'),last_notified_proposal=copy.deepcopy(current),
      last_notified_decision_due_at=record.get('decision_due_at'),cutover_baseline_only=True)
  store.cache_set(KEY,state,ttl_days=365)
  if store.cache_get(KEY)!=state:raise RuntimeError('Cutover full readback mismatch')
  previous_approval=copy.deepcopy(approval)
  approval.update(cabinet='token_2',analysis_publication_approved=True,telegram_delivery_approved=True,
    owner_id=reg['registered_by_user_id'],chat_id=reg['chat_id'],policy_version=POLICY_VERSION,
    delivery_cutover_ready=True,wb_mutations=False,forecasts=False,schedule=False)
  store.cache_set('advertising:ip:limited_rollout:v1',approval,ttl_days=365)
  if store.cache_get('advertising:ip:limited_rollout:v1')!=approval:raise RuntimeError('Delivery approval readback mismatch')
  report.update(analysis_snapshot_id=rows[0]['id'],analysis_run_id=os.environ['APPROVED_ANALYSIS_RUN_ID'],
    cutover_before=before,cutover_after=state,previous_approval=previous_approval,approval=approval)
  seal('advertising-delivery',report)
  import requests
  from urllib.parse import urlsplit
  native=requests.sessions.Session.request;dbhost=urlsplit(os.environ['SUPABASE_URL']).hostname
  def guarded(session,method,url,*args,**kwargs):
   host=urlsplit(url).hostname
   if host!=dbhost:
    if host!='api.telegram.org' or method.upper()!='POST' or not urlsplit(url).path.endswith('/sendMessage') or (kwargs.get('json') or {}).get('chat_id')!=reg['chat_id']:
     raise RuntimeError('Outside approved advertising delivery scope')
    report['telegram_calls']+=1
   return native(session,method,url,*args,**kwargs)
  requests.sessions.Session.request=guarded
  report['delivery']=deliver_runtime()
  report['final_state']=store.cache_get(KEY)
  if store.cache_get(KEY)!=report['final_state']:raise RuntimeError('Final delivery ledger readback mismatch')
  report['receipts']=[r['delivery_receipt'] for r in report['final_state'].get('records',{}).values() if r.get('delivery_receipt')]
except Exception as exc:report['error']=error(exc)
finally:
 report['private_log']=hidden.getvalue();seal('advertising-delivery',report)
 print(json.dumps({'wb_writes':0,'source_calls':0,'telegram_calls':report['telegram_calls'],'delivery':report.get('delivery'),'error_type':(report.get('error') or {}).get('type')}))
