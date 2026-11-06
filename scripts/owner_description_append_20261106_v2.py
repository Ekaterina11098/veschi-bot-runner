"""Single owner-authorized description append; all operational payloads stay private."""
import os,json,time,hashlib,base64,copy,requests
from datetime import datetime,timezone,timedelta
from china_cloud_cost_control import Cache,stamp
ROOT='china_agent:description_append:20261106:v2'
EXPECTED='d33a126c559b1e54b72d66a49934d0e1792f1f3390c9967c8c7bafcf34810b93'
HOST='https://content-api.wildberries.ru'
DOC_FIELDS={'id','type','number','productNumber','tradeName','applicant','startDate','endDate','isEndless'}
def sha(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def chars(c):return sorted([{'id':x['id'],'value':x['value']} for x in c['characteristics']],key=lambda x:x['id'])
def projection(c):
 p={k:copy.deepcopy(c[k]) for k in ['nmID','vendorCode','brand','title','description','kizMarked','gtin'] if k in c}
 p['dimensions']={k:c['dimensions'][k] for k in ['length','width','height','weightBrutto'] if k in c.get('dimensions',{})}
 p['characteristics']=chars(c)
 p['sizes']=[{k:s[k] for k in ['chrtID','techSize','wbSize','skus'] if k in s} for s in c['sizes']]
 if 'documents' in c:
  d=c['documents'];p['documents']={k:copy.deepcopy(d[k]) for k in ['excludeDocuments'] if k in d}
  if 'items' in d:p['documents']['items']=[{k:copy.deepcopy(x[k]) for k in DOC_FIELDS if k in x} for x in d['items']]
 return p
def invariant(c):
 p=projection(c);p.pop('description',None)
 p['photos']=c.get('photos');p['video']=c.get('video');p['tags']=c.get('tags');p['imtID']=c.get('imtID');p['subjectID']=c.get('subjectID')
 return p
class Run:
 def __init__(self):
  self.c=Cache();self.token=os.environ['WB_TOKEN_3'];self.m=self.c.get(ROOT+':manifest')
  assert self.m and self.m['item_count']==221 and sha(self.m['items'])==EXPECTED==self.m['items_sha256']
  claims=json.loads(base64.urlsafe_b64decode(self.token.split('.')[1]+'==='))
  assert claims.get('sid')==self.m['expected_sid'] and claims.get('exp',0)>time.time()
  assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner'
  self.items={r['nm_id']:r for r in self.m['items']};self.progress={'status':'preflight','checked_at':stamp(),'items_sha256':EXPECTED,'items':{},'wb_update_requests':0,'telegram_sends':0}
 def save(self):self.progress['checked_at']=stamp();self.c.put(ROOT+':progress',self.progress)
 def read(self,path,body):
  assert path in ['/content/v2/get/cards/list','/content/v2/cards/error/list']
  for attempt in range(3):
   r=requests.post(HOST+path,headers={'Authorization':self.token},json=body,timeout=90,allow_redirects=False)
   if r.status_code!=429:break
   delay=max(7,int(r.headers.get('Retry-After','60')))
   self.c.put(ROOT+':read_cooldown',{'until':(datetime.now(timezone.utc)+timedelta(seconds=delay)).isoformat()})
   if delay>90:raise RuntimeError('WB read cooldown exceeds bounded run')
   time.sleep(delay)
  if not r.ok:raise RuntimeError('WB read HTTP '+str(r.status_code))
  return r.json()
 def catalogue(self):
  result={};cursor={'limit':100};seen=set()
  for page in range(30):
   data=self.read('/content/v2/get/cards/list',{'settings':{'sort':{'ascending':False},'filter':{'withPhoto':-1},'cursor':cursor}})
   cards=data.get('cards');assert isinstance(cards,list)
   for c in cards:
    if c['nmID'] in result:raise RuntimeError('Duplicate catalogue pagination')
    result[c['nmID']]=c
   cur=data.get('cursor',{})
   if len(cards)<100:return result
   marker=(cur.get('updatedAt'),cur.get('nmID'))
   if None in marker or marker in seen:raise RuntimeError('Invalid catalogue cursor')
   seen.add(marker);cursor={'limit':100,'updatedAt':marker[0],'nmID':marker[1]};time.sleep(.8)
  raise RuntimeError('Catalogue pagination limit')
 def preflight(self):
  live=self.catalogue();ready={};backup=[]
  for nm,r in self.items.items():
   st={'article':r['article'],'status':'blocked'};self.progress['items'][str(nm)]=st
   c=live.get(nm)
   if not c:st['reason']='missing_live_card';continue
   if c.get('vendorCode')!=r['article']:st['reason']='article_identity_changed';continue
   if r['article'].startswith(('143-','590-')):st['reason']='owner_hold';continue
   if c.get('description','').endswith('\n\n'+r['addition']):st['status']='already_present';continue
   if sha(c.get('description',''))!=r['original_description_sha']:st['reason']='description_changed_since_approved_workbook';continue
   if c.get('title')!=r['original_title'] or sha(chars(c))!=r['original_characteristics_sha']:st['reason']='title_or_characteristics_changed';continue
   if not c.get('sizes') or any(not s.get('chrtID') or not s.get('skus') for s in c['sizes']):st['reason']='existing_size_identity_incomplete';continue
   if set(c)-{'nmID','imtID','nmUUID','subjectID','subjectName','vendorCode','kizMarked','brand','title','gtin','description','needKiz','photos','video','dimensions','characteristics','sizes','tags','createdAt','updatedAt','documents'}:st['reason']='unknown_card_fields_require_preservation_review';continue
   payload=projection(c);payload['description']=c['description']+'\n\n'+r['addition']
   assert payload['description'].startswith(c['description']) and payload['description'][len(c['description']):]=='\n\n'+r['addition']
   assert {k:v for k,v in payload.items() if k!='description'}=={k:v for k,v in projection(c).items() if k!='description'}
   assert len(payload['description'])<=2000
   st.update(status='ready',old_chars=len(c['description']),new_chars=len(payload['description']))
   ready[nm]={'before':c,'payload':payload};backup.append({'nm_id':nm,'before':c,'payload':payload,'before_sha':sha(c)})
  for n in range(0,len(backup),25):self.c.put(ROOT+':backup:'+str(n//25),{'items':backup[n:n+25],'created_at':stamp()})
  self.progress.update(status='preflight_complete',catalogue_count=len(live));self.save();return ready
 def update(self,nms,ready,label):
  payload=[ready[n]['payload'] for n in nms];key=ROOT+':submission:'+label
  if not self.c.create(key,{'status':'submitting','nm_ids':nms,'payload_sha':sha(payload),'submitted_at':stamp(),'run_id':os.environ['GITHUB_RUN_ID']}):raise RuntimeError('Existing submission; verification required, no blind replay')
  for n in nms:self.progress['items'][str(n)]['status']='submitting'
  self.progress['wb_update_requests']+=1;self.save()
  try:r=requests.post(HOST+'/content/v2/cards/update',headers={'Authorization':self.token},json=payload,timeout=90,allow_redirects=False)
  except requests.RequestException:
   self.c.put(key,{'status':'unknown_transport_outcome','nm_ids':nms});return 'unknown'
  try:body=r.json()
  except ValueError:body={'body_sha':sha(r.text)}
  self.c.put(key,{'status':'response_received','http_status':r.status_code,'response':body,'nm_ids':nms,'received_at':stamp()})
  if r.status_code==429:
   self.c.put(ROOT+':write_cooldown',{'retry_after':r.headers.get('Retry-After'),'observed_at':stamp()})
  accepted=r.status_code==200 and isinstance(body,dict) and body.get('error') is False
  for n in nms:
   st=self.progress['items'][str(n)];st['status']='submitted' if accepted else 'response_requires_verification';st['submission']=label
  self.save();return 'accepted' if accepted else 'rejected'
 def verify(self,nms,ready,attempts=6):
  pending=set(nms)
  for attempt in range(attempts):
   if attempt:time.sleep(25)
   live=self.catalogue()
   for nm in list(pending):
    a=ready[nm];c=live.get(nm);st=self.progress['items'][str(nm)]
    if not c:continue
    if invariant(c)!=invariant(a['before']):
     st.update(status='unexpected_other_field_change',verification_at=stamp());self.c.put(ROOT+':unexpected:'+str(nm),{'before':a['before'],'after':c});self.save();raise RuntimeError('Unchanged-field invariant mismatch; stopped further writes')
    if c.get('description')==a['payload']['description']:
     st.update(status='verified',verification_at=stamp(),original_prefix_preserved=c['description'].startswith(a['before']['description']));pending.remove(nm)
     self.c.put(ROOT+':verified:'+str(nm),{'article':c['vendorCode'],'description_sha':sha(c['description']),'after':c,'verified_at':stamp()})
    elif c.get('description')!=a['before'].get('description'):
     st.update(status='description_mismatch',verification_at=stamp());self.c.put(ROOT+':unexpected:'+str(nm),{'before':a['before'],'intended':a['payload'],'after':c});self.save();raise RuntimeError('Description differs from exact intended append; no further writes')
   self.save()
   if not pending:return True
  for nm in pending:self.progress['items'][str(nm)]['status']='not_verified';self.save()
  return False
 def finish(self,status):
  self.progress['status']=status;self.progress['counts']={s:sum(x['status']==s for x in self.progress['items'].values()) for s in {x['status'] for x in self.progress['items'].values()}};self.save();print(json.dumps({'status':status,'counts':self.progress['counts'],'wb_update_requests':self.progress['wb_update_requests']}))
 def main(self):
  mode=os.environ.get('MODE','preflight');ready=self.preflight()
  if mode=='preflight':self.finish('preflight_complete');return
  assert mode=='apply' and os.environ.get('APPROVED_MANIFEST_SHA')==EXPECTED
  if not self.c.create(ROOT+':apply_lock',{'run_id':os.environ['GITHUB_RUN_ID'],'started_at':stamp(),'manifest_sha':EXPECTED}):raise RuntimeError('Prior apply lock; verify before any new execution')
  if not ready:self.finish('no_write_needed');return
  # First test one longest description; no bulk write until exact round-trip preservation is proved.
  canary=max(ready,key=lambda n:len(ready[n]['payload']['description']))
  outcome=self.update([canary],ready,'canary')
  if not self.verify([canary],ready,attempts=8):
   self.finish('canary_not_verified_'+outcome);return
  remaining=[n for n in ready if n!=canary]
  for j in range(0,len(remaining),25):
   nms=remaining[j:j+25];time.sleep(7);outcome=self.update(nms,ready,'batch'+str(j//25))
   if outcome!='accepted':
    self.verify(nms,ready,attempts=2);self.finish('stopped_after_unaccepted_response');return
   if not self.verify(nms,ready,attempts=4):self.finish('stopped_pending_batch_verification');return
  self.finish('complete')
if __name__=='__main__':
 r=Run()
 try:r.main()
 except Exception as e:
  r.progress['failure_type']=type(e).__name__;r.finish('stopped_error');raise
