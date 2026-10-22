"""Recover only the actual two owner replies to delivered recommendations107."""
import json
from datetime import datetime,timezone
from china_price_apply import IO
from china_loss_control import *
io=IO()
r=io.get('china_agent:loss_new_recommendations_send:2026-10-22:v1')
p=io.get(PLAN+'loss-20261022-107')
if not r or r.get('status')!='delivered' or r.get('message_id')!=107 or r.get('sha256')!=p.get('png_sha256'):raise ValueError('Receipt mismatch')
if digest(p['items'])!=p['plan_sha256']:raise ValueError('Plan changed')
old=io.get(LATEST)
if old and old.get('plan_id') not in ['loss-20261022-102',p['plan_id']]:raise ValueError('Newer plan exists')
latest=dict(plan_id=p['plan_id'],reply_ids=[107],status='active')
if old:io.put(LATEST,latest)
else:io.create(LATEST,latest)
jobs=io.db('business_agent_jobs?id=in.(67,68)&agent_id=eq.china&chat_id=eq.'+str(CHAT)+'&sender_id=eq.'+str(OWNER)+'&select=*')
if len(jobs)!=2 or any(marker(j).get('reply_message_id')!=107 or not is_all(j['request_text']) for j in jobs):raise ValueError('Original replies unavailable')
j=min(jobs,key=lambda x:x['id'])
class W:
 now=datetime.now(timezone.utc)
 get=staticmethod(io.get)
 def save(self,k,v,insert=False):return io.create(k,v) if insert else io.put(k,v)
answer,trace=handle(W(),j)
if not io.get(APPROVAL+str(j['id'])):raise ValueError('Approval not recovered')
io.create('china_agent:loss_plan_duplicate:v1:68',dict(canonical_job_id=67,report_message_id=107,execution_repeated=False))
print(json.dumps(dict(status='recovered',job_id=j['id'],plan_id=p['plan_id'],wb_writes=0)))
