import os,json,time,requests
from datetime import datetime,timezone
from advertising_agent.notify import cache_get,cache_set
from analytics.mpstats_probe import discover
from analytics.mpstats_gaps import execute_reads
KEY='china_agent:119_two_day:2026-10-23:v1'
out=dict(observed_at=datetime.now(timezone.utc).isoformat(),cabinet='token_3',wb_writes=0,telegram_calls=0,reads={},mpstats=[])
token=os.environ['WB_TOKEN_3']
def persist():cache_set(KEY,json.loads(json.dumps(out)),365)
def read(key,base,path,params=None,body=None,finance=False):
 time.sleep(1.5)
 try:
  r=requests.request('POST' if body is not None else 'GET',base+path,params=params,json=body,headers={'Authorization':os.environ['WB_FINANCE_TOKEN_3'] if finance else token},timeout=55)
  out['reads'][key]=dict(http=r.status_code,data=r.json() if r.ok and r.content else None)
 except Exception as e:out['reads'][key]=dict(error=type(e).__name__)
 persist()
read('campaign','https://advert-api.wildberries.ru','/api/advert/v2/adverts',params={'ids':'41155909'})
read('budget','https://advert-api.wildberries.ru','/adv/v1/budget',params={'id':41155909})
read('ads','https://advert-api.wildberries.ru','/adv/v3/fullstats',params={'ids':'41155909','beginDate':'2026-10-19','endDate':'2026-10-23'})
start=int(datetime(2026,10,18,21,tzinfo=timezone.utc).timestamp())
read('orders','https://marketplace-api.wildberries.ru','/api/v3/orders',params={'limit':1000,'next':0,'dateFrom':start,'dateTo':int(time.time())})
d=out['reads'].get('orders',{}).get('data') or {}
orders=[o for o in d.get('orders',[]) if o.get('nmId')==1473243898]
out['orders_page_count']=len(d.get('orders',[]));out['orders_pagination_complete']=len(d.get('orders',[]))<1000
out['reads']['orders']['data']={'next':d.get('next'),'orders':orders};persist()
if orders:read('statuses','https://marketplace-api.wildberries.ru','/api/v3/orders/status',body={'orders':[o['id'] for o in orders]})
read('stock','https://marketplace-api.wildberries.ru','/api/v3/stocks/2126188',body={'skus':['2042184162004']})
read('price','https://discounts-prices-api.wildberries.ru','/api/v2/list/goods/filter',params={'limit':10,'offset':0,'filterNmID':1473243898})
read('finance','https://finance-api.wildberries.cn','/api/finance/v1/sales-reports/detailed',body={'dateFrom':'2026-09-23','dateTo':'2026-10-22T23:59:59','limit':100000,'rrdId':0,'period':'daily'},finance=True)
f=out['reads'].get('finance',{}).get('data')
if f:
 rows=f if isinstance(f,list) else f.get('data',f.get('rows',[]))
 out['finance_all_count']=len(rows)
 out['finance_latest_rrDate']=max([str(x.get('rrDate','')) for x in rows],default=None)
 out['finance_shared_rows']=[x for x in rows if not x.get('nmId')]
 out['reads']['finance']['data']=[x for x in rows if x.get('nmId')==1473243898];persist()
pending=[]
for label,a,b in [('before','2026-10-19','2026-10-20'),('after','2026-10-21','2026-10-22'),('sample','2026-09-23','2026-10-22')]:
 pending.append(dict(cabinet='token_3',tool='lk_wb_products',arguments=dict(date_from=a,date_to=b,start_row=0,end_row=1500),key=label,priority=95))
pending.append(dict(cabinet='token_3',tool='lk_wb_card_orders',arguments=dict(type='products',value='149503429',date_from='2026-10-19',date_to='2026-10-22',start_row=0,end_row=300),key='card_orders',priority=90))
pending.append(dict(cabinet='token_3',tool='lk_wb_card_table',arguments=dict(type='products',value='149503429',period_type='30days',self_redemption=False),key='card_table',priority=90))
pending.append(dict(cabinet='token_3',tool='lk_wb_taxes',arguments={},key='taxes',priority=80))
def save(cabinet,o):
 def slim(x):
  if isinstance(x,list):
   if any(isinstance(i,dict) and i.get('nm_id')==1473243898 for i in x):return [i for i in x if isinstance(i,dict) and i.get('nm_id')==1473243898]
   return [slim(i) for i in x]
  if isinstance(x,dict):return {k:slim(v) for k,v in x.items()}
  return x
 o['data']=slim(o.get('data'));out['mpstats'].append(o);persist()
try:
 def reader(call,checks,known):return execute_reads(call,checks,known,pending,{},save,max_requests=8)
 z=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=reader)
 out['mpstats_connection']={k:z.get(k) for k in ['status','connected','detail','retry_after']}
except Exception as e:out['mpstats_error']=type(e).__name__
out['completed_at']=datetime.now(timezone.utc).isoformat();persist()
print(json.dumps(dict(saved=True,mpstats_reads=len(out['mpstats']),wb_http={k:v.get('http') for k,v in out['reads'].items()},wb_writes=0,telegram_calls=0)))
