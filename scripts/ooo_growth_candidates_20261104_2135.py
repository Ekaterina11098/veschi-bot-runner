"""Read-only exact growth candidate configuration, price, stock and economics inputs."""
import os,json,time,hashlib,requests
import ooo_owner_apply_all_20261102 as w
from china_moysklad_read import read_stock
w.KEY='ooo_agent:growth_candidates:2026-11-04:2135'
w.state={'status':'collecting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':w.stamp(),'steps':{},'sources':{},'wb_writes':0}
NMS=[851230666,1124312592,1124312599,1124312598,850720070]
ARTICLES=['523-AngelaBag-black','57-NoelBag-burgundy','64-NoelBag-zchocolate','63-NoelBag-zdarkblue','044-NoelBag-black']
def scope():
 e=w.get('ooo_agent:urgent_actions:2026-11-04:v1:execution')or{}
 if e.get('status')!='verified'or e.get('manifest',{}).get('cabinet')!='token_1':raise PermissionError('OOO identity baseline')
 return e
w.authorize=scope
if not w.claim(w.state):raise SystemExit('Existing candidate checks retained')
def raw(host,path,method='GET',body=None,params=None):
 if(method,host,path)not in{('GET','discounts-prices-api.wildberries.ru','/api/v2/list/goods/filter'),('POST','seller-analytics-api.wildberries.ru','/api/analytics/v3/sales-funnel/products')}:raise PermissionError('Read boundary')
 pk='wb-pause:'+hashlib.sha256((w.TOKEN+host+path).encode()).hexdigest()
 for _ in range(3):
  w.wait_until(float((w.get(pk)or{}).get('until',0)),path);scope()
  r=requests.request(method,'https://'+host+path,headers={'Authorization':w.TOKEN},params=params,json=body,timeout=(10,90),allow_redirects=False)
  rawdelay=r.headers.get('Retry-After')or r.headers.get('X-Ratelimit-Retry')or r.headers.get('X-Ratelimit-Reset')
  try:delay=float(rawdelay or 0)
  except ValueError:delay=0
  if delay>time.time()-86400:delay=max(0,delay-time.time())
  if r.status_code==429 or(r.headers.get('X-Ratelimit-Remaining')=='0'and delay>0):w.put(pk,{'until':time.time()+max(delay,60)+3,'basis':'provider_header'})
  if r.status_code==429:continue
  if not r.ok:raise RuntimeError('Read HTTP '+str(r.status_code)+' '+path)
  return r.json()
 raise RuntimeError('Read quota pending')
def read(k,fn):
 try:w.state['sources'][k]={'status':'complete','data':fn(),'observed_at':w.stamp()}
 except Exception as e:w.state['sources'][k]={'status':'unavailable','error':str(e)if isinstance(e,(RuntimeError,ValueError,PermissionError))else type(e).__name__}
 w.save()
scope()
read('configurations',lambda:w.configs([39605579,39605581,39605582,40385586,41515989,41516310,41516903,41517233,41517533]))
read('prices',lambda:raw('discounts-prices-api.wildberries.ru','/api/v2/list/goods/filter',params={'limit':1000,'offset':0}))
read('funnel',lambda:raw('seller-analytics-api.wildberries.ru','/api/analytics/v3/sales-funnel/products','POST',body={'selectedPeriod':{'start':'2026-10-28','end':'2026-11-03'},'pastPeriod':{'start':'2026-10-21','end':'2026-10-27'},'nmIds':NMS,'skipDeletedNm':False,'limit':1000,'offset':0}))
read('moysklad',lambda:read_stock(ARTICLES))
w.state.update(status='finished',finished_at=w.stamp());w.save()
print('Exact candidate read-only evidence saved')
