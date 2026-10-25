"""Scheduled read-only snapshot of five approved tests. No WB writes or Telegram calls."""
import os,json,time,requests
from datetime import datetime,timezone
from china_loss_execute import IO
io=IO();key='china_agent:expanded_tests:2026-10-25:slot16'
old=io.get(key)
if old:print(json.dumps(dict(status=old['status'],cached=True)));raise SystemExit(0)
assert io.get('china_agent:codex_candidate_funding:2026-10-25:v1:execution')['status']=='verified'
assert io.create(key,dict(status='reading',started_at=datetime.now(timezone.utc).isoformat()))
ids=[41270309,41270471,41270474,41296359,41296363]
def read(path,method='GET',body=None):
 time.sleep(1.5);r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},json=body,timeout=50);return dict(http=r.status_code,data=r.json() if r.content else None)
out=dict(status='observed',slot='2026-10-25T16:10:00+03:00',observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_sends=0)
out['campaigns']=read('/api/advert/v2/adverts?ids='+','.join(map(str,ids)))
out['budgets']=read('/api/advert/v2/budget','POST',dict(advertIds=ids))
out['fullstats']=read('/adv/v3/fullstats?ids='+','.join(map(str,ids))+'&beginDate=2026-10-25&endDate=2026-10-25')
io.put(key,out);print(json.dumps(dict(status='private_snapshot_saved',http={k:v['http'] for k,v in out.items() if isinstance(v,dict) and 'http'in v},wb_writes=0)))
