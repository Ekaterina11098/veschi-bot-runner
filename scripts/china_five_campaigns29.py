"""Owner requested diagnostics of five China campaigns. Read only."""
import os,json,requests,time
from datetime import datetime,timezone,timedelta
from china_cloud_cost_control import Cache,WB,stamp,validate_identity
KEY='china_agent:orders12_followup:2026-10-29:v1'
IDS=[41270309]
def main():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner' and os.environ['GITHUB_REF']=='refs/heads/main'
 assert datetime.now(timezone(timedelta(hours=3))).date().isoformat()=='2026-10-29'
 c=Cache();w=WB();validate_identity(c,w)
 if c.get(KEY):print('Existing snapshot; no repeat');return
 assert c.create(KEY,dict(status='collecting',observed_at=stamp(),WBwrites=0,TelegramSends=0))
 inv=w.req('/adv/v1/promotion/count');allids=sorted({x['advertId'] for g in inv.get('adverts',[]) for x in g.get('advert_list',[])})
 camps=w.campaigns(allids)
 c.put(KEY+':campaigns',dict(observed_at=stamp(),campaigns=camps))
 targets={k:v for k,v in camps.items() if int(k) in IDS};assert len(targets)==1
 c.put(KEY+':budgets',dict(observed_at=stamp(),data=w.req('/api/advert/v2/budget','POST',dict(advertIds=IDS))))
 statsids=IDS
 stats=w.req('/adv/v3/fullstats?ids='+','.join(map(str,statsids))+'&beginDate=2026-10-26&endDate=2026-10-29')
 c.put(KEY+':stats',dict(observed_at=stamp(),requested_ids=statsids,data=stats))
 msktime=timezone(timedelta(hours=3));cutoff=datetime.now(timezone.utc);start=datetime(2026,10,28,tzinfo=msktime)
 wanted={n['nm_id'] for v in targets.values() for n in v['nm_settings']};cursor=0;seen={};pages=set()
 while True:
  assert cursor not in pages;pages.add(cursor)
  r=requests.get('https://marketplace-api.wildberries.ru/api/v3/orders',params=dict(limit=1000,next=cursor,dateFrom=int(start.timestamp()),dateTo=int(cutoff.timestamp())),headers={'Authorization':w.token},timeout=45)
  assert r.ok,'Orders HTTP '+str(r.status_code)
  j=r.json();part=j.get('orders');assert isinstance(part,list)
  for x in part:
   if x['nmId'] not in wanted:continue
   dt=datetime.fromisoformat(x['createdAt'].replace('Z','+00:00'))
   if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
   seen[str(x['id'])]=dict(nm=str(x['nmId']),article=x.get('article'),created_msk=dt.astimezone(msktime).strftime('%Y-%m-%d %H:%M:%S'))
  nxt=j.get('next')
  if not part or not nxt:break
  assert nxt!=cursor;cursor=nxt;time.sleep(1)
 c.put(KEY+':orders',dict(observed_at=stamp(),cutoff_msk=cutoff.astimezone(msktime).isoformat(),complete=True,pages=len(pages),rows=list(seen.values())))
 c.put(KEY,dict(status='complete',observed_at=stamp(),cutoff_msk=cutoff.astimezone(msktime).isoformat(),WBwrites=0,TelegramSends=0))
 print('Five-campaign diagnosis inputs saved privately; no WB writes')
if __name__=='__main__':main()
