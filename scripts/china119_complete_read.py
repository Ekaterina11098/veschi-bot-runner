import requests,os,json,time
from datetime import datetime,timezone
from advertising_agent.notify import cache_get,cache_set
KEY='china_agent:119_two_day:2026-10-23:v1'
p=cache_get(KEY);assert p and p.get('completed_at')
out=dict(observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_calls=0)
token=os.environ['WB_TOKEN_3'];orders=p['reads']['orders']['data']['orders'];cursor=p['reads']['orders']['data']['next'];allcount=p['orders_page_count']
for page in range(4):
 r=requests.get('https://marketplace-api.wildberries.ru/api/v3/orders',params={'limit':1000,'next':cursor,'dateFrom':int(datetime(2026,10,18,21,tzinfo=timezone.utc).timestamp()),'dateTo':int(time.time())},headers={'Authorization':token},timeout=45)
 if not r.ok:out['orders_error_http']=r.status_code;break
 d=r.json();rows=d.get('orders',[]);allcount+=len(rows);orders.extend(o for o in rows if o.get('nmId')==1473243898);cursor=d.get('next')
 if len(rows)<1000:out['orders_pagination_complete']=True;break
 time.sleep(2)
out['orders']=list({o['id']:o for o in orders}.values());out['all_orders_read_count']=allcount
r=requests.post('https://marketplace-api.wildberries.ru/api/v3/orders/status',json={'orders':[o['id'] for o in out['orders']]},headers={'Authorization':token},timeout=45)
out['statuses']={'http':r.status_code,'data':r.json() if r.ok else None}
rows=[];cursor=0
for page in range(3):
 r=requests.post('https://finance-api.wildberries.cn/api/finance/v1/sales-reports/detailed',json={'dateFrom':'2026-10-19','dateTo':'2026-10-22T23:59:59','limit':100000,'rrdId':cursor,'period':'daily'},headers={'Authorization':os.environ['WB_FINANCE_TOKEN_3']},timeout=50)
 if r.status_code==204:out['finance_complete']=True;break
 if not r.ok:out['finance_error_http']=r.status_code;break
 d=r.json();part=d if isinstance(d,list) else d.get('data',d.get('rows',[]))
 if not part:out['finance_complete']=True;break
 rows.extend(part);cursor=part[-1]['rrdId']
 cache_set(KEY+':completion',dict(out,finance_rows_119=[x for x in rows if x.get('nmId')==1473243898],finance_rows_total=len(rows)),365)
 time.sleep(61)
out.update(finance_rows_119=[x for x in rows if x.get('nmId')==1473243898],finance_rows_total=len(rows),finance_shared_rows=[x for x in rows if not x.get('nmId')],completed_at=datetime.now(timezone.utc).isoformat())
cache_set(KEY+':completion',out,365);print(json.dumps({k:out.get(k) for k in ['orders_pagination_complete','all_orders_read_count','finance_complete','finance_error_http','finance_rows_total','completed_at']}))
