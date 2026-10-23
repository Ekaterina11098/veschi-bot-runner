"""Reply-bound new China campaigns. Reports never authorize marketplace writes."""
import base64,copy,hashlib,json,re,time
from datetime import datetime,timedelta,timezone
from urllib.parse import quote
from china_loss_control import CHAT,BOT,PLAN,APPROVAL,digest,is_all,marker

BIND='china_agent:new_ad_message:v1:'
EXEC='china_agent:new_ad_execution:v1:'
REQUEST='china_agent:new_ad_report_request:v1:'
LATEST='china_agent:new_ad_report_latest:v1'

def now():return datetime.now(timezone.utc)

def validate_plan(p):
 if p.get('execution_kind')!='ad_create_campaigns' or p.get('chat_id')!=CHAT or p.get('bot_id')!=BOT or p.get('price_changes') is not False:raise ValueError('Wrong new-campaign plan scope')
 items=p.get('items',[])
 if p.get('plan_sha256')!=digest(items) or len(items)!=2:raise ValueError('Plan hash/count mismatch')
 ids=[]
 for c in items:
  if c.get('kind')!='ad_create_campaign' or c.get('payment_type')!='cpc' or c.get('bid_type')!='manual' or c.get('placements')!=['recommendations']:raise ValueError('Unsupported campaign settings')
  if c.get('group') not in ['orders','demand'] or not c.get('name') or len(c['name'])>100:raise ValueError('Invalid campaign identity')
  if type(c.get('budget_cny')) is not int or not 0<c['budget_cny']<=1000 or c.get('daily_limit_minor')!=c['budget_cny']*100 or c.get('carry_over_enabled') is not False or c.get('auto_topup') is not False:raise ValueError('Invalid budget controls')
  if not 1<=len(c.get('skus',[]))<=50:raise ValueError('Invalid SKU count')
  for s in c['skus']:
   if type(s.get('nm_id')) is not int or s['nm_id']<=0 or not s.get('article') or type(s.get('bid_minor')) is not int or s['bid_minor']<=0:raise ValueError('Invalid SKU/bid')
   ids.append(s['nm_id'])
 if len(set(ids))!=len(ids) or {c['group'] for c in items}!={'orders','demand'}:raise ValueError('Duplicate SKU/group')
 return items

def handle(w,job,history=()):
 m=marker(job);binding=w.get(BIND+str(m.get('reply_message_id')))
 if binding:
  if not is_all(job.get('request_text','')):return None
  from china_group_permissions import allowed
  if not allowed(w,job) or m.get('bot_id')!=BOT or m.get('forwarded'):return ('Подтвердить этот план может действующий участник группы, ответом на исходный PNG.',[])
  p=w.get(PLAN+binding['plan_id']);validate_plan(p or {})
  if binding.get('plan_sha256')!=p['plan_sha256'] or binding.get('chat_id')!=CHAT or m['reply_message_id'] not in p.get('report_message_ids',[]):raise ValueError('Wrong PNG binding')
  if w.now>datetime.fromisoformat(p['expires_at']):return ('Срок плана истёк. Запросите новый рекламный тест: проверю данные и пришлю новый PNG для подтверждения.',[])
  at=datetime.fromisoformat(job['created_at'].replace('Z','+00:00'))
  if not datetime.fromisoformat(p['created_at'])<=at<=datetime.fromisoformat(p['expires_at']):return ('Подтверждение вне срока этого плана; нужен свежий PNG.',[])
  accepted='china_agent:new_ad_accept:v1:'+p['plan_id']
  prior=w.get(accepted)
  if prior:
   w.save(APPROVAL+str(prior['job_id']),prior,insert=True)
   return ('Этот план уже подтверждён. Проверю исполнение; повторных РК и пополнений не будет.',[dict(name='new_ad_already_approved',plan_id=p['plan_id'])])
  a=dict(status='approved',plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],job_id=job['id'],update_id=job['update_id'],sender_id=job['sender_id'],chat_id=CHAT,bot_id=BOT,input_message_id=m.get('message_id'),reply_message_id=m['reply_message_id'],created_at=job['created_at'],price_changes=False)
  if not w.save(accepted,a,insert=True):return ('План уже принят другим подтверждением; дубли не создаю.',[])
  w.save(APPROVAL+str(job['id']),a,insert=True)
  return ('Принято: создам две РК по '+str(sum(c['budget_cny'] for c in p['items']))+' ¥ суммарно, проверю ставки и лимиты, затем запущу. Повторная команда не создаст дубли. Цены не меняю.',[dict(name='new_ad_campaigns_approval',plan_id=p['plan_id'])])
 text=job.get('request_text','')
 if not ((re.search(r'реклам\w*\s+тест|тест\w*\s+реклам|кандидат\w*\s+(?:для|в|на)\s+реклам',text,re.I) or re.search(r'реклам',text,re.I) and re.search(r'без\s+(?:РК|реклам)|провер\w*\s+спрос|кандидат',text,re.I)) and re.search(r'подбер|подоб|предлож|подготов|сделай|покаж|отч[её]т|пришли|найди',text,re.I)):return None
 from china_group_permissions import allowed
 if not allowed(w,job):return ('Подготовить план может действующий участник группы.',[])
 w.save(REQUEST+str(job['id']),dict(status='pending',job_id=job['id'],chat_id=CHAT,sender_id=job['sender_id'],reply_message_id=m.get('message_id'),request_text=text,created_at=w.now.isoformat()),insert=True)
 return ('Соберу кандидатов по спросу, выкупу, экономике и доступному остатку МойСклад. Пришлю PNG с отдельными РК для товаров с заказами и проверки спроса. Без подтверждения ничего не запускаю.',[dict(name='new_ad_report_requested',job_id=job['id'],wb_writes=0)])

class Transport:
 def __init__(self,io):self.io=io
 def request(self,path,method='GET',body=None):
  import requests
  reads={'/api/advert/v1/config','/api/advert/v2/adverts','/api/advert/v0/daily-limits','/adv/v1/promotion/count'}
  posts={'/api/advert/v1/bids/min','/api/advert/v2/budget','/adv/v2/seacat/save-ad','/adv/v1/budget/deposit'}
  if not ((method=='GET' and path.split('?')[0] in reads|{'/adv/v0/start'}) or (method=='POST' and path.split('?')[0] in posts) or (method=='PUT' and path=='/api/advert/v0/daily-limits') or (method=='PATCH' and path=='/api/advert/v1/bids')):raise ValueError('Endpoint outside new-campaign scope')
  time.sleep(1.3)
  r=requests.request(method,'https://advert-api.wildberries.ru'+path,headers={'Authorization':self.io.token},json=body,timeout=45)
  if not r.ok:raise RuntimeError('WB advertising HTTP '+str(r.status_code))
  return r.json() if r.content else {}
 def config(self):return self.request('/api/advert/v1/config')
 def preflight(self,items,owned):
  from china_loss_ads import current
  selected={s['nm_id']:s for c in items for s in c['skus']}
  prices=self.io.prices([str(n) for n in selected])
  for nm,s in selected.items():
   p=prices.get(str(nm),{})
   if p.get('vendorCode')!=s['article'] or p.get('currencyIsoCode4217')!='CNY':raise ValueError('SKU identity/currency changed')
  for cid,c in current(self.io).items():
   if cid not in owned and selected.keys() & {n['nm_id'] for n in c.get('nm_settings',[])}:raise ValueError('Candidate already in an unrelated active campaign')
  import requests,os
  headers={'Authorization':'Bearer '+os.environ['MOYSKLAD_API_TOKEN']};base='https://api.moysklad.ru/api/remap/1.2'
  r=requests.get(base+'/entity/store',headers=headers,params={'limit':1000},timeout=45)
  if not r.ok:raise RuntimeError('MoySklad warehouse unavailable')
  stores=[s for s in r.json().get('rows',[]) if s.get('name')=='МСК' and not s.get('archived')]
  if len(stores)!=1:raise ValueError('MoySklad warehouse not unique')
  r=requests.get(base+'/report/stock/all',headers=headers,params={'filter':'store='+stores[0]['meta']['href'],'stockMode':'all','limit':1000},timeout=60)
  if not r.ok:raise RuntimeError('MoySklad stock unavailable')
  j=r.json();rows=j.get('rows',[])
  if j.get('meta',{}).get('size',len(rows))>len(rows):raise ValueError('MoySklad stock pagination required')
  for s in selected.values():
   match=[r for r in rows if str(r.get('article','')).casefold()==s['article'].casefold()]
   if len(match)!=1 or match[0].get('stock') is None or match[0].get('reserve') is None or match[0]['stock']-match[0]['reserve']<=0:raise ValueError('No confirmed available MoySklad stock for '+s['article'])
 def campaign(self,cid):
  rows=self.request('/api/advert/v2/adverts?ids='+str(cid)).get('adverts',[])
  if len(rows)!=1 or rows[0].get('id')!=cid:raise ValueError('Exact campaign missing')
  return rows[0]
 def minima(self,cid,ids):
  j=self.request('/api/advert/v1/bids/min','POST',dict(advert_id=cid,nm_ids=ids,payment_type='cpc',placement_types=['recommendation']));out={}
  for row in j.get('bids',[]):
   bids=[x for x in row.get('bids',[]) if x.get('type')=='recommendation' and x.get('currency')=='CNY']
   if len(bids)!=1:raise ValueError('Bid minimum ambiguous')
   out[row['nm_id']]=bids[0]['value']
  if set(out)!=set(ids):raise ValueError('Bid minima incomplete')
  return out
 def budget(self,cid):
  rows=self.request('/api/advert/v2/budget','POST',dict(advertIds=[cid])).get('adverts',[])
  if len(rows)!=1 or rows[0].get('advertId')!=cid or rows[0].get('currency')!='CNY':raise ValueError('Budget readback missing/currency')
  return rows[0]['total']
 def limit(self,cid):
  rows=self.request('/api/advert/v0/daily-limits?advertIds='+str(cid)).get('adverts',[])
  if len(rows)!=1 or rows[0].get('advertId')!=cid:raise ValueError('Daily limit readback missing')
  return rows[0]

def check_campaign(c,spec,ready=True,bids=False):
 if c.get('currency')!='CNY' or c.get('bid_type')!='manual' or c.get('settings',{}).get('payment_type')!='cpc':raise ValueError('Campaign currency/model mismatch')
 if c.get('settings',{}).get('placements')!={'search':False,'recommendations':True}:raise ValueError('Campaign placements mismatch')
 if ready and c.get('status')!=4:raise ValueError('New campaign is not an unlaunched draft')
 if c.get('settings',{}).get('name')!=spec['name']:raise ValueError('Campaign name mismatch')
 settings=c.get('nm_settings',[])
 if {x['nm_id'] for x in settings}!={x['nm_id'] for x in spec['skus']}:raise ValueError('Campaign membership mismatch')
 if bids:
  wanted={s['nm_id']:s['bid_minor'] for s in spec['skus']}
  if any(n.get('bids_kopecks',{}).get('recommendations')!=wanted[n['nm_id']] for n in settings):raise ValueError('Bid readback mismatch')

def check_limit(row,spec):
 if row.get('currency')!='CNY' or row.get('enabled') is not True or row.get('carryOverEnabled') is not False or row.get('dailyLimit')!=spec['daily_limit_minor'] or row.get('valid') is False:raise ValueError('Daily limit not confirmed or below required minimum')

def execute(io,a,p,t=None):
 specs=validate_plan(p);io.validate_owner(a)
 if a.get('plan_sha256')!=p['plan_sha256'] or a.get('plan_id')!=p['plan_id']:raise ValueError('Approval hash mismatch')
 binding=io.get(BIND+str(a['reply_message_id']))
 if not binding or binding.get('plan_id')!=p['plan_id'] or binding.get('plan_sha256')!=p['plan_sha256'] or binding.get('chat_id')!=CHAT:raise ValueError('Original PNG binding missing')
 key=EXEC+p['plan_id'];e=io.get(key)
 if e and e.get('status') in ('done','blocked','uncertain'):return e
 if not e:
  if now()>datetime.fromisoformat(p['expires_at']):raise ValueError('Plan expired')
  e=dict(status='running',plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],campaigns=[],wb_writes=0,created_at=now().isoformat())
  if not io.create(key,e):return io.get(key)
 t=t or Transport(io)
 def save():io.put(key,e)
 def write(state,step,path,method,body=None):
  prior=state.setdefault('steps',{}).get(step)
  if prior:
   if prior['status']=='verified':return prior.get('response')
   raise ValueError('Uncertain prior '+step+'; write will not be repeated')
  if now()>datetime.fromisoformat(p['expires_at']):raise ValueError('Plan expired before write')
  state['steps'][step]=dict(status='submitting',path=path,method=method,body=body);save()
  try:response=t.request(path,method,body)
  except Exception:
   state['steps'][step]['status']='uncertain';e['status']='uncertain';save();raise
  e['wb_writes']+=1;state['steps'][step].update(status='verified',response=response);save();return response
 try:
  cfg=t.config()
  t.preflight(specs,{s['campaign_id'] for s in e['campaigns'] if s.get('campaign_id')})
  if cfg.get('currency')!='CNY':raise ValueError('Wrong cabinet currency')
  for spec in specs:
   if cfg.get('minTopUp',10**12)>spec['budget_cny']*100 or cfg.get('minDailyLimit',10**12)>spec['daily_limit_minor']:raise ValueError('WB minimum budget increased; new approval required')
   step=cfg.get('cpcStep')
   if type(step) is not int or step<=0 or any(s['bid_minor']%step or s['bid_minor']>cfg.get('cpcMaxBid',10**12) for s in spec['skus']):raise ValueError('Bid step/maximum changed')
  # Build and verify BOTH drafts before funding either, and BOTH budgets before starting either.
  for spec in specs:
   state=next((x for x in e['campaigns'] if x['group']==spec['group']),None)
   if not state:state=dict(group=spec['group'],status='preflight',steps={});e['campaigns'].append(state);save()
   if 'campaign_id' not in state:
    response=write(state,'create','/adv/v2/seacat/save-ad','POST',dict(name=spec['name'],nms=[s['nm_id'] for s in spec['skus']],bid_type='manual',payment_type='cpc',placement_types=['recommendations']))
    cid=response if type(response) is int else response.get('advertId') if isinstance(response,dict) else None
    if type(cid) is not int or cid<=0:raise ValueError('Creation receipt has no campaign ID; do not repeat')
    state['campaign_id']=cid;save()
   cid=state['campaign_id'];c=t.campaign(cid)
   if state.get('status')=='launched' or state['steps'].get('start'):
    check_campaign(c,spec,ready=False,bids=True)
    if c.get('status')!=9:e['status']='readback_pending';save();return e
    state['status']='launched';save()
    continue
   check_campaign(c,spec)
   minima=t.minima(cid,[s['nm_id'] for s in spec['skus']])
   if any(type(minima[s['nm_id']]) is not int or minima[s['nm_id']]>s['bid_minor'] for s in spec['skus']):raise ValueError('Minimum bid above approved bid; no launch')
   write(state,'bids','/api/advert/v1/bids','PATCH',dict(bids=[dict(advert_id=cid,nm_bids=[dict(nm_id=s['nm_id'],bid_kopecks=s['bid_minor'],placement='recommendations') for s in spec['skus']])]))
   check_campaign(t.campaign(cid),spec,bids=True)
   write(state,'limit','/api/advert/v0/daily-limits','PUT',dict(advertIds=[cid],enabled=True,dailyLimit=spec['daily_limit_minor'],carryOverEnabled=False))
   check_limit(t.limit(cid),spec);state['status']='draft_verified';save()
  for spec in specs:
   state=next(s for s in e['campaigns'] if s['group']==spec['group']);cid=state['campaign_id']
   if state.get('status')=='launched':continue
   if not state['steps'].get('deposit'):
    if t.budget(cid)!=0:raise ValueError('Draft already funded; no duplicate deposit')
    write(state,'deposit','/adv/v1/budget/deposit?id='+str(cid),'POST',dict(sum=spec['budget_cny'],type=0))
   if t.budget(cid)!=spec['budget_cny']:raise ValueError('Budget readback differs from approved amount')
   check_limit(t.limit(cid),spec);state['status']='funded_verified';save()
  for spec in specs:
   state=next(s for s in e['campaigns'] if s['group']==spec['group']);cid=state['campaign_id']
   if state.get('status')=='launched':continue
   c=t.campaign(cid)
   if state['steps'].get('start'):
    # Accepted start can be stale in WB cache; recovery only reads, never repeats GET start.
    if c.get('status')!=9:e['status']='readback_pending';save();return e
   else:
    check_campaign(c,spec,bids=True);check_limit(t.limit(cid),spec)
    if t.budget(cid)!=spec['budget_cny']:raise ValueError('Budget changed before start')
    write(state,'start','/adv/v0/start?id='+str(cid),'GET');c=t.campaign(cid)
   check_campaign(c,spec,ready=False,bids=True)
   if c.get('status')!=9:e['status']='readback_pending';save();return e
   state.update(status='launched',verified_at=now().isoformat());save()
  e.update(status='done',completed_at=now().isoformat());save()
  tracking=io.get('china_agent:new_ad_tests:tracking:v1') or dict(plans={})
  tracking['plans'][p['plan_id']]=dict(campaign_ids=[s['campaign_id'] for s in e['campaigns']],items=copy.deepcopy(specs),started_at=e['completed_at'],budget_cny=sum(s['budget_cny'] for s in specs),status='active',existing_reports=True)
  io.put('china_agent:new_ad_tests:tracking:v1',tracking) if io.get('china_agent:new_ad_tests:tracking:v1') else io.create('china_agent:new_ad_tests:tracking:v1',tracking)
 except Exception as ex:
  e.update(status='uncertain' if e.get('status')=='uncertain' else 'blocked',reason=str(ex) if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__);save()
 return e

def deliver(io,p,blob):
 validate_plan(p)
 sha=hashlib.sha256(blob).hexdigest()
 if p.get('png_sha256')!=sha:raise ValueError('PNG hash mismatch')
 key='china_agent:new_ad_delivery:v1:'+p['plan_id'];state=io.get(key)
 if state and state.get('status') in ('sent','sending','uncertain'):return state
 if io.tg('getMe',{}).get('id')!=BOT:raise ValueError('Wrong bot')
 if io.tg('getChat',dict(chat_id=CHAT)).get('id')!=CHAT:raise ValueError('Wrong chat')
 if not state:
  state=dict(status='ready',plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],png_sha256=sha,chat_id=CHAT)
  if not io.create(key,state):return io.get(key)
 state['status']='sending';io.put(key,state)
 try:
  import requests
  caption='Две новые РК · '+str(sum(c['budget_cny'] for c in p['items']))+' ¥ всего. Пока не запущены. Ответьте на этот PNG «делай», «согласен», «подтверждаю» или «сделай всё», чтобы запустить весь указанный план.'
  j=requests.post('https://api.telegram.org/bot'+io.bot+'/sendPhoto',data=dict(chat_id=CHAT,caption=caption),files={'photo':('china-ad-test.png',blob,'image/png')},timeout=45).json()
  if not j.get('ok') or j['result'].get('chat',{}).get('id')!=CHAT:raise RuntimeError('Telegram receipt missing')
  mid=j['result']['message_id']
  state.update(status='sent',message_id=mid,delivered_at=now().isoformat());io.put(key,state)
  p['report_message_ids']=sorted(set(p.get('report_message_ids',[])+[mid]));io.put(PLAN+p['plan_id'],p)
  if not io.create(BIND+str(mid),dict(plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],chat_id=CHAT,png_sha256=sha)):raise ValueError('PNG binding already exists')
 except Exception:
  if state.get('status')!='sent':state['status']='uncertain';io.put(key,state)
  raise
 return state

def process_and_deliver(io,a,p):
 e=execute(io,a,p)
 if e['status']=='readback_pending':return e
 key='china_agent:new_ad_result:v1:'+p['plan_id'];prior=io.get(key)
 if prior and prior.get('status') in ('sent','sending','uncertain'):return e
 text='Результат запуска рекламного теста:\n'+'\n'.join('РК '+str(s.get('campaign_id','не создана'))+' · '+s['group']+' · '+('запущена, проверено WB' if s['status']=='launched' else s['status']) for s in e['campaigns'])
 if e.get('reason'):text+='\nНе завершено: '+e['reason']
 if not io.create(key,dict(status='sending',text=text)):return e
 try:
  r=io.tg('sendMessage',dict(chat_id=CHAT,text=text,reply_parameters=dict(message_id=a['input_message_id'],allow_sending_without_reply=True)))
  io.put(key,dict(status='sent',text=text,message_id=r['message_id']))
 except Exception:io.put(key,dict(status='uncertain',text=text))
 return e

