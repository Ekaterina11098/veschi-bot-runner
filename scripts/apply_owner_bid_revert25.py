"""One explicit private human approval, one bid PATCH, no funding writes."""
import json,time
from datetime import datetime,timezone
from china_loss_execute import IO
from china_loss_ads import current,http
from china_loss_control import digest
from china_ad_rule import minimums,verified_item
from china_new_ads import Transport
REQ='china_agent:codex_bid_revert:2026-10-25:v1'
EXE=REQ+':execution'
def stamp():return datetime.now(timezone.utc).isoformat()
def run():
 io=IO();a=io.get(REQ);assert a and a['status']=='approved' and a['source']=='explicit_human_codex_message'
 p=a['plan'];assert a['plan_sha256']==digest(p) and p['source']==a['source'] and p['quote']==a['quote']
 assert p['cabinet']=='token_3' and p['budget_increase'] is False and p['auto_topup'] is False and p['kind']=='ad_set_bid'
 assert p['placement']=='recommendations' and type(p['target_minor']) is int and p['old_minor']==42 and p['target_minor']==40
 assert datetime.now(timezone.utc)<datetime.fromisoformat(a['expires_at'])
 # Original registered human membership and seller-token identity checks;
 # authority for this bid change comes from the separately recorded Codex message.
 io.validate_owner(io.get('china_agent:loss_plan_approval:v1:86'))
 e=io.get(EXE)
 if e and e['status']=='verified':return
 t=Transport(io);cid=p['campaign_id'];nm=p['nm_id']
 def save():io.put(EXE,json.loads(json.dumps(e)))
 if not e:
  before=current(io,[cid])[cid];cfg=t.config()
  assert before['status']==9 and before['currency']=='CNY' and before['bid_type']=='manual'
  assert before['settings']['payment_type']=='cpc' and before['settings']['placements']==dict(search=False,recommendations=True)
  setting=next(n for n in before['nm_settings'] if n['nm_id']==nm)
  assert setting['bids_kopecks']['recommendations']==p['old_minor'],'Current bid changed; no write'
  assert (cid,nm,p['article'])==(40933588,1473243891,'0-NoelBag-green') # exact owner-approved identity; no unrelated price refresh
  mins=minimums(io,cid,{nm});step=cfg['cpcStep']
  assert cfg['currency']=='CNY' and p['target_minor']%step==0 and mins[nm]<=p['target_minor']<=cfg['cpcMaxBid']
  # Snapshot today's exact SKU attribution before the change; monitoring uses deltas.
  import requests
  day=datetime.now(timezone.utc).astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date().isoformat()
  r=requests.get('https://advert-api.wildberries.ru/adv/v3/fullstats',headers={'Authorization':io.token},params=dict(ids=str(cid),beginDate=day,endDate=day),timeout=60)
  assert r.ok,'Baseline statistics unavailable; no write'
  baseline=r.json();budget=t.budget(cid)
  e=dict(status='preflight',plan=p,plan_sha256=a['plan_sha256'],before=before,budget_before=budget,config=cfg,minimum_minor=mins[nm],baseline_fullstats=baseline,baseline_observed_at=stamp(),wb_writes=0)
  assert io.create(EXE,e)
 if e['status']=='preflight':
  # Recheck exact previous state immediately before crossing the write boundary.
  assert current(io,[cid])[cid]==e['before'],'Campaign changed during preflight'
  e.update(status='submitting',submitted_at=stamp(),request=dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=nm,bid_kopecks=p['target_minor'],placement=p['placement'])])]))
  save()
  import requests
  try:
   r=requests.patch('https://advert-api.wildberries.ru/api/advert/v1/bids',headers={'Authorization':io.token},json=e['request'],timeout=45)
   try:j=r.json()
   except ValueError:j=r.text[:1500]
   e.update(http=r.status_code,response=j,wb_writes=1,status='accepted' if r.ok else 'rejected');save()
  except Exception:
   e.update(status='uncertain',reason='Bid response not received; never repeat PATCH');save()
 if e['status'] in ['accepted','submitting','uncertain']:
  for attempt in range(14):
   got=current(io,[cid])[cid]
   if verified_item(p,e['before'],got):
    e.update(status='verified',after=got,verified_at=stamp(),budget_after=t.budget(cid),funding_writes=0);save();break
   if attempt==13:e.update(status='readback_pending',after=got);save();break
   time.sleep(15)
 if e['status']=='verified':
  key='china_agent:bid_raise_tracking:v1';tracking=io.get(key) or dict(items={})
  old=tracking['items'].get(str(cid)+':'+str(nm))
  if old and old.get('execution_key')!=EXE:tracking.setdefault('history',[]).append(dict(old,status='completed_by_owner_revert',ended_at=e['submitted_at']))
  tracking['items'][str(cid)+':'+str(nm)]=dict(status='active',plan=p,started_at=e['submitted_at'],verified_at=e['verified_at'],execution_key=EXE,target_drr_pct=5,budget_increase=False,baseline_at=e['baseline_observed_at'],start_evaluation='first complete Moscow day after change',auto_revert_authorized=False)
  io.put(key,tracking) if io.get(key) else io.create(key,tracking)
 print(json.dumps(dict(status=e['status'],wb_writes=e['wb_writes'],funding_writes=0)))
if __name__=='__main__':run()

