"""Owner requested completed-day China sales diagnosis; immutable private output only."""
import os,json,requests
from datetime import datetime,timedelta
from china_hourly_sales_read import Cache,ReadOnlyWB,validate_identity,read_orders,select_rows,aggregate,comparison,stamp,MSK
ROOT='china_agent:owner_sales_completed:2026-11-01:review20261102:v1'
def main():
 c=Cache()
 if c.get(ROOT):print('Existing immutable analysis inputs; no repeated reads');return
 w=ReadOnlyWB();validate_identity(c,w)
 def get(path,params=None):
  if path not in ('/api/v3/orders','/api/v3/orders/new'):raise RuntimeError('Read-only FBS guard')
  r=requests.get('https://marketplace-api.wildberries.ru'+path,params=params,headers={'Authorization':w.token},timeout=50)
  if not r.ok:raise RuntimeError('FBS HTTP '+str(r.status_code))
  return r.json()
 new=get('/api/v3/orders/new').get('orders')
 if not isinstance(new,list):raise RuntimeError('New orders response missing')
 catalog=c.get('china_agent:prices:v1')
 if not catalog or catalog.get('cabinet')!='token_3':raise RuntimeError('Cabinet catalogue unavailable')
 allowed={r['nmID'] for r in catalog['rows']}
 result=dict(status='complete',cabinet='token_3',observed_at=stamp(),orders={},wb_writes=0,telegram_calls=0,grants_action_permission=False,basis='FBS created tasks all statuses; convertedPrice buyer-discounted CNY, not seller revenue, buyouts or proven entire cabinet')
 for ds in ('2026-10-31','2026-11-01','2026-10-25'):
  start=datetime.fromisoformat(ds).replace(tzinfo=MSK);end=start+timedelta(days=1)
  raw=read_orders(get,start,end);raw.update({r['id']:r for r in new})
  rows=select_rows(raw.values(),start,end);total=aggregate(rows)
  unknown=sorted({r['nmId'] for r in rows if r['nmId'] not in allowed})
  status='complete' if not unknown and not total['unknown_amount_ids'] else 'partial'
  result['orders'][ds]=dict(status=status,start_msk=start.isoformat(),end_msk=end.isoformat(),observed_at=stamp(),totals=total,rows=rows,unknown_catalogue_nm_ids=unknown)
  if status!='complete':result['status']='partial'
 result['comparisons']={ds:comparison(result['orders']['2026-11-01']['totals'],result['orders'][ds]['totals']) for ds in ('2026-10-31','2026-10-25')}
 if not c.create(ROOT,result):raise RuntimeError('Concurrent immutable inputs')
 if c.get(ROOT)!=result:raise RuntimeError('Private input readback mismatch')
 print(json.dumps(dict(status=result['status'],comparisons=result['comparisons'],wb_writes=0)))


def diagnose():
 from china_advertising_state import AdvertisingIO
 from china_analytic_dialog import Analyst,reading
 from china_advertising_v2 import http,history,read_price_experience
 from china_advertising_economic_review import model_rows
 from datetime import date,timezone
 class IO(AdvertisingIO):
  def wb(self,*a,**k):raise RuntimeError('No WB mutations')
 io=IO()
 key=ROOT+':today-diagnosis'
 if io.get(key):return
 source=io.get('china_agent:advertising_source:2026-11-02:v2')
 ids=[1473245510,1473245492,1473243915,1473245512,1473244354,1535337776,1473245494,1473245505]
 class Work:
  now=datetime.now(timezone.utc)
  def get(self,k):return io.get(k)
  def save(self,k,v,**kw):
   if io.get(k) is None:io.create(k,v)
   else:io.put(k,v)
  def catalog(self):return [(str(r['nmID']),r['vendorCode']) for r in source['catalogue']['rows']]
 an=Analyst(Work(),dict(request_text='Адресная проверка просадок заказов за завершённый1Nov'),[])
 with reading():
  prices=an.collect('prices',ids,date(2026,10,3),date(2026,11,1))
  stock=an.collect('stock',ids,date(2026,10,3),date(2026,11,1))
 for v in (prices,stock):v['observed_at']=datetime.now(timezone.utc).isoformat()
 campaigns=http(io,'/api/advert/v2/adverts?ids='+','.join(map(str,source['ids'])))['adverts']
 cids=[c['id'] for c in campaigns if c['status']==9 and any(n['nm_id'] in ids for n in c['nm_settings'])]
 budgets=http(io,'/api/advert/v2/budget','POST',dict(advertIds=cids)) if cids else {}
 products=io.get('china_agent:analytic_read:v1:893557e46ce1918d55ff958ce88fd1f202ee06e10e60792aeabbbb67cd857b35')
 economics=model_rows(dict(products=products,prices=prices,stock=stock,fx=io.get('china_agent:cbr_cny:v1:2026-11-01')),io.get('china_agent:new_ad_economics_policy:v1')or{},io.get('china_agent:expected_profit_delivery_model:v1')or{})
 events=[e for e in history(source['executions']) if e.get('nm') in ids]
 result=dict(status='complete',observed_at=stamp(),prices=prices,stock=stock,economics=economics,events=events,campaigns=[dict(c,nm_settings=[n for n in c['nm_settings'] if n['nm_id'] in ids])for c in campaigns if any(n['nm_id'] in ids for n in c['nm_settings'])],budgets=budgets,wb_writes=0,telegram_calls=0,grants_action_permission=False)
 if not io.create(key,result):raise RuntimeError('Concurrent immutable diagnosis')
 if io.get(key)!=result:raise RuntimeError('Diagnosis readback mismatch')
 print(json.dumps(dict(status='diagnosiscomplete',wb_writes=0)))
if __name__=='__main__':
 main()
 diagnose()
