"""Cache-only historical evidence, existing experiment journal and shared cache."""
import os,sys,json,hashlib,io,contextlib,gzip,base64
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from stock_deploy_support import seal,error
report={'source_calls':0,'wb_writes':0,'telegram_calls':0,'private_pin':'8aa1eecb8215adc1dad89b8c812de050d99f18cc'}
hidden=io.StringIO()
try:
 with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
  import requests
  from urllib.parse import urlsplit
  host=urlsplit(os.environ['SUPABASE_URL']).hostname;native=requests.sessions.Session.request
  def guarded(session,method,url,*a,**kw):
   if urlsplit(url).hostname!=host:raise RuntimeError('History audit cannot collect marketplace or Telegram data')
   return native(session,method,url,*a,**kw)
  requests.sessions.Session.request=guarded
  from analytics.stage_one import read
  from analytics.collect import database,RUN_ID
  from analytics.payload_storage import decode_rows
  from analytics.ip_history_learning import build_memory, timestamp, validate_current_policy
  rows=read('advertising_experiments',{'cabinet':'eq.token_2','select':'id,campaign_id,nm_id,article,change_log_id,experiment_type,change_field,old_value,new_value,started_at,baseline,checkpoints','order':'id.asc','limit':1000}) or []
  if len(rows)>=1000:raise RuntimeError('Pagination required; refuse incomplete learning audit')
  result=build_memory(rows)
  from advertising_agent.experiments import decision_for
  result['current_policy_validation']=validate_current_policy(rows,decision_for)
  dates=[timestamp(r.get('started_at')).date().isoformat() for r in rows if timestamp(r.get('started_at'))]
  if not dates:raise RuntimeError('History period unavailable')
  digest=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
  sha=digest(result)
  database('POST','analytics_snapshots',body={'source':'ip_historical_learning_audit','cabinet':'token_2','period_from':min(dates),'period_to':max(dates),'run_id':RUN_ID,'status':'partial','payload':[result],'detail':'Cache-only advisory observations, not causal learning or proven recommendation improvement'})
  saved=decode_rows(read('analytics_snapshots',{'source':'eq.ip_historical_learning_audit','cabinet':'eq.token_2','run_id':'eq.'+RUN_ID,'select':'id,payload','order':'id.desc','limit':1}) or [])
  if not saved or digest(saved[0]['payload'][0])!=sha:raise RuntimeError('Historical evidence full readback SHA mismatch')
  summary={k:v for k,v in result.items() if k not in ('evidence','backtests','pair_profiles','current_policy_validation')}
  summary.update(pair_profiles_count=len(result.get('pair_profiles') or {}),
   current_policy_comparison={k:v for k,v in result['current_policy_validation'].items() if k!='comparisons'},
   snapshot_id=saved[0]['id'],sha256=sha,full_readback_verified=True,
   evaluated_predictions={m:r['evaluated'] for m,r in result['backtests'].items()},
   note='Use only conditional hypotheses; no learned demand forecast or intervention benefit proven')
  from advertising_agent.agent_store import cache_set,cache_get
  key='advertising:ip:historical_learning:v1'
  cache_set(key,summary,ttl_days=365)
  if digest(cache_get(key))!=digest(summary):raise RuntimeError('Common memory readback mismatch')
  report['evidence_backup_gzip_b64']=base64.b64encode(gzip.compress(json.dumps({'experiments':rows,'learning':result,'memory':summary},sort_keys=True,ensure_ascii=False,separators=(',',':')).encode(),mtime=0)).decode()
  report.update(status='advisory_audit_saved',summary=summary,full_readback_verified=True,experiment_rows=len(rows))
except Exception as exc:report['error']=error(exc)
finally:
 report['private_log']=hidden.getvalue();seal('advertising-history-learning',report)
 print(json.dumps({'status':report.get('status'),'readback':report.get('full_readback_verified',False),'source_calls':0,'wb_writes':0,'telegram_calls':0,'error_type':report.get('error',{}).get('type')}))
