"""Offline tests of actual prepared source/cache and daily CAS functions."""
import ast,copy,json,os,io,sys,unittest,subprocess
from pathlib import Path
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from unittest.mock import patch
from types import SimpleNamespace
NOW=datetime(2026,10,17,7,tzinfo=timezone.utc)
source=Path('advertising_source_owner.py').read_text()
daily=Path('advertising_daily_owner.py').read_text()
def functions(text,names,ns):
 tree=ast.parse(text)
 exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in names],type_ignores=[]),'actual-prepared-functions','exec'),ns)
 return ns
class SourceTests(unittest.TestCase):
 def setUp(self):
  self.rows={'mpstats:agent_reports:token_2:v1':dict(payload={'reports':{'old':{'raw_snapshot_id':1}}},updated_at='v0')}
  self.calls=[];self.race=False;outer=self
  def db(method,table,body=None,params=None,**kw):
   outer.calls.append((method,copy.deepcopy(params),copy.deepcopy(body)))
   key=str((params or {}).get('cache_key') or (body or {}).get('cache_key')).removeprefix('eq.')
   if method=='GET':return [copy.deepcopy(outer.rows[key])] if key in outer.rows else []
   if method=='PATCH':
    if outer.race:
     outer.rows[key]={'payload':{'reports':{'employee':'preserve'}},'updated_at':'other'};return []
    if outer.rows[key]['updated_at']!=(params or {}).get('updated_at','').removeprefix('eq.'):return []
    outer.rows[key]=copy.deepcopy(body);return None
   if method=='POST':
    if not kw.get('ignore_existing') or key not in outer.rows:outer.rows[key]=copy.deepcopy(body)
    return None
   raise AssertionError(method)
  self.ns=functions(source,{'get','put','flush_derived_caches','digest','SourceTraffic','restore_retained_source','cached_bidder_map'},
   {'copy':copy,'json':json,'datetime':datetime,'timedelta':timedelta,'ZoneInfo':ZoneInfo,'timezone':timezone,'now':NOW,'database':db,
    'gate':SimpleNamespace(fail=lambda:None),'DEFERRED_CACHES':{'mpstats:agent_reports:token_2:v1','mpstats:funnel_periods:token_2:v1'},
    'cache_memo':{},'cache_revisions':{},'cache_dirty':set()})
 def test_nine_updates_one_initial_read_one_write_one_readback(self):
  k='mpstats:agent_reports:token_2:v1'
  for i in range(9):
   v=self.ns['get'](k);v['reports'][str(i)]={'raw_snapshot_id':i+2};self.ns['put'](k,v)
  self.assertEqual([x[0] for x in self.calls],['GET'])
  self.ns['flush_derived_caches']()
  self.assertEqual([x[0] for x in self.calls],['GET','PATCH','GET'])
  self.assertEqual(len(self.rows[k]['payload']['reports']),10)
 def test_memo_does_not_mutate_until_put(self):
  k='mpstats:agent_reports:token_2:v1';v=self.ns['get'](k);v['reports'].clear()
  self.assertIn('old',self.ns['get'](k)['reports'])
 def test_cas_conflict_preserves_other_writer(self):
  k='mpstats:agent_reports:token_2:v1';v=self.ns['get'](k);v['reports']['new']=1;self.ns['put'](k,v);self.race=True
  with self.assertRaises(RuntimeError):self.ns['flush_derived_caches']()
  self.assertEqual(self.rows[k]['payload'],{'reports':{'employee':'preserve'}})
 def test_observer_put_immediate_readback(self):
  k='advertising:ip:order_outcome_monitor:v1';self.ns['put'](k,{'orders':{}})
  self.assertEqual([x[0] for x in self.calls],['POST','GET'])
 def test_limit_retained_100mb(self):
  t=self.ns['SourceTraffic']();self.assertEqual(t.limit,100_000_000)
 def test_threshold_blocks_new_data_but_not_durable_db(self):
  t=self.ns['SourceTraffic'](10);t.bytes=10
  with self.assertRaises(RuntimeError):t.before('mcp.mpstats.io',{'json':{'method':'tools/call','params':{'name':'lk_wb_products'}}})
  t.before('db.example',{})
 def test_cleanup_bounded_without_new_report_reads(self):
  t=self.ns['SourceTraffic'](10);t.bytes=10
  kw={'json':{'params':{'name':'lk_wb_cabinets','arguments':{'action':'reset'}}}}
  t.before('mcp.mpstats.io',kw);t.before('mcp.mpstats.io',kw)
  with self.assertRaises(RuntimeError):t.before('mcp.mpstats.io',kw)
 def test_only_mapping_projected_not_old_request_queue(self):
  seen=[]
  def db(method,table,**kw):
   seen.append(kw);return [{'bidder_map':{'token_2':{'campaign_ids':[1]}}}]
  value=self.ns['cached_bidder_map'](db)
  self.assertEqual(value,{'token_2':{'campaign_ids':[1]}})
  self.assertEqual(seen[0]['params']['select'],'bidder_map:payload->bidder_map')
 def test_batch_snapshot_mirror_body_safe(self):
  t=self.ns['SourceTraffic']()
  label=t.label('db.example','POST','/rest/v1/telegram_api_cache',{'json':[{'cache_key':'analytics:payload:1','payload':{}}]},'db.example')
  self.assertEqual(label,'supabase:POST:telegram_api_cache:other_cache')
 def test_decoded_body_distinct_wire_header(self):
  t=self.ns['SourceTraffic']()
  t.observed('supabase:GET:cache',SimpleNamespace(content=b'x'*1000,headers={'Content-Length':'100','Content-Encoding':'gzip'}))
  self.assertEqual(t.summary()['bytes'],1000)
  self.assertEqual(t.summary()['buckets']['supabase:GET:cache']['content_length_header_bytes'],100)
 def manifest(self):
  return dict(day='2026-10-17',original_run_id='39004453781:1',snapshot_ids=[17841,17842,17843,17844,17845,17847,17849,17851,17853])
 def retained(self,ident,wrong=False):
  tool='lk_wb_card_orders' if ident<=17844 else 'lk_wb_products'
  return [dict(id=ident,cabinet='token_2',run_id='other' if wrong else '39004453781:1',status='complete',
   payload=[dict(tool=tool,status='received',scope_verified=True)])]
 def test_resume_does_not_reingest_four_orders(self):
  called=[];r={}
  self.ns['restore_retained_source'](self.manifest(),lambda table,p:self.retained(int(p['id'][3:])),
   lambda *a,**kw:called.append(kw['retained_id']),r,NOW)
  self.assertEqual(called,[17845,17847,17849,17851,17853]);self.assertEqual(len(r['retained_recovery']),9)
 def test_manifest_all_validated_before_writes(self):
  called=[]
  with self.assertRaises(RuntimeError):
   self.ns['restore_retained_source'](self.manifest(),lambda table,p:self.retained(int(p['id'][3:]),int(p['id'][3:])==17853),
    lambda *a,**kw:called.append(1),{},NOW)
  self.assertEqual(called,[])
 def test_wrong_scope_manifest_rejected(self):
  m=self.manifest();m['snapshot_ids'].append(1)
  with self.assertRaises(PermissionError):self.ns['restore_retained_source'](m,None,None,{},NOW)
class DailyTests(unittest.TestCase):
 def setUp(self):
  self.state=None;self.called=[];self.failcas=False
  def get(k):return copy.deepcopy(self.state)
  def cas(k,expected,new):
   if self.failcas or self.state!=expected:return False
   self.state=copy.deepcopy(new);return True
  self.get=get;self.cas=cas
  self.fn=functions(daily,{'execute_day'},{'datetime':datetime,'timezone':timezone})['execute_day']
  self.names=('source','source_gaps','membership','budgets','analysis_and_delivery','budget_completion')
  self.stages={n:(lambda n=n:self.call(n)) for n in self.names}
 def call(self,n):self.called.append(n);return {'business_status':'complete'}
 def run_day(self,**kw):return self.fn(self.get,None,self.stages,'new:1',NOW,single_writer=True,cas=self.cas,**kw)
 def test_normal_complete_all_stages(self):
  r=self.run_day();self.assertEqual(r['status'],'complete');self.assertTrue(r['analysis_complete']);self.assertEqual(self.called,list(self.names))
 def test_existing_claim_never_reset(self):
  self.state={'status':'incomplete','run_id':'old:1'};r=self.run_day()
  self.assertTrue(r['skipped']);self.assertEqual(self.called,[]);self.assertEqual(self.state['run_id'],'old:1')
 def previous(self):
  self.state=dict(day='2026-10-17',status='incomplete',run_id='old:1',stages=[dict(name='source',status='complete',result={})])
 def test_resume_skips_confirmed_stage(self):
  self.previous();r=self.run_day(resume_from='old:1')
  self.assertEqual(self.called,list(self.names[1:]));self.assertEqual(r['resumed_from'],'old:1')
 def test_active_claim_not_stolen(self):
  self.previous();self.state['status']='running'
  with self.assertRaises(PermissionError):self.run_day(resume_from='old:1')
  self.assertEqual(self.called,[])
 def test_wrong_resume_identity(self):
  self.previous()
  with self.assertRaises(PermissionError):self.run_day(resume_from='other')
 def test_cas_race_no_stage_calls(self):
  self.failcas=True
  with self.assertRaises(RuntimeError):self.run_day()
  self.assertEqual(self.called,[])
 def test_source_limits_recorded_and_second_pass_may_resolve(self):
  self.stages['source']=lambda:{'business_status':'incomplete','reason':'pending_source_requests'}
  r=self.run_day();self.assertEqual(r['status'],'complete')
 def test_remaining_source_limits_explicit_incomplete(self):
  self.stages['source_gaps']=lambda:{'business_status':'incomplete','reason':'collection_threshold'}
  r=self.run_day();self.assertEqual(r['status'],'incomplete');self.assertIn('source_gaps',r['pending_stages']);self.assertTrue(r['analysis_complete'])
 def test_stage_exception_explicit_failed(self):
  def fail():raise RuntimeError('storage readback unavailable')
  self.stages['source']=fail;r=self.run_day();self.assertEqual(r['status'],'failed');self.assertEqual(r['failed_stage'],'source');self.assertEqual(r['stages'],[])
 def test_budget_timeout_not_global_analysis_block(self):
  def fail():raise TimeoutError()
  self.stages['budgets']=fail;r=self.run_day();self.assertTrue(r['analysis_complete']);self.assertEqual(r['status'],'complete');self.assertNotIn('budgets',r['pending_stages'])
 def test_completed_delivery_not_replayed(self):
  self.previous();self.state['stages']=[dict(name=n,status='complete',result={}) for n in self.names[:-1]]
  self.run_day(resume_from='old:1');self.assertEqual(self.called,['budget_completion'])
 def test_checkpoint_prefix_rejected(self):
  self.previous();self.state['stages']=[dict(name='analysis_and_delivery',status='complete')]
  with self.assertRaises(PermissionError):self.run_day(resume_from='old:1')
 def test_source_child_no_wb_or_telegram_credentials(self):
  seen=[];ns={'os':os,'sys':sys,'json':json,'ROOT':Path('.'),'Path':Path,'started':NOW.isoformat(),'resume_profile':{},
   'preserve_checkpoint':lambda *a:seen.append(a),'subprocess':subprocess}
  fn=functions(daily,{'stage'},ns)['stage']
  def run(*a,**kw):
   self.assertNotIn('WB_TOKEN_2',kw['env']);self.assertNotIn('ADVERTISING_TELEGRAM_BOT_TOKEN',kw['env'])
   self.assertEqual(kw['env']['ADVERTISING_EXECUTION_ENABLED'],'false')
   return SimpleNamespace(returncode=0,stdout='{"business_status":"complete"}')
  with patch.dict(os.environ,{'WB_TOKEN_2':'synthetic','ADVERTISING_TELEGRAM_BOT_TOKEN':'synthetic'}),patch.object(subprocess,'run',side_effect=run):
   fn('advertising_source_owner.py',1)()
  self.assertEqual(len(seen),1)
 def test_incomplete_process_exit_is_nonzero(self):
  self.assertIn("if result.get('status') not in ('complete','completed_with_explicit_source_limits'):raise SystemExit(1)",daily)


class AnalysisStatus(unittest.TestCase):
 def setUp(self):
  text=Path('advertising_analysis_owner.py').read_text()
  self.f=functions(text,{'analysis_business_summary'},{})['analysis_business_summary']
 def test_saved_no_messages_is_complete_not_economy_claim(self):
  r=self.f({'analysis':{'rows':[]},'delivery':{'sent':0,'failures':[]}})
  self.assertEqual(r['business_status'],'complete');self.assertEqual(r['telegram_calls'],0);self.assertNotIn('economy_healthy',r)
 def test_uncertain_delivery_explicit_incomplete(self):
  r=self.f({'analysis':{'saved':True},'delivery':{'failures':[{'status':'uncertain'}]}})
  self.assertEqual(r['business_status'],'incomplete');self.assertEqual(r['reason'],'delivery_unconfirmed')
 def test_failed_analysis_explicit_failed(self):
  r=self.f({'error':{'type':'RuntimeError'}})
  self.assertEqual(r['business_status'],'failed')
 def test_absent_analysis_not_complete(self):
  self.assertEqual(self.f({})['business_status'],'incomplete')

class BudgetStageStatus(unittest.TestCase):
 def test_incomplete_budget_summary_survives(self):
  ns={'os':os,'sys':sys,'json':json,'ROOT':Path('.'),'Path':Path,'started':NOW.isoformat(),'resume_profile':{},'subprocess':subprocess,'preserve_checkpoint':lambda *a:None}
  fn=functions(daily,{'stage'},ns)['stage']
  with patch.object(subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{"complete":false}')):
   r=fn('advertising_budgets_owner.py',1)()
  self.assertEqual(r['business_status'],'incomplete');self.assertEqual(r['reason'],'budget_evidence_pending')


class FinalBudgetResolution(DailyTests):
 def test_completion_resolves_single_step_incomplete(self):
  self.stages['budgets']=lambda:{'business_status':'incomplete','reason':'budget_evidence_pending'}
  r=self.run_day();self.assertEqual(r['status'],'complete');self.assertEqual(r['stages'][3]['resolved_by'],'budget_completion')
 def test_unresolved_completion_remains_incomplete(self):
  self.stages['budgets']=lambda:{'business_status':'incomplete'}
  self.stages['budget_completion']=lambda:{'business_status':'incomplete','reason':'budget_evidence_pending'}
  r=self.run_day();self.assertEqual(r['status'],'incomplete');self.assertIn('budget_completion',r['pending_stages'])

class ActualRunIdentity(SourceTests):
 def test_manifest_matches_actual_collect_run_assignment(self):
  tree=ast.parse(Path('private-source/analytics/collect.py').read_text())
  assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='RUN_ID' for t in n.targets))
  ns={'os':os}
  with patch.dict(os.environ,{'GITHUB_RUN_ID':'39004453781','GITHUB_RUN_ATTEMPT':'1'}):
   exec(compile(ast.Module(body=[assignment],type_ignores=[]),'actual-collect-run-id','exec'),ns)
  self.assertEqual(ns['RUN_ID'],'39004453781:1')
  self.assertEqual(self.manifest()['original_run_id'],ns['RUN_ID'])
 def test_missing_attempt_not_silently_accepted(self):
  calls=[]
  def read(table,p):
   rows=self.retained(int(p['id'][3:]));rows[0]['run_id']='39004453781';return rows
  with self.assertRaises(RuntimeError):
   self.ns['restore_retained_source'](self.manifest(),read,lambda *a,**kw:calls.append(1),{},NOW)
  self.assertEqual(calls,[])
 def test_next_profile_stays_disabled(self):
  p=json.loads(Path('advertising_daily_continue.json').read_text())
  self.assertFalse(p['enabled'])
  self.assertEqual(p['from_run_id'],'39015462359:1')
  self.assertEqual(p['mode'],'budgets_only')
  self.assertEqual(p['retained_source_manifest']['original_run_id'],'39004453781:1')
if __name__=='__main__':unittest.main()


