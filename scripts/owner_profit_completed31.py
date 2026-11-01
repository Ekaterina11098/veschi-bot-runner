"""Owner-requested completed-day preliminary profit; bounded reads only, no Telegram."""
import os,json,requests
from datetime import date,datetime,timezone
from urllib.parse import urlparse
from china_cloud_cost_control import Cache
from china_analytic_dialog import allowed_read
from china_profit_forecast import collect,calculate
ROOT='china_agent:owner_profit_completed:2026-10-31:requested20261101:v1'
def main():
 c=Cache()
 if c.get(ROOT+':result'):print('Result already saved');return
 if not c.create(ROOT+':lease',dict(started_at=datetime.now(timezone.utc).isoformat())):return
 class Work:
  now=datetime.now(timezone.utc)
  def get(self,key):return c.get(key)
  def save(self,key,v,*args,**kwargs):
   value=json.loads(json.dumps(v));c.put(key,value);return True
  def catalog(self):return [(str(p['nmID']),p['vendorCode'])for p in(c.get('china_agent:prices:v1')or{}).get('rows',[])]
 original=requests.sessions.Session.request
 def guard(session,method,url,*args,**kw):
  u=urlparse(url);m=method.upper();body=kw.get('json')
  db=u.scheme=='https'and u.hostname==urlparse(c.url).hostname and u.path.startswith('/rest/v1/')and(m=='GET'or m in ['POST','PATCH']and u.path=='/rest/v1/telegram_api_cache')
  status=m=='POST'and u.hostname=='marketplace-api.wildberries.ru'and u.path=='/api/v3/orders/status'and set(body or{})=={'orders'}
  cbr=m=='GET'and u.hostname=='www.cbr.ru'and u.path=='/scripts/XML_daily.asp'
  if not(db or status or cbr or allowed_read(m,url,body)):raise PermissionError('Read-only profit request blocked external write')
  return original(session,method,url,*args,**kw)
 requests.sessions.Session.request=guard
 try:
  w=Work();day=date(2026,10,31);inputs,source=collect(w,dict(id='owner_completed31_20261101',request_text='Прогнозируемая прибыль за31октября'),day)
  inputs=json.loads(json.dumps(inputs));c.put(ROOT+':inputs',inputs)
  result=calculate(inputs,c.get('china_agent:new_ad_economics_policy:v1')or{},c.get('china_agent:expected_profit_delivery_model:v1')or{},day)
  result.update(source_key=source,observed_at=datetime.now(timezone.utc).isoformat())
  result=json.loads(json.dumps(result));c.put(ROOT+':result',result)
  if c.get(ROOT+':result')!=result:raise ValueError('Result readback mismatch')
  print(json.dumps({k:result.get(k)for k in ['status','modelled_orders','collection_errors','errors']}))
 except Exception as ex:
  c.put(ROOT+':error',dict(error=type(ex).__name__,observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0));raise
 finally:requests.sessions.Session.request=original
if __name__=='__main__':main()