"""One missing-hour OOO advertising read. Cache-first, shared quota, no writes/model/delivery."""
import os,json,time,datetime,hashlib,base64,requests
from china_codex_cloud import DB,stamp
ROOT='ooo_agent:midday:2026-11-07:1500'
def run():
 db=DB();p=db.get(ROOT+':request')or{}
 if p.get('read_only')is not True or p.get('cabinet')!='token_1':raise PermissionError('OOO read request required')
 prior=db.get(ROOT+':read')
 if prior and not(prior.get('status')=='waiting_provider'and prior.get('http_status')==429 and not prior.get('data')):print('Existing completed or ambiguous read retained');return
 token=os.environ['WB_TOKEN_1'];cl=json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='));ids=db.api('GET','analytics_snapshots',{'cabinet':'eq.token_1','source':'eq.seller_identity','status':'eq.complete','select':'payload','limit':100})
 if cl.get('exp',0)<time.time()or{r['payload'].get('sid')for r in ids}!={cl.get('sid')}:raise PermissionError('Seller identity mismatch')
 out={'status':'waiting_shared_quota','started_at':stamp(),'run_id':os.environ['GITHUB_RUN_ID'],'previous_read_run':prior.get('run_id')if prior else None,'known_rejected_429_continuation':bool(prior),'wb_writes':0,'model_calls':0,'telegram_calls':0}
 if prior:db.update(ROOT+':read',out)
 else:db.once(ROOT+':read',out)
 status_path='/adv/v1/promotion/count';status_key='wb-pause:'+hashlib.sha256((token+'advert-api.wildberries.ru'+status_path).encode()).hexdigest();status_pause=float((db.get(status_key)or{}).get('until',0))
 if status_pause>time.time():raise RuntimeError('Status read shared quota pending; no bypass')
 sr=requests.get('https://advert-api.wildberries.ru'+status_path,headers={'Authorization':token},timeout=(10,60),allow_redirects=False)
 if sr.status_code!=200:raise RuntimeError('Current status read unavailable')
 statuses={}
 for group in sr.json().get('adverts',[]):
  for item in group.get('advert_list',[]):
   if item['advertId']in p['campaign_ids']:statuses[str(item['advertId'])]={'status':group['status'],'type':group['type'],'changeTime':item.get('changeTime')}
 if set(statuses)!=set(map(str,p['campaign_ids'])):raise ValueError('Current campaign status coverage incomplete')
 out['current_statuses']=statuses;out['statuses_observed_at']=stamp();db.update(ROOT+':read',out)
 path='/adv/v3/fullstats';key='wb-pause:'+hashlib.sha256((token+'advert-api.wildberries.ru'+path).encode()).hexdigest();until=float((db.get(key)or{}).get('until',0))
 if until>time.time():out['resume_after']=datetime.datetime.fromtimestamp(until,datetime.timezone.utc).isoformat();db.update(ROOT+':read',out)
 while time.time()<until:
  if time.time()-datetime.datetime.fromisoformat(out['started_at']).timestamp()>1100:raise RuntimeError('Read wait bound exceeded')
  time.sleep(min(30,max(.2,until-time.time())))
 # Only one request for the missing dated hour. Already prepared full days are not read again.
 r=requests.get('https://advert-api.wildberries.ru'+path,params={'ids':','.join(map(str,p['campaign_ids'])),'beginDate':p['day'],'endDate':p['day']},headers={'Authorization':token},timeout=(10,90),allow_redirects=False)
 raw=r.headers.get('Retry-After')or r.headers.get('X-Ratelimit-Retry')or r.headers.get('X-Ratelimit-Reset')
 try:d=float(raw or 0)
 except ValueError:d=0
 if d>time.time()-86400:d=max(0,d-time.time())
 if r.status_code==429 or(r.headers.get('X-Ratelimit-Remaining')=='0'and d>0):
  v={'until':max(float((db.get(key)or{}).get('until',0)),time.time()+max(d,60)+3),'basis':'provider_header'};db.update(key,v)if db.get(key)else db.once(key,v)
 if r.status_code!=200:out.update(status='waiting_provider'if r.status_code==429 else'error',http_status=r.status_code,observed_at=stamp());db.update(ROOT+':read',out);return
 data=r.json()
 if not isinstance(data,list)or{c['advertId']for c in data}!=set(p['campaign_ids'])or any(c.get('currency')!='KGS'for c in data):raise ValueError('Campaign/currency coverage incomplete')
 out.update(status='complete',data=data,day=p['day'],observed_at=stamp());out.pop('resume_after',None);db.update(ROOT+':read',out);print('Current day all-campaign read complete;no marketplace writes or deliveries')
if __name__=='__main__':run()

