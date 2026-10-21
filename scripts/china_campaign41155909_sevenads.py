import json,requests
from datetime import datetime,timezone
from china_price_apply import IO
from analytics.mpstats_probe import sanitize
io=IO();key='china_agent:seven_ad_diagnosis:2026-10-21:wb:v1'
if io.get(key):print('already_read');raise SystemExit()
out=dict(observed_at=datetime.now(timezone.utc).isoformat(),reads=[],wb_writes=0,telegram_calls=0)
for path,params in [('/api/advert/v2/adverts',dict(ids='40933588,41055480')),('/adv/v3/fullstats',dict(ids='40933588,41055480',beginDate='2026-09-21',endDate='2026-10-20'))]:
 r=requests.get('https://advert-api.wildberries.cn'+path,params=params,headers={'Authorization':io.token},timeout=(10,90),allow_redirects=False)
 item=dict(path=path,status_code=r.status_code)
 if r.status_code==200:item['data']=sanitize(r.json())
 elif r.status_code==429:item['retry_after']=r.headers.get('Retry-After')
 out['reads'].append(item)
io.create(key,out)
print(json.dumps(dict(status='retained',codes=[r['status_code'] for r in out['reads']],wb_writes=0,telegram_calls=0)))
