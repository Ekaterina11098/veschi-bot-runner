"""Durable exact-report execution. Deterministic, private receipts, no model calls."""
import os,json,time,hashlib,copy,base64,requests
from datetime import datetime,timezone
from ooo_sol_dialog import DB as DialogueDB,Worker as Dialogue,ROOT,CHAT,BOT
from ooo_report_command import digest

LEGACY='ooo_agent:report_apply:2026-11-09:v1'
IDS={39605581,39605579,40385586,41515989,41516310,41516903,41517233,41517533,39605582}
def stamp():return datetime.now(timezone.utc).isoformat()
class Deferred(Exception):pass
class Stop(Exception):pass
class DB(DialogueDB):
 def once(self,key,value):
  self.allowed(key)
  rows=self.api('POST',{},dict(cache_key=key,payload=value,updated_at=stamp(),expires_at='2030-11-07T00:00:00Z'))
  if len(rows)!=1:raise Stop('Execution identity already claimed')
  return value
 def allowed(self,key):
  if not(key.startswith(ROOT)or key.startswith(LEGACY+':')or key.startswith('wb-pause:')):raise PermissionError('Private execution scope')
 def update(self,key,value):
  self.allowed(key);value=json.loads(json.dumps(value))
  rows=self.api('PATCH',{'cache_key':'eq.'+key},dict(payload=value,updated_at=stamp()))
  if len(rows)!=1 or self.get(key)!=value:raise Stop('Receipt persistence not verified')
 def put(self,key,value):return self.update(key,value)if self.get(key)is not None else self.once(key,value)

def validate(m):
 if m.get('cabinet')!='token_1'or m.get('currency')!='KGS'or m.get('other_changes',[])!=[]:raise Stop('Report scope invalid')
 if not(m.get('actions')or m.get('topups')):raise Stop('Empty report')
 seen=set()
 for a in m.get('actions',[]):
  if type(a.get('cid'))is not int or a['cid']not in IDS:raise Stop('Unknown campaign')
  kind=a.get('kind')
  if kind not in('exclude_sku','reduce_bid','raise_bid','add_sku','pause_campaign','resume_campaign'):raise Stop('Unsupported action')
  if kind not in('pause_campaign','resume_campaign')and(type(a.get('nm'))is not int or a['nm']<=0):raise Stop('Invalid SKU')
  identity=(a['cid'],a.get('nm'),a.get('placement')if kind in('reduce_bid','raise_bid')else None)
  if identity in seen:raise Stop('Duplicate/conflicting action')
  seen.add(identity)
  if kind in('reduce_bid','raise_bid','add_sku'):
   if a.get('placement')not in('search','recommendations')or type(a.get('to_minor'))is not int or a['to_minor']<=0:raise Stop('Invalid bid')
   if kind!='add_sku'and(type(a.get('from_minor'))is not int or (a['to_minor']>=a['from_minor']if kind=='reduce_bid'else a['to_minor']<=a['from_minor'])):raise Stop('Invalid exact transition')
 for t in m.get('topups',[]):
  if t.get('cid')not in IDS or type(t.get('amount_kgs'))is not int or t['amount_kgs']<=0:raise Stop('Invalid funding')
  if t['cid']==41517533:raise Stop('Campaign funding explicitly disabled by owner')
 if len({t['cid']for t in m.get('topups',[])})!=len(m.get('topups',[])):raise Stop('Duplicate funding')
 if any(a['cid']==41517533 and a['kind']=='resume_campaign'for a in m.get('actions',[])):raise Stop('Campaign start explicitly disabled by owner')

def project(c):
 return {k:copy.deepcopy(c.get(k))for k in('id','status','currency','bid_type','settings','restrictions')}|{'nm_settings':sorted(copy.deepcopy(c['nm_settings']),key=lambda n:n['nm_id'])}

class Executor:
 def __init__(self,db=None,token=None,request=None):
  self.db=db or DB();self.token=token or os.environ['WB_TOKEN_1'];self.request=request or requests.request
 def identity(self):
  c=json.loads(base64.urlsafe_b64decode(self.token.split('.')[1]+'==='))
  rows=self.db.api('GET',{'cache_key':'eq.ooo_agent:seller_identity:v1','select':'payload','limit':1})
  # Seller identity lives in analytics_snapshots, never infer it from token alone.
  from urllib.request import Request,urlopen
  from urllib.parse import urlencode
  key=os.environ['SUPABASE_SECRET_KEY'];headers={'apikey':key,'Authorization':'Bearer '+key}
  url=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/analytics_snapshots?'+urlencode({'cabinet':'eq.token_1','source':'eq.seller_identity','status':'eq.complete','select':'payload','limit':100})
  with urlopen(Request(url,headers=headers),timeout=30)as r:ident=json.load(r)
  if c.get('exp',0)<=time.time()or c.get('t')is not False or int(c.get('s',0))&(1<<30)or not c.get('sid')or {x['payload'].get('sid')for x in ident}!={c['sid']}:raise Stop('OOO seller identity mismatch')
 def call(self,s,save,method,path,body=None,params=None,step=None):
  allowed={('GET','/api/advert/v2/adverts'),('PATCH','/adv/v0/auction/nms'),('PATCH','/api/advert/v1/bids'),('GET','/adv/v0/start'),('GET','/adv/v0/pause'),('POST','/api/advert/v2/budget'),('GET','/adv/v1/balance'),('GET','/api/advert/v1/config'),('POST','/adv/v1/budget/deposit')}
  if(method,path)not in allowed:raise Stop('Endpoint outside scope')
  old=s.setdefault('steps',{}).get(step)if step else None
  if old:
   if old['status']=='accepted':return old.get('response',{})
   if old['status']not in('rejected_429',):raise Stop('Write retained; no replay of '+old['status'])
  pause='wb-pause:'+hashlib.sha256((self.token+'advert-api.wildberries.ru'+path).encode()).hexdigest()
  until=float((self.db.get(pause)or{}).get('until',0))
  if until>time.time():s.update(resume_after=until,waiting_path=path);save();raise Deferred()
  if step:s['steps'][step]={'status':'submitting','path':path,'method':method,'body':body,'params':params,'submitted_at':stamp()};save()
  try:r=self.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':self.token},json=body,params=params,timeout=(10,60),allow_redirects=False)
  except requests.RequestException:
   if step:s['steps'][step]['status']='uncertain';save()
   raise Stop('Transport outcome uncertain; no automatic replay')from None
  try:data=r.json()
  except ValueError:data={'response_text':r.text[:2000]}
  raw=r.headers.get('Retry-After')or r.headers.get('X-Ratelimit-Retry')or r.headers.get('X-Ratelimit-Reset')
  try:delay=float(raw or 0)
  except ValueError:delay=0
  if delay>time.time()-86400:delay=max(0,delay-time.time())
  if r.status_code==429 or(r.headers.get('X-Ratelimit-Remaining')=='0'and delay>0):self.db.put(pause,{'until':max(until,time.time()+max(delay,60)+3),'basis':'provider_header'})
  s.setdefault('last_http',{})[path]={'http_status':r.status_code,'response':data,'observed_at':stamp()};save()
  if r.status_code==429:
   if step:s['steps'][step].update(status='rejected_429',http_status=429);save()
   raise Deferred()
  if not 200<=r.status_code<300:
   if step:s['steps'][step].update(status='rejected',http_status=r.status_code,response=data);save()
   raise Stop('WB rejected HTTP '+str(r.status_code)+' '+path)
  if step:s['steps'][step].update(status='accepted',http_status=r.status_code,response=data,accepted_at=stamp());save()
  return data
 def configs(self,s,save,ids):
  out={str(c['id']):c for c in self.call(s,save,'GET','/api/advert/v2/adverts',params={'ids':','.join(map(str,sorted(ids)))})['adverts']}
  if set(out)!=set(map(str,ids)):raise Stop('Incomplete campaign readback')
  return out
 def prepare(self,m,before):
  expected=copy.deepcopy(before);members={};bids={};statuses=[];adds={}
  for c in before.values():
   if c.get('currency')!='KGS'or c.get('status')not in(9,11)or c.get('bid_type')!='manual'or c.get('settings',{}).get('payment_type')!='cpc':raise Stop('Unsupported campaign baseline')
  for a in m.get('actions',[]):
   cid=str(a['cid']);c=expected[cid];kind=a['kind'];nm=a.get('nm');n=next((n for n in c['nm_settings']if n['nm_id']==nm),None)
   if kind=='exclude_sku':
    if n is None:continue
    if c['restrictions'].get('can_change_nms')is not True:raise Stop('Membership locked')
    members.setdefault(cid,{'add':[],'delete':[]})['delete'].append(nm);c['nm_settings'].remove(n)
   elif kind in('reduce_bid','raise_bid','add_sku'):
    p=a['placement'];target=a['to_minor']
    if not c['settings']['placements'].get(p):raise Stop('Placement disabled')
    minimum=270 if n and n.get('subject',{}).get('id')==294 else 325
    if target<minimum:raise Stop('Below cached category minimum')
    if kind=='add_sku'and n is None:
     if c['restrictions'].get('can_change_nms')is not True:raise Stop('Membership locked')
     members.setdefault(cid,{'add':[],'delete':[]})['add'].append(nm);adds.setdefault(cid,[]).append(nm)
    elif n is None:raise Stop('Bid member missing')
    elif n['bids_kopecks'].get(p)==target:continue
    elif kind=='add_sku'or n['bids_kopecks'].get(p)!=a['from_minor']:raise Stop('Current bid differs from approved transition')
    bids.setdefault(cid,[]).append({'nm_id':nm,'placement':p,'bid_kopecks':target})
    if n:n['bids_kopecks'][p]=target
   else:
    target=9 if kind=='resume_campaign'else 11
    if c['status']!=target:statuses.append([int(cid),target]);c['status']=target
  if any(not c['nm_settings']and not adds.get(cid)for cid,c in expected.items()):raise Stop('Would empty campaign')
  return dict(expected=expected,members=members,bids=bids,statuses=statuses,adds=adds)
 def verify(self,s,after):
  expected=s['expected'];adds=s.get('adds',{})
  if set(after)!=set(expected):raise Stop('Readback coverage mismatch')
  for cid,e in expected.items():
   actual=copy.deepcopy(after[cid]);new=set(adds.get(cid,[]))
   if {n['nm_id']for n in actual['nm_settings']}!={n['nm_id']for n in e['nm_settings']}|new:raise Stop('Membership readback differs')
   actual['nm_settings']=[n for n in actual['nm_settings']if n['nm_id']not in new]
   if project(actual)!=project(e):raise Stop('Unapproved configuration drift')
   for bid in s.get('bids',{}).get(cid,[]):
    n=next(n for n in after[cid]['nm_settings']if n['nm_id']==bid['nm_id'])
    if n['bids_kopecks'].get(bid['placement'])!=bid['bid_kopecks']:raise Stop('Bid readback differs')
 def fund(self,s,save,t,step):
  old=s.get('steps',{}).get(step)
  if old and old['status']=='accepted':return
  amount=t['amount_kgs'];cid=t['cid']
  # Capture diagnostic evidence before any known-rejected retry. Never round approval up.
  if not s.get('funding_config_checked_at'):
   try:s['funding_config']=self.call(s,save,'GET','/api/advert/v1/config')
   except Stop:
    if s.get('last_http',{}).get('/api/advert/v1/config',{}).get('http_status')not in(401,403):raise
   s['funding_config_checked_at']=stamp();save()
  cfg=s.get('funding_config',{})
  if cfg and cfg.get('currency')!='KGS':raise Stop('Funding configuration currency differs')
  if cfg.get('minTopUp',0)>amount*100:raise Stop('Approved funding is below provider minimum; separate approval required')
  b=([s['funding_before']]if step=='deposit_39605581_500_repair1'and s.get('funding_before',{}).get('advertId')==cid else self.call(s,save,'POST','/api/advert/v2/budget',{'advertIds':[cid]})['adverts'])
  wallet=self.call(s,save,'GET','/adv/v1/balance')
  if len(b)!=1 or b[0].get('advertId')!=cid or b[0].get('currency')!='KGS'or wallet.get('currency')!='KGS':raise Stop('Funding currency/readback mismatch')
  source=0 if wallet.get('balance',0)>=amount else 1 if wallet.get('net',0)>=amount else None
  if source is None:raise Stop('Insufficient wallet; funding not submitted')
  s.setdefault('funding_before_by_campaign',{})[str(cid)]=b[0];s['funding_wallet']=wallet;save()
  receipt=self.call(s,save,'POST','/adv/v1/budget/deposit',{'sum':amount,'type':source,'return':True},params={'id':cid},step=step)
  if receipt.get('currency')!='KGS'or type(receipt.get('total'))not in(int,float):raise Stop('Accepted deposit receipt requires reconciliation; never replay')
 def process(self,key,a):
  m=a['manifest'];validate(m)
  if digest(m)!=a['manifest_sha256']:raise Stop('Approval digest mismatch')
  binding=self.db.get(ROOT+'report_binding:'+str(CHAT)+':'+str(a['report_message_id']))or{}
  if binding.get('status')!='delivered_verified'or binding.get('manifest_sha256')!=digest(m)or binding.get('chat_id')!=CHAT:raise Stop('Verified delivered report binding missing')
  s=a.setdefault('execution',{'steps':{},'started_at':stamp(),'model_calls':0})
  def save():self.db.update(key,a)
  def fresh():
   latest=self.db.get(key)or{}
   if latest.get('manifest_sha256')!=a['manifest_sha256']or latest.get('manifest')!=m:raise Stop('Authorization changed')
   if datetime.now(timezone.utc)>=datetime.fromisoformat(a['expires_at']):raise Stop('Authorization expired before pending write')
  a['status']='executing';save()
  try:
   ids={x['cid']for x in m.get('actions',[])}|{t['cid']for t in m.get('topups',[])}
   if not s.get('expected'):
    fresh();s['before']=self.configs(s,save,ids);s.update(self.prepare(m,s['before']));save()
   def write(method,path,body=None,params=None,step=None):
    if s['steps'].get(step,{}).get('status')!='accepted':fresh()
    return self.call(s,save,method,path,body,params,step)
   for cid,status in s['statuses']:
    if status==11:write('GET','/adv/v0/pause',params={'id':cid},step='pause_'+str(cid))
   if s['members']:write('PATCH','/adv/v0/auction/nms',{'nms':[{'advert_id':int(cid),'nms':v}for cid,v in s['members'].items()]},step='memberships')
   if s['bids']:write('PATCH','/api/advert/v1/bids',{'bids':[{'advert_id':int(cid),'nm_bids':v}for cid,v in s['bids'].items()]},step='bids')
   for cid,status in s['statuses']:
    if status==9:write('GET','/adv/v0/start',params={'id':cid},step='start_'+str(cid))
   # Verify advertising even when an independent funding item is rejected.
   if not s.get('advertising_verified_at'):
    s['after']=self.configs(s,save,ids);self.verify(s,s['after']);s['advertising_verified_at']=stamp();save()
   for t in m.get('topups',[]):
    step='deposit_'+str(t['cid'])+'_'+str(t['amount_kgs'])
    if s['steps'].get(step,{}).get('status')!='accepted':fresh()
    self.fund(s,save,t,step)
   if m.get('topups'):s['funding_after']=self.call(s,save,'POST','/api/advert/v2/budget',{'advertIds':[t['cid']for t in m['topups']]});save()
   a['status']='verified';s['verified_at']=stamp();save()
  except Deferred:a['status']='waiting_shared_quota';save()
  except Stop as e:a['status']='attention';s['safe_error']=str(e);save()
 def repair_legacy(self):
  auth=self.db.get(LEGACY+':repair_500')or{}
  if auth.get('status')!='approved':return
  s=self.db.get(LEGACY+':execution')or{}
  if s.get('status')in('verified','repair_attention'):return
  if s.get('manifest_sha256')!=auth.get('manifest_sha256')or s.get('steps',{}).get('deposit_39605581_500',{}).get('status')!='rejected':raise Stop('Legacy rejected-only recovery guard')
  if any(s.get('steps',{}).get(x,{}).get('status')!='accepted'for x in('memberships','bids')):raise Stop('Legacy accepted advertising receipts missing')
  def save():self.db.update(LEGACY+':execution',s)
  try:
   if not s.get('funding_config_checked_at'):
    try:s['funding_config']=self.call(s,save,'GET','/api/advert/v1/config')
    except Stop:
     if s.get('last_http',{}).get('/api/advert/v1/config',{}).get('http_status')not in(401,403):raise
    s['funding_config_checked_at']=stamp();save()
   if not s.get('funding_repair_error')and s.get('steps',{}).get('deposit_39605581_500_repair1',{}).get('status')!='accepted':
    if datetime.now(timezone.utc)>=datetime.fromisoformat(auth['expires_at']):raise Stop('Repair funding authorization expired')
    try:self.fund(s,save,{'cid':39605581,'amount_kgs':500},'deposit_39605581_500_repair1')
    except Stop as e:s['funding_repair_error']=str(e);save()
   if not s.get('advertising_verified_at'):
    s['after']=self.configs(s,save,set(map(int,s['expected'])));s.setdefault('adds',{});s.setdefault('bids',s.get('prepared_bids',{}));self.verify(s,s['after']);s['advertising_verified_at']=stamp();save()
   if s.get('funding_repair_error'):raise Stop(s['funding_repair_error'])
   s['funding_after']=self.call(s,save,'POST','/api/advert/v2/budget',{'advertIds':[39605581]});s.update(status='verified',verified_at=stamp());save()
  except Deferred:s['status']='waiting_shared_quota';save()
  except Stop as e:s.update(status='repair_attention',safe_error=str(e));save()
 def run(self):
  self.identity();self.repair_legacy()
  rows=self.db.api('GET',{'cache_key':'like.'+ROOT+'approved_report:*','payload->>status':'in.(approved_pending_execution,executing,waiting_shared_quota)','select':'cache_key,payload','order':'updated_at.asc','limit':2})
  for row in rows:
   try:self.process(row['cache_key'],row['payload'])
   except Stop as e:
    a=row['payload'];a.update(status='attention');a.setdefault('execution',{})['safe_error']=str(e);self.db.update(row['cache_key'],a)
  print('Private report queue processed; no model calls')

def notify():
 db=DB();dialog=Dialogue(db);dialog.preflight()
 rows=db.api('GET',{'cache_key':'like.'+ROOT+'approved_report:*','payload->>status':'in.(verified,attention)','select':'cache_key,payload','limit':20})
 legacy=db.get(LEGACY+':execution')or{}
 if legacy.get('status')in('verified','repair_attention'):rows.append({'cache_key':LEGACY+':execution','payload':legacy})
 for row in rows:
  a=row['payload'];s=a.get('execution',a)
  if a.get('completion_delivery'):continue
  if a.get('status')=='verified':text='Пакет отчёта выполнен и проверен в WB. Принятые действия повторно не отправлялись.'
  elif s.get('advertising_verified_at'):
   detail=str(s.get('safe_error','требуется разбор отказа WB'))
   provider=s.get('last_http',{}).get('/adv/v1/budget/deposit',{}).get('response',{})
   if 'minimum'in str(provider).lower()or 'below provider minimum'in detail:
    detail='согласованные 500 KGS меньше минимальной суммы WB. Увеличивать сумму без нового согласования не буду'
   elif provider:detail='WB отклонил запрос. Ответ сохранён для разбора: '+json.dumps(provider,ensure_ascii=False)[:500]
   text='Рекламные изменения выполнены и проверены. Пополнение не выполнено: '+detail[:600]+'. Принятые изменения не повторяю.'
  else:text='Исполнение остановлено для проверки: '+str(s.get('safe_error','неполный ответ WB'))[:500]+'. Принятые или неопределённые запросы повторно не отправляю.'
  a['completion_delivery']={'status':'uncertain','attempted_at':stamp()};db.update(row['cache_key'],a)
  try:
   receipt=dialog.tg('sendMessage',{'chat_id':CHAT,'text':text})
   if receipt.get('chat',{}).get('id')!=CHAT or receipt.get('from',{}).get('id')!=BOT or type(receipt.get('message_id'))is not int:raise Stop('Unverified Telegram receipt')
   a['completion_delivery'].update(status='verified',message_id=receipt['message_id'],delivered_at=stamp());db.update(row['cache_key'],a)
  except Exception:pass # Unknown send is never replayed.
 print('Completion receipts retained')

if __name__=='__main__':
 import sys
 if '--notify'in sys.argv:notify()
 else:Executor().run()

