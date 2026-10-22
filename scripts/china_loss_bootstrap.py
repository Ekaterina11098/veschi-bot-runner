"""Register only the exact owner approved PNG102 and recover genuine TG job66.
No writes to WB; no replay of the generic question or price queues.
"""
import json,os
from china_price_apply import IO
from china_loss_control import *
from china_loss_policy import POLICY
def run():
 io=IO();receipt=io.get('china_agent:loss_actions_send:2026-10-22:v1')
 if not receipt or receipt.get('status')!='delivered' or receipt.get('message_id')!=102 or receipt.get('chat_id')!=CHAT:raise ValueError('PNG receipt missing')
 if receipt.get('sha256')!='56ff96f0e58af5e069374fc785d690b0279affec61cdf3c1284ae1879cf01770':raise ValueError('PNG changed')
 p=io.get(PLAN+'loss-20261022-102')
 if not p or p.get('plan_sha256')!=digest(p['items']):raise ValueError('Private plan missing or changed')
 if not io.create(PLAN+p['plan_id'],p):
  if io.get(PLAN+p['plan_id'])!=p:raise ValueError('Existing plan differs')
 latest=dict(plan_id=p['plan_id'],reply_ids=[102]);old=io.get(LATEST)
 if old and old['plan_id']!=p['plan_id']:raise ValueError('Newer plan exists')
 if not old:io.create(LATEST,latest)
 policy=dict(version='2026-10-22',scope='token_3',algorithm=POLICY,prices_frozen=True)
 if not io.create('china_agent:loss_policy:2026-10-22:v1',policy):pass
 jobs=io.db('business_agent_jobs?id=eq.66&agent_id=eq.china&chat_id=eq.'+str(CHAT)+'&sender_id=eq.'+str(OWNER)+'&select=*')
 if len(jobs)!=1:raise ValueError('Command missing')
 j=jobs[0]
 if j['update_id']!=532552690 or marker(j).get('reply_message_id')!=102 or j['request_text']!='сделай все':raise ValueError('Command scope changed')
 class W:
  now=datetime.now(timezone.utc)
  get=staticmethod(io.get)
  def save(self,k,v,insert=False):return io.create(k,v) if insert else io.put(k,v)
 answer,trace=handle(W(),j)
 if not io.get(APPROVAL+'66'):raise ValueError('Approval recovery failed')
 # Retain original answer; mark it excluded from conversational history.
 if not any(t.get('name')=='china_loss_answer_invalid' for t in j.get('tool_trace',[])):
  io.db('business_agent_jobs?id=eq.66','PATCH',dict(tool_trace=j['tool_trace']+[dict(name='china_loss_answer_invalid',reason='wrong119_context_and_unknown_expenses_zero',deleted_message_id=104),*trace]))
 print(json.dumps(dict(status='registered',plan_id=p['plan_id'],recovered_job=66,ready_card_items=3,wb_writes=0,telegram_calls=0)))
if __name__=='__main__':run()
