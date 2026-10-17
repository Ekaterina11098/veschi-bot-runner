"""WB exclusive missing funnel read; no Telegram or WB writes."""
import os,json
from urllib.parse import urlparse
from datetime import datetime,timezone
from china_agent.control_owner_preview import Preview
from analytics.collect import _fetch_transport as fetch
# Narrow missing-metric fallback only; shared provider cooldown remains enforced.
class Funnel(Preview):
 def guard(self,session,method,url,*a,**kw):
  p=urlparse(url)
  if p.hostname=='seller-analytics-api.wildberries.ru' and p.path=='/api/analytics/v3/sales-funnel/products/history' and method.upper()=='POST':
   expected=dict(selectedPeriod=dict(start='2026-10-14',end='2026-10-16'),nmIds=[1535337777],skipDeletedNm=False,aggregationLevel='day')
   if kw.get('json')!=expected:raise RuntimeError('WB funnel scope mismatch')
   return self.original_http(session,method,url,*a,**kw)
  return super().guard(session,method,url,*a,**kw)
 def collect(self):
  body=dict(selectedPeriod=dict(start='2026-10-14',end='2026-10-16'),nmIds=[1535337777],skipDeletedNm=False,aggregationLevel='day')
  result=dict(cabinet='token_3',nm_id='1535337777',requested_period=body['selectedPeriod'],telegram_calls=0,wb_writes=0)
  try:
   result['data']=fetch('POST','https://seller-analytics-api.wildberries.ru/api/analytics/v3/sales-funnel/products/history',os.environ['WB_TOKEN_3'],body=body,max_retry_wait=0)
   result['status']='received'
  except Exception as e:
   result.update(status='unavailable',error_type=type(e).__name__,detail=str(e)[:160])
  result['observed_at']=datetime.now(timezone.utc).isoformat()
  self.save('china_agent:control_gap_funnel:2026-10-17',result)
  print(json.dumps({k:result[k] for k in ('status','telegram_calls','wb_writes')}))
if __name__=='__main__':
 w=Funnel('control')
 try:w.collect()
 finally:
  import requests
  requests.sessions.Session.request=w.original_http
