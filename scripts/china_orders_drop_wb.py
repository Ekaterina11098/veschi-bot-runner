import os,json,time,requests
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from china_price_apply import IO
io=IO();KEY='china_agent:orders_drop:2026-10-23:wb:v1'
if io.get(KEY):print('Existing audit preserved');raise SystemExit(0)
out=dict(cabinet='token_3',observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_calls=0,reads={})
def save():io.put(KEY,json.loads(json.dumps(out)))
io.create(KEY,out)
def get(key,url,params=None):
 time.sleep(2)
 try:
  r=requests.get(url,params=params,headers={'Authorization':io.token},timeout=50)
  out['reads'][key]=dict(http=r.status_code,data=r.json() if r.ok and r.content else None)
 except Exception as e:out['reads'][key]=dict(error=type(e).__name__)
 save();return out['reads'][key].get('data')
tz=ZoneInfo('Europe/Moscow');start=int(datetime(2026,10,15,tzinfo=tz).timestamp());end=int(datetime(2026,10,23,tzinfo=tz).timestamp())-1
orders=[];cursor=0
for n in range(8):
 d=get('order_page_'+str(n),'https://marketplace-api.wildberries.ru/api/v3/orders',{'limit':1000,'next':cursor,'dateFrom':start,'dateTo':end})
 if not d:break
 part=d.get('orders',[]);orders.extend(part);cursor=d.get('next');out['reads']['order_page_'+str(n)]={'count':len(part),'next':cursor}
 if len(part)<1000:out['orders_complete']=True;break
out['orders']=orders;save()
get('campaign_counts','https://advert-api.wildberries.ru/adv/v1/promotion/count')
counts=out['reads'].get('campaign_counts',{}).get('data') or {}
ids=sorted({x['advertId'] for g in counts.get('adverts',[]) if g.get('status') in [9,11] for x in g.get('advert_list',[])})
out['ad_campaign_ids']=ids;save()
if ids and len(ids)<=50:
 get('campaigns','https://advert-api.wildberries.ru/api/advert/v2/adverts',{'ids':','.join(map(str,ids))})
 get('ads','https://advert-api.wildberries.ru/adv/v3/fullstats',{'ids':','.join(map(str,ids)),'beginDate':'2026-10-15','endDate':'2026-10-22'})
get('prices','https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',{'limit':1000,'offset':0})
out['completed_at']=datetime.now(timezone.utc).isoformat();save()
print(json.dumps(dict(saved=True,orders=len(orders),orders_complete=out.get('orders_complete'),campaigns=len(ids),http={k:v.get('http') for k,v in out['reads'].items()},wb_writes=0,telegram_calls=0)))
