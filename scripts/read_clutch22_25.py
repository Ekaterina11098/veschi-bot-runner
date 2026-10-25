"""Scheduled read-only 22:00 MSK check of one campaign. No Telegram transport."""
import os,json,time,requests
from datetime import datetime,timezone
from china_loss_execute import IO
io=IO();key='china_agent:campaign_monitor:41155909:2026-10-25T22:v1'
if io.get(key):print('existing_slot_snapshot');raise SystemExit
out=dict(observed_at=datetime.now(timezone.utc).isoformat(),slot='2026-10-25T22:00',wb_writes=0,telegram_sends=0)
def read(host,path):
 time.sleep(2)
 try:
  r=requests.get('https://'+host+path,headers={'Authorization':io.token},timeout=50)
  return dict(http=r.status_code,data=r.json() if r.content else None)
 except Exception as e:return dict(http=None,error=type(e).__name__)
out['campaign']=read('advert-api.wildberries.ru','/api/advert/v2/adverts?ids=41155909')
out['budget']=read('advert-api.wildberries.ru','/adv/v1/budget?id=41155909')
out['fullstats']=read('advert-api.wildberries.ru','/adv/v3/fullstats?ids=41155909&beginDate=2026-10-25&endDate=2026-10-25')
out['orders']=read('marketplace-api.wildberries.ru','/api/v3/orders?limit=1000&next=0&dateFrom=1792875600&dateTo='+str(int(datetime.now(timezone.utc).timestamp())))
out['completed_at']=datetime.now(timezone.utc).isoformat()
assert io.create(key,out)
print(json.dumps(dict(saved=True,wb_writes=0,telegram_sends=0,http={k:v.get('http') for k,v in out.items() if isinstance(v,dict)})))
