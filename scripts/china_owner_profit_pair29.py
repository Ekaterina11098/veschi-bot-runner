"""One owner-requested current-day snapshot. Read-only WB/MS, private output, no messages."""
import os,time,requests
from datetime import datetime,timezone,timedelta
from china_cloud_cost_control import Cache,WB,stamp,validate_identity
DAY='2026-10-29'
KEY='china_agent:profit_pair:2026-10-29:owner-now:v1'
def main():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner' and os.environ['GITHUB_REF']=='refs/heads/main'
 assert datetime.now(timezone(timedelta(hours=3))).date().isoformat()==DAY
 c=Cache();w=WB()
 if c.get(KEY):print('Existing private snapshot; no repeated collection');return
 validate_identity(c,w)
 state=dict(status='collecting',observed_at=stamp(),cutoff_msk=datetime.now(timezone(timedelta(hours=3))).isoformat(),wb_writes=0,telegram_sends=0)
 if not c.create(KEY,state):raise RuntimeError('Snapshot already claimed')
 try:
  r=requests.get('https://statistics-api.wildberries.ru/api/v1/supplier/orders',params=dict(dateFrom='2026-10-28T00:00:00',flag=0),headers={'Authorization':os.environ['WB_TOKEN_3']},timeout=80)
  if not r.ok:raise RuntimeError('WB orders HTTP '+str(r.status_code))
  raw=r.json()
  if not isinstance(raw,list) or len(raw)>=80000:raise RuntimeError('Orders coverage incomplete')
  fields=['date','lastChangeDate','supplierArticle','nmId','srid','isCancel','cancelDate','totalPrice','discountPercent','spp','finishedPrice','priceWithDisc','currency','currencyName','currencyCode','orderType']
  selected=[{k:o[k] for k in fields if k in o} for o in raw if o.get('date','')[:10] in ['2026-10-28',DAY] and o.get('date','')[:19]<=state['cutoff_msk'][:19]]
  c.put(KEY+':orders',dict(observed_at=stamp(),rows=selected,raw_count=len(raw),selection='exact order date; lastChangeDate flag0',complete=True))
  inv=w.req('/adv/v1/promotion/count')
  statuses={str(x['advertId']):g.get('status') for g in inv.get('adverts',[]) for x in g.get('advert_list',[])}
  ids=sorted(map(int,statuses));stats=[]
  for start in range(0,len(ids),50):
   part=w.req('/adv/v3/fullstats?ids='+','.join(map(str,ids[start:start+50]))+'&beginDate=2026-10-28&endDate='+DAY)
   if not isinstance(part,list):raise RuntimeError('Advertising shape unknown')
   stats+=part
  if any(x.get('currency')!='CNY' for x in stats):raise RuntimeError('Advertising currency unconfirmed')
  c.put(KEY+':ads',dict(observed_at=stamp(),rows=stats,ids=ids,statuses=statuses,missing_ids=[i for i in ids if i not in {x['advertId'] for x in stats}],basis='whole campaign totals counted once; funding is not expense'))
  state.update(status='complete',completed_at=stamp());c.put(KEY,state)
  print('Current-day private snapshots saved; no WB writes or Telegram messages')
 except Exception as ex:
  state.update(status='blocked',error=str(ex) if isinstance(ex,RuntimeError) else type(ex).__name__,completed_at=stamp());c.put(KEY,state)
  raise RuntimeError('Private snapshot incomplete; inspect its private state') from None
if __name__=='__main__':
 try:main()
 except Exception:print('Private input snapshot incomplete.');raise SystemExit(1)
