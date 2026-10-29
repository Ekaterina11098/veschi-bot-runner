"""Owner29Oct: orders only for verified +30% cohort. No WB writes or messages."""
import os,time,requests
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from china_cloud_cost_control import Cache,WB,stamp,validate_identity
DAY='2026-10-29'
ROOT='china_agent:zero30_order_review:'+DAY+':v1'
EXEC='china_agent:price_execution:v1:-1004342917488:155:307200273:e6c13e1e7186bedd902c081a1b11745e6e61099bfa6e2754dce69ef53929cbf7'
MSK=timezone(timedelta(hours=3))
def main():
 assert os.environ.get('GITHUB_REPOSITORY')=='Ekaterina11098/veschi-bot-runner' and os.environ.get('GITHUB_REF')=='refs/heads/main'
 assert datetime.now(MSK).date().isoformat()==DAY
 c=Cache();w=WB();validate_identity(c,w)
 if c.get(ROOT):print('Private review exists; no repeated requests');return
 e=c.get(EXEC)
 if not e or e.get('status')!='done' or len(e.get('items',[]))!=70:raise ValueError('Verified cohort unavailable')
 cohort={}
 for item in e['items']:
  s=item['selection'];rb=item.get('readback') or {};nm=int(s['nm_id'])
  if item['status']!='applied' or rb.get('nmID')!=nm or rb.get('currencyIsoCode4217')!='CNY' or not any(abs(Decimal(str(x['discountedPrice']))-Decimal(s['target_cny']))<Decimal('.011') for x in rb.get('sizes',[])):raise ValueError('Price readback mismatch')
  cohort[nm]=dict(article=s['article'],before_cny=s['current_cny'],after_cny=s['target_cny'])
 if len(cohort)!=70:raise ValueError('Cohort duplicated')
 start=datetime.fromisoformat(e['completed_at'].replace('Z','+00:00'));cutoff=datetime.now(timezone.utc)
 state=dict(status='collecting',observed_at=stamp(),cutoff_msk=cutoff.astimezone(MSK).isoformat(),cohort=cohort,cohort_count=70,price_verified_at=start.isoformat(),execution_key=EXEC,wb_writes=0,telegram_sends=0,scope='orders_only')
 if not c.create(ROOT,state):raise RuntimeError('Concurrent review')
 def get(url,params):
  r=requests.get(url,params=params,headers={'Authorization':w.token},timeout=80)
  if not r.ok:raise RuntimeError('WB read HTTP '+str(r.status_code))
  return r.json()
 try:
  # Created FBS orders, including records not yet published in operational statistics.
  rows=[];nxt=0;seen=set();raw_count=0
  for _ in range(25):
   j=get('https://marketplace-api.wildberries.ru/api/v3/orders',dict(limit=1000,next=nxt,dateFrom=int(start.timestamp()),dateTo=int(cutoff.timestamp())))
   part=j.get('orders')
   if not isinstance(part,list):raise ValueError('FBS order shape unknown')
   raw_count+=len(part)
   for row in part:
    if row.get('nmId') in cohort:
     rows.append({k:row[k] for k in ['id','nmId','article','createdAt','rid','srid','orderUid','price','convertedPrice','currencyCode','convertedCurrencyCode'] if k in row})
   if not part:break
   new=j.get('next')
   if not isinstance(new,int) or new in seen or new==nxt:raise ValueError('FBS pagination incomplete')
   seen.add(nxt);nxt=new;time.sleep(1)
  else:raise ValueError('FBS pagination bound exceeded')
  c.put(ROOT+':fbs',dict(observed_at=stamp(),complete=True,raw_count=raw_count,rows=rows))
  fields=['date','lastChangeDate','supplierArticle','nmId','srid','isCancel','cancelDate','totalPrice','discountPercent','spp','finishedPrice','priceWithDisc','currency','currencyName','currencyCode','orderType']
  last=0
  for day in ['2026-10-28',DAY]:
   if last:time.sleep(max(0,61-(time.monotonic()-last)))
   raw=get('https://statistics-api.wildberries.ru/api/v1/supplier/orders',dict(dateFrom=day,flag=1));last=time.monotonic()
   if not isinstance(raw,list) or len(raw)>=80000:raise ValueError('Statistics order coverage unknown')
   selected=[]
   for row in raw:
    if row.get('nmId') not in cohort:continue
    at=datetime.fromisoformat(row['date'].replace('Z','+00:00'))
    if not at.tzinfo:at=at.replace(tzinfo=MSK)
    if at.astimezone(MSK).date().isoformat()!=day:raise ValueError('Order day mismatch')
    if at>=start and at<=cutoff:selected.append({k:row[k] for k in fields if k in row})
   c.put(ROOT+':orders:'+day,dict(observed_at=stamp(),complete=True,raw_count=len(raw),rows=selected,selection='exact order date flag1; after complete verified price change and before fixed cutoff'))
  state.update(status='complete',completed_at=stamp());c.put(ROOT,state)
  print('Private cohort orders saved; no WB writes or Telegram messages')
 except Exception as ex:
  state.update(status='blocked',error=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__,completed_at=stamp());c.put(ROOT,state)
  raise RuntimeError('Orders review incomplete; inspect private state') from None
def statuses():
 assert os.environ.get('GITHUB_REPOSITORY')=='Ekaterina11098/veschi-bot-runner' and os.environ.get('GITHUB_REF')=='refs/heads/main' and datetime.now(MSK).date().isoformat()==DAY
 c=Cache();w=WB();validate_identity(c,w)
 key=ROOT+':statuses'
 if c.get(key):print('Existing status read; no repeated request');return
 f=c.get(ROOT+':fbs');root=c.get(ROOT)
 if not f or not f.get('complete') or not root or root.get('status')!='complete':raise ValueError('Completed orders review required')
 ids=sorted({o['id'] for o in f['rows']})
 if len(ids)>1000:raise ValueError('Narrow status scope exceeded')
 result=[]
 if ids:
  # POST is the documented read-only batch status method, not a marketplace change.
  r=requests.post('https://marketplace-api.wildberries.ru/api/v3/orders/status',json={'orders':ids},headers={'Authorization':w.token},timeout=60)
  if not r.ok:raise RuntimeError('WB status read HTTP '+str(r.status_code))
  result=r.json().get('orders')
  if not isinstance(result,list) or {x.get('id') for x in result}!=set(ids):raise ValueError('Order status coverage incomplete')
 c.put(key,dict(observed_at=stamp(),complete=True,rows=result,wb_writes=0,scope='read_only_status_for_cohort_orders'))
 print('Cohort order statuses read; no WB writes')
if __name__=='__main__':
 import sys
 statuses() if sys.argv[1:]==['--statuses'] else main()
