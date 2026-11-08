"""Deterministic selection of bid changes from an exact delivered daily PNG."""
import copy,re
from datetime import datetime,timezone
from china_loss_control import CHAT,BOT,PLAN,APPROVAL,digest,marker
BIND='china_agent:daily_ad_message:v2:'

def command(text):
 text=re.sub(r'^/codex\s+','',text.strip(),flags=re.I)
 return bool(re.fullmatch(r'(?:не\s+исключай\s+из\s+рекламы[.!]?\s*)?(?:повысь|повышай|подними)\s+и\s+(?:понизь|понижай|снизь)\s+ставки[.!]?',text,re.I))

def source(io,job):
 m=marker(job)
 if not command(job.get('request_text','')) or job.get('chat_id')!=CHAT or m.get('bot_id')!=BOT or m.get('forwarded'):raise ValueError('Exact human bid command required')
 b=io.get(BIND+str(m.get('reply_message_id')))or{}
 p=io.get(PLAN+b.get('plan_id',''))or{}
 if p.get('execution_kind')!='daily_ad_actions_v2' or p.get('family')!='drr' or p.get('chat_id')!=CHAT or b.get('chat_id')!=CHAT:raise ValueError('Delivered daily plan missing')
 if p.get('invalidated_at') or p.get('status') in ('revoked','invalidated'):raise ValueError('Plan revoked')
 if digest(p.get('items',[]))!=p.get('plan_sha256') or b.get('plan_sha256')!=p['plan_sha256'] or m.get('reply_message_id')not in p.get('report_message_ids',[]):raise ValueError('Plan binding changed')
 at=datetime.fromisoformat(job['created_at'].replace('Z','+00:00'))
 if at<datetime.fromisoformat(p.get('visible_from')or p['created_at']) or datetime.now(timezone.utc)>datetime.fromisoformat(p['expires_at']):raise ValueError('Plan expired or command predates publication')
 items=[copy.deepcopy(i)for i in p['items'] if i.get('kind')=='ad_set_bid' and type(i.get('old_minor'))is int and type(i.get('target_minor'))is int and i['old_minor']!=i['target_minor']]
 if not items:raise ValueError('No bid changes in this PNG')
 return p,items

def prepare(io,job):
 parent,items=source(io,job);m=marker(job);pid=parent['plan_id']+'-bids-job'+str(job['id'])
 p=copy.deepcopy(parent);p.update(plan_id=pid,items=items,plan_sha256=digest(items),parent_plan_id=parent['plan_id'],parent_plan_sha256=parent['plan_sha256'],selection_kind='bid_changes_only',selection_job_id=job['id'])
 a=dict(status='approved',execution_kind='daily_bid_selection_v1',plan_id=pid,plan_sha256=p['plan_sha256'],job_id=job['id'],update_id=job['update_id'],sender_id=job['sender_id'],chat_id=CHAT,bot_id=BOT,input_message_id=m['message_id'],reply_message_id=m['reply_message_id'],created_at=job['created_at'],source_plan_id=parent['plan_id'],source_plan_sha256=parent['plan_sha256'],price_changes=False)
 for k,v in ((PLAN+pid,p),(APPROVAL+str(job['id']),a)):
  old=io.get(k)
  if old:
   if any(old.get(f)!=v.get(f)for f in ('plan_id','plan_sha256','source_plan_sha256','parent_plan_sha256','items') if f in v):raise ValueError('Selection changed')
  elif not io.save(k,v,insert=True):raise ValueError('Selection claim lost')
 return a,p

def validate(io,a,job):
 parent,items=source(io,job);p=io.get(PLAN+a['plan_id'])or{}
 return (a.get('source_plan_id')==parent['plan_id'] and a.get('source_plan_sha256')==parent['plan_sha256'] and p.get('parent_plan_sha256')==parent['plan_sha256'] and p.get('items')==items and p.get('plan_sha256')==a.get('plan_sha256')==digest(items))

def handle(io,job):
 if not command(job.get('request_text','')):return None
 from china_group_permissions import allowed
 if not allowed(io,job):return ('Команда доступна действующим участникам группы.',[])
 try:a,p=prepare(io,job)
 except ValueError:return ('Не удалось подтвердить актуальный план ставок. Нужен свежий PNG; исключения и другие действия не выполнялись.',[])
 return ('Принято '+str(len(p['items']))+' изменений ставок из этого PNG. Исключения не выполняю. Результат сообщу после проверки WB.',[dict(name='daily_ad_actions_approval',plan_id=p['plan_id'])])

