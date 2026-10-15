"""One exact Finance service-code gap, using existing cursor and shared request guard."""
import os,sys,json,io,contextlib,hashlib
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from stock_deploy_support import seal,error
report={'wb_writes':0,'telegram_calls':0,'scope':{'cabinet':'token_2','nm_id':699208547,'day':'2026-10-13'},'code':'79d716d679a0465ee43d0ae18691a9d9c7fb8832'}
hidden=io.StringIO();collector=None
try:
 with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
  from analytics.collect import database,RUN_ID
  from analytics.stage_one import read
  from analytics.finance_daily import Collector,credential,request,Deferred
  from analytics.ip_operation_diagnosis import summarize
  from analytics.storage_collection_gate import CollectionGate
  from analytics.payload_storage import decode_rows
  import requests
  from urllib.parse import urlsplit
  gate=CollectionGate(Path(os.environ['RUNNER_TEMP'])/'dblack-finance-health.json',max_age_seconds=900,scope='exact-Dblack-service-gap')
  digest=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
  key='advertising:dblack-service-health:'+RUN_ID
  def get():
   r=read('telegram_api_cache',{'cache_key':'eq.'+key,'select':'payload','limit':1}) or []
   return r[0]['payload'] if r else None
  def put(value):
   database('POST','telegram_api_cache',body={'cache_key':key,'payload':value,'updated_at':datetime.now(timezone.utc).isoformat(),
    'expires_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()},params={'on_conflict':'cache_key'})
  gate.verify_storage(put,get,{'run':RUN_ID,'scope':'Dblack13Oct'})
  primary=read('analytics_snapshots',{'id':'eq.17419','source':'eq.mpstats_lk_wb_products','cabinet':'eq.token_2','select':'id,payload','limit':1})
  observation=primary[0]['payload'][0];body=observation['data']['data'];args=observation['arguments']
  if not(observation.get('scope_verified') is True and observation.get('status')=='received'
   and args.get('date_from')==args.get('date_to')=='2026-10-13' and body.get('need_update')==0
   and body.get('total')==len(body.get('data',[]))):raise RuntimeError('Primary financial scope not complete')
  products=[x for x in body['data'] if x.get('nm_id')==699208547]
  if len(products)!=1 or abs(products[0]['logistic_all']-312.63)>.005:raise RuntimeError('Exact primary expense changed')
  if any(k in products[0] for k in ('operation_code','supplier_oper_name','sellerOperName','rrdId','rrd_id','srid')):
   raise RuntimeError('Primary may already contain exclusive operation fields; inspect before WB')
  evidence={'cabinet':'token_2','purpose':'service_operation_explanation','source':'mpstats_lk_wb_products',
   'scope_verified':True,'pagination_complete':True,'source_snapshot_id':17419,'nm_id':699208547,
   'reported_logistics':312.63,'missing_fields':['operation_code','rrdId','srid'],'period_from':'2026-10-13','period_to':'2026-10-13'}
  report['primary_gap']=evidence
  native=requests.sessions.Session.request;dbhost=urlsplit(os.environ['SUPABASE_URL']).hostname
  def guarded(session,method,url,*a,**kw):
   u=urlsplit(url)
   if u.hostname!=dbhost:
    if not(u.hostname=='finance-api.wildberries.ru' and method.upper()=='POST'
     and u.path=='/api/finance/v1/sales-reports/detailed'):raise RuntimeError('Exact read-only Finance allowlist')
    gate.before_collection()
   return native(session,method,url,*a,**kw)
  requests.sessions.Session.request=guarded
  token,kind=credential('token_2')
  if not token:raise RuntimeError('Dedicated Finance credential unavailable')
  collector=Collector(fetch=lambda token,body:request(token,body,gap_evidence=evidence),max_requests=2)
  values,marker=collector.collect_day('token_2',token,date(2026,10,13))
  report.update(status='complete_cached_day',actual_wb_read_requests=collector.requests,
   finance_marker={'run_id':marker['run_id'],'collected_at':marker['collected_at'],'row_count':marker['payload']['row_count'],
    'provisional':marker['payload'].get('provisional')},diagnosis=summarize(values,699208547))
  source='ip_dblack_service_operation';expected=digest(report)
  database('POST','analytics_snapshots',body={'source':source,'cabinet':'token_2','period_from':'2026-10-13',
   'period_to':'2026-10-13','run_id':RUN_ID,'status':'partial','payload':[report],
   'detail':'Exact missing service operation; MPStats profit unchanged; no advertising or stock/review mutations'})
  saved=decode_rows(read('analytics_snapshots',{'source':'eq.'+source,'run_id':'eq.'+RUN_ID,'select':'id,payload','order':'id.desc','limit':1}) or [])
  if not saved or digest(saved[0]['payload'][0])!=expected:raise RuntimeError('Diagnostic full readback mismatch')
  report['saved']={'id':saved[0]['id'],'sha256':expected,'full_readback_verified':True}
except Exception as exc:
 if type(exc).__name__=='Deferred':
  report.update(status='pending',reason=str(exc),retry_after_seconds=exc.seconds,
   next_retry_at=(datetime.now(timezone.utc)+timedelta(seconds=exc.seconds)).isoformat())
 else:report['error']=error(exc)
finally:
 if collector:report['actual_wb_read_requests']=collector.requests
 report['private_log']=hidden.getvalue();seal('advertising-dblack-service',report)
 print(json.dumps({'status':report.get('status'),'reads':report.get('actual_wb_read_requests',0),
  'wb_writes':0,'telegram_calls':0,'next_retry_at':report.get('next_retry_at'),'error_type':report.get('error',{}).get('type')}))
