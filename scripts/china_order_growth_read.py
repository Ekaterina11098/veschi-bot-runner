import os,sys,json,time,requests
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
sys.path.insert(0,'scripts')
from china_price_apply import IO
from china_loss_ads import current
io=IO();now=datetime.now(timezone.utc);msk=ZoneInfo('Europe/Moscow');local=now.astimezone(msk);start=datetime(2026,10,21,tzinfo=msk)
out=dict(observed_at=now.isoformat(),cutoff_msk=local.isoformat(),cabinet='token_3',wb_writes=0,telegram_calls=0)
def api(host,path,method='GET',params=None,body=None):
 r=requests.request(method,'https://'+host+path,headers={'Authorization':io.token},params=params,json=body,timeout=45)
 if not r.ok:raise RuntimeError(host+' HTTP '+str(r.status_code))
 return r.json() if r.content else {}
rows=[];cursor=0
for page in range(12):
 j=api('marketplace-api.wildberries.ru','/api/v3/orders',params=dict(limit=1000,next=cursor,dateFrom=int(start.timestamp()),dateTo=int(now.timestamp())))
 added=j.get('orders',[]);rows.extend(added);nxt=j.get('next')
 if not added or not nxt or nxt==cursor:out['orders_complete']=True;break
 cursor=nxt;time.sleep(1)
else:out['orders_complete']=False
out['orders']=rows;out['campaigns']={str(k):v for k,v in current(io).items()}
out['prices']=io.wb('/api/v2/list/goods/filter?limit=1000&offset=0').get('listGoods',[])
warehouses=api('marketplace-api.wildberries.ru','/api/v3/warehouses');out['warehouses']=warehouses
saved=io.get('china_agent:loss_preview_source:2026-10-23:v1');products=saved['observations'][0]['data']['data']['data'];skus=sorted({str(p['barcode']) for p in products if p.get('barcode')})
out['stocks']={}
for wh in warehouses:
 if wh['id']!=2126188:continue
 out['stocks'][str(wh['id'])]=api('marketplace-api.wildberries.ru','/api/v3/stocks/'+str(wh['id']),'POST',body={'skus':skus})
# Exact read-only ad aggregates today and two preceding complete Moscow dates.
ids=sorted(map(int,out['campaigns']));out['ads']=[]
for day in ['2026-10-21','2026-10-22','2026-10-23']:
 for a in range(0,len(ids),50):
  data=api('advert-api.wildberries.ru','/adv/v3/fullstats',params={'ids':','.join(map(str,ids[a:a+50])),'beginDate':day,'endDate':day})
  out['ads'].append(dict(day=day,data=data));time.sleep(21)
io.create('china_agent:order_growth_read:2026-10-23:v1',out)
print(json.dumps(dict(orders=len(rows),orders_complete=out.get('orders_complete'),campaigns=len(out['campaigns']),prices=len(out['prices']),ads=len(out['ads']),wb_writes=0,telegram_calls=0)))
