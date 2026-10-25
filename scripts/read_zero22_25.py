"""Read only the approved bid-test campaign for its 22 MSK slot."""
import json,time,requests
from datetime import datetime,timezone
from china_loss_execute import IO
io=IO();key='china_agent:bid_monitor:0:2026-10-25T22:v1'
if io.get(key):print('existing_slot_snapshot');raise SystemExit
proof=io.get('china_agent:codex_bid_raise:2026-10-23:v1:execution')
assert proof and proof['status']=='verified' and proof['plan']['nm_id']==1473243891
out=dict(observed_at=datetime.now(timezone.utc).isoformat(),slot='2026-10-25T22:00',wb_writes=0,telegram_sends=0)
for name,path in [('campaign','/api/advert/v2/adverts?ids=40933588'),('fullstats','/adv/v3/fullstats?ids=40933588&beginDate=2026-10-23&endDate=2026-10-25')]:
 time.sleep(2)
 try:
  r=requests.get('https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},timeout=50)
  out[name]=dict(http=r.status_code,data=r.json() if r.content else None)
 except Exception as e:out[name]=dict(http=None,error=type(e).__name__)
out['completed_at']=datetime.now(timezone.utc).isoformat()
assert io.create(key,out)
print(json.dumps(dict(saved=True,wb_writes=0,telegram_sends=0,http={k:v['http'] for k,v in out.items() if isinstance(v,dict)})))
