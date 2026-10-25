"""One approved hourly read of the search CPC test. No marketplace writes or Telegram."""
import requests,json,time
from datetime import datetime,timezone
from china_loss_execute import IO
io=IO();key='china_agent:search_test:2026-10-25:hour22:v1'
if io.get(key):print('existing_slot_snapshot');raise SystemExit
assert io.get('china_agent:codex_search_launch:2026-10-25:v1:execution')['status']=='verified'
assert io.get('china_agent:codex_search_exclude553:2026-10-25:v1:execution')['status']=='verified'
out=dict(observed_at=datetime.now(timezone.utc).isoformat(),slot='2026-10-25T22:10',wb_writes=0,telegram_sends=0)
for name,path in [('campaign','/api/advert/v2/adverts?ids=41298169'),('budget','/adv/v1/budget?id=41298169'),('fullstats','/adv/v3/fullstats?ids=41298169&beginDate=2026-10-25&endDate=2026-10-25')]:
 time.sleep(2)
 try:
  r=requests.get('https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},timeout=50)
  out[name]=dict(http=r.status_code,data=r.json() if r.content else None)
 except Exception as e:out[name]=dict(http=None,error=type(e).__name__)
out['completed_at']=datetime.now(timezone.utc).isoformat()
assert io.create(key,out)
print(json.dumps(dict(saved=True,wb_writes=0,telegram_sends=0,http={k:v['http'] for k,v in out.items() if isinstance(v,dict)})))
