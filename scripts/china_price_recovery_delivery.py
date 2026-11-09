"""Owner 9Nov: deliver corrected price proposals, never execute prices."""
import hashlib,json,uuid
from datetime import datetime,timedelta,timezone
from china_agent.morning_pair import PairWorker
from china_cloud_cost_control import Cache,stamp
from china_price_delivery import deliver,rows

ROOT='china_agent:owner_price_delivery_recovery:2026-11-09:v1'
c=Cache()
old=c.get('china_agent:price_delivery:v2:2026-11-09:morning') or {}
if old.get('status')!='sent' or old.get('message_ids')!=[817]:
    if c.get(ROOT+':delivery'):print(json.dumps(dict(status='already_delivered',wb_writes=0)));raise SystemExit()
    raise RuntimeError('Original empty-report receipt changed')
preview=c.get('china_agent:morning_pair:2026-11-09:candidates:verify') or {}
answer=preview.get('preview','');offers=rows(answer)
expected=['046-NoelBag-blue','55-NoelBag-green','56-NoelBag-cream','594-NoelBag-green','Zont01-fio']
if preview.get('status')!='preview_verified' or [r[1] for r in offers]!=expected:raise RuntimeError('Reviewed five-item preview changed')
if preview.get('assessment',{}).get('period_to')!='2026-11-08':raise RuntimeError('Completed-day source changed')
original=c.get('china_agent:price_delivery:v2:2026-11-09:morning:prepared') or {}
if original.get('selection_count')!=0:raise RuntimeError('Cannot replace actionable prior report')
w=PairWorker('candidates')
if str(w.day)!='2026-11-09':raise RuntimeError('Dated recovery expired')
w.mode='morning-recovery1';w.update_id=-98320261109;w.chat=-1004342917488
cfg=w.db('GET','business_agent_config',params=dict(agent_id='eq.china',active='eq.true',limit=2)) or []
if len(cfg)!=1 or cfg[0].get('chat_id')!=w.chat or cfg[0].get('owner_user_id')!=5122667182:raise RuntimeError('Recipient mismatch')
jobs=w.db('GET','business_agent_jobs',params=dict(agent_id='eq.china',update_id='eq.'+str(w.update_id),limit=2)) or []
if jobs:raise RuntimeError('Existing recovery job; inspect receipts before replay')
lease=str(uuid.uuid4())
created=w.db('POST','business_agent_jobs',body=dict(agent_id='china',update_id=w.update_id,chat_id=w.chat,sender_id=5122667182,request_text=w.command,status='running',attempts=1,lease_token=lease,lease_until=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat(),answer=answer,tool_trace=[dict(name='china_price_daily_report',report_date=str(w.day),source_key='china_agent:morning_pair:2026-11-09:candidates:verify',replaces_empty_message_id=817,execution_authorized=False)]),prefer='return=representation') or []
if len(created)!=1:raise RuntimeError('Recovery report identity unavailable')
w.job=created[0]
deliver(w)
key='china_agent:price_delivery:v2:2026-11-09:morning-recovery1'
receipt=c.get(key)
if receipt.get('status')!='sent' or not receipt.get('message_ids'):raise RuntimeError('Delivery unconfirmed')
c.put(ROOT+':delivery',dict(receipt,source_key=key,replaced_empty_message_id=817,execution_authorized=False))
c.put('china_agent:price_delivery:v2:2026-11-09:morning',dict(receipt,source_key=key,replaced_empty_message_id=817))
binding=c.get('china_agent:price_report_message:v1:817')
c.put('china_agent:price_report_message:v1:817',dict(binding,status='replaced_empty_report',replacement_message_ids=receipt['message_ids']))
print(json.dumps(dict(status='sent',message_ids=receipt['message_ids'],job_id=w.job['id'],wb_writes=0)))

