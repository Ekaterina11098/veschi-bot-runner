"""Exact owner search addition, retaining recommendations. No funding or Telegram."""
import os,json,time,copy,requests
from datetime import datetime,timezone,timedelta
from china_cloud_cost_control import Cache,WB,stamp,validate_identity
from china_advertising_state import AdvertisingIO
ROOT="china_agent:owner_search669622_apply29:2026-10-29:v1"
CID=41298169
REC=41270309
STAGE=os.environ.get('ADD_STAGE','preflight')
class Prices(AdvertisingIO):
 def __init__(self):self.token=os.environ['WB_TOKEN_3']
 def tg(self,*a,**k):raise ValueError('No Telegram')
def proj(v):
 return dict(id=v['id'],status=v['status'],currency=v['currency'],bid_type=v['bid_type'],settings=v['settings'],nm_settings=sorted(v['nm_settings'],key=lambda n:n['nm_id']))
def save(c,e):c.put(ROOT+':execution',json.loads(json.dumps(e,allow_nan=False)))
def main():
 assert os.environ['GITHUB_REPOSITORY']=='Ekaterina11098/veschi-bot-runner' and os.environ['GITHUB_REF']=='refs/heads/main'
 assert datetime.now(timezone(timedelta(hours=3))).date().isoformat()=='2026-10-29'
 c=Cache();w=WB();validate_identity(c,w);a=c.get(ROOT+':approval')
 assert a['status']=='approved' and a['owner_user_id']==5122667182 and a['campaign_id']==CID and a['keep_recommendations'] and a['budget_change']==0
 assert datetime.now(timezone.utc)<datetime.fromisoformat(a['expires_at'])
 ns=sorted(x['nm_id'] for x in a['items']);assert ns==[1473243820,1473244353]
 assert c.create(ROOT+':'+STAGE+':guard',dict(at=stamp())),'Existing stage guard: inspect canonical state; no blind repeat'
 e=c.get(ROOT+':execution') or dict(status='preflight',created_at=stamp(),steps=[],approval_key=ROOT+':approval',WBwrites=0,TelegramSends=0)
 try:
  if STAGE in ['preflight','preflight_retry']:
   e['status']='preflight';save(c,e)
   current=w.campaigns([CID,REC]);before=current[str(CID)];rec=current[str(REC)]
   assert before['status']==9 and before['currency']=='CNY' and before['bid_type']=='manual' and before['settings']['payment_type']=='cpc' and before['settings']['placements']==dict(search=True,recommendations=False),'Destination settings changed'
   assert all(any(n['nm_id']==nm for n in rec['nm_settings']) for nm in ns),'Source recommendation membership missing'
   assert rec['status']==9 and rec['settings']['placements']['recommendations']
   e['before']=before;e['recommendations_before']=rec;e['preflight_at']=stamp();save(c,e)
   try:rates=w.minimums(CID,ns,'search');e['minimum_source_campaign']=CID
   except RuntimeError:
    rates=w.minimums(REC,ns,'search');e['minimum_source_campaign']=REC
   assert set(rates)==set(ns) and all(0<r<=a['maximum_search_minor'] for r in rates.values()),'Minimum exceeds approved search cap'
   e['minimums']={str(k):v for k,v in rates.items()};e['minimums_at']=stamp()
   prices=Prices().prices(ns)
   assert all(p['currencyIsoCode4217']=='CNY' for p in prices.values()),'Price currency mismatch'
   e['prices']=prices;e['prices_at']=stamp()
   headers={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN'],'Accept-Encoding':'gzip'}
   def get(path,params):
    for attempt in range(2):
     try:
      r=requests.get('https://api.moysklad.ru/api/remap/1.2'+path,params=params,headers=headers,timeout=35)
      break
     except requests.exceptions.RequestException:
      if attempt:raise
      time.sleep(2)
    assert r.ok,'MoySklad read HTTP '+str(r.status_code)
    return r.json()
   stores=get('/entity/store',dict(limit=1000));assert stores['meta']['size']<=len(stores['rows'])
   stores=[s for s in stores['rows'] if s.get('name')=='МСК' and not s.get('archived')];assert len(stores)==1
   names={x['article'] for x in a['items']};rows=[];offset=0
   while True:
    j=get('/report/stock/all',dict(filter='store='+stores[0]['meta']['href']+';stockMode=all;quantityMode=all',limit=100,offset=offset))
    part=j['rows'];rows.extend({k:r.get(k) for k in ['article','stock','reserve','price']} for r in part if r.get('article') in names)
    offset+=len(part)
    c.put(ROOT+':stock_progress',dict(offset=offset,total=j['meta']['size'],at=stamp()))
    if offset>=j['meta']['size']:break
    assert part and offset<50000
   assert len(rows)==2 and {r['article'] for r in rows}==names,'Stock article ambiguity'
   assert all(isinstance(r['stock'],(int,float)) and isinstance(r['reserve'],(int,float)) and r['stock']-r['reserve']>=30 and r['price']>0 for r in rows),'Available MSK stock or COGS insufficient'
   e['stock']=dict(observed_at=stamp(),warehouse='МСК',rows=rows);e['economics']=[]
   for item in a['items']:
    nm=item['nm_id'];p=prices[str(nm)];assert p['vendorCode']==item['article'],'Article identity mismatch'
    price=p['sizes'][0]['discountedPrice'];stock=next(r for r in rows if r['article']==item['article']);cost=stock['price']/1200
    logistics=12 if nm==1473243820 else 35
    scenarios={str(cr):.5*(.75*price-cost)-logistics-10/12-(rates[nm]/100)/cr for cr in [.01,.02,.03]}
    assert max(scenarios.values())>0,'No positive preliminary scenario'
    e['economics'].append(dict(nm_id=nm,price_cny=price,cogs_cny=cost,buyout_scenario=.5,commission=.20,tax=.05,handling_rub=10,fx=12,logistics_cny=logistics,logistics_qualification='669 dated default12;622 unknown,conservative assumption35,not measured actual',CR_scenarios=scenarios))
   e['budget_before']=w.req('/api/advert/v2/budget','POST',dict(advertIds=[CID,REC]));assert any(b['advertId']==CID and b['currency']=='CNY' and b['total']>0 for b in e['budget_before']['adverts'])
   e['baseline_fullstats']=w.req('/adv/v3/fullstats?ids='+str(CID)+','+str(REC)+'&beginDate=2026-10-29&endDate=2026-10-29')
   e['prepared_at']=stamp();e['status']='prepared';save(c,e);print('Fresh preflight complete privately; no WB changes')
  elif STAGE=='apply':
   assert e['status']=='prepared' and datetime.now(timezone.utc)-datetime.fromisoformat(e['prepared_at'])<timedelta(minutes=20),'Preflight stale'
   current=w.campaigns([CID,REC]);before=current[str(CID)];rec=current[str(REC)]
   assert proj(before)==proj(e['before']) and proj(rec)==proj(e['recommendations_before']),'State changed since preflight'
   missing=[nm for nm in ns if not any(n['nm_id']==nm for n in before['nm_settings'])]
   assert len(before['nm_settings'])+len(missing)<=100
   if missing:
    body=dict(nms=[dict(advert_id=CID,nms=dict(add=missing,delete=[]))])
    step=dict(label='add_two_to_existing_search',status='submitting',body=body,at=stamp());e['steps'].append(step);e['status']='applying';save(c,e)
    try:response=w.req('/adv/v0/auction/nms','PATCH',body,write=True)
    except Exception:
     step['status']='uncertain';save(c,e);raise
    step['status']='submitted';step['response']=response;e['WBwrites']=1;save(c,e)
   rates={int(k):v for k,v in e['minimums'].items()}
   old={n['nm_id']:n for n in before['nm_settings']}
   def checked(after,recafter):
    if proj(recafter)!=proj(rec):return False
    if {k:v for k,v in proj(after).items() if k!='nm_settings'}!={k:v for k,v in proj(before).items() if k!='nm_settings'}:return False
    got={n['nm_id']:n for n in after['nm_settings']}
    if set(got)!=set(old)|set(ns):return False
    if any(got[nm]!=v for nm,v in old.items()):return False
    return all(got[nm]['bids_kopecks']['search']==rates[nm] and got[nm]['bids_kopecks']['recommendations']==0 for nm in ns)
   for _ in range(20):
    afters=w.campaigns([CID,REC]);after=afters[str(CID)];recafter=afters[str(REC)]
    if checked(after,recafter):break
    time.sleep(6)
   e['after']=after;e['recommendations_after']=recafter;save(c,e)
   assert checked(after,recafter),'Exact addition or recommendation preservation readback mismatch'
   fresh=w.minimums(CID,ns,'search');assert fresh==rates,'Minimum changed after addition'
   e['minimums_after']={str(k):v for k,v in fresh.items()};e['status']='verified';e['verified_at']=stamp()
   for step in e['steps']:step['status']='verified'
   save(c,e);print('WB verified two exact minimum CPC search additions; recommendations preserved; no funding')
  else:raise ValueError('Unsupported stage')
 except Exception as ex:
  e['status']='uncertain' if any(s.get('status') in ['submitting','submitted','uncertain'] for s in e.get('steps',[])) else 'blocked'
  e['error']=str(ex) if isinstance(ex,(ValueError,AssertionError,RuntimeError)) else type(ex).__name__;e['failed_at']=stamp();save(c,e)
  raise RuntimeError('Owner operation stopped; inspect private canonical ledger') from None
if __name__=='__main__':main()
