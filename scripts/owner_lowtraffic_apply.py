"""Dated explicit owner scope: two CPC raises and two explicitly approved retests. No funding or Telegram."""
import copy,json,hashlib,os,time
from datetime import datetime,timezone,date
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from china_cloud_cost_control import Cache,WB,validate_identity,stamp
ROOT='china_agent:owner_lowtraffic_apply:2026-11-02:v1'
MSK=ZoneInfo('Europe/Moscow')
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def projection(cp):
 return dict(id=cp['id'],status=cp['status'],currency=cp['currency'],bid_type=cp['bid_type'],settings=cp['settings'],nms={str(n['nm_id']):dict(subject=n['subject']['id'],bids=n['bids_kopecks'])for n in cp['nm_settings']})
def approval(c):
 a=c.get(ROOT+':approval')or{};items=a.get('approved_items',[])
 if a.get('status')!='approved'or a.get('owner_user_id')!=5122667182 or a.get('source_channel')!='codex'or a.get('cabinet')!='token_3'or a.get('execution_authorized')is not True:raise ValueError('Exact owner approval absent')
 if datetime.now(timezone.utc)>=datetime.fromisoformat(a['expires_at'])or datetime.now(MSK).date()!=date(2026,11,2):raise ValueError('Dated approval expired')
 if digest(items)!=a.get('scope_sha256')or len(items)!=2:raise ValueError('Scope hash mismatch')
 expected={(41298169,1473243900,28,30),(40933588,1473243914,28,30)}
 if {(x['campaign_id'],x['nm_id'],x['old_minor'],x['target_minor'])for x in items}!=expected or any(x['kind']!='ad_set_bid' or x['placement']!=('search' if x['campaign_id']==41298169 else 'recommendations')for x in items):raise ValueError('Only exact two owner raises authorized')
 return a,items

def mutation(cid,kind,items):
 if not items or len({x['nm_id']for x in items})!=len(items)or any(x['campaign_id']!=cid for x in items):raise ValueError('Mixed or duplicate group')
 if kind=='bids':return '/api/advert/v1/bids',dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=x['nm_id'],placement=x['placement'],bid_kopecks=x['target_minor'])for x in items])])
 if kind=='add'and len(items)==1 and items[0]['kind']=='ad_add_sku':return '/adv/v0/auction/nms',dict(nms=[dict(advert_id=cid,nms=dict(add=[items[0]['nm_id']],delete=[]))])
 raise ValueError('Mutation kind unapproved')
def check_write(path,method,body,approved):
 if method.upper()!='PATCH':raise ValueError('Only exact PATCH allowed')
 for cid in {x['campaign_id']for x in approved}:
  for kind in ['bids','add']:
   group=[x for x in approved if x['campaign_id']==cid and(kind=='bids'or x['kind']=='ad_add_sku')]
   ids=[x.get('nm_id')for g in body.get('bids',[])for x in g.get('nm_bids',[])]if kind=='bids'else[x for g in body.get('nms',[])for x in g.get('nms',{}).get('add',[])]
   chosen=[x for x in group if x['nm_id']in ids]
   if chosen and mutation(cid,kind,chosen)==(path,body):return
 raise ValueError('Write outside owner scope')
def expected_bid(cp,items):
 out=copy.deepcopy(cp)
 for x in items:
  ns=[n for n in out['nm_settings']if n['nm_id']==x['nm_id']]
  if len(ns)!=1:raise ValueError('Approved member missing')
  ns[0]['bids_kopecks'][x['placement']]=x['target_minor']
 return out
def membership_exact(before,after,item):
 bp,ap=projection(before),projection(after);new=str(item['nm_id'])
 if set(ap['nms'])!=set(bp['nms'])|{new}:return False
 if any(ap[k]!=bp[k]for k in ['id','status','currency','bid_type','settings']):return False
 if any(ap['nms'][k]!=v for k,v in bp['nms'].items()):return False
 if ap['nms'][new]['subject']!=61:return False
 return all(v==0 for k,v in ap['nms'][new]['bids'].items()if k!=item['placement'])
def put(c,key,value):
 value=json.loads(json.dumps(value))
 try:c.put(key,value)
 except Exception:
  if c.get(key)==value:return
  raise
class ScopedWB(WB):
 def __init__(self,items):super().__init__();self.items=items
 def req(self,path,method='GET',body=None,write=False):
  if write:check_write(path,method,body,self.items)
  return super().req(path,method,body,write)
def main():
 import requests
 from china_advertising_state import AdvertisingIO
 from china_moysklad_read import read_stock
 class Prices(AdvertisingIO):
  def __init__(self,token):self.token=token
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner'or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 c=Cache();a,items=approval(c)
 if c.get(ROOT+':execution'):print('Existing execution: no replay');return
 wb=ScopedWB(items);validate_identity(c,wb);original=requests.sessions.Session.request
 def guard(session,method,url,*args,**kw):
  u=urlparse(url);m=method.upper();body=kw.get('json')
  db=u.scheme=='https'and u.hostname==urlparse(c.url).hostname and u.path.startswith('/rest/v1/')and(m=='GET'or m in ['POST','PATCH']and u.path=='/rest/v1/telegram_api_cache')
  ads=u.scheme=='https'and u.hostname=='advert-api.wildberries.ru'and((m=='GET'and u.path in ['/adv/v1/promotion/count','/api/advert/v2/adverts','/api/advert/v1/config'])or(m=='POST'and u.path in ['/api/advert/v2/budget','/api/advert/v1/bids/min']))
  if u.scheme=='https'and u.hostname=='advert-api.wildberries.ru'and m=='PATCH':check_write(u.path,m,body,items);return original(session,method,url,*args,**kw)
  prices=u.scheme=='https'and u.hostname=='discounts-prices-api.wildberries.ru'and m=='GET'and u.path=='/api/v2/list/goods/filter'
  stock=u.scheme=='https'and u.hostname=='marketplace-api.wildberries.ru'and m=='POST'and u.path=='/api/v3/stocks/2126188'and isinstance(body,dict)and set(body)=={'chrtIds'}
  ms=u.scheme=='https'and u.hostname=='api.moysklad.ru'and m=='GET'and u.path in ['/api/remap/1.2/entity/store','/api/remap/1.2/entity/product','/api/remap/1.2/report/stock/all']
  if not(db or ads or prices or stock or ms):raise PermissionError('External endpoint outside owner scope')
  return original(session,method,url,*args,**kw)
 requests.sessions.Session.request=guard
 e=dict(status='preflight',created_at=stamp(),items=items,steps={},preflight=[],approval_key=ROOT+':approval',proposal_key=a['proposal_key'],scope_sha256=a['scope_sha256'],wb_writes=0,budget_writes=0,price_writes=0,telegram_calls=0)
 def save():put(c,ROOT+':execution',e)
 try:
  if not c.create(ROOT+':execution',e):print('Concurrent execution: no replay');return
  inv=wb.req('/adv/v1/promotion/count');allids=sorted({n['advertId']for g in inv.get('adverts',[])if g['status']in[9,11]for n in g.get('advert_list',[])})
  cs=wb.campaigns(allids);e['before']=copy.deepcopy(cs)
  prices=Prices(wb.token).prices([x['nm_id']for x in items]);e['prices']=prices;e['prices_at']=stamp()
  stock=read_stock([x['article']for x in items]);e['stock']=stock;sm={r['article']:r for r in stock['rows']}
  sizes=[s['sizeID']for p in prices.values()for s in p['sizes']]
  rr=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',headers={'Authorization':wb.token},json={'chrtIds':sizes},timeout=50);rr.raise_for_status();e['published_stock']=rr.json();pub={r['chrtId']:r['amount']for r in rr.json()['stocks']}
  rr=requests.get('https://advert-api.wildberries.ru/api/advert/v1/config',headers={'Authorization':wb.token},timeout=45);rr.raise_for_status();cfg=rr.json();e['config']=cfg
  if cfg.get('currency')!='CNY'or not cfg.get('cpcStep'):raise ValueError('CPC config unknown')
  ids=sorted({x['campaign_id']for x in items});e['budgets']=wb.req('/api/advert/v2/budget','POST',dict(advertIds=ids));balances={r['advertId']:r['total']for r in e['budgets']['adverts']}
  # A same-MSK-day verified raise must not be compounded in another campaign.
  raised=set()
  for cid,key in(c.get('china_agent:verified_campaign_state:v1')or{}).items():
   rc=c.get(key)or{};at=rc.get('verified_at')or rc.get('submitted_at')
   if rc.get('status')!='verified'or not at:continue
   if datetime.fromisoformat(at.replace('Z','+00:00').replace(' UTC','+00:00')).astimezone(MSK).date()!=date(2026,11,2):continue
   old={n['nm_id']:n for n in(rc.get('before')or{}).get('nm_settings',[])}
   for n in(rc.get('after')or{}).get('nm_settings',[]):
    if n['nm_id']in old and any(n['bids_kopecks'].get(z,0)>old[n['nm_id']]['bids_kopecks'].get(z,0)for z in ['search','recommendations']):raised.add(n['nm_id'])
  minima={};eligible=[];already=[]
  for x in items:
   r=dict(article=x['article'],nm_id=x['nm_id'],campaign_id=x['campaign_id'],status='ready')
   try:
    cp=cs[str(x['campaign_id'])];g=prices[str(x['nm_id'])];ev=x['evidence'];st=sm[x['article']]
    if cp['status']!=9 or cp['currency']!='CNY'or cp['bid_type']!='manual'or cp['settings']['payment_type']!='cpc'or cp['settings']['placements'].get(x['placement'])is not True:raise ValueError('Campaign mode changed')
    if balances.get(cp['id'],0)<=0:raise ValueError('No positive campaign budget; funding not approved')
    if g['vendorCode']!=x['article']or g['currencyIsoCode4217']!='CNY'or {s['discountedPrice']for s in g['sizes']}!={ev['price_cny']}:raise ValueError('Seller price or article changed')
    if st.get('stock')is None or st.get('reserve')is None or st['stock']-st['reserve']<=0 or not st.get('price')or st['price']<=0:raise ValueError('Stock/reserve or COGS unavailable')
    if not g['sizes']or any(s['sizeID']not in pub for s in g['sizes'])or sum(pub[s['sizeID']]for s in g['sizes'])<=0:raise ValueError('Published WB stock unavailable')
    margin=ev['margin_before_ads']-ev['q']*(st['price']/100-ev['cogs_rub'])/ev['fx_rub_per_cny']
    if margin<=ev['cpa_target']:raise ValueError('Current preliminary economics no longer positive after modeled ads')
    if x['target_minor']%cfg['cpcStep']or not 0<x['target_minor']<=cfg['cpcMaxBid']:raise ValueError('Bid outside current step/max')
    ns=next((n for n in cp['nm_settings']if n['nm_id']==x['nm_id']),None)
    if x['kind']=='ad_set_bid':
     if ns is None:raise ValueError('Approved existing member missing')
     current=ns['bids_kopecks'][x['placement']]
     if current==x['target_minor']:r['status']='already_target';already.append(x);e['preflight'].append(r);continue
     if current!=x['old_minor']or x['nm_id']in raised:raise ValueError('Bid changed or product already raised today')
     key=str(cp['id'])+':'+x['placement']
     if key not in minima:
      group=[v['nm_id']for v in items if v['campaign_id']==cp['id']and v['placement']==x['placement']and v['kind']=='ad_set_bid']
      minima[key]=wb.minimums(cp['id'],group,x['placement'])
     minimum=minima[key][x['nm_id']]
    else:
     if ns:
      if ns['bids_kopecks'][x['placement']]!=x['target_minor']:raise ValueError('Retest product already present with unexpected bid')
      r['status']='already_target';already.append(x);e['preflight'].append(r);continue
     if any(any(n['nm_id']==x['nm_id']for n in q['nm_settings'])for q in cs.values()if q['status']==9):raise ValueError('Retest product already in another active campaign')
     if not cp.get('restrictions',{}).get('can_change_nms')or len(cp['nm_settings'])>=50:raise ValueError('Membership locked or capacity full')
     if {n['subject']['id']for n in cp['nm_settings']}!={61}:raise ValueError('Addition category mismatch')
     peer=cp['nm_settings'][0]['nm_id'];minimum=wb.minimums(cp['id'],[peer],x['placement'])[peer]
    if minimum>x['target_minor']:raise ValueError('Fresh minimum exceeds approved target')
    r.update(minimum_minor=minimum,price_cny=ev['price_cny'],stock_free=st['stock']-st['reserve'],published=sum(pub[s['sizeID']]for s in g['sizes']),cogs_rub=st['price']/100,preliminary_margin_before_ads=margin);eligible.append(x)
   except (ValueError,KeyError,TypeError,RuntimeError)as ex:r.update(status='blocked',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__)
   e['preflight'].append(r);save()
  e['minimums']=minima;e['status']='applying';save()
  def submit(cid,kind,batch):
   approval(c);key=ROOT+':'+str(cid)+':'+kind+(':'+str(batch[0]['nm_id'])if kind=='add'else'')+':execution'
   if c.get(key):raise ValueError('Child exists; never replay')
   before=wb.campaigns([cid])[str(cid)];base=cs[str(cid)]
   if projection(before)!=projection(base):raise ValueError('Campaign changed after preflight')
   path,body=mutation(cid,kind,batch);check_write(path,'PATCH',body,items)
   target=expected_bid(before,batch)if kind=='bids'else None
   step=dict(status='submitting',before=before,expected=target,items=batch,path=path,body=body,submitted_at=stamp(),parent=ROOT+':execution',approval_key=ROOT+':approval')
   if not c.create(key,step):raise ValueError('Concurrent child')
   e['steps'][str(cid)+':'+kind+(':'+str(batch[0]['nm_id'])if kind=='add'else'')]=key;save()
   try:
    e['wb_writes']+=1;save();step['response']=wb.req(path,'PATCH',body,write=True);step['status']='accepted';put(c,key,step)
    for attempt in range(4):
     after=wb.campaigns([cid])[str(cid)];step['after']=after
     good=projection(after)==projection(target)if kind=='bids'else membership_exact(before,after,batch[0])
     if good:break
     if attempt<3:time.sleep(3)
    else:raise ValueError('WB readback mismatch; no repeat')
    if kind=='add':
     x=batch[0];minimum=wb.minimums(cid,[x['nm_id']],x['placement'])[x['nm_id']];step['exact_added_minimum']=minimum
     ns=next(n for n in after['nm_settings']if n['nm_id']==x['nm_id'])
     if minimum>x['target_minor']or ns['bids_kopecks'][x['placement']]!=x['target_minor']:raise ValueError('Added membership present; bid/minimum differs from approved target, do not replay')
    step.update(status='verified',verified_at=stamp());put(c,key,step);cs[str(cid)]=after
    registry=c.get('china_agent:verified_campaign_state:v1')or{};registry[str(cid)]=key;put(c,'china_agent:verified_campaign_state:v1',registry)
   except Exception as ex:
    step.update(status='uncertain',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__);put(c,key,step);raise
   save()
  for cid in ids:
   batch=[x for x in eligible if x['campaign_id']==cid and x['kind']=='ad_set_bid']
   if batch:submit(cid,'bids',batch)
  for x in eligible:
   if x['kind']=='ad_add_sku':submit(x['campaign_id'],'add',[x])
  # Combined per-campaign receipts retain both raises and a later addition in the registry.
  registry=c.get('china_agent:verified_campaign_state:v1')or{}
  for cid in ids:
   group=[x for x in items if x['campaign_id']==cid]
   if any(r['status']=='blocked'for r in e['preflight']if r['campaign_id']==cid):continue
   receipt=dict(status='verified',verified_at=stamp(),before=e['before'][str(cid)],after=cs[str(cid)],items=group,parent=ROOT+':execution',approval_key=ROOT+':approval',child_keys=[v for k,v in e['steps'].items()if k.startswith(str(cid)+':')])
   key=ROOT+':'+str(cid)+':execution'
   if not c.create(key,receipt):raise ValueError('Combined receipt already exists')
   if c.get(key)!=json.loads(json.dumps(receipt)):raise ValueError('Combined receipt readback mismatch')
   registry[str(cid)]=key
  put(c,'china_agent:verified_campaign_state:v1',registry)
  children=[c.get(k)or{}for k in e['steps'].values()];e['verified_items']=sum(len(s['items'])for s in children if s.get('status')=='verified');e['already_target_items']=len(already)
  e.update(status='verified'if e['verified_items']+len(already)==len(items)else'partial_or_blocked',after={str(cid):cs[str(cid)]for cid in ids},completed_at=stamp());save()
 except Exception as ex:
  e.update(status='partial_or_uncertain'if e['steps']else'blocked',reason=str(ex)if isinstance(ex,(ValueError,RuntimeError))else type(ex).__name__,completed_at=stamp());save()
 finally:requests.sessions.Session.request=original
 print(json.dumps({k:e.get(k)for k in ['status','verified_items','already_target_items','wb_writes','budget_writes','price_writes','telegram_calls','reason']}))
if __name__=='__main__':main()

