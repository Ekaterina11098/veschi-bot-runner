import os,json,time,requests
from datetime import datetime,timezone
from china_price_apply import IO
from analytics.mpstats_probe import sanitize
io=IO();KEY='china_agent:119_stock_drop:2026-10-21:v1'
if io.get(KEY):print('Existing diagnostic retained');raise SystemExit()
out=dict(observed_at=datetime.now(timezone.utc).isoformat(),nm_id=1473243898,article='119-NoelBag-darkblack',reads=[],wb_writes=0,telegram_calls=0)
base='https://marketplace-api.wildberries.cn'
def call(path,method='GET',params=None,body=None):
 time.sleep(.3)
 r=requests.request(method,base+path,params=params,json=body,headers={'Authorization':io.token},timeout=(10,60),allow_redirects=False)
 value=dict(path=path,method=method,status_code=r.status_code)
 if r.status_code==200:value['data']=sanitize(r.json())
 out['reads'].append(value)
 io.put(KEY,out)
 return value
io.create(KEY,out)
warehouses=call('/api/v3/warehouses')
warehouse_id=os.environ.get('WB_STOCK_WAREHOUSE_3','')
if warehouse_id:ids=[int(warehouse_id)]
else:ids=[x['id'] for x in warehouses.get('data',[]) if not x.get('isDeleting')]
out['warehouse_ids']=ids
for wid in ids:call('/api/v3/stocks/'+str(wid),'POST',body=dict(skus=['2042184162004']))
new=call('/api/v3/orders/new')
if isinstance(new.get('data'),dict):new['data']['orders']=[x for x in new['data'].get('orders',[]) if x.get('nmId')==1473243898]
now=datetime.now(timezone.utc)
start=int(datetime(2026,10,20,0,tzinfo=timezone.utc).timestamp());end=int(now.timestamp());cursor=0;matching=[];pages=0
while pages<5:
 item=call('/api/v3/orders',params=dict(limit=1000,next=cursor,dateFrom=start,dateTo=end))
 rows=item.get('data',{}).get('orders',[])
 matching += [x for x in rows if x.get('nmId')==1473243898]
 nxt=item.get('data',{}).get('next')
 item['data']=dict(orders=[x for x in rows if x.get('nmId')==1473243898],total_rows_received=len(rows),next=nxt)
 pages+=1
 if len(rows)<1000 or nxt in (None,0,cursor):break
 cursor=nxt
out['target_orders']=matching
order_ids=sorted({x['id'] for x in matching}|{x['id'] for x in new.get('data',{}).get('orders',[])})
if order_ids:call('/api/v3/orders/status','POST',body=dict(orders=order_ids))
out['status']='complete';out['completed_at']=datetime.now(timezone.utc).isoformat();io.put(KEY,out)
print(json.dumps(dict(status='complete',target_orders=len(matching),wb_writes=0,telegram_calls=0)))
