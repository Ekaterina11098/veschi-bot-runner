"""Owner-approved exact two CPC changes; no preflight rates or stock reads."""
import os,time
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,stamp
ROOT='china_agent:owner_raise_044_36:2026-10-26:v1'
PLAN=[dict(cid=40933588,nm=1473243894,article='044-NoelBag-black',old=28,target=31),dict(cid=41055480,nm=1473243439,article='36-EthelBag-brown',old=28,target=30)]
def main():
 assert os.environ.get('GITHUB_REPOSITORY')=='Ekaterina11098/veschi-bot-runner'
 assert os.environ.get('GITHUB_REF')=='refs/heads/main'
 assert datetime.now(timezone.utc)<datetime.fromisoformat('2026-10-26T20:00:00+00:00')
 c=Cache();w=WB();auth=c.get(ROOT+':approval')
 assert auth and auth.get('owner_authorized') is True and auth.get('plan')==PLAN and auth.get('skip_preflight_rates_stock') is True
 key=ROOT+':execution'
 p=dict(status='prepared',created_at=stamp(),items=PLAN,preflight_rates_stock_skipped=True,before_basis='Last verified receipt 17:21 MSK, not a new preflight',budget_writes=0,telegram_sends=0,stock_writes=0)
 if not c.create(key,p):
  print('Existing execution identity; no replay');return
 body=dict(bids=[dict(advert_id=x['cid'],nm_bids=[dict(nm_id=x['nm'],bid_kopecks=x['target'],placement='recommendations')]) for x in PLAN])
 p.update(status='sending',request=body,write_started_at=stamp());c.put(key,p)
 try:
  response=w.req('/api/advert/v1/bids','PATCH',body,write=True)
 except Exception as e:
  p.update(status='uncertain',error=str(e),failed_at=stamp());c.put(key,p);raise
 p.update(status='applied_unverified',response=response);c.put(key,p)
 for attempt in range(3):
  after=w.campaigns([x['cid'] for x in PLAN])
  ok=all(after[str(x['cid'])].get('currency')=='CNY' and any(n['nm_id']==x['nm'] and n['bids_kopecks']['recommendations']==x['target'] for n in after[str(x['cid'])]['nm_settings']) for x in PLAN)
  p.update(after=after,readback_at=stamp());c.put(key,p)
  if ok:break
  time.sleep(3)
 if not ok:
  p.update(status='verification_mismatch');c.put(key,p);raise RuntimeError('Target readback mismatch; no replay')
 registry=c.get('china_agent:verified_campaign_state:v1') or {}
 for x in PLAN:
  child=ROOT+':'+str(x['cid'])+':execution'
  c.put(child,dict(status='verified',after=after[str(x['cid'])],items=[x],verified_at=stamp(),parent=key,before_basis=p['before_basis']))
  registry[str(x['cid'])]=child
 c.put('china_agent:verified_campaign_state:v1',registry)
 p.update(status='verified',verified_at=stamp(),wb_writes=1);c.put(key,p)
 print('Both exact bids WB-verified; no other mutations')
if __name__=='__main__':main()
