import copy,json,time,os,requests
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from china_cloud_cost_control import Cache,WB,validate_identity,projection,stamp
from china_moysklad_read import read_stock
ROOT='china_agent:owner_panama2_raise:2026-11-03:v2'
CID=41325622
NM=1535337770
BODY={'bids':[{'advert_id':CID,'nm_bids':[{'nm_id':NM,'placement':'search','bid_kopecks':12}]}]}
class ExactWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write and (path!='/api/advert/v1/bids' or method!='PATCH' or body!=BODY):raise ValueError('Write outside exact owner scope')
  return super().req(path,method,body,write)
def main():
 c=Cache();a=c.get(ROOT+':approval') or {}
 if a.get('owner_user_id')!=5122667182 or a.get('execution_authorized') is not True or a.get('campaign_id')!=CID or a.get('nm_id')!=NM or a.get('old_minor')!=11 or a.get('target_minor')!=12 or datetime.now(timezone.utc)>=datetime.fromisoformat(a['expires_at']):raise ValueError('Exact fresh owner approval missing')
 if c.get(ROOT+':execution'):print('Existing execution; never replay');return
 w=ExactWB();validate_identity(c,w)
 e=dict(status='preflight',created_at=stamp(),wb_writes=0,budget_writes=0,price_writes=0,telegram_calls=0,approval_key=ROOT+':approval')
 if not c.create(ROOT+':execution',e):return
 def save():c.put(ROOT+':execution',e)
 def raw(method,url,body=None):
  r=requests.request(method,url,headers={'Authorization':w.token},json=body,timeout=45)
  if not r.ok:raise RuntimeError('Read HTTP '+str(r.status_code))
  return r.json()
 try:
  cp=w.campaigns([CID])[str(CID)];e['before']=cp;save()
  if cp['status']!=9 or cp['currency']!='CNY' or cp['bid_type']!='manual' or cp['settings']['payment_type']!='cpc' or cp['settings']['placements']!={'search':True,'recommendations':False}:raise ValueError('Campaign mode changed')
  ns=next(n for n in cp['nm_settings'] if n['nm_id']==NM)
  if ns['bids_kopecks']['search']==12:e.update(status='already_target',completed_at=stamp());save();return
  if ns['bids_kopecks']['search']!=11:raise ValueError('Approved old bid changed')
  for k in (c.get('china_agent:verified_campaign_state:v1') or {}).values():
   rc=c.get(k) or {};at=rc.get('verified_at')
   if rc.get('status')!='verified' or not at:continue
   if datetime.fromisoformat(at.replace('Z','+00:00').replace(' UTC','+00:00')).astimezone(ZoneInfo('Europe/Moscow')).date()!=datetime.now(ZoneInfo('Europe/Moscow')).date():continue
   old={n['nm_id']:n for n in (rc.get('before') or {}).get('nm_settings',[])}
   for n in (rc.get('after') or {}).get('nm_settings',[]):
    if n['nm_id']==NM and (NM not in old or any(n['bids_kopecks'].get(p,0)>old[NM]['bids_kopecks'].get(p,0) for p in ['search','recommendations'])):raise ValueError('Product already raised today')
  st=read_stock(['2-FurPanama-black']);e['moysklad']=st;save()
  if not st['coverage_complete'] or len(st['rows'])!=1:raise ValueError('MSK coverage incomplete')
  sr=st['rows'][0]
  if sr.get('stock') is None or sr.get('reserve') is None or sr['stock']-sr['reserve']<=0 or not sr.get('price') or sr['price']<=0:raise ValueError('MSK free stock or COGS unavailable')
  price=raw('GET','https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter?limit=1&filterNmID='+str(NM));e['price']=price
  gs=price['data']['listGoods']
  if len(gs)!=1 or gs[0]['nmID']!=NM or gs[0]['vendorCode']!='2-FurPanama-black' or gs[0]['currencyIsoCode4217']!='CNY' or {s['discountedPrice'] for s in gs[0]['sizes']}!={105}:raise ValueError('Price changed; recalculate first')
  ids=[s['sizeID'] for s in gs[0]['sizes']]
  pub=raw('POST','https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',{'chrtIds':ids});e['published_stock']=pub
  if {r['chrtId'] for r in pub['stocks']}!=set(ids) or sum(r['amount'] for r in pub['stocks'])<=0:raise ValueError('No published stock')
  cfg=raw('GET','https://advert-api.wildberries.ru/api/advert/v1/config');e['config']=cfg
  if cfg['currency']!='CNY' or 12%cfg['cpcStep'] or 12>cfg['cpcMaxBid']:raise ValueError('Bid step or maximum changed')
  minimum=w.minimums(CID,[NM],'search')[NM];e['minimum_minor']=minimum
  if minimum>12:raise ValueError('Minimum above approved bid')
  budget=w.req('/api/advert/v2/budget','POST',{'advertIds':[CID]});e['budget']=budget
  if len(budget['adverts'])!=1 or budget['adverts'][0]['currency']!='CNY' or budget['adverts'][0]['total']<=0:raise ValueError('Budget unavailable')
  margin=14.504249570212096-(21/47)*(sr['price']/100-200.99797520661156)/12.0873
  e['preliminary_margin_before_ads_cny']=margin;e['unknown_reverse_and_shared_costs']=True
  if margin<=5:raise ValueError('Preliminary margin insufficient for bounded experiment')
  fresh=w.campaigns([CID])[str(CID)]
  if projection(fresh)!=projection(cp):raise ValueError('Campaign changed during preflight')
  expected=copy.deepcopy(cp)
  next(n for n in expected['nm_settings'] if n['nm_id']==NM)['bids_kopecks']['search']=12
  e.update(status='submitting',expected=expected,body=BODY,submitted_at=stamp());save()
  e['wb_writes']=1;save()
  e['response']=w.req('/api/advert/v1/bids','PATCH',BODY,write=True);e['status']='accepted';save()
  for attempt in range(4):
   after=w.campaigns([CID])[str(CID)];e['after']=after
   if projection(after)==projection(expected):break
   if attempt<3:time.sleep(3)
  else:raise ValueError('Readback mismatch; never repeat mutation')
  e.update(status='verified',verified_at=stamp(),completed_at=stamp(),items=[dict(kind='ad_set_bid',campaign_id=CID,nm_id=NM,article='2-FurPanama-black',placement='search',old_minor=11,target_minor=12)]);save()
  registry=c.get('china_agent:verified_campaign_state:v1') or {};registry[str(CID)]=ROOT+':execution';c.put('china_agent:verified_campaign_state:v1',registry)
 except Exception as ex:
  e.update(status='uncertain' if e['wb_writes'] else 'blocked',reason=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__,completed_at=stamp());save()
 print(json.dumps({k:e.get(k) for k in ['status','reason','wb_writes']}))
if __name__=='__main__':main()
