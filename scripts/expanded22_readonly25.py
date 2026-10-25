"""Narrow late 22:10 monitoring slot; no WB changes or Telegram calls."""
import json,time,requests
from datetime import datetime,timezone
from china_loss_execute import IO
KEY='china_agent:expanded_tests:2026-10-25:slot22:v1'
IDS=[41270471,41270474,41296359,41296363]
io=IO()
if io.get(KEY):
 print('existing_slot_snapshot');raise SystemExit
out=dict(observed_at=datetime.now(timezone.utc).isoformat(),slot='2026-10-25T22:10:00+03:00',ids=IDS,wb_writes=0,telegram_sends=0,reused_41270309='china_agent:codex_campaign41270309_trim:2026-10-25:v1:execution')
for name,path in [('campaigns','/api/advert/v2/adverts?ids='+','.join(map(str,IDS)))]+[('budget_'+str(i),'/adv/v1/budget?id='+str(i)) for i in IDS]+[('fullstats','/adv/v3/fullstats?ids='+','.join(map(str,IDS))+'&beginDate=2026-10-25&endDate=2026-10-25')]:
 time.sleep(1.5)
 r=requests.get('https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},timeout=50)
 try:data=r.json()
 except ValueError:data=None
 out[name]=dict(http=r.status_code,data=data,observed_at=datetime.now(timezone.utc).isoformat())
out['completed_at']=datetime.now(timezone.utc).isoformat()
assert io.create(KEY,out)
print(json.dumps(dict(saved=True,http={k:v['http'] for k,v in out.items() if isinstance(v,dict) and 'http' in v},wb_writes=0,telegram_sends=0)))
