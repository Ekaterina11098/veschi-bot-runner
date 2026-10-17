"""Prepared dedicated daily IP runner. OFF until separate owner activation."""
import os,sys,json,subprocess,time,shutil
from pathlib import Path
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'private-source'))
def execute_day(get,put,stages,run_id,now=None,single_writer=False,*,resume_from=None,cas=None):
 """CAS-protected same-day continuation; no claim reset or completed-stage replay."""
 import copy
 from zoneinfo import ZoneInfo
 if not single_writer or cas is None:raise RuntimeError('Shared writer and durable CAS are required')
 now=now or datetime.now(timezone.utc);day=now.astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()
 key='advertising:ip:daily_run:v1:'+day;previous=get(key);expected=copy.deepcopy(previous)
 names=('source','source_gaps','membership','budgets','analysis_and_delivery','budget_completion')
 if previous and not resume_from:
  return dict(status=previous.get('status','incomplete'),skipped=True,reason='day_already_claimed',previous=previous)
 if resume_from:
  if (not previous or previous.get('run_id')!=resume_from or previous.get('day')!=day
    or previous.get('status') not in ('incomplete','failed')):raise PermissionError('Exact terminal incomplete claim required; active run cannot be resumed')
  done=previous.get('stages') or []
  if [r.get('name') for r in done]!=list(names[:len(done)]):raise PermissionError('Checkpoint prefix invalid')
  state=copy.deepcopy(previous);state.setdefault('continuations',[]).append(dict(from_run=resume_from,to_run=run_id,at=now.isoformat()))
  state.update(run_id=run_id,status='running',resumed_from=resume_from)
 else:
  state=dict(day=day,run_id=run_id,status='running',started_at=now.isoformat(),stages=[],wb_mutations=False,forecasts=False,old_queues_executed=False)
 def save():
  nonlocal expected
  if not cas(key,expected,state) or get(key)!=state:raise RuntimeError('Daily claim CAS/full readback mismatch')
  expected=copy.deepcopy(state)
 save()
 for name in names[len(state['stages']):]:
  try:
   result=stages[name]()
   if not isinstance(result,dict) or result.get('error_type'):raise RuntimeError('Stage durable result unconfirmed')
   state['stages'].append(dict(name=name,status=result.get('business_status','complete'),result=result))
   save()
  except TimeoutError as exc:
   if name in ('budgets','budget_completion'):
    state['stages'].append(dict(name=name,status='incomplete',reason='budget_evidence_pending',unknown_is_not_zero=True));save();continue
   state.update(status='incomplete',failed_stage=name,reason='timeout',error_type=type(exc).__name__);save();return state
  except Exception as exc:
   state.update(status='failed',failed_stage=name,reason=str(exc)[:300],error_type=type(exc).__name__)
   if hasattr(exc,'summary'):state['partial_stage_result']=exc.summary
   save();return state
 latest_source=next((r for r in reversed(state['stages']) if r['name'] in ('source','source_gaps')),None)
 budget_done=next((r for r in state['stages'] if r['name']=='budget_completion' and r.get('status')=='complete'),None)
 if budget_done:
  for r in state['stages']:
   if r['name']=='budgets' and r.get('status')=='incomplete':r['resolved_by']='budget_completion'
 if latest_source and latest_source.get('status')=='complete':
  for r in state['stages']:
   if r['name']=='source' and r.get('status')=='incomplete':r['resolved_by']='source_gaps'
 pending=[r['name'] for r in state['stages'] if r.get('status')=='incomplete' and not r.get('resolved_by') and r['name'] not in ('source','source_gaps')]
 if latest_source and latest_source.get('status')!='complete':pending.insert(0,'source_gaps')
 state['completed_stages']=[r['name'] for r in state['stages'] if r.get('status')=='complete']
 state['analysis_complete']=any(r['name']=='analysis_and_delivery' and r.get('status')=='complete' for r in state['stages'])
 state.update(status='incomplete' if pending else 'complete',pending_stages=pending,reason='pending_stage_evidence' if pending else None)
 state.pop('failed_stage',None);state.pop('error_type',None);save();return state

def daily_claim_cas(key,expected,value):
 import copy
 rows=store.db('GET','telegram_api_cache',params={'cache_key':'eq.'+key,'select':'payload,updated_at','limit':1}) or []
 if (rows[0]['payload'] if rows else None)!=expected:return False
 body=dict(payload=copy.deepcopy(value),updated_at=datetime.now(timezone.utc).isoformat(),expires_at=(datetime.now(timezone.utc)+timedelta(days=365)).isoformat())
 if rows:
  store.db('PATCH','telegram_api_cache',body=body,params={'cache_key':'eq.'+key,'updated_at':'eq.'+rows[0]['updated_at']})
 else:
  store.db('POST','telegram_api_cache',body=dict(body,cache_key=key),params={'on_conflict':'cache_key'},prefer='resolution=ignore-duplicates')
 return store.cache_get(key)==value


from advertising_agent import agent_store as store
if os.environ.get('IP_DAILY_ADVERTISING_ENABLED')!='true':
 print(json.dumps(dict(enabled=False,source_calls=0,telegram_calls=0,wb_writes=0)));raise SystemExit(0)
approval=store.cache_get('advertising:ip:daily_rollout:v1') or {}
if not (approval.get('enabled') is True and approval.get('source_sha')==os.environ['APPROVED_SOURCE_SHA']):
 raise RuntimeError('Dedicated daily owner approval and exact source pin required')
from stock_deploy_support import seal
registration=store.registration()
if approval.get('owner_id')!=registration['registered_by_user_id'] or approval.get('chat_id')!=registration['chat_id']:
 raise RuntimeError('Daily owner registration changed')
from zoneinfo import ZoneInfo
day=datetime.now(timezone.utc).astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()
if os.environ.get('GITHUB_EVENT_NAME')=='schedule' and day<approval['schedule_not_before']:
 print(json.dumps(dict(skipped=True,reason='before_approved_first_daily_date')));raise SystemExit(0)
resume_profile={}
if os.environ.get('GITHUB_EVENT_NAME')=='push':
 candidate_path=ROOT/'advertising_daily_continue.json'
 if candidate_path.exists():
  candidate=json.loads(candidate_path.read_text())
  if candidate.get('enabled') is True:
   if candidate.get('day')!=day or candidate.get('from_run_id')!='39004453781:1' or candidate.get('private_source_sha')!=os.environ['APPROVED_SOURCE_SHA']:
    raise PermissionError('Exact reviewed continuation profile required')
   resume_profile=candidate
if os.environ.get('GITHUB_EVENT_NAME')!='schedule' and day!=approval['controlled_day'] and not resume_profile:
 raise RuntimeError('One controlled day authorization expired')
def preserve_checkpoint(filename,summary):
 checkpoint=dict(stage=filename,run_id=os.environ['GITHUB_RUN_ID'],source_sha=os.environ['APPROVED_SOURCE_SHA'],summary=summary,at=datetime.now(timezone.utc).isoformat())
 seal('advertising-daily-checkpoint',checkpoint)
 out=Path(os.environ['RUNNER_TEMP'])/'stock-deploy-proof';dest=ROOT/'recovery-output'/'advertising';dest.mkdir(parents=True,exist_ok=True)
 names=['advertising-daily-checkpoint','advertising-preview'] if filename=='advertising_analysis_owner.py' else ['advertising-daily-checkpoint']
 for name in names:
  source=out/(name+'.aes.json')
  if source.exists():shutil.copyfile(source,dest/('daily-'+name+'-'+os.environ['GITHUB_RUN_ID']+'.aes.json'))
 for args in (['git','config','user.name','github-actions[bot]'],['git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com'],['git','add','recovery-output/advertising/']):
  subprocess.run(args,cwd=ROOT,check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 committed=subprocess.run(['git','commit','-m','Preserve owner encrypted daily checkpoint'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 if committed.returncode not in (0,1):raise RuntimeError('Checkpoint commit failed')
 for attempt in range(3):
  pulled=subprocess.run(['git','pull','--rebase','origin','main'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  if pulled.returncode:raise RuntimeError('Ciphertext checkpoint rebase failed')
  pushed=subprocess.run(['git','push','origin','HEAD:main'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  if pushed.returncode==0:return
 raise RuntimeError('Ciphertext checkpoint push failed; no stage replay')
started=(datetime.now(timezone.utc)-timedelta(hours=6)).isoformat()
resume_manifest_sent=set()
def stage(filename,timeout,single_step=False):
 def call():
  child=dict(os.environ)
  child.update(ADVERTISING_MIN_CONFIGURATION_AT=started,ADVERTISING_EXECUTION_ENABLED='false',ADVERTISING_BUDGET_STEP_ONLY='true' if single_step else 'false')
  if filename!='advertising_analysis_owner.py':
   child.pop('ADVERTISING_TELEGRAM_BOT_TOKEN',None)
   child['IP_LIMITED_TELEGRAM_DELIVERY']='false';child['IP_LIMITED_ANALYSIS_PUBLISH']='false'
  if filename=='advertising_source_owner.py':
   child.pop('WB_TOKEN_2',None)
   if resume_profile and not resume_manifest_sent:
    child['ADVERTISING_RETAINED_SOURCE_MANIFEST']=json.dumps(resume_profile['retained_source_manifest'])
    resume_manifest_sent.add('source')
  try:p=subprocess.run([sys.executable,str(ROOT/filename)],cwd=ROOT,env=child,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
  except subprocess.TimeoutExpired:raise TimeoutError('Bounded stage timed out') from None
  # Parse durable business summary even if the process returned nonzero.
  records=[]
  for line in p.stdout.splitlines():
   try:value=json.loads(line)
   except (ValueError,TypeError):continue
   if isinstance(value,dict):records.append(value)
  if not records:raise RuntimeError('Stage durable summary missing')
  value=records[-1]
  if filename=='advertising_budgets_owner.py' and value.get('complete') is False:
   value.update(business_status='incomplete',reason='budget_evidence_pending')
  preserve_checkpoint(filename,value)
  if p.returncode or value.get('error_type'):
   if filename=='advertising_budgets_owner.py' and value['error_type'] in ('ReadTimeout','TimeoutError','ExplicitRateLimit'):raise TimeoutError('Budget evidence remains unknown')
   exc=RuntimeError('Stage failed: '+str(value.get('reason') or value.get('error_type') or p.returncode));exc.summary=value;raise exc
  return value
 return call
stages=dict(source=stage('advertising_source_owner.py',900),
 source_gaps=stage('advertising_source_owner.py',900),
 membership=stage('advertising_exclusive_owner.py',600),
 budgets=stage('advertising_budgets_owner.py',180,True),
 analysis_and_delivery=stage('advertising_analysis_owner.py',1800),
 budget_completion=stage('advertising_budgets_owner.py',13800))
if __name__=='__main__':
 try:
  result=execute_day(store.cache_get,lambda k,v:store.cache_set(k,v,ttl_days=365),stages,
   os.environ['GITHUB_RUN_ID']+':'+os.environ.get('GITHUB_RUN_ATTEMPT','1'),single_writer=True,resume_from=resume_profile.get('from_run_id'),cas=daily_claim_cas)
 except Exception as exc:
  # Claim/storage failure must not turn into a green job or overwrite a rival claim.
  result=dict(status='failed',reason='claim_or_checkpoint_not_confirmed',error_type=type(exc).__name__,
   run_id=os.environ['GITHUB_RUN_ID'],completed_stages=[],completed_stages_unknown=True,
   wb_mutations=False,forecasts=False,old_queues_executed=False)
 seal('advertising-daily',result)
 summary=dict(status=result.get('status'),skipped=result.get('skipped',False),reason=result.get('reason'),
  failed_stage=result.get('failed_stage'),completed_stages=result.get('completed_stages',[]),pending_stages=result.get('pending_stages',[]),
  analysis_complete=result.get('analysis_complete',False),wb_writes=0)
 print(json.dumps(summary))
 if os.environ.get('GITHUB_STEP_SUMMARY'):
  with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as stream:
   stream.write('Advertising business result: '+json.dumps(summary,ensure_ascii=False)+'\\n')
 if result.get('status') not in ('complete','completed_with_explicit_source_limits'):raise SystemExit(1)
