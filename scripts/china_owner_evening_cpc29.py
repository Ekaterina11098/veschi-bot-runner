"""One owner-requested read-only order timeline/current campaign snapshot."""
import os,requests
from datetime import datetime,timezone,timedelta
from china_cloud_cost_control import Cache,WB,stamp,validate_identity
ROOT='china_agent:evening_cpc_review:2026-10-29:v1'
MSK=timezone(timedelta(hours=3))
def main():
 assert datetime.now(MSK).date().isoformat()=='2026-10-29'
 c=Cache();w=WB()
 if c.get(ROOT):return
 validate_identity(c,w);cut=datetime.now(MSK)
 state=dict(status='collecting',cutoff_msk=cut.isoformat(),observed_at=stamp(),wb_writes=0,telegram_sends=0)
 if not c.create(ROOT,state):return
 try:
  start=int(datetime(2026,10,28,tzinfo=MSK).timestamp());end=int(cut.timestamp());cursor=0;rows={};pages=0
  while True:
   r=requests.get('https://marketplace-api.wildberries.ru/api/v3/orders',headers={'Authorization':os.environ['WB_TOKEN_3']},params=dict(limit=1000,next=cursor,dateFrom=start,dateTo=end),timeout=60,allow_redirects=False)
   if not r.ok:raise RuntimeError('FBS orders HTTP '+str(r.status_code))
   j=r.json();part=j.get('orders')
   if not isinstance(part,list):raise RuntimeError('FBS shape unknown')
   for x in part:
    v={k:x.get(k) for k in ['id','nmId','article','createdAt']}
    if v['id'] in rows and rows[v['id']]!=v:raise RuntimeError('FBS identity conflict')
    rows[v['id']]=v
   pages+=1;nxt=j.get('next')
   if not part or not nxt:break
   if nxt==cursor or pages>=5:raise RuntimeError('FBS pagination incomplete')
   cursor=nxt
  c.put(ROOT+':orders',dict(rows=list(rows.values()),complete=True,observed_at=stamp(),cutoff_msk=cut.isoformat(),pages=pages,scope='FBS created orders, not buyouts'))
  inv=w.req('/adv/v1/promotion/count')
  ids=sorted({x['advertId'] for g in inv.get('adverts',[]) for x in g.get('advert_list',[])})
  if len(ids)>50:raise RuntimeError('Campaign read bound exceeded')
  campaigns=w.req('/api/advert/v2/adverts?ids='+','.join(map(str,ids)))
  c.put(ROOT+':campaigns',dict(observed_at=stamp(),ids=ids,data=campaigns))
  state.update(status='complete',completed_at=stamp());c.put(ROOT,state)
 except Exception as ex:
  state.update(status='blocked',error=str(ex) if isinstance(ex,RuntimeError) else type(ex).__name__,completed_at=stamp());c.put(ROOT,state)
  raise RuntimeError('Private evening review incomplete') from None
if __name__=='__main__':
 try:main();print('Private owner-requested read completed.')
 except Exception:print('Private read incomplete; inspect private state.');raise SystemExit(1)
