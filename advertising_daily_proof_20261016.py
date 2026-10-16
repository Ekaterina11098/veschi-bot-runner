"""Read back exact saved controlled analysis only; no sources or delivery."""
import os,sys,json,hashlib,contextlib,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from stock_deploy_support import seal,error
report=dict(wb_calls=0,wb_writes=0,telegram_calls=0,external_sources=0)
hidden=io.StringIO()
try:
 with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
  import requests
  from urllib.parse import urlsplit
  native=requests.sessions.Session.request;host=urlsplit(os.environ['SUPABASE_URL']).hostname
  def guard(session,method,url,*args,**kwargs):
   if method.upper()!='GET' or urlsplit(url).hostname!=host:raise RuntimeError('Proof allows Supabase GET only')
   return native(session,method,url,*args,**kwargs)
  requests.sessions.Session.request=guard
  from analytics.collect import _database_transport as db
  from analytics.payload_storage import decode_rows
  def exact(ident):
   args=dict(id='eq.'+str(ident),select='id,source,status,run_id,period_from,period_to,payload')
   one=db('GET','analytics_snapshots',params=args)
   two=db('GET','analytics_snapshots',params=args)
   if one!=two or len(one)!=1:raise RuntimeError('Full exact row readback mismatch')
   decoded=decode_rows(one)[0]
   report.setdefault('readback',[]).append(dict(id=ident,source=one[0]['source'],run_id=one[0]['run_id'],sha256=one[0]['payload'][0].get('sha256'),full_equal=True,period_from=one[0]['period_from'],period_to=one[0]['period_to']))
   return decoded['payload'][0]
  replay=exact(17622);canonical=exact(17624)
  if replay['daily']['financial_risk']!=canonical['daily']['financial_risk']:raise RuntimeError('Canonical risk differs from calculation')
  d=canonical['daily'];risk=d['financial_risk']
  report.update(summary=replay['summary'],period_from=risk['period_from'],period_to=risk['period_to'],
   financial_risk=risk,actions=d.get('actions',[]),budget_analysis=d.get('budget_analysis'),
   expense_test_candidates=d.get('expense_test_candidates'),daily_flags={k:d.get(k) for k in ('wb_writes_enabled','financial_risk_delivery_enabled','all_active_campaigns_assessed')})
  from advertising_agent import agent_store as store
  report['daily_approval']=store.cache_get('advertising:ip:daily_rollout:v1')
  report['daily_execution']=store.cache_get('advertising:ip:daily_run:v1:2026-10-16')
  report['decision_state']=store.cache_get('advertising:ip_pair_decisions:token_2:v1')
  report['delivery_state_readback_equal']=report['decision_state']==store.cache_get('advertising:ip_pair_decisions:token_2:v1')
  if not report['delivery_state_readback_equal']:raise RuntimeError('Delivery state changed during full readback')
  conf=db('GET','analytics_snapshots',params=dict(id='eq.17613',select='id,payload,collected_at'))[0]
  focus={1123677454,1007948808,320248210}
  report['focus_current_controls']=[dict(campaign_id=a['id'],settings=a.get('settings'),nm_setting=n,observed_at=conf['collected_at'],snapshot_id=17613) for a in conf['payload']['adverts'] for n in a.get('nm_settings',[]) if n['nm_id'] in focus]
  report['budget_snapshot']=db('GET','analytics_snapshots',params=dict(source='eq.advertising_campaign_budgets',cabinet='eq.token_2',select='id,payload,collected_at',order='id.desc',limit=1))[0]
  report['verified']=True
except Exception as exc:report['error']=error(exc)
finally:
 report['private_log']=hidden.getvalue()
 seal('advertising-daily-proof',report)
 print(json.dumps(dict(verified=report.get('verified',False),error_type=report.get('error',{}).get('type'),source_calls=0,wb_writes=0,telegram_calls=0)))
