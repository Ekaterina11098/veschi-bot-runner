"""Bounded IP-only source recovery using existing MPStats normalization and cached history."""
import os,sys,json,time,copy,contextlib,io
from pathlib import Path
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from stock_deploy_support import seal,error
from analytics.collect import database,RUN_ID
from analytics.stage_one import read,cache,compose_cached_finance
from analytics.mpstats_probe import discover,ProbeError
from analytics.mpstats_gaps import execute_reads,period
from analytics.mpstats_recovery import normalize,import_products,BIDDER
from analytics.storage_collection_gate import CollectionGate
now=datetime.now(timezone.utc);end=now.astimezone(ZoneInfo('Europe/Moscow')).date()-timedelta(days=1);start=end-timedelta(days=6)
report=dict(cabinet='token_2',period_from=str(start),period_to=str(end),saved=[],normalization_errors=[],wb_calls=0,wb_writes=0,telegram_calls=0)
gate=CollectionGate(Path(os.environ['RUNNER_TEMP'])/'ads-storage-health.json',max_age_seconds=900,scope='ip-ads-source')
def digest(v):
 import hashlib
 return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def get(k):
 rows=database('GET','telegram_api_cache',params={'cache_key':'eq.'+k,'select':'payload','limit':1}) or []
 return rows[0]['payload'] if rows else None
def put(k,v):
 body=dict(cache_key=k,payload=v,updated_at=datetime.now(timezone.utc).isoformat(),expires_at=(now+timedelta(days=365)).isoformat())
 database('POST','telegram_api_cache',body=body,params={'on_conflict':'cache_key'})
 if digest(get(k))!=digest(v):gate.fail();raise RuntimeError('Private cache readback mismatch')
def save_snapshot(source,value,a,b,status='complete'):
 body=dict(source=source,cabinet='token_2',run_id=RUN_ID,period_from=str(a),period_to=str(b),payload=[value],status=status,detail='Owner advertising recovery; bounded missing scope; no WB mutation or Telegram')
 database('POST','analytics_snapshots',body=body)
 got=database('GET','analytics_snapshots',params={'source':'eq.'+source,'cabinet':'eq.token_2','run_id':'eq.'+RUN_ID,'order':'id.desc','select':'id,payload','limit':1}) or []
 if not got or digest(got[0]['payload'])!=digest([value]):gate.fail();raise RuntimeError('Snapshot full payload readback mismatch')
 return got[0]['id']
def wanted(tool,args,purpose=None):
 key='token_2:'+tool+':'+json.dumps(args,sort_keys=True)+((':'+purpose) if purpose else '')
 # Received, explicit rejected parameter errors and retries are all preserved.
 from analytics.collect import _database_transport
 a,b=period(args)
 candidates=_database_transport('GET','analytics_snapshots',params={'source':'eq.mpstats_'+tool,'cabinet':'eq.token_2','period_from':'eq.'+a,'period_to':'eq.'+b,'select':'id,request_key:payload->0->>request_key,observation_status:payload->0->>status,retry_after:payload->0->>retry_after,observed_at:payload->0->>observed_at','order':'id.desc','limit':100}) or []
 old=[row for row in candidates if row.get('request_key')==key]
 if old:
  obs=old[0]
  if obs.get('observation_status')=='received':return None
  retry=float(obs.get('retry_after') or 0)
  if not retry or (now-datetime.fromisoformat(obs['observed_at'])).total_seconds()<retry:return None
 return dict(key=key,cabinet='token_2',tool=tool,arguments=args)
hidden=io.StringIO()
try:
 with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
  report['purpose']='Exact Dblack order-detail gap 13 October; not complete history'
  gate.verify_storage(lambda v:put('advertising:recovery:health:'+RUN_ID,v),lambda:get('advertising:recovery:health:'+RUN_ID),{'run':RUN_ID,'scope':'Dblack-only'})
  import requests
  from urllib.parse import urlsplit
  native=requests.sessions.Session.request;dbhost=urlsplit(os.environ['SUPABASE_URL']).hostname
  def guarded(session,method,url,*a,**kw):
   host=urlsplit(url).hostname
   if host not in (dbhost,'mcp.mpstats.io'):raise RuntimeError('Only primary MPStats and storage')
   if host=='mcp.mpstats.io':gate.before_collection()
   return native(session,method,url,*a,**kw)
  requests.sessions.Session.request=guarded
  paused=database('GET','telegram_api_cache',params={'cache_key':'eq.mpstats:cooldown','expires_at':'gt.'+now.isoformat(),'select':'expires_at','limit':1}) or []
  if paused:report['pending_pause']=paused
  else:
   args={'type':'articles','value':'584-ReginaBag-dblack','date_from':'2026-10-13','date_to':'2026-10-13','start_row':0,'end_row':300}
   request=wanted('lk_wb_card_orders',args)
   if not request:report['reused_or_explicit_error']='Existing exact scope is not repeated; inspect retained receipt'
   else:
    caps=read('analytics_snapshots',dict(source='eq.mpstats_connection',cabinet='eq.shared',select='payload->0->tools',order='id.desc',limit=1))
    def saved(cabinet,observation):
     ident=save_snapshot('mpstats_lk_wb_card_orders',observation,'2026-10-13','2026-10-13')
     report['saved'].append({'id':ident,'readback':True,'status':observation.get('status')})
     report['observation']=observation
     seal('advertising-dblack-gap',report)
    def reader(call,checks,known):return execute_reads(call,checks,known,[request],copy.deepcopy(BIDDER),saved,max_requests=1)
    result=discover(os.environ.get('MPSTATS_API_TOKEN',''),read_checks=True,catalog=caps[0].get('tools') if caps else None,extra_reader=reader)
    report['provider_status']={k:v for k,v in result.items() if k not in ('tools','checks')}
    if result.get('retry_after'):
     put('mpstats:cooldown',dict(pending=True,retry_after=result['retry_after']))
     database('PATCH','telegram_api_cache',body={'expires_at':(datetime.now(timezone.utc)+timedelta(seconds=result['retry_after'])).isoformat()},params={'cache_key':'eq.mpstats:cooldown'})
except Exception as exc:report['error']=error(exc)
finally:
 report['private_log']=hidden.getvalue();seal('advertising-dblack-gap',report)
 print(json.dumps({'saved':report['saved'],'wb_calls':0,'wb_writes':0,'telegram_calls':0,'error_type':report.get('error',{}).get('type')}))
