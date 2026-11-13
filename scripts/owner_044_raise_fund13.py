"""Exact owner-approved 044 bid and350 CNY funding; independent no-replay journals."""
import copy,json,os,time,requests
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity,stamp,projection
from china_moysklad_read import read_stock
from china_loss_control import digest
ROOT='china_agent:owner_044_raise_fund:2026-11-13:v1'
CID=40933588;NM=1473243894
BID={'bids':[{'advert_id':CID,'nm_bids':[{'nm_id':NM,'placement':'recommendations','bid_kopecks':38}]}]}
def norm(v):return json.loads(json.dumps(v))
class ExactWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write:
   if (method,path,body) not in [('PATCH','/api/advert/v1/bids',BID),('POST','/adv/v1/budget/deposit?id=40933588',{'sum':350,'type':0})]:raise ValueError('Outside owner write scope')
  elif (method,path.split('?')[0]) not in [('GET','/api/advert/v2/adverts'),('GET','/api/advert/v1/config'),('GET','/adv/v1/balance'),('POST','/api/advert/v2/budget'),('POST','/api/advert/v1/bids/min')]:raise ValueError('Outside exact reads')
  time.sleep(1.3)
  r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':self.token},json=body,timeout=50)
  if not r.ok:raise RuntimeError('WB HTTP '+str(r.status_code))
  return r.json() if r.content else {}
def budget(w):
 rows=w.req('/api/advert/v2/budget','POST',{'advertIds':[CID]})['adverts']
 if len(rows)!=1 or rows[0]['advertId']!=CID or rows[0]['currency']!='CNY':raise ValueError('Budget identity')
 return rows[0]['total']
def main():
 c=Cache();auth=c.get(ROOT+':approval')or{}
 if auth.get('execution_authorized')is not True or auth.get('owner_id')!=5122667182 or auth.get('scope')!={'campaign_id':CID,'nm_id':NM,'old_minor':36,'target_minor':38,'placement':'recommendations','amount_cny':350,'fund_type':0} or datetime.now(timezone.utc)>=datetime.fromisoformat(auth['expires_at']):raise ValueError('Fresh exact owner approval required')
 prior=c.get(ROOT+':execution')
 if prior:print(json.dumps({'status':prior.get('status'),'no_replay':True}));return
 w=ExactWB();validate_identity(c,w)
 e=dict(status='preflight',approval_key=ROOT+':approval',created_at=stamp(),wb_writes=0,steps={},grants_action_permission=False)
 if not c.create(ROOT+':execution',e):return
 def save():c.put(ROOT+':execution',norm(e))
 def raw(url,body=None):
  r=requests.request('POST' if body else 'GET',url,headers={'Authorization':w.token},json=body,timeout=45)
  if not r.ok:raise RuntimeError('Input HTTP '+str(r.status_code))
  return r.json()
 def child(key,v):
  if c.get(key):c.put(key,norm(v))
  elif not c.create(key,norm(v)):raise ValueError('Child claimed')
 try:
  cp=w.campaigns([CID])[str(CID)];e['before']=cp
  if cp['status']!=9 or cp['currency']!='CNY' or cp['bid_type']!='manual' or cp['settings']['payment_type']!='cpc' or cp['settings']['placements']!={'search':False,'recommendations':True}:raise ValueError('Campaign mode changed')
  ns=next(n for n in cp['nm_settings']if n['nm_id']==NM);old=ns['bids_kopecks']['recommendations']
  if old not in (36,38):raise ValueError('Approved old bid changed')
  e['already_target']=old==38
  p=raw('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter?limit=1&filterNmID='+str(NM))['data']['listGoods']
  if len(p)!=1 or p[0]['nmID']!=NM or p[0]['vendorCode']!='044-NoelBag-black' or p[0]['currencyIsoCode4217']!='CNY' or {r['discountedPrice']for r in p[0]['sizes']}!={221.1}:raise ValueError('Price changed')
  st=read_stock(['044-NoelBag-black']);e['stock']=st;e['price']=p
  if not st['coverage_complete'] or len(st['rows'])!=1:raise ValueError('Stock incomplete')
  sr=st['rows'][0]
  if sr['stock']-sr['reserve']<=0 or not sr['price']:raise ValueError('Availability/COGS')
  sizes=[r['sizeID']for r in p[0]['sizes']];pub=raw('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',{'chrtIds':sizes});e['published_stock']=pub
  if {r['chrtId']for r in pub['stocks']}!=set(sizes) or sum(r['amount']for r in pub['stocks'])<=0:raise ValueError('Published availability')
  margin=(221.1*.72-sr['price']/100/12.4009)*60/91-12.9;e['preliminary_margin_before_ads_cny']=margin
  if margin<40:raise ValueError('Economics materially changed')
  cfg=w.req('/api/advert/v1/config');wallet=w.req('/adv/v1/balance');minimum=w.minimums(CID,[NM],'recommendations')[NM];bb=budget(w)
  e.update(config=cfg,wallet_before=wallet,minimum_minor=minimum,before_budget=bb);save()
  if cfg['currency']!='CNY' or wallet['currency']!='CNY' or minimum>38 or 38%cfg['cpcStep'] or 38>cfg['cpcMaxBid'] or cfg['minTopUp']>35000:raise ValueError('Currency/minimum/step changed')
  if wallet.get('balance',0)<350:raise ValueError('Insufficient cash balance; do not switch funding source')
  if bb>2580:raise ValueError('New funding since proposal; prevent duplicate')
  expected=copy.deepcopy(cp);next(n for n in expected['nm_settings']if n['nm_id']==NM)['bids_kopecks']['recommendations']=38
  if projection(w.campaigns([CID])[str(CID)])!=projection(cp):raise ValueError('Concurrent campaign change')
  fk=ROOT+':funding';fund=dict(status='submitting',before=cp,before_budget=bb,amount_cny=350,submitted_at=stamp())
  if not c.create(fk,norm(fund)):raise ValueError('Funding receipt exists; no replay')
  e['steps']['funding']=fk;e['wb_writes']+=1;save()
  try:
   fund['response']=w.req('/adv/v1/budget/deposit?id=40933588','POST',{'sum':350,'type':0},write=True);fund['status']='accepted';child(fk,fund)
   for i in range(4):
    ab=budget(w);fund['after_budget']=ab
    if bb+348<=ab<=bb+350:break
    if i<3:time.sleep(3)
   else:raise ValueError('Funding readback uncertain; never repeat')
   afterfund=w.campaigns([CID])[str(CID)];fund['after']=afterfund
   if projection(afterfund)!=projection(cp):raise ValueError('Concurrent settings change during funding')
   fund.update(status='verified',verified_at=stamp());child(fk,fund)
  except Exception:
   fund.update(status='uncertain');child(fk,fund);raise
  bk=ROOT+':bid';bid=dict(status='submitting',before=cp,expected=expected,body=BID,submitted_at=stamp())
  if not c.create(bk,norm(bid)):raise ValueError('Bid receipt exists; no replay')
  e['steps']['bid']=bk;save()
  try:
   if old==38:bid['already_done']=True
   else:
    e['wb_writes']+=1;save();bid['response']=w.req('/api/advert/v1/bids','PATCH',BID,write=True);bid['status']='accepted';child(bk,bid)
   for i in range(4):
    after=w.campaigns([CID])[str(CID)];bid['after']=after
    if projection(after)==projection(expected):break
    if i<3:time.sleep(3)
   else:raise ValueError('Bid readback uncertain; never repeat')
   bid.update(status='verified',verified_at=stamp(),items=[dict(kind='ad_set_bid',campaign_id=CID,nm_id=NM,article='044-NoelBag-black',placement='recommendations',old_minor=old,target_minor=38)]);child(bk,bid)
   registry=c.get('china_agent:verified_campaign_state:v1')or{};registry[str(CID)]=bk;c.put('china_agent:verified_campaign_state:v1',norm(registry))
  except Exception:
   bid.update(status='uncertain');child(bk,bid);raise
  e.update(status='verified',after=bid['after'],verified_at=stamp(),completed_at=stamp(),final_budget=budget(w),items=[dict(bid,id='bid044'),dict(fund,id='fund350')]);save()
  from china_execution_notice import deliver_registered
  class NoticeIO:
   def get(self,k):return c.get(k)
   def create(self,k,v):return c.create(k,norm(v))
   def put(self,k,v):c.put(k,norm(v))
   def tg(self,method,body):
    if method!='sendMessage' or body.get('chat_id')!=-1004342917488:raise ValueError('Completion destination')
    body.pop('reply_parameters',None)
    r=requests.post('https://api.telegram.org/bot'+os.environ['TELEGRAM_BOT_TOKEN']+'/sendMessage',json=body,timeout=45)
    if not r.ok:raise RuntimeError('Telegram HTTP '+str(r.status_code))
    return r.json()['result']
  contract=c.get(ROOT+':completion_contract');e['completion_notice']=dict(authorization_key=contract['authorization_key'],plan=contract['plan'],approval=contract['approval']);save()
  notice=deliver_registered(NoticeIO(),ROOT+':execution',e);e['delivery']=dict(status=(notice or{}).get('status'),message_id=(notice or{}).get('message_id'));save()
 except Exception as ex:
  e.update(status='delivery_attention' if e.get('status')=='verified' else 'partial_or_uncertain' if e['wb_writes'] else 'blocked',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__,completed_at=stamp());save()
 print(json.dumps({k:e.get(k)for k in ['status','reason','wb_writes','final_budget','delivery']}))
if __name__=='__main__':main()

