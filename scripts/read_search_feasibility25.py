"""Read-only CPC search feasibility and two scheduled campaign snapshots. No writes to WB or Telegram."""
import os,json,time,requests
from datetime import datetime,timezone
from china_loss_execute import IO
io=IO()
key='china_agent:search_probe:2026-10-25:result'
p=io.get('china_agent:search_probe:2026-10-25:request')
def read(path,method='GET',body=None):
 time.sleep(1.5);r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},json=body,timeout=50)
 return dict(http=r.status_code,data=r.json() if r.content else None)
out=dict(observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_sends=0)
out['config']=read('/api/advert/v1/config')
out['search_minima']=read('/api/advert/v1/bids/min','POST',dict(advert_id=40933588,nm_ids=p['nm_ids'],payment_type='cpc',placement_types=['search']))
out['campaigns']=read('/api/advert/v2/adverts?ids=40933588,41155909')
out['budgets']=read('/api/advert/v2/budget','POST',dict(advertIds=[40933588,41155909]))
out['fullstats']=read('/adv/v3/fullstats?ids=40933588,41155909&beginDate=2026-10-23&endDate=2026-10-25')
io.put(key,out) if io.get(key) else io.create(key,out)
print(json.dumps(dict(status='private_readbacks_saved',http={k:v['http'] for k,v in out.items() if isinstance(v,dict) and 'http' in v},wb_writes=0)))
