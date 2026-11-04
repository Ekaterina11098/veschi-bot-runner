"""Owner-requested read-only followup: three exact SKUs, no marketplace writes."""
import os,time,json,hashlib,datetime,collections,requests
import ooo_owner_apply_all_20261102 as w
w.KEY='ooo_agent:three_followup:2026-11-04:2127'
w.state={'status':'collecting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':w.stamp(),'steps':{},'sources':{},'wb_writes':0}
IDS={1124312584,1124312594,851316021};MSK=datetime.timezone(datetime.timedelta(hours=3))
def scope():
 e=w.get('ooo_agent:urgent_actions:2026-11-04:v1:execution')or{}
 if e.get('status')!='verified'or e.get('manifest',{}).get('cabinet')!='token_1':raise PermissionError('Verified OOO baseline required')
 return e
w.authorize=scope
if not w.claim(w.state):raise SystemExit('Existing read retained')
def raw(host,path,params):
 if(host,path)not in{('advert-api.wildberries.ru','/adv/v3/fullstats'),('statistics-api.wildberries.ru','/api/v1/supplier/orders'),('discounts-prices-api.wildberries.ru','/api/v2/list/goods/filter')}:raise PermissionError('Read boundary')
 pk='wb-pause:'+hashlib.sha256((w.TOKEN+host+path).encode()).hexdigest()
 for _ in range(3):
  w.wait_until(float((w.get(pk)or{}).get('until',0)),path);scope()
  r=requests.get('https://'+host+path,headers={'Authorization':w.TOKEN},params=params,timeout=(10,90),allow_redirects=False)
  rawdelay=r.headers.get('Retry-After')or r.headers.get('X-Ratelimit-Retry')or r.headers.get('X-Ratelimit-Reset')
  try:delay=float(rawdelay or 0)
  except ValueError:delay=0
  if delay>time.time()-86400:delay=max(0,delay-time.time())
  if r.status_code==429 or(r.headers.get('X-Ratelimit-Remaining')=='0'and delay>0):w.put(pk,{'until':time.time()+max(delay,60)+3,'basis':'provider_header'})
  if r.status_code==429:continue
  if not r.ok:raise RuntimeError('Read HTTP '+str(r.status_code)+' '+path)
  return r.json()
 raise RuntimeError('Shared quota pending')
def read(label,fn):
 try:w.state['sources'][label]={'status':'complete','data':fn(),'observed_at':w.stamp()}
 except Exception as e:w.state['sources'][label]={'status':'unavailable','error':str(e)if isinstance(e,(RuntimeError,ValueError,PermissionError))else type(e).__name__}
 w.save()
def orders():
 data=raw('statistics-api.wildberries.ru','/api/v1/supplier/orders',{'dateFrom':'2026-11-04','flag':1})
 if not isinstance(data,list)or len(data)>=80000:raise RuntimeError('Order coverage unknown')
 e=scope();ad=datetime.datetime.fromisoformat(e['steps']['bids_594_59']['accepted_at']);price=datetime.datetime.fromisoformat(e['steps']['price_143']['accepted_at'])
 out={str(nm):{'before':{'orders':0,'cancelled':0},'after':{'orders':0,'cancelled':0}}for nm in IDS};seen=set()
 for r in data:
  nm=int(r.get('nmId',r.get('nmID',0)))
  if nm not in IDS:continue
  sid=r.get('srid')
  if not sid:raise RuntimeError('Order identity missing')
  if sid in seen:continue
  seen.add(sid);t=datetime.datetime.fromisoformat(r['date'].replace('Z','+00:00'))
  if t.tzinfo is None:t=t.replace(tzinfo=MSK)
  if t.astimezone(MSK).date().isoformat()!='2026-11-04':continue
  p='after'if t>=(price if nm==851316021 else ad)else'before';v=out[str(nm)][p];v['orders']+=1;v['cancelled']+=bool(r.get('isCancel'))
 return {'rows_received':len(data),'skus':out,'advert_change_at':ad.isoformat(),'price_upload_at':price.isoformat(),'note':'General orders by event timestamp, not advertising attribution'}
scope()
read('advertising',lambda:raw('advert-api.wildberries.ru','/adv/v3/fullstats',{'ids':'39605581,40385586,41516310','beginDate':'2026-11-04','endDate':'2026-11-04'}))
read('orders',orders)
read('price143',lambda:raw('discounts-prices-api.wildberries.ru','/api/v2/list/goods/filter',{'limit':1000,'offset':0,'filterNmID':851316021}))
w.state.update(status='finished',finished_at=w.stamp());w.save()
print('Read-only three SKU followup saved privately')

