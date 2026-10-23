import json,time,requests
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from china_price_apply import IO
io=IO();KEY='china_agent:orders_drop:2026-10-23:today:v1'
if io.get(KEY):print('Existing read preserved');raise SystemExit(0)
now=datetime.now(timezone.utc);start=int(datetime(2026,10,23,tzinfo=ZoneInfo('Europe/Moscow')).timestamp());orders=[];cursor=0
out=dict(cabinet='token_3',observed_at=now.isoformat(),cutoff_msk=now.astimezone(ZoneInfo('Europe/Moscow')).isoformat(),wb_writes=0,telegram_calls=0)
for page in range(4):
 r=requests.get('https://marketplace-api.wildberries.ru/api/v3/orders',params={'limit':1000,'next':cursor,'dateFrom':start,'dateTo':int(now.timestamp())},headers={'Authorization':io.token},timeout=50)
 if not r.ok:out['orders_error_http']=r.status_code;break
 d=r.json();part=d.get('orders',[]);orders.extend(part);cursor=d.get('next')
 if len(part)<1000:out['orders_complete']=True;break
 time.sleep(2)
out['orders']=orders
prior=io.get('china_agent:orders_drop:2026-10-23:wb:v1');ids=prior.get('ad_campaign_ids',[])
if ids:
 r=requests.get('https://advert-api.wildberries.ru/adv/v3/fullstats',params={'ids':','.join(map(str,ids)),'beginDate':'2026-10-21','endDate':'2026-10-23'},headers={'Authorization':io.token},timeout=50)
 out['ads']={'http':r.status_code,'data':r.json() if r.ok else None}
io.create(KEY,out)
print(json.dumps(dict(saved=True,orders=len(orders),complete=out.get('orders_complete'),ads_http=out.get('ads',{}).get('http'),wb_writes=0,telegram_calls=0)))
