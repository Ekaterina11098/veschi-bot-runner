"""Bounded fresh inputs for two owner-requested risk proposals; read-only."""
import json,os,time
from urllib.parse import urlparse
import requests
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
from china_moysklad_read import read_stock
from china_product_current import read_prices
from china_analytic_dialog import reading,allowed_read
ROOT='china_agent:owner_umbrella_risk:2026-11-14:v1'
CIDS=[41325637]
EXTRA=[]
def main():
 c=Cache()
 if(c.get(ROOT)or{}).get('status')=='complete':return
 w=WB();validate_identity(c,w)
 old=requests.sessions.Session.request;ctx=reading();ctx.__enter__()
 def guard(session,method,url,**kw):
  u=urlparse(url);m=method.upper();private=url.startswith(c.url)and u.path.endswith('/telegram_api_cache')and m in ['GET','POST','PATCH']
  if not(private or allowed_read(method,url,kw.get('json'))):raise ValueError('Read-only scope')
  return old(session,method,url,**kw)
 requests.sessions.Session.request=guard
 out=c.get(ROOT)or dict(status='reading',created_at=stamp(),inputs={},errors={},wb_writes=0,telegram_calls=0,model_calls=0,grants_action_permission=False)
 def save():
  v=json.loads(json.dumps(out))
  if c.get(ROOT):c.put(ROOT,v)
  else:c.create(ROOT,v)
 def stage(name,fn):
  if name in out['inputs']:return
  try:out['inputs'][name]=fn()
  except Exception as ex:out['errors'][name]=str(ex)[:180]if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__
  save()
 def get(url,params=None):
  r=requests.get(url,params=params,headers={'Authorization':w.token},timeout=50)
  if r.status_code==429:
   time.sleep(min(60,max(7,int(r.headers.get('Retry-After','7')))));r=requests.get(url,params=params,headers={'Authorization':w.token},timeout=50)
  if not r.ok:raise ValueError('Exact read HTTP '+str(r.status_code))
  return r.json()
 try:
  stage('campaigns',lambda:w.campaigns(CIDS))
  cp=out['inputs']['campaigns'];ids=sorted({n['nm_id']for v in cp.values()for n in v['nm_settings']}|set(EXTRA))
  if len(ids)>20:raise ValueError('Current scope expanded')
  stage('prices',lambda:read_prices(get,ids))
  prices=out['inputs'].get('prices',{})
  stage('stock',lambda:read_stock([r['article']for r in prices['rows']],'msk'))
  def published():
   mapping={z:r['nm_id']for r in prices['rows']for z in r['size_ids']}
   r=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',headers={'Authorization':w.token},json={'chrtIds':sorted(mapping)},timeout=50)
   if not r.ok:raise ValueError('WB stock HTTP '+str(r.status_code))
   return dict(observed_at=stamp(),raw=r.json(),size_to_nm=mapping)
  stage('published',published)
  stage('budgets',lambda:w.req('/api/advert/v2/budget','POST',{'advertIds':CIDS}))
  for cid in CIDS:stage('minimum:'+str(cid),lambda cid=cid:w.minimums(cid,[n['nm_id']for n in cp[str(cid)]['nm_settings']],'recommendations'))
  stage('stats',lambda:w.req('/adv/v3/fullstats?ids=41325637&beginDate=2026-11-09&endDate=2026-11-13'))
 finally:requests.sessions.Session.request=old;ctx.__exit__(None,None,None)
 out.update(status='complete'if not out['errors']else'partial',completed_at=stamp());save();print(json.dumps({'status':out['status'],'errors':out['errors'],'wb_writes':0}))
if __name__=='__main__':main()

