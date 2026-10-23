import json,time,requests
from datetime import datetime,timezone
from china_price_apply import IO
io=IO();KEY='china_agent:orders_drop:2026-10-23:checks:v1'
if io.get(KEY):print('Existing read preserved');raise SystemExit(0)
out=dict(cabinet='token_3',observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_calls=0)
def read(k,url,body):
 time.sleep(3)
 try:
  r=requests.post(url,json=body,headers={'Authorization':io.token},timeout=50);out[k]={'http':r.status_code,'data':r.json() if r.ok else None}
 except Exception as e:out[k]={'error':type(e).__name__}
 if not io.get(KEY):io.create(KEY,out)
 else:io.put(KEY,out)
read('stocks','https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',{'skus':['2048515352137','2045291540062','2045291539967','2051011189411','2044257763354','2051011191711']})
read('min_bags1','https://advert-api.wildberries.ru/api/advert/v1/bids/min',{'advert_id':40933588,'nm_ids':[1473243911,1473243239,1473244354],'payment_type':'cpc','placement_types':['recommendation']})
read('min_bags2','https://advert-api.wildberries.ru/api/advert/v1/bids/min',{'advert_id':41055480,'nm_ids':[1473244342,1473243090],'payment_type':'cpc','placement_types':['recommendation']})
w=io.get('china_agent:orders_drop:2026-10-23:wb:v1')
ids=[o['id'] for o in w['orders'] if '2026-10-20T21:00:00'<=o['createdAt']<'2026-10-22T21:00:00']
read('statuses','https://marketplace-api.wildberries.ru/api/v3/orders/status',{'orders':ids})
out['completed_at']=datetime.now(timezone.utc).isoformat();io.put(KEY,out)
print(json.dumps({k:v.get('http') for k,v in out.items() if isinstance(v,dict)}))
