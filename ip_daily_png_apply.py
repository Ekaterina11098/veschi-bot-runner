"""Human reply to one frozen daily PNG. No old queues, automatic restoration or budgets."""
import argparse,copy,datetime,hashlib,json,math,os,time,urllib.error
from ip_apply_nine_20261103 import SixTransport,projection,stamp,HOST
from ip_daily_png_contract import PREFIX,CHAT,BOT,digest,action_id,ready
from ip_bags_growth_20261104 import active_ids
def validate(p,a,key):
 if not key.startswith(PREFIX) or not key.endswith(':approval') or not p or not a:raise PermissionError('Unknown daily PNG approval')
 if p.get('version')!='ip-daily-png-v1' or p.get('delivery_status')!='sent' or p.get('chat_id')!=CHAT or p.get('bot_id')!=BOT:raise PermissionError('PNG scope mismatch')
 if not p['actions'] or p['plan_sha256']!=digest(p['actions']) or any(not ready(x,p['period']) for x in p['actions']):raise PermissionError('Frozen ready actions missing')
 if a.get('chat_id')!=CHAT or a.get('bot_id')!=BOT or a.get('reply_message_id')!=p.get('message_id') or a.get('plan_sha256')!=p['plan_sha256'] or a.get('command')!='Сделай всё' or type(a.get('sender_id')) is not int:raise PermissionError('Reply approval binding mismatch')
 if datetime.datetime.now(datetime.timezone.utc)>=datetime.datetime.fromisoformat(p['expires_at']):raise PermissionError('Expired daily plan')
def expected_state(p,before):
 expected=copy.deepcopy(before)
 for a in p['actions']:
  cid=str(a['campaign']);c=before[cid];nm=a['nm']
  if projection(c)!=projection(a['baseline']):raise ValueError('WB changed since recommendation; no overwrite')
  if c.get('status')!=9 or c.get('currency')!='RUB' or c.get('bid_type')!='manual':raise ValueError('Active manual RUB campaign required')
  members={n['nm_id']:n for n in c['nm_settings']}
  if a['kind']=='remove':
   if nm not in members or not c['restrictions'].get('can_change_nms') or len(expected[cid]['nm_settings'])<=1:raise ValueError('Exact SKU removal not available')
   expected[cid]['nm_settings']=[n for n in expected[cid]['nm_settings'] if n['nm_id']!=nm]
  elif a['kind'] in ('raise_bid','lower_bid'):
   if nm not in members or members[nm]['bids_kopecks'].get(a['placement'])!=a['stored_bid_minor']:raise ValueError('Approved bid baseline changed')
   if a['kind']=='lower_bid' and not a['target_bid_minor']<a['stored_bid_minor']:raise ValueError('Not a reduction')
   if a['target_bid_minor']<a.get('minimum_bid_minor',a['stored_bid_minor']):raise ValueError('Target below verified minimum')
   for n in expected[cid]['nm_settings']:
    if n['nm_id']==nm:n['bids_kopecks'][a['placement']]=a['target_bid_minor']
  elif a['kind']=='add':
   if a.get('subject') not in (50,51,57,61,255,756) or c['settings'].get('payment_type')!='cpc' or c['settings'].get('placements')!={'search':True,'recommendations':False}:raise ValueError('Verified category/search-only CPC required for addition')
   if any(n['nm_id']==nm for v in before.values() if v.get('status')==9 for n in v['nm_settings']):raise ValueError('SKU already advertised; no overlap')
   if len(expected[cid]['nm_settings'])>=50 or not c['restrictions'].get('can_change_nms'):raise ValueError('Addition capacity unavailable')
   peers=[n for n in c['nm_settings'] if n['subject']['id']==a['subject']]
   if not peers or {n['subject']['id'] for n in c['nm_settings']}!={a['subject']}:raise ValueError('Do not mix categories')
   if a.get('minimum_bid_minor') is None or a['target_bid_minor']<a['minimum_bid_minor']:raise ValueError('Verified category minimum required')
   expected[cid]['nm_settings'].append(dict(nm_id=nm,subject=copy.deepcopy(peers[0]['subject']),bids_kopecks={'search':a['target_bid_minor'],'recommendations':0}))
  else:raise PermissionError('Unknown operation')
 return expected
def run(key):
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise PermissionError('Public main only')
 t=SixTransport();plan_key=key.removesuffix(':approval');p=t.get(plan_key);approval=t.get(key);validate(p,approval,key)
 ek=plan_key+':execution';state=dict(status='preflight',run_id=os.environ['GITHUB_RUN_ID'],approval=approval,steps={},wb_write_attempts=0,wb_accepted_requests=0,started_at=stamp())
 if not t.create(ek,state):print('Prior execution retained; no replay');return
 def save():t.save(ek,state)
 def progress(path,until):state.update(status='waiting_provider_cooldown',wait_endpoint=path,next_allowed_at=datetime.datetime.fromtimestamp(until,datetime.timezone.utc).isoformat());save()
 t.progress=progress
 def tg(method,body):
  token=os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()
  r=t.raw('https://api.telegram.org/bot'+token+'/'+method,{'Content-Type':'application/json'},'POST',body)
  if not r.get('ok'):raise RuntimeError('Telegram response not confirmed')
  return r['result']
 def guard():
  validate(p,approval,key)
  if t.get(plan_key)!=p or t.get(key)!=approval:raise PermissionError('Approval changed')
 ids=sorted({a['campaign'] for a in p['actions']})
 try:
  t.identity()
  if tg('getMe',{}).get('id')!=BOT:raise PermissionError('Bot identity mismatch')
  member=tg('getChatMember',dict(chat_id=CHAT,user_id=approval['sender_id']))
  if member.get('user',{}).get('is_bot') or member.get('user',{}).get('id')!=approval['sender_id'] or not(member.get('status') in ('member','administrator','creator') or member.get('status')=='restricted' and member.get('is_member')):raise PermissionError('Current human group member required')
  if any(a['kind']=='add' for a in p['actions']):ids,_=active_ids(t,ids)
  before=t.configs(ids);expected=expected_state(p,before);state.update(before=before,expected=expected,read_at=stamp());save();stage=copy.deepcopy(before);read_time=time.time()
  for a in p['actions']:
   marker='advertising:ip:action-once:v1:'+action_id(a)
   if not t.create(marker,dict(status='approved',plan_key=plan_key,execution_key=ek,approved_at=stamp())):raise PermissionError('Action already approved; no replay')
  def write(name,path,body):
   nonlocal read_time,stage
   for attempt in range(4):
    t.pause(path);guard()
    if time.time()-read_time>180:
     cur=t.configs(ids);read_time=time.time()
     if any(projection(cur[k])!=projection(stage[k]) for k in stage):raise ValueError('WB changed while waiting; no overwrite')
    step=dict(status='submitting',path=path,body=body,submitted_at=stamp());state['steps'][name+str(attempt)]=step;state['wb_write_attempts']+=1;save()
    try:
     response=t.raw(HOST+path,{'Authorization':t.token,'Content-Type':'application/json','User-Agent':'python-requests/2.32.5'},'PATCH',body)
     step.update(status='accepted',response=response,accepted_at=stamp());state['wb_accepted_requests']+=1;save();return
    except urllib.error.HTTPError as e:
     step.update(status='rejected',http_status=e.code);save();retry=e.headers.get('Retry-After') or e.headers.get('X-Ratelimit-Retry') or e.headers.get('X-Ratelimit-Reset')
     if e.code==429 and retry and attempt<3:
      seconds=float(retry)
      if not math.isfinite(seconds) or seconds<0:raise ValueError('Invalid retry interval')
      pause='wb-pause:'+hashlib.sha256((t.token+'advert-api.wildberries.ru'+path).encode()).hexdigest();old=t.get(pause) or {};t.save(pause,{'until':max(float(old.get('until',0)),time.time()+seconds+1),'basis':'provider_429_definite_rejection'});continue
     raise RuntimeError('WB rejected HTTP'+str(e.code)) from None
    except Exception:step.update(status='uncertain');save();raise
  removals={};bids={};adds={}
  for a in p['actions']:
   if a['kind']=='remove':removals.setdefault(a['campaign'],[]).append(a['nm'])
   elif a['kind']=='add':
    adds.setdefault(a['campaign'],[]).append(a['nm']);bids.setdefault(a['campaign'],[]).append(dict(nm_id=a['nm'],placement=a['placement'],bid_kopecks=a['target_bid_minor']))
   else:bids.setdefault(a['campaign'],[]).append(dict(nm_id=a['nm'],placement=a['placement'],bid_kopecks=a['target_bid_minor']))
  if removals or adds:
   write('membership','/adv/v0/auction/nms',{'nms':[dict(advert_id=cid,nms=dict(add=sorted(adds.get(cid,[])),delete=sorted(removals.get(cid,[])))) for cid in sorted(set(removals)|set(adds))]})
   stage=t.configs(ids);read_time=time.time();intermediate=copy.deepcopy(before)
   for cid,nms in removals.items():intermediate[str(cid)]['nm_settings']=[n for n in intermediate[str(cid)]['nm_settings'] if n['nm_id'] not in nms]
   for cid,nms in adds.items():
    for nm in nms:
     matches=[n for n in stage[str(cid)]['nm_settings'] if n['nm_id']==nm];target=next(n for n in expected[str(cid)]['nm_settings'] if n['nm_id']==nm)
     if len(matches)!=1 or matches[0]['subject']!=target['subject']:raise ValueError('Addition/category not verified')
     intermediate[str(cid)]['nm_settings'].append(copy.deepcopy(matches[0]))
   if any(projection(stage[k])!=projection(intermediate[k]) for k in stage):raise ValueError('Removal readback differs; no bid changes')
  if bids:write('bids','/api/advert/v1/bids',{'bids':[dict(advert_id=cid,nm_bids=nms) for cid,nms in sorted(bids.items())]})
  after=t.configs(ids);verified=all(projection(after[k])==projection(expected[k]) for k in expected)
  state.update(after=after,readback_at=stamp(),status='verified' if verified else 'attention_readback');save()
  if verified:
   nk=ek+':notification'
   if t.create(nk,dict(status='sending')):
    try:
     result=tg('sendMessage',dict(chat_id=CHAT,text='Выполнены '+str(len(p['actions']))+' изменений из подтверждённого PNG. Результат каждого проверен WB. Остальные настройки сохранены.',reply_parameters=dict(message_id=approval['input_message_id'])))
     t.save(nk,dict(status='confirmed',message_id=result['message_id']))
    except Exception:t.save(nk,dict(status='uncertain'))
 except Exception as e:state.update(status='attention',error=str(e) if isinstance(e,(PermissionError,RuntimeError,ValueError)) else type(e).__name__);save()
 finally:state.update(finished_at=stamp());save()
 print(json.dumps({k:state.get(k) for k in ('status','wb_write_attempts','wb_accepted_requests')}))
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--approval-key',required=True);run(parser.parse_args().approval_key)

