"""Owner-requested OOO sales decline diagnosis. All marketplace endpoints read-only."""
import os,json,time,datetime,hashlib,collections,requests,base64
import ooo_owner_apply_all_20261102 as w
w.KEY='ooo_agent:full_review:2026-11-04:advertising_retry'
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


parent=w.get('ooo_agent:full_review:2026-11-04:evidence')
if parent.get('sources',{}).get('advertising14',{}).get('status')!='unavailable':raise SystemExit('No failed advertising read to continue')
ids=[39605579,39605581,39605582,40385586,41515989,41516310,41516903,41517233,41517533]
for attempt in range(3):
 try:
  w.state['attempt']=attempt+1;w.save()
  value=raw('advert-api.wildberries.ru','/adv/v3/fullstats',params={'ids':','.join(map(str,ids)),'beginDate':'2026-10-21','endDate':'2026-11-03'})
  if not isinstance(value,list) or {r['advertId']for r in value}!=set(ids) or any(r.get('currency')!='KGS'for r in value):raise ValueError('Incomplete KGS campaign set')
  w.state['sources']['advertising14']={'status':'complete','data':value,'observed_at':w.stamp()}
  break
 except RuntimeError as e:
  w.state['last_error']=str(e)[:1000];w.save()
  if 'HTTP 429'not in str(e):raise
else:raise RuntimeError('Statistics retries exhausted')
w.state.update(status='finished',finished_at=w.stamp());w.save()
print('Read-only advertising history stored privately')
