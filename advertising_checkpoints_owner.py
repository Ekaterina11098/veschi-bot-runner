"""Cached native MPStats checkpoint assessment; no source or marketplace requests."""
import os,sys,json,contextlib,io,subprocess
from pathlib import Path
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from stock_deploy_support import seal,error
root=Path(__file__).parent;source=root/'private-source';sys.path.insert(0,str(source))
report={'source_calls':0,'wb_writes':0,'telegram_calls':0,'canonical_experiment_rows_modified':False}
hidden=io.StringIO()
try:
 with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
  import socket,unittest
  from unittest.mock import patch
  os.chdir(source)
  tests=unittest.defaultTestLoader.discover('tests',pattern='test_ip_native_checkpoints.py')
  with patch.object(socket.socket,'connect',side_effect=AssertionError('No network in regression')):
   passed=unittest.TextTestRunner(verbosity=2).run(tests)
  if not passed.wasSuccessful():raise RuntimeError('Native checkpoint regression failed')
  from analytics.collect import database,_database_transport,RUN_ID
  from analytics.payload_storage import decode_rows
  from advertising_agent.experiments import native_daily_checkpoint
  from urllib.parse import urlsplit
  import requests
  native=requests.sessions.Session.request;host=urlsplit(os.environ['SUPABASE_URL']).hostname
  def guarded(session,method,url,*args,**kwargs):
   if urlsplit(url).hostname!=host:raise RuntimeError('Cached checkpoint source requests forbidden')
   return native(session,method,url,*args,**kwargs)
  requests.sessions.Session.request=guarded
  now=datetime.now(timezone.utc);completed=now.astimezone(ZoneInfo('Europe/Moscow')).date()-timedelta(days=1)
  exps=database('GET','advertising_experiments',params={'cabinet':'eq.token_2','status':'eq.active','select':'id,cabinet,campaign_id,nm_id,article,started_at,baseline,old_value,new_value,experiment_type','order':'id.asc','limit':100}) or []
  before=json.dumps(exps,sort_keys=True,default=str)
  catalogs=decode_rows(database('GET','analytics_snapshots',params={'source':'eq.mpstats_campaign_catalog','cabinet':'eq.token_2','period_from':'eq.'+str(completed-timedelta(days=6)),'period_to':'eq.'+str(completed),'select':'id,payload','order':'id.desc','limit':20})) or []
  mapping={}
  for row in catalogs:
   for cat in row.get('payload') or []:
    for r in cat.get('rows',[]):mapping[r.get('wb_id')]=r.get('id')
  pairs={(mapping.get(e['campaign_id']),e['nm_id']) for e in exps};ids=[];offset=0
  while True:
   page=_database_transport('GET','analytics_snapshots',params={'source':'eq.mpstats_campaign_report','cabinet':'eq.token_2','period_to':'gte.2026-10-09','select':'id,scope_nm_id:payload->0->>scope_nm_id,campaign_id:payload->0->>campaign_id,kind:payload->0->>report','order':'id.desc','limit':100,'offset':offset}) or []
   for marker in page:
    try:pair=(int(marker.get('campaign_id')),int(marker.get('scope_nm_id')))
    except (ValueError,TypeError):continue
    if marker.get('kind')=='days' and pair in pairs:ids.append(marker['id'])
   if len(page)<100:break
   offset+=100
  reports=[]
  for ident in ids:
   rows=decode_rows(database('GET','analytics_snapshots',params={'id':'eq.'+str(ident),'select':'id,payload','limit':1}))
   reports.extend(rows[0]['payload'])
  outputs=[]
  for exp in exps:
   cid=mapping.get(exp['campaign_id'])
   if cid is None:outputs.append({'experiment_id':exp['id'],'article':exp['article'],'reason':'Campaign identity not mapped; no guessed zero'});continue
   outputs.append({'experiment_id':exp['id'],'article':exp['article'],'campaign_id':exp['campaign_id'],'checkpoints':[native_daily_checkpoint(exp,h,reports,cid,completed) for h in (24,48,72)]})
  after=database('GET','advertising_experiments',params={'cabinet':'eq.token_2','status':'eq.active','select':'id,cabinet,campaign_id,nm_id,article,started_at,baseline,old_value,new_value,experiment_type','order':'id.asc','limit':100}) or []
  if before!=json.dumps(after,sort_keys=True,default=str):raise RuntimeError('Canonical experiment data changed during read-only assessment')
  report.update(completed_day=str(completed),experiments=outputs,native_report_ids=ids,canonical_rows_unchanged=True)
  body=dict(source='ip_owner_checkpoint_preview',cabinet='token_2',run_id=RUN_ID,period_from=str(completed-timedelta(days=6)),period_to=str(completed),payload=[report],status='partial',detail='Native MPStats observations; actual intervention time remains unconfirmed; baseline untouched')
  database('POST','analytics_snapshots',body=body)
  got=database('GET','analytics_snapshots',params={'source':'eq.ip_owner_checkpoint_preview','run_id':'eq.'+RUN_ID,'select':'payload','order':'id.desc','limit':1}) or []
  if not got or got[0]['payload']!=[report]:raise RuntimeError('Checkpoint result full readback mismatch')
  report['readback_verified']=True
except Exception as exc:report['error']=error(exc)
finally:
 report['private_log']=hidden.getvalue();seal('advertising-checkpoints',report)
 print(json.dumps({'experiments':len(report.get('experiments',[])),'readback_verified':report.get('readback_verified',False),'error_type':report.get('error',{}).get('type'),'source_calls':0,'wb_writes':0,'telegram_calls':0}))
