"""Dated, owner-approved IP changes only. No dispatcher, schedules or Telegram."""
import base64,copy,datetime,gzip,hashlib,json,math,os,time,urllib.request,urllib.error,urllib.parse
ROOT='ip_agent:expanded98:2026-11-02:v1'
PARENT=ROOT+':execution'
EXEC=PARENT+':optimized2'
HOST='https://advert-api.wildberries.ru'
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def projection(c):
 return {k:copy.deepcopy(c.get(k)) for k in ('id','status','bid_type','currency','settings','restrictions')}|{'nm_settings':sorted(copy.deepcopy(c['nm_settings']),key=lambda n:n['nm_id'])}
def minimum_map(raw,ids,placement):
 out={}
 for r in raw.get('bids',[]):
  if r.get('nm_id') not in ids:continue
  found=[v for v in r.get('bids',[]) if v.get('type')==placement and v.get('currency')=='RUB' and type(v.get('value')) is int and v['value']>0]
  if len(found)!=1:raise ValueError('Minimum not proven for nm')
  out[r['nm_id']]=found[0]['value']
 if set(out)!=set(ids):raise ValueError('Minimum coverage incomplete')
 return out
def minimum_group(c,nm):
 rows=[n for n in c['nm_settings'] if n['nm_id']==nm]
 if len(rows)!=1 or type(rows[0].get('subject',{}).get('id')) is not int:raise ValueError('Exact subject missing')
 payment=c['settings']['payment_type'];placement='recommendation' if payment=='cpm' else 'search'
 return (rows[0]['subject']['id'],payment,placement,c['currency'],c['bid_type'])
def representatives(c,wanted,known):
 missing={}
 for nm in wanted:
  group=minimum_group(c,nm)
  if group not in known:missing.setdefault(group,nm)
 return list(missing.values())
def remember_minimums(c,values,known):
 pending=dict(known)
 for nm,value in values.items():
  group=minimum_group(c,nm)
  if group in pending and pending[group]!=value:raise ValueError('Category minimum conflict; fresh category check required')
  pending[group]=value
 return pending
def allowed_subset(before,after,selected):
 observed=copy.deepcopy(before)
 for a in selected:
  cid=str(a['campaign']);nm=a['nm'];members={n['nm_id']:n for n in after[cid]['nm_settings']}
  if a['kind']=='remove' and nm not in members:
   observed[cid]['nm_settings']=[n for n in observed[cid]['nm_settings'] if n['nm_id']!=nm]
  elif a['kind'] in ('raise_bid','lower_bid') and nm in members and members[nm].get('bids_kopecks',{}).get(a['placement'])==a['target_bid_minor']:
   for n in observed[cid]['nm_settings']:
    if n['nm_id']==nm:n['bids_kopecks'][a['placement']]=a['target_bid_minor']
 return {cid:projection(observed[cid])==projection(after[cid]) for cid in before}
def select(scope,configs,minimums):
 expected=copy.deepcopy(configs);selected=[];results=[]
 for a in scope:
  if a['kind'] not in ('remove','raise_bid','lower_bid'):
   results.append(dict(nm=a['nm'],sku=a['sku'],kind=a['kind'],status='preparation_required',reason=a.get('readiness')));continue
  cid=str(a['campaign']);before=configs.get(cid);result=dict(nm=a['nm'],sku=a['sku'],kind=a['kind'],campaign=a['campaign'])
  def block(reason):results.append(dict(result,status='blocked_preflight',reason=reason))
  if not before or before.get('currency')!='RUB' or before.get('bid_type')!='manual' or before.get('status')!=9:block('Campaign not an active manual RUB campaign');continue
  members={n['nm_id']:n for n in before['nm_settings']};nm=a['nm']
  if a['kind']=='remove':
   if before['settings'].get('payment_type')!='cpm' or not before.get('restrictions',{}).get('can_change_nms'):block('Expected mutable CPM campaign not confirmed');continue
   if nm not in members:results.append(dict(result,status='already_absent'));continue
   expected[cid]['nm_settings']=[n for n in expected[cid]['nm_settings'] if n['nm_id']!=nm]
  else:
   placement='recommendations' if before['settings'].get('payment_type')=='cpm' else 'search'
   if nm not in members:block('Membership missing; no automatic addition');continue
   old=members[nm].get('bids_kopecks',{}).get(placement);target=a.get('target_bid_minor')
   if type(target) is not int or target<=0:block('Exact target not frozen');continue
   if old==target:results.append(dict(result,status='already_target'));continue
   if old!=a.get('stored_bid_minor'):block('Current bid differs from approved source');continue
   minimum=minimums.get((cid,nm))
   if type(minimum) is not int or target<minimum:block('Target below minimum or current minimum unknown');continue
   if a['kind']=='raise_bid' and not(old<target<=math.floor(old*1.05)):block('Raise exceeds approved5percent');continue
   if a['kind']=='lower_bid' and not(0<target<old):block('Invalid reduction');continue
   if a['kind']=='raise_bid' and a['evidence'].get('msk_available_2nov')==0:block('Verified zero MSK, current FBO confirmation required');continue
   for n in expected[cid]['nm_settings']:
    if n['nm_id']==nm:n['bids_kopecks'][placement]=target
   a=copy.deepcopy(a);a['placement']=placement
  selected.append(a);results.append(dict(result,status='planned'))
 return selected,expected,results
class Transport:
 def __init__(self):
  self.sb=os.environ['SUPABASE_URL'].rstrip('/');key=os.environ['SUPABASE_SECRET_KEY']
  self.sh={'apikey':key,'Content-Type':'application/json'}
  if not key.startswith('sb_secret_'):self.sh['Authorization']='Bearer '+key
  self.token=os.environ['WB_TOKEN_2'];self.deadline=time.time()+4*3600
  class NoRedirect(urllib.request.HTTPRedirectHandler):
   def redirect_request(self,*a,**k):raise RuntimeError('Redirect blocked')
  self.opener=urllib.request.build_opener(NoRedirect)
 def identity(self):
  try:claims=json.loads(base64.urlsafe_b64decode(self.token.split('.')[1]+'==='))
  except Exception:raise PermissionError('WB token format invalid') from None
  if claims.get('exp',0)<=time.time() or claims.get('t') is not False or int(claims.get('s',0))&(1<<30):raise PermissionError('WB token expired, test or read only')
  q=urllib.parse.urlencode({'cabinet':'eq.token_2','source':'eq.seller_identity','status':'eq.complete','select':'payload','limit':100})
  rows=self.raw(self.sb+'/rest/v1/analytics_snapshots?'+q,self.sh)
  if {x['payload'].get('sid') for x in rows}!={claims.get('sid')} or not claims.get('sid'):raise PermissionError('IP seller identity mismatch')
 def raw(self,url,headers,method='GET',body=None):
  req=urllib.request.Request(url,headers=headers,method=method,data=None if body is None else json.dumps(body).encode())
  with self.opener.open(req,timeout=55) as r:
   b=r.read()
   if r.headers.get('Content-Encoding')=='gzip':b=gzip.decompress(b)
   if url.startswith(HOST):self.last_headers={k.lower():v for k,v in r.headers.items()}
   return json.loads(b) if b else {}
 def db(self,method,params=None,body=None,prefer=None):
  h=dict(self.sh)
  if prefer:h['Prefer']=prefer
  return self.raw(self.sb+'/rest/v1/telegram_api_cache?'+urllib.parse.urlencode(params or {}),h,method,body)
 def get(self,key):
  r=self.db('GET',{'cache_key':'eq.'+key,'select':'payload'})
  return r[0]['payload'] if r else None
 def create(self,key,value):
  r=self.db('POST',{'on_conflict':'cache_key'},{'cache_key':key,'payload':value,'updated_at':stamp(),'expires_at':'2036-11-02T00:00:00Z'},'resolution=ignore-duplicates,return=representation')
  return len(r)==1
 def save(self,key,value):
  self.db('POST',{'on_conflict':'cache_key'},{'cache_key':key,'payload':value,'updated_at':stamp(),'expires_at':'2036-11-02T00:00:00Z'},'resolution=merge-duplicates')
 def pause(self,path):
  key='wb-pause:'+hashlib.sha256((self.token+'advert-api.wildberries.ru'+path).encode()).hexdigest()
  while True:
   r=self.get(key) or {};remaining=max(0,float(r.get('until',0))-time.time()+1)
   if remaining<=1:return key
   if time.time()+remaining>self.deadline:raise RuntimeError('Provider cooldown exceeds execution window')
   if hasattr(self,'progress'):self.progress(path,float(r['until']))
   time.sleep(remaining)
 def wb(self,path,method='GET',body=None,write=False):
  bare=path.split('?')[0];allowed={'/api/advert/v1/bids','/adv/v0/auction/nms'} if write else {'/api/advert/v2/adverts','/api/advert/v1/bids/min'}
  if bare not in allowed or (write and method!='PATCH'):raise ValueError('Unapproved endpoint')
  for attempt in range(3 if not write else 1):
   key=self.pause(bare)
   try:
    response=self.raw(HOST+path,{'Authorization':self.token,'Content-Type':'application/json','User-Agent':'python-requests/2.32.5'},method,body)
    headers=getattr(self,'last_headers',{});gap=getattr(self,'cadence',{}).get(bare,0)
    if headers.get('x-ratelimit-remaining')=='0':
     try:gap=max(gap,float(headers.get('x-ratelimit-reset',0)))
     except (TypeError,ValueError):pass
     if gap>0:
      prior=self.get(key) or {};self.save(key,{'until':max(float(prior.get('until',0)),time.time()+gap),'basis':'provider_reset_or_retained_observed_interval'})
    return response
   except urllib.error.HTTPError as e:
    retry=e.headers.get('Retry-After') or e.headers.get('X-Ratelimit-Retry') or e.headers.get('X-Ratelimit-Reset')
    if e.code==429 and retry:
     try:seconds=float(retry)
     except (ValueError,TypeError):seconds=None
     if seconds is not None and math.isfinite(seconds) and seconds>=0:
      old=self.get(key) or {};until=max(float(old.get('until',0)),time.time()+seconds+1)
      self.save(key,{'until':until,'basis':'provider_header'})
      if not write and attempt<2:continue
    raise RuntimeError('WB HTTP '+str(e.code)+'; retry_seconds '+str(retry)) from None
  raise RuntimeError('Read retry exhausted')
 def configs(self,ids):
  j=self.wb('/api/advert/v2/adverts?ids='+','.join(map(str,ids)))
  result={str(c['id']):c for c in j.get('adverts',[])}
  if set(result)!=set(map(str,ids)):raise ValueError('Incomplete current configuration')
  return result
def derive_cadence(parent,diagnosis):
 def dt(s):return datetime.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
 observations=sorted(dt(x['observed_at']) for x in parent.get('minimum_receipts',[]))
 result={}
 if len(observations)>1:result['/api/advert/v1/bids/min']=math.ceil(max(b-a for a,b in zip(observations,observations[1:])))+1
 if diagnosis and diagnosis.get('finished_at') and parent.get('configuration_observed_at'):
  gap=dt(parent['configuration_observed_at'])-dt(diagnosis['finished_at'])
  if gap>0:result['/api/advert/v2/adverts']=math.ceil(gap)+1
 return result
def seeded_minima(parent,before):
 known={}
 for receipt in parent.get('minimum_receipts',[]):
  cid=str(receipt['campaign']);c=before[cid];placement='recommendation' if c['settings']['payment_type']=='cpm' else 'search'
  ids=[r['nm_id'] for r in receipt['response'].get('bids',[])]
  known=remember_minimums(c,minimum_map(receipt['response'],ids,placement),known)
 return known
PLAN='ip_agent:expanded98:finish:2026-11-02:v2'
EXEC=PLAN+':execution'

class FinishTransport(Transport):
 def wb(self,path,method='GET',body=None,write=False):
  bare=path.split('?')[0]
  reads={('/adv/v2/supplier/nms','POST'),('/api/advert/v2/adverts','GET'),('/adv/v1/promotion/count','GET'),('/api/advert/v1/bids/min','POST'),('/api/advert/v2/budget','POST')}
  writes={('/api/advert/v1/bids','PATCH'),('/adv/v0/auction/nms','PATCH'),('/adv/v2/seacat/save-ad','POST'),('/adv/v1/budget/deposit','POST'),('/adv/v0/start','GET')}
  if (bare,method) not in (writes if write else reads):raise ValueError('Endpoint outside owner finish scope')
  for attempt in range(4):
   key=self.pause(bare)
   if write and hasattr(self,'pre_write'):self.pre_write(bare,body)
   try:
    reply=self.raw(HOST+path,{'Authorization':self.token,'Content-Type':'application/json','User-Agent':'python-requests/2.32.5'},method,body)
    gap=self.cadence.get(bare,0)
    if gap:
     old=self.get(key) or {};self.save(key,{'until':max(float(old.get('until',0)),time.time()+gap),'basis':'documented_basic_or_observed_interval'})
    return reply
   except urllib.error.HTTPError as e:
    retry=e.headers.get('Retry-After') or e.headers.get('X-Ratelimit-Retry') or e.headers.get('X-Ratelimit-Reset')
    if e.code==429 and retry:
     seconds=float(retry)
     if not math.isfinite(seconds) or seconds<0:raise ValueError('Invalid retry header')
     old=self.get(key) or {};self.save(key,{'until':max(float(old.get('until',0)),time.time()+seconds+1),'basis':'provider_429_rejected_request'})
     if attempt<3:continue
    detail=e.read(4096).decode('utf-8',errors='replace').replace(self.token,'[REDACTED]')
    self.save(EXEC+':last_http_failure',{'status':e.code,'path':bare,'detail_private':detail,'observed_at':stamp()})
    raise RuntimeError('WB HTTP '+str(e.code)+'; retry '+str(retry)) from None
  raise RuntimeError('Request attempts exhausted')

def validate_plan(p,root):
 if not p or p.get('status')!='owner_authorized' or p.get('root')!=ROOT or not root or root.get('status')!='authorized_pending_preflight':raise PermissionError('Approval missing')
 if {(x['nm'],x['campaign'],x['target_bid_minor']) for x in p['existing']}!={(1123642993,39634287,295),(997991777,40192945,175)}:raise PermissionError('Existing scope changed')
 source={a['nm'] for a in root['scope'] if a['kind']=='new_campaign'}
 ids=[a['nm'] for c in p['new_campaigns'] for a in c['items']]
 if len(ids)!=9 or len(set(ids))!=9 or set(ids)!=source or len(p['new_campaigns'])!=2:raise PermissionError('New campaign scope differs from frozen98')
 if any(c['budget_rub']!=1000 for c in p['new_campaigns']) or p.get('daily_caps') is not False or p.get('auto_topup') is not False:raise PermissionError('Budget authorization mismatch')
 if p.get('placement')!='search' or p.get('payment_type')!='cpc' or p.get('bid_type')!='manual':raise PermissionError('Campaign type changed')
 return True

def check_new(c,spec,minimum,active=False):
 if c.get('status')!=(9 if active else 4) or c.get('currency')!='RUB' or c.get('bid_type')!='manual':raise ValueError('New campaign status/currency/type mismatch')
 if c['settings'].get('name')!=spec['name'] or c['settings'].get('payment_type')!='cpc' or c['settings'].get('placements')!={'search':True,'recommendations':False}:raise ValueError('New campaign settings differ')
 members=c['nm_settings']
 if {n['nm_id'] for n in members}!={a['nm'] for a in spec['items']}:raise ValueError('New membership differs')
 if any(n['subject']['id']!=spec['subject'] or n['bids_kopecks'].get('search')!=minimum or n['bids_kopecks'].get('recommendations',0)!=0 for n in members):raise ValueError('New subject or automatic minimum differs')

def fresh_fbo(t,scope,state,save):
 token=os.environ.get('WB_FINANCE_TOKEN_2') or t.token
 claim=lambda v:json.loads(base64.urlsafe_b64decode(v.split('.')[1]+'==='))
 if claim(token).get('sid')!=claim(t.token).get('sid') or claim(token).get('exp',0)<=time.time():raise PermissionError('FBO reader identity/expiry')
 def read(path,params=None):
  host='seller-analytics-api.wildberries.ru';group=path
  if '/warehouse_remains/tasks/' in path:group='/api/v1/warehouse_remains/tasks/{task}/'+path.rsplit('/',1)[-1]
  key='wb-pause:'+hashlib.sha256((token+host+group).encode()).hexdigest()
  prior=t.get(key) or {};until=float(prior.get('until',0))
  if until>time.time():
   if until>t.deadline:raise RuntimeError('FBO cooldown exceeds job window')
   t.progress(group,until);time.sleep(max(0,until-time.time()+1))
  try:return t.raw('https://'+host+path+('?' +urllib.parse.urlencode(params) if params else ''),{'Authorization':token,'Content-Type':'application/json','Accept-Encoding':'gzip'})
  except urllib.error.HTTPError as e:
   retry=e.headers.get('Retry-After') or e.headers.get('X-Ratelimit-Retry')
   if e.code==429 and retry:t.save(key,{'until':time.time()+float(retry)+1,'basis':'provider_header'})
   raise RuntimeError('FBO source HTTP '+str(e.code)) from None
 from uuid import UUID
 created=read('/api/v1/warehouse_remains',{'locale':'ru','groupBySa':'true','groupByNm':'true','groupByBarcode':'false','groupBySize':'false','filterPics':0,'filterVolume':0})
 task=str(UUID(created['data']['taskId']));time.sleep(20)
 if read('/api/v1/warehouse_remains/tasks/'+task+'/status').get('data',{}).get('status')!='done':raise RuntimeError('FBO report pending; no blind polling')
 rows=read('/api/v1/warehouse_remains/tasks/'+task+'/download')
 if not isinstance(rows,list):raise ValueError('FBO full report invalid')
 qty={};seen=set()
 for r in rows:
  nm=r.get('nmId')
  if type(nm)is not int or nm in seen or not isinstance(r.get('warehouses'),list):raise ValueError('FBO grouped scope ambiguous')
  seen.add(nm);values={}
  for w in r['warehouses']:
   name=w.get('warehouseName');v=w.get('quantity')
   if not isinstance(name,str) or name in values or type(v) not in (int,float) or not math.isfinite(v) or v<0 or int(v)!=v:raise ValueError('FBO warehouse invalid')
   values[name]=int(v)
  if nm in scope:qty[nm]=values.get('Всего находится на складах',sum(v for n,v in values.items() if not n.startswith('В пути') and not n.startswith('Всего') and n!='Маркетплейс'))
 result={'observed_at':stamp(),'source':'existing_grouped_warehouse_remains','quantity':{str(nm):qty.get(nm,0) for nm in scope},'no_fbs_or_msk':True}
 state.setdefault('fbo_receipts',[]).append(result);save()
 if any(qty.get(nm,0)<=0 for nm in scope):raise ValueError('Selected item has no positive current FBO; no launch/addition')
 return result

def run_finish():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise PermissionError('Public main only')
 if datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).date().isoformat()!='2026-11-02':raise PermissionError('Dated authorization only')
 t=FinishTransport();p=t.get(PLAN);root=t.get(ROOT);validate_plan(p,root)
 state={'status':'starting','started_at':stamp(),'run_id':os.environ['GITHUB_RUN_ID'],'approval_key':PLAN,'steps':{},'campaigns':[],'telegram_sends':0,'wb_write_attempts':0}
 if not t.create(EXEC,state):print('Existing execution retained; no replay');return
 active=t.get('ip_agent:expanded98:active_execution:v1') or {}
 active.update(status='running_independent_campaign_continuation',active_execution=EXEC,latest_execution=EXEC,run_id=state['run_id'],queued_execution=None)
 t.save('ip_agent:expanded98:active_execution:v1',active)
 def save():t.save(EXEC,state)
 def progress(path,until):state.update(status='waiting_provider_cooldown',wait_endpoint=path,next_allowed_at=datetime.datetime.fromtimestamp(until,datetime.timezone.utc).isoformat());save()
 t.progress=progress;t.cadence={'/api/advert/v2/adverts':3606,'/api/advert/v1/bids/min':733,'/adv/v1/promotion/count':901,'/adv/v2/seacat/save-ad':733,'/adv/v1/budget/deposit':733,'/api/advert/v2/budget':901,'/adv/v0/start':733,'/adv/v2/supplier/nms':1801}
 def write(name,path,method,body=None):
  if t.get(PLAN)!=p or t.get(ROOT)!=root:raise PermissionError('Authorization changed')
  if name in state['steps']:raise RuntimeError('Existing write receipt; no replay')
  state['steps'][name]={'status':'submitting','path':path,'method':method,'body':body,'at':stamp()};state['wb_write_attempts']+=1;save()
  try:r=t.wb(path,method,body,write=True)
  except Exception as e:state['steps'][name].update(status='not_confirmed',error=str(e) if isinstance(e,(ValueError,RuntimeError)) else type(e).__name__);save();raise
  state['steps'][name].update(status='accepted',response=r,accepted_at=stamp());save();return r
 def budgets(ids):
  j=t.wb('/api/advert/v2/budget','POST',{'advertIds':ids});rows=j.get('adverts',[])
  if len(rows)!=len(ids) or {r.get('advertId') for r in rows}!=set(ids) or any(r.get('currency')!='RUB' or type(r.get('total')) not in (int,float) for r in rows):raise ValueError('Budget coverage/currency missing')
  return {r['advertId']:r['total'] for r in rows}
 try:
  t.identity();parent=t.get('ip_agent:expanded98:finish:2026-11-02:v1:execution') or {}
  if not parent.get('finished_at') or parent.get('campaigns') or not parent.get('recovery_readback'):raise ValueError('Predecessor not settled or has campaign creation receipts; no duplicate continuation')
  index=t.wb('/adv/v1/promotion/count');ids=set();drafts=set()
  for g in index.get('adverts',[]):
   if g.get('status') in (4,9):
    dest=drafts if g['status']==4 else ids
    dest.update(x['advertId'] for x in g.get('advert_list',[]))
  if len(ids|drafts|{39634287,40192945})>50:raise ValueError('Configuration scope over50; no automatic expansion')
  wanted=ids|drafts|{39634287,40192945};retained=parent['recovery_readback'];age=time.time()-datetime.datetime.fromisoformat(parent['recovery_readback_at']).timestamp()
  before=copy.deepcopy(retained) if set(retained)==set(map(str,wanted)) and 0<=age<=180 else t.configs(sorted(wanted))
  state.update(before=before,baseline_readback_at=parent['recovery_readback_at'] if before==retained else stamp(),predecessor_run=parent.get('run_id'));save()
  eligible=t.wb('/adv/v2/supplier/nms','POST',[756]);state['white_eligibility_receipt']=eligible;save()
  def has_white(o):
   if isinstance(o,dict):return any(o.get(k)==997991777 for k in ('nm','nmId','nm_id')) or any(has_white(v) for v in o.values())
   return any(has_white(v) for v in o) if isinstance(o,list) else False
  white_eligible=has_white(eligible)
  names={c['settings']['name'] for c in before.values()}
  if any(s['name'] in names for s in p['new_campaigns']):raise ValueError('Matching campaign exists without this execution receipt; no duplicate creation')
  active={n['nm_id'] for c in before.values() if c.get('status')==9 for n in c['nm_settings']}
  newids={a['nm'] for s in p['new_campaigns'] for a in s['items']}
  if active&newids:raise ValueError('New candidates already actively advertised')
  fresh_fbo(t,newids|{997991777},state,save)
  def stock_guard(path,body):
   if path not in ('/adv/v0/auction/nms','/adv/v1/budget/deposit','/adv/v0/start'):return
   needed={997991777} if path=='/adv/v0/auction/nms' else newids
   receipt=state['fbo_receipts'][-1]
   age=time.time()-datetime.datetime.fromisoformat(receipt['observed_at']).timestamp()
   if age>1800 or not all(str(n) in receipt['quantity'] for n in needed):fresh_fbo(t,needed,state,save)
  t.pre_write=stock_guard
  expected=copy.deepcopy(before);bidrows=[];adds=[];state['existing_items']=[]
  for a in p['existing']:
   cid=str(a['campaign']);c=before[cid]
   if c.get('status')!=9 or c.get('currency')!='RUB' or c.get('bid_type')!='manual' or c['settings'].get('payment_type')!='cpc' or c['settings'].get('placements')!={'search':True,'recommendations':False}:raise ValueError('Existing target type/status changed')
   members={n['nm_id']:n for n in c['nm_settings']};nm=a['nm']
   if a['kind']=='lower_bid':
    if nm not in members or members[nm]['bids_kopecks']['search'] not in (295,300):raise ValueError('Bag current rate differs from authorized295/300')
    if members[nm]['bids_kopecks']['search']!=295:bidrows.append({'advert_id':a['campaign'],'nm_bids':[{'nm_id':nm,'placement':'search','bid_kopecks':295}]})
    for n in expected[cid]['nm_settings']:
     if n['nm_id']==nm:n['bids_kopecks']['search']=295
   else:
    if nm in active and nm not in members:raise ValueError('White manishka overlap')
    if nm not in members and not white_eligible:
     state['existing_items'].append(dict(a,status='not_eligible_for_advertising',reason='Exact nm absent from current supplier/nms response'));continue
    if nm not in members:
     if len(members)>=50 or not c.get('restrictions',{}).get('can_change_nms'):raise ValueError('White membership immutable/capacity')
     peers=[n for n in c['nm_settings'] if n['subject']['id']==756]
     if not peers:raise ValueError('Manishka category absent')
     adds.append({'advert_id':a['campaign'],'nms':{'add':[nm],'delete':[]}})
     expected[cid]['nm_settings'].append({'nm_id':nm,'subject':copy.deepcopy(peers[0]['subject']),'bids_kopecks':{'search':175,'recommendations':0}})
    elif members[nm]['bids_kopecks']['search']!=175:raise ValueError('Existing white manishka rate differs')
   state['existing_items'].append(dict(a,status='pending_readback'))
  retained=[n for n in before['40192945']['nm_settings'] if n['nm_id']==997991776]
  if len(retained)!=1 or retained[0]['bids_kopecks']['search']!=183:raise ValueError('Brown manishka approved rate changed')
  state['already_verified_brown']=dict(p['already_target'],status='verified',observed_at=stamp());save()
  if bidrows:write('existing_bids','/api/advert/v1/bids','PATCH',{'bids':bidrows})
  if adds:
   try:write('white_membership','/adv/v0/auction/nms','PATCH',{'nms':adds})
   except RuntimeError as rejected:
    if 'WB HTTP 400;' not in str(rejected):raise
    expected['40192945']['nm_settings']=[n for n in expected['40192945']['nm_settings'] if n['nm_id']!=997991777]
    for a in state['existing_items']:
     if a['nm']==997991777:a['status']='rejected_by_wb_400'
    state['white_rejected_detail_key']=EXEC+':last_http_failure';save()
  for spec in p['new_campaigns']:
   r=write('create_'+spec['group'],'/adv/v2/seacat/save-ad','POST',{'name':spec['name'],'nms':[a['nm'] for a in spec['items']],'bid_type':'manual','payment_type':'cpc','placement_types':['search']})
   cid=r if type(r)is int else r.get('advertId') if isinstance(r,dict) else None
   if type(cid)is not int or cid<=0:raise ValueError('Creation ID unknown; no blind repeat')
   state['campaigns'].append({'group':spec['group'],'campaign_id':cid,'spec':spec,'status':'created_unfunded'});save()
  for c in state['campaigns']:
   nm=c['spec']['items'][0]['nm'];j=t.wb('/api/advert/v1/bids/min','POST',{'advert_id':c['campaign_id'],'nm_ids':[nm],'payment_type':'cpc','placement_types':['search']})
   c['minimum_minor']=minimum_map(j,[nm],'search')[nm];c['minimum_receipt']=j;save()
  cids=[c['campaign_id'] for c in state['campaigns']];observed=t.configs(sorted(set(map(int,before))|set(cids)))
  exact={cid:projection(expected[cid])==projection(observed[cid]) for cid in before}
  state['existing_readback']=observed;state['existing_exact_campaigns']=exact;state['existing_readback_at']=stamp();save()
  if not all(exact.values()):raise ValueError('Unexpected campaign change after scoped writes; no new funding')
  for a in state['existing_items']:
   if a['status']=='pending_readback':a['status']='verified'
  for c in state['campaigns']:check_new(observed[str(c['campaign_id'])],c['spec'],c['minimum_minor']);c['status']='draft_verified'
  balances=budgets(cids);state['budgets_before']=balances;save()
  if any(v!=0 for v in balances.values()):raise ValueError('New draft already funded; no duplicate deposits')
  fresh_fbo(t,newids,state,save)
  for c in state['campaigns']:write('fund_'+c['group'],'/adv/v1/budget/deposit?id='+str(c['campaign_id']),'POST',{'sum':1000,'type':0})
  funded=budgets(cids);state['funded_readback']=funded;save()
  if any(funded.get(cid)!=1000 for cid in cids):raise ValueError('Approved1000RUB budget not confirmed; no start')
  for c in state['campaigns']:write('start_'+c['group'],'/adv/v0/start?id='+str(c['campaign_id']),'GET');c['status']='start_accepted';save()
  after=t.configs(sorted(set(map(int,before))|set(cids)));state['after']=after;state['readback_at']=stamp();save()
  if any(projection(expected[cid])!=projection(after[cid]) for cid in before):raise ValueError('Final existing scope variance')
  for c in state['campaigns']:check_new(after[str(c['campaign_id'])],c['spec'],c['minimum_minor'],active=True);c['status']='active_verified'
  state['no_change_at_floor']=p['no_change_at_floor'];state['status']='new_campaigns_verified_white_unavailable' if any(a['status']!='verified' for a in state['existing_items']) else 'verified_with_minimum_constraints'
 except Exception as e:
  state.update(status='attention',error=str(e) if isinstance(e,(PermissionError,ValueError,RuntimeError)) else type(e).__name__);save()
  if state.get('before') and state.get('wb_write_attempts',0) and not state.get('after'):
   try:
    check_ids=set(map(int,state['before']))|{c['campaign_id'] for c in state['campaigns']}
    recovery=t.configs(sorted(check_ids));state['recovery_readback']=recovery;state['recovery_readback_at']=stamp()
    for a in state.get('existing_items',[]):
     cid=str(a['campaign']);members=[n for n in recovery[cid]['nm_settings'] if n['nm_id']==a['nm']]
     if len(members)==1 and members[0]['bids_kopecks']['search']==a['target_bid_minor'] and projection(expected[cid])==projection(recovery[cid]):a['status']='verified'
    save()
   except Exception as check_error:state['readback_error']=str(check_error) if isinstance(check_error,(ValueError,RuntimeError)) else type(check_error).__name__
 state['finished_at']=stamp();save()
 pointer=t.get('ip_agent:expanded98:active_execution:v1') or {}
 added_verified=sum(a.get('status')=='verified' for a in state.get('existing_items',[]))
 new_verified=sum(len(c['spec']['items']) for c in state['campaigns'] if c.get('status')=='active_verified')
 total=76+added_verified+bool(state.get('already_verified_brown'))+new_verified
 pointer.update(status=state['status'],active_execution=None,latest_execution=EXEC,verified_unique_products=total,remaining_products=98-total,minimum_constraints=p['no_change_at_floor'],new_campaigns=[{'id':c['campaign_id'],'status':c['status']} for c in state['campaigns']],finished_at=state['finished_at'])
 t.save('ip_agent:expanded98:active_execution:v1',pointer)
 print(json.dumps({'status':state['status'],'new_campaigns':len(state['campaigns']),'active_verified':sum(c.get('status')=='active_verified' for c in state['campaigns']),'telegram_sends':0}))

if __name__=='__main__':run_finish()
