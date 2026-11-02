"""Opt-in exact-thread pilot. No WB tools or model calls; existing TG transport only."""
import re,uuid
from datetime import datetime,timedelta,timezone

ROOT='china_agent:codex_bridge:v1:'
THREAD='01a14b40-d7b4-76b1-a8eb-9bc1eea36335'
CHAT=-1004342917488
BOT=8780468043
def stamp():return datetime.now(timezone.utc).isoformat()
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
  patch(dict(status='pending',lease_until=None,retry_at=(now+timedelta(minutes=1)).isoformat(),error=None));return 'codex_bridge_queued'
 if (out.get('status') not in ('ready','delivered') or out.get('thread_id')!=THREAD or out.get('chat_id')!=CHAT or out.get('input_message_id')!=marker['message_id'] or out.get('job_id')!=job['id'] or not isinstance(out.get('answer'),str) or not 0<len(out['answer'])<=3500):
  patch(dict(status='failed',lease_until=None,error='codex_bridge_invalid_reply'));return 'codex_bridge_invalid_reply'
 w.active_question_id=job['id'];w.reply_id=marker['message_id']
 outcome=w.send_once('codex_bridge:'+str(job['id'])+':0',CHAT,out['answer'])
 receipt=w.get('china_agent:conversion_watch_delivery:v1:codex_bridge:'+str(job['id'])+':0') or {}
 if outcome=='sent' and receipt.get('status')=='sent' and receipt.get('message_id'):
  w.save(ROOT+'outbox:'+str(job['id']),out|dict(status='delivered',message_id=receipt['message_id'],delivered_at=stamp(),receipt_key='china_agent:conversion_watch_delivery:v1:codex_bridge:'+str(job['id'])+':0'))
  w.save(key,inbox|dict(status='delivered',message_id=receipt['message_id'],delivered_at=stamp()))
  patch(dict(status='done',answer=out['answer'],lease_until=None,error=None,completed_at=stamp()));return 'codex_bridge_delivered'
 patch(dict(status='pending' if outcome in ('waiting','rejected') else 'failed',lease_until=None,error='codex_bridge_delivery_'+outcome,retry_at=(now+timedelta(minutes=5)).isoformat()))
 return 'codex_bridge_delivery_'+outcome
