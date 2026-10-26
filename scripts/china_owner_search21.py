"""One owner-approved 21-SKU cross-placement test; no automatic re-funding or pauses."""
import os,json,copy,time,math
from datetime import datetime,timezone
import requests
from china_cloud_cost_control import Cache,validate_identity
KEY='china_agent:owner_search_expand:2026-10-26:v4:execution'
ARTICLES=['143-ReginaBag-black','447-AngelaBag-burgundy','595-Noelbag-zblack','600-JessicaBag-blue','044-NoelBag-black','673-NoelBag-green','58-NoelBag-brown','208-AngelaBag-black','36-EthelBag-brown','267-AmiraBag-beige','623-AngelaBag-brown','523-AngelaBag-black','680-VivienneBag-black','594-NoelBag-green','2-FurPanama-black','8-FurPanama-pink','92-Zont-red','64-Zont-cream-beige','114-Zont-Iblue','65-Zont-lilac-cream','26-Zont-green']
class Wire:
 def __init__(self):self.token=os.environ['WB_TOKEN_3']
 def req(self,path,method='GET',body=None):
  permitted={('GET','/adv/v1/balance'),('GET','/adv/v1/promotion/count'),('GET','/api/advert/v2/adverts'),('GET','/api/advert/v1/config'),('POST','/api/advert/v2/budget'),('POST','/api/advert/v1/bids/min'),('PATCH','/adv/v0/auction/nms'),('PATCH','/api/advert/v1/bids'),('POST','/adv/v2/seacat/save-ad'),('PUT','/api/advert/v0/daily-limits'),('GET','/api/advert/v0/daily-limits'),('POST','/adv/v1/budget/deposit'),('GET','/adv/v0/start')}
  if (method,path.split('?')[0]) not in permitted:raise RuntimeError('Endpoint outside exact owner scope')
  time.sleep(2);r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':self.token},json=body,timeout=50)
  if not r.ok:raise RuntimeError('WB HTTP '+str(r.status_code))
  return r.json() if r.content else {}
 def campaigns(self,ids):return {str(x['id']):x for x in self.req('/api/advert/v2/adverts?ids='+','.join(map(str,ids)))['adverts']}
def run():
 c=Cache();w=Wire();validate_identity(c,w)
 out=dict(status='read_only',observed_at=datetime.now(timezone.utc).isoformat(),balance=w.req('/adv/v1/balance'),budgets=w.req('/api/advert/v2/budget','POST',dict(advertIds=[41325622,41325637])),campaigns=w.campaigns([41325622,41325637]))
 c.put('china_agent:owner_search_fund:2026-10-26:reconciliation:v1',out)
 print('Read-only reconciliation saved privately; no WB writes')
if __name__=='__main__':run()
