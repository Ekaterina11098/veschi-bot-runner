"""One dated private owner manifest. No deposits, prices, schedules or Telegram."""
import os,json,time,hashlib,datetime,base64,copy,requests
from china_codex_cloud import DB,stamp
ROOT='ooo_agent:midday_apply:2026-11-06:v1'
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def projection(c):return {k:copy.deepcopy(c.get(k))for k in ['id','status','currency','bid_type','settings','restrictions']}|{'nm_settings':sorted(copy.deepcopy(c['nm_settings']),key=lambda n:n['nm_id'])}
def run():
 db=DB();a=db.get(ROOT+':authorization')or{};m=a.get('manifest')or{}
 def scope():
  fresh=db.get(ROOT+':authorization')or{}
  if fresh!=a or a.get('status')!='approved'or a.get('manifest_sha256')!=digest(m)or m.get('cabinet')!='token_1'or m.get('currency')!='KGS'or m.get('other_changes')!=[]:raise PermissionError('Exact dated owner authorization required')
  if datetime.datetime.now(datetime.timezone.utc)>=datetime.datetime.fromisoformat(a['expires_at']):raise PermissionError('Authorization expired')
 scope()
 prior=db.get(ROOT+':execution')
 recovering=bool(prior and prior.get('status')=='attention'and prior.get('safe_error')=='Exact cache update readback mismatch'and prior.get('steps')=={}and prior.get('before')and time.time()-datetime.datetime.fromisoformat(prior['baseline_observed_at']).timestamp()<3600)
 if prior and not recovering:print('Existing receipt retained; no replay');return
 token=os.environ['WB_TOKEN_1'];cl=json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='));ident=db.api('GET','analytics_snapshots',{'cabinet':'eq.token_1','source':'eq.seller_identity','status':'eq.complete','select':'payload','limit':100})
 if cl.get('exp',0)<time.time()or cl.get('t')is not False or int(cl.get('s',0))&(1<<30)or not cl.get('sid')or{r['payload'].get('sid')for r in ident}!={cl['sid']}:raise PermissionError('OOO seller mismatch')
 state={'status':'starting','run_id':os.environ['GITHUB_RUN_ID'],'started_at':stamp(),'manifest':m,'manifest_sha256':digest(m),'steps':{},'model_calls':0,'telegram_calls':0}
 if recovering:
  state=prior;state.update(status='recovering_before_writes',previous_run_id=state['run_id'],run_id=os.environ['GITHUB_RUN_ID']);state.pop('safe_error',None)
 else:db.once(ROOT+':execution',state)
 def save():db.update(ROOT+':execution',json.loads(json.dumps(state)))
 def req(method,path,body=None,params=None,step=None):
  allowed={('GET','/api/advert/v2/adverts'),('PATCH','/adv/v0/auction/nms'),('PATCH','/api/advert/v1/bids'),('GET','/adv/v0/start'),('GET','/adv/v0/pause')}
  if(method,path)not in allowed:raise PermissionError('Endpoint scope')
  if step and step in state['steps']:raise RuntimeError('Step replay refused')
  key='wb-pause:'+hashlib.sha256((token+'advert-api.wildberries.ru'+path).encode()).hexdigest()
  for attempt in range(2):
   while True:
    until=float((db.get(key)or{}).get('until',0))
    if until<=time.time():break
    state.update(status='waiting_shared_quota',waiting_path=path,resume_after=datetime.datetime.fromtimestamp(until,datetime.timezone.utc).isoformat());save();scope();time.sleep(min(30,max(.2,until-time.time())))
   scope()
   if step:state['steps'][step]={'status':'submitting','method':method,'path':path,'body':body,'params':params,'submitted_at':stamp()};save()
   try:r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':token},json=body,params=params,timeout=(10,90),allow_redirects=False)
   except requests.RequestException:
    if step:state['steps'][step]['status']='uncertain';save()
    raise RuntimeError('Transport outcome unknown; never replay')from None
   raw=r.headers.get('Retry-After')or r.headers.get('X-Ratelimit-Retry')or r.headers.get('X-Ratelimit-Reset')
   try:d=float(raw or 0)
   except ValueError:d=0
   if d>time.time()-86400:d=max(0,d-time.time())
   if r.status_code==429 or(r.headers.get('X-Ratelimit-Remaining')=='0'and d>0):
    old=db.get(key)or{};v={'until':max(float(old.get('until',0)),time.time()+max(d,60)+3),'basis':'provider_header'};db.update(key,v)if old else db.once(key,v)
   if r.status_code==429:
    if step:state['steps'][step]['status']='rejected_429';save()
    continue
   if not 200<=r.status_code<300:
    if step:state['steps'][step].update(status='rejected',http_status=r.status_code);save()
    raise RuntimeError('WB HTTP '+str(r.status_code)+' '+path)
   value=r.json()if r.content else{}
   if step:state['steps'][step].update(status='accepted',http_status=r.status_code,response=value,accepted_at=stamp());save()
   return value
  raise RuntimeError('Explicit429 persisted; no new executor')
 def configs():
  rows=req('GET','/api/advert/v2/adverts',params={'ids':','.join(map(str,ids))})['adverts'];out={c['id']:c for c in rows}
  if set(out)!=set(ids):raise RuntimeError('Incomplete configuration coverage')
  return out
 try:
  ids=sorted(set(x['cid']for x in m['actions'])|{39605581});before={int(k):v for k,v in prior['before'].items()}if recovering else configs();state.update(before=before,baseline_observed_at=prior['baseline_observed_at']if recovering else stamp());save();expected=copy.deepcopy(before)
  members={};bids={};statuses=[]
  for cid,c in before.items():
   if c['currency']!='KGS'or c['status']not in[9,11]or c['bid_type']!='manual'or c['settings']['payment_type']!='cpc':raise RuntimeError('Unsupported current campaign')
  # Prior accepted exclusion is only observed here, never repeated by this manifest.
  state['prior_143_membership_absent']=all(n['nm_id']!=851316021 for n in before[39605581]['nm_settings']);save()
  for x in m['actions']:
   cid=x['cid'];c=before[cid];e=expected[cid];kind=x['kind'];nm=x.get('nm');n=next((n for n in c['nm_settings']if n['nm_id']==nm),None)
   if kind=='exclude_sku':
    if n is None:state.setdefault('already_satisfied',[]).append(x);continue
    if c['restrictions'].get('can_change_nms')is not True:raise RuntimeError('Membership locked')
    members.setdefault(cid,{'add':[],'delete':[]})['delete'].append(nm);e['nm_settings']=[n for n in e['nm_settings']if n['nm_id']!=nm]
   elif kind in['reduce_bid','add_sku']:
    p=x['placement'];target=x['to_minor']
    if not c['settings']['placements'].get(p)or target<325:raise RuntimeError('Placement/minimum mismatch')
    if kind=='add_sku'and n is None:
     if c['restrictions'].get('can_change_nms')is not True:raise RuntimeError('Membership locked')
     members.setdefault(cid,{'add':[],'delete':[]})['add'].append(nm)
    elif n is None:raise RuntimeError('Bid member missing')
    elif n['bids_kopecks'].get(p)==target:state.setdefault('already_satisfied',[]).append(x);continue
    elif kind=='add_sku'or n['bids_kopecks'].get(p)!=x['from_minor']:raise RuntimeError('Current bid differs from approved transition')
    bids.setdefault(cid,[]).append({'nm_id':nm,'placement':p,'bid_kopecks':target})
    if n:next(n for n in e['nm_settings']if n['nm_id']==nm)['bids_kopecks'][p]=target
   elif kind in['resume_campaign','pause_campaign']:
    target=9 if kind=='resume_campaign'else 11;e['status']=target
    if c['status']==target:state.setdefault('already_satisfied',[]).append(x)
    else:statuses.append((cid,target))
   else:raise PermissionError('Unknown action kind')
  if any(not c['nm_settings']for c in expected.values()):raise RuntimeError('Would empty campaign')
  state.update(expected=expected,prepared_memberships=members,prepared_bids=bids,prepared_statuses=statuses);save()
  # Stop the specifically approved campaign first. No starts beyond exact approved umbrella.
  for cid,target in statuses:
   if target==11:req('GET','/adv/v0/pause',params={'id':cid},step='pause_'+str(cid))
  if members:req('PATCH','/adv/v0/auction/nms',{'nms':[{'advert_id':cid,'nms':v}for cid,v in members.items()]},step='memberships')
  if bids:req('PATCH','/api/advert/v1/bids',{'bids':[{'advert_id':cid,'nm_bids':v}for cid,v in bids.items()]},step='bids')
  for cid,target in statuses:
   if target==9:req('GET','/adv/v0/start',params={'id':cid},step='start_'+str(cid))
  state.update(status='accepted_waiting_readback',accepted_at=stamp());save();after=configs();state.update(after=after,readback_at=stamp());save()
  for cid,e in expected.items():
   actual=after[cid];oldids={n['nm_id']for n in before[cid]['nm_settings']};adds=set(members.get(cid,{}).get('add',[]))
   wanted={n['nm_id']for n in e['nm_settings']}|adds
   if {n['nm_id']for n in actual['nm_settings']}!=wanted:raise RuntimeError('Membership readback mismatch')
   for k in['id','status','currency','bid_type','settings','restrictions']:
    if actual.get(k)!=e.get(k):raise RuntimeError('Concurrent campaign drift: '+str(cid)+' '+k)
   for n in e['nm_settings']:
    if next(v for v in actual['nm_settings']if v['nm_id']==n['nm_id'])!=n:raise RuntimeError('Unapproved SKU/bid difference')
   for b in bids.get(cid,[]):
    if next(n for n in actual['nm_settings']if n['nm_id']==b['nm_id'])['bids_kopecks'].get(b['placement'])!=b['bid_kopecks']:raise RuntimeError('Exact added bid not verified')
  state.update(status='verified',verified_at=stamp());state.pop('resume_after',None);state.pop('waiting_path',None);save();print('Exact approved manifest verified; no deposits/prices/TG')
 except Exception as e:
  state.update(status='attention',safe_error=str(e)if isinstance(e,(RuntimeError,PermissionError))else type(e).__name__,observed_at=stamp());save();print('Stopped; private receipt saved; no blind replay')
if __name__=='__main__':
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner'or os.environ.get('GITHUB_REF')!='refs/heads/main':raise PermissionError('Expected repository main')
 run()

