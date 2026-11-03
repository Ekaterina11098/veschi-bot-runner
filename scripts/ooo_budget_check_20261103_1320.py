"""Read-only campaign balances and statistics, requested by owner."""
import os,time,hashlib,datetime,requests
import ooo_owner_apply_all_20261102 as w
w.KEY='ooo_agent:budget_check:2026-11-03:1320'
w.state={'status':'collecting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':w.stamp(),'steps':{},'sources':{}}
def scope():
 a=w.get(w.ROOT+':authorization')
 if not a or a.get('cabinet')!='token_1' or a.get('plan_sha256')!=w.HASH:raise PermissionError('Cabinet scope')
 return a
w.authorize=scope
if not w.claim(w.state):raise SystemExit('Existing collection preserved')
ids=[39605579,39605581,39605582,40385586,41515989,41516310,41516903,41517233,41517533]
def read(label,fn):
 try:w.state['sources'][label]={'status':'complete','data':fn(),'observed_at':w.stamp()}
 except Exception as e:w.state['sources'][label]={'status':'unavailable','error':str(e)[:1000]}
 w.save()
read('budgets',lambda:w.budget(ids))
def stats():
 host='advert-api.wildberries.ru';path='/adv/v3/fullstats'
 pk='wb-pause:'+hashlib.sha256((w.TOKEN+host+path).encode()).hexdigest()
 for attempt in range(3):
  w.wait_until(float((w.get(pk) or {}).get('until',0)),path)
  scope()
  r=requests.get('https://'+host+path,headers={'Authorization':w.TOKEN},params={'ids':','.join(map(str,ids)),'beginDate':'2026-10-31','endDate':'2026-11-03'},timeout=(10,90),allow_redirects=False)
  delay=r.headers.get('Retry-After') or r.headers.get('X-Ratelimit-Retry') or r.headers.get('X-Ratelimit-Reset')
  try:seconds=float(delay or 0)
  except ValueError:seconds=0
  if seconds>time.time()-86400:seconds=max(0,seconds-time.time())
  if r.status_code==429 or (r.headers.get('X-Ratelimit-Remaining')=='0' and seconds>0):
   w.put(pk,{'until':time.time()+max(seconds,60)+3,'basis':'provider_header'})
  if r.status_code==429:continue
  r.raise_for_status()
  return r.json()
 raise RuntimeError('Statistics quota exhausted')
read('advertising',stats)
w.state.update(status='finished',finished_at=w.stamp());w.save()
print('Read-only evidence stored privately')
