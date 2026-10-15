"""Cache-only operation investigation. No WB, MPStats, Telegram, or canonical decisions."""
import os,sys,json,io,contextlib,hashlib
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from stock_deploy_support import seal,error
report={'source_calls':0,'telegram_calls':0,'wb_writes':0,'private_pin':'5b0c24c67408c28a709ab37db62999a02e2e0bd7'}
hidden=io.StringIO()
try:
 with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
  import requests
  from urllib.parse import urlsplit
  native=requests.sessions.Session.request;host=urlsplit(os.environ['SUPABASE_URL']).hostname
  def guarded(session,method,url,*a,**kw):
   if urlsplit(url).hostname!=host:raise RuntimeError('Cache-only investigation')
   return native(session,method,url,*a,**kw)
  requests.sessions.Session.request=guarded
  from analytics.stage_one import read
  from analytics.collect import database,RUN_ID
  from analytics.payload_storage import decode_rows
  from analytics.ip_operation_diagnosis import collect_cached
  source=read('analytics_snapshots',{'source':'eq.ip_working_mode_replay','cabinet':'eq.token_2',
   'id':'eq.17521','run_id':'eq.38803127207:1','select':'id,payload,period_from,period_to','order':'id.desc','limit':1}) or []
  source=decode_rows(source)
  if not source:raise RuntimeError('Required new cached analysis not complete yet; no source replay')
  replay=source[0]['payload'][0];start=date.fromisoformat(source[0]['period_from']);end=date.fromisoformat(source[0]['period_to'])
  products={}
  for row in replay['daily']['pair_decision_trace']:
   if (row.get('shop_profit') or {}).get('net_profit') is not None and row['shop_profit']['net_profit']<0:
    products[row['nm_id']]=row.get('article')
  report.update(analysis_snapshot_id=source[0]['id'],summary=replay['summary'],
   native_services=collect_cached(read,start,end,list(products.items())))
  index=read('analytics_snapshots',{'source':'eq.advertising_campaign_index','cabinet':'eq.token_2',
   'select':'id,payload,collected_at','order':'id.desc','limit':1}) or []
  report['campaign_scope']={'index_id':index[0]['id'],'observed_at':index[0]['collected_at'],
   'departed_campaign_id':40223879,'observations':[
   dict(status=g['status'],type=g['type'],**item)
   for g in index[0]['payload']['raw']['adverts'] for item in g.get('advert_list',[]) if item['advertId']==40223879],
   'operator_or_reason_known':False,'history_removed':False}
  digest=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
  expected=digest(report)
  database('POST','analytics_snapshots',body={'source':'ip_owner_operation_diagnosis','cabinet':'token_2',
   'period_from':str(start),'period_to':str(end),'status':'partial','run_id':RUN_ID,'payload':[report],
   'detail':'Retained services only; no primary profit replacement, source or Telegram calls'})
  saved=decode_rows(read('analytics_snapshots',{'source':'eq.ip_owner_operation_diagnosis','run_id':'eq.'+RUN_ID,
   'select':'id,payload','order':'id.desc','limit':1}) or [])
  if not saved or digest(saved[0]['payload'][0])!=expected:raise RuntimeError('Full diagnostic readback SHA mismatch')
  report['saved']={'id':saved[0]['id'],'sha256':expected,'full_readback_verified':True}
except Exception as exc:report['error']=error(exc)
finally:
 report['private_log']=hidden.getvalue();seal('advertising-operation-quality',report)
 print(json.dumps({'saved':report.get('saved',{}).get('full_readback_verified',False),'source_calls':0,'telegram_calls':0,'wb_writes':0,'error_type':report.get('error',{}).get('type')}))
