"""Owner-requested read-only diagnosis; no marketplace mutations."""
import os,json,requests
from datetime import datetime,timezone
from china_price_apply import IO
from analytics.mpstats_probe import sanitize
io=IO()
key='china_agent:campaign_diagnosis:41155909:2026-10-21:v1'
out=dict(observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0,telegram_calls=0,reads=[])
for host,path,params in [('https://advert-api.wildberries.cn','/api/advert/v2/adverts',dict(ids='41155909')),('https://advert-api.wildberries.cn','/adv/v1/budget',dict(id=41155909))]:
 r=requests.get(host+path,params=params,headers={'Authorization':os.environ['WB_TOKEN_3']},timeout=(10,40),allow_redirects=False)
 item=dict(path=path,status_code=r.status_code)
 if r.status_code==200:item['data']=sanitize(r.json())
 out['reads'].append(item)
io.put(key,out) if io.get(key) else io.create(key,out)
print(json.dumps(dict(status='recorded',http_codes=[x['status_code'] for x in out['reads']],wb_writes=0,telegram_calls=0)))
