"""Morning OOO evidence only: no WB mutations and no delivery."""
import os,json,time,hashlib,datetime,requests
import ooo_owner_apply_all_20261102 as w
w.KEY='ooo_agent:morning:2026-11-03:evidence'
w.state={'status':'collecting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':w.stamp(),'steps':{},'sources':{}}
def scope():
 a=w.get(w.ROOT+':authorization')
 if not a or a.get('cabinet')!='token_1' or a.get('plan_sha256')!=w.HASH:raise PermissionError('OOO identity scope')
 return a
w.authorize=scope
if not w.claim(w.state):print('Existing morning collection preserved');raise SystemExit(0)
ids=[39605579,39605581,39605582,40385586]+[int(k) for k in w.get(w.ROOT+':apply_all')['new_campaigns']]
def read(label,fn):
 try:w.state['sources'][label]={'status':'complete','data':fn(),'observed_at':w.stamp()}
 except Exception as e:w.state['sources'][label]={'status':'unavailable','error':str(e) if isinstance(e,(RuntimeError,ValueError,PermissionError)) else type(e).__name__}
 w.save()
def fullstats():
 path='/adv/v3/fullstats'
 pk='wb-pause:'+hashlib.sha256((w.TOKEN+w.HOST+path).encode()).hexdigest()
 if float((w.get(pk) or {}).get('until',0))>time.time():raise RuntimeError('Provider cooldown, no request sent')
 r=requests.get('https://'+w.HOST+path,params={'ids':','.join(map(str,ids)),'beginDate':'2026-10-31','endDate':'2026-11-02'},headers={'Authorization':w.TOKEN},timeout=(10,60),allow_redirects=False)
 if r.status_code==429:
  raw=r.headers.get('Retry-After') or r.headers.get('X-Ratelimit-Retry') or r.headers.get('X-Ratelimit-Reset') or '3600'
  try:wait=float(raw)
  except ValueError:wait=3600
  w.put(pk,{'until':time.time()+wait+3,'basis':'provider_header'})
 if not r.ok:raise RuntimeError('Native fullstats HTTP '+str(r.status_code)+' '+r.text[:1000])
 j=r.json()
 if not isinstance(j,list):raise RuntimeError('Statistics schema invalid')
 return j
read('fullstats',fullstats)
read('budgets',lambda:w.budget(ids))
read('configurations',lambda:w.configs(ids))
if w.state['sources']['fullstats']['status']!='complete':
 try:
  from analytics.mpstats_probe import discover,unpack_tool,sanitize
  def extra(call,checks,seen):
   def tool(name,args):return sanitize(unpack_tool(call('tools/call',{'name':name,'arguments':args})))
   cabinets=tool('wbbidder_cabinets',{})
   if not any(r.get('id')==913194 and r.get('name')=='Киргизия VESCHI' for r in cabinets.get('data',{}).get('data',[])):raise RuntimeError('Bidder identity mismatch')
   catalog=tool('wbbidder_campaigns',{'tokens':[913194],'d1':'2026-10-31','d2':'2026-11-02','report':'stats','limit':100,'start_row':0})
   w.state['sources']['mpstats_catalog']={'status':'complete','data':catalog,'observed_at':w.stamp()};w.save()
   mapping={int(r['wb_id']):int(r['id']) for r in catalog.get('data',{}).get('data',[])}
   for cid in ids:
    if cid not in mapping:continue
    for report in ('days','products'):
     value=tool('wbbidder_campaign_stats',{'campaign_id':mapping[cid],'d1':'2026-10-31','d2':'2026-11-02','report':report,'zone':'all'})
     w.state['sources']['mpstats_'+str(cid)+'_'+report]={'status':'complete','data':value,'observed_at':w.stamp()};w.save()
   return {'read_only':True}
  result=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=extra)
  w.state['mpstats_result']={'status':result.get('status'),'retry_after':result.get('retry_after')}
 except Exception as e:w.state['mpstats_error']=str(e) if isinstance(e,(RuntimeError,ValueError)) else type(e).__name__
w.state.update(status='finished',finished_at=w.stamp());w.save()
print('Morning OOO read-only sources collected privately')
