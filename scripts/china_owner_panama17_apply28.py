"""Exact owner-authorized Panama search raise; one PATCH, full campaign readback."""
import os,copy,json
from datetime import datetime,timezone
import requests
from china_cloud_cost_control import Cache,WB,validate_identity,projection,stamp
from china_bid_proposals import fresh_stock
from china_advertising_plans import economics
ROOT='china_agent:owner_panama17_apply28:2026-10-28:v2'
PLAN='china_agent:owner_panama17_plan28:2026-10-28:v1'
CID=41325622
ITEMS=[dict(nm_id=1535337780,article='17-FurPanama-leo',old_minor=11,target_minor=14)]
def validate_body(body):
 if set(body)!={'bids'} or len(body['bids'])!=1:raise ValueError('Forbidden scope')
 group=body['bids'][0]
 if set(group)!={'advert_id','nm_bids'} or group['advert_id']!=CID:raise ValueError('Forbidden campaign')
 seen=set();allowed={i['nm_id']:i['target_minor'] for i in ITEMS}
 for x in group['nm_bids']:
  if set(x)!={'nm_id','bid_kopecks','placement'} or x['nm_id'] not in allowed or x['nm_id'] in seen or x['bid_kopecks']!=allowed[x['nm_id']] or x['placement']!='search':raise ValueError('Forbidden bid change')
  seen.add(x['nm_id'])
 if not seen:raise ValueError('Empty mutation')
class ScopedWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write:
   if path!='/api/advert/v1/bids' or method!='PATCH':raise ValueError('Only approved bid PATCH')
   validate_body(body)
  return super().req(path,method,body,write)
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or datetime.now(timezone.utc).date().isoformat()!='2026-10-28':raise ValueError('Dated public main only')
 c=Cache();wb=ScopedWB();a=c.get(ROOT+':approval') or {};p=c.get(PLAN) or {}
 if a.get('status')!='approved' or a.get('owner_user_id')!=5122667182 or a.get('source_channel')!='codex' or datetime.now(timezone.utc)>datetime.fromisoformat(a['expires_at']):raise ValueError('Exact approval missing or expired')
 for rows in [a.get('approved_items',[]),p.get('items',[])]:
  if len(rows)!=1 or [{k:x[k] for k in ['nm_id','article','old_minor','target_minor']} for x in rows]!=ITEMS or any(x['campaign_id']!=CID or x['placement']!='search' for x in rows):raise ValueError('Exact approved scope mismatch')
 if p.get('invalidated_at') or p.get('status')!='pending_owner_approval':raise ValueError('Proposal not executable')
 prior=c.get(ROOT+':execution')
 if prior:print(json.dumps(dict(status=prior['status'],existing=True)));return
 validate_identity(c,wb)
 e=dict(status='preflight',created_at=stamp(),items=[dict(i,campaign_id=CID,placement='search') for i in ITEMS],steps={},wb_writes=0,telegram_calls=0,budget_writes=0,price_writes=0,approval_key=ROOT+':approval')
 if not c.create(ROOT+':execution',e):raise ValueError('Concurrent execution')
 def save():c.put(ROOT+':execution',copy.deepcopy(e))
 try:
  before=wb.campaigns([CID])[str(CID)];e['before']=before
  if before['status']!=9 or before['currency']!='CNY' or before['bid_type']!='manual' or before['settings']['payment_type']!='cpc' or before['settings']['placements']!=dict(search=True,recommendations=False):raise ValueError('Campaign scope changed')
  stock=fresh_stock({},[i['article'] for i in ITEMS])
  r=requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',params=dict(limit=1000,offset=0),headers={'Authorization':wb.token},timeout=60)
  if not r.ok:raise ValueError('Price preflight HTTP '+str(r.status_code))
  goods=r.json().get('data',{}).get('listGoods',[])
  if not goods or len(goods)>=1000:raise ValueError('Price scope incomplete')
  model=copy.deepcopy(c.get('china_agent:new_ad_source:v1:2026-10-28') or {})
  if (datetime.now(timezone.utc)-datetime.fromisoformat(model['observed_at'].replace('Z','+00:00'))).total_seconds()>86400:raise ValueError('Economic source stale')
  model.update(stock=stock,prices=goods)
  old_econ={1535337780:dict(seller_price_cny=126,cogs_kopecks=22419)}
  mins=wb.minimums(CID,[i['nm_id'] for i in ITEMS],'search')
  rr=requests.get('https://advert-api.wildberries.ru/api/advert/v1/config',headers={'Authorization':wb.token},timeout=45)
  if not rr.ok:raise ValueError('WB bid config unavailable')
  cfg=rr.json();e.update(stock=stock,minimums={str(k):v for k,v in mins.items()},config=cfg,economics=[])
  need=[]
  for i in ITEMS:
   ns=[n for n in before['nm_settings'] if n['nm_id']==i['nm_id']]
   if len(ns)!=1 or ns[0]['bids_kopecks']['search'] not in [i['old_minor'],i['target_minor']]:raise ValueError('Current bid changed')
   ec=economics(model,i['nm_id']);e['economics'].append(ec)
   old=old_econ[i['nm_id']]
   if ec['article']!=i['article'] or ec['seller_price_cny']!=old['seller_price_cny'] or abs(ec['cogs_kopecks']-old['cogs_kopecks'])>100:raise ValueError('Price or economics changed')
   target=i['target_minor']
   if mins[i['nm_id']]>target or cfg.get('currency')!='CNY' or type(cfg.get('cpcStep'))is not int or cfg['cpcStep']<=0 or target%cfg['cpcStep'] or target>cfg.get('cpcMaxBid',0):raise ValueError('Approved target outside WB limits')
   if ns[0]['bids_kopecks']['search']==i['old_minor']:need.append(i)
  e['baseline_fullstats']=wb.req('/adv/v3/fullstats?ids='+str(CID)+'&beginDate=2026-10-28&endDate=2026-10-28');e['preflight_verified_at']=stamp();save()
  if need:
   active=c.get(PLAN) or {};approval=c.get(ROOT+':approval') or {}
   if active.get('status')!='pending_owner_approval' or active.get('invalidated_at') or approval.get('status')!='approved' or datetime.now(timezone.utc)>datetime.fromisoformat(approval['expires_at']):raise ValueError('Approval revoked or expired')
   body=dict(bids=[dict(advert_id=CID,nm_bids=[dict(nm_id=i['nm_id'],bid_kopecks=i['target_minor'],placement='search') for i in need])]);validate_body(body)
   e['steps']['bid']=dict(status='submitting',body=body,submitted_at=stamp());save()
   try:result=wb.req('/api/advert/v1/bids','PATCH',body,write=True)
   except Exception:e['steps']['bid']['status']='uncertain';save();raise
   e['wb_writes']=1;e['steps']['bid'].update(status='accepted',response=result);save()
  after=wb.campaigns([CID])[str(CID)];e['after']=after;expected=copy.deepcopy(before)
  for i in ITEMS:next(n for n in expected['nm_settings'] if n['nm_id']==i['nm_id'])['bids_kopecks']['search']=i['target_minor']
  if projection(after)!=projection(expected):raise ValueError('Full campaign after mismatch; no retry')
  e.update(status='verified',verified_at=stamp(),completed_at=stamp())
  if e['steps']:e['steps']['bid']['status']='verified'
  save()
  child=ROOT+':'+str(CID)+':execution';value=dict(status='verified',before=before,after=after,items=e['items'],baseline_fullstats=e['baseline_fullstats'],verified_at=e['verified_at'],parent=ROOT+':execution')
  if not c.create(child,value) and c.get(child)!=value:raise ValueError('Canonical child conflict')
  registry=c.get('china_agent:verified_campaign_state:v1') or {};registry[str(CID)]=child;c.put('china_agent:verified_campaign_state:v1',registry)
  p.update(status='executed',execution_key=ROOT+':execution',executed_at=e['verified_at']);c.put(PLAN,p)
 except Exception as ex:
  e.update(status='uncertain' if e['steps'] else 'blocked',reason=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__,completed_at=stamp());save()
 print(json.dumps({k:e.get(k) for k in ['status','wb_writes','price_writes','budget_writes','reason','verified_at']}))
if __name__=='__main__':run()
