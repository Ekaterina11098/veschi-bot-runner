"""Exact 143 diagnostics, OOO token_1, marketplace reads only."""
import os,time,datetime,hashlib,requests
import ooo_owner_apply_all_20261102 as w
w.KEY='ooo_agent:143_review:2026-11-05:1249'
w.state={'status':'collecting','run_id':os.environ['GITHUB_RUN_ID'],'sources':{},'wb_writes':0,'started_at':w.stamp()}
if not w.claim(w.state):raise SystemExit('Existing review preserved')
def raw(host,path,method='GET',params=None,body=None):
 if (method,host,path)not in {('GET','advert-api.wildberries.ru','/adv/v3/fullstats'),('GET','advert-api.wildberries.ru','/api/advert/v2/adverts'),('POST','seller-analytics-api.wildberries.ru','/api/analytics/v3/sales-funnel/products')}:
  raise PermissionError('Read boundary')
 pk='wb-pause:'+hashlib.sha256((w.TOKEN+host+path).encode()).hexdigest()
 until=float((w.get(pk)or{}).get('until',0))
 if until>time.time():raise RuntimeError('Provider cooldown until '+datetime.datetime.fromtimestamp(until,datetime.timezone.utc).isoformat())
 r=requests.request(method,'https://'+host+path,headers={'Authorization':w.TOKEN},params=params,json=body,timeout=(10,90),allow_redirects=False)
 z=r.headers.get('Retry-After')or r.headers.get('X-Ratelimit-Retry')or r.headers.get('X-Ratelimit-Reset')
 try:sec=float(z or 0)
 except ValueError:sec=0
 if sec>time.time()-86400:sec=max(0,sec-time.time())
 if r.status_code==429 or(r.headers.get('X-Ratelimit-Remaining')=='0'and sec>0):w.put(pk,{'until':time.time()+max(sec,60)+3,'basis':'provider_header'})
 if not r.ok:raise RuntimeError('HTTP '+str(r.status_code)+' '+path+' '+r.text[:200])
 return r.json()
def read(k,fn):
 try:w.state['sources'][k]={'status':'complete','observed_at':w.stamp(),'data':fn()}
 except Exception as e:w.state['sources'][k]={'status':'unavailable','error':str(e)if isinstance(e,(RuntimeError,PermissionError))else type(e).__name__}
 w.save()
read('advertising',lambda:raw('advert-api.wildberries.ru','/adv/v3/fullstats',params={'ids':'39605581','beginDate':'2026-11-04','endDate':'2026-11-05'}))
read('funnel',lambda:raw('seller-analytics-api.wildberries.ru','/api/analytics/v3/sales-funnel/products','POST',body={'selectedPeriod':{'start':'2026-11-05','end':'2026-11-05'},'pastPeriod':{'start':'2026-11-04','end':'2026-11-04'},'nmIds':[851316021],'skipDeletedNm':False,'limit':1000,'offset':0}))
read('configuration',lambda:raw('advert-api.wildberries.ru','/api/advert/v2/adverts',params={'ids':'39605581'}))
w.state.update(status='finished',finished_at=w.stamp());w.save()
print('143 read-only review saved privately')
