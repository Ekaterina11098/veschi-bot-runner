"""Read-only funding reconciliation: never repeats a deposit."""
import requests,time
from china_price_apply import IO,now
io=IO();pid='china-new-ad-test-20261023-8sku-v4-three'
e=io.get('china_agent:new_ad_execution:v1:'+pid)
ids=[c['campaign_id'] for c in e['campaigns']]
out=dict(at=now().isoformat(),responses=[],wb_writes=0)
for path,method,body in [('/adv/v1/balance','GET',None),('/api/advert/v2/budget','POST',dict(advertIds=ids)),('/api/advert/v2/adverts?ids='+','.join(map(str,ids)),'GET',None)]:
 r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},json=body,timeout=45)
 try:j=r.json()
 except ValueError:j=r.text[:3000]
 out['responses'].append(dict(path=path,http=r.status_code,data=j));time.sleep(2)
key='china_agent:new_ad_funding_reconcile:v1:'+pid
io.put(key,out) if io.get(key) else io.create(key,out)
print('Read-only campaign funding and account balance saved privately')
