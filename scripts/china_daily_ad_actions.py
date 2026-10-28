"""Exact page-bound daily advertising/budget approvals; isolated journalled execution."""
import copy,json,time
from datetime import datetime,timezone,timedelta
from china_loss_control import CHAT,BOT,PLAN,APPROVAL,digest,is_all,marker
BIND='china_agent:daily_ad_message:v2:'
EXEC='china_agent:daily_ad_execution:v2:'
def plan(io,day,f,index,slot=''):
 pid='daily-'+day+('-'+slot if slot else '')+'-'+f['family']+'-'+str(index);items=copy.deepcopy(f['actions'])
 p=dict(plan_id=pid,chat_id=CHAT,bot_id=BOT,execution_kind='daily_ad_actions_v2',family=f['family'],created_at=datetime.now(timezone.utc).isoformat(),expires_at=(datetime.now(timezone.utc)+timedelta(hours=20)).isoformat(),items=items,plan_sha256=digest(items),report_message_ids=[],price_changes=False,auto_topup=False,period_to=day)
 k=PLAN+pid;old=io.get(k)
 if old:
  if old['plan_sha256']!=p['plan_sha256']:raise ValueError('Daily page plan changed')
  return old
 if not io.create(k,p):raise ValueError('Concurrent daily page plan')
 return p

def bind(io,f,receipt):
 p=io.get(PLAN+f['plan_id'])
 if not p or digest(p['items'])!=f['plan_sha256'] or p['plan_sha256']!=f['plan_sha256']:raise ValueError('Daily PNG plan binding mismatch')
 mid=receipt['message_id'];p['report_message_ids']=sorted(set(p['report_message_ids']+[mid]));io.put(PLAN+p['plan_id'],p)
 b=dict(plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],chat_id=CHAT,family=p['family'])
 old=io.get(BIND+str(mid))
 if old and old!=b:raise ValueError('Daily message binding changed')
 if not old and not io.create(BIND+str(mid),b):raise ValueError('Concurrent daily binding')

def handle(w,job):
 from china_daily_selected import handle as selected_handle
 selected_result=selected_handle(w,job)
 if selected_result is not None:return selected_result
 m=marker(job);b=w.get(BIND+str(m.get('reply_message_id')))
 if not b or not is_all(job.get('request_text','')):return None
 from china_group_permissions import allowed
 if not allowed(w,job) or m.get('bot_id')!=BOT:return ('Применить план могут только действующие участники этой группы.',[])
 p=w.get(PLAN+b['plan_id'])
 if not p or p.get('chat_id')!=CHAT or p['plan_sha256']!=digest(p['items']) or b['plan_sha256']!=p['plan_sha256']:raise ValueError('Daily plan hash mismatch')
 if m.get('reply_message_id') not in p['report_message_ids']:raise ValueError('Daily reply not bound')
 if w.now>datetime.fromisoformat(p['expires_at']):return ('План устарел. Нужен свежий отчёт и подтверждение обновлённых действий.',[])
 if p.get('invalidated_at'):return ('План этого PNG отозван после проверки: '+p.get('invalidation_reason','нужен свежий план')+'. Изменения не выполняю.',[])
 if p.get('visible_from') and datetime.fromisoformat(job['created_at'])<datetime.fromisoformat(p['visible_from']):return ('PNG обновлён после этого подтверждения. Ответьте на обновлённый отчёт ещё раз.',[])
 if not p['items']:return ('В этом PNG нет новых действий. Уже выполненное и наблюдение повторно не запускаю.',[])
 a=dict(status='approved',plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],job_id=job['id'],update_id=job['update_id'],sender_id=job['sender_id'],chat_id=CHAT,bot_id=BOT,input_message_id=m.get('message_id'),reply_message_id=m['reply_message_id'],created_at=job['created_at'],price_changes=False)
 w.save(APPROVAL+str(job['id']),a,insert=True)
 return ('Принято: только '+str(len(p['items']))+' новых действий этого PNG. Проверю текущие параметры и результат WB. Цены и автопополнение не меняю.',[dict(name='daily_ad_actions_approval',plan_id=p['plan_id'])])

def execute(io,a,p):
 io.validate_owner(a)
 if p.get('invalidated_at'):raise ValueError('Daily PNG plan invalidated after audit')
 if p.get('visible_from') and (not a.get('created_at') or datetime.fromisoformat(a['created_at'])<datetime.fromisoformat(p['visible_from'])):raise ValueError('Approval predates corrected PNG')
 if p['execution_kind']!='daily_ad_actions_v2' or p['plan_sha256']!=digest(p['items']) or a['plan_sha256']!=p['plan_sha256']:raise ValueError('Daily execution scope changed')
 key=EXEC+p['plan_id'];e=io.get(key)
 if not e:
  e=dict(status='running',items=[],wb_writes=0,plan_sha256=p['plan_sha256']);assert io.create(key,e)
 def save():io.put(key,json.loads(json.dumps(e)))
 def req(path,method='GET',body=None):
  import requests
  time.sleep(1.5);r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':io.token},json=body,timeout=50)
  if not r.ok:raise RuntimeError('WB advertising HTTP '+str(r.status_code))
  return r.json() if r.content else {}
 def campaign(cid):
  j=req('/api/advert/v2/adverts?ids='+str(cid)).get('adverts',[])
  if len(j)!=1 or j[0]['id']!=cid or j[0].get('currency')!='CNY':raise ValueError('Campaign readback missing')
  return j[0]
 def budget(cid):
  j=req('/api/advert/v2/budget','POST',dict(advertIds=[cid])).get('adverts',[])
  if len(j)!=1 or j[0]['advertId']!=cid or j[0]['currency']!='CNY':raise ValueError('Budget readback missing')
  return j[0]['total']
 def verified(item,state):
  cid=item['campaign_id'];after=campaign(cid);state['after']=after;before=state['before'];kind=item['kind']
  if kind=='topup_campaign':
   b=budget(cid);state['after_budget']=b
   return after['settings']==before['settings'] and after['status']==9 and b>=state['before_budget']+item['amount_cny']-2
  if kind=='pause_campaign':return after['status']==11 and after['settings']==before['settings'] and after['nm_settings']==before['nm_settings']
  expected=copy.deepcopy(before['nm_settings'])
  if kind=='ad_exclude_sku':expected=[n for n in expected if n['nm_id']!=item['nm_id']]
  else:
   for n in expected:
    if n['nm_id']==item['nm_id']:n['bids_kopecks'][item['placement']]=item['target_minor']
  state['after']=after
  return after['status']==before['status'] and after['settings']==before['settings'] and sorted(after['nm_settings'],key=lambda n:n['nm_id'])==sorted(expected,key=lambda n:n['nm_id'])
 for item in p['items']:
  state=next((x for x in e['items'] if x['id']==item['id']),None)
  if state:
   if state['status'] in ['submitting','accepted','uncertain']:
    try:state['status']='verified' if verified(item,state) else 'uncertain'
    except Exception:state['status']='uncertain'
    save()
   continue
  state=dict(id=item['id'],status='preflight');e['items'].append(state);save()
  try:
   if datetime.now(timezone.utc)>datetime.fromisoformat(p['expires_at']):raise ValueError('Plan expired')
   cid=item['campaign_id'];before=campaign(cid);state['before']=before;save()
   if before['status']!=9:raise ValueError('Campaign no longer active')
   kind=item['kind'];method='PATCH'
   if kind in ['topup_campaign','pause_campaign'] and sorted(n['nm_id'] for n in before['nm_settings'])!=item['nm_ids']:raise ValueError('Campaign composition changed since PNG')
   if kind in ['ad_set_bid','ad_exclude_sku']:
    selected=next((n for n in before['nm_settings'] if n['nm_id']==item['nm_id']),None)
    if kind=='ad_exclude_sku' and selected is None:state.update(status='verified',already_done=True,after=before);save();continue
    if not selected or before['settings']['payment_type']!='cpc' or before['bid_type']!='manual':raise ValueError('Product/model changed')
    zone=item['placement'];old=selected['bids_kopecks'].get(zone)
    if kind=='ad_set_bid' and old==item['target_minor']:state.update(status='verified',already_done=True,after=before);save();continue
    if old!=item['old_minor']:raise ValueError('Bid changed since PNG')
    if kind=='ad_set_bid':
     if not 0<item['target_minor']<old:raise ValueError('Only exact approved bid reduction')
     typ='search' if zone=='search' else 'recommendation';j=req('/api/advert/v1/bids/min','POST',dict(advert_id=cid,nm_ids=[item['nm_id']],payment_type='cpc',placement_types=[typ]));v=[b['value'] for row in j.get('bids',[]) if row['nm_id']==item['nm_id'] for b in row['bids'] if b['type']==typ and b['currency']=='CNY']
     if len(v)!=1 or v[0]>item['target_minor']:raise ValueError('WB minimum changed')
     path='/api/advert/v1/bids';body=dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=item['nm_id'],bid_kopecks=item['target_minor'],placement=zone)])])
    else:
     if len(before['nm_settings'])<=1 or not before.get('restrictions',{}).get('can_change_nms'):raise ValueError('Exclusion would empty campaign or is not permitted')
     path='/adv/v0/auction/nms';body=dict(nms=[dict(advert_id=cid,nms=dict(add=[],delete=[item['nm_id']]))])
   elif kind=='pause_campaign':path='/adv/v0/pause?id='+str(cid);method='GET';body=None
   elif kind=='topup_campaign':
    b=budget(cid);state['before_budget']=b;state['after_budget']=b;save()
    if b>=item['target_balance']:state.update(status='verified',already_done=True,after=before);save();continue
    if b>item['balance_before']+2:raise ValueError('Budget was funded after PNG; refresh plan')
    cfg=req('/api/advert/v1/config')
    if cfg['currency']!='CNY' or cfg['minTopUp']>item['amount_cny']*100:raise ValueError('Minimum topup changed')
    bal=req('/adv/v1/balance');source=0 if bal.get('balance',0)>=item['amount_cny'] else 1 if bal.get('net',0)>=item['amount_cny'] else None
    if bal.get('currency')!='CNY' or source is None:raise ValueError('Insufficient available CNY funds')
    path='/adv/v1/budget/deposit?id='+str(cid);method='POST';body=dict(sum=item['amount_cny'],type=source)
   else:raise ValueError('Daily action kind not allowed')
   state.update(status='submitting',request=dict(path=path,method=method,body=body));save()
   response=req(path,method,body);state.update(status='accepted',response=response,submitted_at=datetime.now(timezone.utc).isoformat());e['wb_writes']+=1;save()
   for _ in range(20):
    if verified(item,state):state['status']='verified';break
    time.sleep(8)
   save()
  except Exception as ex:
   state.update(status='uncertain' if state['status']=='submitting' else state['status'] if state['status']=='accepted' else 'blocked',reason=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__);save()
 e['status']='done' if all(x['status'] in ['verified','blocked'] for x in e['items']) else 'attention';save()
 from china_execution_notice import deliver_result
 deliver_result(io,a,p,e)
 notice=io.get('china_agent:daily_ad_result:v2:'+p['plan_id'])
 if e['status']=='done' and notice and notice.get('status')=='sent':
  completed=dict(a,status='completed',result_status=e['status'],execution_key=key,result_message_id=notice.get('message_id'))
  io.put(APPROVAL+str(a['job_id']),completed)
 return e

def process_and_deliver(io,a,p):
 # execute always journals and delivers its own result, including direct recovery calls.
 return execute(io,a,p)

