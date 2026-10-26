"""One owner-approved 21-SKU cross-placement test; no automatic re-funding or pauses."""
import os,json,copy,time,math
from datetime import datetime,timezone
import requests
from china_cloud_cost_control import Cache,validate_identity
KEY='china_agent:owner_search_expand:2026-10-26:v2:execution'
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
 previous=c.get('china_agent:owner_search_expand:2026-10-26:v1:execution') or {}
 if previous.get('wb_writes')!=0:raise RuntimeError('Previous execution may have writes; no retry')
 old=c.get(KEY)
 if old:print('Owner execution already recorded; do not repeat');return
 e=dict(status='preflight',owner_id=5122667182,owner_quotes=['делай все','давай добавим все предложенное, а потом лучше будем исключать.','если есть возможность, то добавляем в действующие рк, если таких нет, то создаем'],articles=ARTICLES,test_cap_cny=200,steps={},campaigns=[],wb_writes=0,telegram_sends=0,created_at=datetime.now(timezone.utc).isoformat())
 if not c.create(KEY,e):return
 def save():c.put(KEY,e)
 def mutate(step,path,method,body=None):
  if step in e['steps']:raise RuntimeError('Prior write exists; never repeat')
  e['steps'][step]=dict(status='submitting',path=path,method=method,body=body);save()
  try:r=w.req(path,method,body)
  except Exception:e['steps'][step]['status']='uncertain';save();raise
  e['steps'][step].update(status='accepted',response=r);e['wb_writes']+=1;save();return r
 def campaign(cid):return w.campaigns([cid])[str(cid)]
 def budget(cid):
  rows=w.req('/api/advert/v2/budget','POST',dict(advertIds=[cid]))['adverts']
  if len(rows)!=1 or rows[0].get('currency')!='CNY':raise RuntimeError('Budget scope invalid')
  return rows[0]['total']
 try:
  auth=c.get('china_agent:owner_search_expand:2026-10-26:v1:approval') or {}
  if auth.get('status')!='approved' or auth.get('test_cap_cny')!=200:raise RuntimeError('Exact current owner approval missing')
  source=c.get('china_agent:new_ad_source:v1:2026-10-26') or {}
  products={x['sa_name']:x for x in source.get('products',[])}
  prices={x['nmID']:x for x in source.get('prices',[])}
  stocks={x.get('article','').casefold():x for x in source.get('stock',[])}
  if set(ARTICLES)-set(products):raise RuntimeError('Exact article catalogue missing')
  groups={}
  for article in ARTICLES:
   p=products[article];nm=int(p['nm_id']);pr=prices.get(nm);st=stocks.get(article.casefold())
   if not pr or pr.get('currencyIsoCode4217')!='CNY' or not st or st.get('stock') is None or st.get('reserve') is None or st['stock']-st['reserve']<=0:
    e.setdefault('skipped',[]).append(dict(article=article,reason='Price or available stock not confirmed; absent row is not zero'));save();continue
   groups.setdefault(p['subject_id'],[]).append(dict(nm_id=nm,article=article))
  cfg=w.req('/api/advert/v1/config')
  if cfg.get('currency')!='CNY':raise RuntimeError('Wrong currency')
  inv=w.req('/adv/v1/promotion/count');ids=sorted({x['advertId'] for g in inv.get('adverts',[]) if g['status'] in [4,9,11] for x in g.get('advert_list',[])})
  cs=w.campaigns(ids)
  # Confirm exact prices narrowly through the WB price API; no price writes.
  fresh=[]
  for offset in [0]:
   time.sleep(2);r=requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',headers={'Authorization':w.token},params={'limit':1000,'offset':offset},timeout=50)
   if not r.ok:raise RuntimeError('WB prices HTTP '+str(r.status_code))
   fresh=r.json().get('data',{}).get('listGoods',[])
   if not fresh: fresh=r.json().get('listGoods',[])
  fp={x['nmID']:x for x in fresh}
  for items in groups.values():
   for item in items:
    p=fp.get(item['nm_id'])
    if not p or p.get('vendorCode')!=item['article'] or p.get('currencyIsoCode4217')!='CNY':raise RuntimeError('Fresh SKU identity unavailable')
  for subject,items in groups.items():
   wanted={x['nm_id'] for x in items}
   suitable=[x for x in cs.values() if x['status']==9 and x.get('currency')=='CNY' and x.get('bid_type')=='manual' and x['settings']['payment_type']=='cpc' and x['settings']['placements']=={'search':True,'recommendations':False} and {n['subject']['id'] for n in x['nm_settings']}=={subject}]
   suitable.sort(key=lambda x:(x['id']!=41298169,-len(wanted & {n['nm_id'] for n in x['nm_settings']})))
   if suitable:
    before=suitable[0];cid=before['id'];oldids={n['nm_id'] for n in before['nm_settings']};add=sorted(wanted-oldids)
    if len(oldids|wanted)>50:raise RuntimeError('Existing campaign would exceed conservative 50SKU bound')
    state=dict(campaign_id=cid,subject_id=subject,existing=True,items=items,before=before,status='preflight');e['campaigns'].append(state);save()
    if add:mutate('add:'+str(cid),'/adv/v0/auction/nms','PATCH',dict(nms=[dict(advert_id=cid,nms=dict(add=add,delete=[]))]))
    after=campaign(cid)
    if {n['nm_id'] for n in after['nm_settings']}!=oldids|wanted or after['status']!=9 or after['settings']!=before['settings']:raise RuntimeError('Existing membership not verified')
    state['after_membership']=after
    if add:e['steps']['add:'+str(cid)]['status']='verified'
   else:
    name='Китай поиск 26.10 · '+str(subject)+' · owner21'
    state=dict(subject_id=subject,existing=False,items=items,status='preflight');e['campaigns'].append(state);save()
    resp=mutate('create:'+str(subject),'/adv/v2/seacat/save-ad','POST',dict(name=name,nms=sorted(wanted),bid_type='manual',payment_type='cpc',placement_types=['search']))
    cid=resp if type(resp)is int else resp.get('advertId') if isinstance(resp,dict) else None
    if type(cid)is not int:raise RuntimeError('Uncertain creation ID; no retry')
    state['campaign_id']=cid;save();after=campaign(cid)
    if after['status']!=4 or after['settings']['placements']!={'search':True,'recommendations':False} or {n['nm_id'] for n in after['nm_settings']}!=wanted:raise RuntimeError('New draft verification failed')
    e['steps']['create:'+str(subject)]['status']='verified'
   mins=w.req('/api/advert/v1/bids/min','POST',dict(advert_id=cid,nm_ids=sorted(wanted),payment_type='cpc',placement_types=['search']))
   targets={}
   for row in mins.get('bids',[]):
    vs=[b['value'] for b in row.get('bids',[]) if b.get('currency')=='CNY' and b.get('type')=='search']
    if len(vs)!=1 or type(vs[0])is not int or vs[0]>28:raise RuntimeError('Minimum exceeds approved conservative .28CNY ceiling')
    targets[row['nm_id']]=max(28 if subject==50 else vs[0],vs[0])
   if set(targets)!=wanted:raise RuntimeError('Incomplete exact search minima')
   mutate('bids:'+str(cid),'/api/advert/v1/bids','PATCH',dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=nm,bid_kopecks=bid,placement='search') for nm,bid in targets.items()])]))
   after=campaign(cid)
   if any(n['bids_kopecks'].get('search')!=targets[n['nm_id']] for n in after['nm_settings'] if n['nm_id'] in wanted):raise RuntimeError('Bid readback failed')
   e['steps']['bids:'+str(cid)]['status']='verified';state.update(status='composition_bids_verified',after=after,bids=targets,baseline_budget=budget(cid));save()
  # Existing total remaining budget plus the two new category minima must fit200.
  existing=sum(x['baseline_budget'] for x in e['campaigns'] if x['existing']);new=[x for x in e['campaigns'] if not x['existing']]
  minimum=math.ceil(max(cfg.get('minTopUp',0),cfg.get('minDailyLimit',0))/100)
  if minimum<=0 or existing+len(new)*minimum>200:raise RuntimeError('Verified WB minimum budgets plus existing balance exceed200CNY cap; drafts left unfunded')
  for state in new:
   cid=state['campaign_id'];limit=minimum*100
   mutate('limit:'+str(cid),'/api/advert/v0/daily-limits','PUT',dict(advertIds=[cid],enabled=True,dailyLimit=limit,carryOverEnabled=False))
   rows=w.req('/api/advert/v0/daily-limits?advertIds='+str(cid))['adverts']
   if len(rows)!=1 or rows[0].get('dailyLimit')!=limit or rows[0].get('enabled')is not True or rows[0].get('carryOverEnabled')is not False:raise RuntimeError('Daily limit not verified')
   if budget(cid)!=0:raise RuntimeError('New draft already funded; no duplicate')
   mutate('deposit:'+str(cid),'/adv/v1/budget/deposit?id='+str(cid),'POST',dict(sum=minimum,type=0))
   if budget(cid)!=minimum:raise RuntimeError('Deposit readback not confirmed')
   state['funded_cny']=minimum
   mutate('start:'+str(cid),'/adv/v0/start?id='+str(cid),'GET')
   after=campaign(cid)
   if after['status']!=9:raise RuntimeError('Start accepted, active status not yet confirmed; no repeated start')
   state.update(status='verified_active',after=after);save()
  e.update(status='verified',completed_at=datetime.now(timezone.utc).isoformat(),remaining_exposure_cap_basis='Current whole-campaign balances + single new deposits <=200CNY; no re-funding')
 except Exception as ex:
  e.update(status='uncertain' if any(s.get('status')=='uncertain' for s in e['steps'].values()) else 'blocked',reason=str(ex) if isinstance(ex,RuntimeError) else type(ex).__name__,completed_at=datetime.now(timezone.utc).isoformat())
 finally:
  save()
  registry=c.get('china_agent:verified_campaign_state:v1') or {}
  for x in e['campaigns']:
   if x.get('after') and x['status'] in ['composition_bids_verified','verified_active']:
    k='china_agent:owner_search_expand:2026-10-26:'+str(x['campaign_id'])+':execution'
    c.put(k,dict(status='verified',before=x.get('before'),after=x['after'],verified_at=e.get('completed_at'),items=x['items'],parent=KEY))
    registry[str(x['campaign_id'])]=k
  c.put('china_agent:verified_campaign_state:v1',registry)
  print('Owner search execution saved privately; status='+e['status'])
if __name__=='__main__':run()
