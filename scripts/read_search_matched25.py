"""Read search minima only for products belonging to their actual campaigns."""
import json,time,requests
from china_loss_execute import IO
from datetime import datetime,timezone
io=IO();p=io.get('china_agent:search_probe:2026-10-25:request');old=io.get('china_agent:search_probe:2026-10-25:result')
def read(path,method='GET',body=None):
 time.sleep(1.5);r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},json=body,timeout=50);return dict(http=r.status_code,data=r.json() if r.content else None)
cs=read('/api/advert/v2/adverts?ids=40933588,41055480');out=dict(observed_at=datetime.now(timezone.utc).isoformat(),campaigns=cs,minima={},wb_writes=0)
for c in cs['data'].get('adverts',[]):
 ids=sorted(set(p['nm_ids']) & {n['nm_id'] for n in c['nm_settings']})
 if ids:out['minima'][str(c['id'])]=read('/api/advert/v1/bids/min','POST',dict(advert_id=c['id'],nm_ids=ids,payment_type='cpc',placement_types=['search']))
key='china_agent:search_probe:2026-10-25:matched_minima'
io.put(key,out) if io.get(key) else io.create(key,out)
print(json.dumps(dict(status='private_search_minima_saved',wb_writes=0)))
