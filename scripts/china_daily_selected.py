"""Exact selection of one action from a delivered daily list; no free-form WB access."""
import copy,re
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from china_loss_control import PLAN,APPROVAL,CHAT,BOT,digest,marker

def selected_command(text):
 m=re.fullmatch(r'\s*(?:выполни|сделай|выполнить)\s+только\s+(\d+)\s+(?:по\s+списку\s+)?(?:предложение|пункт)\s*[.!]?\s*(?:сумка\s+(\d+)\s*[.!]?)?\s*',text,re.I)
 return dict(index=int(m[1]),article_hint=m[2]) if m else None

def source(io,job):
 m=marker(job);sel=selected_command(job['request_text'])
 if not sel or m.get('bot_id')!=BOT or m.get('forwarded'):raise ValueError('Exact numbered selection required')
 delivery=io.get('china_agent:conversion_watch_delivery:v1:question:'+str(m.get('parent_job_id'))+':0')
 if not delivery or delivery.get('status')!='sent' or delivery.get('chat_id')!=CHAT or delivery.get('message_id')!=m.get('reply_message_id') or delivery.get('text')!=m.get('reply_text'):raise ValueError('Delivered source list missing')
 entries=re.findall(r'(?:^|\n)(\d+)\.\s+([^,\n]+),\s*РК\s+(\d+)',delivery['text'])
 if not entries or [int(x[0]) for x in entries]!=list(range(1,len(entries)+1)):raise ValueError('Ambiguous numbered list')
 day=datetime.fromisoformat(job['created_at'].replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()
 art=io.get('china_agent:advertising_artifacts:'+day+':v2') or {}
 matches=[]
 for file in art.get('files',[]):
  p=io.get(PLAN+file.get('plan_id',''))
  if not p or p.get('invalidated_at') or p.get('plan_sha256')!=digest(p['items']):continue
  if file.get('plan_sha256')!=p['plan_sha256']:continue
  if len(p['items'])!=len(entries):continue
  if [(x['article'],str(x['campaign_id'])) for x in p['items']]!=[(x[1],x[2]) for x in entries]:continue
  if datetime.fromisoformat(job['created_at'])<datetime.fromisoformat(p.get('visible_from') or p['created_at']):continue
  matches.append(p)
 if len(matches)!=1:raise ValueError('Current exact source plan missing')
 p=matches[0]
 if datetime.now(timezone.utc)>datetime.fromisoformat(p['expires_at']):raise ValueError('Source plan expired')
 if not 1<=sel['index']<=len(p['items']):raise ValueError('Selection outside list')
 item=p['items'][sel['index']-1]
 if sel['article_hint'] and item['article'].split('-')[0].lstrip('0')!=sel['article_hint'].lstrip('0'):raise ValueError('Number/article disagree')
 return p,item,sel

def prepare(io,job):
 parent,item,sel=source(io,job);pid=parent['plan_id']+'-selected-job'+str(job['id'])
 p=copy.deepcopy(parent);p.update(plan_id=pid,items=[copy.deepcopy(item)],plan_sha256=digest([item]),report_message_ids=[marker(job)['reply_message_id']],parent_plan_id=parent['plan_id'],parent_plan_sha256=parent['plan_sha256'],selected_index=sel['index'],selection_job_id=job['id'])
 old=io.get(PLAN+pid)
 if old and old!=p:raise ValueError('Selection changed')
 if not old and not io.create(PLAN+pid,p):raise ValueError('Selection race')
 a=dict(status='approved',execution_kind='daily_selected_v1',plan_id=pid,plan_sha256=p['plan_sha256'],job_id=job['id'],sender_id=job['sender_id'],update_id=job['update_id'],chat_id=CHAT,bot_id=BOT,input_message_id=marker(job)['message_id'],reply_message_id=marker(job)['reply_message_id'],created_at=job['created_at'],selection=sel,source_plan_id=parent['plan_id'],source_plan_sha256=parent['plan_sha256'],price_changes=False)
 old=io.get(APPROVAL+str(job['id']))
 if old and old!=a:raise ValueError('Approval changed')
 if not old and not io.create(APPROVAL+str(job['id']),a):raise ValueError('Approval race')
 return a,p

def validate(io,a,job):
 parent,item,sel=source(io,job);p=io.get(PLAN+a['plan_id'])
 return a.get('selection')==sel and a.get('source_plan_id')==parent['plan_id'] and a.get('source_plan_sha256')==parent['plan_sha256'] and p and p.get('parent_plan_sha256')==parent['plan_sha256'] and p['items']==[item] and p['plan_sha256']==digest([item])

def handle(io,job):
 if not selected_command(job.get('request_text','')):return None
 from china_group_permissions import allowed
 if not allowed(io,job):return ('Команда доступна действующим участникам группы.',[])
 try:a,p=prepare(io,job)
 except ValueError as e:return ('Не выполняю неоднозначный выбор: '+str(e)+'. Ответьте на действующий точный план.',[])
 item=p['items'][0]
 return ('Выбран только пункт '+str(p['selected_index'])+': '+item['article']+', РК '+str(item['campaign_id'])+'. Перед изменением проверю WB; остальные предложения не выполняю.',[dict(name='daily_ad_actions_approval',plan_id=p['plan_id'])])

