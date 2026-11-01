"""Execute only the frozen first PNG explicitly approved in Codex, once."""
import copy,json,os,time
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from china_cloud_cost_control import Cache,WB,validate_identity,projection,digest,stamp
ROOT='china_agent:owner_intraday_apply:2026-11-01:v1'
SCOPE='e006577fa8a70f26fbf98caeedfa1bf367ec4d587757592099cc8774128492a2'
PNG='bbcf95dbdcb6df4e2bab4c75b27cc101fb625bbb34dca8f6ba70e601807a3a97'
def approval(c):
 a=c.get(ROOT+':approval')or{}
 if a.get('status')!='approved' or a.get('owner_user_id')!=5122667182 or a.get('source_channel')!='codex' or a.get('cabinet')!='token_3' or a.get('execution_authorized')is not True:raise ValueError('Exact approval missing')
 if a.get('png_sha256')!=PNG or a.get('scope_sha256')!=SCOPE or digest(a.get('approved_items'))!=SCOPE:raise ValueError('Frozen PNG scope mismatch')
 if datetime.now(timezone.utc)>=datetime.fromisoformat(a['expires_at']) or datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat()!='2026-11-01':raise ValueError('Approval expired')
 items=a['approved_items']
 if len(items)!=28 or sum(x['kind']=='ad_set_bid'for x in items)!=4 or sum(x['kind']=='ad_exclude_sku'for x in items)!=24:raise ValueError('Wrong action count')
 if any(x.get('target_minor',0)>=x['old_minor']for x in items if x['kind']=='ad_set_bid'):raise ValueError('No raises authorized')
 return items
def mutation(cid,kind,items):
 if not items or len({x['nm_id']for x in items})!=len(items) or any(x['campaign_id']!=cid or x['kind']!=kind for x in items):raise ValueError('Mixed or duplicate batch')
 if kind=='ad_set_bid':return '/api/advert/v1/bids',dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=x['nm_id'],bid_kopecks=x['target_minor'],placement=x['placement'])for x in items])])
 if kind=='ad_exclude_sku':return '/adv/v0/auction/nms',dict(nms=[dict(advert_id=cid,nms=dict(add=[],delete=[x['nm_id']for x in items]))])
 raise ValueError('Unapproved mutation')
def check_write(path,method,body,items):
 if method!='PATCH':raise ValueError('Only exact PATCH authorized')
 candidates=[]
 for cid,kind in sorted({(x['campaign_id'],x['kind'])for x in items}):
  batch=[x for x in items if x['campaign_id']==cid and x['kind']==kind]
  # A preflight-blocked subset is allowed; additional items never are.
  if kind=='ad_set_bid':nms=[x.get('nm_id')for g in body.get('bids',[])for x in g.get('nm_bids',[])]
  else:nms=[x for g in body.get('nms',[])for x in g.get('nms',{}).get('delete',[])]
  selected=[x for x in batch if x['nm_id']in nms]
  if selected and mutation(cid,kind,selected)==(path,body):candidates.append(selected)
 if len(candidates)!=1:raise ValueError('Write outside frozen approval')
class ScopedWB(WB):
 def __init__(self,items):super().__init__();self.items=items
 def req(self,path,method='GET',body=None,write=False):
  if write:check_write(path,method,body,self.items)
  return super().req(path,method,body,write)
def expected(cp,items):
 out=copy.deepcopy(cp)
 for x in items:
  ns=[n for n in out['nm_settings']if n['nm_id']==x['nm_id']]
  if len(ns)!=1 or ns[0]['bids_kopecks'].get(x['placement'])!=x['old_minor']:raise ValueError('Current membership or bid changed')
  if x['kind']=='ad_set_bid':
   if not 0<x['target_minor']<x['old_minor']:raise ValueError('Not an approved reduction')
   ns[0]['bids_kopecks'][x['placement']]=x['target_minor']
  elif x['kind']=='ad_exclude_sku':out['nm_settings']=[n for n in out['nm_settings']if n['nm_id']!=x['nm_id']]
  else:raise ValueError('Unsupported action')
 if not out['nm_settings']:raise ValueError('Cannot empty campaign')
 return out
def put(c,key,value):
 value=json.loads(json.dumps(value))
 try:c.put(key,value)
 except Exception as ex:
  if c.get(key)==value:return
  if not (str(ex).startswith('Private state HTTP')or type(ex).__name__in['Timeout','ConnectionError','ReadTimeout']):raise
  time.sleep(2);c.put(key,value)
def main(resume=False):
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 c=Cache();items=approval(c)
 prior=c.get(ROOT+':execution')
 if prior and not resume:print('Existing execution: never repeat');return
 if resume:
  if not prior or prior.get('status')not in ['partial_or_uncertain','partial_or_blocked','blocked']:raise ValueError('No terminal partial execution to resume')
  for key in prior.get('steps',{}).values():
   if (c.get(key)or{}).get('status')!='verified':raise ValueError('Unresolved child: no mutation retry')
  if not c.create(ROOT+':resume1_lease',dict(started_at=stamp())):return
 w=ScopedWB(items);validate_identity(c,w)
 if prior:
  e=copy.deepcopy(prior);e.setdefault('prior_attempts',[]).append({k:copy.deepcopy(e.get(k))for k in ['status','reason','preflight','completed_at']});e['preflight']=[];e.update(status='preflight',resume_started_at=stamp());e.pop('reason',None)
 else:
  e=dict(status='preflight',created_at=stamp(),approval_key=ROOT+':approval',scope_sha256=SCOPE,png_sha256=PNG,items=items,steps={},preflight=[],wb_writes=0,budget_writes=0,price_writes=0,telegram_calls=0)
  if not c.create(ROOT+':execution',e):raise ValueError('Concurrent execution')
 def save():put(c,ROOT+':execution',e)
 try:
  from china_advertising_state import AdvertisingIO
  from china_moysklad_read import read_stock
  import requests
  ids=sorted({x['campaign_id']for x in items});campaigns=w.campaigns(ids);e.setdefault('before',copy.deepcopy(campaigns));e['latest_preflight_campaigns']=copy.deepcopy(campaigns)
  e['budgets']=w.req('/api/advert/v2/budget','POST',dict(advertIds=ids));e['budget_observed_at']=stamp();save()
  stock=read_stock(sorted({x['article']for x in items}));e['stock']=stock
  prices=AdvertisingIO().prices(sorted({x['nm_id']for x in items}));e['prices']=prices;e['prices_observed_at']=stamp()
  rr=requests.get('https://advert-api.wildberries.ru/api/advert/v1/config',headers={'Authorization':w.token},timeout=50);rr.raise_for_status();cfg=rr.json();e['config']=cfg
  if cfg.get('currency')!='CNY' or type(cfg.get('cpcStep'))is not int or cfg['cpcStep']<=0:raise ValueError('Unknown bid step')
  original=c.get('china_agent:owner_intraday_review:2026-11-01:v1:inputs');oldprices={r['nm_id']:r['seller_price']for r in original['inputs']['prices']['rows']};sm={r['article'].casefold():r for r in stock['rows']}
  e['minimums']={};eligible=[]
  for cid in ids:
   group=[x for x in items if x['campaign_id']==cid];cp=campaigns[str(cid)]
   for z in sorted({x['placement']for x in group}):e['minimums'][str(cid)+':'+z]=w.minimums(cid,[x['nm_id']for x in group if x['placement']==z],z)
   for x in group:
    result=dict(id=x['id'],campaign_id=cid,nm_id=x['nm_id'],article=x['article'],status='ready')
    try:
     if cp['status']!=9 or cp['currency']!='CNY' or cp['bid_type']!='manual' or cp['settings']['payment_type']!='cpc' or cp['settings']['placements'].get(x['placement'])is not True:raise ValueError('Campaign status or placement changed')
     ns=[n for n in cp['nm_settings']if n['nm_id']==x['nm_id']]
     if not ns and x['kind']=='ad_exclude_sku':result['status']='already_absent';e['preflight'].append(result);continue
     if ns and x['kind']=='ad_set_bid' and ns[0]['bids_kopecks'].get(x['placement'])==x['target_minor']:result['status']='already_target';e['preflight'].append(result);continue
     expected(cp,[x]);g=prices[str(x['nm_id'])];ps={s['discountedPrice']for s in g['sizes']}
     if g['vendorCode'].casefold()!=x['article'].casefold() or g['currencyIsoCode4217']!='CNY' or ps!={oldprices[x['nm_id']]}:raise ValueError('Seller price or article changed since PNG')
     st=sm[x['article'].casefold()];result.update(price_cny=next(iter(ps)),stock_free=st['stock']-st['reserve'],cogs_rub=st.get('price',0)/100)
     minimum=e['minimums'][str(cid)+':'+x['placement']][x['nm_id']];result['minimum_minor']=minimum
     if x['kind']=='ad_set_bid':
      if x['target_minor']<minimum or x['target_minor']%cfg['cpcStep']:raise ValueError('Approved target below fresh minimum or outside step')
     elif cp.get('restrictions',{}).get('can_change_nms')is not True or minimum<x['old_minor']:raise ValueError('Composition locked or lower-cost bid alternative appeared')
     eligible.append(x)
    except (ValueError,KeyError,TypeError)as ex:result.update(status='blocked',reason=str(ex)if isinstance(ex,ValueError)else type(ex).__name__)
    e['preflight'].append(result)
   save()
  e.update(status='applying',preflight_verified_at=stamp());save()
  for cid in ids:
   stopped=False
   for kind in ['ad_set_bid','ad_exclude_sku']:
    batch=[x for x in eligible if x['campaign_id']==cid and x['kind']==kind]
    if not batch or stopped:continue
    approval(c);key=ROOT+':'+str(cid)+':'+kind+':execution'
    existing=c.get(key)
    if existing:
     if existing.get('status')=='verified':continue
     raise ValueError('Existing unresolved child; never repeat')
    before=w.campaigns([cid])[str(cid)]
    if before['status']!=9 or before['currency']!='CNY' or before['bid_type']!='manual' or before['settings']['payment_type']!='cpc' or any(before['settings']['placements'].get(x['placement'])is not True for x in batch):raise ValueError('Campaign mode changed after preflight')
    if kind=='ad_exclude_sku' and before.get('restrictions',{}).get('can_change_nms')is not True:raise ValueError('Composition locked after preflight')
    target=expected(before,batch);path,body=mutation(cid,kind,batch);check_write(path,'PATCH',body,items)
    step=dict(status='submitting',before=before,expected=target,items=batch,body=body,parent=ROOT+':execution',approval_key=ROOT+':approval',submitted_at=stamp(),preflight_projection_changed=projection(before)!=projection(campaigns[str(cid)]))
    if not c.create(key,step):raise ValueError('Duplicate child')
    e['steps'][str(cid)+':'+kind]=key;save()
    try:
     e['wb_writes']+=1;save();response=w.req(path,'PATCH',body,write=True)
     step.update(status='accepted',response=response);put(c,key,step)
     for attempt in range(4):
      after=w.campaigns([cid])[str(cid)];step['after']=after
      if projection(after)==projection(target):break
      if attempt<3:time.sleep(3)
     else:raise ValueError('WB readback mismatch; never repeat')
     step.update(status='verified',verified_at=stamp());put(c,key,step);campaigns[str(cid)]=after
     reg=c.get('china_agent:verified_campaign_state:v1')or{};reg[str(cid)]=key;put(c,'china_agent:verified_campaign_state:v1',reg)
    except Exception as ex:
     step.update(status='uncertain',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__);put(c,key,step);stopped=True
    save()
  children=[c.get(k)or{}for k in e['steps'].values()];e['verified_items']=sum(len(s['items'])for s in children if s.get('status')=='verified')
  e.update(status='verified'if e['verified_items']==len(items) else 'partial_or_blocked',completed_at=stamp())
 except Exception as ex:e.update(status='partial_or_uncertain'if e['steps']else'blocked',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__,completed_at=stamp())
 save();print(json.dumps({k:e.get(k)for k in ['status','verified_items','wb_writes','budget_writes','price_writes','telegram_calls','reason']}))
if __name__=='__main__':main()

