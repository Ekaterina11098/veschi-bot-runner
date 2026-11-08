"""Owner-requested calculated bag proposal for actual Pavel270. No WB mutations."""
from datetime import datetime,timezone
from china_loss_execute import IO
from china_new_ad_reports import process_requests,source
from china_ad_retest import assess
from collections import Counter
from china_loss_control import PLAN
from china_new_ads import REQUEST
io=IO()
rows=io.db('business_agent_jobs?id=eq.270&agent_id=eq.china&chat_id=eq.-1004342917488&select=id,chat_id,sender_id,request_text')
if len(rows)!=1 or rows[0]['sender_id']!=307200273 or 'Не хочу запускать зонты давай сумки' not in rows[0]['request_text']:
 raise ValueError('Original Pavel category change not verified')
key=REQUEST+'270'
old=io.get(key)
if old and old.get('revision')!='brief-v2':
 archive=key+':archive:before-owner-brief-v2'
 if not io.get(archive):io.create(archive,old)
 old_plan=io.get(PLAN+old.get('plan_id',''))
 if old_plan:
  io.put(PLAN+old['plan_id'],dict(old_plan,status='superseded',invalidated_at=datetime.now(timezone.utc).isoformat(),superseded_reason='Owner requested concise grouped PNG and maximum qualified candidates'))
 io.put(key,dict(old,status='pending',maximum_count=50,revision='brief-v2',owner_restyle_source='Owner Codex8Nov: as many as possible; concise PNG like our regular tables'))
if not io.get(key):
 io.create(key,dict(status='pending',job_id=270,chat_id=-1004342917488,sender_id=307200273,reply_message_id=779,request_text=rows[0]['request_text'],created_at=datetime.now(timezone.utc).isoformat(),nm_ids=[],subject_ids=[50],maximum_count=20,source_question_job_id=270,grants_action_permission=False,owner_recovery='Owner Codex8Nov: fix calculated concrete proposals'))
s=source(io)
bags=dict(s,products=[p for p in s['products']if p.get('subject_id')==50])
assessed=assess(bags,manual_review=True)
counts=Counter(reason for r in assessed for reason in r['requires_review'])
audit=dict(source_products=len(s['products']),bag_products=len(bags['products']),positive_model_assessed=len(assessed),qualified=sum(r['eligible']for r in assessed),reasons=dict(counts),no_forced_quantity=True,requested_maximum=50,observed_at=s['observed_at'],wb_writes=0)
auditkey='china_agent:proposal_scope_audit:v1:270:brief-v2'
if not io.get(auditkey):io.create(auditkey,audit)
process_requests(io,job_id=270)
p=io.get(key)or{}
print({'job_id':270,'status':p.get('status'),'plan_id':p.get('plan_id'),'wb_writes':0})
if p.get('status')not in ('done','reviewed'):raise RuntimeError('Concrete preparation incomplete')
