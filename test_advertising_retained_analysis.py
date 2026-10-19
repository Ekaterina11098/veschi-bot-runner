"""Targeted tests of the actual runner functions. No credentials, collectors, or delivery."""
import ast,copy,io,json,unittest
from pathlib import Path
from datetime import datetime,timezone
from contextlib import redirect_stdout
from advertising_daily_runtime_guard import retained_analysis_profile,verify_retained_metadata,independent_statuses,merge_telemetry
from advertising_budget_evidence import compact_report
NOW=datetime(2026,10,19,9,tzinfo=timezone.utc)
def extract(path,names,env):
 tree=ast.parse(Path(path).read_text(encoding='utf-8'))
 exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),path,'exec'),env)
 return env
def previous():
 return dict(day='2026-10-19',run_id='39202750461:1',status='failed',failed_stage='analysis_and_delivery',analysis_complete=False,
  stages=[dict(name=n,status='incomplete' if n=='budgets' else 'complete',result={}) for n in ('source','source_gaps','membership','budgets')],
  telemetry=dict(attempts={'39202750461:1':{'source':dict(calls=1,decoded_response_bytes=62419586,request_body_bytes=0,complete=True)}}))
def profile():
 return dict(enabled=True,mode='retained_analysis_only',day='2026-10-19',from_run_id='39202750461:1',private_source_sha='reviewed',
  wb_mutations=False,forecasts=False,telegram_delivery=False,source_collection=False,input_high_watermark=18458,retained_manifest={'snapshots':[{'id':1}]})
class Continuation(unittest.TestCase):
 def test_exact_terminal_manifest_profile_and_flags(self):
  self.assertTrue(retained_analysis_profile(previous(),profile(),'2026-10-19','reviewed'))
  for field,value in [('day','2026-10-18'),('from_run_id','39202750461:2'),('source_collection',True),('telegram_delivery',True),('retained_manifest',{}),('private_source_sha','wrong')]:
   p=profile();p[field]=value
   with self.assertRaises(PermissionError):retained_analysis_profile(previous(),p,'2026-10-19','reviewed')
  for field,value in [('status','running'),('analysis_complete',True)]:
   p=previous();p[field]=value
   with self.assertRaises(PermissionError):retained_analysis_profile(p,profile(),'2026-10-19','reviewed')
 def test_only_analysis_same_claim_no_source_budget_or_notification_replay(self):
  state=previous();saved=[copy.deepcopy(state)];calls=[]
  def get(k):return copy.deepcopy(saved[0])
  def cas(k,expected,value):
   self.assertEqual(saved[0],expected);saved[0]=copy.deepcopy(value);return True
  def forbidden():self.fail('Completed stage or budget collector replayed')
  def analyze():
   calls.append('analysis')
   return dict(business_status='incomplete',analysis_saved=True,notification_status='not_requested',reason='campaign_metrics_missing',
    telemetry=dict(calls=3,decoded_response_bytes=100,request_body_bytes=0,complete=True))
  ns=extract('advertising_daily_owner.py',{'execute_day'},{'datetime':datetime,'timezone':timezone})
  result=ns['execute_day'](get,None,{n:analyze if n=='analysis_and_delivery' else forbidden for n in ('source','source_gaps','membership','budgets','analysis_and_delivery','budget_completion')},
   'controlled:1',now=NOW,single_writer=True,resume_from='39202750461:1',cas=cas,analysis_only=True)
  self.assertEqual(calls,['analysis']);self.assertEqual(result['analysis_status'],'complete')
  self.assertEqual(result['status'],'incomplete');self.assertEqual(result['notification_status'],'not_requested')
  self.assertEqual(result['budget_status'],'pending');self.assertEqual(result['telemetry']['decoded_response_bytes'],62419686)
  self.assertEqual(result['telemetry']['attempts']['39202750461:1'],state['telemetry']['attempts']['39202750461:1'])
  self.assertEqual(result['stages'][:4],state['stages'])
 def test_manifest_missing_row_or_changed_metadata_stops(self):
  row=dict(id=2,source='retained',cabinet='token_2',collected_at='stamp',period_from='2026-10-18',period_to='2026-10-18',status='complete')
  self.assertTrue(verify_retained_metadata(lambda *a:[row],dict(snapshots=[row])))
  with self.assertRaises(PermissionError):verify_retained_metadata(lambda *a:[],dict(snapshots=[row]))
  with self.assertRaises(PermissionError):verify_retained_metadata(lambda *a:[dict(row,status='partial')],dict(snapshots=[row]))
 def test_registry_and_index_hashes_are_checked(self):
  import hashlib
  value={'records':{'existing':{'delivery_receipt':{'message_id':168}}}}
  sha=hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  row=dict(id=2,source='retained',cabinet='token_2',collected_at='stamp',period_from='2026-10-18',period_to='2026-10-18',status='complete')
  def read(t,p):return [row] if t=='analytics_snapshots' else [{'payload':value}]
  m=dict(snapshots=[row],caches=[dict(cache_key='advertising:ip_pair_decisions:token_2:v1',sha256=sha)])
  self.assertTrue(verify_retained_metadata(read,m));value['records']['new']={}
  with self.assertRaises(PermissionError):verify_retained_metadata(read,m)
class Summary(unittest.TestCase):
 def test_failed_regression_produces_durable_summary_and_nonzero(self):
  text=Path('advertising_analysis_owner.py').read_text(encoding='utf-8');tree=ast.parse(text)
  assignment=next(i for i,n in enumerate(tree.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='RUN_ID' for t in n.targets))
  first_try=next(i for i,n in enumerate(tree.body) if isinstance(n,ast.Try))
  self.assertLess(assignment,first_try)
  ns=extract('advertising_analysis_owner.py',{'analysis_business_summary'},{})
  ns.update(report={'error':{'type':'RuntimeError'},'failure_stage':'targeted_regressions','targeted_regressions':{'log':'failed'}},hidden=io.StringIO(),RUN_ID='39202750461:1',json=json,seal=lambda *a:None)
  body=tree.body[first_try].finalbody
  output=io.StringIO()
  with redirect_stdout(output),self.assertRaises(SystemExit) as exc:exec(compile(ast.Module(body=body,type_ignores=[]),'actual-finally','exec'),ns)
  self.assertEqual(exc.exception.code,1);got=json.loads(output.getvalue().splitlines()[-1])
  self.assertEqual(got['failed_step'],'targeted_regressions');self.assertEqual(got['business_status'],'failed')
 def test_missing_metrics_not_complete_or_zero(self):
  fn=extract('advertising_analysis_owner.py',{'analysis_business_summary'},{})['analysis_business_summary']
  result=fn({'analysis':{'saved':True},'compact_report':{'complete':False},'delivery':{'reason':'retained_preview_only'}})
  self.assertTrue(result['analysis_saved']);self.assertEqual(result['business_status'],'incomplete')
  self.assertEqual(result['reason'],'campaign_metrics_missing');self.assertEqual(result['notification_status'],'not_requested')
class Compact(unittest.TestCase):
 def data(self):
  return dict(period_from='2026-10-12',period_to='2026-10-18',campaign_review={'rows':[
   dict(campaign_id=1,article='A',facts={'spend':70,'direct_orders':1,'direct_turnover':700}),
   dict(campaign_id=2,article='B',facts={'spend':None,'direct_orders':None,'direct_turnover':None})]},
   budget_analysis=[dict(campaign_id=1,balance=100,balance_observed_at='2026-10-19T08:00:00+00:00',balance_is_current=True),
    dict(campaign_id=2,balance=200,balance_observed_at='2026-10-17T08:00:00+00:00',balance_is_current=False)])
 def test_all_campaigns_unknown_not_normal_and_no_stale_capacity(self):
  r=compact_report(self.data(),NOW,True)
  self.assertEqual(r['campaign_count'],2);self.assertFalse(r['complete'])
  self.assertIn('A — 10,00%',r['messages'][0]);self.assertEqual(r['details'][0]['scenario_days'],10)
  self.assertIsNone(r['details'][1]['scenario_days']);self.assertIn('исторический',r['messages'][1])
  self.assertIn('Нет данных',r['messages'][1]);self.assertNotIn('в пределах',r['messages'][1])
 def test_zero_orders_not_zero_drr(self):
  d=self.data();d['campaign_review']['rows'][0]['facts'].update(direct_orders=0,direct_turnover=0)
  r=compact_report(d,NOW,True);self.assertIn('нет прямых заказов',r['messages'][0]);self.assertNotIn('ДРР 0,00%',r['messages'][0])
 def test_no_scenario_without_explicit_option_or_known_spend(self):
  self.assertIsNone(compact_report(self.data(),NOW)['details'][0]['scenario_days'])
  d=self.data();d['campaign_review']['rows'][0]['facts']['spend']=0
  self.assertIsNone(compact_report(d,NOW,True)['details'][0]['scenario_days'])
if __name__=='__main__':unittest.main()
