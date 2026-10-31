"""One bounded owner-authorized read; no Telegram token and no marketplace writes."""
import os,json
from datetime import datetime,timedelta,timezone
import requests
from china_cloud_cost_control import Cache,WB,validate_identity
from china_analytic_dialog import Analyst,allowed_read
from china_product_current import scoped
ROOT='china_agent:owner_diagnostic_inputs:2026-10-31:v1'
IDS=[1473243911,1473245494,1473245495,1473245508]
def run():
 c=Cache()
 if c.get(ROOT):return
 validate_identity(c,WB())
 class W:
  now=datetime.now(timezone.utc)
  def get(self,k):return c.get(k)
  def save(self,k,v):return c.put(k,v) if c.get(k) else c.create(k,v)
  def catalog(self):return [(str(p['nmID']),p['vendorCode']) for p in (c.get('china_agent:prices:v1')or{}).get('rows',[]) if p['nmID']in IDS]
 w=W();a=Analyst(w,dict(id='owner-diagnostic-inputs31',request_text='Адресная проверка цены и экономики'),[])
 end=w.now.astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date()-timedelta(days=1);first=end-timedelta(days=29)
 original=requests.sessions.Session.request
 def guard(session,method,url,**kw):
  from urllib.parse import urlparse
  u=urlparse(url)
  if url.startswith(c.url) and u.path.endswith('/telegram_api_cache'):
   if method.upper() not in ['GET','POST','PATCH']:raise ValueError('Private cache method')
  elif not allowed_read(method,url,kw.get('json')):raise ValueError('Non-read endpoint blocked')
  return original(session,method,url,**kw)
 requests.sessions.Session.request=guard
 result=dict(observed_at=w.now.isoformat(),cabinet='token_3',nm_ids=IDS,inputs={},errors={},wb_writes=0,telegram_calls=0,grants_action_permission=False)
 try:
  for topic in ['prices','stock','products']:
   try:result['inputs'][topic]=scoped(a,topic,IDS,first,end,900 if topic!='products' else 86400)
   except Exception as ex:result['errors'][topic]=str(ex)[:240] if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__
 finally:requests.sessions.Session.request=original
 result['status']='complete' if not result['errors'] else 'partial';result['completed_at']=datetime.now(timezone.utc).isoformat()
 if not c.create(ROOT,result):raise ValueError('Immutable result duplicate')
 saved=c.get(ROOT)
 if saved!=result:raise ValueError('Private result readback mismatch')
 print(json.dumps(dict(status=result['status'],topics=list(result['inputs']),errors=result['errors'],wb_writes=0,telegram_calls=0)))
if __name__=='__main__':run()
