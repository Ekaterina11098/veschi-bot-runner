"""Owner-authorized cache-only execution of existing experiment learning refresh."""
import os,sys,json,hashlib,io,contextlib,gzip,base64
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from stock_deploy_support import seal,error
report={'source_calls':0,'wb_writes':0,'telegram_calls':0,'private_pin':'6a9015bdd0eab870d44a06e43b92a1d930ecd58d'}
hidden=io.StringIO()
try:
 with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
  import requests
  from urllib.parse import urlsplit
  host=urlsplit(os.environ['SUPABASE_URL']).hostname;native=requests.sessions.Session.request
  def guarded(session,method,url,*a,**kw):
   if urlsplit(url).hostname!=host:raise RuntimeError('Cache-only historical learning cannot collect marketplace or Telegram data')
   return native(session,method,url,*a,**kw)
  requests.sessions.Session.request=guarded
  from advertising_agent.experiments import refresh_learning,experiment_rows
  from analytics.stage_one import read
  from analytics.payload_storage import decode_rows
  from advertising_agent.agent_store import cache_get
  saved=refresh_learning()
  if saved.get('status')!='advisory_saved':raise RuntimeError('No saved historical evidence')
  records=decode_rows(read('analytics_snapshots',{'id':'eq.'+str(saved['snapshot_id']),'source':'eq.ip_historical_learning_audit','cabinet':'eq.token_2','select':'id,payload','limit':1}) or [])
  result=records[0]['payload'][0]
  digest=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
  if digest(result)!=saved['sha256']:raise RuntimeError('Full historical evidence SHA mismatch')
  summary=cache_get('advertising:ip:historical_learning:v1')
  if summary.get('sha256')!=saved['sha256'] or summary.get('snapshot_id')!=saved['snapshot_id']:raise RuntimeError('Common memory identity mismatch')
  rows=experiment_rows({'cabinet':'eq.token_2','select':'id,campaign_id,nm_id,article,change_log_id,experiment_type,change_field,old_value,new_value,started_at,baseline,checkpoints','order':'id.asc'})
  report['evidence_backup_gzip_b64']=base64.b64encode(gzip.compress(json.dumps({'experiments':rows,'learning':result,'memory':summary},sort_keys=True,ensure_ascii=False,separators=(',',':')).encode(),mtime=0)).decode()
  report.update(status='advisory_audit_saved',summary=summary,full_readback_verified=True,experiment_rows=len(rows),existing_journal_refresh_used=True)
except Exception as exc:report['error']=error(exc)
finally:
 report['private_log']=hidden.getvalue();seal('advertising-history-learning',report)
 print(json.dumps({'status':report.get('status'),'readback':report.get('full_readback_verified',False),'source_calls':0,'wb_writes':0,'telegram_calls':0,'error_type':report.get('error',{}).get('type')}))
