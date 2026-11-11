"""One dated intraday snapshot. Only GET count/fullstats; shared provider quota."""
import os,json,time,hashlib,datetime,base64,requests
from china_codex_cloud import DB,stamp
ROOT='ooo_agent:midday:2026-11-11:1500'
IDS=[39605581,39605579,40385586,41515989,41516310,41516903,41517233,41517533,39605582]
def run():
 db=DB();p=db.get(ROOT+':request')or{}
 if p!={'read_only':True,'cabinet':'token_1','day':'2026-11-11','campaign_ids':IDS}:raise PermissionError('Exact dated read request required')
 prior=db.get(ROOT+':read')
 if prior:print('Existing snapshot/collector retained; no duplicate');return
 token=os.environ['WB_TOKEN_1'];cl=json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='));identity=db.api('GET','analytics_snapshots',{'cabinet':'eq.token_1','source':'eq.seller_identity','status':'eq.complete','select':'payload','limit':100})
 if cl.get('exp',0)<=time.time()or cl.get('t')is not False or int(cl.get('s',0))&(1<<30)or not cl.get('sid')or{r['payload'].get('sid')for r in identity}!={cl['sid']}:raise PermissionError('OOO identity mismatch')
 state={'status':'collecting','started_at':stamp(),'run_id':os.environ['GITHUB_RUN_ID'],'wb_writes':0,'model_calls':0,'telegram_calls':0,'steps':{}}
 db.once(ROOT+':read',state)
 def save():db.update(ROOT+':read',state)
 def get(path,params=None):
  if path not in('/adv/v1/promotion/count','/adv/v3/fullstats'):raise PermissionError('Read-only endpoint scope')
  key='wb-pause:'+hashlib.sha256((token+'advert-api.wildberries.ru'+path).encode()).hexdigest()
  for attempt in range(3):
   until=float((db.get(key)or{}).get('until',0))
   while time.time()<until:
    state.update(status='waiting_shared_quota',waiting_path=path,resume_after=datetime.datetime.fromtimestamp(until,datetime.timezone.utc).isoformat());save();time.sleep(min(30,max(.2,until-time.time())))
   r=requests.get('https://advert-api.wildberries.ru'+path,params=params,headers={'Authorization':token},timeout=(10,90),allow_redirects=False)
   raw=r.headers.get('Retry-After')or r.headers.get('X-Ratelimit-Retry')or r.headers.get('X-Ratelimit-Reset')
   try:delay=float(raw or 0)
   except ValueError:delay=0
   if delay>time.time()-86400:delay=max(0,delay-time.time())
   if r.status_code==429 or(r.headers.get('X-Ratelimit-Remaining')=='0'and delay>0):
    pause={'until':max(until,time.time()+max(delay,60)+3),'basis':'provider_header'};db.update(key,pause)if db.get(key)else db.once(key,pause)
   if r.status_code==429:state.update(status='waiting_provider',http_status=429);save();continue
   if r.status_code!=200:raise RuntimeError('Read HTTP '+str(r.status_code)+' '+path)
   return r.json()
  raise RuntimeError('Explicit provider 429 persists; collector stopped safely')
 try:
  counts=get('/adv/v1/promotion/count');statuses={}
  for group in counts.get('adverts',[]):
   for item in group.get('advert_list',[]):statuses[str(item['advertId'])]={'status':group['status'],'type':group['type'],'changeTime':item.get('changeTime')}
  if not set(map(str,IDS))<=set(statuses):raise RuntimeError('Nine campaign status coverage incomplete')
  state.update(current_statuses={str(cid):statuses[str(cid)]for cid in IDS},all_statuses=statuses,statuses_observed_at=stamp());save()
  # All serving, paused and closed campaigns are included in cabinet totals.
  ids=sorted(set(IDS)|{int(cid)for cid,v in statuses.items()if v['status']in(7,9,11)})
  data=[]
  for i in range(0,len(ids),50):
   batch=ids[i:i+50];rows=get('/adv/v3/fullstats',{'ids':','.join(map(str,batch)),'beginDate':p['day'],'endDate':p['day']})
   if not isinstance(rows,list)or any(c.get('currency')!='KGS'or c['advertId']not in batch for c in rows):raise RuntimeError('Currency or campaign response mismatch')
   state['steps'][str(i)]={'status':'complete','requested_ids':batch,'returned_ids':[c['advertId']for c in rows],'observed_at':stamp()};data+=rows;state['data']=data;save()
  if not set(IDS)<={c['advertId']for c in data}:raise RuntimeError('Required campaign statistics missing; not zero')
  state.update(status='complete',day=p['day'],data=data,requested_ids=ids,missing_ids=sorted(set(ids)-{c['advertId']for c in data}),observed_at=stamp());state.pop('resume_after',None);save();print('Dated intraday snapshot complete; no WB writes/model/delivery')
 except Exception as e:state.update(status='attention',safe_error=str(e)if isinstance(e,RuntimeError)else type(e).__name__);save();print('Read stopped; exact private state retained')
if __name__=='__main__':run()