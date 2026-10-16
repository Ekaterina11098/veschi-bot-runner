"""Owner-approved exact product outcome refresh; no marketplace mutations or executable actions."""
import os,sys,json,copy,hashlib,contextlib,io
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from stock_deploy_support import seal,error
from analytics.collect import database,RUN_ID
from analytics.mpstats_probe import discover
from analytics.mpstats_gaps import execute_reads
from analytics.mpstats_recovery import BIDDER
from analytics.storage_collection_gate import CollectionGate
from advertising_agent import agent_store as store
now=datetime.now(timezone.utc)
r=dict(wb_calls=0,wb_writes=0,telegram_calls=0,saved=[],assumed_buyout_ratio=None,production_actions_created=0)
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def get(k):return store.cache_get(k)
def put(k,v):
 store.cache_set(k,v,ttl_days=365)
 if get(k)!=v:raise RuntimeError('Cache full readback mismatch')
gate=CollectionGate(Path(os.environ['RUNNER_TEMP'])/'cohort-storage-health.json',max_age_seconds=900,scope='ip-cohort-outcomes')
hidden=io.StringIO()
try:
 with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
  gate.verify_storage(lambda v:put('advertising:cohort:health:'+RUN_ID,v),lambda:get('advertising:cohort:health:'+RUN_ID),{'run':RUN_ID})
  import requests
  from urllib.parse import urlsplit
  original=requests.sessions.Session.request
  allowed=urlsplit(os.environ['SUPABASE_URL']).hostname
  def guarded(session,method,url,*a,**kw):
   host=urlsplit(url).hostname
   if host not in (allowed,'mcp.mpstats.io'):raise RuntimeError('Outside exact source allowlist')
   if host=='mcp.mpstats.io':gate.before_collection()
   return original(session,method,url,*a,**kw)
  requests.sessions.Session.request=guarded
  pause=database('GET','telegram_api_cache',params={'cache_key':'eq.mpstats:cooldown','expires_at':'gt.'+now.isoformat(),'select':'expires_at','limit':1}) or []
  if pause:r.update(status='paused',pause=pause)
  else:
   caps=database('GET','analytics_snapshots',params={'source':'eq.mpstats_connection','cabinet':'eq.shared','select':'payload->0->tools','order':'id.desc','limit':1})
   catalog=caps[0].get('tools')
   schema=next(x for x in catalog if x['name']=='lk_wb_card_orders')
   r['tool_schema']=schema
   plan=[]
   for pid in ('139147637','124391695'):
    args=dict(type='products',value=pid,date_from='2026-10-04',date_to='2026-10-15',start_row=0,end_row=300)
    plan.append(dict(key='owner-cohort-refresh:'+RUN_ID+':'+pid,cabinet='token_2',tool='lk_wb_card_orders',arguments=args))
   def saved(cabinet,obs):
    token=os.environ.get('MPSTATS_API_TOKEN','')
    obs=json.loads(json.dumps(obs,ensure_ascii=False).replace(token,'[REDACTED]')) if token else obs
    body=dict(source='mpstats_lk_wb_card_orders',cabinet=cabinet,run_id=RUN_ID,period_from='2026-10-04',period_to='2026-10-15',status='complete' if obs.get('status')=='received' else 'partial',payload=[obs],detail='Exact product outcome refresh includes older target orders; response completeness and maturity assessed separately')
    database('POST','analytics_snapshots',body=body)
    rows=database('GET','analytics_snapshots',params={'source':'eq.mpstats_lk_wb_card_orders','cabinet':'eq.token_2','run_id':'eq.'+RUN_ID,'order':'id.desc','select':'id,payload,collected_at','limit':1}) or []
    if not rows or digest(rows[0]['payload'])!=digest([obs]):raise RuntimeError('Exact source full readback failed')
    r['saved'].append(rows[0])
    seal('sku685-141-outcome-refresh',r)
    if obs.get('retry_after'):
     database('POST','telegram_api_cache',body=dict(cache_key='mpstats:cooldown',payload={'pending':True},expires_at=(datetime.now(timezone.utc)+timedelta(seconds=obs['retry_after'])).isoformat()),params={'on_conflict':'cache_key'})
   def reader(call,checks,known):return execute_reads(call,checks,known,plan,copy.deepcopy(BIDDER),saved,max_requests=2)
   result=discover(os.environ.get('MPSTATS_API_TOKEN',''),read_checks=True,catalog=catalog,extra_reader=reader)
   r['provider_status']={k:v for k,v in result.items() if k not in ('tools','checks')}
   r['status']='received_for_validation' if len(r['saved'])==2 and all(x['payload'][0].get('status')=='received' for x in r['saved']) else 'incomplete'
  key='advertising:ip:focus_preparation:20261016';memory=get(key) or {};updated=copy.deepcopy(memory)
  updated['outcome_refresh_20261016']=r
  readiness=updated.setdefault('pilot_57_readiness_20261016',{})
  readiness.update(preferred_end=None,proposed_start=None,end_time_preference_only=False,test_window_approved=False,backup_participation_authorized=False,backup_availability_confirmed=False,execution_authorized=False,restore_authorized=False)
  put(key,updated);r['common_memory_full_readback']=True
except Exception as e:r.update(status='incomplete',error=error(e))
finally:
 r['private_log']=hidden.getvalue();seal('sku685-141-outcome-refresh',r)
 print(json.dumps(dict(status=r.get('status'),saved=len(r['saved']),error_type=(r.get('error') or {}).get('type'),wb_writes=0)))
if r.get('status') not in ('received_for_validation','paused'):raise SystemExit(1)
