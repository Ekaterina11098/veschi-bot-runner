"""Execute a dated private owner approval once; no budgets, prices or Telegram writes."""
import copy,json,os,time,hashlib
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
ROOT='china_agent:owner_umbrella_apply:2026-11-01:v1'
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def projection(c):return {k:copy.deepcopy(c[k])for k in ['id','status','currency','bid_type','settings','nm_settings']}
def approval(c):
 a=c.get(ROOT+':approval')or{}
 if a.get('status')!='approved' or a.get('owner_user_id')!=5122667182 or a.get('execution_authorized')is not True or a.get('cabinet')!='token_3' or a.get('source_channel')!='codex':raise ValueError('Owner approval absent')
 if datetime.now(timezone.utc)>=datetime.fromisoformat(a['expires_at']) or datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat()!='2026-11-01':raise ValueError('Approval expired')
 if digest(a['actions'])!=a['scope_sha256'] or len(a['actions'])!=2 or sorted(x['kind']for x in a['actions'])!=['exclude','pause']:raise ValueError('Scope mismatch')
 if len(next(x for x in a['actions']if x['kind']=='exclude')['items'])!=3:raise ValueError('Exactly three exclusions authorized')
 return a
def expected(before,x):
 if before['status']!=9 or before['currency']!='CNY' or before['settings']['payment_type']!='cpc' or before['bid_type']!='manual':raise ValueError('Campaign mode changed')
 if projection(before)!=x['expected_before']:raise ValueError('Campaign state changed since proposal')
 out=copy.deepcopy(before)
 if x['kind']=='pause':out['status']=11
 elif x['kind']=='exclude':
  ids={i['nm_id']for i in x['items']}
  if not before.get('restrictions',{}).get('can_change_nms') or not ids<={n['nm_id']for n in before['nm_settings']}:raise ValueError('Membership changed or locked')
  out['nm_settings']=[n for n in out['nm_settings']if n['nm_id']not in ids]
  if not out['nm_settings']:raise ValueError('Empty campaign forbidden')
 else:raise ValueError('Unknown action')
 return out
def mutation(x):
 cid=x['campaign_id']
 if x['kind']=='pause':return '/adv/v0/pause?id='+str(cid),'GET',None
 if x['kind']=='exclude':return '/adv/v0/auction/nms','PATCH',dict(nms=[dict(advert_id=cid,nms=dict(add=[],delete=[i['nm_id']for i in x['items']]))])
 raise ValueError('Unknown mutation')
class ScopedWB(WB):
 def __init__(self,actions):super().__init__();self.actions=actions
 def req(self,path,method='GET',body=None,write=False):
  if write and not any(mutation(x)==(path,method,body)for x in self.actions):raise ValueError('Unapproved mutation')
  return super().req(path,method,body,write)
def put(c,k,v):
 c.put(k,v)
 if c.get(k)!=json.loads(json.dumps(v)):raise ValueError('Private receipt readback mismatch')
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Wrong repository')
 c=Cache();a=approval(c)
 prior=c.get(ROOT+':execution')
 if prior:
  if prior.get('status')!='blocked' or prior.get('wb_writes')!=0 or prior.get('steps'):print('Existing execution; no replay');return
  if not c.create(ROOT+':preflight_recovery_lease',dict(started_at=stamp())):return
 w=ScopedWB(a['actions']);validate_identity(c,w)
 e=dict(status='preflight',approval_key=ROOT+':approval',scope_sha256=a['scope_sha256'],steps={},wb_writes=0,budget_writes=0,price_writes=0,telegram_calls=0,created_at=stamp())
 if prior:e['prior_preflight_attempt']=prior;put(c,ROOT+':execution',e)
 elif not c.create(ROOT+':execution',e):return
 def save():put(c,ROOT+':execution',e)
 try:
  from china_advertising_state import AdvertisingIO
  from china_moysklad_read import read_stock
  items=[i for x in a['actions']for i in x.get('items',[])]
  class Prices(AdvertisingIO):
   def __init__(self,token):self.token=token
  e['prices']=Prices(w.token).prices([i['nm_id']for i in items]);e['stock']=read_stock([i['article']for i in items]);e['preflight_at']=stamp()
  states=w.campaigns([x['campaign_id']for x in a['actions']]);e['before']=states;e['minimums']={}
  for x in a['actions']:
   expected(states[str(x['campaign_id'])],x)
   if x['kind']=='exclude':
    mins=w.minimums(x['campaign_id'],[i['nm_id']for i in x['items']],'search');e['minimums']=mins
    for i in x['items']:
     g=e['prices'][str(i['nm_id'])]
     if g['vendorCode']!=i['article'] or {s['discountedPrice']for s in g['sizes']}!={i['price_cny']} or g['currencyIsoCode4217']!='CNY':raise ValueError('Seller price changed')
     if mins[i['nm_id']]<i['old_minor']:raise ValueError('Cheaper search bid alternative appeared')
  e['status']='applying';save()
  for x in a['actions']:
   approval(c);cid=x['campaign_id'];key=ROOT+':'+str(cid)+':execution'
   if c.get(key):raise ValueError('Existing child; never replay')
   before=w.campaigns([cid])[str(cid)];target=expected(before,x);path,method,body=mutation(x)
   step=dict(status='submitting',before=before,expected=target,action=x,parent=ROOT+':execution',submitted_at=stamp())
   if not c.create(key,step):raise ValueError('Concurrent child')
   e['steps'][str(cid)]=key;save()
   try:
    e['wb_writes']+=1;save();step['response']=w.req(path,method,body,write=True);step['status']='accepted';put(c,key,step)
    for attempt in range(4):
     after=w.campaigns([cid])[str(cid)];step['after']=after
     if projection(after)==projection(target):break
     if attempt<3:time.sleep(3)
    else:raise ValueError('WB readback mismatch; never repeat')
    step.update(status='verified',verified_at=stamp());put(c,key,step)
    reg=c.get('china_agent:verified_campaign_state:v1')or{};reg[str(cid)]=key;put(c,'china_agent:verified_campaign_state:v1',reg)
   except Exception as ex:
    step.update(status='uncertain',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__);put(c,key,step);raise
  e.update(status='verified',completed_at=stamp());save()
 except Exception as ex:
  e.update(status='partial_or_uncertain'if e['steps']else'blocked',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__,completed_at=stamp());save()
 print(json.dumps({k:e.get(k)for k in ['status','wb_writes','reason']}))
if __name__=='__main__':main()