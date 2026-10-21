"""Read-only investigation of exact China campaign reach constraints."""
import os,json,time,requests
from datetime import datetime,timezone
from china_price_apply import IO
KEY='china_agent:119_reach_constraints:2026-10-21:v1'
io=IO();old=io.get(KEY)
if old and old.get('status')=='complete':print('already_collected');raise SystemExit()
if old:raise RuntimeError('Existing partial audit requires review')
p=dict(status='collecting',started_at=datetime.now(timezone.utc).isoformat(),reads=[],wb_writes=0,telegram_calls=0)
if not io.create(KEY,p):raise RuntimeError('Concurrent audit')
def read(path,method='GET',params=None,body=None):
 r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},params=params,json=body,timeout=40)
 try:data=r.json()
 except Exception:data=dict(non_json=True)
 if r.status_code!=200:data=dict(error_response=True,status=r.status_code)
 p['reads'].append(dict(path=path,method=method,params=params,body=body,status=r.status_code,data=data,observed_at=datetime.now(timezone.utc).isoformat()));io.put(KEY,p)
 time.sleep(3)
read('/api/advert/v2/adverts',params=dict(ids='41155909,40945502,40945478,40811856'))
read('/adv/v1/budget',params=dict(id=41155909))
read('/api/advert/v0/daily-limits',params=dict(advertIds='41155909'))
read('/api/advert/v1/bids/min','POST',body=dict(advert_id=41155909,nm_ids=[1473243898],payment_type='cpc',placement_types=['recommendation','search']))
for cid,nm in [(41155909,1473243898),(40945502,1560345288),(40945478,1535337769),(40811856,1556488183)]:
 read('/api/advert/v0/bids/recommendations',params=dict(advertId=cid,nmId=nm))
r=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',headers={'Authorization':io.token},json=dict(skus=['2042184162004']),timeout=40)
p['stock']=dict(status=r.status_code,data=r.json() if r.status_code==200 else None,observed_at=datetime.now(timezone.utc).isoformat())
p['status']='complete';p['completed_at']=datetime.now(timezone.utc).isoformat();io.put(KEY,p)
print(json.dumps(dict(status=p['status'],read_statuses=[r['status'] for r in p['reads']],wb_writes=0,telegram_calls=0)))
