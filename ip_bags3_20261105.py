"""One owner-authorized subset. Private frozen scope; public runner; no Telegram."""
import copy,datetime,hashlib,json,math,os,time,urllib.error
from ip_apply_nine_20261103 import SixTransport,projection,stamp,HOST,minimum_map
PLAN='ip_agent:bags3:2026-11-05:v1'
EXEC=PLAN+':execution'
FROZEN_SCOPE_SHA='2cda75f1b9800a4fa57cb595b0e93c765e469bd1b0f0a68ffd0800eb340d3a3f'

def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def active_ids(t,targets):
 path='/adv/v1/promotion/count'
 for attempt in range(3):
  key=t.pause(path)
  try:
   raw=t.raw(HOST+path,{'Authorization':t.token,'Content-Type':'application/json'})
   ids=set(targets)
   for group in raw.get('adverts',[]):
    if group.get('status')==9:ids.update(x['advertId'] for x in group.get('advert_list',[]))
   if not ids or len(ids)>50:raise ValueError('Unexpected campaign index size; no mutation')
   return sorted(ids),raw
  except urllib.error.HTTPError as e:
   retry=e.headers.get('Retry-After') or e.headers.get('X-Ratelimit-Retry') or e.headers.get('X-Ratelimit-Reset')
   if e.code==429 and retry and attempt<2:
    seconds=float(retry)
    if not math.isfinite(seconds) or seconds<0:raise ValueError('Invalid retry interval')
    prior=t.get(key) or {};t.save(key,{'until':max(float(prior.get('until',0)),time.time()+seconds+1),'basis':'provider_header'});continue
   raise RuntimeError('Index read HTTP'+str(e.code)) from None
def prepare(scope,before,minimum):
 expected=copy.deepcopy(before);pending=[];items=[]
 for a in scope:
  cid=str(a['campaign']);c=before[cid];nm=a['nm'];members={n['nm_id']:n for n in c['nm_settings']}
  if c.get('status')!=9 or c.get('currency')!='RUB' or c.get('bid_type')!='manual' or c['settings']!={'payment_type':'cpc','placements':{'search':True,'recommendations':False}}:
   # Other settings must be preserved, but harmless additional fields are permitted.
   if c.get('status')!=9 or c.get('currency')!='RUB' or c.get('bid_type')!='manual' or c['settings'].get('payment_type')!='cpc' or c['settings'].get('placements')!={'search':True,'recommendations':False}:raise ValueError('Target campaign not active manual search CPC RUB')
  target=a['target_bid_minor']
  if target<minimum or a['subject']!=50 or a['stock_fbo']+a['stock_fbs']<=0:raise ValueError('Minimum/category/stock constraint')
  item=dict(sku=a['sku'],nm=nm,campaign=a['campaign'],kind=a['kind'])
  if a['kind']=='raise_bid':
   if nm not in members or members[nm].get('subject',{}).get('id')!=50:raise ValueError('Approved existing bag not present')
   old=members[nm]['bids_kopecks']['search']
   if old==target:items.append(dict(item,status='already_target'));continue
   if old!=a['stored_bid_minor'] or not old<target<=math.floor(old*1.05):raise ValueError('Current bid differs or raise exceeds5percent')
   for n in expected[cid]['nm_settings']:
    if n['nm_id']==nm:n['bids_kopecks']['search']=target
  elif a['kind']=='add':
   overlaps=[k for k,v in before.items() if v.get('status')==9 and any(n['nm_id']==nm for n in v['nm_settings'])]
   if overlaps:
    if overlaps==[cid] and members[nm]['bids_kopecks']['search']==target:items.append(dict(item,status='already_target'));continue
    raise ValueError('Already advertised; no overlap or overwrite')
   if not c.get('restrictions',{}).get('can_change_nms') or len(expected[cid]['nm_settings'])>=50:raise ValueError('Addition/capacity unavailable')
   if {n['subject']['id'] for n in c['nm_settings']}!={50}:raise ValueError('Bag category mismatch')
   expected[cid]['nm_settings'].append(dict(nm_id=nm,subject=copy.deepcopy(c['nm_settings'][0]['subject']),bids_kopecks={'search':target,'recommendations':0}))
  else:raise PermissionError('Operation outside approved subset')
  pending.append(a);items.append(dict(item,status='planned'))
 return expected,pending,items

def unchanged(before,current,scope,allow_added=False,allow_bids=False):
 if set(before)!=set(current):return False
 baseline=copy.deepcopy(before);observed=copy.deepcopy(current)
 for a in scope:
  cid=str(a['campaign']);nm=a['nm'];old={n['nm_id']:n for n in baseline[cid]['nm_settings']};new={n['nm_id']:n for n in observed[cid]['nm_settings']}
  if a['kind']=='add' and nm not in old and nm in new:
   if not allow_added or new[nm].get('subject',{}).get('id')!=50:return False
   if allow_bids and new[nm]['bids_kopecks'].get('search')!=a['target_bid_minor']:return False
   if new[nm]['bids_kopecks'].get('recommendations',0)!=0:return False
   observed[cid]['nm_settings']=[n for n in observed[cid]['nm_settings'] if n['nm_id']!=nm]
  elif a['kind']=='raise_bid' and allow_bids and nm in new and nm in old:
   if new[nm]['bids_kopecks']['search'] not in (old[nm]['bids_kopecks']['search'],a['target_bid_minor']):return False
   observed[cid]['nm_settings'][next(i for i,n in enumerate(observed[cid]['nm_settings']) if n['nm_id']==nm)]['bids_kopecks']['search']=old[nm]['bids_kopecks']['search']
 return all(projection(baseline[k])==projection(observed[k]) for k in baseline)

def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise PermissionError('Public main only')
 t=SixTransport();p=t.get(PLAN)
 if not p or p.get('status')!='owner_authorized' or len(p['scope'])!=3 or digest(p['scope'])!=FROZEN_SCOPE_SHA:raise PermissionError('Frozen approval missing')
 state=dict(status='preflight',run_id=os.environ['GITHUB_RUN_ID'],started_at=stamp(),approval_key=PLAN,steps={},items=[],wb_write_attempts=0,wb_accepted_requests=0,telegram_sends=0)
 if not t.create(EXEC,state):print('Prior claim retained; no replay');return
 def save():t.save(EXEC,state)
 def progress(path,until):state.update(status='waiting_provider_cooldown',wait_endpoint=path,next_allowed_at=datetime.datetime.fromtimestamp(until,datetime.timezone.utc).isoformat());save()
 t.progress=progress
 def guard():
  if datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).date().isoformat()!='2026-11-05' or t.get(PLAN)!=p:raise PermissionError('Dated approval changed')
  for key in ('ip_agent:expanded98:finish:2026-11-02:v1','ip_agent:expanded98:finish:2026-11-02:v2'):
   old=t.get(key)
   if old and old.get('status')!='manual_handoff':raise PermissionError('Old writer authorization reactivated')
  if (t.get('ip_agent:traffic_adjustments:2026-11-03:nine:v1:execution') or {}).get('status')!='verified_all15':raise PermissionError('Prior15 not verified')
 def write(name,path,body,refresh):
  for attempt in range(4):
   t.pause(path);guard();refresh()
   step=dict(status='submitting',path=path,body=body,submitted_at=stamp());state['steps'][name+':'+str(attempt)]=step;state['wb_write_attempts']+=1;save()
   try:
    response=t.raw(HOST+path,{'Authorization':t.token,'Content-Type':'application/json','User-Agent':'python-requests/2.32.5'},'PATCH',body)
    step.update(status='accepted',response=response,accepted_at=stamp());state['wb_accepted_requests']+=1;save();return response
   except urllib.error.HTTPError as e:
    retry=e.headers.get('Retry-After') or e.headers.get('X-Ratelimit-Retry') or e.headers.get('X-Ratelimit-Reset')
    detail=e.read(4096).decode('utf-8',errors='replace').replace(t.token,'[REDACTED]');step.update(status='rejected',http_status=e.code,detail_private=detail);save()
    if e.code==429 and retry and attempt<3:
     seconds=float(retry)
     if not math.isfinite(seconds) or seconds<0:raise ValueError('Invalid retry interval')
     key='wb-pause:'+hashlib.sha256((t.token+'advert-api.wildberries.ru'+path).encode()).hexdigest();prior=t.get(key) or {}
     t.save(key,{'until':max(float(prior.get('until',0)),time.time()+seconds+1),'basis':'provider_429_definite_rejection'});continue
    raise RuntimeError('WB rejected HTTP'+str(e.code)) from None
   except Exception:
    step.update(status='uncertain',error='Unknown result; no replay');save();raise
 try:
  t.identity();guard()
  # Current index prevents adding a SKU already advertised in a newly created campaign.
  ids,index=active_ids(t,{a['campaign'] for a in p['scope']});state.update(campaign_index=index,campaign_index_at=stamp(),campaign_ids=ids);save()
  before=t.configs(ids);observed=time.time();state.update(before=before,configuration_observed_at=stamp());save()
  # Reuse category50/CPC/search/RUB minimum proven by Nov4 receipt and today's added209 readback.
  donor=t.get('ip_agent:png17:2026-11-05:v1:execution') or {}
  old=t.get('ip_agent:bags_growth:2026-11-04:six:v1:execution') or {}
  receipt=old.get('category_minimum_receipt') or {}
  if receipt.get('subject')!=50 or receipt.get('payment_type')!='cpc' or receipt.get('placement')!='search' or minimum_map(receipt['response'],[419974169],'search')[419974169]!=295:raise PermissionError('Category295 proof missing')
  n=next(n for n in donor['after']['39483230']['nm_settings'] if n['nm_id']==347406432)
  if n['bids_kopecks']['search']!=295 or not donor.get('readback_at','').startswith('2026-11-05'):raise PermissionError('Today category readback missing')
  diagnostic=t.get(p['stock_source']) or {}
  observations=[o for o in diagnostic.get('observations',[]) if o.get('tool')=='lk_wb_products' and o.get('status')=='received' and o.get('observed_at','').startswith('2026-11-05')]
  if len(observations)!=1:raise PermissionError('Exact saved stocks missing')
  rows=observations[0]['data']['data']['data']
  for a in p['scope']:
   matches=[r for r in rows if r.get('nm_id')==a['nm']]
   if len(matches)!=1 or matches[0]['sa_name']!=a['sku'] or float(matches[0]['stock_api_stock_count'])!=a['stock_fbo'] or float(matches[0]['fbs_stock'])!=a['stock_fbs']:raise PermissionError('Exact variant stock proof missing')
  minimum=295;state['category_minimum_receipt']=receipt;save()
  expected,selected,items=prepare(p['scope'],before,minimum);state.update(expected=expected,items=items);save()
  # Refresh after minimum lookup/cooldown, without replacing the authorized baseline.
  stage=copy.deepcopy(before)
  def refresh():
   nonlocal observed
   if time.time()-observed>180:
    current=t.configs(ids);observed=time.time()
    if any(projection(current[k])!=projection(stage[k]) for k in stage):raise ValueError('WB changed since preflight; no overwrite')
    state['pre_write_readback_at']=stamp();save()
  adds=[a for a in selected if a['kind']=='add']
  if adds:
   cid=adds[0]['campaign']
   if any(a['campaign']!=cid for a in adds):raise PermissionError('One approved addition destination only')
   response=write('membership','/adv/v0/auction/nms',{'nms':[{'advert_id':cid,'nms':{'add':sorted(a['nm'] for a in adds),'delete':[]}}]},refresh)
   state['membership_ack']=response;save()
   stage=t.configs(ids);observed=time.time();state.update(membership_readback=stage,membership_readback_at=stamp());save()
   if not unchanged(before,stage,p['scope'],allow_added=True) or any(a['nm'] not in {n['nm_id'] for n in stage[str(a['campaign'])]['nm_settings']} for a in adds):raise ValueError('Addition readback incomplete/unrelated change; no further writes')
  bids={}
  for a in selected:
   n=next(n for n in stage[str(a['campaign'])]['nm_settings'] if n['nm_id']==a['nm'])
   if n['bids_kopecks'].get('search')!=a['target_bid_minor']:bids.setdefault(a['campaign'],[]).append({'nm_id':a['nm'],'placement':'search','bid_kopecks':a['target_bid_minor']})
  if bids:write('bids','/api/advert/v1/bids',{'bids':[{'advert_id':cid,'nm_bids':nms} for cid,nms in sorted(bids.items())]},refresh)
  state['status']='verifying';save();after=t.configs(ids) if bids or not adds else stage;state.update(after=after,readback_at=stamp())
  preserved=unchanged(before,after,p['scope'],allow_added=True,allow_bids=True);state['unrelated_members_settings_preserved']=preserved
  for item in state['items']:
   a=next(a for a in p['scope'] if a['nm']==item['nm']);match=[n for n in after[str(a['campaign'])]['nm_settings'] if n['nm_id']==a['nm']]
   item['status']='verified' if preserved and len(match)==1 and match[0]['bids_kopecks']['search']==a['target_bid_minor'] else 'not_verified'
  state['status']='verified' if all(i['status']=='verified' for i in state['items']) else 'attention_readback';save()
 except Exception as e:
  state.update(status='attention',error=str(e) if isinstance(e,(RuntimeError,ValueError,PermissionError)) else type(e).__name__);save()
  if state['wb_write_attempts']:
   try:state.update(recovery_readback=t.configs(state['campaign_ids']),recovery_readback_at=stamp())
   except Exception as re:state['recovery_error']=type(re).__name__
 finally:
  if state.get('error'):state['status']='attention'
  state.update(finished_at=stamp(),decoded_response_bytes=getattr(t,'decoded_bytes',0));save()
 print(json.dumps({k:state.get(k) for k in ('status','wb_write_attempts','wb_accepted_requests','telegram_sends')}))
if __name__=='__main__':run()

