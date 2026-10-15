"""Save the completed primary-source Dblack expense explanation. Cache only."""
import os,sys,json,contextlib,io,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'private-source'))
from stock_deploy_support import seal,error
report={'source_calls':0,'wb_writes':0,'telegram_calls':0,'private_pin':'b4a0ed969134c84752c4588fd916644d0a0117e7'}
hidden=io.StringIO()
try:
 with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
  import requests
  from urllib.parse import urlsplit
  host=urlsplit(os.environ['SUPABASE_URL']).hostname;native=requests.sessions.Session.request
  def guarded(session,method,url,*a,**kw):
   if urlsplit(url).hostname!=host:raise RuntimeError('Cache only; no marketplace or Telegram')
   return native(session,method,url,*a,**kw)
  requests.sessions.Session.request=guarded
  from analytics.stage_one import read
  from analytics.collect import database,RUN_ID
  from analytics.payload_storage import decode_rows
  from analytics.ip_operation_diagnosis import explain_primary_order_logistics
  raw=read('analytics_snapshots',{'id':'eq.17526','source':'eq.mpstats_lk_wb_card_orders','cabinet':'eq.token_2','select':'id,payload','limit':1})
  report['new_order_delivery']=explain_primary_order_logistics(raw[0]['payload'][0],699208547,124410488,'2026-10-13',312.63)
  if not report['new_order_delivery']['amount_reconciled']:raise RuntimeError('Primary order amount not explained')
  operations=decode_rows(read('analytics_snapshots',{'id':'eq.17524','source':'eq.ip_owner_operation_diagnosis','cabinet':'eq.token_2','select':'id,payload','limit':1}))
  case=next(p for p in operations[0]['payload'][0]['native_services']['products'] if p['nm_id']==699208547)
  canceled=[r for r in case['operations'] if r['day']=='2026-10-10' and r['service_reason'] in ('К клиенту при отмене','От клиента при отмене')]
  if len(canceled)!=2 or len({r['order_id'] for r in canceled})!=1 or len({r['operation_id'] for r in canceled})!=2 or abs(sum(r['logistics'] for r in canceled)-396.39)>.005:
   raise RuntimeError('Retained cancellation explanation changed')
  report.update(status='primary_period_logistics_explained',cancelled_order_services=canceled,
   logistics_total=709.02,storage=30.19,advertising=7.05,mpstats_period_profit=-746.26,
   old_provisional_reconciliation={'day':'2026-10-08','status':'open_source_recognition_question',
    'does_not_override_primary_profit':True,'old_operations':[r for r in case['operations'] if r['day']=='2026-10-08']},
   new_action=None,reason='Reported period cost includes cancelled-order delivery and an unsettled new order; no evidence for bid/price/photo change or disputed tariff')
  digest=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
  expected=digest(report)
  database('POST','analytics_snapshots',body={'source':'ip_dblack_resolved_diagnosis','cabinet':'token_2',
   'period_from':'2026-10-08','period_to':'2026-10-14','run_id':RUN_ID,'status':'partial','payload':[report],
   'detail':'Primary financial expense explained; old provisional recognition question separate; forecast not settled profit'})
  saved=decode_rows(read('analytics_snapshots',{'source':'eq.ip_dblack_resolved_diagnosis','run_id':'eq.'+RUN_ID,
   'select':'id,payload','order':'id.desc','limit':1}) or [])
  if not saved or digest(saved[0]['payload'][0])!=expected:raise RuntimeError('Full readback SHA mismatch')
  report['saved']={'id':saved[0]['id'],'sha256':expected,'full_readback_verified':True}
except Exception as exc:report['error']=error(exc)
finally:
 report['private_log']=hidden.getvalue();seal('advertising-dblack-resolved',report)
 print(json.dumps({'status':report.get('status'),'saved':report.get('saved',{}).get('full_readback_verified',False),
  'source_calls':0,'wb_writes':0,'telegram_calls':0,'error_type':report.get('error',{}).get('type')}))
