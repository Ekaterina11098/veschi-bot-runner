"""Recover only Pavel266 preparation consent; calculate proposal, never execute WB."""
import os,json
from datetime import datetime,timezone
from china_loss_execute import IO
from china_ad_proposal_consent import handle
from china_free_ads import confirmation_text
from china_new_ad_reports import process_requests
CHAT=-1004342917488;BOT=8780468043
KEY='china_agent:owner_prepare_recovery:2026-11-08:v1:266'
class Adapter:
 def __init__(self,io):self.io=io;self.now=datetime.now(timezone.utc)
 def get(self,k):return self.io.get(k)
 def save(self,k,v,insert=False):
  if insert:return self.io.create(k,v)
  self.io.put(k,v);return True
 def member_check(self,actor):return self.io.tg('getChatMember',{'chat_id':CHAT,'user_id':actor})
 def config(self):
  rows=self.io.db('business_agent_config?agent_id=eq.china&select=active,chat_id,bot_id,owner_user_id')
  if len(rows)!=1 or rows[0].get('active')is not True or rows[0].get('chat_id')!=CHAT or rows[0].get('bot_id')!=BOT:raise ValueError('Active scope mismatch')
  return rows[0]
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 io=IO();w=Adapter(io)
 rows=io.db('business_agent_jobs?id=eq.266&agent_id=eq.china&select=id,chat_id,sender_id,request_text,tool_trace,created_at,update_id')
 if len(rows)!=1 or rows[0].get('sender_id')!=307200273 or rows[0].get('chat_id')!=CHAT:raise ValueError('Exact Pavel job missing')
 job=rows[0];m=next((x for x in job.get('tool_trace',[])if x.get('name')=='china_saved_question'),{})
 if m.get('bot_id')!=BOT or m.get('message_id')!=766 or m.get('reply_message_id')!=765:raise ValueError('Reply scope mismatch')
 job=dict(job,request_text=confirmation_text(job));answer=handle(w,job)
 req=io.get('china_agent:new_ad_report_request:v1:266')or{}
 if req.get('maximum_count')!=20 or req.get('nm_ids')!=[] or req.get('source_question_job_id')!=263 or req.get('grants_action_permission')is not False:raise ValueError('Scoped preparation not accepted')
 if not io.get(KEY):
  state=dict(status='sending',job_id=266,chat_id=CHAT,bot_id=BOT,text=answer,wb_writes=0,model_calls=0)
  if not io.create(KEY,state):raise ValueError('Reply claim lost')
  try:
   r=io.tg('sendMessage',dict(chat_id=CHAT,text=answer,reply_parameters=dict(message_id=766,allow_sending_without_reply=False)))
   if r.get('chat',{}).get('id')!=CHAT or r.get('from',{}).get('id')!=BOT or type(r.get('message_id'))is not int:raise ValueError('Receipt mismatch')
   state.update(status='sent',message_id=r['message_id'],receipt=r);io.put(KEY,state)
   rk='china_agent:owner_dialog_resolution:v1:job:266'
   if not io.get(rk):io.create(rk,dict(status='answered_by_owner',chat_id=CHAT,message_id=r['message_id'],receipt_key=KEY,answer=answer))
  except Exception:
   io.put(KEY,state|{'status':'uncertain'});raise RuntimeError('Delivery uncertain; no blind repeat')from None
 process_requests(io,job_id=266)
 result=io.get('china_agent:new_ad_report_request:v1:266')or{}
 print(json.dumps({'job_id':266,'status':result.get('status'),'plan_id':result.get('plan_id'),'reason':result.get('reason'),'wb_writes':0,'model_calls':0},ensure_ascii=False))
if __name__=='__main__':main()
