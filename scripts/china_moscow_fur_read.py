"""Owner-requested exact furcoat evidence: fixed WB reads, private persistence only."""
import os,json,time
from datetime import datetime,timezone
import requests
IDS=[2215883910,2216045897,2216111729,2216167898,2216217906,2216257724,1900197978]
ROOT='china_agent:owner_moscow_fur:2026-11-11:v1'
def main():
 from conversion_watches import runtime
 w=runtime();now=datetime.now(timezone.utc).isoformat();out=dict(cabinet='token_3',observed_at=now,wb_writes=0,telegram_sends=0,model_calls=0,cards=[],reads={})
 headers={'Authorization':os.environ['WB_TOKEN_3']}
 def read(name,url,method='GET',body=None,params=None):
  r=requests.request(method,url,headers=headers,json=body,params=params,timeout=75,allow_redirects=False)
  result=dict(status=r.status_code,source=url,observed_at=datetime.now(timezone.utc).isoformat())
  if r.status_code==200:result['data']=r.json()
  else:result['retry_after']=r.headers.get('Retry-After')
  out['reads'][name]=result;w.save(ROOT+':raw:'+now,out)
  return result.get('data')
 date='2026-11-11'
 read('boxes','https://common-api.wildberries.ru/api/v1/tariffs/box',params={'date':date})
 read('returns','https://common-api.wildberries.ru/api/v1/tariffs/return',params={'date':date})
 read('commission','https://common-api.wildberries.ru/api/v1/tariffs/commission',params={'locale':'ru'})
 read('warehouses','https://marketplace-api.wildberries.ru/api/v3/warehouses')
 for nm in IDS:
  data=read('card:'+str(nm),'https://content-api.wildberries.ru/content/v2/get/cards/list','POST',{'settings':{'cursor':{'limit':100},'filter':{'withPhoto':-1,'textSearch':str(nm)}}})
  matches=[c for c in (data or{}).get('cards',[])if c.get('nmID')==nm]
  if len(matches)==1:
   c=matches[0];out['cards'].append({k:c.get(k)for k in ('nmID','vendorCode','subjectID','subjectName','dimensions','sizes')})
  time.sleep(0.7)
 out['status']='collected';out['source_key']=ROOT+':raw:'+now
 w.save(ROOT+':inputs',out)
 print(json.dumps(dict(status=out['status'],cards=len(out['cards']),http={k:r['status']for k,r in out['reads'].items()},wb_writes=0),ensure_ascii=False))
if __name__=='__main__':main()

