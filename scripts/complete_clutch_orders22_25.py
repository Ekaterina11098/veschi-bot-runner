"""Complete only the saved FBS pagination for the same approved slot."""
import json,requests,time
from datetime import datetime,timezone
from china_loss_execute import IO
io=IO();key='china_agent:campaign_monitor:41155909:2026-10-25T22:v1'
p=io.get(key);assert p and p['orders']['http']==200
if p.get('orders_complete'):print('already_complete');raise SystemExit
body=p['orders']['data'];rows=body['orders'];cursor=body.get('next');pages=1;until=int(datetime.fromisoformat(p['completed_at']).timestamp())
while cursor and pages<4:
 time.sleep(2)
 r=requests.get('https://marketplace-api.wildberries.ru/api/v3/orders',params=dict(limit=1000,next=cursor,dateFrom=1792875600,dateTo=until),headers={'Authorization':io.token},timeout=50)
 if r.status_code!=200:p['orders_completion_http']=r.status_code;break
 b=r.json();pages+=1;part=b.get('orders',[]);rows+=part
 if not part or not b.get('next'):p['orders_complete']=True;break
 if b['next']==cursor:break
 cursor=b['next']
p['orders']['data']['orders']=rows;p['orders_pages']=pages;p['orders_pagination_checked_at']=datetime.now(timezone.utc).isoformat()
io.put(key,p)
print(json.dumps(dict(saved=True,complete=p.get('orders_complete',False),wb_writes=0,telegram_sends=0)))
