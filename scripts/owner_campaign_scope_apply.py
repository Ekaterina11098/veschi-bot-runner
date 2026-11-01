"""Apply one privately approved campaign scope once; no funding, prices or Telegram."""
import copy,json,hashlib,os,time
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
ROOT='china_agent:owner_campaign_scope_apply:2026-11-02:v1'
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def project(cp):
 return dict(id=cp['id'],status=cp['status'],currency=cp['currency'],bid_type=cp['bid_type'],settings=cp['settings'],members={str(n['nm_id']):dict(subject=n['subject']['id'],bids=n['bids_kopecks'])for n in cp['nm_settings']})
def put(c,k,v):c.put(k,json.loads(json.dumps(v)))
def approval(c):
 a=c.get(ROOT+':approval')or{}
 if a.get('status')!='approved'or a.get('execution_authorized')is not True or a.get('owner_user_id')!=5122667182 or a.get('cabinet')!='token_3':raise ValueError('Exact approval absent')
 if datetime.now(timezone.utc)>=datetime.fromisoformat(a['expires_at']):raise ValueError('Approval expired')
 if digest(a['actions'])!=a['scope_sha256']:raise ValueError('Approval hash changed')
 if sorted(x['kind']for x in a['actions'])!=['bids','exclude']or len(a['actions'][0]['items'])!=5 or len(a['actions'][1]['items'])!=1:raise ValueError('Scope cardinality changed')
 return a
def mutation(cid,x):
 if x['kind']=='exclude':return '/adv/v0/auction/nms',dict(nms=[dict(advert_id=cid,nms=dict(add=[],delete=[i['nm_id']for i in x['items']]))])
 if x['kind']=='bids':return '/api/advert/v1/bids',dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=i['nm_id'],placement='recommendations',bid_kopecks=i['target_minor'])for i in x['items']])])
 raise ValueError('Unapproved mutation')
def expected(before,x):
 after=copy.deepcopy(before);members={n['nm_id']:n for n in after['nm_settings']}
 if any(i['nm_id']not in members for i in x['items']):raise ValueError('Approved member absent; no replay')
 if x['kind']=='exclude':after['nm_settings']=[n for n in after['nm_settings']if n['nm_id']not in {i['nm_id']for i in x['items']}]
 else:
  for i in x['items']:
   if members[i['nm_id']]['bids_kopecks']['recommendations']!=i['old_minor']:raise ValueError('Bid changed since approval')
   members[i['nm_id']]['bids_kopecks']['recommendations']=i['target_minor']
 return after
class ScopedWB(WB):
 def __init__(self,cid,actions):super().__init__();self.cid=cid;self.actions=actions
 def req(self,path,method='GET',body=None,write=False):
  if write and(method!='PATCH'or not any(mutation(self.cid,x)==(path,body)for x in self.actions)):raise PermissionError('Mutation outside exact owner scope')
  return super().req(path,method,body,write)
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner'or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Wrong deployment')
 c=Cache();a=approval(c);cid=a['campaign_id'];actions=a['actions']
 if c.get(ROOT+':execution'):print('Existing execution; no replay');return
 w=ScopedWB(cid,actions);validate_identity(c,w)
 e=dict(status='preflight',approval_key=ROOT+':approval',scope_sha256=a['scope_sha256'],steps={},items=[],wb_writes=0,budget_writes=0,price_writes=0,telegram_calls=0,created_at=stamp())
 if not c.create(ROOT+':execution',e):return
 def save():put(c,ROOT+':execution',e)
 try:
  from china_advertising_state import AdvertisingIO
  from china_moysklad_read import read_stock
  class Prices(AdvertisingIO):
   def __init__(self,token):self.token=token
  before=w.campaigns([cid])[str(cid)];e['before']=before
  if project(before)!=a['expected_before']:raise ValueError('Campaign changed since reviewed source')
  if before['status']!=9 or before['currency']!='CNY' or before['settings']['payment_type']!='cpc' or not before.get('restrictions',{}).get('can_change_nms'):raise ValueError('Campaign mode or membership locked')
  items=[i for x in actions for i in x['items']];e['prices']=Prices(w.token).prices([i['nm_id']for i in items]);e['stock']=read_stock([i['article']for i in items]);mins=w.minimums(cid,[i['nm_id']for i in items],'recommendations');e['minimums']=mins
  for x in actions:
   for i in x['items']:
    price=e['prices'][str(i['nm_id'])]
    if price['vendorCode']!=i['article']or price['currencyIsoCode4217']!='CNY'or {z['discountedPrice']for z in price['sizes']}!={i['price_cny']}:raise ValueError('Price/identity changed')
    if x['kind']=='bids'and mins[i['nm_id']]>i['target_minor']:raise ValueError('Target below minimum')
    if x['kind']=='exclude'and mins[i['nm_id']]<i['old_minor']:raise ValueError('Lower bid alternative appeared')
  e['preflight_at']=stamp();e['status']='applying';save();state=before
  for x in actions:
   approval(c);live=w.campaigns([cid])[str(cid)]
   if project(live)!=project(state):raise ValueError('Concurrent state change')
   target=expected(live,x);key=ROOT+':'+str(cid)+':'+x['kind']+':execution';step=dict(status='submitting',before=live,expected=target,items=x['items'],parent=ROOT+':execution',submitted_at=stamp())
   if not c.create(key,step):raise ValueError('Existing child; no replay')
   e['steps'][x['kind']]=key;save()
   try:
    path,body=mutation(cid,x);e['wb_writes']+=1;save();step['response']=w.req(path,'PATCH',body,write=True);step['status']='accepted';put(c,key,step)
    for attempt in range(4):
     after=w.campaigns([cid])[str(cid)];step['after']=after
     if project(after)==project(target):break
     if attempt<3:time.sleep(3)
    else:raise ValueError('WB readback mismatch; no repeat')
    step.update(status='verified',verified_at=stamp());put(c,key,step);state=after;e['items']+=x['items'];save()
   except Exception as ex:
    step.update(status='uncertain',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__);put(c,key,step);raise
  combined=ROOT+':'+str(cid)+':execution';receipt=dict(status='verified',before=before,after=state,items=e['items'],child_keys=list(e['steps'].values()),parent=ROOT+':execution',verified_at=stamp())
  if not c.create(combined,receipt):raise ValueError('Combined receipt exists')
  registry=c.get('china_agent:verified_campaign_state:v1')or{};registry[str(cid)]=combined;put(c,'china_agent:verified_campaign_state:v1',registry)
  e.update(status='verified',after=state,completed_at=stamp());save()
  try:e['owner_archived_campaign_readback']=w.campaigns([a['archive_campaign_id']])[str(a['archive_campaign_id'])];save()
  except Exception as ex:e['archive_read_error']=type(ex).__name__;save()
 except Exception as ex:
  e.update(status='partial_or_uncertain'if e['steps']else'blocked',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError,PermissionError))else type(ex).__name__,completed_at=stamp());save()
 print(json.dumps({k:e.get(k)for k in ['status','wb_writes','reason']}))
if __name__=='__main__':main()

