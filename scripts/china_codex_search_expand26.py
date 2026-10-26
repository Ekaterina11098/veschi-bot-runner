"""Exact owner-approved16bags+5umbrellas at fresh minima; other categories inspect only."""
import os,json,copy,time
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity
from china_price_apply import IO
ROOT='china_agent:codex_search_expand26:v1:'
def iso():return datetime.now(timezone.utc).isoformat()
def members(c):return {str(n['nm_id']):dict(subject_id=n['subject']['id'],bids=dict(n['bids_kopecks'])) for n in c['nm_settings']}
def stable(c):return {k:c[k] for k in ['id','status','currency','bid_type','settings']}
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise RuntimeError('Public main only')
 c=Cache();w=WB();validate_identity(c,w);a=c.get(ROOT+'approval') or {}
 if a.get('status')!='approved' or a.get('owner_id')!=5122667182 or a.get('minimum_bid_only')is not True:raise RuntimeError('Exact owner approval absent')
 if (datetime.now(timezone.utc)-datetime.fromisoformat(a['created_at'])).total_seconds()>7200:raise RuntimeError('Approval expired')
 if c.get(ROOT+'execution'):raise RuntimeError('Existing execution; never repeat writes')
 e=dict(status='preflight',created_at=iso(),groups=[],steps={},wb_writes=0,telegram_sends=0,stock_writes=0,budget_writes=0,inspect_only=a['inspect_only'])
 if not c.create(ROOT+'execution',e):return
 def save():c.put(ROOT+'execution',json.loads(json.dumps(e)))
 def write(step,path,body):
  if step in e['steps']:raise RuntimeError('No repeat write')
  e['steps'][step]=dict(status='submitting',path=path,body=body,submitted_at=iso());save()
  try:r=w.req(path,'PATCH',body,write=True)
  except Exception:e['steps'][step]['status']='uncertain';save();raise
  e['steps'][step].update(status='accepted',response=r);e['wb_writes']+=1;save()
 try:
  inv=w.req('/adv/v1/promotion/count')
  ids=sorted({x['advertId'] for g in inv.get('adverts',[]) if g['status'] in [4,9,11] for x in g.get('advert_list',[])})
  campaigns={}
  for pos in range(0,len(ids),50):campaigns.update(w.campaigns(ids[pos:pos+50]))
  e['catalogue_read_at']=iso()
  e['search_campaigns']=[dict(id=x['id'],name=x['settings']['name'],status=x['status'],subjects=sorted({n['subject']['id'] for n in x['nm_settings']}),nm_ids=[n['nm_id'] for n in x['nm_settings']]) for x in campaigns.values() if x['settings']['placements'].get('search')]
  # Category compatibility is based on actual WB subject IDs; no category creation is authorized.
  e['category_inspection']=dict(belts=[x for x in e['search_campaigns'] if 51 in x['subjects']],other_categories=e['search_campaigns'])
  os.environ.setdefault('CHINA_TELEGRAM_BOT_TOKEN','');pio=IO()
  prices=pio.prices([str(i['nm_id']) for g in a['groups'] for i in g['items']])
  for g in a['groups']:
   cid=g['campaign_id'];before=campaigns[str(cid)]
   if before['status']!=9 or before['currency']!='CNY' or before['bid_type']!='manual' or before['settings']['payment_type']!='cpc' or before['settings']['placements']!=dict(search=True,recommendations=False):raise RuntimeError('Target campaign not active manual CNY search')
   old=members(before)
   if {x['subject_id'] for x in old.values()}!={g['subject_id']}:raise RuntimeError('Target category mismatch')
   missing=[i['nm_id'] for i in g['items'] if str(i['nm_id']) not in old]
   if len(old)+len(missing)>50:raise RuntimeError('Campaign SKU capacity would exceed50')
   for i in g['items']:
    p=prices[str(i['nm_id'])]
    if p['vendorCode']!=i['article'] or p['currencyIsoCode4217']!='CNY':raise RuntimeError('Exact SKU identity changed')
    duplicates=[x['id'] for x in campaigns.values() if x['id']!=cid and x['status']==9 and x['settings']['placements'].get('search') and str(i['nm_id']) in members(x)]
    if duplicates:raise RuntimeError('SKU already in another active search campaign: '+i['article'])
   # Future SKU minima are requested before membership changes.
   minimum=w.minimums(cid,[i['nm_id'] for i in g['items']],'search')
   if any(type(v)is not int or v<=0 for v in minimum.values()):raise RuntimeError('Unknown fresh minimum')
   state=dict(campaign_id=cid,before=before,items=g['items'],minimums={str(k):v for k,v in minimum.items()},missing=missing,status='preflight')
   e['groups'].append(state);save()
  target_ids=[g['campaign_id'] for g in a['groups']]
  day=datetime.now(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date().isoformat()
  e['baseline_fullstats']=w.req('/adv/v3/fullstats?ids='+','.join(map(str,target_ids))+'&beginDate='+day+'&endDate='+day);e['baseline_observed_at']=iso();save()
  for state in e['groups']:
   cid=state['campaign_id'];before=state['before'];old=members(before)
   fresh=w.campaigns([cid])[str(cid)]
   if stable(fresh)!=stable(before) or members(fresh)!=old:raise RuntimeError('Campaign changed during preflight')
   if state['missing']:
    write(str(cid)+':add','/adv/v0/auction/nms',dict(nms=[dict(advert_id=cid,nms=dict(add=state['missing'],delete=[]))]))
    mid=w.campaigns([cid])[str(cid)];mm=members(mid)
    if set(mm)!=set(old)|{str(n) for n in state['missing']} or stable(mid)!=stable(before) or any(mm[k]!=v for k,v in old.items()):raise RuntimeError('Membership readback mismatch')
    e['steps'][str(cid)+':add']['status']='verified';state['after_membership']=mid;save()
   else:mid=fresh;mm=members(mid)
   # Refresh minimum again after addition; owner explicitly authorized actual minimum.
   mins=w.minimums(cid,[i['nm_id'] for i in state['items']],'search')
   state['minimums']={str(k):v for k,v in mins.items()};save()
   bids=[dict(nm_id=i['nm_id'],bid_kopecks=mins[i['nm_id']],placement='search') for i in state['items']]
   write(str(cid)+':bids','/api/advert/v1/bids',dict(bids=[dict(advert_id=cid,nm_bids=bids)]))
   after=w.campaigns([cid])[str(cid)];expected=copy.deepcopy(mm)
   for i in state['items']:expected[str(i['nm_id'])]['bids']['search']=mins[i['nm_id']]
   if stable(after)!=stable(before) or members(after)!=expected:raise RuntimeError('Minimum bids exact readback mismatch')
   e['steps'][str(cid)+':bids']['status']='verified'
   state.update(status='verified',after=after,verified_at=iso());save()
   ck=ROOT+str(cid)+':execution'
   c.put(ck,dict(status='verified',before=before,after=after,items=[dict(kind='ad_add_sku',nm_id=i['nm_id'],article=i['article'],placement='search',target_minor=mins[i['nm_id']]) for i in state['items']],verified_at=state['verified_at'],parent=ROOT+'execution',baseline_fullstats=e['baseline_fullstats']))
   reg=c.get('china_agent:verified_campaign_state:v1') or {};reg[str(cid)]=ck;c.put('china_agent:verified_campaign_state:v1',reg)
  e.update(status='verified',completed_at=iso());save()
 except Exception as ex:
  e.update(status='uncertain' if any(v['status']in ['submitting','accepted','uncertain'] for v in e['steps'].values()) else 'blocked',reason=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__,completed_at=iso());save()
 finally:
  verified=[g for g in e['groups'] if g.get('status')=='verified']
  if verified:
   c.put('china_agent:search_trials:v1',dict(status='active',owner_authorized=True,started_at=e['baseline_observed_at'],baseline_fullstats=e['baseline_fullstats'],execution_key=ROOT+'execution',items=[dict(campaign_id=g['campaign_id'],nm_id=i['nm_id'],article=i['article'],bid_minor=g['minimums'][str(i['nm_id'])],added_at=g['verified_at'],group='bags' if g['campaign_id']==41298169 else 'umbrellas') for g in verified for i in g['items']],report_slots=['morning','midday'],hourly_autonomy=False,automatic_writes=False))
  print('Owner search expansion result: '+e['status'])
if __name__=='__main__':run()
