"""One owner-approved 21-SKU cross-placement test; no automatic re-funding or pauses."""
import os,json,copy,time,math
from datetime import datetime,timezone
import requests
from china_cloud_cost_control import Cache,validate_identity
KEY='china_agent:owner_search_expand:2026-10-26:v4:execution'
ARTICLES=['143-ReginaBag-black','447-AngelaBag-burgundy','595-Noelbag-zblack','600-JessicaBag-blue','044-NoelBag-black','673-NoelBag-green','58-NoelBag-brown','208-AngelaBag-black','36-EthelBag-brown','267-AmiraBag-beige','623-AngelaBag-brown','523-AngelaBag-black','680-VivienneBag-black','594-NoelBag-green','2-FurPanama-black','8-FurPanama-pink','92-Zont-red','64-Zont-cream-beige','114-Zont-Iblue','65-Zont-lilac-cream','26-Zont-green']
class Wire:
 def __init__(self):self.token=os.environ['WB_TOKEN_3']
 def req(self,path,method='GET',body=None):
  permitted={('GET','/adv/v1/promotion/count'),('GET','/api/advert/v2/adverts'),('GET','/api/advert/v1/config'),('POST','/api/advert/v2/budget'),('POST','/api/advert/v1/bids/min'),('PATCH','/adv/v0/auction/nms'),('PATCH','/api/advert/v1/bids'),('POST','/adv/v2/seacat/save-ad'),('PUT','/api/advert/v0/daily-limits'),('GET','/api/advert/v0/daily-limits'),('POST','/adv/v1/budget/deposit'),('GET','/adv/v0/start')}
  if (method,path.split('?')[0]) not in permitted:raise RuntimeError('Endpoint outside exact owner scope')
  time.sleep(2);r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':self.token},json=body,timeout=50)
  if not r.ok:raise RuntimeError('WB HTTP '+str(r.status_code))
  return r.json() if r.content else {}
 def campaigns(self,ids):return {str(x['id']):x for x in self.req('/api/advert/v2/adverts?ids='+','.join(map(str,ids)))['adverts']}
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise RuntimeError('Public main only')
 c=Cache();w=Wire();validate_identity(c,w)
 key='china_agent:owner_search_fund:2026-10-26:v1:execution'
 approval=c.get('china_agent:owner_search_fund:2026-10-26:v1:approval') or {}
 if approval.get('status')!='approved' or approval.get('amounts')!={'41325622':100,'41325637':100} or approval.get('start') is not True:raise RuntimeError('Exact funding approval missing')
 if c.get(key):print('Existing execution: never repeat writes');return
 parent=c.get('china_agent:owner_search_expand:2026-10-26:v4:execution') or {}
 if parent.get('status')!='drafts_verified_unfunded':raise RuntimeError('Verified draft plan missing')
 e=dict(status='preflight',owner_quote='подтверждаю пополнение',owner_id=5122667182,steps={},campaigns=[],total_deposit_cny=0,telegram_sends=0,created_at=datetime.now(timezone.utc).isoformat())
 if not c.create(key,e):return
 def save():c.put(key,json.loads(json.dumps(e)))
 def write(step,path,method,body=None):
  if step in e['steps']:raise RuntimeError('Never repeat an existing write')
  e['steps'][step]=dict(status='submitting',path=path,method=method,body=body);save()
  try:r=w.req(path,method,body)
  except Exception:e['steps'][step]['status']='uncertain';save();raise
  e['steps'][step].update(status='accepted',response=r);save()
 def budget(cid):
  rows=w.req('/api/advert/v2/budget','POST',dict(advertIds=[cid]))['adverts']
  if len(rows)!=1 or rows[0].get('currency')!='CNY':raise RuntimeError('Exact CNY budget missing')
  return rows[0]['total']
 try:
  cfg=w.req('/api/advert/v1/config')
  if cfg.get('currency')!='CNY' or max(cfg.get('minTopUp',0),cfg.get('minDailyLimit',0))>10000:raise RuntimeError('Fresh minimum exceeds approved100CNY')
  # Validate BOTH exact drafts before any financial mutation.
  for cid in [41325622,41325637]:
   prior=next(x for x in parent['campaigns'] if x['campaign_id']==cid)
   before=w.campaigns([cid])[str(cid)]
   if before['status']!=4 or before['currency']!='CNY' or before['settings']!=prior['after']['settings'] or before['nm_settings']!=prior['after']['nm_settings']:raise RuntimeError('Draft changed since approval')
   b=budget(cid)
   if b!=0:raise RuntimeError('Draft already funded; do not deposit again')
   e['campaigns'].append(dict(campaign_id=cid,before=before,items=prior['items'],baseline_budget=b,status='preflight'));save()
  for state in e['campaigns']:
   cid=state['campaign_id'];p=str(cid)
   write('limit:'+p,'/api/advert/v0/daily-limits','PUT',dict(advertIds=[cid],enabled=True,dailyLimit=10000,carryOverEnabled=False))
   rows=w.req('/api/advert/v0/daily-limits?advertIds='+p)['adverts']
   if len(rows)!=1 or rows[0].get('dailyLimit')!=10000 or rows[0].get('enabled')is not True or rows[0].get('carryOverEnabled')is not False:raise RuntimeError('Daily limit readback failed')
   e['steps']['limit:'+p]['status']='verified';save()
   if budget(cid)!=0:raise RuntimeError('Balance changed before deposit')
   write('deposit:'+p,'/adv/v1/budget/deposit?id='+p,'POST',dict(sum=100,type=0))
   b=budget(cid);state['balance_after_deposit']=b
   if b!=100:raise RuntimeError('Deposit readback mismatch; never repeat')
   e['steps']['deposit:'+p]['status']='verified';e['total_deposit_cny']+=100;save()
   write('start:'+p,'/adv/v0/start?id='+p,'GET')
   after=w.campaigns([cid])[p];state['after']=after
   if after['status']!=9 or after['settings']!=state['before']['settings'] or after['nm_settings']!=state['before']['nm_settings']:raise RuntimeError('Active state/composition not confirmed; never repeat start')
   e['steps']['start:'+p]['status']='verified';state['status']='verified_active';save()
  e['status']='verified'
 except Exception as ex:
  e.update(status='uncertain' if any(x.get('status')in ['submitting','uncertain','accepted'] for x in e['steps'].values()) else 'blocked',reason=str(ex) if isinstance(ex,RuntimeError) else type(ex).__name__)
 finally:
  e['completed_at']=datetime.now(timezone.utc).isoformat();save()
  registry=c.get('china_agent:verified_campaign_state:v1') or {}
  for state in e['campaigns']:
   if state.get('status')=='verified_active':
    receipt='china_agent:owner_search_fund:2026-10-26:'+str(state['campaign_id'])+':execution'
    c.put(receipt,dict(status='verified',before=state['before'],after=state['after'],items=state['items'],funded_cny=100,verified_at=e['completed_at'],parent=key))
    registry[str(state['campaign_id'])]=receipt
  c.put('china_agent:verified_campaign_state:v1',registry)
  print('Funding result saved privately: '+e['status'])
if __name__=='__main__':run()
