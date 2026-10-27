"""Exact seven-item Codex owner approval. Scoped writes, durable steps and WB readback."""
import os,json,copy,hashlib
from datetime import datetime,timezone
from urllib.parse import urlencode
from types import SimpleNamespace
from china_price_apply import IO
from china_cloud_cost_control import Cache,WB,validate_identity
from china_advertising_plans import members,economics
from china_bid_proposals import sources,timestamp,fresh_stock
PLAN='china_agent:owner_growth_plan:2026-10-27:v2'
APP='china_agent:owner_growth_apply27:2026-10-27:v1:approval'
EXEC='china_agent:owner_growth_apply27:2026-10-27:v1:execution'
def stamp():return datetime.now(timezone.utc).isoformat()
def digest(items):return hashlib.sha256(json.dumps(items,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def projection(items):return [{k:i[k] for k in ['kind','article','campaign_id','nm_id','placement','old_minor','target_minor']} for i in items]
def exact(before,after,items):
 expected=members(before)
 for i in items:
  k=str(i['nm_id'])
  if k not in expected:expected[k]=dict(subject=i['economics']['subject_id'],bids=dict(search=0,recommendations=0))
  expected[k]['bids'][i['placement']]=i['target_minor']
 return members(after)==expected and all(after[k]==before[k] for k in ['status','currency','bid_type','settings'])
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or datetime.now(timezone.utc).date().isoformat()!='2026-10-27':raise ValueError('Dated public main only')
 io=IO();wb=WB();validate_identity(Cache(),wb)
 a=io.get(APP);p=io.get(PLAN)
 if not a or a.get('status')!='approved' or a.get('source_channel')!='codex' or a.get('owner_user_id')!=5122667182:raise PermissionError('Owner command absent')
 if not p or p.get('status')!='pending_owner_approval' or len(p.get('items',[]))!=7 or digest(p['items'])!=p['plan_sha256'] or a['plan_sha256']!=p['plan_sha256'] or projection(p['items'])!=a['items']:raise ValueError('Exact approved plan mismatch')
 if datetime.now(timezone.utc)>timestamp(p['expires_at']):raise ValueError('Exact plan expired')
 prior=io.get(EXEC)
 if prior:print(json.dumps(dict(status=prior['status'],existing=True)));return
 e=dict(status='running',created_at=stamp(),approval_key=APP,plan_key=PLAN,plan_sha256=p['plan_sha256'],items=[],steps={},wb_writes=0,telegram_calls=0)
 if not io.create(EXEC,e):raise ValueError('Concurrent execution')
 def persist():io.put(EXEC,json.loads(json.dumps(e)))
 def write(name,path,body):
  active=io.get(PLAN) or {}
  if active.get('status')!='pending_owner_approval' or active.get('plan_sha256')!=p['plan_sha256'] or active.get('invalidated_at') or datetime.now(timezone.utc)>timestamp(p['expires_at']):raise ValueError('Plan no longer executable')
  if name in e['steps']:raise ValueError('Write already attempted; no blind repeat')
  e['steps'][name]=dict(status='submitting',path=path,body=body,submitted_at=stamp());persist()
  try:
   result=wb.req(path,'PATCH',body,write=True);e['wb_writes']+=1
   e['steps'][name].update(status='accepted',response=result);persist()
  except Exception as error:
   e['steps'][name].update(status='uncertain',reason=str(error) if isinstance(error,(ValueError,RuntimeError)) else type(error).__name__);persist();raise
 try:
  def db(method,table,params=None,**kw):
   if method!='GET':raise PermissionError('History is read only')
   return io.db(table+('?' +urlencode(params) if params else ''))
  view=sources(SimpleNamespace(now=datetime.now(timezone.utc),get=io.get,db=db,save=lambda *a,**kw:None))
  for i in p['items']:
   if any(x.get('nm')==i['nm_id'] and timestamp(x.get('at')) and timestamp(x['at'])>timestamp(p['created_at']) for x in view['changes']):raise ValueError('New verified change after proposal: '+i['article'])
  inv=wb.req('/adv/v1/promotion/count')
  ids=sorted({n['advertId'] for g in inv.get('adverts',[]) if g.get('status') in [9,11] for n in g.get('advert_list',[])})
  allcs=wb.campaigns(ids);targetids=sorted({i['campaign_id'] for i in p['items']})
  before={str(cid):allcs[str(cid)] for cid in targetids};e['before']=before;persist()
  goods=io.wb('/api/v2/list/goods/filter?limit=1000&offset=0').get('listGoods',[])
  if len(goods)>=1000:raise ValueError('Price catalogue incomplete')
  prices={g['nmID']:g for g in goods};stock=fresh_stock({},[i['article'] for i in p['items']])
  model=copy.deepcopy(io.get('china_agent:new_ad_source:v1:2026-10-27') or {})
  if not timestamp(model.get('observed_at')) or (datetime.now(timezone.utc)-timestamp(model['observed_at'])).total_seconds()>86400:raise ValueError('Economic source stale')
  model['prices']=goods;model['stock']=stock
  adds={cid:[] for cid in targetids};need_raise=[]
  for k,i in enumerate(p['items']):
   cid=i['campaign_id'];camp=before[str(cid)];nm=i['nm_id'];ns={n['nm_id']:n for n in camp['nm_settings']}
   if camp['status']!=9 or camp['currency']!='CNY' or camp['bid_type']!='manual' or camp['settings']['payment_type']!='cpc' or camp['settings']['placements']!=dict(search=i['placement']=='search',recommendations=i['placement']=='recommendations'):raise ValueError('Campaign scope changed')
   price=prices.get(nm,{})
   if price.get('vendorCode')!=i['article'] or price.get('currencyIsoCode4217')!='CNY' or price.get('sizes',[{}])[0].get('discountedPrice')!=i['economics']['seller_price_cny']:raise ValueError('Card or seller price changed: '+i['article'])
   ec=economics(model,nm)
   st=dict(index=k,item=i,status='preflight',current_economics=ec);e['items'].append(st)
   if i['kind']=='ad_raise_bid':
    if nm not in ns or ns[nm]['bids_kopecks'][i['placement']] not in [i['old_minor'],i['target_minor']]:raise ValueError('Bid/member differs from approved plan')
    st['already_done']=ns[nm]['bids_kopecks'][i['placement']]==i['target_minor']
    if not st['already_done']:need_raise.append(i)
   elif i['kind']=='ad_add_sku':
    if {n['subject']['id'] for n in camp['nm_settings']}!={ec['subject_id']}:raise ValueError('Category mismatch')
    if any(c['status']==9 and c['settings']['placements'].get('search') and c['id']!=cid and any(n['nm_id']==nm for n in c['nm_settings']) for c in allcs.values()):raise ValueError('Already in another active search campaign')
    st['already_done']=nm in ns and ns[nm]['bids_kopecks']['search']==i['target_minor']
    if nm in ns and not st['already_done']:raise ValueError('Pre-existing new member has different rate')
    if nm not in ns:adds[cid].append(nm)
   else:raise ValueError('Unapproved action type')
  for cid,ns in adds.items():
   if len(before[str(cid)]['nm_settings'])+len(ns)>50:raise ValueError('Campaign capacity exceeded')
  for i in need_raise:
   m=wb.minimums(i['campaign_id'],[i['nm_id']],i['placement'])[i['nm_id']]
   if m>i['target_minor']:raise ValueError('Minimum exceeds approved belt bid')
  persist()
  addbody=dict(nms=[dict(advert_id=cid,nms=dict(add=nms,delete=[])) for cid,nms in adds.items() if nms])
  if addbody['nms']:
   write('membership','/adv/v0/auction/nms',addbody)
  interim=wb.campaigns(targetids);e['after_membership']=interim;persist()
  need=list(need_raise)
  for cid in targetids:
   camp=interim[str(cid)];old=before[str(cid)]
   planned=[i for i in p['items'] if i['campaign_id']==cid]
   newids=set(members(old))|{str(n) for n in adds[cid]}
   if set(members(camp))!=newids or any(members(camp)[k]!=v for k,v in members(old).items()) or any(camp[k]!=old[k] for k in ['status','currency','bid_type','settings']):raise ValueError('Membership or existing rates changed unexpectedly')
   newitems=[i for i in planned if i['kind']=='ad_add_sku' and not next(s for s in e['items'] if s['item']['nm_id']==i['nm_id'])['already_done']]
   if newitems:
    minima=wb.minimums(cid,[i['nm_id'] for i in newitems],'search')
    for i in newitems:
     if minima[i['nm_id']]>i['target_minor']:raise ValueError('Added SKU minimum exceeds exact approved category rate')
     state=next(n for n in camp['nm_settings'] if n['nm_id']==i['nm_id'])
     if state['bids_kopecks']['search']!=i['target_minor']:need.append(i)
  if need:
   body=dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=i['nm_id'],bid_kopecks=i['target_minor'],placement=i['placement']) for i in need if i['campaign_id']==cid]) for cid in targetids if any(i['campaign_id']==cid for i in need)])
   write('bids','/api/advert/v1/bids',body)
  after=wb.campaigns(targetids);e['after']=after
  for s in e['items']:
   cid=s['item']['campaign_id'];same=exact(before[str(cid)],after[str(cid)],[i for i in p['items'] if i['campaign_id']==cid])
   s.update(status='verified' if same else 'uncertain',before=before[str(cid)],after=after[str(cid)])
  ok=all(s['status']=='verified' for s in e['items'])
  e.update(status='verified' if ok else 'attention',verified_at=stamp(),completed_at=stamp())
  if ok:
   for st in e['steps'].values():st['status']='verified'
  persist()
 except Exception as error:
  e.update(status='attention' if e['steps'] else 'blocked',reason=str(error) if isinstance(error,(ValueError,RuntimeError)) else type(error).__name__,completed_at=stamp());persist()
 if e['status']=='verified':
  registry=io.get('china_agent:verified_campaign_state:v1') or {}
  for cid in targetids:
   key='china_agent:owner_growth_apply27:2026-10-27:v1:'+str(cid)+':execution'
   receipt=dict(status='verified',verified_at=e['verified_at'],before=e['before'][str(cid)],after=e['after'][str(cid)],items=[i for i in p['items'] if i['campaign_id']==cid],parent=EXEC,approval_key=APP,approval_source='codex')
   if not io.create(key,receipt):raise ValueError('Concurrent child receipt')
   registry[str(cid)]=key
  if io.get('china_agent:verified_campaign_state:v1') is None:io.create('china_agent:verified_campaign_state:v1',registry)
  else:io.put('china_agent:verified_campaign_state:v1',registry)
  io.put(PLAN,dict(p,status='executed',execution_key=EXEC,completed_at=e['completed_at']))
 print(json.dumps(dict(status=e['status'],items=len(e['items']),verified=sum(s['status']=='verified' for s in e['items']),wb_writes=e['wb_writes'],reason=e.get('reason'))))
if __name__=='__main__':run()
