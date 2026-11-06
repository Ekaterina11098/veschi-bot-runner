"""Continue only the unavailable morning cohort read, respecting shared provider pauses."""
import os,time,json,hashlib,collections,requests
import ooo_owner_apply_all_20261102 as w
START='2026-10-05'
w.KEY='ooo_agent:morning:2026-11-06:cohort_retry'
w.state={'status':'collecting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':w.stamp(),'steps':{}}
def scope():
 a=w.get(w.ROOT+':authorization')
 if not a or a.get('cabinet')!='token_1'or a.get('plan_sha256')!=w.HASH:raise PermissionError('OOO read identity')
 return a
w.authorize=scope
if not w.claim(w.state):raise SystemExit('Existing cohort continuation retained')
def raw(host,path,params):
 if host!='statistics-api.wildberries.ru'or path not in ['/api/v1/supplier/orders','/api/v1/supplier/sales']:raise PermissionError('Read boundary')
 pk='wb-pause:'+hashlib.sha256((w.TOKEN+host+path).encode()).hexdigest()
 for _ in range(3):
  w.wait_until(float((w.get(pk)or{}).get('until',0)),path)
  r=requests.get('https://'+host+path,headers={'Authorization':w.TOKEN},params=params,timeout=(10,90),allow_redirects=False)
  delay=r.headers.get('Retry-After')or r.headers.get('X-Ratelimit-Retry')or r.headers.get('X-Ratelimit-Reset')
  try:delay=float(delay or 0)
  except ValueError:delay=0
  if delay>time.time()-86400:delay=max(0,delay-time.time())
  if r.status_code==429 or(r.headers.get('X-Ratelimit-Remaining')=='0'and delay>0):w.put(pk,{'until':time.time()+max(delay,60)+3,'basis':'provider_header'})
  if r.status_code==429:continue
  if not r.ok:raise RuntimeError('Cohort read HTTP '+str(r.status_code))
  return r.json()
 raise RuntimeError('Cohort quota pending')
def cohort():
 oo=raw('statistics-api.wildberries.ru','/api/v1/supplier/orders',params={'dateFrom':START+'T00:00:00','flag':0})
 ss=raw('statistics-api.wildberries.ru','/api/v1/supplier/sales',params={'dateFrom':START+'T00:00:00','flag':0})
 if not isinstance(oo,list) or not isinstance(ss,list) or len(oo)>=80000 or len(ss)>=80000:raise ValueError('Cohort coverage')
 orders={r['srid']:r for r in oo if r.get('srid') and '2026-10-05'<=str(r.get('date',''))[:10]<='2026-10-28'}
 sales={}
 for r in ss:
  sr=r.get('srid')
  if sr not in orders:continue
  if sr not in sales or str(r.get('date',''))>str(sales[sr].get('date','')):sales[sr]=r
 out=collections.defaultdict(collections.Counter)
 for sr,r in orders.items():
  v=out[(int(r.get('nmId',r.get('nmID',0))),r.get('supplierArticle',''))];v['ordered']+=1
  sale=sales.get(sr)
  if sale and str(sale.get('saleID','')).startswith('S'):v['paid']+=1;v['closed']+=1
  elif sale and str(sale.get('saleID','')).startswith('R'):v['returned']+=1;v['closed']+=1
  elif r.get('isCancel'):v['cancelled']+=1;v['closed']+=1
  else:v['unresolved']+=1
 return {'cohort_from':'2026-10-05','cohort_to':'2026-10-28','observed_at':w.stamp(),'rows':[{'nm':k[0],'article':k[1],**dict(v)} for k,v in out.items()]}

try:
 parent=w.get('ooo_agent:morning:2026-11-06:evidence')
 if parent['sources']['cohort']['status']!='unavailable':raise RuntimeError('No missing cohort to continue')
 value=cohort()
 w.state.update(status='finished',data=value,observed_at=w.stamp(),wb_writes=0);w.save()
except Exception as e:
 w.state.update(status='unavailable',error=str(e)if isinstance(e,(RuntimeError,ValueError,PermissionError))else type(e).__name__);w.save()
print('Read-only cohort continuation saved privately')
