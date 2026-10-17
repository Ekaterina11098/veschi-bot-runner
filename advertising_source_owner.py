"""Bounded IP-only source recovery using existing MPStats normalization and cached history."""
import os,sys,json,time,copy,contextlib,io
from pathlib import Path
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from stock_deploy_support import seal,error
from analytics.collect import database,RUN_ID
from analytics.stage_one import read,cache,compose_cached_finance
import analytics.stage_one as finance_stage
from advertising_cached_finance_reader import install as install_bounded_finance
install_bounded_finance(finance_stage)
from analytics.mpstats_probe import discover,ProbeError
from analytics.mpstats_gaps import execute_reads,period
from analytics.mpstats_recovery import normalize,import_products,BIDDER
from analytics.storage_collection_gate import CollectionGate
from advertising_order_outcome_monitor import KEY as ORDER_MONITOR_KEY,seed as seed_order_monitor,plan as plan_order_checks,ingest as ingest_order_observation,financial_revision,historical_685_scope
now=datetime.now(timezone.utc);end=now.astimezone(ZoneInfo('Europe/Moscow')).date()-timedelta(days=1);start=end-timedelta(days=6)
report=dict(cabinet='token_2',period_from=str(start),period_to=str(end),saved=[],normalization_errors=[],wb_calls=0,wb_writes=0,telegram_calls=0)
gate=CollectionGate(Path(os.environ['RUNNER_TEMP'])/'ads-storage-health.json',max_age_seconds=900,scope='ip-ads-source')
def digest(v):
 import hashlib
 return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
class SourceTraffic:
 """Decoded HTTP-body accounting; not compressed wire bytes or JSON expansion."""
 def __init__(self,limit=100_000_000):
  self.limit=limit;self.bytes=0;self.calls=0;self.buckets={};self.repeated={};self.cleanup_calls=0
 def label(self,host,method,path,kwargs,db_host):
  if host=='mcp.mpstats.io':
   rpc=kwargs.get('json') or {};p=rpc.get('params') or {}
   return 'mpstats:'+str(p.get('name') or rpc.get('method'))
  table=path.rsplit('/',1)[-1];params=kwargs.get('params') or {};body=kwargs.get('json') or {}
  detail=body.get('source') or params.get('source') or ''
  key=str(params.get('cache_key') or body.get('cache_key') or '')
  if table=='telegram_api_cache':
   detail=key if any(x in key for x in ('mpstats:agent_reports:','mpstats:funnel_periods:','advertising:ip:order_outcome_monitor:')) else 'other_cache'
  return 'supabase:'+method.upper()+':'+table+':'+str(detail)
 def before(self,host,kwargs):
  if self.bytes<self.limit or host!='mcp.mpstats.io':return
  rpc=kwargs.get('json') or {};p=rpc.get('params') or {};args=p.get('arguments') or {}
  if p.get('name')=='lk_wb_cabinets' and args.get('action') in ('select','reset') and self.cleanup_calls<2:
   self.cleanup_calls+=1;return
  raise RuntimeError('100MB decoded-body collection threshold reached; durable saved results retained')
 def observed(self,label,response):
  n=len(response.content);self.bytes+=n;self.calls+=1
  b=self.buckets.setdefault(label,dict(calls=0,decoded_response_bytes=0,content_length_header_bytes=0))
  b['calls']+=1;b['decoded_response_bytes']+=n
  try:b['content_length_header_bytes']+=int(response.headers.get('Content-Length') or 0)
  except (TypeError,ValueError):pass
 def summary(self):
  return dict(limit_bytes=self.limit,bytes=self.bytes,calls=self.calls,buckets=self.buckets,
   measurement='len(response.content), HTTP decoded body; not compressed wire bytes or payload gzip expansion',
   cleanup_calls=self.cleanup_calls,threshold_blocks_new_mpstats_reads=True)

# Only derived append-like report caches are deferred. Immutable raw/normalized
# snapshots and order observer writes/readbacks remain immediate.
DEFERRED_CACHES={'mpstats:agent_reports:token_2:v1','mpstats:funnel_periods:token_2:v1'}
cache_memo={};cache_revisions={};cache_dirty=set()
def flush_derived_caches():
 for key in list(cache_dirty):
  value=cache_memo[key];stamp=cache_revisions[key]
  body=dict(payload=value,updated_at=datetime.now(timezone.utc).isoformat(),expires_at=(now+timedelta(days=365)).isoformat())
  if stamp is None:
   database('POST','telegram_api_cache',body=dict(body,cache_key=key),params={'on_conflict':'cache_key'},ignore_existing=True)
  else:
   database('PATCH','telegram_api_cache',body=body,params={'cache_key':'eq.'+key,'updated_at':'eq.'+stamp})
  rows=database('GET','telegram_api_cache',params={'cache_key':'eq.'+key,'select':'payload,updated_at','limit':1}) or []
  if len(rows)!=1 or digest(rows[0]['payload'])!=digest(value):
   gate.fail();raise RuntimeError('Derived cache CAS/full readback failed; reuse immutable snapshots, no blind write retry')
  cache_revisions[key]=rows[0]['updated_at'];cache_dirty.remove(key)

def get(k):
 if k in DEFERRED_CACHES:
  if k not in cache_memo:
   rows=database('GET','telegram_api_cache',params={'cache_key':'eq.'+k,'select':'payload,updated_at','limit':1}) or []
   cache_memo[k]=rows[0]['payload'] if rows else None
   cache_revisions[k]=rows[0].get('updated_at') if rows else None
  return copy.deepcopy(cache_memo[k])
 rows=database('GET','telegram_api_cache',params={'cache_key':'eq.'+k,'select':'payload','limit':1}) or []
 return rows[0]['payload'] if rows else None
def put(k,v):
 if k in DEFERRED_CACHES:
  if k not in cache_memo:get(k)
  cache_memo[k]=copy.deepcopy(v);cache_dirty.add(k);return
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
def campaign_day_gaps(snapshots,campaign_id,first,last,refresh_days=()):
 from datetime import date,timedelta
 covered=set()
 for snapshot in snapshots:
  for pack in snapshot.get('payload') or []:
   if (pack.get('campaign_id')!=campaign_id or pack.get('report')!='days'
       or pack.get('scope_nm_id') is not None or pack.get('spending_reconciled') is not True):continue
   for row in pack.get('rows') or []:
    day=str(row.get('date',''))[:10]
    if type(row.get('ac_spending_sum')) in (int,float):covered.add(day)
 missing=[];day=date.fromisoformat(first);finish=date.fromisoformat(last)
 while day<=finish:
  if str(day) not in covered or str(day) in refresh_days:missing.append(day)
  day+=timedelta(days=1)
 spans=[]
 for day in missing:
  if spans and day==spans[-1][1]+timedelta(days=1):spans[-1][1]=day
  else:spans.append([day,day])
 return [(str(a),str(b)) for a,b in spans]

def finance_refresh_reason(day, observations, now, explicit=False):
 """Completeness is not settlement finality; one exact-day revision per UTC day.
 Recent seven completed MSK days are mutable. Explicit older incidents stay scoped.
 A received revision suppresses recollection for 24h, not forever.
 """
 from datetime import date,datetime,timedelta
 from zoneinfo import ZoneInfo
 recent=0<(now.astimezone(ZoneInfo('Europe/Moscow')).date()-date.fromisoformat(day)).days<=7
 if not recent and not explicit:return None
 received=[o for o in observations if o.get('observation_status')=='received']
 if not received:return 'missing'
 try:age=(now-datetime.fromisoformat(received[0]['observed_at'].replace('Z','+00:00'))).total_seconds()
 except (KeyError,TypeError,ValueError):return 'freshness_unknown'
 if age<0:return 'freshness_unknown'
 if age>=24*3600:return 'late_accrual_revision'
 return None

def daily_refresh_dates(snapshots,campaign_id,first,last,now):
 from datetime import date,datetime,timedelta
 from zoneinfo import ZoneInfo
 today=now.astimezone(ZoneInfo('Europe/Moscow')).date();dates=set()
 for n in range(1,4):
  day=str(today-timedelta(days=n))
  if not first<=day<=last:continue
  candidates=[s for s in snapshots for p in s.get('payload') or []
   if p.get('campaign_id')==campaign_id and p.get('report')=='days'
   and p.get('scope_nm_id') is None and p.get('spending_reconciled') is True
   and any(str(r.get('date',''))[:10]==day for r in p.get('rows',[]))]
  try:fresh=any(0<=(now-datetime.fromisoformat(s['collected_at'].replace('Z','+00:00'))).total_seconds()<24*3600 for s in candidates)
  except (KeyError,ValueError,TypeError):fresh=False
  if not fresh:dates.add(day)
 return dates

def financial_response_state(observation):
 body=(observation.get('data') or {}).get('data') or {}
 return dict(response_complete=observation.get('status')=='received' and observation.get('scope_verified') is True
  and body.get('need_update')==0 and isinstance(body.get('data'),list) and body.get('total')==len(body['data']),
  accruals_final=False,accrual_finality='not_provided_by_source',
  advertising_basis='financial_recognition',campaign_spend_additive=False,
  zero_advertisement_is_final_absence=False)

# A dated push profile uses the same source runner/lock, never the daily schedule.
focus_profile={}
if os.getenv('GITHUB_EVENT_NAME')=='push' and os.getenv('GITHUB_WORKFLOW')=='Advertising IP source recovery only, owner preparation':
 try:
  candidate=json.loads((Path(__file__).parent/'advertising_source_continue.trigger').read_text())
  if candidate.get('mode')=='historical_685_twelve' and candidate.get('authorized_day')==str(now.astimezone(ZoneInfo('Europe/Moscow')).date()):focus_profile=candidate
 except (ValueError,FileNotFoundError):pass
focus_target_ids=None
hidden=io.StringIO()
try:
 with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
  probe={'run':RUN_ID,'scope':'advertising-ip','at':now.isoformat()}
  gate.verify_storage(lambda v:put('advertising:recovery:health:'+RUN_ID,v),lambda:get('advertising:recovery:health:'+RUN_ID),probe)
  order_monitor=seed_order_monitor(get(ORDER_MONITOR_KEY),get('advertising:ip:focus_preparation:20261016') or {})
  put(ORDER_MONITOR_KEY,order_monitor)
  report['order_outcome_monitor']={'tracked_orders':len(order_monitor.get('orders',{})),'wb_mutations':False,'maturity_not_inferred':True}
  import requests
  original=requests.sessions.Session.request;traffic=SourceTraffic()
  allowed_host=__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(os.environ['SUPABASE_URL']).hostname
  def guarded(session,method,url,*args,**kwargs):
   host=__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(url).hostname
   if host not in (allowed_host,'mcp.mpstats.io'):raise RuntimeError('Source outside MPStats-only recovery allowlist')
   if host=='mcp.mpstats.io':gate.before_collection()
   traffic.before(host,kwargs)
   parsed=__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(url)
   label=traffic.label(host,method,parsed.path,kwargs,allowed_host)
   response=original(session,method,url,*args,**kwargs);traffic.observed(label,response)
   return response
  requests.sessions.Session.request=guarded
  pause=database('GET','telegram_api_cache',params={'cache_key':'eq.mpstats:cooldown','expires_at':'gt.'+now.isoformat(),'select':'expires_at','limit':1}) or []
  if pause:report['pending_pause']=pause
  else:
   caps=read('analytics_snapshots',dict(source='eq.mpstats_connection',cabinet='eq.shared',select='payload->0->tools',order='id.desc',limit=1))
   catalog=caps[0].get('tools') if caps else None
   bidder=copy.deepcopy(BIDDER);state=get('mpstats:gap_requests:v1') or {}
   bidder['token_2']['campaign_ids']=state.get('bidder_map',{}).get('token_2',{}).get('campaign_ids',[])
   requests_plan=plan_order_checks(order_monitor,now,max_requests=4)
   report['planned_order_outcome_checks']=copy.deepcopy(requests_plan)
   refreshed_finance_days=set()
   gap_state=get('analytics:source_gaps') or {}
   explicit_finance_days={g.get('day') for g in gap_state.get('gaps',[]) if g.get('cabinet')=='token_2' and g.get('metric')=='advertising_spend' and g.get('status') in ('open','resolved_mpstats_daily')}
   finance_days=sorted({str(end-timedelta(days=i)) for i in range(7)} | explicit_finance_days,reverse=True)
   for day in finance_days:
    # Exact daily missing components only; old verified days are reused.
    existing=database('GET','analytics_snapshots',params={'source':'eq.mpstats_lk_wb_products','cabinet':'eq.token_2','status':'eq.complete','period_from':'eq.'+day,'period_to':'eq.'+day,'select':'id,observation_status:payload->0->>status,need_update:payload->0->data->data->>need_update,observed_at:payload->0->>observed_at','order':'id.desc','limit':5}) or []
    refresh_reason=finance_refresh_reason(day,existing,now,explicit=day in explicit_finance_days)
    if refresh_reason is None and any(x.get('observation_status')=='received' and str(x.get('need_update'))=='0' for x in existing):
     report.setdefault('reused_daily_ids',[]).extend(x['id'] for x in existing[:1]);continue
    req=wanted('lk_wb_products',dict(date_from=day,date_to=day,start_row=0,end_row=1500),purpose='finance-revision:'+str(now.date()) if refresh_reason else None)
    if req:requests_plan.append(req)
   prior_catalogs=read('analytics_snapshots',dict(source='eq.mpstats_campaign_catalog',cabinet='eq.token_2',period_from='eq.'+str(start),period_to='eq.'+str(end),select='payload',order='id.desc',limit=20)) or []
   retained_catalogs=[v for row in prior_catalogs for v in row.get('payload',[]) if isinstance(v,dict)]
   for kind in ('stats','state'):
    total=max([x.get('total',0) for x in retained_catalogs if x.get('report')==kind]+[1])
    for offset in range(0,total,100):
     req=wanted('wbbidder_campaigns',dict(tokens=[152922],report=kind,d1=str(start),d2=str(end),limit=100,start_row=offset,bidder_only=False,sort='wb_id',sort_dir='asc'))
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
   focused=bool(focus_profile) or os.getenv('FOCUSED_DAILY_GAPS') in ('20261012-15','20261009-11-focus')
   if focused and not focus_profile:
    requests_plan=[]
    mapping={r['wb_id']:r['id'] for cat in report.get('catalogs',[]) for r in cat.get('rows',[])}
    configuration=read('analytics_snapshots',dict(id='eq.17613',select='payload'))[0]['payload']
    active_wb=configuration['campaign_ids']
    scopes=[(mapping[cid],None) for cid in active_wb]
    scopes += [(mapping[cid],nm) for cid,nm in ((40223314,1123677454),(39634287,1123677454),(40428505,1123677454),(39410834,320248210),(39483230,320248210),(39410834,1007948808),(39634287,1007948808))]
    gap_start,gap_end='2026-10-12','2026-10-15'
    if os.getenv('FOCUSED_DAILY_GAPS')=='20261009-11-focus':
     scopes=[(mapping[cid],nm) for cid,nm in ((40223314,1123677454),(39634287,1123677454),(40428505,1123677454),(39410834,320248210),(39410834,1007948808),(39634287,1007948808))]
     gap_start,gap_end='2026-10-09','2026-10-11'
    for cid,nm in scopes:
     args=dict(campaign_id=cid,report='days',d1=gap_start,d2=gap_end)
     if nm is not None:args['nm_id']=nm
     req=wanted('wbbidder_campaign_stats',args)
     if req:requests_plan.append(req)
    if os.getenv('FOCUSED_DAILY_GAPS')=='20261009-11-focus':
     req=wanted('wbbidder_campaign_stats',dict(campaign_id=mapping[40696479],nm_id=320248210,report='days',d1='2026-10-09',d2='2026-10-15'))
     if req:requests_plan.append(req)
    report['daily_gap_cause']='Existing collector requested active products aggregates; days only for active experiments. Weekly finance, products and days coverage are independent.'
    report['scope']='exact retained missing12-15October; no balances or full recollection'
   if focus_profile:
    scope=historical_685_scope(get('advertising:ip:focus_preparation:20261016') or {})
    focus_target_ids=set(scope['target_gnumbers'])
    requests_plan=[dict(key='owner-historical-685-twelve:'+focus_profile['nonce']+':'+a+':'+b,cabinet='token_2',tool='lk_wb_card_orders',
     arguments=dict(type='products',value=scope['product_id'],date_from=a,date_to=b,start_row=0,end_row=300),priority=100) for a,b in scope['spans']]
    report['historical_twelve_scope']=scope
    report['scope']='Exact retained twelve GN; minimal product/date scopes because API has no GN filter'
   report['planned']=requests_plan
   def saved(cabinet,obs):
    if cabinet!='token_2':raise RuntimeError('Unexpected cabinet')
    a,b=period(obs['arguments']);ident=save_snapshot('mpstats_'+obs['tool'],obs,a,b,'complete' if obs.get('status')=='received' else 'partial')
    report['saved'].append(dict(id=ident,key=obs['request_key'],status=obs.get('status'),readback=True))
    if obs.get('status')=='received' and obs['tool']=='lk_wb_card_orders':
     try:updated_monitor=ingest_order_observation(order_monitor,obs,ident,target_new_ids=focus_target_ids)
     except ValueError as exc:
      report.setdefault('order_outcome_limits',[]).append(dict(snapshot_id=ident,reason=str(exc),unknown_is_not_zero=True))
     else:
      put(ORDER_MONITOR_KEY,updated_monitor)
      order_monitor.clear();order_monitor.update(updated_monitor)
      report['order_outcome_monitor'].update(tracked_orders=len(order_monitor['orders']),last_snapshot_id=ident,full_readback=True)
    if obs.get('status')=='received' and obs['tool']=='lk_wb_products':
     updated_monitor=financial_revision(order_monitor,obs,datetime.now(timezone.utc))
     if updated_monitor!=order_monitor:
      put(ORDER_MONITOR_KEY,updated_monitor)
      order_monitor.clear();order_monitor.update(updated_monitor)
    if obs.get('retry_after'):
     put('mpstats:cooldown',{'pending':True,'retry_after':obs['retry_after']})
     database('PATCH','telegram_api_cache',body={'expires_at':(datetime.now(timezone.utc)+timedelta(seconds=obs['retry_after'])).isoformat()},params={'cache_key':'eq.mpstats:cooldown'})
    if obs.get('status')=='received':
     if obs['tool']=='lk_wb_products':
      refreshed_finance_days.add(a)
      report.setdefault('financial_response_states',[]).append(dict(day=a,snapshot_id=ident,**financial_response_state(obs)))
     if ':confirmed-finance-gap:' in obs['request_key']:
      import math
      body=(obs.get('data') or {}).get('data') or {};items=body.get('data') or []
      fields=('sales_ret_sum','for_pay','advertisement','total_commission_without_spp','acquiring','logistic_all','storage_fee','deduction','acceptance','penalty')
      balanced=bool(items) and body.get('total')==len(items) and body.get('need_update')==0
      try:
       for item in items:
        vals={k:float(item[k]) for k in fields}
        if not all(math.isfinite(v) for v in vals.values()) or abs(vals['sales_ret_sum']-vals['for_pay']-sum(vals[k] for k in fields[2:]))>.05:balanced=False
       spend=sum(float(item['advertisement']) for item in items)
      except (TypeError,KeyError,ValueError):balanced=False;spend=None
      report['finance_gap_observation']={'day':a,'snapshot_id':ident,'balanced':balanced,'advertising_spend':spend,'resolved':False}
      if balanced and spend is not None and spend>0:
       current=database('GET','telegram_api_cache',params={'cache_key':'eq.analytics:source_gaps','select':'payload,updated_at','limit':1}) or []
       if current:
        updated=copy.deepcopy(current[0]['payload'])
        for gap in updated.get('gaps',[]):
         if gap.get('cabinet')=='token_2' and gap.get('day')==a and gap.get('metric')=='advertising_spend' and gap.get('status')=='open':
          gap.update(status='resolved_mpstats_daily',mpstats_daily_snapshot_id=ident,resolved_at=datetime.now(timezone.utc).isoformat(),resolution='Fresh exact-day complete MPStats financial report with nonzero expense and balanced components')
        database('PATCH','telegram_api_cache',params={'cache_key':'eq.analytics:source_gaps','updated_at':'eq.'+current[0]['updated_at']},body={'payload':updated,'updated_at':datetime.now(timezone.utc).isoformat()})
        report['finance_gap_observation']['resolved']=get('analytics:source_gaps')==updated
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
    results=execute_reads(call,checks,known,requests_plan,bidder,saved,max_requests=20 if focused else 12)
    if focused:return results
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
     retained_days=read('analytics_snapshots',{'source':'eq.mpstats_campaign_report','cabinet':'eq.token_2','payload->0->>report':'eq.days','select':'id,payload,collected_at','order':'id.desc','limit':1000})
     report['campaign_daily_gaps']={}
     for cid in active:
      for first,last in campaign_day_gaps(retained_days,cid,str(start),str(end),daily_refresh_dates(retained_days,cid,str(start),str(end),now)):
       report['campaign_daily_gaps'].setdefault(str(cid),[]).append([first,last])
       day_req=wanted('wbbidder_campaign_stats',dict(campaign_id=cid,report='days',d1=first,d2=last),purpose='daily-revision:'+str(now.date()))
       if day_req:more.append(day_req)
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
     assessment=database('GET','analytics_snapshots',params={'source':'eq.ip_owner_checkpoint_preview','cabinet':'eq.token_2','select':'payload','order':'id.desc','limit':1}) or []
     missing_before=[]
     if assessment:
      for exp in assessment[0]['payload'][0].get('experiments',[]):
       missing=sorted({day for cp in exp.get('checkpoints',[]) for day in cp.get('before',{}).get('missing_days',[])})
       cid=mapping.get(exp.get('campaign_id'))
       if missing and cid is not None:
        identity=next((e for e in experiments if e['id']==exp['experiment_id']),None)
        if identity:missing_before.append((cid,identity['nm_id'],missing[0],missing[-1]))
     for cid,nm,first,last in missing_before:
      # Before requesting a smaller gap, reuse a valid longer retained raw receipt.
      from analytics.collect import _database_transport
      markers=_database_transport('GET','analytics_snapshots',params={'source':'eq.mpstats_wbbidder_campaign_stats','cabinet':'eq.token_2','period_from':'lte.'+first,'period_to':'gte.'+last,'select':'id,cid:payload->0->arguments->>campaign_id,nm:payload->0->arguments->>nm_id,kind:payload->0->arguments->>report,state:payload->0->>status','order':'id.desc','limit':1000}) or []
      reused=False
      for marker in markers:
       if str(marker.get('cid'))!=str(cid) or str(marker.get('nm'))!=str(nm) or marker.get('kind')!='days' or marker.get('state')!='received':continue
       raw=read('analytics_snapshots',dict(id='eq.'+str(marker['id']),select='payload',limit=1))
       try:
        source,valid=normalize(raw[0]['payload'][0],'token_2')
        if source=='mpstats_campaign_report' and valid.get('spending_reconciled'):
         valid['raw_snapshot_id']=marker['id'];save_snapshot(source,valid,valid['period_from'],valid['period_to'])
         report.setdefault('reused_baseline_raw_ids',[]).append(marker['id']);reused=True;break
       except (ValueError,KeyError,TypeError):continue
      if not reused:
       req=wanted('wbbidder_campaign_stats',dict(campaign_id=cid,nm_id=nm,report='days',d1=first,d2=last))
       if req:more.append(req)
     report['pending_experiment_scopes']=[r for r in more if r['arguments'].get('report')=='days']
     results+=execute_reads(call,checks,known,more,bidder,saved,max_requests=max(0,20-len(results)))
    return results
   result=discover(os.environ.get('MPSTATS_API_TOKEN',''),read_checks=True,catalog=catalog,extra_reader=reader)
   report['provider_status']={k:v for k,v in result.items() if k not in ('tools','checks')}
   if result.get('retry_after'):
    put('mpstats:cooldown',dict(pending=True,retry_after=result['retry_after']))
    database('PATCH','telegram_api_cache',body={'expires_at':(datetime.now(timezone.utc)+timedelta(seconds=result['retry_after'])).isoformat()},params={'cache_key':'eq.mpstats:cooldown'})
   flush_derived_caches()
   composed=read('analytics_snapshots',dict(source='eq.mpstats_products_composed',cabinet='eq.token_2',period_from='eq.'+str(start),period_to='eq.'+str(end),select='id,collected_at',order='id.desc',limit=1)) or []
   report['refreshed_finance_days']=sorted(refreshed_finance_days)
   # Recompose current window from latest exact-day versions, never add campaign spend.
   report['finance_composition']={'status':'reused','id':composed[0]['id']} if composed and not refreshed_finance_days else compose_cached_finance('token_2',start,end,datetime.now(timezone.utc))
   # Older explicit incidents may affect retained overlapping periods too.
   if refreshed_finance_days:
    periods=read('analytics_snapshots',dict(source='eq.mpstats_products_composed',cabinet='eq.token_2',select='period_from,period_to',order='id.desc',limit=200)) or []
    affected={(r['period_from'],r['period_to']) for r in periods if any(r['period_from']<=d<=r['period_to'] for d in refreshed_finance_days)}
    from datetime import date
    report['recomposed_affected_periods']=[]
    for a,b in sorted(affected-{(str(start),str(end))})[:10]:
     result=compose_cached_finance('token_2',date.fromisoformat(a),date.fromisoformat(b),datetime.now(timezone.utc))
     report['recomposed_affected_periods'].append(dict(period_from=a,period_to=b,result=result))
    report['affected_periods_beyond_pass_limit']=max(0,len(affected-{(str(start),str(end))})-10)
  report['traffic']=traffic.summary()
except Exception as exc:report['error']=error(exc)
finally:
 try:flush_derived_caches()
 except Exception as flush_error:
  report['cache_flush_error']=error(flush_error)
  if 'error' not in report:report['error']=error(flush_error)
 if 'traffic' in globals():report['traffic']=traffic.summary()
 report['business_status']='failed' if report.get('cache_flush_error') else ('incomplete' if report.get('error') or report.get('pending_pause') or report.get('normalization_errors') else 'complete')
 report['completed_units']=[dict(id=x['id'],key=x['key'],status=x['status']) for x in report['saved'] if x.get('readback')]
 report['private_log']=hidden.getvalue();seal('advertising-source',report)
 print(json.dumps({'saved':len(report['saved']),'provider_status':report.get('provider_status',{}).get('status'),'pending_pause':bool(report.get('pending_pause')),'error_type':report.get('error',{}).get('type'),'business_status':report['business_status'],'reason':report.get('error',{}).get('type') or ('pending_pause' if report.get('pending_pause') else None),'completed_units':report['completed_units'],'wb_calls':0,'telegram_calls':0}))

