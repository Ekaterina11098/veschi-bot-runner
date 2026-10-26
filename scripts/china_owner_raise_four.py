"""Exact owner-approved four-SKU recommendation bid test; no deposits, starts, pauses or Telegram."""
import os,json,time
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity
KEY='china_agent:owner_raise_four:2026-10-26:v1:execution'
PLAN={40933588:{1473245494:'143-ReginaBag-black',1473244340:'447-AngelaBag-burgundy',1473244354:'623-AngelaBag-brown'},41055480:{1473243890:'595-Noelbag-zblack'}}
def norm(c):
 return dict(status=c['status'],currency=c['currency'],bid_type=c['bid_type'],settings=c['settings'],members={str(n['nm_id']):dict(subject_id=n['subject']['id'],bids=dict(n['bids_kopecks'])) for n in c['nm_settings']})
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise RuntimeError('Public main only')
 c=Cache();w=WB();validate_identity(c,w)
 auth=c.get('china_agent:owner_raise_four:2026-10-26:v1:approval') or {}
 if auth.get('status')!='approved' or auth.get('target_minor')!=31 or auth.get('owner_id')!=5122667182:raise RuntimeError('Exact approval missing')
 if c.get(KEY):print('Existing receipt; no repeated writes');return
 e=dict(status='preflight',owner_quote='меняем ставки',steps={},campaigns=[],telegram_sends=0,budget_writes=0,created_at=datetime.now(timezone.utc).isoformat(),planning_additional_expense_caps_cny={'143':40,'447':20,'623':20,'595':20},cap_note='Planning caps; no technical per-SKU cap exists and no hourly autonomy enabled')
 if not c.create(KEY,e):return
 def save():c.put(KEY,json.loads(json.dumps(e)))
 try:
  cs=w.campaigns(list(PLAN))
  stats=w.req('/adv/v3/fullstats?ids=40933588,41055480&beginDate=2026-10-26&endDate=2026-10-26')
  e['baseline_fullstats']=stats;e['stats_observed_at']=datetime.now(timezone.utc).isoformat();save()
  for cid,items in PLAN.items():
   before=cs[str(cid)]
   if before['status']!=9 or before['currency']!='CNY' or before['bid_type']!='manual' or before['settings']['payment_type']!='cpc' or before['settings']['placements']!={'search':False,'recommendations':True}:raise RuntimeError('Campaign scope changed')
   ns={n['nm_id']:n for n in before['nm_settings']}
   mins=w.minimums(cid,list(items),'recommendations')
   metrics={nm:dict(spend=0,amount=0,orders=0,clicks=0) for nm in items}
   campaigns=[x for x in stats if x['advertId']==cid]
   if len(campaigns)!=1 or campaigns[0].get('currency')!='CNY':raise RuntimeError('Current campaign stats incomplete')
   for day in campaigns[0].get('days',[]):
    if day['date'][:10]!='2026-10-26':continue
    for app in day.get('apps',[]):
     for n in app.get('nms',[]):
      if n['nmId'] in metrics:
       t=metrics[n['nmId']]
       for out,src in [('spend','sum'),('amount','sum_price'),('orders','orders'),('clicks','clicks')]:t[out]+=n[src]
   state=dict(campaign_id=cid,before=before,items=[dict(nm_id=nm,article=article,old_minor=28,target_minor=31) for nm,article in items.items()],metrics=metrics,status='preflight')
   e['campaigns'].append(state);save()
   for nm in items:
    if nm not in ns or ns[nm]['bids_kopecks']['recommendations']!=28 or mins[nm]>31:raise RuntimeError('Exact member/current bid/minimum differs from approved plan')
    m=metrics[nm]
    if not m['amount'] or not m['orders'] or m['spend']/m['amount']>.05:raise RuntimeError('Fresh current SKU result no longer meets5percent target: '+items[nm])
  # Both campaigns must pass before any mutation.
  for state in e['campaigns']:
   cid=state['campaign_id'];step=str(cid)
   body=dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=x['nm_id'],bid_kopecks=31,placement='recommendations') for x in state['items']])])
   e['steps'][step]=dict(status='submitting',body=body);save()
   try:r=w.req('/api/advert/v1/bids','PATCH',body,write=True)
   except Exception:e['steps'][step]['status']='uncertain';save();raise
   e['steps'][step].update(status='accepted',response=r);save()
   after=w.campaigns([cid])[str(cid)];state['after']=after
   expected=norm(state['before'])
   for x in state['items']:expected['members'][str(x['nm_id'])]['bids']['recommendations']=31
   if norm(after)!=expected:raise RuntimeError('Exact post-write state mismatch; never retry')
   e['steps'][step]['status']='verified';state['status']='verified';save()
  e['status']='verified'
 except Exception as ex:
  e.update(status='uncertain' if any(x.get('status')in ['submitting','accepted','uncertain'] for x in e['steps'].values()) else 'blocked',reason=str(ex) if isinstance(ex,RuntimeError) else type(ex).__name__)
 finally:
  e['completed_at']=datetime.now(timezone.utc).isoformat();save()
  registry=c.get('china_agent:verified_campaign_state:v1') or {}
  for state in e['campaigns']:
   if state['status']=='verified':
    k='china_agent:owner_raise_four:2026-10-26:'+str(state['campaign_id'])+':execution'
    c.put(k,dict(status='verified',before=state['before'],after=state['after'],items=state['items'],baseline_fullstats=e.get('baseline_fullstats'),verified_at=e['completed_at'],parent=KEY))
    registry[str(state['campaign_id'])]=k
  c.put('china_agent:verified_campaign_state:v1',registry)
  print('Exact owner bid test saved privately: '+e['status'])
if __name__=='__main__':run()
