"""Read rejected limit state, then one idempotent exact setting reconciliation."""
import requests
from china_price_apply import IO,now
io=IO();pid='china-new-ad-test-20261023-8sku-v4-three'
e=io.get('china_agent:new_ad_execution:v1:'+pid);c=e['campaigns'][0];cid=c['campaign_id']
assert e['reason']=='WB advertising HTTP 400' and c['steps']['limit']['status']=='uncertain'
key='china_agent:new_ad_limit_diagnostic:v1:'+pid
assert io.create(key,dict(status='reading',at=now().isoformat()))
out=dict(campaign_id=cid,reads=[],at=now().isoformat())
for path,method,body in [('/api/advert/v0/daily-limits?advertIds='+str(cid),'GET',None),('/api/advert/v2/adverts?ids='+str(cid),'GET',None),('/api/advert/v0/daily-limits','PUT',c['steps']['limit']['body'])]:
 r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},json=body,timeout=45)
 try:j=r.json()
 except ValueError:j=r.text[:3000]
 out['reads'].append(dict(path=path,method=method,http=r.status_code,data=j));io.put(key,out)
print('Exact existing-draft limit response saved privately; no deposits or starts')

