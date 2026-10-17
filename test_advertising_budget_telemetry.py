"""Offline regression of pending budgets, independent statuses and durable traffic."""
import ast,copy,json,os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from unittest.mock import patch
from advertising_daily_runtime_guard import budget_pending,merge_telemetry,StageTraffic,independent_statuses
NOW=datetime(2026,10,17,10,tzinfo=timezone.utc)
tree=ast.parse(Path('advertising_daily_owner.py').read_text())
ns={'datetime':datetime,'timezone':timezone}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='execute_day'],type_ignores=[]),'actual-execute-day','exec'),ns)
execute=ns['execute_day']
class BudgetStateTests(unittest.TestCase):
 def test_two_unknown_current_balances_not_zero(self):
  p={'items':[dict(campaign_id=1,available=True,observed_at=NOW.isoformat(),total=10),dict(campaign_id=2,available=False,observed_at=(NOW-timedelta(days=1)).isoformat(),total=1514)],'next_retry_at':(NOW+timedelta(seconds=905)).isoformat()}
  q=budget_pending(p,[1,2,3],NOW)
  self.assertEqual(q['pending_campaign_ids'],[2,3]);self.assertEqual(q['next_allowed_at'],p['next_retry_at']);self.assertTrue(all(x['current_value_unknown'] for x in q['requests']))
 def test_inactive_ids_removed_not_resumed(self):
  self.assertEqual(budget_pending({'items':[]},[7],NOW)['pending_campaign_ids'],[7])
 def test_future_or_stale_not_fresh(self):
  for t in [NOW+timedelta(seconds=1),NOW-timedelta(hours=6)]:
   q=budget_pending({'items':[dict(campaign_id=1,available=True,observed_at=t.isoformat())]},[1],NOW);self.assertFalse(q['complete'])
 def test_malformed_retry_time_fail_closed(self):
  with self.assertRaises(ValueError):budget_pending({'next_retry_at':'wrong'},[1],NOW)
class ResumeTests(unittest.TestCase):
 def setUp(self):
  self.names=['source','source_gaps','membership','budgets','analysis_and_delivery','budget_completion']
  self.state={'day':'2026-10-17','run_id':'39015462359:1','status':'incomplete','analysis_complete':True,'stages':[dict(name=n,status='complete',result={}) for n in self.names]}
  self.state['stages'][3]['status']='incomplete';self.state['stages'][5]['status']='incomplete'
  self.state['stages'][4]['result']={'analysis_saved':True,'delivery_unconfirmed_count':0}
  self.calls=[]
 def runit(self,result=None):
  def cas(k,old,new):
   if old!=self.state:return False
   self.state=copy.deepcopy(new);return True
  def step():self.calls.append('budget');return result or {'business_status':'complete'}
  stages={n:lambda:(_ for _ in ()).throw(AssertionError('Nonbudget stage replay')) for n in self.names}
  stages['budget_completion']=step
  return execute(lambda k:copy.deepcopy(self.state),None,stages,'new:1',NOW,single_writer=True,cas=cas,resume_from='39015462359:1',budget_only=True)
 def test_only_budget_runs_analysis_and_notifications_stay_complete(self):
  r=self.runit();self.assertEqual(self.calls,['budget']);self.assertEqual(r['analysis_status'],'complete');self.assertEqual(r['notification_status'],'complete');self.assertEqual(r['budget_status'],'complete');self.assertEqual(r['status'],'complete');self.assertEqual(len(r['stages']),6)
 def test_pending_budget_preserves_successful_analysis(self):
  r=self.runit({'business_status':'incomplete','next_allowed_at':'2026-10-17T10:24:08+00:00','pending_campaign_ids':[37155100,39410834]})
  self.assertEqual(r['analysis_status'],'complete');self.assertEqual(r['notification_status'],'complete');self.assertEqual(r['budget_status'],'pending');self.assertEqual(r['status'],'incomplete')
 def test_false_analysis_flag_cannot_bypass_saved_stage(self):
  self.state['stages']=self.state['stages'][:3]
  with self.assertRaises(PermissionError):self.runit()
  self.assertEqual(self.calls,[])
 def test_no_complete_analysis_no_budget_call(self):
  self.state['analysis_complete']=False
  with self.assertRaises(PermissionError):self.runit()
  self.assertEqual(self.calls,[])
 def test_active_day_claim_not_stolen(self):
  self.state['status']='running'
  with self.assertRaises(PermissionError):self.runit()
 def test_wrong_attempt_not_accepted(self):
  self.state['run_id']='39015462359:2'
  with self.assertRaises(PermissionError):self.runit()
 def test_repeat_without_explicit_resume_does_not_run(self):
  r=execute(lambda k:self.state,None,{},'new',NOW,single_writer=True,cas=lambda *a:False)
  self.assertTrue(r['skipped'])
class TelemetryTests(unittest.TestCase):
 def test_idempotent_stage_and_attempt_totals(self):
  s={};a=dict(complete=True,calls=2,decoded_response_bytes=100,request_body_bytes=7)
  merge_telemetry(s,'r:1','source',a);merge_telemetry(s,'r:1','source',a)
  merge_telemetry(s,'r:1','source_gaps',dict(a,decoded_response_bytes=50))
  merge_telemetry(s,'r:2','budget',dict(a,decoded_response_bytes=20))
  self.assertEqual(s['telemetry']['decoded_response_bytes'],170);self.assertEqual(len(s['telemetry']['attempts']),2)
 def test_changed_stage_counter_rejected(self):
  s={};merge_telemetry(s,'r:1','source',dict(calls=1))
  with self.assertRaises(RuntimeError):merge_telemetry(s,'r:1','source',dict(calls=2))
 def test_legacy_unmeasured_not_called_full_total(self):
  s={'telemetry':{'attempts':{},'legacy_unmeasured':True}}
  self.assertFalse(merge_telemetry(s,'r:2','budget',dict(complete=True))['coverage_complete'])
 def test_response_bytes_include_non200_and_requests(self):
  with tempfile.TemporaryDirectory() as t:
   meter=StageTraffic(Path(t)/'stage.json')
   response=SimpleNamespace(content=b'bad',request=SimpleNamespace(body='request'),status_code=429)
   self.assertIs(meter.request(lambda *a,**k:response,None,'GET','https://advert-api.wildberries.ru/adv/v1/budget'),response)
   self.assertEqual(meter.value['decoded_response_bytes'],3);self.assertEqual(meter.value['request_body_bytes'],7)
   self.assertFalse(meter.value['complete']);self.assertFalse(meter.value['in_flight'])
 def test_failure_is_persisted_without_invented_response_bytes(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'stage.json';m=StageTraffic(p)
   def fail(*a,**k):raise TimeoutError()
   with self.assertRaises(TimeoutError):m.request(fail,None,'GET','https://example.test')
   v=json.loads(p.read_text());self.assertEqual(v['failed_calls'],1);self.assertEqual(v['decoded_response_bytes'],0);self.assertFalse(v['complete'])
 def test_cumulative_100mb_blocks_new_source_but_allows_durability(self):
  with tempfile.TemporaryDirectory() as t:
   m=StageTraffic(Path(t)/'stage.json',baseline=100000000)
   with self.assertRaises(RuntimeError):m.request(lambda *a:None,None,'POST','https://mcp.mpstats.io',json={'params':{'name':'lk_wb_products'}})
   r=SimpleNamespace(content=b'',request=SimpleNamespace(body=None))
   m.request(lambda *a,**k:r,None,'GET','https://db.supabase.co/rest/v1/telegram_api_cache')
 def test_no_secrets_or_urls_in_records(self):
  with tempfile.TemporaryDirectory() as t:
   m=StageTraffic(Path(t)/'stage.json');r=SimpleNamespace(content=b'',request=SimpleNamespace(body=b'secret'))
   m.request(lambda *a,**k:r,None,'GET','https://x.test?a=secret',headers={'Authorization':'secret'})
   self.assertNotIn('secret',json.dumps(m.value))
class InstrumentationIntegration(unittest.TestCase):
 def test_actual_wrapper_measures_stage_and_flushes_finally(self):
  from advertising_daily_runtime_guard import run_instrumented
  import requests
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);script=root/'sample.py';out=root/'traffic.json'
   script.write_text("import requests\nrequests.get('https://example.test/no-secrets')\n")
   response=requests.Response();response.status_code=200;response._content=b'hello'
   with patch.object(requests.sessions.Session,'send',return_value=response):run_instrumented(str(script),str(out),0)
   m=json.loads(out.read_text());self.assertEqual(m['decoded_response_bytes'],5);self.assertEqual(m['calls'],1);self.assertTrue(m['complete'])
 def test_cannot_call_network_if_local_telemetry_is_unwritable(self):
  with tempfile.TemporaryDirectory() as t:
   m=StageTraffic(Path(t)/'traffic.json');called=[]
   with patch.object(m,'persist',side_effect=OSError('disk')):
    with self.assertRaises(OSError):m.request(lambda *a:called.append(1),None,'GET','https://example.test')
   self.assertEqual(called,[])
class ActualBudgetWorker(unittest.TestCase):
 def worker(self,mode='normal',single=False):
  import runpy,requests,types,sys
  from contextlib import redirect_stdout
  import io
  active=list(range(11));state={'advertising_active_configuration':{'collected_at':datetime.now(timezone.utc).isoformat(),'payload':{'campaign_ids':active}},'advertising_campaign_budgets':{'payload':{'items':[]}}}
  calls=[];seals=[];stub=types.ModuleType('stock_deploy_support');stub.seal=lambda n,v:seals.append(copy.deepcopy(v));stub.error=lambda e:{'type':type(e).__name__}
  c=types.SimpleNamespace()
  def latest(source,status=None):
   if mode=='storage_failure' and source=='advertising_budget_pending':return None
   return state.get(source)
  def save(source,payload,status=None):state[source]={'payload':copy.deepcopy(payload)}
  def collect(token,ids):
   calls.append(1);items=state['advertising_campaign_budgets']['payload'].get('items',[])
   if len(calls)>5:
    fresh={x['campaign_id'] for x in items};cid=next(i for i in ids if i not in fresh)
    items=items+[dict(campaign_id=cid,available=True,observed_at=c.NOW.isoformat(),total=7)]
   state['advertising_campaign_budgets']={'payload':{'items':items,'complete':len(items)==len(ids)}}
  c.latest=latest;c.save=save;c.collect_campaign_budgets=collect
  if mode=='pause':state['advertising_campaign_budgets']['payload']['next_retry_at']=(datetime.now(timezone.utc)+timedelta(seconds=905)).isoformat()
  if mode=='retained_pause':state['advertising_budget_pending']={'payload':{'campaign_ids':active,'pending_campaign_ids':active,'next_allowed_at':(datetime.now(timezone.utc)+timedelta(seconds=905)).isoformat()}}
  pkg=types.ModuleType('advertising_agent');pkg.collect_ip=c
  native=requests.sessions.Session.request
  try:
   with patch.dict(sys.modules,{'stock_deploy_support':stub,'advertising_agent':pkg}),patch.dict(os.environ,{'SUPABASE_URL':'https://example.supabase.co','WB_TOKEN_2':'fake','ADVERTISING_BUDGET_STEP_ONLY':'true' if single else 'false'}),redirect_stdout(io.StringIO()):
    runpy.run_path('advertising_budgets_owner.py',run_name='__main__')
  finally:requests.sessions.Session.request=native
  return calls,seals[-1]
 def test_five_rate_deferrals_do_not_exhaust_before_eleven_successes(self):
  calls,r=self.worker();self.assertTrue(r.get('complete'),str(r));self.assertEqual(len(calls),16);self.assertTrue(r['pending_queue']['complete'])
 def test_pending_queue_storage_failure_prevents_wb_read(self):
  calls,r=self.worker('storage_failure');self.assertEqual(calls,[]);self.assertEqual(r['error']['type'],'RuntimeError')
 def test_retained_queue_next_allowed_at_survives_missing_budget_delay(self):
  with patch('time.sleep',side_effect=AssertionError('Must not sleep')):calls,r=self.worker('retained_pause',single=True)
  self.assertEqual(calls,[]);self.assertTrue(r['pending_until'])
 def test_single_step_does_not_sleep_through905seconds(self):
  with patch('time.sleep',side_effect=AssertionError('Must not sleep')):
   calls,r=self.worker('pause',single=True)
  self.assertEqual(calls,[]);self.assertEqual(len(r['pending_queue']['requests']),11);self.assertTrue(r['pending_until'])
class StructuralGuards(unittest.TestCase):
 def test_budget_deadline_queue_and_retryafter_retained(self):
  s=Path('advertising_budgets_owner.py').read_text()
  for token in ['deadline=time.monotonic()','pending_queue','Budget pending queue full readback missing','next_allowed_at','wait+60>deadline','collect_campaign_budgets']:
   self.assertIn(token,s)
  self.assertNotIn('len(active)+2',s)
 def test_unchanged_daily_cron_and_no_wb_execution(self):
  s=Path('.github/workflows/advertising-daily-prepared.yml').read_text()
  self.assertIn("cron: '30 4 * * *'",s);self.assertIn("ADVERTISING_EXECUTION_ENABLED: 'false'",s);self.assertIn('group: wb-ip-advertising-agent',s)
 def test_disabled_budget_only_profile(self):
  s=json.loads(Path('advertising_daily_continue.json').read_text())
  self.assertIs(s['enabled'],False);self.assertEqual(s['mode'],'budgets_only');self.assertIs(s['wb_mutations'],False)
if __name__=='__main__':unittest.main()
