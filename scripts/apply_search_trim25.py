"""Execute one owner-approved ten-SKU removal. One bulk PATCH; no funding/sends."""
import os,json,time,base64,copy,requests
from datetime import datetime,timezone
from china_loss_execute import IO as OriginalIO
from china_loss_ads import current,nmset
from china_loss_control import digest
REQ='china_agent:codex_search_trim:2026-10-25:v1'
EXE=REQ+':execution'
CID=41298169
APPROVED={1473242760,1473245513,1473245496,1473243916,1473243440,1473243914,1473243903,1473243911,1473245495,1473244984}
def stamp():return datetime.now(timezone.utc).isoformat()
class IO(OriginalIO):
 def tg(self,method,body):
  if method not in ['getMe','getChatMember']:raise PermissionError('No Telegram send permission')
  return super().tg(method,body)
 def validate_owner(self,p):
  assert p['status']=='approved' and p['source']=='explicit_human_codex_message'
  assert p['human_quote']=='делаем' and p['plan_sha256']==digest(p['items'])
  assert p['campaign_id']==CID and p['expected_before_count']==43 and p['expected_after_count']==33
  assert p['budget_increase'] is False and p['auto_topup'] is False and p['bid_minor']==28 and p['placement']=='search'
  assert {x['nm_id'] for x in p['items']}==APPROVED and len(p['items'])==10
  assert all(x['campaign_id']==CID and x['kind']=='ad_exclude_sku' for x in p['items'])
  assert self.db('business_agent_config?agent_id=eq.china&select=active,chat_id,bot_id,owner_user_id')==[dict(active=True,chat_id=-1004342917488,bot_id=8780468043,owner_user_id=5122667182)]
  me=self.tg('getMe',{});assert me['id']==8780468043
  member=self.tg('getChatMember',dict(chat_id=-1004342917488,user_id=5122667182))
  assert member['user']['id']==5122667182 and member['user'].get('is_bot') is False
  assert member.get('status') in ['creator','administrator','member'] or member.get('status')=='restricted' and member.get('is_member') is True
  claims=json.loads(base64.urlsafe_b64decode(self.token.split('.')[1]+'='*(-len(self.token.split('.')[1])%4)))
  assert claims.get('t') is False and claims.get('exp',0)>time.time() and not int(claims.get('s',0))&(1<<30)
  ids=self.db('analytics_snapshots?cabinet=eq.token_3&source=eq.seller_identity&status=eq.complete&select=payload&limit=100')
  assert {x['payload'].get('sid') for x in ids}=={claims.get('sid')}
def shape(c):
 return c['status']==9 and c['currency']=='CNY' and c['bid_type']=='manual' and c['settings']['payment_type']=='cpc' and c['settings']['placements']==dict(search=True,recommendations=False)
def run():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner'
 io=IO();p=io.get(REQ);io.validate_owner(p)
 e=io.get(EXE)
 if e and e['status']=='verified':print('already_verified');return
 wanted=set(p['keep_nm_ids']);assert len(wanted)==33 and not wanted.intersection(APPROVED)
 def save():io.put(EXE,json.loads(json.dumps(e)))
 def read(path):
  time.sleep(1.5)
  r=requests.get('https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},timeout=50)
  if not r.ok:raise RuntimeError('WB read HTTP '+str(r.status_code))
  return r.json()
 def budget():return read('/adv/v1/budget?id='+str(CID))
 def matches(c):
  expected=copy.deepcopy(e['before'])
  expected['nm_settings']=[n for n in expected['nm_settings'] if n['nm_id'] not in APPROVED]
  return shape(c) and nmset(c)==wanted and c['settings']==expected['settings'] and sorted(c['nm_settings'],key=lambda n:n['nm_id'])==sorted(expected['nm_settings'],key=lambda n:n['nm_id'])
 if not e:
  assert datetime.now(timezone.utc)<datetime.fromisoformat(p['expires_at'])
  before=current(io,[CID])[CID]
  assert shape(before) and nmset(before)==wanted|APPROVED and len(before['nm_settings'])==43
  assert all(n['bids_kopecks']['search']==28 for n in before['nm_settings'])
  e=dict(status='preflight',plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],before=before,excluded_items=p['items'],budget_before=budget(),wb_writes=0,funding_writes=0,telegram_sends=0)
  try:
   e['baseline_fullstats']=read('/adv/v3/fullstats?ids='+str(CID)+'&beginDate=2026-10-25&endDate=2026-10-25')
   e['baseline_observed_at']=stamp()
  except RuntimeError:
   cached=io.get('china_agent:search_test:2026-10-25:hour22:v1')
   assert cached['fullstats']['http']==200
   e.update(baseline_fullstats=cached['fullstats']['data'],baseline_observed_at=cached['observed_at'],baseline_is_cached=True)
  assert io.create(EXE,e)
 if e['status']=='preflight':
  assert datetime.now(timezone.utc)<datetime.fromisoformat(p['expires_at'])
  assert current(io,[CID])[CID]==e['before'],'Campaign changed during preflight; no write'
  e.update(status='submitting',submitted_at=stamp(),request=dict(nms=[dict(advert_id=CID,nms=dict(add=[],delete=sorted(APPROVED)))]))
  save()
  try:
   r=requests.patch('https://advert-api.wildberries.ru/adv/v0/auction/nms',headers={'Authorization':io.token},json=e['request'],timeout=50)
   try:j=r.json() if r.content else {}
   except ValueError:j=dict(non_json_response=True)
   e.update(http=r.status_code,response=j,wb_writes=1,status='accepted' if r.ok else 'rejected');save()
  except Exception:
   e.update(status='uncertain',reason='No response: never repeat PATCH');save()
 if e['status'] in ['accepted','submitting','uncertain','readback_pending']:
  for attempt in range(16):
   after=current(io,[CID])[CID]
   if matches(after):
    e.update(status='verified',after=after,verified_at=stamp(),budget_after=budget());save();break
   if attempt==15:e.update(status='readback_pending',after=after);save();break
   time.sleep(8)
 if e['status']=='verified':
  key='china_agent:search_test:2026-10-25:tracking:v1';t=io.get(key);assert t['campaign_id']==CID
  if not any(x.get('execution_key')==EXE for x in t.get('owner_changes',[])):
   t.setdefault('owner_changes',[]).append(dict(kind='sku_exclusion_batch',nm_ids=sorted(APPROVED),campaign_id=CID,verified_at=e['verified_at'],execution_key=EXE))
  t.setdefault('original_launch_items',t.get('items',[]))
  t.update(items=[x for x in t.get('items',[]) if x['nm_id'] in wanted],active_nm_ids=sorted(wanted),active_sku_count=33,last_composition_change_at=e['submitted_at'],composition_baseline_at=e['baseline_observed_at'],composition_baseline_execution_key=EXE,latest_campaign=e['after'],last_checked_at=e['verified_at'])
  io.put(key,t)
 print(json.dumps(dict(status=e['status'],wb_writes=e['wb_writes'],funding_writes=0,telegram_sends=0)))
if __name__=='__main__':run()
