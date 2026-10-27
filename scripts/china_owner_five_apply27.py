"""Exact owner-approved five traffic tests; no funding/TG, one scoped PATCH, verified diffs."""
import os,json,copy,time
from datetime import datetime,timezone
import requests
from china_cloud_cost_control import Cache,WB,validate_identity,projection
from china_owner_five_checks27 import ITEMS,stocks
ROOT='china_agent:owner_five_apply:2026-10-27:v1'
SOURCE='china_agent:owner_five_tests:2026-10-27:v1:check'
def stamp():return datetime.now(timezone.utc).isoformat()
def expected(c,items):
 out=copy.deepcopy(c)
 for item in items:
  next(n for n in out['nm_settings'] if n['nm_id']==item['nm_id'])['bids_kopecks']['recommendations']=31
 return projection(out)
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or datetime.now(timezone.utc).date().isoformat()!='2026-10-27':raise ValueError('Dated public main only')
 c=Cache();wb=WB();a=c.get(ROOT+':approval') or {};source=c.get(SOURCE) or {}
 scope=[dict(campaign_id=cid,nm_id=nm,article=article,placement='recommendations',old_minor=28,target_minor=31) for cid,nm,article in ITEMS]
 if a.get('status')!='approved' or a.get('owner_user_id')!=5122667182 or a.get('source_channel')!='codex' or a.get('approved_items')!=scope or datetime.now(timezone.utc)>datetime.fromisoformat(a['expires_at']):raise ValueError('Exact five owner approval missing')
 if source.get('status')!='checked' or len(source.get('items',[]))!=5:raise ValueError('Checked proposal missing')
 prior=c.get(ROOT+':execution')
 if prior:print(json.dumps(dict(status=prior['status'],existing=True)));return
 validate_identity(c,wb)
 e=dict(status='preflight',created_at=stamp(),approval_key=ROOT+':approval',proposal_source=SOURCE,items=scope,groups=[],steps={},wb_writes=0,telegram_calls=0,economics_basis='Owner explicitly approved exploratory tests with unknown own buyout and logistics, not verified profit')
 if not c.create(ROOT+':execution',e):raise ValueError('Concurrent five execution')
 def save():c.put(ROOT+':execution',copy.deepcopy(e))
 try:
  cids=[41155824,41296363];before=wb.campaigns(cids);e['before']=before
  fresh_stocks=stocks();e['stocks']=fresh_stocks
  minima={}
  for cid in cids:minima.update(wb.minimums(cid,[i['nm_id'] for i in scope if i['campaign_id']==cid],'recommendations'))
  e['minimums']={str(k):v for k,v in minima.items()};need=[]
  for i in scope:
   cid=i['campaign_id'];nm=i['nm_id'];camp=before[str(cid)]
   if camp['status']!=9 or camp['currency']!='CNY' or camp['bid_type']!='manual' or camp['settings']['payment_type']!='cpc' or camp['settings']['placements']!=dict(search=False,recommendations=True):raise ValueError('Campaign settings changed')
   members=[n for n in camp['nm_settings'] if n['nm_id']==nm]
   if len(members)!=1 or members[0]['bids_kopecks']['recommendations'] not in [28,31] or minima[nm]>31:raise ValueError('Current bid/minimum differs from exact approval')
   st=next(s for s in fresh_stocks if s['article'].casefold()==i['article'].casefold())
   if not isinstance(st.get('stock'),(int,float)) or not isinstance(st.get('reserve'),(int,float)) or st['stock']-st['reserve']<=0:raise ValueError('Free stock no longer available')
   old=next(x for x in source['items'] if x['nm_id']==nm)
   if abs(st['price']-old['stock']['price'])>100:raise ValueError('COGS changed materially; review test economics')
   time.sleep(1)
   r=requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',headers={'Authorization':wb.token},params=dict(limit=1000,offset=0,filterNmID=nm),timeout=45)
   if not r.ok:raise ValueError('Price recheck unavailable')
   data=r.json()
   if data.get('error'):raise ValueError('Price recheck rejected')
   goods=data.get('data',data).get('listGoods',[])
   if len(goods)!=1 or goods[0].get('nmID')!=nm or goods[0].get('vendorCode')!=i['article'] or goods[0].get('currencyIsoCode4217')!='CNY' or {s['discountedPrice'] for s in goods[0]['sizes']}!={old['seller_price_cny']}:raise ValueError('Price changed since proposal')
   if members[0]['bids_kopecks']['recommendations']==28:need.append(i)
  e['preflight_verified_at']=stamp();save()
  if need:
   body=dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=i['nm_id'],bid_kopecks=31,placement='recommendations') for i in need if i['campaign_id']==cid]) for cid in cids if any(i['campaign_id']==cid for i in need)])
   e['steps']['bids']=dict(status='submitting',path='/api/advert/v1/bids',body=body,submitted_at=stamp());save()
   try:result=wb.req('/api/advert/v1/bids','PATCH',body,write=True)
   except Exception:
    e['steps']['bids']['status']='uncertain';save();raise
   e['wb_writes']=1;e['steps']['bids'].update(status='accepted',response=result);save()
  after=wb.campaigns(cids);e['after']=after;verified_at=stamp();allgood=True
  for cid in cids:
   selected=[i for i in scope if i['campaign_id']==cid];ok=projection(after[str(cid)])==expected(before[str(cid)],selected)
   group=dict(status='verified' if ok else 'uncertain',verified_at=verified_at,before=before[str(cid)],after=after[str(cid)],items=selected,approval_key=ROOT+':approval',parent=ROOT+':execution')
   e['groups'].append(group);allgood=allgood and ok
  e.update(status='verified' if allgood else 'uncertain',verified_at=verified_at,completed_at=stamp())
  if allgood and 'bids' in e['steps']:e['steps']['bids']['status']='verified'
  save()
  registry=c.get('china_agent:verified_campaign_state:v1') or {}
  for group in e['groups']:
   if group['status']!='verified':continue
   cid=group['after']['id'];key=ROOT+':'+str(cid)+':execution'
   if not c.create(key,group) and c.get(key)!=group:raise ValueError('Canonical child receipt conflict')
   registry[str(cid)]=key
  c.put('china_agent:verified_campaign_state:v1',registry)
 except Exception as error:
  e.update(status='uncertain' if e['steps'] else 'blocked',reason=str(error) if isinstance(error,(ValueError,RuntimeError)) else type(error).__name__,completed_at=stamp());save()
 print(json.dumps(dict(status=e['status'],verified=sum(len(g['items']) for g in e['groups'] if g['status']=='verified'),wb_writes=e['wb_writes'],reason=e.get('reason'))))
if __name__=='__main__':run()
