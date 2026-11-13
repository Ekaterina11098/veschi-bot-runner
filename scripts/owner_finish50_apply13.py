"""Complete only owner-confirmed50 and two blocked deposits; no Telegram or repeat writes."""
import copy,json,os,time,math
from datetime import datetime,timezone,timedelta
from china_advertising_state import AdvertisingIO
from china_cloud_cost_control import Cache,WB,validate_identity
ROOT='china_agent:owner_finish50_funding:2026-11-13:v1'
AD='daily-2026-11-13-drr-0-buttons-ca9e3074dc3e315c3036f970-5122667182'
BU='daily-2026-11-13-budgets-1-buttons-b88ab41f93ebcb99501f107e-5122667182'
NM=1473243824;CID=41332083;BID=28
def stamp():return datetime.now(timezone.utc).isoformat()
def composition(c):return {n['nm_id']:n for n in c['nm_settings']}
def same(before,after,added=False):
 old=composition(before);new=composition(after)
 return after['id']==before['id'] and after['settings']==before['settings'] and after['status']==before['status']==9 and after['currency']==before['currency']=='CNY' and set(new)==set(old)|({NM}if added else set()) and all(new[n]==v for n,v in old.items())
class ScopedWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write:
   add=dict(nms=[dict(advert_id=CID,nms=dict(add=[NM],delete=[]))])
   remove=dict(nms=[dict(advert_id=CID,nms=dict(add=[],delete=[NM]))])
   bid=dict(bids=[dict(advert_id=CID,nm_bids=[dict(nm_id=NM,placement='search',bid_kopecks=BID)])])
   allowed=(method=='PATCH'and(path=='/adv/v0/auction/nms'and body in [add,remove]or path=='/api/advert/v1/bids'and body==bid))or(method=='POST'and path in ['/adv/v1/budget/deposit?id=40933588','/adv/v1/budget/deposit?id=41055480']and body.get('sum')==({40933588:700,41055480:100}[int(path.split('=')[1])])and body.get('type')in[0,1])
   if not allowed:raise ValueError('Owner scope exceeded')
  elif path.split('?')[0]not in ['/api/advert/v1/config','/adv/v1/balance']:
   return super().req(path,method,body,False)
  import requests
  time.sleep(1.6);r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':self.token},json=body,timeout=55)
  if not r.ok:raise RuntimeError('WB HTTP '+str(r.status_code))
  return r.json()if r.content else {}
def journal(io,key):
 old=io.get(key)
 if old:
  if old['status']=='verified':return old,False
  raise ValueError('Existing remainder receipt needs read-only reconciliation; no replay')
 state=dict(status='preflight',started_at=stamp(),wb_writes=0,telegram_calls=0)
 if not io.create(key,state):raise ValueError('Remainder claim lost')
 return state,True
def add50(io,w,source):
 key=ROOT+':addition';s,fresh=journal(io,key)
 if not fresh:return
 try:
  p=io.get('china_agent:loss_plan:v1:'+AD);item=next(x for x in p['items']if x['id']=='41332083:add:1473243824')
  assert (item['campaign_id'],item['nm_id'],item['target_minor'],item['placement'])==(CID,NM,BID,'search')
  original=io.get('china_agent:daily_ad_execution:v2:'+AD)
  excluded=next(x for x in original['items']if x['id']=='40933588:1473243824')
  blocked=next(x for x in original['items']if x['id']==item['id'])
  assert excluded['status']=='verified'and blocked['status']=='blocked'and blocked['reason']=='Exact minimum quote membership changed'
  assert NM in composition(excluded['before'])and NM not in composition(excluded['after'])
  quote=source['addition_bid_quotes']['41332083:1473243824:search']
  assert quote['bid_verified']is True and quote['target_minor']==BID and quote['quote_campaign_id']==40933588
  assert 0<=(datetime.now(timezone.utc)-datetime.fromisoformat(quote['observed_at'])).total_seconds()<7200
  before=w.campaigns([CID])[str(CID)];s.update(before=before,item=item,quote_basis='fresh_pre_exclusion_exact_quote_then_live_post_add_minimum');io.put(key,s)
  if NM in composition(before):
   assert composition(before)[NM]['bids_kopecks']['search']==BID
   s.update(status='verified',already_present=True,after=before,verified_at=stamp());io.put(key,s);return
  e=item['growth_evidence']
  assert before['status']==9 and before['currency']=='CNY'and before['bid_type']=='manual'and before['settings']['payment_type']=='cpc'and before['settings']['placements']['search']is True
  assert before['restrictions']['can_change_nms']and len(before['nm_settings'])<50 and {n['subject']['id']for n in before['nm_settings']}=={50}
  from china_morning_readiness import current_prices,published_stock
  from china_moysklad_read import read_stock
  from china_advertising_reserve import require
  prices=current_prices(io,[NM]);pr=prices['rows'][0];stock=read_stock([item['article']]);pub=published_stock(io,prices,[NM]);st=stock['rows'][0]
  assert pr['article'].casefold()==item['article'].casefold()and pr['seller_price']==e['price_cny']and stock['coverage_complete']and st['stock']-st['reserve']>0 and pub['amounts'][str(NM)]>0
  assert st['price']>0 and e['expected_margin_before_ads_cny']-e['buyout']*(st['price']/100-e['own_cogs_rub'])/e['fx_rub_per_cny']>0
  cfg=w.req('/api/advert/v1/config');assert cfg['currency']=='CNY'and BID%cfg['cpcStep']==0 and BID<=cfg['cpcMaxBid']
  s['reserve']=require(io,item);s['status']='submitting';io.put(key,s)
  s['response']=w.req('/adv/v0/auction/nms','PATCH',dict(nms=[dict(advert_id=CID,nms=dict(add=[NM],delete=[]))]),True);s['wb_writes']+=1;s['status']='accepted';io.put(key,s)
  for _ in range(12):
   after=w.campaigns([CID])[str(CID)]
   if NM in composition(after):break
   time.sleep(3)
  assert same(before,after,True)
  minimum=w.minimums(CID,[NM],'search')[NM];s['live_minimum_minor']=minimum;io.put(key,s)
  if minimum>BID:
   s['status']='rollback_submitting';io.put(key,s)
   w.req('/adv/v0/auction/nms','PATCH',dict(nms=[dict(advert_id=CID,nms=dict(add=[],delete=[NM]))]),True);s['wb_writes']+=1
   for _ in range(12):
    reverted=w.campaigns([CID])[str(CID)]
    if same(before,reverted):break
    time.sleep(3)
   assert same(before,reverted);s.update(status='rolled_back',after=reverted,reason='Live minimum exceeds approved28; no higher bid authorized');io.put(key,s);return
  if composition(after)[NM]['bids_kopecks']['search']!=BID:
   s['bid_phase']='submitting';io.put(key,s)
   s['bid_response']=w.req('/api/advert/v1/bids','PATCH',dict(bids=[dict(advert_id=CID,nm_bids=[dict(nm_id=NM,placement='search',bid_kopecks=BID)])]),True);s['wb_writes']+=1;s['bid_phase']='accepted';io.put(key,s)
  for _ in range(15):
   after=w.campaigns([CID])[str(CID)]
   if same(before,after,True)and composition(after)[NM]['bids_kopecks'].get('search')==BID:break
   time.sleep(3)
  assert same(before,after,True)and composition(after)[NM]['bids_kopecks'].get('search')==BID and composition(after)[NM]['bids_kopecks'].get('recommendations',0)==0
  s.update(status='verified',after=after,verified_at=stamp());io.put(key,s)
  reg=io.get('china_agent:verified_campaign_state:v1')or{};reg[str(CID)]=key;io.put('china_agent:verified_campaign_state:v1',reg)
 except Exception as e:
  s.update(status='uncertain'if s['status']in['submitting','accepted','rollback_submitting']else'blocked',reason=str(e),finished_at=stamp());io.put(key,s)
def fund(io,w,source,cid,amount):
 key=ROOT+':funding:'+str(cid);s,fresh=journal(io,key)
 if not fresh:return
 try:
  original=io.get('china_agent:daily_ad_execution:v2:'+BU);old=next(x for x in original['items']if x['id']=='topup:'+str(cid))
  assert old['status']=='blocked'and old['reason']=='Campaign composition changed since PNG'
  plan=io.get('china_agent:loss_plan:v1:'+BU);item=copy.deepcopy(next(x for x in plan['items']if x['id']==old['id']));assert item['amount_cny']==amount
  before=w.campaigns([cid])[str(cid)]
  adplan=io.get('china_agent:loss_plan:v1:'+AD);execution=io.get('china_agent:daily_ad_execution:v2:'+AD)
  expected=copy.deepcopy(next(c for b in source['batches'].values()for c in b['campaigns']['adverts']if c['id']==cid));emap=composition(expected)
  for action in adplan['items']:
   if action['campaign_id']!=cid:continue
   done=next(x for x in execution['items']if x['id']==action['id']);assert done['status']=='verified'
   if action['kind']=='ad_exclude_sku':emap.pop(action['nm_id'])
   elif action['kind']=='ad_add_sku':emap[action['nm_id']]=composition(done['after'])[action['nm_id']]
   else:emap[action['nm_id']]['bids_kopecks'][action['placement']]=action['target_minor']
  expected['nm_settings']=list(emap.values())
  assert composition(before)==composition(expected)and before['settings']==expected['settings']and before['status']==9
  from china_budget_ready_model import attach,validate_funding
  from china_advertising_v2 import history
  src=copy.deepcopy(source)
  for batch in src['batches'].values():
   batch['campaigns']['adverts']=[before if c['id']==cid else c for c in batch['campaigns']['adverts']]
  bundle=io.get('china_agent:advertising_artifacts:2026-11-13:v2')['bundle'];small=dict(budget_days=bundle['budget_days'],campaigns=[dict(id=cid)])
  refreshed=attach(small,src,history(src.get('executions',[])))['campaigns'][0]['campaign_budget_economics']
  assert refreshed['status']=='positive'and refreshed['ready']
  item['budget_evidence']=refreshed;item['nm_ids']=sorted(composition(before));io.daily_report_current_revalidation=True
  validate_funding(io,item,before)
  assert str(cid)not in(io.get('china_agent:budget_owner_policy:v1')or{}).get('do_not_fund',{})
  rows=w.req('/api/advert/v2/budget','POST',dict(advertIds=[cid]))['adverts'];assert len(rows)==1 and rows[0]['currency']=='CNY';balance=rows[0]['total']
  assert balance<=item['balance_before']+2
  cfg=w.req('/api/advert/v1/config');cash=w.req('/adv/v1/balance');assert cfg['currency']==cash['currency']=='CNY'and cfg['minTopUp']<=amount*100
  source_type=0 if cash.get('balance',0)>=amount else 1 if cash.get('net',0)>=amount else None
  assert source_type is not None
  s.update(status='submitting',before=before,before_budget=balance,amount_cny=amount,budget_evidence=refreshed);io.put(key,s)
  s['response']=w.req('/adv/v1/budget/deposit?id='+str(cid),'POST',dict(sum=amount,type=source_type),True);s['wb_writes']+=1;s['status']='accepted';io.put(key,s)
  for _ in range(15):
   after=w.campaigns([cid])[str(cid)];r=w.req('/api/advert/v2/budget','POST',dict(advertIds=[cid]))['adverts'][0]
   if same(before,after)and r['currency']=='CNY'and r['total']>=balance+amount-2:break
   time.sleep(3)
  assert same(before,after)and r['currency']=='CNY'and r['total']>=balance+amount-2
  s.update(status='verified',after=after,after_budget=r['total'],verified_at=stamp());io.put(key,s)
 except Exception as e:
  s.update(status='uncertain'if s['status']in['submitting','accepted']else'blocked',reason=str(e),finished_at=stamp());io.put(key,s)
def main():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner'and os.environ['GITHUB_REF']=='refs/heads/main'
 io=AdvertisingIO();assert io.get(ROOT+':notice_contract'),'A confirmed recovery must register its completion before marketplace work'
 w=ScopedWB();validate_identity(Cache(),w)
 approval=io.get(ROOT+':approval');assert approval['owner_id']==5122667182 and approval['source_channel']=='codex'and approval['status']=='approved'
 assert approval['addition']==dict(campaign_id=CID,nm_id=NM,target_minor=BID)and approval['funding']=={'40933588':700,'41055480':100}
 assert datetime.now(timezone.utc)<datetime.fromisoformat(approval['expires_at'])
 source=io.get('china_agent:advertising_source:2026-11-13:v2')
 add50(io,w,source)
 fund(io,w,source,40933588,700)
 fund(io,w,source,41055480,100)
 from china_execution_completion import complete
 complete(io,ROOT+':notice_contract')
 print(json.dumps({key:(io.get(ROOT+':'+key)or{}).get('status')for key in ['addition','funding:40933588','funding:41055480']}))
if __name__=='__main__':main()
