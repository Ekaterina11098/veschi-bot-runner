"""Resume the exact five owner-approved IP changes after definite400. No other queues."""
import copy,datetime,hashlib,json,math,os,time,urllib.error,gzip
from ip_apply_nine_20261103 import SixTransport,projection,stamp,HOST,allowed_subset
from ip_owner_five_20261104 import PLAN,FROZEN,expected_state
from ip_daily_png_contract import digest,action_id
REC=PLAN+':recovery:v2';EXEC=REC+':execution'
def targets(p,current):
 baseline={str(a['campaign']):copy.deepcopy(a['baseline']) for a in p['actions']}
 desired=expected_state(p,baseline)
 if not all(allowed_subset(baseline,current,p['actions']).values()):raise ValueError('Unrelated WB state changed; do not overwrite')
 pending=[]
 for a in p['actions']:
  member=next((n for n in current[str(a['campaign'])]['nm_settings'] if n['nm_id']==a['nm']),None)
  done=member is None if a['kind']=='remove' else member is not None and member['bids_kopecks'].get(a['placement'])==a['target_bid_minor']
  if not done:pending.append(a)
 return pending,desired
def verified_items(p,after):
 out=[]
 for a in p['actions']:
  n=next((n for n in after[str(a['campaign'])]['nm_settings'] if n['nm_id']==a['nm']),None)
  good=n is None if a['kind']=='remove' else n is not None and n['bids_kopecks'].get(a['placement'])==a['target_bid_minor']
  out.append({k:a[k] for k in ('campaign','nm','sku','kind')}|dict(status='verified' if good else 'not_verified',target_bid_minor=a.get('target_bid_minor')))
 return out
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise PermissionError('Public main only')
 t=SixTransport();p=t.get(PLAN);old=t.get(PLAN+':execution');auth=t.get(REC)
 def guard():
  if not auth or auth.get('status')!='owner_authorized_recovery' or auth.get('scope_sha256')!=FROZEN or datetime.datetime.now(datetime.timezone.utc)>=datetime.datetime.fromisoformat(auth['expires_at']):raise PermissionError('Recovery approval missing/expired')
  if not p or digest(p['actions'])!=FROZEN or t.get(PLAN)!=p or t.get(REC)!=auth:raise PermissionError('Exact owner scope changed')
  if not old or old.get('status')!='attention' or old.get('wb_accepted_requests')!=0 or old.get('wb_write_attempts')!=1 or list(old.get('steps',{}).values())[0].get('http_status')!=400:raise PermissionError('Definite failed parent required; never replay uncertain work')
 guard()
 state=dict(status='preflight',approval_key=PLAN,recovery_key=REC,parent_execution=PLAN+':execution',run_id=os.environ['GITHUB_RUN_ID'],steps={},items=[],wb_write_attempts=0,wb_accepted_requests=0,started_at=stamp(),telegram_sends=0)
 if not t.create(EXEC,state):print('Existing recovery retained; no replay');return
 def save():t.save(EXEC,state)
 def progress(path,until):state.update(status='waiting_provider_cooldown',wait_endpoint=path,next_allowed_at=datetime.datetime.fromtimestamp(until,datetime.timezone.utc).isoformat());save()
 t.progress=progress
 ids=sorted({a['campaign'] for a in p['actions']});stage=None;read_time=0
 def refresh():
  nonlocal stage,read_time
  if stage is None:return
  if time.time()-read_time>180:
   cur=t.configs(ids);read_time=time.time()
   if any(projection(cur[k])!=projection(stage[k]) for k in stage):raise ValueError('WB changed during cooldown; no overwrite')
 def pause_header(path,h):
  retry=h.get('retry-after') or h.get('x-ratelimit-retry') or h.get('x-ratelimit-reset')
  if not retry:return
  seconds=float(retry)
  if not math.isfinite(seconds) or seconds<0:raise ValueError('Invalid provider interval')
  key='wb-pause:'+hashlib.sha256((t.token+'advert-api.wildberries.ru'+path).encode()).hexdigest();prior=t.get(key) or {}
  t.save(key,dict(until=max(float(prior.get('until',0)),time.time()+seconds+1),basis='provider_header'))
 def write(name,path,body):
  for attempt in range(4):
   t.pause(path);guard();refresh()
   st=dict(status='submitting',path=path,body=body,submitted_at=stamp());state['steps'][name+':'+str(attempt)]=st;state['wb_write_attempts']+=1;save()
   try:
    r=t.raw(HOST+path,{'Authorization':t.token,'Content-Type':'application/json','User-Agent':'python-requests/2.32.5'},'PATCH',body)
    h=getattr(t,'last_headers',{});st.update(status='accepted',response=r,accepted_at=stamp(),provider_headers={k:v for k,v in h.items() if 'ratelimit' in k or k=='retry-after'});state['wb_accepted_requests']+=1;save()
    if h.get('x-ratelimit-remaining')=='0':pause_header(path,h)
    return r
   except urllib.error.HTTPError as e:
    raw=e.read(16384)
    if e.headers.get('Content-Encoding')=='gzip':
     try:raw=gzip.decompress(raw)
     except Exception:pass
    detail=raw.decode('utf-8',errors='replace').replace(t.token,'[REDACTED]');h={k.lower():v for k,v in e.headers.items()}
    st.update(status='rejected',http_status=e.code,detail_private=detail,provider_headers={k:v for k,v in h.items() if 'ratelimit' in k or k=='retry-after'});save()
    if e.code==429 and attempt<3:pause_header(path,h);continue
    raise RuntimeError('WB rejected HTTP'+str(e.code)) from None
   except Exception:
    st.update(status='uncertain');save();raise
 try:
  t.identity()
  for a in p['actions']:
   m=t.get('advertising:ip:action-once:v1:'+action_id(a))
   if not m or m.get('plan_key')!=PLAN or m.get('execution_key')!=PLAN+':execution':raise PermissionError('Original action claim missing/mismatched; do not reset')
  current=t.configs(ids);stage=copy.deepcopy(current);read_time=time.time();pending,desired=targets(p,current);state.update(before=current,expected=desired,configuration_observed_at=stamp(),already_satisfied=5-len(pending));save()
  for a in [a for a in pending if a['kind']=='remove']:
   cid=a['campaign'];nm=a['nm']
   r=write('remove:'+str(cid),'/adv/v0/auction/nms',{'nms':[{'advert_id':cid,'nms':{'add':[],'delete':[nm]}}]})
   ack=r.get('nms',[])
   if len(ack)!=1 or ack[0].get('advert_id')!=cid or ack[0].get('nms',{}).get('added') or set(ack[0].get('nms',{}).get('deleted',[]))!={nm}:raise ValueError('Incomplete removal acknowledgment; no further writes')
   stage[str(cid)]['nm_settings']=[n for n in stage[str(cid)]['nm_settings'] if n['nm_id']!=nm]
  bids={}
  for a in pending:
   if a['kind'] in ('raise_bid','lower_bid'):bids.setdefault(a['campaign'],[]).append(dict(nm_id=a['nm'],placement=a['placement'],bid_kopecks=a['target_bid_minor']))
  if bids:write('bids','/api/advert/v1/bids',{'bids':[dict(advert_id=cid,nm_bids=items) for cid,items in sorted(bids.items())]})
  state['status']='verifying';save();after=t.configs(ids);state.update(after=after,readback_at=stamp(),items=verified_items(p,after));state['unrelated_members_settings_preserved']=all(projection(after[c])==projection(desired[c]) for c in desired);state['status']='verified' if state['unrelated_members_settings_preserved'] and all(i['status']=='verified' for i in state['items']) else 'attention_readback';save()
 except Exception as e:
  state.update(status='attention',error=str(e) if isinstance(e,(RuntimeError,ValueError,PermissionError)) else type(e).__name__);save()
  if state['wb_write_attempts']:
   try:
    after=t.configs(ids);state.update(recovery_readback=after,recovery_readback_at=stamp(),items=verified_items(p,after));save()
   except Exception as second:state['recovery_readback_error']=type(second).__name__;save()
 finally:state['finished_at']=stamp();save()
 print(json.dumps({k:state.get(k) for k in ('status','wb_write_attempts','wb_accepted_requests','items')}))
 if state['status']!='verified':raise SystemExit(1)
if __name__=='__main__':run()
