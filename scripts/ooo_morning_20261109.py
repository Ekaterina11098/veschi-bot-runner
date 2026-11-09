"""Owner-requested OOO sales decline diagnosis. All marketplace endpoints read-only."""
import os,json,time,datetime,hashlib,collections,requests,base64
import ooo_owner_apply_all_20261102 as w
w.KEY='ooo_agent:morning:2026-11-09:evidence'
w.state={'status':'collecting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':w.stamp(),'steps':{},'sources':{}}
MSK=datetime.timezone(datetime.timedelta(hours=3));NOW=datetime.datetime.now(MSK);START='2026-10-05'
def scope():
 a=w.get(w.ROOT+':authorization')
 if not a or a.get('cabinet')!='token_1' or a.get('plan_sha256')!=w.HASH:raise PermissionError('OOO scope missing')
 return a
w.authorize=scope
if not w.claim(w.state):print('Existing diagnosis preserved');raise SystemExit(0)
ALLOW={
 ('GET','statistics-api.wildberries.ru','/api/v1/supplier/orders'),
 ('GET','statistics-api.wildberries.ru','/api/v1/supplier/sales'),
 ('GET','discounts-prices-api.wildberries.ru','/api/v2/list/goods/filter'),
 ('POST','seller-analytics-api.wildberries.ru','/api/analytics/v3/sales-funnel/products'),
 ('GET','advert-api.wildberries.ru','/adv/v3/fullstats')}
def raw(host,path,method='GET',params=None,body=None):
 if (method,host,path) not in ALLOW:raise PermissionError('Read-only boundary')
 pk='wb-pause:'+hashlib.sha256((w.TOKEN+host+path).encode()).hexdigest()
 until=float((w.get(pk) or {}).get('until',0))
 if until>time.time():w.wait_until(until,path)
 r=requests.request(method,'https://'+host+path,headers={'Authorization':w.TOKEN},params=params,json=body,timeout=(10,90),allow_redirects=False)
 delay=r.headers.get('Retry-After') or r.headers.get('X-Ratelimit-Retry') or r.headers.get('X-Ratelimit-Reset')
 try:seconds=float(delay) if delay else 0
 except ValueError:seconds=0
 if seconds>time.time()-86400:seconds=max(0,seconds-time.time())
 if r.status_code==429 or (r.headers.get('X-Ratelimit-Remaining')=='0' and seconds>0):
  w.put(pk,{'until':time.time()+max(seconds,60)+3,'basis':'provider_header'})
 if not r.ok:raise RuntimeError('HTTP '+str(r.status_code)+' '+host+path+' '+r.text[:1200])
 return r.json()
def read(label,fn):
 try:w.state['sources'][label]={'status':'complete','data':fn(),'observed_at':w.stamp()}
 except Exception as e:w.state['sources'][label]={'status':'unavailable','error':str(e) if isinstance(e,(RuntimeError,PermissionError,ValueError)) else type(e).__name__}
 w.save()
def transactions(kind):
 data=raw('statistics-api.wildberries.ru','/api/v1/supplier/'+kind,params={'dateFrom':START+'T00:00:00','flag':0})
 if not isinstance(data,list):raise RuntimeError('Transaction schema')
 if len(data)>=80000:raise RuntimeError('Possible transaction truncation; pagination required')
 out=collections.defaultdict(collections.Counter);seen=set()
 for r in data:
  day=str(r.get('date',''))[:10]
  if not START<=day<=NOW.date().isoformat():continue
  rid=r.get('srid') if kind=='orders' else r.get('saleID')
  if not rid:raise RuntimeError('Transaction ID unavailable for deduplication')
  if rid in seen:continue
  seen.add(rid)
  nm=int(r.get('nmId',r.get('nmID',0)));article=r.get('supplierArticle','')
  t=datetime.datetime.fromisoformat(r['date'].replace('Z','+00:00'))
  if t.tzinfo is None:t=t.replace(tzinfo=MSK)
  matched=t.astimezone(MSK).time().replace(tzinfo=None)<=NOW.time().replace(tzinfo=None)
  v=out[(day,nm,article)];v['rows']+=1
  if kind=='orders':
   v['orders']+=1;v['cancellations']+=bool(r.get('isCancel'))
   if matched:v['orders_same_time']+=1;v['cancellations_same_time']+=bool(r.get('isCancel'))
  else:
   isreturn=str(r.get('saleID','')).startswith('R')
   v['returns' if isreturn else 'buyouts']+=1
   if matched:v['returns_same_time' if isreturn else 'buyouts_same_time']+=1
 return {'date_from':START,'date_to':str(NOW.date()),'matched_cutoff_msk':NOW.strftime('%H:%M:%S'),'rows_received':len(data),'unique_rows_used':len(seen),'aggregate':[{'date':k[0],'nm_id':k[1],'article':k[2],**dict(v)} for k,v in out.items()]}

from china_moysklad_read import read_stock
morning=w.get('ooo_agent:morning:2026-11-08:evidence')
assert morning['status']=='finished'
ids=[39605579,39605581,39605582,40385586,41515989,41516310,41516903,41517233,41517533]
read('prices',lambda:raw('discounts-prices-api.wildberries.ru','/api/v2/list/goods/filter',params={'limit':1000,'offset':0}))
goods=w.state['sources']['prices']['data']['data']['listGoods']if w.state['sources']['prices']['status']=='complete'else morning['sources']['prices']['data']['data']['listGoods']
read('moysklad',lambda:read_stock(list(dict.fromkeys(r['vendorCode'] for r in goods))))
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
cached=w.get('ooo_agent:morning:2026-11-06:cohort_retry')
assert cached and cached.get('data')
w.state['sources']['cohort']={'status':'complete','data':cached['data'],'observed_at':cached.get('observed_at',cached['data'].get('observed_at')),'basis':'dated_cache_06.11; no duplicate transaction collection'};w.save()
read('funnel14',lambda:raw('seller-analytics-api.wildberries.ru','/api/analytics/v3/sales-funnel/products','POST',body={'selectedPeriod':{'start':'2026-10-26','end':'2026-11-08'},'pastPeriod':{'start':'2026-10-12','end':'2026-10-25'},'nmIds':[r['nmID']for r in goods],'skipDeletedNm':False,'limit':1000,'offset':0}))
def delta_advertising():
 fresh=raw('advert-api.wildberries.ru','/adv/v3/fullstats',params={'ids':','.join(map(str,ids)),'beginDate':'2026-11-08','endDate':'2026-11-08'})
 if {r['advertId']for r in fresh}!=set(ids)or any(r.get('currency')!='KGS'for r in fresh):raise ValueError('Incomplete advertising coverage/currency')
 prior={r['advertId']:r for r in morning['sources']['advertising14']['data']}
 for r in fresh:
  r['days']=[d for d in prior[r['advertId']]['days']if '2026-10-26'<=d['date'][:10]<'2026-11-08']+r.get('days',[])
 return fresh
read('advertising14',delta_advertising)
read('configurations',lambda:w.configs(ids))
read('budgets',lambda:w.budget(ids))
w.state.update(status='finished',finished_at=w.stamp());w.save()
print('Full OOO read-only sources stored privately')

