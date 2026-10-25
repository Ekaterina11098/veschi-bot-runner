"""Execute exact owner-approved plan; two bulk writes maximum, no funding or sends."""
import os,json,time,base64,copy,requests
from datetime import datetime,timezone
from china_loss_execute import IO as OriginalIO
from china_loss_ads import current,nmset
from china_loss_control import digest
from china_ad_rule import minimums
REQ='china_agent:codex_late_campaign_changes:2026-10-25:v1'
EXE=REQ+':execution'
EXPECTED_HASH='2908cdba8b88e90204c801532af1947cadeca63de4c852efcf4cf59543a9bd79'
def stamp():return datetime.now(timezone.utc).isoformat()
class IO(OriginalIO):
 def tg(self,method,body):
  if method not in ['getMe','getChatMember']:raise PermissionError('No Telegram sends')
  return super().tg(method,body)
 def validate_owner(self,p):
  assert p['status']=='approved' and p['source']=='explicit_human_codex_message'
  assert digest(p['items'])==EXPECTED_HASH and len(p['items'])==15
  assert p['human_quote']=='Делаем предложенные снижения ставок и исключения, остальные оставляем и наблюдаем. Бюджеты пока не меняем.'
  assert p['budget_increase'] is False and p['auto_topup'] is False and p['funding_writes']==0 and p['price_changes'] is False
  assert self.db('business_agent_config?agent_id=eq.china&select=active,chat_id,bot_id,owner_user_id')==[dict(active=True,chat_id=-1004342917488,bot_id=8780468043,owner_user_id=5122667182)]
  me=self.tg('getMe',{});assert me['id']==8780468043
  member=self.tg('getChatMember',dict(chat_id=-1004342917488,user_id=5122667182))
  assert member['user']['id']==5122667182 and member['user'].get('is_bot') is False
  assert member.get('status') in ['creator','administrator','member'] or member.get('status')=='restricted' and member.get('is_member') is True
  claims=json.loads(base64.urlsafe_b64decode(self.token.split('.')[1]+'='*(-len(self.token.split('.')[1])%4)))
  assert claims.get('t') is False and claims.get('exp',0)>time.time() and not int(claims.get('s',0))&(1<<30)
  ids=self.db('analytics_snapshots?cabinet=eq.token_3&source=eq.seller_identity&status=eq.complete&select=payload&limit=100')
  assert {x['payload'].get('sid') for x in ids}=={claims.get('sid')}

def same(a,b):
 return a['id']==b['id'] and all(a.get(k)==b.get(k) for k in ['status','currency','bid_type','settings']) and sorted(a['nm_settings'],key=lambda n:n['nm_id'])==sorted(b['nm_settings'],key=lambda n:n['nm_id'])
def run():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner'
 io=IO();p=io.get(REQ);io.validate_owner(p)
 assert datetime.now(timezone.utc)<datetime.fromisoformat(p['expires_at'])
 ids=sorted({x['campaign_id'] for x in p['items']})
 e=io.get(EXE)
 def save():io.put(EXE,json.loads(json.dumps(e)))
 def budget():
  time.sleep(1.5)
  r=requests.post('https://advert-api.wildberries.ru/api/advert/v2/budget',headers={'Authorization':io.token},json=dict(advertIds=ids),timeout=50)
  assert r.ok,'Budget read unavailable'
  return r.json()
 if not e:
  cached=io.get('china_agent:all_campaigns_owner_review:2026-10-25:late:v1')
  assert cached['campaigns']['http']==200 and cached['fullstats_0']['http']==200
  saved={c['id']:c for c in cached['campaigns']['data']['adverts'] if c['id'] in ids}
  before=current(io,ids)
  for cid in ids:
   c=before[cid];assert same(c,saved[cid]),'Saved campaign changed: no write'
   assert c['status']==9 and c['currency']=='CNY' and c['bid_type']=='manual' and c['settings']['payment_type']=='cpc'
   assert c['restrictions']['can_change_nms']
  for item in p['items']:
   c=before[item['campaign_id']];nm=next(n for n in c['nm_settings'] if n['nm_id']==item['nm_id'])
   assert nm['bids_kopecks'][item['placement']]==item['old_minor']
   assert c['settings']['placements']==dict(search=item['placement']=='search',recommendations=item['placement']=='recommendations')
  for cid in ids:
   selected=[x for x in p['items'] if x['campaign_id']==cid and x['kind']=='ad_set_bid']
   if selected:
    mins=minimums(io,cid,{x['nm_id'] for x in selected})
    assert all(mins[x['nm_id']]<=x['target_minor']<x['old_minor'] for x in selected),'Minimum changed: no writes'
  e=dict(status='preflight',plan_sha256=EXPECTED_HASH,before={str(k):v for k,v in before.items()},budget_before=budget(),stages={},wb_writes=0,funding_writes=0,telegram_sends=0,baseline_fullstats=cached['fullstats_0']['data'],baseline_observed_at=cached['fullstats_0']['observed_at'])
  assert io.create(EXE,e)
 expected=copy.deepcopy(e['before'])
 for stage,kind,path in [('exclusions','ad_exclude_sku','/adv/v0/auction/nms'),('bids','ad_set_bid','/api/advert/v1/bids')]:
  selected=[x for x in p['items'] if x['kind']==kind]
  for item in selected:
   c=expected[str(item['campaign_id'])]
   if kind=='ad_exclude_sku':c['nm_settings']=[n for n in c['nm_settings'] if n['nm_id']!=item['nm_id']]
   else:
    for n in c['nm_settings']:
     if n['nm_id']==item['nm_id']:n['bids_kopecks'][item['placement']]=item['target_minor']
  assert all(c['nm_settings'] for c in expected.values())
  state=e['stages'].get(stage)
  if state and state['status']=='verified':continue
  if state and state['status']=='rejected':break
  if not state:
   live=current(io,ids)
   previous=e['before'] if stage=='exclusions' else e['stages']['exclusions']['after']
   assert all(same(live[cid],previous[str(cid)]) for cid in ids),'State changed before write'
   assert datetime.now(timezone.utc)<datetime.fromisoformat(p['expires_at'])
   if kind=='ad_exclude_sku':
    body=dict(nms=[dict(advert_id=cid,nms=dict(add=[],delete=[x['nm_id'] for x in selected if x['campaign_id']==cid])) for cid in ids if any(x['campaign_id']==cid for x in selected)])
   else:
    body=dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=x['nm_id'],bid_kopecks=x['target_minor'],placement=x['placement']) for x in selected if x['campaign_id']==cid]) for cid in ids if any(x['campaign_id']==cid for x in selected)])
   state=dict(status='submitting',submitted_at=stamp(),path=path,body=body)
   e['stages'][stage]=state;e['status']='running';save()
   try:
    r=requests.patch('https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},json=body,timeout=50)
    try:j=r.json() if r.content else {}
    except ValueError:j=dict(non_json_response=True)
    e['wb_writes']+=1;state.update(status='accepted' if r.ok else 'rejected',http=r.status_code,response=j);save()
   except Exception:
    e['wb_writes']+=1;state.update(status='uncertain',reason='No response; never repeat write');save()
  if state['status']!='rejected':
   for attempt in range(8):
    got=current(io,ids)
    if all(same(got[cid],expected[str(cid)]) for cid in ids):
     state.update(status='verified',verified_at=stamp(),after={str(k):v for k,v in got.items()});save();break
    if attempt==7:state.update(status='readback_pending');save()
    else:time.sleep(6)
  if state['status']!='verified':break
 if all(e['stages'].get(k,{}).get('status')=='verified' for k in ['exclusions','bids']):
  e.update(status='verified',verified_at=stamp(),after=expected,budget_after=budget());save()
  registry=io.get('china_agent:verified_campaign_state:v1') or {}
  for cid in ids:
   key='china_agent:codex_late_campaign_state:'+str(cid)+':2026-10-25:v1:execution'
   receipt=dict(status='verified',before=e['before'][str(cid)],after=e['after'][str(cid)],verified_at=e['verified_at'],baseline_observed_at=e['baseline_observed_at'],baseline_fullstats=[x for x in e['baseline_fullstats'] if x['advertId']==cid],items=[x for x in p['items'] if x['campaign_id']==cid],parent_execution_key=EXE,wb_writes=0,actual_batch_writes=e['wb_writes'],funding_writes=0,telegram_sends=0)
   io.put(key,receipt);registry[str(cid)]=key
  io.put('china_agent:verified_campaign_state:v1',registry)
 else:e['status']='attention';save()
 print(json.dumps(dict(status=e['status'],stages={k:v['status'] for k,v in e['stages'].items()},wb_writes=e['wb_writes'],funding_writes=0,telegram_sends=0)))
if __name__=='__main__':run()
