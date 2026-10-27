"""Reconcile confirmed membership once; keep exact approved rates and undo only unsupported default."""
import os,json,copy
from datetime import datetime,timezone
from china_price_apply import IO
from china_cloud_cost_control import Cache,WB,validate_identity
from china_owner_growth_apply27 import PLAN,APP,EXEC,stamp,exact,digest,projection
KEY=EXEC+':reconcile:v1'
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 io=IO();wb=WB();validate_identity(Cache(),wb);p=io.get(PLAN);a=io.get(APP);e=io.get(EXEC)
 if io.get(KEY):print('Reconciliation exists; no blind repeats');return
 if not a or a.get('status')!='approved' or a.get('source_channel')!='codex' or a.get('owner_user_id')!=5122667182 or p.get('status')!='pending_owner_approval' or a.get('plan_sha256')!=p.get('plan_sha256') or digest(p['items'])!=p['plan_sha256'] or projection(p['items'])!=a['items']:raise ValueError('Exact approval changed')
 if not e or e.get('status')!='attention' or e.get('reason')!='Added SKU minimum exceeds exact approved category rate' or e.get('steps',{}).get('membership',{}).get('status')!='accepted' or 'bids' in e['steps']:raise ValueError('Recovery scope differs')
 if (datetime.now(timezone.utc)-datetime.fromisoformat(e['steps']['membership']['submitted_at'])).total_seconds()>600:raise ValueError('Preflight older than10min; need narrow new validation')
 ids=sorted({i['campaign_id'] for i in p['items']});current=wb.campaigns(ids)
 # No intervening unrelated changes may be overwritten.
 if any(not exact(e['after_membership'][str(cid)],current[str(cid)],[]) for cid in ids):raise ValueError('Intervening state change; review recovery')
 z=next(i for i in p['items'] if i['nm_id']==1556488181)
 minimum=wb.minimums(z['campaign_id'],[z['nm_id']],'search')[z['nm_id']]
 r=dict(status='running',created_at=stamp(),source_execution=EXEC,approval_key=APP,before=current,umbrella_minimum_minor=minimum,steps={},wb_writes=0)
 if not io.create(KEY,r):raise ValueError('Concurrent recovery')
 def save():io.put(KEY,json.loads(json.dumps(r)))
 def write(name,path,body):
  if name in r['steps']:raise ValueError('Write previously attempted')
  live=io.get(PLAN) or {}
  if live.get('status')!='pending_owner_approval' or live.get('plan_sha256')!=p['plan_sha256'] or datetime.now(timezone.utc)>datetime.fromisoformat(p['expires_at']):raise ValueError('Plan no longer valid')
  r['steps'][name]=dict(status='submitting',path=path,body=body);save()
  try:
   response=wb.req(path,'PATCH',body,write=True);r['steps'][name].update(status='accepted',response=response);r['wb_writes']+=1;save()
  except Exception as error:r['steps'][name].update(status='uncertain',reason=str(error));save();raise
 try:
  rollback=minimum>z['target_minor']
  if rollback:write('remove_unsupported_umbrella','/adv/v0/auction/nms',dict(nms=[dict(advert_id=z['campaign_id'],nms=dict(add=[],delete=[z['nm_id']]))]))
  belt=next(i for i in p['items'] if i['kind']=='ad_raise_bid')
  need=[]
  bn=next(n for n in current[str(belt['campaign_id'])]['nm_settings'] if n['nm_id']==belt['nm_id'])
  if bn['bids_kopecks']['recommendations']==belt['old_minor']:need.append(belt)
  elif bn['bids_kopecks']['recommendations']!=belt['target_minor']:raise ValueError('Belt rate changed')
  if not rollback:need.append(z)
  if need:write('exact_remaining_bids','/api/advert/v1/bids',dict(bids=[dict(advert_id=i['campaign_id'],nm_bids=[dict(nm_id=i['nm_id'],bid_kopecks=i['target_minor'],placement=i['placement'])]) for i in need]))
  after=wb.campaigns(ids);r['after']=after
  kept=[i for i in p['items'] if not rollback or i['nm_id']!=z['nm_id']]
  for cid in ids:
   expected=[i for i in kept if i['campaign_id']==cid]
   if not exact(e['before'][str(cid)],after[str(cid)],expected):raise ValueError('Final exact rates/membership not confirmed')
  r.update(status='verified',verified_at=stamp(),completed_at=stamp(),verified_items=projection(kept),rolled_back_items=[dict(article=z['article'],nm_id=z['nm_id'],campaign_id=z['campaign_id'],approved_minor=z['target_minor'],actual_minimum_minor=minimum)] if rollback else [])
  for s in r['steps'].values():s['status']='verified'
  save()
  e.update(status='partial_verified' if rollback else 'verified',after=after,verified_at=r['verified_at'],completed_at=r['completed_at'],reconciliation_key=KEY,verified_count=len(kept),rolled_back_count=int(rollback))
  for st in e['items']:
   cid=st['item']['campaign_id'];st.update(status='rolled_back' if rollback and st['item']['nm_id']==z['nm_id'] else 'verified',after=after[str(cid)])
  io.put(EXEC,e)
  registry=io.get('china_agent:verified_campaign_state:v1') or {}
  for cid in ids:
   key='china_agent:owner_growth_apply27:2026-10-27:v1:'+str(cid)+':execution'
   b=current[str(cid)] if rollback and cid==z['campaign_id'] else e['before'][str(cid)]
   receipt=dict(status='verified',before=b,after=after[str(cid)],items=[i for i in kept if i['campaign_id']==cid],verified_at=r['verified_at'],parent=EXEC,reconciliation_key=KEY,approval_key=APP)
   if not io.create(key,receipt):raise ValueError('Concurrent receipt')
   registry[str(cid)]=key
  io.put('china_agent:verified_campaign_state:v1',registry)
  io.put(PLAN,dict(p,status='partially_executed' if rollback else 'executed',execution_key=EXEC,completed_at=r['completed_at'],remaining_requires_new_plan=rollback))
 except Exception as error:
  r.update(status='attention',reason=str(error) if isinstance(error,(ValueError,RuntimeError)) else type(error).__name__,completed_at=stamp());save()
 print(json.dumps(dict(status=r['status'],wb_writes=r['wb_writes'],verified=len(r.get('verified_items',[])),rolled_back=r.get('rolled_back_items',[]),reason=r.get('reason'))))
if __name__=='__main__':run()
