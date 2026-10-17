"""Existing IP analysis with owner-gated delivery; no WB mutations."""
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
  import analytics.stage_one as finance_stage
  from advertising_cached_finance_reader import install as install_bounded_finance
  install_bounded_finance(finance_stage)
  from advertising_budget_evidence import install as install_dated_budgets
  install_dated_budgets()
  from advertising_current_promotion import install as install_current_promotion
  install_current_promotion()
  from datetime import datetime,timedelta,timezone
  from zoneinfo import ZoneInfo
  today=datetime.now(timezone.utc).astimezone(ZoneInfo('Europe/Moscow')).date()
  start=today-timedelta(days=7);end=today-timedelta(days=1)
  gaps=database('GET','telegram_api_cache',params={'cache_key':'eq.analytics:source_gaps','select':'payload','limit':1}) or []
  resolved=[g for g in (gaps[0]['payload'].get('gaps',[]) if gaps else []) if g.get('cabinet')=='token_2' and g.get('status')=='resolved_mpstats_daily' and str(start)<=g.get('day','')<=str(end) and g.get('mpstats_daily_snapshot_id')]
  from analytics.collect import _database_transport
  components=_database_transport('GET','analytics_snapshots',params={'source':'eq.mpstats_products_composed','cabinet':'eq.token_2','period_from':'eq.'+str(start),'period_to':'eq.'+str(end),'select':'id,components:payload->0->component_snapshot_ids','order':'id.desc','limit':1}) or []
  # Recompose only already saved disjoint days to preserve new logistics detail fields.
  from analytics.stage_one import compose_cached_finance
  report['recomposition']=compose_cached_finance('token_2',start,end,datetime.now(timezone.utc))
  finance,finance_marker=profit_rows(read,'token_2',start,end)
  from collections import Counter
  report['finance_diagnostic']={'rows':len(finance),'known_profit':sum(x.get('net_profit') is not None for x in finance.values()),'status_counts':dict(Counter(x.get('economics_status') for x in finance.values())),'marker_id':(finance_marker or {}).get('id')}
  # Supabase-only readiness wait; never starts another WB collector.
  import time
  deadline=time.monotonic()+12*60
  while True:
   config=database('GET','analytics_snapshots',params={'source':'eq.advertising_active_configuration','cabinet':'eq.token_2','select':'collected_at,id','order':'id.desc','limit':1}) or []
   if config and datetime.fromisoformat(config[0]['collected_at'].replace('Z','+00:00'))>=datetime.fromisoformat(os.environ.get('ADVERTISING_MIN_CONFIGURATION_AT') or (datetime.now(timezone.utc)-timedelta(minutes=30)).isoformat()):break
   if time.monotonic()>deadline:raise RuntimeError('Fresh approved campaign membership still pending; no analysis or delivery executed')
   time.sleep(30)
  from analytics.stage_one import daily_ready
  report['new_day_complete']=daily_ready('token_2',str(end),datetime.now(timezone.utc))
  report['membership_readiness']=config[0]
  old=database('GET','telegram_api_cache',params={'cache_key':'eq.'+KEY,'select':'payload','limit':1})
  from analytics.ip_working_mode_replay import run
  import requests,copy
  native_request=requests.sessions.Session.request
  from advertising_agent import agent_store as store
  from analytics.ip_daily_recommendations import POLICY_VERSION
  registration=store.registration()
  approval=store.cache_get('advertising:ip:limited_rollout:v1')
  if not approval:
   baseline=copy.deepcopy(old[0]['payload'] if old else dict(records={}))
   for record in baseline.get('records',{}).values():
    if record.get('stage')!='confirmed':
     record.update(last_notified_stage=record.get('stage'),
       last_notified_proposal=copy.deepcopy(record.get('latest_proposal') or record.get('proposal')),
       last_notified_decision_due_at=record.get('decision_due_at'),
       cutover_baseline_only=True)
   approval=dict(cabinet='token_2',analysis_publication_approved=True,telegram_delivery_approved=True,
     owner_id=registration['registered_by_user_id'],chat_id=registration['chat_id'],
     policy_version=POLICY_VERSION,approved_head='2d2ccf6f7ebdfb4729fd728a61db93a219b58a0b',
     merge_sha='f5e3d8a656ca8b9ca4f2a3003bfd16254a2b0a3a',cutover_at=datetime.now(timezone.utc).isoformat(),
     original_decision_state=old[0]['payload'] if old else {},wb_mutations=False,forecasts=False,schedule=False)
   store.cache_set('advertising:ip:limited_rollout:v1',approval,ttl_days=365)
   if store.cache_get('advertising:ip:limited_rollout:v1')!=approval:raise RuntimeError('Approval readback mismatch')
   store.cache_set(KEY,baseline,ttl_days=365)
   if store.cache_get(KEY)!=baseline:raise RuntimeError('Cutover baseline readback mismatch')
  report['rollout_approval']=approval
  try:run()
  finally:
   requests.sessions.Session.request=native_request
   import analytics.collect as collect
   collect.database=database
   import analytics.stage_one as stage_one
   stage_one.database=database
  new=database('GET','telegram_api_cache',params={'cache_key':'eq.'+KEY,'select':'payload','limit':1})
  report['production_decision_state_modified']=old!=new
  data=decode_rows(database('GET','analytics_snapshots',params={'source':'eq.ip_working_mode_replay','cabinet':'eq.token_2','run_id':'eq.'+RUN_ID,'select':'payload','order':'id.desc','limit':1}))
  report['analysis']=data[0]['payload'][0] if data else None
  if not report['analysis']:raise RuntimeError('No saved full analysis result')
  report['canonical_state_unchanged']=old==new
  from analytics.ip_daily_recommendations import deliver_runtime
  report['delivery']=deliver_runtime()
  report['final_decision_state']=store.cache_get(KEY)
  report['telegram_calls']=report['delivery'].get('sent',0)+len(report['delivery'].get('failures',[]))
  if store.cache_get(KEY)!=report['final_decision_state']:raise RuntimeError('Delivery state readback mismatch')
  report['delivery_receipts']=[r.get('delivery_receipt') for r in report['final_decision_state'].get('records',{}).values() if r.get('delivery_receipt')]
except Exception as exc:report['error']=error(exc)
finally:
 report['private_log']=hidden.getvalue();seal('advertising-analysis',report)
 a=report.get('analysis') or {};daily=a.get('daily') or {}
 preview={k:report.get(k) for k in ('finance_diagnostic','canonical_state_unchanged','recomposition','error','rollout_approval','delivery','delivery_receipts')}
 preview['summary']=a.get('summary');preview['campaign_summary']=a.get('campaign_summary')
 preview['pair_decisions']=[{k:t.get(k) for k in ('article','nm_id','campaign_id','outcome','final_status','reason','actions','shop_profit','advertising_profit','experiment_result','query_totals')}|{'blockers':[{'metric':b['metric'],'reason':b['reason']} for b in t.get('blockers',[])]} for t in daily.get('pair_decision_trace',[])]
 preview['actions']=[{k:x.get(k) for k in ('article','campaign_id','kind','action','reason','expected_effect','criterion','risk')} for x in daily.get('actions',[])]
 preview['new_messages']=(a.get('new_preview') or {}).get('messages',[])
 preview['budget_analysis']=daily.get('budget_analysis')
 preview['current_promotion_control']=daily.get('current_promotion_control')
 preview['financial_risk']=daily.get('financial_risk')
 preview['expense_test_candidates']=daily.get('expense_test_candidates')
 preview['analysis_run_id']=RUN_ID
 preview['new_day_complete']=report.get('new_day_complete')
 preview['final_decision_state']=report.get('final_decision_state')
 preview['regression_tail']=(report.get('targeted_regressions') or {}).get('log','')[-500:]
 seal('advertising-preview',preview)
 delivery_failures=(report.get('delivery') or {}).get('failures') or []
 business_status='failed' if report.get('error') else ('incomplete' if not report.get('analysis') or delivery_failures else 'complete')
 print(json.dumps({'analysis_saved':bool(report.get('analysis')),'business_status':business_status,
  'reason':report.get('error',{}).get('type') or ('delivery_unconfirmed' if delivery_failures else ('analysis_not_saved' if not report.get('analysis') else None)),
  'delivery_unconfirmed_count':len(delivery_failures),'error_type':report.get('error',{}).get('type'),'wb_writes':0,'telegram_calls':report.get('telegram_calls',0)}))
