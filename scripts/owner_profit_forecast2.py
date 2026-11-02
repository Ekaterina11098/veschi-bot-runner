"""Owner requested two-date same-cutoff forecast. WB reads only; no Telegram."""
import json,requests,os,copy
from datetime import datetime,date,timezone
from urllib.parse import urlparse
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
from china_advertising_state import AdvertisingIO
from china_moysklad_read import read_stock
from china_profit_forecast import calculate
from china_analytic_dialog import allowed_read,reading
ROOT='china_agent:owner_profit_forecast:2026-11-02T22:codex224:v1'
SOURCE='china_agent:hourly_sales_api:v1:snapshot:2026-11-02T22:MSK'
def main():
 c=Cache()
 if c.get(ROOT+':result'):return
 if not c.create(ROOT+':lease:v2',dict(started_at=stamp())):return
 wb=WB();validate_identity(c,wb);original=requests.sessions.Session.request
 def guard(session,method,url,*args,**kw):
  u=urlparse(url);m=method.upper();body=kw.get('json')
  db=u.hostname==urlparse(c.url).hostname and u.path.startswith('/rest/v1/')and(m=='GET'or m in ['POST','PATCH']and u.path=='/rest/v1/telegram_api_cache')
  status=m=='POST'and u.hostname=='marketplace-api.wildberries.ru'and u.path=='/api/v3/orders/status'and set(body or{})=={'orders'}
  if not(db or status or allowed_read(m,url,body)):raise PermissionError('Read-only comparison blocked write')
  return original(session,method,url,*args,**kw)
 context=reading();context.__enter__()
 requests.sessions.Session.request=guard
 try:
  current=c.get(SOURCE)
  if current.get('status')!='complete' or current.get('cabinet')!='token_3':raise ValueError('Complete dated source missing')
  own=c.get('china_agent:analytic_read:v1:893557e46ce1918d55ff958ce88fd1f202ee06e10e60792aeabbbb67cd857b35')
  if own['period_from']!='2026-10-03' or own['period_to']!='2026-11-01':raise ValueError('Own history date mismatch')
  slices=[('today',date(2026,11,2),current['orders']['0'],current['advertising'],SOURCE)]
  orders={r['id']:r for _,_,o,_,_ in slices for r in o['rows']}
  if len(orders)>1000:raise ValueError('Status request exceeds single batch')
  rr=requests.post('https://marketplace-api.wildberries.ru/api/v3/orders/status',headers={'Authorization':wb.token},json={'orders':list(orders)},timeout=55);rr.raise_for_status();statuses=rr.json()['orders']
  if {r['id']for r in statuses}!=set(orders):raise ValueError('Status coverage missing')
  class Prices(AdvertisingIO):
   def __init__(self,token):self.token=token
  raw=Prices(wb.token).prices(sorted({r['nmId']for r in orders.values()}));prices=[]
  for nm,r in raw.items():
   vals={s['discountedPrice']for s in r['sizes']}
   if r['currencyIsoCode4217']!='CNY'or len(vals)!=1:raise ValueError('Seller price ambiguous')
   prices.append(dict(nm_id=int(nm),article=r['vendorCode'],currency='CNY',seller_price=next(iter(vals))))
  stock=read_stock(sorted({r['article']for r in orders.values()}));at=stamp()
  common=dict(prices=dict(rows=prices,observed_at=at),stock=stock,fx=dict(rub_per_cny=12.0873,effective_date='2026-10-31',source='Common fixed CBR31Oct',observed_at=at),own_products=own)
  policy=c.get('china_agent:new_ad_economics_policy:v1')or{};delivery=c.get('china_agent:expected_profit_delivery_model:v1')or{};results={};sources={}
  for label,day,o,ads,key in slices:
   if o['status']!='complete'or len(o['rows'])!=o['totals']['count']:raise ValueError('Orders incomplete')
   cutoff=f'{day}T22:00:00+03:00'
   if datetime.fromisoformat(o['end_msk'])!=datetime.fromisoformat(cutoff):raise ValueError('Order cutoff differs')
   wanted={r['id']for r in o['rows']};parts=copy.deepcopy(common)
   # Common frozen history for comparability; deliberately not a shifting per-date cohort.
   parts['own_products']['comparison_history_period']=dict(first=own['period_from'],last=own['period_to'])
   parts['own_products'].pop('period_from',None);parts['own_products'].pop('period_to',None)
   parts['orders']=dict(rows=[{k:r[k]for k in ['id','nmId','article','createdAt']}for r in o['rows']],complete=True,cutoff_msk=cutoff,observed_at=o['observed_at'])
   parts['statuses']=dict(rows=[r for r in statuses if r['id']in wanted],complete=True,observed_at=at)
   parts['advertising']=dict(rows=ads['stats'],catalogue=ads['requested_ids'],all_statuses_included=True,observed_at=ads['observed_at'])
   state=dict(cabinet='token_3',inputs=parts,errors={});c.put(ROOT+':inputs:'+label,json.loads(json.dumps(state)))
   r=calculate(state,policy,delivery,day);rev=0.;missing=0;oi={p['nm_id']:p for p in own['rows']}
   for row in r['details']:
    p=oi.get(row['nm_id'],{});f=p.get('finished_orders');v=p.get('backwardlogisticsum')
    if f and isinstance(v,(int,float)):rev+=v/f/12.0873
    else:missing+=1
   r['totals']['model_reverse_logistics_cny']=rev
   if r['totals']['forecast_profit_cny']is not None:r['totals']['forecast_profit_cny']-=rev;r['totals']['forecast_profit_rub']=r['totals']['forecast_profit_cny']*12.0873
   r.update(common_history='2026-10-03–2026-11-01',unknown_general_costs=True,missing_reverse_model_orders=missing)
   results[label]=r;sources[label]=key
  result=dict(status='preliminary_comparable'if all(x['status']=='preliminary_model'for x in results.values())else'incomplete',observed_at=stamp(),cutoff_hour_msk=22,sources=sources,results=results,comparison='Forecast only for created FBS orders00-22MSK2Nov; statuses and sellerprices collected now, sellerprices are proxy for order-timeprice; frozen own3Oct-1Nov buyout, FX12.0873dated31Oct. All cachedads22:07 inclclosedCPM. Other unconfirmed published/general charges excluded, not assumed absent.',wb_writes=0,telegram_calls=0,grants_action_permission=False)
  result=json.loads(json.dumps(result));c.put(ROOT+':result',result)
  if c.get(ROOT+':result')!=result:raise ValueError('Result readback mismatch')
  print(json.dumps(dict(status=result['status'],orders={k:v['totals']['orders']for k,v in results.items()})))
 except Exception as ex:c.put(ROOT+':error',dict(error=type(ex).__name__,message=str(ex)if isinstance(ex,(ValueError,PermissionError))else None,observed_at=stamp()));raise
 finally:
  requests.sessions.Session.request=original;context.__exit__(None,None,None)
if __name__=='__main__':main()

