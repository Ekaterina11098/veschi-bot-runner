"""One owner-requested current-day snapshot. Read-only WB/MS, private output, no messages."""
import os,time,requests
from datetime import datetime,timezone,timedelta
from china_cloud_cost_control import Cache,WB,stamp,validate_identity
DAY='2026-10-28'
KEY='china_agent:profit_now:2026-10-28:2218:v1'
def main():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner' and os.environ['GITHUB_REF']=='refs/heads/main'
 assert datetime.now(timezone(timedelta(hours=3))).date().isoformat()==DAY
 c=Cache();w=WB()
 if c.get(KEY):print('Existing private snapshot; no repeated collection');return
 validate_identity(c,w)
 state=dict(status='collecting',observed_at=stamp(),cutoff_msk=datetime.now(timezone(timedelta(hours=3))).isoformat(),wb_writes=0,telegram_sends=0)
 if not c.create(KEY,state):raise RuntimeError('Snapshot already claimed')
 try:
  r=requests.get('https://statistics-api.wildberries.ru/api/v1/supplier/orders',params=dict(dateFrom=DAY+'T00:00:00',flag=0),headers={'Authorization':os.environ['WB_TOKEN_3']},timeout=80)
  if not r.ok:raise RuntimeError('WB orders HTTP '+str(r.status_code))
  raw=r.json()
  if not isinstance(raw,list) or len(raw)>=80000:raise RuntimeError('Orders coverage incomplete')
  fields=['date','lastChangeDate','supplierArticle','nmId','srid','isCancel','cancelDate','totalPrice','discountPercent','spp','finishedPrice','priceWithDisc','currency','currencyName','currencyCode','orderType']
  selected=[{k:o[k] for k in fields if k in o} for o in raw if o.get('date','')[:10]==DAY]
  c.put(KEY+':orders',dict(observed_at=stamp(),rows=selected,raw_count=len(raw),selection='exact order date; lastChangeDate flag0',complete=True))
  inv=w.req('/adv/v1/promotion/count')
  statuses={str(x['advertId']):g.get('status') for g in inv.get('adverts',[]) for x in g.get('advert_list',[])}
  ids=sorted(map(int,statuses));stats=[]
  for start in range(0,len(ids),50):
   part=w.req('/adv/v3/fullstats?ids='+','.join(map(str,ids[start:start+50]))+'&beginDate='+DAY+'&endDate='+DAY)
   if not isinstance(part,list):raise RuntimeError('Advertising shape unknown')
   stats+=part
  if any(x.get('currency')!='CNY' for x in stats):raise RuntimeError('Advertising currency unconfirmed')
  c.put(KEY+':ads',dict(observed_at=stamp(),rows=stats,ids=ids,statuses=statuses,missing_ids=[i for i in ids if i not in {x['advertId'] for x in stats}],basis='whole campaign totals counted once; funding is not expense'))
  base='https://api.moysklad.ru/api/remap/1.2';headers={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN'],'Accept-Encoding':'gzip'}
  def get(path,params):
   r=requests.get(base+path,params=params,headers=headers,timeout=60)
   if not r.ok:raise RuntimeError('MoySklad HTTP '+str(r.status_code))
   return r.json()
  stores=get('/entity/store',dict(limit=1000))
  if stores.get('meta',{}).get('size',1001)>len(stores.get('rows',[])):raise RuntimeError('Store coverage incomplete')
  stores=[s for s in stores['rows'] if s.get('name')=='МСК' and not s.get('archived')]
  if len(stores)!=1:raise RuntimeError('MSK warehouse ambiguous')
  rows=[];offset=0
  while True:
   j=get('/report/stock/all',dict(filter='store='+stores[0]['meta']['href']+';stockMode=all;quantityMode=all',limit=1000,offset=offset))
   part=j.get('rows');size=j.get('meta',{}).get('size')
   if not isinstance(part,list) or type(size) is not int:raise RuntimeError('COGS coverage unknown')
   rows+=part
   if len(rows)>=size:break
   if not part or offset>50000:raise RuntimeError('COGS pagination incomplete')
   offset+=len(part)
  c.put(KEY+':stock',dict(observed_at=stamp(),warehouse='МСК',complete=True,rows=[{k:r.get(k) for k in ['article','price','stock','reserve']} for r in rows]))
  state.update(status='complete',completed_at=stamp());c.put(KEY,state)
  print('Current-day private snapshots saved; no WB writes or Telegram messages')
 except Exception as ex:
  state.update(status='blocked',error=str(ex) if isinstance(ex,RuntimeError) else type(ex).__name__,completed_at=stamp());c.put(KEY,state)
  raise RuntimeError('Private snapshot incomplete; inspect its private state') from None
if __name__=='__main__':main()
