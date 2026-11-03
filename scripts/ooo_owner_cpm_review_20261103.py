"""Owner-requested paused CPM review. Read-only fullstats and config."""
import os,time,json,hashlib,requests
import ooo_owner_apply_all_20261102 as w
w.KEY='ooo_agent:cpm_review:2026-11-03:evidence'
w.state={'status':'collecting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':w.stamp(),'steps':{}}
def scope():
 a=w.get(w.ROOT+':authorization')
 if not a or a.get('cabinet')!='token_1' or a.get('plan_sha256')!=w.HASH:raise PermissionError('OOO scope')
 return a
w.authorize=scope
if not w.claim(w.state):print('Existing CPM review preserved');raise SystemExit(0)
try:
 path='/adv/v3/fullstats';key='wb-pause:'+hashlib.sha256((w.TOKEN+w.HOST+path).encode()).hexdigest()
 wait=float((w.get(key) or {}).get('until',0))
 w.wait_until(wait,path)
 r=requests.get('https://'+w.HOST+path,params={'ids':'39605582','beginDate':'2026-10-20','endDate':'2026-11-03'},headers={'Authorization':w.TOKEN},timeout=(10,60),allow_redirects=False)
 if r.status_code==429:
  raw=r.headers.get('Retry-After') or r.headers.get('X-Ratelimit-Retry') or r.headers.get('X-Ratelimit-Reset') or '3600'
  try:seconds=float(raw)
  except ValueError:seconds=3600
  w.put(key,{'until':time.time()+seconds+3,'basis':'provider_header'})
 if not r.ok:raise RuntimeError('Native fullstats HTTP '+str(r.status_code)+' '+r.text[:1000])
 w.state['statistics']=r.json();w.state['stats_observed_at']=w.stamp();w.save()
 w.state['configuration']=w.configs([39605582])[39605582];w.save()
 w.state['budget_kgs']=w.budget([39605582])[39605582]
 w.state.update(status='complete',observed_at=w.stamp());w.save()
except Exception as e:
 w.state.update(status='attention',error=str(e) if isinstance(e,(RuntimeError,ValueError,PermissionError)) else type(e).__name__);w.save()
print(json.dumps({'status':w.state['status']}))
