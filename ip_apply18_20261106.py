"""Exact owner-approved saved preview. Scoped writes, no delivery or other queues."""
import copy,datetime,hashlib,json,math,os,time,urllib.error,gzip
from ip_apply_nine_20261103 import SixTransport,projection,stamp,HOST
from ip_daily_png_contract import digest,action_id,ready
from ip_bags_growth_20261104 import active_ids
PLAN='ip_agent:png18:2026-11-06:v1';EXEC=PLAN+':execution'
FROZEN='8f79150e8e45b9f85aa106bfaf8ac4a4ca8f86095e2efcdf06ea49f159ce4e3f'
def prepare(p,before,stock):
 stage=copy.deepcopy(before);pending=[];items=[]
 for a in p['actions']:
  cid=str(a['campaign']);c=before[cid];old=a['baseline'];nm=a['nm']
  if c['status']!=9 or c['currency']!='RUB' or c['bid_type']!='manual' or c['settings'].get('payment_type')!=old['settings'].get('payment_type') or c['settings'].get('placements')!=old['settings'].get('placements'):raise ValueError('Target campaign mode changed')
  current=next((n for n in c['nm_settings'] if n['nm_id']==nm),None);item={k:a[k] for k in ('campaign','nm','sku','kind')};item['status']='pending'
  if a['kind']=='remove':
   if current is None:item['status']='already_satisfied'
   else:
    if not c['restrictions'].get('can_change_nms') or len(stage[cid]['nm_settings'])<=1:raise ValueError('Exact removal unavailable')
    stage[cid]['nm_settings']=[n for n in stage[cid]['nm_settings'] if n['nm_id']!=nm]
  elif a['kind'] in ('raise_bid','lower_bid'):
   if not current:raise ValueError('Bid target absent; do not re-add')
   value=current['bids_kopecks'].get(a['placement'])
   if value==a['target_bid_minor']:item['status']='already_satisfied'
   elif value!=a['stored_bid_minor']:raise ValueError('Exact target bid changed; no overwrite')
   for n in stage[cid]['nm_settings']:
    if n['nm_id']==nm:n['bids_kopecks'][a['placement']]=a['target_bid_minor']
  elif a['kind']=='add':
   if c['settings'].get('payment_type')!='cpc' or c['settings'].get('placements')!={'search':True,'recommendations':False} or {n['subject']['id'] for n in c['nm_settings']}!={a['subject']}:raise ValueError('Category/search mismatch')
   if any(n['nm_id']==nm for k,v in before.items() if k!=cid and v.get('status')==9 for n in v['nm_settings']):raise ValueError('Already advertised elsewhere; no overlap')
   if current:
    if current['subject']['id']!=a['subject'] or current['bids_kopecks'].get('search')!=a['target_bid_minor']:raise ValueError('Existing addition differs; no overwrite')
    item['status']='already_satisfied'
   else:
    if len(stage[cid]['nm_settings'])>=50 or not c['restrictions'].get('can_change_nms'):raise ValueError('No capacity')
    stage[cid]['nm_settings'].append(dict(nm_id=nm,subject=copy.deepcopy(c['nm_settings'][0]['subject']),bids_kopecks=dict(search=a['target_bid_minor'],recommendations=0)))
  else:raise PermissionError('Scope operation unavailable')
  if a['kind'] in ('add','raise_bid') and item['status']!='already_satisfied':
   q=stock.get(str(nm));subject=a.get('subject') or current['subject']['id']
   if not q or not all(math.isfinite(q[k]) and q[k]>=0 for k in ('fbo','fbs')) or (q['fbo'] if subject in (51,57,255,756) else q['fbo']+q['fbs'])<=0:raise ValueError('Positive saved current stock not proven')
  items.append(item)
  if item['status']!='already_satisfied':pending.append(a)
 return pending,stage,items
def item_results(p,current):
 out=[]
 for a in p['actions']:
  n=next((n for n in current[str(a['campaign'])]['nm_settings'] if n['nm_id']==a['nm']),None)
  good=n is None if a['kind']=='remove' else n is not None and n['bids_kopecks'].get(a['placement'])==a['target_bid_minor']
  out.append({k:a[k] for k in ('campaign','nm','sku','kind')}|dict(status='verified' if good else 'not_verified',target_bid_minor=a.get('target_bid_minor')))
 return out
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise PermissionError('Public main only')
 t=SixTransport();p=t.get(PLAN)
 def guard():
  if not p or p.get('status')!='owner_authorized' or p.get('budgets_authorized')is not False or len(p['actions'])!=18 or digest(p['actions'])!=FROZEN or any(not ready(a,p['period']) for a in p['actions']):raise PermissionError('Exact18approval missing')
  if datetime.datetime.now(datetime.timezone.utc)>=datetime.datetime.fromisoformat(p['expires_at']) or t.get(PLAN)!=p:raise PermissionError('Approval expired/changed')
 guard();state=dict(status='preflight',approval_key=PLAN,run_id=os.environ['GITHUB_RUN_ID'],steps={},items=[],wb_write_attempts=0,wb_accepted_requests=0,started_at=stamp(),telegram_sends=0)
 if not t.create(EXEC,state):print('Existing18execution retained; no replay');return
 def save():t.save(EXEC,state)
 def progress(path,until):state.update(status='waiting_provider_cooldown',wait_endpoint=path,next_allowed_at=datetime.datetime.fromtimestamp(until,datetime.timezone.utc).isoformat());save()
 t.progress=progress;stage=None;read_time=0;ids=[];stock={}
 def refresh():
  nonlocal read_time
  if time.time()-read_time>180:
   cur=t.configs(ids);read_time=time.time()
   if any(projection(cur[k])!=projection(stage[k]) for k in stage):raise ValueError('WB changed during wait; no overwrite')
 def pause_header(path,h):
  value=h.get('retry-after') or h.get('x-ratelimit-retry') or h.get('x-ratelimit-reset')
  if value is None:return False
  seconds=float(value)
  if not math.isfinite(seconds) or seconds<0:raise ValueError('Invalid provider interval')
  key='wb-pause:'+hashlib.sha256((t.token+'advert-api.wildberries.ru'+path).encode()).hexdigest();prior=t.get(key) or {}
  t.save(key,dict(until=max(float(prior.get('until',0)),time.time()+seconds+1),basis='provider_header'));return True
 def write(name,path,body):
  for attempt in range(4):
   t.pause(path);guard();refresh();st=dict(status='submitting',path=path,body=body,submitted_at=stamp());state['steps'][name+':'+str(attempt)]=st;state['wb_write_attempts']+=1;save()
   try:
    r=t.raw(HOST+path,{'Authorization':t.token,'Content-Type':'application/json','User-Agent':'python-requests/2.32.5'},'PATCH',body)
    st.update(status='accepted',response=r,accepted_at=stamp());state['wb_accepted_requests']+=1;save();h=getattr(t,'last_headers',{})
    if h.get('x-ratelimit-remaining')=='0':pause_header(path,h)
    return r
   except urllib.error.HTTPError as e:
    b=e.read(16384)
    if e.headers.get('Content-Encoding')=='gzip':
     try:b=gzip.decompress(b)
     except Exception:pass
    h={k.lower():v for k,v in e.headers.items()};st.update(status='rejected',http_status=e.code,detail_private=b.decode('utf-8',errors='replace').replace(t.token,'[REDACTED]'));save()
    if e.code==429 and attempt<3 and pause_header(path,h):continue
    if e.code==400:return None
    raise RuntimeError('WB rejected HTTP'+str(e.code)) from None
   except Exception:st['status']='uncertain';save();raise
 try:
  t.identity();ids,index=active_ids(t,{a['campaign'] for a in p['actions']});state.update(campaign_index=index,campaign_ids=ids);save()
  evidence=t.get(PLAN+':stock-evidence') or {};stock={str(r['nm']):dict(fbo=float(r['fbo']),fbs=float(r['fbs'])) for r in evidence.get('rows',[])}
  if evidence.get('plan_sha256')!=FROZEN or evidence.get('period')!=p['period']:raise PermissionError('Exact retained stock evidence missing')
  before=t.configs(ids);read_time=time.time();pending,desired,items=prepare(p,before,stock);stage=copy.deepcopy(before);state.update(before=before,expected=desired,configuration_observed_at=stamp(),stock_evidence=evidence,items=items);save()
  for a in pending:
   if not t.create('advertising:ip:action-once:v1:'+action_id(a),dict(status='approved',plan_key=PLAN,execution_key=EXEC,approved_at=stamp())):raise PermissionError('Existing action claim; no replay')
  groups={}
  for a in pending:
   if a['kind'] in ('add','remove') and a['campaign']!=40192945:
    n=groups.setdefault(a['campaign'],dict(add=[],delete=[]));n['add' if a['kind']=='add' else 'delete'].append(a['nm'])
  if groups:
   r=write('membership','/adv/v0/auction/nms',dict(nms=[dict(advert_id=cid,nms=n) for cid,n in sorted(groups.items())]))
   if r is None:raise ValueError('Membership batch rejected; readback required before any other write')
   ack={x['advert_id']:x['nms'] for x in r.get('nms',[])}
   if set(ack)!=set(groups) or any(set(ack[cid].get('added',[]))!=set(n['add']) or set(ack[cid].get('deleted',[]))!=set(n['delete']) for cid,n in groups.items()):raise ValueError('Exact membership ack incomplete')
   for a in pending:
    if a['campaign'] not in groups or a['kind'] not in ('add','remove'):continue
    cid=str(a['campaign'])
    if a['kind']=='remove':stage[cid]['nm_settings']=[n for n in stage[cid]['nm_settings'] if n['nm_id']!=a['nm']]
    else:stage[cid]['nm_settings'].append(next(copy.deepcopy(n) for n in desired[cid]['nm_settings'] if n['nm_id']==a['nm']))
  if any(a['kind']=='add' for a in pending):
   cur=t.configs(ids);read_time=time.time()
   for cid in stage:
    probe=copy.deepcopy(cur[cid]);target=copy.deepcopy(stage[cid])
    for a in pending:
     if a['kind']=='add' and str(a['campaign'])==cid:
      n=next((n for n in probe['nm_settings'] if n['nm_id']==a['nm']),None)
      wanted=next(n for n in target['nm_settings'] if n['nm_id']==a['nm'])
      if not n or n['subject']!=wanted['subject']:raise ValueError('Added SKU readback missing/category changed')
      wanted['bids_kopecks']=copy.deepcopy(n['bids_kopecks'])
    if projection(probe)!=projection(target):raise ValueError('Unrelated settings changed after membership')
   stage=cur
  bids={}
  for a in pending:
   if a['kind'] in ('raise_bid','lower_bid','add'):bids.setdefault(a['campaign'],[]).append(dict(nm_id=a['nm'],placement=a['placement'],bid_kopecks=a['target_bid_minor']))
  if bids:
   r=write('bids','/api/advert/v1/bids',dict(bids=[dict(advert_id=cid,nm_bids=n) for cid,n in sorted(bids.items())]))
   if r is None:raise ValueError('Bid batch rejected; no substituted values')
   for a in pending:
    if a['kind'] in ('raise_bid','lower_bid','add'):
     next(n for n in stage[str(a['campaign'])]['nm_settings'] if n['nm_id']==a['nm'])['bids_kopecks'][a['placement']]=a['target_bid_minor']
  isolated=[a for a in pending if a['kind']=='remove' and a['campaign']==40192945]
  for a in isolated:
   r=write('isolated40192945','/adv/v0/auction/nms',dict(nms=[dict(advert_id=a['campaign'],nms=dict(add=[],delete=[a['nm']]))]))
   if r is not None:
    ack=r.get('nms',[])
    if len(ack)!=1 or ack[0]['advert_id']!=a['campaign'] or ack[0]['nms'].get('added') or set(ack[0]['nms'].get('deleted',[]))!={a['nm']}:raise ValueError('Isolated ack incomplete')
    stage[str(a['campaign'])]['nm_settings']=[n for n in stage[str(a['campaign'])]['nm_settings'] if n['nm_id']!=a['nm']]
   else:state['blocked_campaign']=40192945;save()
  state['status']='verifying';save();after=t.configs(ids);state.update(after=after,readback_at=stamp(),items=item_results(p,after));state['unrelated_members_settings_preserved']=all(projection(after[c])==projection(stage[c]) for c in stage);state['status']='verified' if all(i['status']=='verified' for i in state['items']) and state['unrelated_members_settings_preserved'] else 'partial_verified' if state['unrelated_members_settings_preserved'] else 'attention_readback';save()
 except Exception as e:
  state.update(status='attention',error=str(e) if isinstance(e,(RuntimeError,ValueError,PermissionError)) else type(e).__name__);save()
  if state['wb_write_attempts']:
   try:
    after=t.configs(ids);state.update(recovery_readback=after,recovery_readback_at=stamp(),items=item_results(p,after));save()
   except Exception as second:state['recovery_readback_error']=type(second).__name__;save()
 finally:
  if state.get('error') and state['status']=='waiting_provider_cooldown':state['status']='attention'
  state['finished_at']=stamp();save()
 print(json.dumps({k:state.get(k) for k in ('status','wb_write_attempts','wb_accepted_requests')}))
 if state['status']!='verified':raise SystemExit(1)
if __name__=='__main__':run()

