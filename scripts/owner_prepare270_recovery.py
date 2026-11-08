"""Owner-requested calculated bag proposal for actual Pavel270. No WB mutations."""
from datetime import datetime,timezone
from china_loss_execute import IO
from china_new_ad_reports import process_requests
from china_new_ads import REQUEST
io=IO()
rows=io.db('business_agent_jobs?id=eq.270&agent_id=eq.china&chat_id=eq.-1004342917488&select=id,chat_id,sender_id,request_text')
if len(rows)!=1 or rows[0]['sender_id']!=307200273 or 'Не хочу запускать зонты давай сумки' not in rows[0]['request_text']:
 raise ValueError('Original Pavel category change not verified')
key=REQUEST+'270'
if not io.get(key):
 io.create(key,dict(status='pending',job_id=270,chat_id=-1004342917488,sender_id=307200273,reply_message_id=779,request_text=rows[0]['request_text'],created_at=datetime.now(timezone.utc).isoformat(),nm_ids=[],subject_ids=[50],maximum_count=20,source_question_job_id=270,grants_action_permission=False,owner_recovery='Owner Codex8Nov: fix calculated concrete proposals'))
process_requests(io,job_id=270)
p=io.get(key)or{}
print({'job_id':270,'status':p.get('status'),'plan_id':p.get('plan_id'),'wb_writes':0})
if p.get('status')not in ('done','reviewed'):raise RuntimeError('Concrete preparation incomplete')
