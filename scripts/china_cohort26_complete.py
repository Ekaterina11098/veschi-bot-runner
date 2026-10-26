"""Complete exact owner plan on reconciled existing draft41332083; never create/fund/start."""
import os,copy,json
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity
ROOT='china_agent:codex_search_expand26:v4:'
def iso():return datetime.now(timezone.utc).isoformat()
def members(c):return {str(n['nm_id']):dict(subject_id=n['subject']['id'],bids=dict(n['bids_kopecks'])) for n in c['nm_settings']}
def stable(c):return {k:c[k] for k in ['id','status','currency','bid_type','settings']}
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise RuntimeError('Public main only')
 c=Cache();w=WB();validate_identity(c,w);a=c.get(ROOT+'approval') or {}
 if a.get('status')!='approved' or a.get('owner_id')!=5122667182 or a.get('no_new_campaign_creation')is not True:raise RuntimeError('Exact continuation approval missing')
 if (datetime.now(timezone.utc)-datetime.fromisoformat(a['created_at'])).total_seconds()>7200:raise RuntimeError('Approval expired')
 proof=c.get(a['reconcile_known_creation']) or {};created=(proof.get('campaigns')or{}).get('41332083')
 if not created or created['status']!=4:raise RuntimeError('Known creation not reconciled')
 if c.get(ROOT+'execution'):raise RuntimeError('Existing continuation; no repeated writes')
 e=dict(status='preflight',created_at=iso(),groups=[],steps={},wb_writes=0,budget_writes=0,start_writes=0,telegram_sends=0,baseline_fullstats=[],baseline_observed_at=iso())
 if not c.create(ROOT+'execution',e):return
 def save():c.put(ROOT+'execution',json.loads(json.dumps(e)))
 def write(key,path,body):
  if key in e['steps']:raise RuntimeError('No repeated write')
  e['steps'][key]=dict(status='submitting',path=path,body=body,submitted_at=iso());save()
  try:r=w.req(path,'PATCH',body,write=True)
  except Exception:e['steps'][key]['status']='uncertain';save();raise
  e['steps'][key].update(status='accepted',response=r);e['wb_writes']+=1;save()
 try:
  cs=w.campaigns([g['campaign_id'] for g in a['groups']])
  # Validate both scopes before any further mutation.
  for g in a['groups']:
   b=cs[str(g['campaign_id'])]
   if b['currency']!='CNY' or b['bid_type']!='manual' or b['settings']['payment_type']!='cpc' or b['settings']['placements']!=dict(search=True,recommendations=False):raise RuntimeError('Campaign type changed')
   if g.get('new_draft'):
    if b['status']not in [4,9] or b['settings']['name']!=g['name'] or set(members(b))!={str(i['nm_id']) for i in g['items']}:raise RuntimeError('Known bag cohort changed')
   elif b['status']!=9 or len(set(members(b))|{str(i['nm_id']) for i in g['items']})>50:raise RuntimeError('Umbrella campaign inactive/full')
   if {n['subject']['id'] for n in b['nm_settings']}!={g['subject_id']}:raise RuntimeError('Campaign category mismatch')
  for g in a['groups']:
   cid=g['campaign_id'];before=cs[str(cid)];old=members(before)
   state=dict(campaign_id=cid,before=before,items=g['items'],new_draft=g.get('new_draft',False),status='preflight');e['groups'].append(state);save()
   missing=[i['nm_id'] for i in g['items'] if str(i['nm_id']) not in old]
   if missing:
    write(str(cid)+':add','/adv/v0/auction/nms',dict(nms=[dict(advert_id=cid,nms=dict(add=missing,delete=[]))]))
    mid=w.campaigns([cid])[str(cid)]
    if set(members(mid))!=set(old)|{str(n) for n in missing} or stable(mid)!=stable(before) or any(members(mid)[k]!=v for k,v in old.items()):raise RuntimeError('Addition readback mismatch')
    e['steps'][str(cid)+':add']['status']='verified';save()
   else:mid=before
   mins=w.minimums(cid,[i['nm_id'] for i in g['items']],'search');state['minimums']={str(k):v for k,v in mins.items()};save()
   needed=[dict(nm_id=i['nm_id'],bid_kopecks=mins[i['nm_id']],placement='search') for i in g['items'] if members(mid)[str(i['nm_id'])]['bids']['search']!=mins[i['nm_id']]]
   if needed:write(str(cid)+':bids','/api/advert/v1/bids',dict(bids=[dict(advert_id=cid,nm_bids=needed)]))
   after=w.campaigns([cid])[str(cid)];expected=copy.deepcopy(members(mid))
   for i in g['items']:expected[str(i['nm_id'])]['bids']['search']=mins[i['nm_id']]
   if members(after)!=expected or stable(after)!=stable(before):raise RuntimeError('Minimum bid readback mismatch')
   if needed:e['steps'][str(cid)+':bids']['status']='verified'
   state.update(status='verified',after=after,verified_at=iso());save()
   key=ROOT+str(cid)+':execution';c.put(key,dict(status='verified',before=before,after=after,items=[dict(kind='ad_set_bid' if g.get('new_draft') else 'ad_add_sku',nm_id=i['nm_id'],article=i['article'],placement='search',target_minor=mins[i['nm_id']]) for i in g['items']],verified_at=state['verified_at'],parent=ROOT+'execution',creation_receipt='china_agent:codex_search_expand26:v3:execution' if g.get('new_draft') else None))
   reg=c.get('china_agent:verified_campaign_state:v1') or {};reg[str(cid)]=key;c.put('china_agent:verified_campaign_state:v1',reg)
  e.update(status='verified',budgets_after=w.req('/api/advert/v2/budget','POST',dict(advertIds=[g['campaign_id'] for g in a['groups']])),config=w.req('/api/advert/v1/config'),completed_at=iso());save()
 except Exception as ex:
  e.update(status='uncertain' if any(v['status']in ['submitting','accepted','uncertain'] for v in e['steps'].values()) else 'blocked',reason=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__,completed_at=iso());save()
 finally:
  verified=[g for g in e['groups'] if g.get('status')=='verified']
  if verified:c.put('china_agent:search_trials:v1',dict(status='active',owner_authorized=True,started_at=e['baseline_observed_at'],baseline_fullstats=[],baseline_note='New bag draft and newly added umbrella items had no prior active exposure in target',execution_key=ROOT+'execution',items=[dict(campaign_id=g['campaign_id'],nm_id=i['nm_id'],article=i['article'],bid_minor=g['minimums'][str(i['nm_id'])],added_at=g['verified_at'],pending_activation=g.get('new_draft',False)and g['after']['status']==4,group='high_conversion_bags' if g.get('new_draft') else 'umbrellas') for g in verified for i in g['items']],report_slots=['codex_manual_morning'],hourly_autonomy=False,automatic_writes=False))
  print('Known-cohort completion: '+e['status'])
if __name__=='__main__':run()
