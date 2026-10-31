"""Owner requested read-only current China sales and advertising. No browser, sends or WB writes."""
import os,json,requests,time
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
ROOT='china_agent:same_hour_sales:2026-10-31:api:v1'
MSK=ZoneInfo('Europe/Moscow')
def run():
 c=Cache();w=WB()
 if c.get(ROOT):print('Existing frozen read');return
 validate_identity(c,w);now=datetime.now(timezone.utc);cut=now.astimezone(MSK).replace(minute=0,second=0,microsecond=0)
 first=datetime(2026,10,30,tzinfo=MSK);catalog=c.get('china_agent:prices:v1')or{}
 if catalog.get('cabinet')!='token_3':raise ValueError('China catalogue identity unavailable')
 allowed={int(g['nmID'])for g in catalog.get('rows',[])}
 e=dict(status='reading',observed_at=stamp(),cutoff_msk=cut.isoformat(),cabinet='token_3',wb_writes=0,telegram_calls=0)
 if not c.create(ROOT,e):raise ValueError('Race')
 def save():c.put(ROOT,e)
 def get(path,params=None):
  r=requests.get('https://marketplace-api.wildberries.ru'+path,headers={'Authorization':w.token},params=params,timeout=50)
  if not r.ok:raise ValueError('FBS read HTTP '+str(r.status_code))
  return r.json()
 try:
  rows={};cursor=0;pages=0
  while True:
   j=get('/api/v3/orders',dict(limit=1000,next=cursor,dateFrom=int(first.timestamp()),dateTo=int(cut.timestamp())));part=j.get('orders',[]);pages+=1
   for r in part:rows[r['id']]=r
   nxt=j.get('next')
   if not part or not nxt:break
   if nxt==cursor or pages>=12:raise ValueError('Orders pagination incomplete')
   cursor=nxt;time.sleep(.4)
  newer=get('/api/v3/orders/new').get('orders',[])
  for r in newer:rows[r['id']]=r
  selected=[];unknown=[]
  for r in rows.values():
   at=datetime.fromisoformat(r['createdAt'].replace('Z','+00:00')).astimezone(MSK)
   if at.date()not in[first.date(),cut.date()]or at.time()>=cut.timetz().replace(tzinfo=None):continue
   if int(r['nmId'])not in allowed:unknown.append(r['nmId']);continue
   fields=['id','nmId','article','createdAt','price','finalPrice','convertedPrice','convertedFinalPrice','currencyCode','convertedCurrencyCode','isZeroOrder']
   selected.append({k:r.get(k)for k in fields})
  if unknown:raise ValueError('Foreign or missing catalogue nmIDs: '+str(len(set(unknown))))
  e.update(orders=dict(status='complete',rows=selected,pages=pages,new_rows=len(newer),currency_codes=sorted({str(r.get('currencyCode'))for r in selected}),converted_currency_codes=sorted({str(r.get('convertedCurrencyCode'))for r in selected}),basis='FBS created assembly units, historical + new, dedup byid; statuses all; not buyouts; cancellation not inferred',observed_at=stamp()));save()
 except Exception as ex:e['orders']=dict(status='unavailable',reason=str(ex)if isinstance(ex,ValueError)else type(ex).__name__);save()
 try:
  inv=w.req('/adv/v1/promotion/count');ids=sorted({a['advertId']for g in inv.get('adverts',[])if g['status']in[4,7,9,11]for a in g.get('advert_list',[])})
  if len(ids)>50:raise ValueError('Campaign pagination required')
  raw=w.req('/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate=2026-10-31&endDate=2026-10-31')
  e['advertising']=dict(status='complete'if {r['advertId']for r in raw}==set(ids)else'partial',observed_at=stamp(),campaign_ids_requested=ids,stats=raw,currency='CNY',time_basis='cumulative current API snapshot; not retrospectively hour-filterable')
 except Exception as ex:e['advertising']=dict(status='unavailable',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__)
 e.update(status='complete'if e['orders']['status']=='complete'and e['advertising']['status']=='complete'else'partial',completed_at=stamp());save()
 print(json.dumps({'status':e['status'],'orders_status':e['orders']['status'],'ad_status':e['advertising']['status'],'wb_writes':0}))
if __name__=='__main__':run()
