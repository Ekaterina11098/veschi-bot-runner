"""One owner-requested read-only statistics batch for the eight raised SKUs."""
import os,time,hashlib,datetime,requests
import ooo_owner_apply_all_20261102 as w
w.KEY='ooo_agent:eight_raise_followup:2026-11-04:1000'
w.state={'status':'collecting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':w.stamp(),'steps':{},'sources':{},'wb_writes':0}
def scope():
 e=w.get('ooo_agent:approved_actions:2026-11-04:v1:execution')or{}
 if e.get('status')!='verified'or e.get('manifest',{}).get('cabinet')!='token_1':raise PermissionError('Verified OOO execution baseline required')
 return e
w.authorize=scope
if not w.claim(w.state):raise SystemExit('Existing read preserved; no duplicate')
try:
 e=scope();w.state['bid_accepted_at']=e['steps']['raise_eight']['accepted_at'];w.save()
 host='advert-api.wildberries.ru';path='/adv/v3/fullstats'
 pk='wb-pause:'+hashlib.sha256((w.TOKEN+host+path).encode()).hexdigest()
 for attempt in range(3):
  w.wait_until(float((w.get(pk)or{}).get('until',0)),path)
  scope()
  r=requests.get('https://'+host+path,headers={'Authorization':w.TOKEN},params={'ids':'39605579,41516310,41517233','beginDate':'2026-11-03','endDate':'2026-11-04'},timeout=(10,90),allow_redirects=False)
  raw=r.headers.get('Retry-After')or r.headers.get('X-Ratelimit-Retry')or r.headers.get('X-Ratelimit-Reset')
  try:delay=float(raw or 0)
  except ValueError:delay=0
  if delay>time.time()-86400:delay=max(0,delay-time.time())
  if r.status_code==429 or(r.headers.get('X-Ratelimit-Remaining')=='0'and delay>0):w.put(pk,{'until':time.time()+max(delay,60)+3,'basis':'provider_header'})
  if r.status_code==429:continue
  if not r.ok:raise RuntimeError('WB statistics HTTP '+str(r.status_code))
  data=r.json()
  if not isinstance(data,list)or{c['advertId']for c in data}!={39605579,41516310,41517233}or any(c.get('currency')!='KGS'for c in data):raise RuntimeError('Incomplete native KGS campaign set')
  w.state['sources']['advertising']={'status':'complete','data':data,'observed_at':w.stamp(),'period_from':'2026-11-03','period_to':'2026-11-04'}
  w.state.update(status='finished',finished_at=w.stamp());w.save();break
 else:raise RuntimeError('Shared statistics quota persisted')
except Exception as e:
 w.state.update(status='unavailable',error=str(e)if isinstance(e,(RuntimeError,ValueError,PermissionError))else type(e).__name__);w.save()
print('Read-only comparison statistics stored privately')

