"""One owner-controlled PR27 analytics pass. No budget collector or WB mutations."""
import os,sys,json,subprocess,copy,hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'private-source'))
from stock_deploy_support import seal,error
from analytics.collect import database,RUN_ID
from analytics.stage_one import read
from advertising_agent import agent_store as store
PIN='6eb5f990aecfa1a92909169ffd76f05ac6da469d'
KEY='advertising:ip:pr27-controlled:20261016:v1'
result=dict(source_sha=PIN,wb_writes=0,budget_collector_started=False,forecasts=False,test57_enabled=False,stages=[],started_at=datetime.now(timezone.utc).isoformat())
def sha(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def save():
 store.cache_set(KEY,result,ttl_days=365)
 if store.cache_get(KEY)!=result:raise RuntimeError('Controlled pass journal readback failed')
 seal('advertising-pr27-controlled',result)
def profits():
 from analytics.mpstats_primary import profit_rows
 from zoneinfo import ZoneInfo
 end=datetime.now(timezone.utc).astimezone(ZoneInfo('Europe/Moscow')).date()-timedelta(days=1)
 start=end-timedelta(days=6)
 rows,marker=profit_rows(read,'token_2',start,end)
 return dict(period_from=str(start),period_to=str(end),marker_id=(marker or {}).get('id'),items={str(n):rows.get(n) for n in (1007948808,1123677454,320248210)})
def stage(filename,timeout=1200):
 child=dict(os.environ,ADVERTISING_EXECUTION_ENABLED='false',IP_FINANCIAL_RISK_NOTIFICATIONS='false',SUPABASE_EGRESS_OPTIMIZED='false')
 if filename!='advertising_analysis_owner.py':
  child.pop('ADVERTISING_TELEGRAM_BOT_TOKEN',None);child['IP_LIMITED_TELEGRAM_DELIVERY']='false';child['IP_LIMITED_ANALYSIS_PUBLISH']='false'
 if filename=='advertising_source_owner.py':child.pop('WB_TOKEN_2',None);child['FOCUSED_DAILY_GAPS']='false'
 child['ADVERTISING_MIN_CONFIGURATION_AT']=result['started_at']
 p=subprocess.run([sys.executable,str(ROOT/filename)],cwd=ROOT,env=child,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
 entries=[]
 for line in p.stdout.splitlines():
  try:value=json.loads(line)
  except (TypeError,ValueError):continue
  if isinstance(value,dict):entries.append(value)
 if p.returncode or not entries or entries[-1].get('error_type'):raise RuntimeError('Controlled stage failed: '+filename)
 result['stages'].append(dict(name=filename,summary=entries[-1]));save()
try:
 if os.environ.get('ADVERTISING_EXECUTION_ENABLED')!='false':raise PermissionError('WB mutations must remain disabled')
 if store.cache_get(KEY):raise RuntimeError('Controlled pass already recorded; do not replay')
 reg=store.registration();approval=store.cache_get('advertising:ip:daily_rollout:v1')
 if not approval or approval.get('owner_id')!=reg['registered_by_user_id'] or approval.get('chat_id')!=reg['chat_id']:raise PermissionError('Existing owner rollout registration required')
 if approval.get('source_sha') not in ('8bea1186491b2182dc339a6d5ca16ad9ce879760',PIN):raise PermissionError('Unexpected rollout source; inspect before repinning')
 result['status']='running';save()
 approved=copy.deepcopy(approval);approved.update(source_sha=PIN)
 approved.setdefault('source_history',[]).append(dict(previous_sha=approval.get('source_sha'),sha=PIN,reason='owner approved unchanged PR27+runner4',at=result['started_at']))
 store.cache_set('advertising:ip:daily_rollout:v1',approved,ttl_days=365)
 if store.cache_get('advertising:ip:daily_rollout:v1')!=approved:raise RuntimeError('Rollout source pin readback failed')
 result['daily_approval_source_verified']=True;result['before']=profits();save()
 stage('advertising_exclusive_owner.py',900)
 stage('advertising_source_owner.py',1200)
 stage('advertising_source_owner.py',1200)
 result['after_sources']=profits();save()
 stage('advertising_analysis_owner.py',1800)
 result['after']=profits()
 reports=read('analytics_snapshots',dict(source='eq.mpstats_campaign_report',cabinet='eq.token_2','select':'id,payload,collected_at',order='id.desc',limit=1000))
 catalog=read('analytics_snapshots',dict(source='eq.mpstats_campaign_catalog',cabinet='eq.token_2',select='payload',order='id.desc',limit=10))
 mapping={r['wb_id']:r['id'] for s in reversed(catalog) for p in s['payload'] for r in p.get('rows',[])}
 config=read('analytics_snapshots',dict(source='eq.advertising_active_configuration',cabinet='eq.token_2',select='id,payload,collected_at',order='id.desc',limit=1))[0]
 from datetime import date
 from runpy import run_path
 # Read pure planner definitions without executing the source collector again.
 import ast
 tree=ast.parse((ROOT/'advertising_source_owner.py').read_text())
 ns={};exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='campaign_day_gaps'],type_ignores=[]),'actual-day-coverage','exec'),ns)
 result['configuration']=dict(id=config['id'],collected_at=config['collected_at'],campaign_ids=config['payload']['campaign_ids'])
 a,b=result['after']['period_from'],result['after']['period_to']
 result['daily_coverage']={str(cid):ns['campaign_day_gaps'](reports,mapping.get(cid),a,b) for cid in config['payload']['campaign_ids']}
 result['profit_changes']={n:dict(before=(result['before']['items'].get(n) or {}).get('net_profit'),after=(result['after']['items'].get(n) or {}).get('net_profit')) for n in result['after']['items']}
 result['status']='complete';save()
except Exception as exc:
 result.update(status='incomplete',error=error(exc))
 seal('advertising-pr27-controlled',result)
 print(json.dumps({'status':'incomplete','error_type':type(exc).__name__,'wb_writes':0}))
 raise SystemExit(1)
print(json.dumps({'status':result['status'],'wb_writes':0,'budget_collector_started':False}))
