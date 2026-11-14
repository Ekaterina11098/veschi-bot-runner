"""Exact report selection transport and shared execution claims. No marketplace writes."""
import copy,hashlib,json,inspect
from urllib.parse import quote
from datetime import datetime,timezone
from china_loss_control import PLAN,APPROVAL,CHAT,BOT,digest,marker
ROOT='china_agent:report_buttons:v1:'
GATE='china_agent:daily_action_claim:v1:'
GROUPS=[('up','Повысить ставки'),('add','Добавить товары'),('down','Снизить ставки'),('exclude','Исключить товары'),('archive','Завершить РК'),('pause','Приостановить РК'),('recover','Снизить ставки, пополнить и запустить РК')]
def category(i):
 k=i['kind']
 if k=='recover_campaign'and i.get('selection_family')=='budgets':return 'budget'
 if k=='ad_set_bid':return 'up'if i['target_minor']>i['old_minor']else'down'
 return {'ad_add_sku':'add','ad_exclude_sku':'exclude','archive_campaign':'archive','topup_campaign':'budget','pause_campaign':'pause','recover_campaign':'recover'}.get(k)
def domain(items):return sorted({'budgets'if category(i)=='budget'else'drr'for i in items})
def create(io,k,v):
 return io.save(k,v,insert=True)if hasattr(io,'save')else io.create(k,v)
def put(io,k,v):
 return io.save(k,v)if hasattr(io,'save')else io.put(k,v)
def claim(io,parent,domains,owner):
 """One atomic shared gate serializes text and callbacks, separately for ads/budgets."""
 key=GATE+parent
 for _ in range(4):
  old=io.get(key)
  if old is None:
   if not create(io,key,dict(domains={})):continue
   old=io.get(key)
  occupied=old.get('domains',{})
  if any(k in occupied and occupied[k]!=owner for k in domains):raise ValueError('Эта часть плана уже подтверждена. Повторное исполнение закрыто.')
  new=copy.deepcopy(old);new.setdefault('domains',{}).update({k:owner for k in domains})
  if new==old:return
  if 'params'in inspect.signature(io.db).parameters:
   rows=io.db('PATCH','telegram_api_cache',params={'cache_key':'eq.'+key,'payload':'eq.'+json.dumps(old,separators=(',',':'))},body={'payload':new},prefer='return=representation')
  else:
   rows=io.db('telegram_api_cache?cache_key=eq.'+quote(key,safe='')+'&payload=eq.'+quote(json.dumps(old,separators=(',',':')),safe=''),'PATCH',{'payload':new},'return=representation')
  if rows:return
 raise ValueError('Одновременное подтверждение. Откройте выбор ещё раз.')
def prepare(io,p,family):
 if not(io.get(ROOT+'policy')or{}).get('enabled'):return None
 if p.get('invalidated_at')or p.get('owner_budget_resolution')or not p.get('items'):return None
 items=[i for i in p['items']if category(i)and ('budgets'if category(i)=='budget'else'drr')==family]
 if not items:return None
 token=hashlib.sha256((p['plan_id']+':'+p['plan_sha256']+':'+family).encode()).hexdigest()[:24]
 value=dict(status='active',chat_id=CHAT,bot_id=BOT,plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],family=family,expires_at=p['expires_at'],report_generation=p.get('report_generation'),items=[dict(id=i['id'],index=n,group=category(i),article=i.get('article',''),campaign_id=i['campaign_id'],amount_cny=i.get('amount_cny',0))for n,i in enumerate(items)])
 key=ROOT+'plan:'+token;old=io.get(key)
 if old and old!=value:raise ValueError('Frozen report button identity changed')
 if not old and not create(io,key,value):raise ValueError('Concurrent button preparation')
 prefix='cab1:'+token+':'
 if family=='budgets':
  rows=[[dict(text='[ ] РК '+str(i['campaign_id'])+' · +'+str(i['amount_cny'])+' CNY',callback_data=prefix+'i'+str(n))]for n,i in enumerate(items[:6])]
  if len(items)>6:rows.append([dict(text='Следующие РК ›',callback_data=prefix+'p1')])
 else:rows=[[dict(text='[ ] '+label+' · '+str(sum(category(i)==g for i in items)),callback_data=prefix+'g'+g)]for g,label in GROUPS if any(category(i)==g for i in items)]
 rows.extend([[dict(text='Выбрать всё',callback_data=prefix+'all'),dict(text='Сбросить',callback_data=prefix+'clear')],[dict(text='Посмотреть выбранное',callback_data=prefix+'review')]])
 rows.append([dict(text='‹ Главное меню',callback_data='cmn1:home')])
 return dict(inline_keyboard=rows)
def bind(io,f,receipt):
 if not(io.get(ROOT+'policy')or{}).get('enabled'):return
 p=io.get(PLAN+f['plan_id']);family=f.get('family',p['family']);keyboard=prepare(io,p,family)
 if not keyboard:return
 token=keyboard['inline_keyboard'][0][0]['callback_data'].split(':')[1]
 k=ROOT+'message:'+str(receipt['message_id'])
 value=dict(status='sent',token=token,plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],family=family,chat_id=CHAT,bot_id=BOT,message_id=receipt['message_id'],receipt=receipt)
 old=io.get(k)
 if old and old!=value:raise ValueError('Report button binding changed')
 if not old and not create(io,k,value):raise ValueError('Concurrent button binding')
def validate(io,a,job):
 m=marker(job);c=io.get(ROOT+'confirmation:'+m.get('report_button_confirmation',''))or{}
 parent=io.get(PLAN+c.get('plan_id',''))or{}
 from china_daily_report_validity import valid
 return bool(c.get('status')=='confirmed'and c.get('job_id')==job['id']and c.get('sender_id')==job['sender_id']and c.get('chat_id')==CHAT and c.get('report_message_id')==m.get('reply_message_id')and c.get('plan_sha256')==parent.get('plan_sha256')and parent.get('items')and digest(parent['items'])==parent['plan_sha256']and valid(io,parent)and a.get('button_confirmation')==m.get('report_button_confirmation')and a.get('result_message_id')==c.get('review_message_id')and a.get('parent_plan_id')==parent['plan_id']and a.get('selected_ids')==c.get('selected_ids'))
def handle(io,job):
 m=marker(job);token=m.get('report_button_confirmation')
 if not token:return None
 c=io.get(ROOT+'confirmation:'+token)or{}
 parent=io.get(PLAN+c.get('plan_id',''))or{}
 pid=parent.get('plan_id','')+'-buttons-'+token
 selected=set(c.get('selected_ids',[]));items=[copy.deepcopy(i)for i in parent.get('items',[])if i['id']in selected]
 if not items or len(items)!=len(selected):raise ValueError('Confirmed selection missing')
 a=dict(status='approved',execution_kind='daily_buttons_v1',plan_id=pid,plan_sha256=digest(items),job_id=job['id'],sender_id=job['sender_id'],update_id=job['update_id'],chat_id=CHAT,bot_id=BOT,input_message_id=m['message_id'],reply_message_id=m['reply_message_id'],created_at=job['created_at'],price_changes=False,button_confirmation=token,parent_plan_id=parent['plan_id'],selected_ids=c['selected_ids'],result_message_id=c['review_message_id'])
 if not validate(io,a,job):raise ValueError('Callback confirmation no longer valid')
 claim(io,parent['plan_id'],domain(items),'button:'+token)
 p=copy.deepcopy(parent);p.update(plan_id=pid,items=items,plan_sha256=digest(items),parent_plan_id=parent['plan_id'],parent_plan_sha256=parent['plan_sha256'],button_confirmation=token)
 for k,v in [(PLAN+pid,p),(APPROVAL+str(job['id']),a)]:
  old=io.get(k)
  if old and (old.get('plan_sha256')!=v['plan_sha256']or old.get('plan_id')!=v['plan_id']):raise ValueError('Button selection changed')
  if not old and not create(io,k,v):raise ValueError('Concurrent confirmed selection')
 return ('Выбранные действия подтверждены.',[dict(name='daily_ad_actions_approval',plan_id=pid)])
def execution_claim(io,a,p):
 if not a.get('button_confirmation')and not(io.get(ROOT+'policy')or{}).get('enabled'):return
 parent=p.get('parent_plan_id')or p['plan_id']
 owner='button:'+a['button_confirmation']if a.get('button_confirmation')else'job:'+str(a['job_id'])
 claim(io,parent,domain(p['items']),owner)


