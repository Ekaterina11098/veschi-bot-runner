"""Read-only two-day order and all-campaign expense comparison."""
import json,time,requests
from datetime import datetime,timezone,timedelta
from china_loss_execute import IO
io=IO();MSK=timezone(timedelta(hours=3));cutoff=datetime.now(timezone.utc)
def read(host,path,params=None):
 time.sleep(1.2);r=requests.get('https://'+host+path,headers={'Authorization':io.token},params=params,timeout=60);r.raise_for_status();return r.json()
orders={};cursor=0
for _ in range(30):
 j=read('marketplace-api.wildberries.ru','/api/v3/orders',dict(limit=1000,next=cursor,dateFrom=int(datetime(2026,10,24,tzinfo=MSK).timestamp()),dateTo=int(cutoff.timestamp())))
 part=j.get('orders',[])
 for r in part:orders[r['id']]={k:r.get(k) for k in ['id','nmId','article','createdAt','price','salePrice','convertedPrice','currencyCode','convertedCurrencyCode']}
 nxt=j.get('next')
 if not part or not nxt:break
 assert nxt!=cursor;cursor=nxt
else:raise RuntimeError('Incomplete pagination')
count=read('advert-api.wildberries.ru','/adv/v1/promotion/count')
ids=sorted({x['advertId'] for g in count.get('adverts',[]) for x in g.get('advert_list',[])})
batches=[]
for i in range(0,len(ids),50):
 batch=ids[i:i+50]
 batches.append(dict(ids=batch,data=read('advert-api.wildberries.ru','/adv/v3/fullstats',dict(ids=','.join(map(str,batch)),beginDate='2026-10-24',endDate='2026-10-25'))))
out=dict(observed_at=datetime.now(timezone.utc).isoformat(),orders_cutoff=cutoff.isoformat(),orders=list(orders.values()),campaign_ids=ids,ad_batches=batches,wb_writes=0,telegram_sends=0)
key='china_agent:owner_profit_compare:2026-10-24:2026-10-25:v1'
if io.get(key):io.put(key,out)
else:assert io.create(key,out)
print(json.dumps(dict(status='private_snapshot_saved',order_count=len(orders),campaign_count=len(ids),wb_writes=0)))
