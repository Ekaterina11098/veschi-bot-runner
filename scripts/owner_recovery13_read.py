"""Owner-scoped read-only diagnosis. No model calls or marketplace mutations."""
import json,os,time
from datetime import datetime,timezone
from urllib.parse import urlparse
import requests
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
from china_analytic_dialog import allowed_read,reading
from china_product_current import read_prices
from china_moysklad_read import read_stock
from china_hourly_sales_read import collect_funnel,MSK
ROOT='china_agent:owner_recovery04417741779660:2026-11-13:v2'
TARGETS=[1473243894,1473244337]
CIDS=[40933588,41298169,41779660]
def run():
 c=Cache()
 if c.get(ROOT):return
 wb=WB();validate_identity(c,wb)
 original=requests.sessions.Session.request
 def guard(session,method,url,**kw):
  u=urlparse(url);m=method.upper()
  private=url.startswith(c.url) and u.path.endswith('/telegram_api_cache') and m in ['GET','POST','PATCH']
  warehouses=m=='GET' and u.hostname=='marketplace-api.wildberries.ru' and u.path=='/api/v3/warehouses'
  if not(private or warehouses or allowed_read(method,url,kw.get('json'))):raise ValueError('Read-only scope blocked')
  return original(session,method,url,**kw)
 read_context=reading();read_context.__enter__()
 requests.sessions.Session.request=guard
 result=dict(cabinet='token_3',observed_at=stamp(),inputs={},errors={},wb_writes=0,telegram_calls=0,model_calls=0,grants_action_permission=False)
 def save():
  if c.get(ROOT):c.put(ROOT,result)
  else:c.create(ROOT,result)
 def get(url,params=None):
  r=requests.get(url,params=params,headers={'Authorization':os.environ['WB_TOKEN_3']},timeout=50)
  if r.status_code==429:
   time.sleep(min(60,max(7,int(r.headers.get('Retry-After','7')))))
   r=requests.get(url,params=params,headers={'Authorization':os.environ['WB_TOKEN_3']},timeout=50)
  if not r.ok:raise ValueError('Read HTTP '+str(r.status_code))
  return r.json()
 def stage(name,fn):
  try:result['inputs'][name]=fn()
  except Exception as ex:result['errors'][name]=str(ex)[:220] if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__
  save()
 try:
  stage('campaigns',lambda:wb.campaigns(CIDS))
  cp=result['inputs'].get('campaigns',{})
  new=cp.get(41779660,cp.get('41779660',{}));newids=[r['nm_id']for r in new.get('nm_settings',[])]
  if len(newids)!=18:raise ValueError('Exact new campaign coverage changed')
  ids=TARGETS+newids
  stage('prices',lambda:read_prices(get,ids))
  prices=result['inputs'].get('prices',{}).get('rows',[])
  stage('stock_msk',lambda:read_stock([r['article']for r in prices if r['nm_id']in TARGETS],warehouse_role='msk'))
  stage('stock_guangzhou',lambda:read_stock(list(dict.fromkeys(r['article']for r in prices if r['nm_id']in newids)),warehouse_role='guangzhou'))
  stage('warehouses',lambda:get('https://marketplace-api.wildberries.ru/api/v3/warehouses'))
  mapping={z:r['nm_id']for r in prices for z in r['size_ids']}
  warehouses=result['inputs'].get('warehouses',[])
  if not isinstance(warehouses,list) or len(warehouses)>15:raise ValueError('Warehouse read scope ambiguous')
  for wh in warehouses:
   wid=wh.get('id')
   if type(wid)is not int:continue
   def stock(wid=wid):
    r=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/'+str(wid),headers={'Authorization':os.environ['WB_TOKEN_3']},json={'chrtIds':sorted(mapping)},timeout=50)
    if not r.ok:raise ValueError('Published stock HTTP '+str(r.status_code))
    return dict(observed_at=stamp(),raw=r.json(),size_to_nm=mapping)
   stage('published_stock:'+str(wid),stock)
  stage('funnel',lambda:collect_funnel(c,datetime.now(MSK),TARGETS))
  stage('completed_ads',lambda:wb.req('/adv/v3/fullstats?ids=40933588,41298169&beginDate=2026-11-07&endDate=2026-11-12'))
  time.sleep(21)
  stage('new_campaign_ads',lambda:wb.req('/adv/v3/fullstats?ids=41779660&beginDate=2026-11-11&endDate=2026-11-13'))
 finally:
  requests.sessions.Session.request=original
  read_context.__exit__(None,None,None)
 result['completed_at']=stamp();result['status']='complete' if not result['errors']else'partial';save()
 if c.get(ROOT)!=json.loads(json.dumps(result)):raise ValueError('Readback mismatch')
 print(json.dumps(dict(status=result['status'],stages=list(result['inputs']),errors=result['errors'],wb_writes=0,telegram_calls=0,model_calls=0)))
if __name__=='__main__':run()

