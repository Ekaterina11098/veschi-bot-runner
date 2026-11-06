"""Opt-in exact-thread pilot. No WB tools or model calls; existing TG transport only."""
import re,uuid
from datetime import datetime,timedelta,timezone

ROOT='china_agent:codex_bridge:v1:'
THREAD='01a14b40-d7b4-76b1-a8eb-9bc1eea36335'
CHAT=-1004342917488
BOT=8780468043
def stamp():return datetime.now(timezone.utc).isoformat()
def prepare_analytics(w,job,inbox):
 req=w.get(ROOT+'data_request:'+str(job['id'])) or {}
 if not req or req.get('status')!='requested':return
 if req.get('job_id')!=job['id'] or req.get('thread_id')!=THREAD or req.get('chat_id')!=CHAT or req.get('kind')not in ('preliminary_profit','read'):raise ValueError('Unapproved bridge read scope')
 from datetime import date
 day=date.fromisoformat(req.get('day_msk') or req.get('date_to'))
 from zoneinfo import ZoneInfo
 today=datetime.now(ZoneInfo('Europe/Moscow')).date()
 if req.get('kind')=='preliminary_profit' and not 0<=(today-day).days<=14:raise ValueError('Bridge forecast date outside scope')
 try:
  if req.get('kind')=='read':
   from china_codex_read_broker import collect as collect_read
   result=collect_read(w,job,req)
   value=dict(status='calculated',kind='read',job_id=job['id'],thread_id=THREAD,chat_id=CHAT,result=result,read_round=req.get('read_round'),created_at=stamp(),wb_writes=0,telegram_sends=0)
   w.save(ROOT+'analytics:'+str(job['id']),value)
   w.save(ROOT+'data_request:'+str(job['id']),req|dict(status='complete',completed_at=stamp()))
   w.save(ROOT+'inbox:'+str(job['id']),inbox|dict(status='queued',analytics_key=ROOT+'analytics:'+str(job['id'])))
   return
  from china_profit_forecast import collect,calculate
  state,key=collect(w,job,day)
  result=calculate(state,w.get('china_agent:new_ad_economics_policy:v1') or {},w.get('china_agent:expected_profit_delivery_model:v1') or {},day)
  # Keep the same historical reverse-logistics allowance used in owner forecasts.
  own={int(p['nm_id']):p for p in state['inputs'].get('own_products',{}).get('rows',[])};reverse=0.;missing=0
  fx=float(state['inputs']['fx']['rub_per_cny'])
  for row in result.get('details',[]):
   p=own.get(row['nm_id'],{});n=p.get('finished_orders');v=p.get('backwardlogisticsum')
   if n and type(v) in (int,float):reverse+=v/n/fx
   else:missing+=1
  result['totals']['model_reverse_logistics_cny']=reverse
  if result['totals'].get('forecast_profit_cny') is not None:
   result['totals']['forecast_profit_cny']-=reverse;result['totals']['forecast_profit_rub']=result['totals']['forecast_profit_cny']*fx
  result['missing_reverse_model_orders']=missing
  value=dict(status='calculated',job_id=job['id'],thread_id=THREAD,chat_id=CHAT,source_key=key,result=result,read_round=req.get('read_round'),created_at=stamp(),wb_writes=0,telegram_sends=0)
 except Exception as e:value=dict(status='failed',job_id=job['id'],thread_id=THREAD,chat_id=CHAT,error=type(e).__name__,read_round=req.get('read_round'),created_at=stamp(),wb_writes=0,telegram_sends=0)
 w.save(ROOT+'analytics:'+str(job['id']),value)
 w.save(ROOT+'data_request:'+str(job['id']),req|dict(status='complete' if value['status']=='calculated' else 'failed',completed_at=stamp()))
 w.save(ROOT+'inbox:'+str(job['id']),inbox|dict(status='queued',analytics_key=ROOT+'analytics:'+str(job['id'])))
def question(text):
 m=re.match(r'^(?:/codex(?:@[A-Za-z0-9_]+)?(?:\s+|$)|Кодекс\s*[,,:]\s*)([\s\S]*)$',text or '',re.I)
 return m.group(1).strip() if m else None

def handle(w,job,cfg):
 text=question(job.get('request_text'))
 marker=next((x for x in job.get('tool_trace') or [] if x.get('name')=='china_saved_question'),{})
 if marker.get('codex_bridge') is True:text=marker.get('bridge_request_text') or text or job.get('request_text','')
 if text is None:return None
 p=w.get(ROOT+'policy') or {}
 if not p.get('enabled'):return None
 # Prefix remains exclusively reserved during the enabled pilot, even for rejected senders.
 if p.get('thread_id')!=THREAD or p.get('chat_id')!=CHAT or p.get('bot_id')!=BOT:raise ValueError('Codex bridge scope mismatch')
 if job.get('chat_id')!=CHAT or cfg.get('chat_id')!=CHAT or marker.get('bot_id')!=BOT:return 'codex_bridge_scope_rejected'
 if job.get('sender_id') not in p.get('allowed_sender_ids',[]):return 'codex_bridge_sender_rejected'
 now=datetime.now(timezone.utc)
 if now>=datetime.fromisoformat(p['expires_at']):return 'codex_bridge_expired'
 if not text or len(text)>4000:return 'codex_bridge_empty_or_long'
 # Claim the original job, so the old analyst can never race this delivery.
 lease=str(uuid.uuid4())
 filters={'id':'eq.'+str(job['id']),'status':'eq.'+job['status']}
 if job['status']=='running':filters['lease_until']='eq.'+job['lease_until']
 changed=w.db('PATCH','business_agent_jobs',params=filters,body=dict(status='running',lease_token=lease,lease_until=(now+timedelta(minutes=3)).isoformat()),prefer='return=representation') or []
 if not changed:return 'codex_bridge_claim_lost'
 def patch(body):
  if not w.db('PATCH','business_agent_jobs',params={'id':'eq.'+str(job['id']),'lease_token':'eq.'+lease},body=body,prefer='return=representation'):raise RuntimeError('Codex bridge lease lost')
 key=ROOT+'inbox:'+str(job['id'])
 inbox=w.get(key)
 if not inbox:
  inbox=dict(status='queued',job_id=job['id'],update_id=job.get('update_id'),chat_id=CHAT,bot_id=BOT,sender_id=job['sender_id'],input_message_id=marker['message_id'],thread_id=THREAD,request_text=text,created_at=stamp(),origin='telegram',pilot=True,wb_action_permission=False)
  w.save(key,inbox)
 out=w.get(ROOT+'outbox:'+str(job['id'])) or {}
 if not out:
  from china_no_paid import enabled,safe_answer
  if enabled(w):
   answer=safe_answer(w,dict(job,request_text=text))
   out=dict(status='ready',job_id=job['id'],chat_id=CHAT,input_message_id=inbox['input_message_id'],thread_id=THREAD,
            answer=answer,created_at=stamp(),source_channel='deterministic_no_paid',paid_model_calls=0,wb_action_permission=False)
   w.save(ROOT+'outbox:'+str(job['id']),out)
   w.save(key,inbox|dict(status='answered',source_channel='deterministic_no_paid'))
 if not out:
  prepare_analytics(w,job,inbox)
  patch(dict(status='pending',lease_until=None,retry_at=(now+timedelta(minutes=1)).isoformat(),error=None));return 'codex_bridge_queued'
 if (out.get('status') not in ('ready','delivered') or out.get('thread_id')!=THREAD or out.get('chat_id')!=CHAT or out.get('input_message_id')!=marker['message_id'] or out.get('job_id')!=job['id'] or not isinstance(out.get('answer'),str) or not 0<len(out['answer'])<=12000):
  patch(dict(status='failed',lease_until=None,error='codex_bridge_invalid_reply'));return 'codex_bridge_invalid_reply'
 w.active_question_id=job['id'];w.reply_id=marker['message_id']
 from china_table_png import delivery_parts
 from conversion_watches import split_message
 parts=delivery_parts(w,job,out['answer'],split_message)
 message_ids=[];outcome='sent'
 for index,part in enumerate(parts):
  delivery_key='codex_bridge:'+str(job['id'])+':'+str(index)
  outcome=w.send_once(delivery_key,CHAT,part)
  receipt=w.get('china_agent:conversion_watch_delivery:v1:'+delivery_key) or {}
  if outcome!='sent' or receipt.get('status')!='sent' or not receipt.get('message_id'):
   if outcome=='sent':outcome='uncertain'
   break
  message_ids.append(receipt['message_id'])
 if outcome=='sent' and len(message_ids)==len(parts) and message_ids:
  w.save(ROOT+'outbox:'+str(job['id']),out|dict(status='delivered',message_id=message_ids[0],message_ids=message_ids,delivered_at=stamp(),receipt_key='china_agent:conversion_watch_delivery:v1:codex_bridge:'+str(job['id'])+':0',parts_count=len(parts)))
  w.save(key,inbox|dict(status='delivered',message_id=message_ids[0],message_ids=message_ids,delivered_at=stamp()))
  patch(dict(status='done',answer=out['answer'],lease_until=None,error=None,completed_at=stamp()));return 'codex_bridge_delivered'
 patch(dict(status='pending' if outcome in ('waiting','rejected') else 'failed',lease_until=None,error='codex_bridge_delivery_'+outcome,retry_at=(now+timedelta(minutes=5)).isoformat()))
 return 'codex_bridge_delivery_'+outcome
