"""Owner-requested narrow read of one campaign, without writes or Telegram."""
import json,time,requests
from datetime import datetime,timezone
from china_loss_execute import IO
io=IO();key='china_agent:campaign41270309:2026-10-25:owner2252:v1'
if io.get(key):print('existing_owner_snapshot');raise SystemExit
out=dict(observed_at=datetime.now(timezone.utc).isoformat(),campaign_id=41270309,wb_writes=0,telegram_sends=0)
for name,path in [('campaign','/api/advert/v2/adverts?ids=41270309'),('budget','/adv/v1/budget?id=41270309'),('fullstats','/adv/v3/fullstats?ids=41270309&beginDate=2026-10-23&endDate=2026-10-25')]:
 time.sleep(1.5)
 try:
  r=requests.get('https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},timeout=50)
  out[name]=dict(http=r.status_code,data=r.json() if r.content else None)
 except Exception as e:out[name]=dict(http=None,error=type(e).__name__)
out['completed_at']=datetime.now(timezone.utc).isoformat()
assert io.create(key,out)
print(json.dumps(dict(saved=True,wb_writes=0,telegram_sends=0,http={k:v['http'] for k,v in out.items() if isinstance(v,dict)})))
