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
 global result
 result=json.loads(json.dumps(result,ensure_ascii=False,default=str))
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
 child['ADVERTISING_MIN_CONFIGURATION_AT']=(datetime.fromisoformat(result['started_at'])-timedelta(hours=6)).isoformat()
 p=subprocess.run([sys.executable,str(ROOT/filename)],cwd=ROOT,env=child,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
 entries=[]
 for line in p.stdout.splitlines():
  try:value=json.loads(line)
  except (TypeError,ValueError):continue
  if isinstance(value,dict):entries.append(value)
 if p.returncode or not entries or entries[-1].get('error_type'):raise RuntimeError('Controlled stage failed: '+filename)
 result['stages'].append(dict(name=filename,summary=entries[-1]));save()
try:
 from advertising_cached_finance_reader import install
 import analytics.stage_one as finance_stage
 install(finance_stage)
 result=store.cache_get(KEY)
 if not result or result.get('source_sha')!=PIN or result.get('analysis_started_at'):raise RuntimeError('No exact unanalysed controlled checkpoint; no replay')
 if [x['name'] for x in result.get('stages',[])]!=['advertising_exclusive_owner.py']:raise RuntimeError('Unexpected controlled progress')
 saved=read('analytics_snapshots',dict(id='in.(17815,17817,17819,17821,17823)',select='id,source,cabinet,status'))
 if len(saved)!=5 or any(x.get('status')!='complete' for x in saved):raise RuntimeError('Saved source scope not fully confirmed')
 result['continued_from']='38927519970';result['retained_source_ids']=[x['id'] for x in saved]
 result['stages'].append(dict(name='advertising_source_owner.py',summary=dict(saved=5,reused_from_original_pass=True,new_external_calls=0)))
 from analytics.stage_one import compose_cached_finance
 from datetime import date
 a,b=result['before']['period_from'],result['before']['period_to']
 result['recomposition']=compose_cached_finance('token_2',date.fromisoformat(a),date.fromisoformat(b),datetime.now(timezone.utc))
 if result['recomposition'].get('status')!='composed':raise RuntimeError('Saved daily composition remains incomplete')
 history=read('analytics_snapshots',dict(source='eq.mpstats_products_composed',cabinet='eq.token_2',select='period_from,period_to',order='id.desc',limit=200))
 affected={(r['period_from'],r['period_to']) for r in history if any(r['period_from']<=d<=r['period_to'] for d in ('2026-10-09','2026-10-11','2026-10-12'))}
 result['affected_recompositions']=[]
 for first,last in sorted(affected-{(a,b)})[:10]:
  result['affected_recompositions'].append(dict(period_from=first,period_to=last,result=compose_cached_finance('token_2',date.fromisoformat(first),date.fromisoformat(last),datetime.now(timezone.utc))))
 result['after_sources']=profits();save()
 result['analysis_started_at']=datetime.now(timezone.utc).isoformat();save()
 stage('advertising_analysis_owner.py',1800)
 result['after']=profits()
 reports=read('analytics_snapshots',dict(source='eq.mpstats_campaign_report',cabinet='eq.token_2',select='id,payload,collected_at',order='id.desc',limit=1000))
 catalog=read('analytics_snapshots',dict(source='eq.mpstats_campaign_catalog',cabinet='eq.token_2',select='payload',order='id.desc',limit=10))
 mapping={r['wb_id']:r['id'] for s in reversed(catalog) for p in s['payload'] for r in p.get('rows',[])}
 config=read('analytics_snapshots',dict(source='eq.advertising_active_configuration',cabinet='eq.token_2',select='id,payload,collected_at',order='id.desc',limit=1))[0]
 import ast
 tree=ast.parse((ROOT/'advertising_source_owner.py').read_text());ns={}
 exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='campaign_day_gaps'],type_ignores=[]),'actual-day-coverage','exec'),ns)
 result['configuration']=dict(id=config['id'],collected_at=config['collected_at'],campaign_ids=config['payload']['campaign_ids'])
 result['daily_coverage']={str(cid):ns['campaign_day_gaps'](reports,mapping.get(cid),a,b) for cid in config['payload']['campaign_ids']}
 result['profit_changes']={n:dict(before=(result['before']['items'].get(n) or {}).get('net_profit'),after=(result['after']['items'].get(n) or {}).get('net_profit')) for n in result['after']['items']}
 ids=[result['before']['marker_id']]+[x for row in result['before']['items'].values() if row for x in row.get('component_snapshot_ids',[])]
 retained=read('analytics_snapshots',dict(id='in.('+','.join(map(str,set(ids)))+')',select='id'))
 result['prior_history_retained']=set(x['id'] for x in retained)==set(ids)
 result['status']='complete';save()
except Exception as exc:
 result.update(status='incomplete',error=error(exc));seal('advertising-pr27-controlled',result)
 print(json.dumps({'status':'incomplete','error_type':type(exc).__name__,'wb_writes':0}));raise SystemExit(1)
print(json.dumps({'status':result['status'],'wb_writes':0,'budget_collector_started':False}))
