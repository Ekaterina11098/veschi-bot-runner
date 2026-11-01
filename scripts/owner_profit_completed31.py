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
def reconcile_saved_inputs():
 from china_wb_evidence import Reports
 c=Cache()
 if c.get(ROOT+':result:v3'):return
 if not c.create(ROOT+':calculation_v3_lease',dict(started_at=datetime.now(timezone.utc).isoformat())):return
 state=c.get(ROOT+':inputs')
 if not state or state['inputs']['orders'].get('cutoff_msk')!='2026-11-01T00:00:00+03:00':raise ValueError('Full day orders missing')
 own=(c.get('china_agent:owner_profit_now:2026-10-31:v1:collection')or{}).get('inputs',{}).get('own_products')
 if not own or own.get('period_from')!='2026-10-01' or own.get('period_to')!='2026-10-30':raise ValueError('Exact own completed-day history missing')
 state['inputs']['own_products']=own;state.setdefault('repairs',{})['own_products']='Reused exact validated1-30Oct302SKU history; no new MPStats collection'
 state['errors'].pop('own_products',None)
 class Work:
  def get(self,key):return c.get(key)
  def save(self,key,value,*args,**kwargs):c.put(key,json.loads(json.dumps(value)));return True
  def db(self,method,path,params=None,body=None,prefer=None):
   if method!='GET'and not(method in ['POST','PATCH']and path=='telegram_api_cache'):raise PermissionError('Private write outside cache')
   r=requests.request(method,c.url.rsplit('/',1)[0]+'/'+path,params=params,json=body,headers=c.h|({'Prefer':prefer}if prefer else{}),timeout=35)
   r.raise_for_status();return r.json()if r.content else[]
 try:
  state['inputs']['finance']=Reports(Work()).finance('2026-10-31','2026-10-31');state['errors'].pop('finance',None)
 except Exception as ex:state['errors']['finance']=type(ex).__name__
 # Normalize documented case-insensitive currency and decimal-string money in a working copy.
 for row in state.get('inputs',{}).get('finance',{}).get('rows',[]):
  if str(row.get('currency','')).upper()!='CNY':raise ValueError('Finance currency unverified')
  row['currency']='CNY'
  for field in ['paidStorage','paidAcceptance','penalty','deduction','additionalPayment']:
   if isinstance(row.get(field),str):row[field]=float(row[field])
 state=json.loads(json.dumps(state));c.put(ROOT+':inputs:v3',state)
 result=calculate(state,c.get('china_agent:new_ad_economics_policy:v1')or{},c.get('china_agent:expected_profit_delivery_model:v1')or{},date(2026,10,31))
 # Saved own historical reverse logistics are a separate preliminary model, not final cohort charges.
 ownmap={int(r['nm_id']):r for r in own['rows']};fx=float(state['inputs']['fx']['rub_per_cny']);reverse=0.;missing_reverse=0
 for row in result['details']:
  product=ownmap.get(row['nm_id'],{});finished=product.get('finished_orders');back=product.get('backwardlogisticsum')
  if finished and isinstance(back,(int,float)):reverse+=back/finished/fx
  else:missing_reverse+=1
 result['totals']['model_reverse_logistics_cny']=reverse
 if result['totals']['forecast_profit_cny']is not None:
  result['totals']['forecast_profit_cny']-=reverse;result['totals']['forecast_profit_rub']=result['totals']['forecast_profit_cny']*fx
 result.update(source_key=ROOT+':inputs:v3',observed_at=datetime.now(timezone.utc).isoformat(),missing_reverse_model_orders=missing_reverse)
 result=json.loads(json.dumps(result));c.put(ROOT+':result:v3',result)
 if c.get(ROOT+':result:v3')!=result:raise ValueError('Calculation readback mismatch')
 print(json.dumps({k:result.get(k)for k in ['status','modelled_orders','collection_errors','errors']}))
if __name__=='__main__':
 main();reconcile_saved_inputs()