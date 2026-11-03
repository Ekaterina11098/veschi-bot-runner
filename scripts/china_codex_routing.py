"""Cloud-only analysis routing, retaining only exact human-bound execution acknowledgements."""
import copy
from china_codex_analysis import POLICY
from china_codex_cloud import CHAT,THREAD,BOT,SENDERS
BINDINGS=('china_agent:daily_ad_message:v2:','china_agent:advertising_dialog_message:v1:','china_agent:new_ad_message:v1:','china_agent:loss_message:v1:')
def cloud_only(w):
 p=w.get(POLICY)or{}
 return p.get('status')=='active' and p.get('legacy_analysis_enabled')is False
def bound_execution(w,job):
 from china_loss_control import is_all,marker
 from china_advertising_plans import bid_confirmation
 from china_daily_selected import selected_command
 text=job.get('request_text','')
 if not is_all(text) and not bid_confirmation(text) and not selected_command(text):return False
 m=marker(job)
 if m.get('bot_id')!=BOT or m.get('forwarded')or not m.get('reply_message_id'):return False
 if selected_command(text) and m.get('parent_job_id'):
  receipt=w.get('china_agent:conversion_watch_delivery:v1:question:'+str(m['parent_job_id'])+':0')or{}
  if receipt.get('status')=='sent' and receipt.get('chat_id')==CHAT and receipt.get('message_id')==m['reply_message_id']:return True
 return any((w.get(k+str(m['reply_message_id']))or{}).get('chat_id')==CHAT for k in BINDINGS)
def execute_acknowledgement(w,job):
 if not bound_execution(w,job):raise ValueError('No exact current human-bound execution plan')
 from china_daily_ad_actions import handle as daily
 from china_advertising_plans import handle as ads
 for handler in (daily,ads):
  answer=handler(w,job)
  if answer is not None:return answer
 from china_new_ads import handle as new
 value=new(w,job,[])
 if value is not None:return value
 from china_loss_control import handle as loss
 value=loss(w,job)
 if value is not None:return value
 return ('Для этой команды нет подтверждённого актуального плана. Изменения не выполнены.',[])
def promote(w,job):
 if job.get('chat_id')!=CHAT or job.get('sender_id')not in SENDERS:raise PermissionError('Cloud question sender outside configured scope')
 original=job.get('request_text','');text=original
 if text.startswith('/codex '):text=text[7:].strip()
 m=next((copy.deepcopy(x)for x in job.get('tool_trace',[])if x.get('name')=='china_saved_question'),None)
 if not m or m.get('bot_id')!=BOT:raise ValueError('Original Telegram marker missing')
 m.update(codex_bridge=True,codex_thread_id=THREAD,bridge_request_text=text,original_request_text=original,migrated_from_legacy=True)
 traces=[m]+[x for x in job.get('tool_trace',[])if x.get('name')!='china_saved_question']
 filters={'id':'eq.'+str(job['id']),'agent_id':'eq.china','chat_id':'eq.'+str(CHAT),'status':'eq.'+job['status']}
 if job['status']=='running':filters['lease_until']='eq.'+job['lease_until']
 rows=w.db('PATCH','business_agent_jobs',params=filters,body=dict(request_text='/codex '+text,tool_trace=traces),prefer='return=representation')or[]
 if len(rows)!=1:raise RuntimeError('Cloud routing claim lost')
 return rows[0]
