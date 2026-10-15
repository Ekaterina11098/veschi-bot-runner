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
def wanted(tool,args):
 key='token_2:'+tool+':'+json.dumps(args,sort_keys=True)
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
  probe={'run':RUN_ID,'scope':'advertising-ip','at':now.isoformat()}
  gate.verify_storage(lambda v:put('advertising:recovery:health:'+RUN_ID,v),lambda:get('advertising:recovery:health:'+RUN_ID),probe)
  import requests
  original=requests.sessions.Session.request;traffic={'bytes':0,'calls':0}
  allowed_host=__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(os.environ['SUPABASE_URL']).hostname
  def guarded(session,method,url,*args,**kwargs):
   host=__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(url).hostname
   if host not in (allowed_host,'mcp.mpstats.io'):raise RuntimeError('Source outside MPStats-only recovery allowlist')
   if host=='mcp.mpstats.io':gate.before_collection()
   if traffic['bytes']>=100_000_000:raise RuntimeError('100MB pass threshold reached; continue from saved receipts only')
   response=original(session,method,url,*args,**kwargs);traffic['bytes']+=len(response.content);traffic['calls']+=1
   return response
  requests.sessions.Session.request=guarded
  pause=database('GET','telegram_api_cache',params={'cache_key':'eq.mpstats:cooldown','expires_at':'gt.'+now.isoformat(),'select':'expires_at','limit':1}) or []
  if pause:report['pending_pause']=pause
  else:
   caps=read('analytics_snapshots',dict(source='eq.mpstats_connection',cabinet='eq.shared',select='payload->0->tools',order='id.desc',limit=1))
   catalog=caps[0].get('tools') if caps else None
   bidder=copy.deepcopy(BIDDER);state=get('mpstats:gap_requests:v1') or {}
   bidder['token_2']['campaign_ids']=state.get('bidder_map',{}).get('token_2',{}).get('campaign_ids',[])
   requests_plan=[]
   for offset in range(7):
    day=str(end-timedelta(days=offset))
    # Exact daily missing components only; old verified days are reused.
    existing=database('GET','analytics_snapshots',params={'source':'eq.mpstats_lk_wb_products','cabinet':'eq.token_2','status':'eq.complete','period_from':'eq.'+day,'period_to':'eq.'+day,'select':'id,observation_status:payload->0->>status,need_update:payload->0->data->data->>need_update','order':'id.desc','limit':5}) or []
    if any(x.get('observation_status')=='received' and str(x.get('need_update'))=='0' for x in existing):
     report.setdefault('reused_daily_ids',[]).extend(x['id'] for x in existing[:1]);continue
    req=wanted('lk_wb_products',dict(date_from=day,date_to=day,start_row=0,end_row=1500))
    if req:requests_plan.append(req)
   for kind in ('stats','state'):
    req=wanted('wbbidder_campaigns',dict(tokens=[152922],report=kind,d1=str(start),d2=str(end),limit=100,start_row=0,bidder_only=False,sort='wb_id',sort_dir='asc'))
    if req:requests_plan.append(req)
   existing_catalogs=read('analytics_snapshots',dict(source='eq.mpstats_campaign_catalog',cabinet='eq.token_2',period_from='eq.'+str(start),period_to='eq.'+str(end),select='id,payload',order='id.desc',limit=30)) or []
   catalogs_by_page={}
   for row in existing_catalogs:
    for cat in row.get('payload') or []:
     if isinstance(cat,dict):catalogs_by_page.setdefault((cat.get('report'),cat.get('start_row')),cat)
   report['catalogs']=list(catalogs_by_page.values())
   for kind in ('stats','state'):
    first=catalogs_by_page.get((kind,0))
    if first:
     for offset in range(100,first.get('total',0),100):
      args=dict(tokens=[152922],report=kind,d1=str(start),d2=str(end),limit=100,start_row=offset,bidder_only=False,sort='wb_id',sort_dir='asc')
      req=wanted('wbbidder_campaigns',args)
      if req:requests_plan.append(req)
   for cat in report['catalogs']:
    bidder['token_2']['campaign_ids']=sorted(set(bidder['token_2']['campaign_ids'])|{r['id'] for r in cat.get('rows',[])})
   report['planned']=requests_plan
   def saved(cabinet,obs):
    if cabinet!='token_2':raise RuntimeError('Unexpected cabinet')
    a,b=period(obs['arguments']);ident=save_snapshot('mpstats_'+obs['tool'],obs,a,b,'complete' if obs.get('status')=='received' else 'partial')
    report['saved'].append(dict(id=ident,key=obs['request_key'],status=obs.get('status'),readback=True))
    if obs.get('retry_after'):
     put('mpstats:cooldown',{'pending':True,'retry_after':obs['retry_after']})
     database('PATCH','telegram_api_cache',body={'expires_at':(datetime.now(timezone.utc)+timedelta(seconds=obs['retry_after'])).isoformat()},params={'cache_key':'eq.mpstats:cooldown'})
    if obs.get('status')=='received':
     try:
      source,normalized=normalize(obs,cabinet)
      if source:
       normalized['raw_snapshot_id']=ident
       nid=save_snapshot(source,normalized,normalized.get('period_from') or a,normalized.get('period_to') or b)
       index=get('mpstats:agent_reports:token_2:v1') or dict(cabinet='token_2',reports={})
       key=':'.join(str(normalized.get(k) or '') for k in ('tool','report','campaign_id','period_from','period_to','start_row','nm_id','scope_nm_id','query'))
       index['reports'][key]=dict(source=source,report=normalized)
       put('mpstats:agent_reports:token_2:v1',index)
       if source=='mpstats_products_validated':import_products(normalized,get,put)
       if source=='mpstats_campaign_catalog':
        bidder['token_2']['campaign_ids']=sorted(set(bidder['token_2']['campaign_ids'])|{r['id'] for r in normalized['rows']})
        report.setdefault('catalogs',[]).append(normalized)
     except (ValueError,KeyError,TypeError) as exc:report['normalization_errors'].append(dict(id=ident,error=str(exc)))
    seal('advertising-source',report)
   def reader(call,checks,known):
    results=execute_reads(call,checks,known,requests_plan,bidder,saved,max_requests=12)
    # No product statistics until the complete cabinet-wide catalog is evidenced.
    pages={}
    for cat in report.get('catalogs',[]):
     if cat.get('report')=='stats':pages[cat.get('start_row')]=cat
    rows=[r for offset,cat in sorted(pages.items()) for r in cat.get('rows',[])]
    full=bool(pages.get(0)) and len(rows)==pages[0].get('total') and len({r['id'] for r in rows})==len(rows)
    if full and not any(x['status']!='received' for x in results):
     configuration=read('analytics_snapshots',dict(source='eq.advertising_active_configuration',cabinet='eq.token_2',select='payload,collected_at',order='id.desc',limit=1)) or []
     cp=configuration[0]['payload'] if configuration else {}
     wbactive=set(cp.get('campaign_ids',[])) if isinstance(cp,dict) else set()
     active=[r['id'] for r in rows if (r.get('wb_id') in wbactive if wbactive else r.get('status_id')==9)]
     report['full_catalog_count']=len(rows)
     more=[]
     for cid in active:
      req=wanted('wbbidder_campaign_stats',dict(campaign_id=cid,report='products',d1=str(start),d2=str(end)))
      if req:more.append(req)
     report['active_mpstats_campaign_ids']=active;report['missing_campaign_aggregate_requests']=list(more)
     mapping={r.get('wb_id'):r['id'] for r in rows}
     experiments=database('GET','advertising_experiments',params={'cabinet':'eq.token_2','status':'eq.active','select':'id,campaign_id,nm_id,started_at','order':'id.asc','limit':100}) or []
     seen=set()
     for exp in experiments:
      cid=mapping.get(exp.get('campaign_id'));nm=exp.get('nm_id')
      if cid is None or not isinstance(nm,int):continue
      first=max(str(start),exp['started_at'][:10])
      identity=(cid,nm,first,str(end))
      if identity in seen:continue
      seen.add(identity)
      req=wanted('wbbidder_campaign_stats',dict(campaign_id=cid,nm_id=nm,report='days',d1=first,d2=str(end)))
      if req:more.append(req)
     report['pending_experiment_scopes']=[r for r in more if r['arguments'].get('report')=='days']
     results+=execute_reads(call,checks,known,more,bidder,saved,max_requests=max(0,20-len(results)))
    return results
   result=discover(os.environ.get('MPSTATS_API_TOKEN',''),read_checks=True,catalog=catalog,extra_reader=reader)
   report['provider_status']={k:v for k,v in result.items() if k not in ('tools','checks')}
   if result.get('retry_after'):
    put('mpstats:cooldown',dict(pending=True,retry_after=result['retry_after']))
    database('PATCH','telegram_api_cache',body={'expires_at':(datetime.now(timezone.utc)+timedelta(seconds=result['retry_after'])).isoformat()},params={'cache_key':'eq.mpstats:cooldown'})
   composed=read('analytics_snapshots',dict(source='eq.mpstats_products_composed',cabinet='eq.token_2',period_from='eq.'+str(start),period_to='eq.'+str(end),select='id,collected_at',order='id.desc',limit=1)) or []
   report['finance_composition']={'status':'reused','id':composed[0]['id']} if composed else compose_cached_finance('token_2',start,end,datetime.now(timezone.utc))
  report['traffic']=traffic
except Exception as exc:report['error']=error(exc)
finally:
 report['private_log']=hidden.getvalue();seal('advertising-source',report)
 print(json.dumps({'saved':len(report['saved']),'provider_status':report.get('provider_status',{}).get('status'),'pending_pause':bool(report.get('pending_pause')),'error_type':report.get('error',{}).get('type'),'wb_calls':0,'telegram_calls':0}))
