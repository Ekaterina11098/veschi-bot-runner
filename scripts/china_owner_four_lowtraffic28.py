"""Four explicit owner-authorized CPC tests; no other marketplace mutation."""
import os,json,copy,hashlib,time
from datetime import datetime,timezone
import requests
_original_get=requests.get
def read_get(*args,**kwargs):
 for attempt in range(3):
  try:return _original_get(*args,**kwargs)
  except (requests.exceptions.ConnectionError,requests.exceptions.Timeout):
   if attempt==2:raise
   time.sleep(2*(attempt+1))
requests.get=read_get
from china_cloud_cost_control import Cache,WB,validate_identity,projection,stamp,counts
from china_bid_proposals import fresh_stock
ROOT='china_agent:owner_four_lowtraffic28:2026-10-28:v1'
PLAN=ROOT+':plan'
SCOPE=[dict(campaign_id=41296359,nm_id=1473245515,article='154-ReginaBag-green',placement='recommendations',old_minor=28,target_minor=34),dict(campaign_id=41296359,nm_id=1473246048,article='642-MelanieBag-beige',placement='recommendations',old_minor=28,target_minor=34),dict(campaign_id=41155824,nm_id=1473244996,article='560-HelgaBag-ginger',placement='recommendations',old_minor=28,target_minor=31),dict(campaign_id=41155824,nm_id=1473244997,article='568-HelgaBag-black',placement='recommendations',old_minor=28,target_minor=31)]
HASH='1974df9239b4f19dec9ef2fca0366c11cb9991280e3bd40c350c69d117cb20d8'
def validate_body(body):
 if set(body)!={'bids'} or not body['bids']:raise ValueError('Only exact bids payload')
 allowed={(i['campaign_id'],i['nm_id']):i['target_minor'] for i in SCOPE};seen=set();cs=set()
 for g in body['bids']:
  if set(g)!={'advert_id','nm_bids'} or g['advert_id'] in cs or not g['nm_bids']:raise ValueError('Invalid campaign group')
  cs.add(g['advert_id'])
  for x in g['nm_bids']:
   key=(g['advert_id'],x.get('nm_id'))
   if set(x)!={'nm_id','placement','bid_kopecks'} or key in seen or key not in allowed or x['placement']!='recommendations' or x['bid_kopecks']!=allowed[key]:raise ValueError('Unapproved bid mutation')
   seen.add(key)
 if seen!=set(allowed):raise ValueError('All four exact bids required')
class ScopedWB(WB):
 def req(self,path,method='GET',body=None,write=False):
  if write:
   if path!='/api/advert/v1/bids' or method!='PATCH':raise ValueError('Only exact bid PATCH permitted')
   validate_body(body)
  return super().req(path,method,body,write)
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or datetime.now(timezone.utc).date().isoformat()!='2026-10-28':raise ValueError('Dated public main only')
 c=Cache();w=ScopedWB();a=c.get(ROOT+':approval') or {};p=c.get(PLAN) or {}
 def auth():
  for rec in [c.get(ROOT+':approval') or {},c.get(PLAN) or {}]:
   if rec.get('scope_sha256')!=HASH or rec.get('items')!=SCOPE or rec.get('invalidated_at') or datetime.now(timezone.utc)>datetime.fromisoformat(rec['expires_at']):raise ValueError('Scope binding revoked or expired')
  aa=c.get(ROOT+':approval') or {}
  if aa.get('status')!='approved' or aa.get('owner_user_id')!=5122667182 or aa.get('source_channel')!='codex' or aa.get('plan_key')!=PLAN:raise ValueError('Exact current human approval missing')
  if (c.get(PLAN) or {}).get('status')!='approved':raise ValueError('Plan not executable')
 auth()
 if hashlib.sha256(json.dumps(SCOPE,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()!=HASH:raise ValueError('Internal scope hash changed')
 old=c.get(ROOT+':execution')
 if old:print(json.dumps(dict(status=old.get('status'),existing=True)));return
 validate_identity(c,w)
 e=dict(status='preflight',items=SCOPE,created_at=stamp(),steps={},wb_writes=0,price_writes=0,budget_writes=0,telegram_calls=0,approval_key=ROOT+':approval',plan_key=PLAN,scope_sha256=HASH,economics_basis='Owner-approved exploratory scenarios, CR and buyout unmeasured, logistics35 hypothetical except154dated26; no lowDRR claim')
 if not c.create(ROOT+':execution',e):raise ValueError('Duplicate execution')
 def save():c.put(ROOT+':execution',copy.deepcopy(e))
 try:
  e['stage']='fresh campaign, MS stock and COGS';save()
  cids=[41296359,41155824];before=w.campaigns(cids);e['before']=before
  stocks=fresh_stock({},[i['article'] for i in SCOPE]);e['stocks']=stocks;save()
  if {s['article'] for s in stocks}!={i['article'] for i in SCOPE}:raise ValueError('MS stock/COGS incomplete')
  e['stage']='WB price and published stock';save()
  r=requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',params=dict(limit=1000,offset=0),headers={'Authorization':w.token},timeout=60)
  if not r.ok:raise ValueError('Price preflight HTTP '+str(r.status_code))
  goods=r.json().get('data',{}).get('listGoods',[])
  if not goods or len(goods)>=1000:raise ValueError('Price pagination incomplete')
  wanted={i['nm_id'] for i in SCOPE};gm={g['nmID']:g for g in goods if g['nmID'] in wanted}
  if set(gm)!=wanted:raise ValueError('Exact current goods missing')
  sizes={s['sizeID']:g['nmID'] for g in gm.values() for s in g['sizes']}
  r=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',json=dict(chrtIds=list(sizes)),headers={'Authorization':w.token},timeout=50)
  if not r.ok:raise ValueError('WB published stock HTTP '+str(r.status_code))
  pub={}
  for s in r.json().get('stocks',[]):
   if s['chrtId'] not in sizes or type(s.get('amount'))is not int:raise ValueError('Unverified stock row')
   nm=sizes[s['chrtId']];pub[nm]=pub.get(nm,0)+s['amount']
  e['prices']=list(gm.values());e['published_stock']={str(k):v for k,v in pub.items()};save()
  minima={}
  for cid in cids:minima.update(w.minimums(cid,[i['nm_id'] for i in SCOPE if i['campaign_id']==cid],'recommendations'))
  rr=requests.get('https://advert-api.wildberries.ru/api/advert/v1/config',headers={'Authorization':w.token},timeout=45)
  if not rr.ok:raise ValueError('Bid config unavailable')
  cfg=rr.json();e.update(minimums={str(k):v for k,v in minima.items()},config=cfg,economics=[]);need=[]
  basis={i['nm_id']:i for i in p['economics']}
  for i in SCOPE:
   nm=i['nm_id'];camp=before[str(i['campaign_id'])]
   if camp['status']!=9 or camp['currency']!='CNY' or camp['bid_type']!='manual' or camp['settings']['payment_type']!='cpc' or camp['settings']['placements']!=dict(search=False,recommendations=True):raise ValueError('Campaign settings differ')
   member=[x for x in camp['nm_settings'] if x['nm_id']==nm]
   if len(member)!=1 or member[0]['bids_kopecks']['recommendations']!=i['old_minor']:raise ValueError('Current bid differs; do not repeat earlier changes')
   g=gm[nm];b=basis[nm];st=next(x for x in stocks if x['article']==i['article'])
   if g.get('vendorCode')!=i['article'] or g.get('currencyIsoCode4217')!='CNY' or {x['discountedPrice'] for x in g['sizes']}!={b['price']}:raise ValueError('Price/identity differs from approved scenario')
   if any(type(st.get(k))not in [int,float] for k in ['stock','reserve','price']) or st['stock']-st['reserve']<=0 or pub.get(nm,0)<=0:raise ValueError('Free MS or WB stock unavailable')
   cogs=st['price']/1200
   if abs(cogs-b['cogs'])>.1:raise ValueError('COGS changed materially; review economics')
   target=i['target_minor'];step=cfg.get('cpcStep')
   if minima[nm]>target or cfg.get('currency')!='CNY' or type(step)is not int or step<=0 or target%step or target>cfg.get('cpcMaxBid',0):raise ValueError('Target outside current minimum/step/max')
   profit=.5*(b['price']*.75-cogs)-b['logistics']-10/12-target/2
   if profit<=0:raise ValueError('Approved CR2 scenario no longer positive')
   e['economics'].append(dict(nm_id=nm,article=i['article'],price=b['price'],cogs=cogs,logistics=b['logistics'],logistics_source=b['logistics_source'],profit_per_order_at_cr2=round(profit,2),buyout_scenario=.5,cr_scenario=.02,not_verified_profit=True))
   need.append(i)
  e['stage']='statistics baseline';save()
  stats=w.req('/adv/v3/fullstats?ids=41296359,41155824&beginDate=2026-10-28&endDate=2026-10-28')
  if not isinstance(stats,list) or {s['advertId'] for s in stats}!=set(cids):raise ValueError('Baseline campaigns incomplete')
  e['baseline_fullstats']=stats;e['baseline_observed_at']=stamp()
  _,sku=counts(stats);e['baseline_items']={str(i['nm_id']):sku.get(str(i['campaign_id'])+':'+str(i['nm_id'])) for i in SCOPE}
  e['preflight_verified_at']=stamp();save()
  auth()
  live=w.campaigns(cids)
  if any(projection(live[str(cid)])!=projection(before[str(cid)]) for cid in cids):raise ValueError('Concurrent change before PATCH')
  body=dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=i['nm_id'],placement='recommendations',bid_kopecks=i['target_minor']) for i in need if i['campaign_id']==cid]) for cid in cids])
  validate_body(body);e['steps']['bid']=dict(status='submitting',body=body,submitted_at=stamp());save()
  e['wb_writes']=1;save()
  try:response=w.req('/api/advert/v1/bids','PATCH',body,write=True)
  except Exception:e['steps']['bid']['status']='uncertain';save();raise
  e['steps']['bid'].update(status='accepted',response=response);save()
  groups=[]
  for attempt in range(4):
   after=w.campaigns(cids);e['after']=after;groups=[]
   for cid in cids:
    ex=copy.deepcopy(before[str(cid)]);selected=[i for i in SCOPE if i['campaign_id']==cid]
    for i in selected:next(n for n in ex['nm_settings'] if n['nm_id']==i['nm_id'])['bids_kopecks']['recommendations']=i['target_minor']
    ok=projection(after[str(cid)])==projection(ex)
    groups.append(dict(status='verified' if ok else 'uncertain',before=before[str(cid)],after=after[str(cid)],items=selected,verified_at=stamp() if ok else None,parent=ROOT+':execution',baseline_fullstats=[s for s in stats if s['advertId']==cid],baseline_observed_at=e['baseline_observed_at']))
   if all(g['status']=='verified' for g in groups):break
   if attempt<3:time.sleep(12)
  e.update(groups=groups,status='verified' if all(g['status']=='verified' for g in groups) else 'uncertain',completed_at=stamp());e['steps']['bid']['status']=e['status']
  if e['status']=='verified':e['verified_at']=stamp()
  save()
  for group in groups:
   if group['status']!='verified':continue
   cid=group['after']['id'];key=ROOT+':'+str(cid)+':execution'
   if not c.create(key,group) and c.get(key)!=group:raise ValueError('Child receipt conflict')
   registry=c.get('china_agent:verified_campaign_state:v1') or {};registry[str(cid)]=key;c.put('china_agent:verified_campaign_state:v1',registry)
  if e['status']=='verified':
   p.update(status='executed',execution_key=ROOT+':execution',executed_at=e['verified_at']);c.put(PLAN,p)
   c.put(ROOT+':tracking',dict(status='active',items=SCOPE,canonical_execution_key=ROOT+':execution',baseline_items=e['baseline_items'],baseline_observed_at=e['baseline_observed_at'],verified_at=e['verified_at'],first_full_msk_day='2026-10-29',first_full_day_evaluation='2026-10-30',automatic_changes_allowed=False,funding_allowed=False))
 except Exception as ex:
  e.update(status='uncertain' if e['steps'] else 'blocked',reason=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__+' at '+e.get('stage','preflight'),completed_at=stamp());save()
 print(json.dumps({k:e.get(k) for k in ['status','wb_writes','reason','verified_at','baseline_items']}))
if __name__=='__main__':run()
