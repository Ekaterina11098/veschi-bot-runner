"""One exact owner-approved membership deletion. No other WB mutations or Telegram."""
import os,json,time,hashlib,datetime,base64,copy,requests
from china_codex_cloud import DB,stamp
ROOT='ooo_agent:exclude143:2026-11-06:v1'
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def projection(c):return {k:copy.deepcopy(c.get(k))for k in ['id','status','currency','bid_type','settings','restrictions']}|{'nm_settings':sorted(copy.deepcopy(c['nm_settings']),key=lambda n:n['nm_id'])}
def expected_after(before,nm):
 e=copy.deepcopy(before);e['nm_settings']=[n for n in e['nm_settings']if n['nm_id']!=nm];return e
def run():
 db=DB();a=db.get(ROOT+':authorization')or{};m=a.get('manifest')or{}
 def scope():
  if a.get('status')!='approved'or a.get('manifest_sha256')!=digest(m)or m.get('cabinet')!='token_1'or m.get('kind')!='exclude_one_sku'or m.get('allowed_other_changes')!=[]:raise PermissionError('Exact isolated approval required')
  if datetime.datetime.now(datetime.timezone.utc)>=datetime.datetime.fromisoformat(a['expires_at']):raise PermissionError('Dated authorization expired')
 scope()
 if db.get(ROOT+':execution'):print('Existing execution retained; no replay');return
 token=os.environ['WB_TOKEN_1'];cl=json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='));ident=db.api('GET','analytics_snapshots',{'cabinet':'eq.token_1','source':'eq.seller_identity','status':'eq.complete','select':'payload','limit':100})
 if cl.get('exp',0)<time.time()or cl.get('t')is not False or int(cl.get('s',0))&(1<<30) or not cl.get('sid')or{r['payload'].get('sid')for r in ident}!={cl['sid']}:raise PermissionError('OOO seller mismatch')
 source=db.get(a['baseline_key'])or{};entry=source.get('sources',{}).get('configurations')or{}
 if source.get('status')!='finished'or entry.get('status')!='complete'or time.time()-datetime.datetime.fromisoformat(entry['observed_at']).timestamp()>7200:raise RuntimeError('Fresh read baseline required')
 cid=m['campaign_id'];nm=m['nm_id'];before=next(c for c in entry['data']['adverts']if c['id']==cid)
 if before['currency']!='KGS'or before['status']!=m['status_before']or before['bid_type']!='manual'or before['settings']['payment_type']!='cpc'or before['restrictions'].get('can_change_nms')is not True:raise RuntimeError('Campaign baseline mismatch')
 if len(before['nm_settings'])<2 or len([n for n in before['nm_settings']if n['nm_id']==nm])!=1:raise RuntimeError('Membership baseline mismatch')
 state={'status':'ready','run_id':os.environ['GITHUB_RUN_ID'],'started_at':stamp(),'manifest':m,'manifest_sha256':digest(m),'before':before,'baseline_at':entry['observed_at'],'steps':{},'telegram_calls':0,'model_calls':0};db.once(ROOT+':execution',state)
 def save():db.update(ROOT+':execution',state)
 def pausekey(path):return'wb-pause:'+hashlib.sha256((token+'advert-api.wildberries.ru'+path).encode()).hexdigest()
 def wait(path):
  key=pausekey(path);until=float((db.get(key)or{}).get('until',0))
  if until>time.time():state.update(status='accepted_waiting_readback'if state['steps'].get('exclude_one',{}).get('status')=='accepted'else'waiting_provider',waiting_path=path,resume_after=datetime.datetime.fromtimestamp(until,datetime.timezone.utc).isoformat());save()
  while time.time()<until:scope();time.sleep(min(30,max(.2,until-time.time())))
 def send(method,path,body=None,params=None):
  if(method,path)not in{('PATCH','/adv/v0/auction/nms'),('GET','/api/advert/v2/adverts')}:raise PermissionError('Endpoint boundary')
  wait(path);scope();r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':token},json=body,params=params,timeout=(10,90),allow_redirects=False)
  raw=r.headers.get('Retry-After')or r.headers.get('X-Ratelimit-Retry')or r.headers.get('X-Ratelimit-Reset')
  try:d=float(raw or 0)
  except ValueError:d=0
  if d>time.time()-86400:d=max(0,d-time.time())
  if r.status_code==429 or(r.headers.get('X-Ratelimit-Remaining')=='0'and d>0):
   key=pausekey(path);old=db.get(key)or{};value={'until':max(float(old.get('until',0)),time.time()+max(d,60)+3),'basis':'provider_header'};db.update(key,value)if old else db.once(key,value)
  return r
 try:
  body={'nms':[{'advert_id':cid,'nms':{'add':[],'delete':[nm]}}]}
  for attempt in range(2):
   state['steps']['exclude_one']={'status':'submitting','method':'PATCH','path':'/adv/v0/auction/nms','body':body,'submitted_at':stamp(),'attempt':attempt+1};save()
   try:r=send('PATCH','/adv/v0/auction/nms',body)
   except requests.RequestException:
    state['steps']['exclude_one'].update(status='uncertain',observed_at=stamp());save();raise RuntimeError('Write outcome unknown; no blind retry')from None
   if r.status_code==429:state['steps']['exclude_one'].update(status='rejected_429');save();continue
   if not 200<=r.status_code<300:state['steps']['exclude_one'].update(status='rejected',http_status=r.status_code);save();raise RuntimeError('Deletion rejected by WB')
   state['steps']['exclude_one'].update(status='accepted',accepted_at=stamp(),http_status=r.status_code,response_sha256=hashlib.sha256(r.content).hexdigest());state.update(status='accepted_waiting_readback',accepted_at=stamp());save();break
  else:raise RuntimeError('Known rejection retained; no new continuation created')
  # Accepted PATCH is never issued again. Only this same job continues complete GET readback.
  for attempt in range(2):
   r=send('GET','/api/advert/v2/adverts',params={'ids':cid})
   if r.status_code==429:continue
   if r.status_code!=200:raise RuntimeError('Readback unavailable; accepted write not repeated')
   after=next(c for c in r.json()['adverts']if c['id']==cid)
   if projection(after)!=projection(expected_after(before,nm)):raise RuntimeError('Unexpected membership, bid, status or setting readback')
   state.update(status='verified',after=after,verified_at=stamp(),remaining_sku_count=len(after['nm_settings']));state.pop('resume_after',None);state.pop('waiting_path',None);save();print('Exact deletion verified; status and all remaining members/bids preserved');return
  raise RuntimeError('Readback quota pending; accepted write retained')
 except Exception as e:state.update(status='attention',error_type=type(e).__name__,safe_error=str(e)if isinstance(e,(RuntimeError,PermissionError))else None,observed_at=stamp());save();print('Stopped; private receipt retained; no automatic write replay')
if __name__=='__main__':run()

