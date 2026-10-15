"""Recompute existing IP pipeline on main+PR19 without deliveries or WB writes."""
import os,sys,json,subprocess,contextlib,io
from pathlib import Path
from stock_deploy_support import seal,error
root=Path(__file__).parent;source=root/'combined'
report={'wb_writes':0,'telegram_calls':0,'source_calls':0,'production_decision_state_modified':False}
hidden=io.StringIO()
try:
 for args in (['git','fetch',str(root/'pr19'),'HEAD'],['git','-c','user.name=ReadOnlyAcceptance','-c','user.email=acceptance@invalid.local','merge','--no-commit','--no-ff','FETCH_HEAD']):
  p=subprocess.run(args,cwd=source,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  if p.returncode:raise RuntimeError('Combined source merge failed: '+p.stdout)
 os.chdir(source);sys.path.insert(0,str(source))
 with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
  testcode="""import socket,unittest,sys
from unittest.mock import patch
suite=unittest.TestSuite()
for pattern in ('test_ip_unknown_identity_controls.py','test_ip_price_event_analysis.py','test_ip_full_offline_pipeline.py','test_ip_campaign_audit.py','test_ip_complete_cache_catalog.py','test_ip_missing_catalog_coverage.py','test_payload_storage.py'):
 suite.addTests(unittest.defaultTestLoader.discover('tests',pattern=pattern))
with patch.object(socket.socket,'connect',side_effect=AssertionError('External test network forbidden')):
 result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
"""
  testenv={k:v for k,v in os.environ.items() if not any(k.startswith(prefix) for prefix in ('SUPABASE_','WB_','MPSTATS_','TELEGRAM_','MOYSKLAD_','ADVERTISING_','OPENAI_'))}
  tested=subprocess.run([sys.executable,'-c',testcode],cwd=source,env=testenv,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  report['targeted_regressions']={'exit':tested.returncode,'log':tested.stdout}
  if tested.returncode:raise RuntimeError('Targeted regression failed')
  from analytics.collect import database,RUN_ID
  from analytics.payload_storage import decode_rows
  from analytics.ip_daily_recommendations import KEY
  from analytics.mpstats_primary import profit_rows
  from analytics.stage_one import read
  from datetime import datetime,timedelta,timezone
  from zoneinfo import ZoneInfo
  today=datetime.now(timezone.utc).astimezone(ZoneInfo('Europe/Moscow')).date()
  start=today-timedelta(days=7);end=today-timedelta(days=1)
  gaps=database('GET','telegram_api_cache',params={'cache_key':'eq.analytics:source_gaps','select':'payload','limit':1}) or []
  resolved=[g for g in (gaps[0]['payload'].get('gaps',[]) if gaps else []) if g.get('cabinet')=='token_2' and g.get('status')=='resolved_mpstats_daily' and str(start)<=g.get('day','')<=str(end) and g.get('mpstats_daily_snapshot_id')]
  from analytics.collect import _database_transport
  components=_database_transport('GET','analytics_snapshots',params={'source':'eq.mpstats_products_composed','cabinet':'eq.token_2','period_from':'eq.'+str(start),'period_to':'eq.'+str(end),'select':'id,components:payload->0->component_snapshot_ids','order':'id.desc','limit':1}) or []
  if any(g['mpstats_daily_snapshot_id'] not in (components[0].get('components',[]) if components else []) for g in resolved):
   from analytics.stage_one import compose_cached_finance
   report['recomposition']=compose_cached_finance('token_2',start,end,datetime.now(timezone.utc))
  finance,finance_marker=profit_rows(read,'token_2',start,end)
  from collections import Counter
  report['finance_diagnostic']={'rows':len(finance),'known_profit':sum(x.get('net_profit') is not None for x in finance.values()),'status_counts':dict(Counter(x.get('economics_status') for x in finance.values())),'marker_id':(finance_marker or {}).get('id')}
  old=database('GET','telegram_api_cache',params={'cache_key':'eq.'+KEY,'select':'payload','limit':1})
  from analytics.ip_working_mode_replay import run
  run()
  new=database('GET','telegram_api_cache',params={'cache_key':'eq.'+KEY,'select':'payload','limit':1})
  if old!=new:raise RuntimeError('Canonical decision state changed unexpectedly')
  data=decode_rows(database('GET','analytics_snapshots',params={'source':'eq.ip_working_mode_replay','cabinet':'eq.token_2','run_id':'eq.'+RUN_ID,'select':'payload','order':'id.desc','limit':1}))
  report['analysis']=data[0]['payload'][0] if data else None
  if not report['analysis']:raise RuntimeError('No saved full analysis result')
  report['canonical_state_unchanged']=True
except Exception as exc:report['error']=error(exc)
finally:
 report['private_log']=hidden.getvalue();seal('advertising-analysis',report)
 a=report.get('analysis') or {};daily=a.get('daily') or {}
 preview={k:report.get(k) for k in ('finance_diagnostic','canonical_state_unchanged','recomposition','error')}
 preview['summary']=a.get('summary');preview['campaign_summary']=a.get('campaign_summary')
 preview['pair_decisions']=[{k:t.get(k) for k in ('article','nm_id','campaign_id','outcome','final_status','reason','actions','shop_profit','advertising_profit','experiment_result','query_totals')}|{'blockers':[{'metric':b['metric'],'reason':b['reason']} for b in t.get('blockers',[])]} for t in daily.get('pair_decision_trace',[])]
 preview['actions']=[{k:x.get(k) for k in ('article','campaign_id','kind','action','reason','expected_effect','criterion','risk')} for x in daily.get('actions',[])]
 preview['new_messages']=(a.get('new_preview') or {}).get('messages',[])
 preview['budget_analysis']=daily.get('budget_analysis')
 preview['regression_tail']=(report.get('targeted_regressions') or {}).get('log','')[-500:]
 seal('advertising-preview',preview)
 print(json.dumps({'analysis_saved':bool(report.get('analysis')),'error_type':report.get('error',{}).get('type'),'wb_writes':0,'telegram_calls':0}))
