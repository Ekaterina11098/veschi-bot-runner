"""Owner exact cohort16bags draft and5umbrellas existing; no funding/start/TG."""
import os,json,copy,time,requests
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity
from china_price_apply import IO
ROOT='china_agent:codex_search_expand26:v3:'
def iso():return datetime.now(timezone.utc).isoformat()
def members(c):return {str(n['nm_id']):dict(subject_id=n['subject']['id'],bids=dict(n['bids_kopecks'])) for n in c['nm_settings']}
def stable(c):return {k:c[k] for k in ['id','status','currency','bid_type','settings']}
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise RuntimeError('Public main only')
 c=Cache();w=WB();validate_identity(c,w);a=c.get(ROOT+'approval') or {}
 if a.get('status')!='approved' or a.get('owner_id')!=5122667182 or a.get('minimum_bid_only')is not True or a.get('create_bag_draft')is not True:raise RuntimeError('Exact approval missing')
 if (datetime.now(timezone.utc)-datetime.fromisoformat(a['created_at'])).total_seconds()>7200:raise RuntimeError('Approval expired')
 old=c.get('china_agent:codex_search_expand26:v2:execution')
 if old and old.get('wb_writes',0):raise RuntimeError('Earlier version wrote; reconcile')
 if c.get(ROOT+'execution'):raise RuntimeError('Existing execution; no repeat')
 e=dict(status='preflight',created_at=iso(),groups=[],steps={},wb_writes=0,budget_writes=0,start_writes=0,telegram_sends=0)
 if not c.create(ROOT+'execution',e):return
 def save():c.put(ROOT+'execution',json.loads(json.dumps(e)))
 def write(step,path,method,body):
  if step in e['steps']:raise RuntimeError('Never repeat write')
  e['steps'][step]=dict(status='submitting',path=path,body=body,submitted_at=iso());save()
  try:
   if path=='/adv/v2/seacat/save-ad':
    time.sleep(2);r=requests.post('https://advert-api.wildberries.ru'+path,headers={'Authorization':w.token},json=body,timeout=55)
    if not r.ok:raise RuntimeError('WB create HTTP '+str(r.status_code))
    result=r.json()
   else:result=w.req(path,method,body,write=True)
  except Exception:e['steps'][step]['status']='uncertain';save();raise
  e['steps'][step].update(status='accepted',response=result);e['wb_writes']+=1;save();return result
 try:
  inv=w.req('/adv/v1/promotion/count')
  ids=sorted({x['advertId'] for g in inv.get('adverts',[]) if g['status'] in [4,9,11] for x in g.get('advert_list',[])})
  campaigns={}
  for pos in range(0,len(ids),50):campaigns.update(w.campaigns(ids[pos:pos+50]))
  e['search_campaigns']=[dict(id=x['id'],name=x['settings']['name'],status=x['status'],subjects=sorted({n['subject']['id'] for n in x['nm_settings']}),nm_ids=[n['nm_id'] for n in x['nm_settings']]) for x in campaigns.values() if x['settings']['placements'].get('search')]
  e['inspection_only']=dict(items=a['inspect_only'],compatible_search_campaigns=e['search_campaigns']);save()
  os.environ.setdefault('CHINA_TELEGRAM_BOT_TOKEN','');pio=IO()
  ps=pio.prices([str(i['nm_id']) for g in a['groups'] for i in g['items']])
  for g in a['groups']:
   for i in g['items']:
    p=ps[str(i['nm_id'])]
    if p['vendorCode']!=i['article'] or p['currencyIsoCode4217']!='CNY':raise RuntimeError('SKU identity changed')
    duplicate=[x['id'] for x in campaigns.values() if x['id']!=g.get('campaign_id') and x['status']==9 and x['settings']['placements'].get('search') and str(i['nm_id']) in members(x)]
    if duplicate:raise RuntimeError('Another active search already contains '+i['article'])
  ug=next(g for g in a['groups'] if g['campaign_id'])
  ub=campaigns[str(ug['campaign_id'])]
  if ub['status']!=9 or ub['currency']!='CNY' or ub['bid_type']!='manual' or ub['settings']['payment_type']!='cpc' or ub['settings']['placements']!=dict(search=True,recommendations=False):raise RuntimeError('Existing umbrella campaign scope changed')
  if {n['subject']['id'] for n in ub['nm_settings']}!={61} or len(set(members(ub))|{str(i['nm_id']) for i in ug['items']})>50:raise RuntimeError('Umbrella category/capacity mismatch')
  day=datetime.now(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date().isoformat()
  e['baseline_fullstats']=[];e['baseline_observed_at']=iso();e['baseline_note']='Selected umbrella SKUs absent from active target before addition; new bag draft has no prior exposure';save()
  for g in a['groups']:
   state=dict(items=g['items'],status='preflight',campaign_id=g.get('campaign_id'));e['groups'].append(state);save()
   cid=g.get('campaign_id')
   if not cid:
    if any(x['settings']['name']==g['name'] for x in campaigns.values()):raise RuntimeError('Named cohort already exists; do not create again')
    result=write('bags:create','/adv/v2/seacat/save-ad','POST',dict(name=g['name'],nms=[i['nm_id'] for i in g['items']],bid_type='manual',payment_type='cpc',placement_types=['search']))
    cid=result if type(result)is int else result.get('advertId') if isinstance(result,dict) else None
    if type(cid)is not int:raise RuntimeError('Missing new campaign ID; no repeat')
    state['campaign_id']=cid;state['new_draft']=True;save()
    before=w.campaigns([cid])[str(cid)]
    if before['status']!=4 or before['currency']!='CNY' or before['settings']['name']!=g['name'] or before['settings']['placements']!=dict(search=True,recommendations=False) or set(members(before))!={str(i['nm_id']) for i in g['items']}:raise RuntimeError('Draft readback mismatch')
    e['steps']['bags:create']['status']='verified'
   else:before=w.campaigns([cid])[str(cid)]
   state['before']=before;old=members(before);save()
   missing=[i['nm_id'] for i in g['items'] if str(i['nm_id']) not in old]
   if missing:
    write(str(cid)+':add','/adv/v0/auction/nms','PATCH',dict(nms=[dict(advert_id=cid,nms=dict(add=missing,delete=[]))]))
    mid=w.campaigns([cid])[str(cid)]
    if set(members(mid))!=set(old)|{str(n) for n in missing} or stable(mid)!=stable(before) or any(members(mid)[k]!=v for k,v in old.items()):raise RuntimeError('Membership readback mismatch')
    e['steps'][str(cid)+':add']['status']='verified';state['after_membership']=mid;save()
   else:mid=before
   minimum=w.minimums(cid,[i['nm_id'] for i in g['items']],'search')
   state['minimums']={str(k):v for k,v in minimum.items()};save()
   write(str(cid)+':bids','/api/advert/v1/bids','PATCH',dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=i['nm_id'],bid_kopecks=minimum[i['nm_id']],placement='search') for i in g['items']])]))
   after=w.campaigns([cid])[str(cid)];expected=copy.deepcopy(members(mid))
   for i in g['items']:expected[str(i['nm_id'])]['bids']['search']=minimum[i['nm_id']]
   if stable(after)!=stable(before) or members(after)!=expected:raise RuntimeError('Minimum bid readback mismatch')
   state.update(status='verified',after=after,verified_at=iso());e['steps'][str(cid)+':bids']['status']='verified';save()
   key=ROOT+str(cid)+':execution'
   c.put(key,dict(status='verified',before=before if not state.get('new_draft') else None,after=after,items=[dict(kind='ad_create_search_draft' if state.get('new_draft') else 'ad_add_sku',nm_id=i['nm_id'],article=i['article'],placement='search',target_minor=minimum[i['nm_id']]) for i in g['items']],verified_at=state['verified_at'],parent=ROOT+'execution'))
   reg=c.get('china_agent:verified_campaign_state:v1') or {};reg[str(cid)]=key;c.put('china_agent:verified_campaign_state:v1',reg)
  budgets=w.req('/api/advert/v2/budget','POST',dict(advertIds=[g['campaign_id'] for g in e['groups']]))
  e.update(status='verified',budgets_after=budgets,config=w.req('/api/advert/v1/config'),completed_at=iso());save()
 except Exception as ex:
  e.update(status='uncertain' if any(v['status']in ['submitting','accepted','uncertain'] for v in e['steps'].values()) else 'blocked',reason=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__,completed_at=iso());save()
 finally:
  verified=[g for g in e['groups'] if g.get('status')=='verified']
  if verified:c.put('china_agent:search_trials:v1',dict(status='active',owner_authorized=True,started_at=e['baseline_observed_at'],baseline_fullstats=e['baseline_fullstats'],execution_key=ROOT+'execution',items=[dict(campaign_id=g['campaign_id'],nm_id=i['nm_id'],article=i['article'],bid_minor=g['minimums'][str(i['nm_id'])],added_at=g['verified_at'],pending_activation=g.get('new_draft',False),group='high_conversion_bags' if g.get('new_draft') else 'umbrellas') for g in verified for i in g['items']],report_slots=['codex_manual_morning'],hourly_autonomy=False,automatic_writes=False))
  print('Owner search cohort result: '+e['status'])
if __name__=='__main__':run()
