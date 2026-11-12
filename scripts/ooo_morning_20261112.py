"""One complete dated OOO report collection. Read-only WB/MSK; no models or delivery."""
import os,json,time,datetime,hashlib,base64,requests
from china_codex_cloud import DB,stamp
from china_moysklad_read import read_stock
KEY='ooo_agent:morning:2026-11-12:evidence'
IDS=[39605579,39605581,39605582,40385586,41515989,41516310,41516903,41517233,41517533]
def run():
 db=DB()
 if db.get(KEY):print('Existing dated collector/evidence retained');return
 token=os.environ['WB_TOKEN_1'];claim=json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='));ident=db.api('GET','analytics_snapshots',{'cabinet':'eq.token_1','source':'eq.seller_identity','status':'eq.complete','select':'payload','limit':100})
 if claim.get('exp',0)<=time.time()or claim.get('t')is not False or int(claim.get('s',0))&(1<<30)or not claim.get('sid')or{r['payload'].get('sid')for r in ident}!={claim['sid']}:raise PermissionError('OOO seller identity mismatch')
 previous=db.get('ooo_agent:morning:2026-11-11:evidence')or{}
 if previous.get('status')!='finished':raise RuntimeError('Dated previous complete evidence unavailable')
 state={'status':'collecting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':stamp(),'steps':{},'sources':{},'wb_writes':0,'model_calls':0,'telegram_calls':0};db.once(KEY,state)
 def save():db.update(KEY,json.loads(json.dumps(state)))
 allowed={('GET','advert-api.wildberries.ru','/adv/v1/promotion/count'),('GET','advert-api.wildberries.ru','/api/advert/v2/adverts'),('POST','advert-api.wildberries.ru','/api/advert/v2/budget'),('GET','advert-api.wildberries.ru','/adv/v3/fullstats'),('GET','discounts-prices-api.wildberries.ru','/api/v2/list/goods/filter'),('POST','seller-analytics-api.wildberries.ru','/api/analytics/v3/sales-funnel/products')}
 def raw(host,path,method='GET',params=None,body=None):
  if(method,host,path)not in allowed:raise PermissionError('Read-only method boundary')
  key='wb-pause:'+hashlib.sha256((token+host+path).encode()).hexdigest()
  for attempt in range(3):
   until=float((db.get(key)or{}).get('until',0))
   while time.time()<until:
    state.update(status='waiting_provider',waiting_path=path,resume_after=datetime.datetime.fromtimestamp(until,datetime.timezone.utc).isoformat());save();time.sleep(min(30,max(.2,until-time.time())))
   r=requests.request(method,'https://'+host+path,headers={'Authorization':token},params=params,json=body,timeout=(10,90),allow_redirects=False)
   rawdelay=r.headers.get('Retry-After')or r.headers.get('X-Ratelimit-Retry')or r.headers.get('X-Ratelimit-Reset')
   try:delay=float(rawdelay or 0)
   except ValueError:delay=0
   if delay>time.time()-86400:delay=max(0,delay-time.time())
   if r.status_code==429 or(r.headers.get('X-Ratelimit-Remaining')=='0'and delay>0):
    value={'until':max(until,time.time()+max(delay,60)+3),'basis':'provider_header'};db.update(key,value)if db.get(key)else db.once(key,value)
   if r.status_code==429:continue
   if r.status_code!=200:raise RuntimeError('Read HTTP '+str(r.status_code)+' '+path)
   return r.json()
  raise RuntimeError('Provider quota still rejects read; no duplicate collector')
 def read(label,fn):
  try:state['sources'][label]={'status':'complete','data':fn(),'observed_at':stamp()}
  except Exception as e:state['sources'][label]={'status':'unavailable','error':str(e)if isinstance(e,RuntimeError)else type(e).__name__}
  save()
 try:
  read('campaign_list',lambda:raw('advert-api.wildberries.ru','/adv/v1/promotion/count'))
  read('prices',lambda:raw('discounts-prices-api.wildberries.ru','/api/v2/list/goods/filter',params={'limit':1000,'offset':0}))
  goods=state['sources']['prices']['data']['data']['listGoods']
  if len(goods)>=1000:raise RuntimeError('Catalogue may be truncated')
  read('moysklad',lambda:read_stock(list(dict.fromkeys(r['vendorCode']for r in goods))))
  cached=db.get('ooo_agent:morning:2026-11-06:cohort_retry')
  if not cached or not cached.get('data'):raise RuntimeError('Dated mature cohort cache unavailable')
  state['sources']['cohort']={'status':'complete','data':cached['data'],'observed_at':cached.get('observed_at',cached['data'].get('observed_at')),'basis':'dated mature cohort cache; not current fulfilment'};save()
  read('funnel14',lambda:raw('seller-analytics-api.wildberries.ru','/api/analytics/v3/sales-funnel/products','POST',body={'selectedPeriod':{'start':'2026-10-29','end':'2026-11-11'},'pastPeriod':{'start':'2026-10-15','end':'2026-10-28'},'nmIds':[r['nmID']for r in goods],'skipDeletedNm':False,'limit':1000,'offset':0}))
  def advertising():
   listed=state['sources']['campaign_list']['data'];ids=set(IDS)
   for g in listed.get('adverts',[]):
    if g['status']in(7,9,11):ids.update(r['advertId']for r in g.get('advert_list',[]))
   rows=[]
   for i in range(0,len(ids),50):rows+=raw('advert-api.wildberries.ru','/adv/v3/fullstats',params={'ids':','.join(map(str,sorted(ids)[i:i+50])),'beginDate':'2026-11-09','endDate':'2026-11-11'})
   if not set(IDS)<={r['advertId']for r in rows}or any(r.get('currency')!='KGS'for r in rows):raise RuntimeError('Advertising required coverage/currency incomplete')
   state['advertising_coverage']={'requested_ids':sorted(ids),'returned_ids':[r['advertId']for r in rows],'missing_ids_not_zeroed':sorted(ids-{r['advertId']for r in rows}),'fresh_period':['2026-11-09','2026-11-11'],'historical_before_08':'dated previous morning cache, not refreshed'}
   prior={r['advertId']:r for r in previous['sources']['advertising14']['data']}
   for r in rows:r['days']=[d for d in prior.get(r['advertId'],{}).get('days',[])if '2026-10-29'<=d['date'][:10]<'2026-11-09']+r.get('days',[])
   return rows
  read('advertising14',advertising)
  def configurations():
   rows=raw('advert-api.wildberries.ru','/api/advert/v2/adverts',params={'ids':','.join(map(str,IDS))})['adverts']
   if {r['id']for r in rows}!=set(IDS)or any(r.get('currency')!='KGS'for r in rows):raise RuntimeError('Configuration coverage/currency incomplete')
   return {str(r['id']):r for r in rows}
  read('configurations',configurations)
  def budgets():
   rows=raw('advert-api.wildberries.ru','/api/advert/v2/budget','POST',body={'advertIds':IDS})['adverts']
   if {r['advertId']for r in rows}!=set(IDS)or any(r.get('currency')!='KGS'for r in rows):raise RuntimeError('Budget coverage/currency incomplete')
   return {str(r['advertId']):r['total']for r in rows}
  read('budgets',budgets)
  state.update(status='finished',finished_at=stamp());state.pop('resume_after',None);save();print('Dated read-only sources saved privately')
 except Exception as e:state.update(status='attention',safe_error=str(e)if isinstance(e,RuntimeError)else type(e).__name__);save();print('Collector stopped safely; private evidence retained')
if __name__=='__main__':run()