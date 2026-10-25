"""Owner-requested campaign review. Read-only WB data; private cache only."""
import json,time,requests
from datetime import datetime,timezone
from china_loss_execute import IO
io=IO()
KEY='china_agent:all_campaigns_owner_review:2026-10-25:late:v1'
if io.get(KEY):print('existing_snapshot');raise SystemExit
known=[40811856,40892162,40933588,40945478,40945502,40964981,41055480,41155824,41155909,41187173,41270309,41270471,41270474,41296359,41296363,41298169]
reuse={41270309,41270471,41270474,41296359,41296363}
out=dict(observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_sends=0,reused_ids=sorted(reuse))
def read(name,path,body=None):
 time.sleep(1.8)
 r=requests.get('https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},timeout=55) if body is None else requests.post('https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},json=body,timeout=55)
 try:data=r.json()
 except ValueError:data=None
 out[name]=dict(http=r.status_code,data=data,observed_at=datetime.now(timezone.utc).isoformat())
 return data if r.ok else None
inventory=read('inventory','/adv/v1/promotion/count')
ids=set(known)-reuse
if isinstance(inventory,dict):
 for group in inventory.get('adverts',[]):
  if group.get('status') in [4,7,9,11]:
   for row in group.get('advert_list',[]):ids.add(row['advertId'])
ids=sorted(ids-reuse)
out['requested_ids']=ids
read('campaigns','/api/advert/v2/adverts?ids='+','.join(map(str,ids)))
read('budgets','/api/advert/v2/budget',dict(advertIds=ids))
for offset in range(0,len(ids),50):
 batch=ids[offset:offset+50]
 read('fullstats_'+str(offset//50),'/adv/v3/fullstats?ids='+','.join(map(str,batch))+'&beginDate=2026-10-23&endDate=2026-10-25')
 time.sleep(1)
out['completed_at']=datetime.now(timezone.utc).isoformat()
assert io.create(KEY,out)
print(json.dumps(dict(saved=True,count=len(ids),http={k:v['http'] for k,v in out.items() if isinstance(v,dict) and 'http'in v},wb_writes=0,telegram_sends=0)))
