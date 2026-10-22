import sys,json,requests
from datetime import datetime,timedelta,timezone
sys.path.insert(0,'scripts')
from china_price_apply import IO,now,day
io=IO();key='china_agent:six_loss_diagnosis:2026-10-22:v1'
if day()!='2026-10-22':raise RuntimeError('Expired diagnostic')
if io.get(key):print('Existing diagnostic preserved');raise SystemExit()
nms={1473243909,1473243915,1560345288,1473243912,1473243918,1535337772}
start=datetime(2026,9,22,tzinfo=timezone(timedelta(hours=3)));end=datetime(2026,10,22,tzinfo=timezone(timedelta(hours=3)))-timedelta(seconds=1)
out=dict(status='reading',cabinet='token_3',period_from='2026-09-22',period_to='2026-10-21',observed_at=now().isoformat(),wb_writes=0,telegram_calls=0,pages=[],orders=[])
if not io.create(key,out):raise RuntimeError('Concurrent read')
cursor=0;seen=set()
for page in range(6):
 r=requests.get('https://marketplace-api.wildberries.ru/api/v3/orders',headers={'Authorization':io.token},params={'limit':1000,'next':cursor,'dateFrom':int(start.timestamp()),'dateTo':int(end.timestamp())},timeout=(15,60),allow_redirects=False)
 if r.status_code!=200:out.update(status='unavailable',http_status=r.status_code);io.put(key,out);raise RuntimeError('Order read failed')
 raw=r.json();rows=raw.get('orders',[]);out['pages'].append(dict(rows=len(rows),next=raw.get('next')))
 for o in rows:
  if o['id'] in seen:raise RuntimeError('Order pagination duplicate')
  seen.add(o['id'])
  if o.get('nmId') in nms:out['orders'].append({k:v for k,v in o.items() if k in ('id','nmId','article','createdAt','rid','orderUid','warehouseId','isCancel','cancelDate','deliveryType')})
 if len(rows)<1000:out['orders_complete']=True;break
 nxt=raw.get('next')
 if nxt is None or nxt==cursor:raise RuntimeError('Order cursor stalled')
 cursor=nxt
if not out.get('orders_complete'):raise RuntimeError('Order coverage bounded')
ids=[o['id'] for o in out['orders']]
r=requests.post('https://marketplace-api.wildberries.ru/api/v3/orders/status',headers={'Authorization':io.token},json={'orders':ids},timeout=(15,60),allow_redirects=False)
out['statuses']=dict(http_status=r.status_code,data=r.json() if r.status_code==200 else None)
out['prices']=io.prices([str(n) for n in nms]);out['all_order_count']=len(seen)
# Status history is a read-only endpoint. Store only exact six product order timelines.
r=requests.post('https://marketplace-api.wildberries.ru/api/v3/orders/status/history',headers={'Authorization':io.token},json={'orders':ids},timeout=(15,60),allow_redirects=False)
out['status_history']=dict(http_status=r.status_code,data=r.json() if r.status_code==200 else None)
out.update(status='complete',completed_at=now().isoformat());io.put(key,out)
print(json.dumps(dict(status='complete',total_orders=len(seen),selected_orders=len(ids),statuses_http=out['statuses']['http_status'],history_http=r.status_code,wb_writes=0)))
