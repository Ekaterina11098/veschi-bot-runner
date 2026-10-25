"""Owner requested narrow read-only search campaign snapshot."""
import json,time,requests
from datetime import datetime,timezone
from china_loss_execute import IO
io=IO()
def read(path,method='GET',body=None):
 time.sleep(1.5)
 r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},json=body,timeout=50)
 return dict(http=r.status_code,data=r.json() if r.content else None)
out=dict(observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_sends=0)
out['campaigns']=read('/api/advert/v2/adverts?ids=41298169')
out['budgets']=read('/api/advert/v2/budget','POST',dict(advertIds=[41298169]))
out['fullstats']=read('/adv/v3/fullstats?ids=41298169&beginDate=2026-10-25&endDate=2026-10-25')
io.put('china_agent:search_test:2026-10-25:owner_check:v1',out)
print(json.dumps(dict(status='private_snapshot_saved',http={k:v['http'] for k,v in out.items() if isinstance(v,dict) and 'http'in v},wb_writes=0)))
