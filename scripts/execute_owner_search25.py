"""Exact human-approved advertising actions; no price, budget or Telegram sends."""
import os,json,base64,time
from datetime import datetime,timezone,timedelta
from china_loss_execute import IO as OriginalIO
from china_loss_control import digest
from china_ad_rule import execute
REQ='china_agent:codex_search_launch:2026-10-25:v1'
PLAN_ID='codex-owner-adchanges-20261025-v1'
class IO(OriginalIO):
 def validate_owner(self,a):
  saved=self.get(REQ)
  if not saved or saved.get('status')!='approved' or saved.get('source')!='explicit_human_codex_message':raise ValueError('Exact human approval missing')
  if datetime.now(timezone.utc)>datetime.fromisoformat(saved['expires_at']):raise ValueError('Approval expired')
  if digest(saved['items'])!=a['plan_sha256']:raise ValueError('Approved items changed')
  cfg=self.db('business_agent_config?agent_id=eq.china&select=active,chat_id,bot_id,owner_user_id')
  if cfg!=[dict(active=True,chat_id=-1004342917488,bot_id=8780468043,owner_user_id=5122667182)]:raise ValueError('Registration changed')
  me=self.tg('getMe',{});assert me['id']==8780468043
  member=self.tg('getChatMember',dict(chat_id=-1004342917488,user_id=5122667182))
  assert member.get('user',{}).get('id')==5122667182 and member['user'].get('is_bot') is False
  assert member.get('status') in ['creator','administrator','member'] or member.get('status')=='restricted' and member.get('is_member') is True
  claims=json.loads(base64.urlsafe_b64decode(self.token.split('.')[1]+'='*(-len(self.token.split('.')[1])%4)))
  assert claims.get('t') is False and claims.get('exp',0)>time.time() and not int(claims.get('s',0))&(1<<30)
  ids=self.db('analytics_snapshots?cabinet=eq.token_3&source=eq.seller_identity&status=eq.complete&select=payload&limit=100')
  assert {r['payload'].get('sid') for r in ids}=={claims.get('sid')}

import requests
from china_loss_ads import current,nmset
from china_ad_rule import minimums
EXE=REQ+':execution'
def run():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner'
 io=IO();p=io.get(REQ);io.validate_owner(dict(plan_sha256=digest(p['items'])))
 assert p['budget_cny']==500 and p['placement']=='search' and not p['auto_topup'] and not p['daily_limit']
 e=io.get(EXE)
 if e and e.get('status')=='verified':print(json.dumps(dict(status='already_verified',wb_writes=0)));return
 if not e:
  e=dict(status='preflight',steps={},wb_writes=0,plan_sha256=digest(p['items']),created_at=datetime.now(timezone.utc).isoformat());assert io.create(EXE,e)
 assert e['plan_sha256']==digest(p['items'])
 def save():io.put(EXE,json.loads(json.dumps(e)))
 def req(path,method='GET',body=None):
  time.sleep(1.5);r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},json=body,timeout=50)
  if not r.ok:
   e['last_http_error']=dict(path=path,http=r.status_code,response=r.json() if r.content else None);save();raise RuntimeError('WB advertising HTTP '+str(r.status_code))
  return r.json() if r.content else {}
 def write(label,path,method,body=None):
  prior=e['steps'].get(label)
  if prior:
   if prior['status'] in ['accepted','verified']:return prior.get('response')
   raise ValueError('Uncertain write; no blind retry '+label)
  assert datetime.now(timezone.utc)<datetime.fromisoformat(p['expires_at'])
  e['steps'][label]=dict(status='submitting',path=path,body=body,submitted_at=datetime.now(timezone.utc).isoformat());save()
  try:r=req(path,method,body)
  except Exception:e['steps'][label]['status']='uncertain';save();raise
  e['wb_writes']+=1;e['steps'][label].update(status='accepted',response=r);save();return r
 def verify(label):e['steps'][label]['status']='verified';save()
 def campaign(predicate):
  for _ in range(25):
   c=current(io,[e['campaign_id']])[e['campaign_id']];e['last_campaign']=c;save()
   if predicate(c):return c
   time.sleep(8)
  raise ValueError('Readback pending; do not repeat accepted writes')
 def shape(c):
  return c.get('currency')=='CNY' and c.get('bid_type')=='manual' and c.get('settings',{}).get('payment_type')=='cpc' and c.get('settings',{}).get('placements')==dict(search=True,recommendations=False)
 def budget():
  rows=req('/api/advert/v2/budget','POST',dict(advertIds=[e['campaign_id']])).get('adverts',[])
  assert len(rows)==1 and rows[0]['advertId']==e['campaign_id'] and rows[0]['currency']=='CNY'
  return rows[0]['total']
 try:
  if 'eligible' not in e:
   cs=current(io);blocked={n['nm_id'] for c in cs.values() if c.get('settings',{}).get('placements',{}).get('search') for n in c.get('nm_settings',[])}
   e['eligible']=[x for x in p['items'] if x['nm_id'] not in blocked];e['skipped_existing_search']=[x['nm_id'] for x in p['items'] if x['nm_id'] in blocked];e['before_campaigns']=cs;save()
  selected=e['eligible'];assert 0<len(selected)<=50
  if 'campaign_id' not in e:
   r=write('create','/adv/v2/seacat/save-ad','POST',dict(name=p['campaign_name'],nms=[x['nm_id'] for x in selected],bid_type='manual',payment_type='cpc',placement_types=['search']))
   cid=r if type(r)is int else r.get('advertId') if isinstance(r,dict) else None
   assert type(cid)is int and cid>0;e['campaign_id']=cid;save()
  cid=e['campaign_id'];wanted={x['nm_id'] for x in selected}
  c=campaign(lambda c:shape(c) and nmset(c)==wanted and c['status'] in [4,9]);verify('create')
  if 'minima' not in e:
   j=req('/api/advert/v1/bids/min','POST',dict(advert_id=cid,nm_ids=sorted(wanted),payment_type='cpc',placement_types=['search']))
   mins={}
   for row in j.get('bids',[]):
    values=[b['value'] for b in row['bids'] if b['type']=='search' and b['currency']=='CNY'];assert len(values)==1;mins[row['nm_id']]=values[0]
   assert set(mins)==wanted;e['minima']=mins;save()
  valid=[x for x in selected if e['minima'].get(str(x['nm_id']),e['minima'].get(x['nm_id'],10**9))<=x['bid_minor']]
  invalid=wanted-{x['nm_id'] for x in valid};e['skipped_above_bid']=sorted(invalid);save()
  if invalid:
   write('remove_above_bid','/adv/v0/auction/nms','PATCH',dict(nms=[dict(advert_id=cid,nms=dict(add=[],delete=sorted(invalid)))]))
   campaign(lambda c:nmset(c)==wanted-invalid);verify('remove_above_bid')
  assert valid
  targets={x['nm_id']:x['bid_minor'] for x in valid}
  def check(c):return shape(c) and nmset(c)==set(targets) and all(n['bids_kopecks']['search']==targets[n['nm_id']] for n in c['nm_settings'])
  write('bids','/api/advert/v1/bids','PATCH',dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=x['nm_id'],bid_kopecks=x['bid_minor'],placement='search') for x in valid])]))
  campaign(check);verify('bids')
  if 'deposit' not in e['steps']:
   assert budget()==0
   bal=req('/adv/v1/balance');assert bal['currency']=='CNY'
   source=0 if bal.get('balance',0)>=500 else 1 if bal.get('net',0)>=500 else None
   if source is None:raise ValueError('Insufficient account funds for500CNY')
   e['funding_source']=source;save()
   write('deposit','/adv/v1/budget/deposit?id='+str(cid),'POST',dict(sum=500,type=source))
  for _ in range(16):
   b=budget();e['budget_after']=b;save()
   if b>=498:break
   time.sleep(5)
  if b<498:raise ValueError('Deposit readback pending; no duplicate deposit')
  verify('deposit')
  if 'start' not in e['steps']:
   c=campaign(check);assert c['status']==4
   write('start','/adv/v0/start?id='+str(cid),'GET')
  c=campaign(lambda c:check(c) and c['status']==9);verify('start')
  # Only the new campaign was written. Read previous campaigns to detect unrelated changes.
  e.update(status='verified',after=c,verified_at=datetime.now(timezone.utc).isoformat(),launched_items=valid);save()
  track=dict(status='active',campaign_id=cid,execution_key=EXE,items=valid,baseline_at=e['verified_at'],budget_cny=500,bid_minor=28,placement='search',auto_topup=False,auto_changes=False)
  try:track['baseline_fullstats']=req('/adv/v3/fullstats?ids='+str(cid)+'&beginDate=2026-10-25&endDate=2026-10-25')
  except Exception as ex:track['stats_error']=type(ex).__name__
  key='china_agent:search_test:2026-10-25:tracking:v1'
  io.put(key,track) if io.get(key) else io.create(key,track)
  print(json.dumps(dict(status='verified',campaign_id=cid,count=len(valid),skipped=len(invalid),budget_cny=500,wb_writes=e['wb_writes'])))
 except Exception as ex:
  e.update(status='attention',reason=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__);save();print(json.dumps(dict(status=e['status'],reason=e['reason'],wb_writes=e['wb_writes'])))
if __name__=='__main__':run()
