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

PLAN='ip_agent:traffic_adjustments:2026-11-03:six:v1'
EXEC=PLAN+':execution'
FROZEN_SCOPE_SHA='c7a63251d99765fcffc76231232c5962adc1e349d26fe9959bf0fe0bae8853e7'

def scope_hash(scope):return hashlib.sha256(json.dumps(scope,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def prepare_six(scope,configs):
 expected=copy.deepcopy(configs);selected=[];items=[]
 for a in scope:
  cid=str(a['campaign']);c=configs[cid];members={n['nm_id']:n for n in c['nm_settings']};nm=a['nm']
  if c.get('status')!=9 or c.get('currency')!='RUB' or c.get('bid_type')!='manual':raise ValueError('Approved active manual RUB campaign not confirmed')
  result=dict(sku=a['sku'],nm=nm,campaign=a['campaign'],kind=a['kind'])
  if a['kind']=='remove':
   keep=configs[str(a['preserve_cpc'])]
   if keep.get('status')!=9 or keep['settings'].get('payment_type')!='cpc' or nm not in {n['nm_id'] for n in keep['nm_settings']}:raise ValueError('Preserved CPC presence/activity not confirmed')
   if c['settings'].get('payment_type')!='cpm' or not c.get('restrictions',{}).get('can_change_nms'):raise ValueError('Expected mutable CPM not confirmed')
   if nm not in members:items.append(dict(result,status='already_absent'));continue
   expected[cid]['nm_settings']=[n for n in expected[cid]['nm_settings'] if n['nm_id']!=nm]
  elif a['kind']=='raise_bid':
   if c['settings'].get('payment_type')!='cpc' or nm not in members:raise ValueError('Expected CPC member not confirmed')
   old=members[nm].get('bids_kopecks',{}).get('search');target=a['target_bid_minor']
   if old==target:items.append(dict(result,status='already_target'));continue
   if old!=a['stored_bid_minor'] or not old<target<=math.floor(old*1.05):raise ValueError('Current bid differs from exact owner approval')
   for n in expected[cid]['nm_settings']:
    if n['nm_id']==nm:n['bids_kopecks']['search']=target
   a=dict(a,placement='search')
  else:raise PermissionError('Unapproved operation')
  selected.append(a);items.append(dict(result,status='planned'))
 return selected,expected,items

class SixTransport(Transport):
 def raw(self,url,headers,method='GET',body=None):
  req=urllib.request.Request(url,headers=headers,method=method,data=None if body is None else json.dumps(body).encode())
  with self.opener.open(req,timeout=55) as r:
   b=r.read(100*1024*1024+1)
   if len(b)>100*1024*1024:raise RuntimeError('100MB wire limit')
   if r.headers.get('Content-Encoding')=='gzip':b=gzip.decompress(b)
   self.decoded_bytes=getattr(self,'decoded_bytes',0)+len(b)
   if self.decoded_bytes>100*1024*1024:raise RuntimeError('100MB decoded limit')
   if url.startswith(HOST):self.last_headers={k.lower():v for k,v in r.headers.items()}
   return json.loads(b) if b else {}

def run_six():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise PermissionError('Public main only')
 t=SixTransport();p=t.get(PLAN)
 if not p or p.get('status')!='owner_authorized' or len(p.get('scope',[]))!=6 or scope_hash(p['scope'])!=FROZEN_SCOPE_SHA:raise PermissionError('Frozen six-item approval missing')
 state=dict(status='starting',run_id=os.environ['GITHUB_RUN_ID'],approval_key=PLAN,started_at=stamp(),steps={},items=[],wb_write_attempts=0,wb_accepted_requests=0,telegram_sends=0)
 if not t.create(EXEC,state):print('Prior claim retained; no replay');return
 def save():t.save(EXEC,state)
 def progress(path,until):state.update(status='waiting_provider_cooldown',wait_endpoint=path,next_allowed_at=datetime.datetime.fromtimestamp(until,datetime.timezone.utc).isoformat());save()
 t.progress=progress
 def guard():
  if datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).date().isoformat()!='2026-11-03' or t.get(PLAN)!=p:raise PermissionError('Dated approval changed/expired')
  for key in ('ip_agent:expanded98:finish:2026-11-02:v1','ip_agent:expanded98:finish:2026-11-02:v2'):
   old=t.get(key)
   if old and old.get('status')!='manual_handoff':raise PermissionError('Old writer authorization not retired')
 ids=sorted({a['campaign'] for a in p['scope']}|{a['preserve_cpc'] for a in p['scope'] if a['kind']=='remove'})
 try:
  t.identity();guard()
  # Existing FBO-only reader, no stock mutations; one category report for the two panamas.
  fresh_fbo(t,{a['nm'] for a in p['scope'] if a.get('fbo_only')},state,save)
  before=t.configs(ids);read_time=time.time();state.update(before=before,configuration_observed_at=stamp());save()
  selected,expected,items=prepare_six(p['scope'],before);state.update(expected=expected,items=items);save()
  reached=copy.deepcopy(before)
  def submit(name,path,body,actions):
   nonlocal reached,read_time
   for attempt in range(4):
    t.pause(path);guard()
    if time.time()-read_time>180:
     current=t.configs(ids);read_time=time.time()
     if any(projection(current[k])!=projection(reached[k]) for k in reached):raise ValueError('Fresh WB state changed; no overwrite')
     state['pre_write_refresh_at']=stamp();save()
    step_id=name+':'+str(attempt)
    if step_id in state['steps']:raise PermissionError('Attempt already exists')
    step=dict(status='submitting',path=path,body=body,submitted_at=stamp());state['steps'][step_id]=step;state['wb_write_attempts']+=1;save()
    try:
     response=t.raw(HOST+path,{'Authorization':t.token,'Content-Type':'application/json','User-Agent':'python-requests/2.32.5'},'PATCH',body)
     step.update(status='accepted',response=response,accepted_at=stamp());state['wb_accepted_requests']+=1;save()
     for a in actions:
      c=reached[str(a['campaign'])]
      if a['kind']=='remove':c['nm_settings']=[n for n in c['nm_settings'] if n['nm_id']!=a['nm']]
      else:
       for n in c['nm_settings']:
        if n['nm_id']==a['nm']:n['bids_kopecks']['search']=a['target_bid_minor']
     return
    except urllib.error.HTTPError as e:
     retry=e.headers.get('Retry-After') or e.headers.get('X-Ratelimit-Retry') or e.headers.get('X-Ratelimit-Reset')
     detail=e.read(4096).decode('utf-8',errors='replace').replace(t.token,'[REDACTED]')
     step.update(status='rejected',http_status=e.code,detail_private=detail);save()
     if e.code==429 and retry and attempt<3:
      seconds=float(retry)
      if not math.isfinite(seconds) or seconds<0:raise ValueError('Invalid retry header')
      key='wb-pause:'+hashlib.sha256((t.token+'advert-api.wildberries.ru'+path).encode()).hexdigest();old=t.get(key) or {}
      t.save(key,{'until':max(float(old.get('until',0)),time.time()+seconds+1),'basis':'provider_429_definite_rejection'});continue
     raise RuntimeError('WB rejected request HTTP'+str(e.code)) from None
    except Exception:
     step.update(status='uncertain',error='Unknown result; do not replay');save();raise
   raise RuntimeError('429 retry allowance exhausted')
  removes=[a for a in selected if a['kind']=='remove']
  if removes:submit('membership','/adv/v0/auction/nms',{'nms':[{'advert_id':removes[0]['campaign'],'nms':{'add':[],'delete':sorted(a['nm'] for a in removes)}}]},removes)
  raises=[a for a in selected if a['kind']=='raise_bid'];bids={}
  for a in raises:bids.setdefault(a['campaign'],[]).append({'nm_id':a['nm'],'bid_kopecks':a['target_bid_minor'],'placement':'search'})
  if bids:submit('bids','/api/advert/v1/bids',{'bids':[{'advert_id':cid,'nm_bids':nms} for cid,nms in sorted(bids.items())]},raises)
  state['status']='verifying';save()
  after=t.configs(ids);state.update(after=after,readback_at=stamp(),no_unapproved_changes={k:projection(after[k])==projection(expected[k]) for k in expected})
  for item in state['items']:
   a=next(a for a in p['scope'] if a['nm']==item['nm']);c=after[str(a['campaign'])];members={n['nm_id']:n for n in c['nm_settings']}
   ok=(a['nm'] not in members) if a['kind']=='remove' else (a['nm'] in members and members[a['nm']]['bids_kopecks'].get('search')==a['target_bid_minor'])
   item['status']='verified' if ok and all(state['no_unapproved_changes'].values()) else 'not_verified'
  state['status']='verified' if all(x['status']=='verified' for x in state['items']) else 'attention_readback';save()
 except Exception as e:
  state.update(status='attention',error=str(e) if isinstance(e,(RuntimeError,ValueError,PermissionError)) else type(e).__name__)
  if state['wb_write_attempts']:
   try:state.update(recovery_readback=t.configs(ids),recovery_readback_at=stamp())
   except Exception as re:state['recovery_readback_error']=type(re).__name__
  save()
 finally:state.update(finished_at=stamp(),decoded_response_bytes=getattr(t,'decoded_bytes',0));save()
 print(json.dumps({k:state.get(k) for k in ('status','wb_write_attempts','wb_accepted_requests','telegram_sends')}))

if __name__=='__main__':run_six()
