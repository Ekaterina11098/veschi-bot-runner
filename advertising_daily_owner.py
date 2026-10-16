"""Prepared dedicated daily IP runner. OFF until separate owner activation."""
import os,sys,json,subprocess,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'private-source'))
from analytics.ip_daily_schedule import execute_day
from advertising_agent import agent_store as store
if os.environ.get('IP_DAILY_ADVERTISING_ENABLED')!='true':
 print(json.dumps(dict(enabled=False,source_calls=0,telegram_calls=0,wb_writes=0)));raise SystemExit(0)
approval=store.cache_get('advertising:ip:daily_rollout:v1') or {}
if not (approval.get('enabled') is True and approval.get('source_sha')==os.environ['APPROVED_SOURCE_SHA']):
 raise RuntimeError('Dedicated daily owner approval and exact source pin required')
from stock_deploy_support import seal
started=(datetime.now(timezone.utc)-timedelta(hours=6)).isoformat()
def stage(filename,timeout,single_step=False):
 def call():
  child=dict(os.environ)
  child.update(ADVERTISING_MIN_CONFIGURATION_AT=started,ADVERTISING_EXECUTION_ENABLED='false',ADVERTISING_BUDGET_STEP_ONLY='true' if single_step else 'false')
  if filename!='advertising_analysis_owner.py':
   child.pop('ADVERTISING_TELEGRAM_BOT_TOKEN',None)
   child['IP_LIMITED_TELEGRAM_DELIVERY']='false';child['IP_LIMITED_ANALYSIS_PUBLISH']='false'
  if filename=='advertising_source_owner.py':child.pop('WB_TOKEN_2',None)
  try:p=subprocess.run([sys.executable,str(ROOT/filename)],cwd=ROOT,env=child,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
  except subprocess.TimeoutExpired:raise TimeoutError('Bounded stage timed out') from None
  if p.returncode:raise RuntimeError('Stage process failed')
  records=[]
  for line in p.stdout.splitlines():
   try:value=json.loads(line)
   except (ValueError,TypeError):continue
   if isinstance(value,dict):records.append(value)
  if not records:raise RuntimeError('Stage durable summary missing')
  value=records[-1]
  if value.get('error_type'):
   if filename=='advertising_budgets_owner.py' and value['error_type'] in ('ReadTimeout','TimeoutError','ExplicitRateLimit'):raise TimeoutError('Budget evidence remains unknown')
   raise RuntimeError('Stage failed before durable completion')
  return value
 return call
stages=dict(source=stage('advertising_source_owner.py',900),
 source_gaps=stage('advertising_source_owner.py',900),
 membership=stage('advertising_exclusive_owner.py',600),
 budgets=stage('advertising_budgets_owner.py',180,True),
 analysis_and_delivery=stage('advertising_analysis_owner.py',1800),
 budget_completion=stage('advertising_budgets_owner.py',13800))
result=execute_day(store.cache_get,lambda k,v:store.cache_set(k,v,ttl_days=365),stages,
 os.environ['GITHUB_RUN_ID']+':'+os.environ.get('GITHUB_RUN_ATTEMPT','1'),single_writer=True)
seal('advertising-daily',result)
print(json.dumps(dict(status=result.get('status'),skipped=result.get('skipped',False),wb_writes=0)))
