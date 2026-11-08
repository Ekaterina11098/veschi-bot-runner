"""Send the owner-requested proposal-preparation question once; no WB/model."""
import os,json,requests
from datetime import datetime,timezone
from china_codex_cloud import DB,CHAT,BOT
from china_ad_proposal_consent import ask,bind,QUESTION
KEY='china_agent:owner_pavel_proposal_question:2026-11-08:v1:263'
IDS=[1473243911,1473243915,1473243905,1473243901,1473245495]
class Adapter:
 def __init__(self,db):self.db=db;self.now=datetime.now(timezone.utc)
 def get(self,key):return self.db.get(key)
 def save(self,key,value,insert=False):
  if insert:self.db.once(key,value);return True
  return self.db.update(key,value)
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 db=DB();w=Adapter(db);prior=db.get(KEY)
 if prior:
  if prior.get('status')=='sent':bind(w,263,[prior['message_id']],prior['text'])
  print(json.dumps({'status':prior['status'],'message_id':prior.get('message_id')}));return
 rows=db.api('GET','business_agent_jobs',{'id':'eq.263','select':'id,chat_id,sender_id,request_text,tool_trace'})
 if len(rows)!=1 or rows[0].get('chat_id')!=CHAT or rows[0].get('sender_id')!=307200273:raise ValueError('Original Pavel question missing')
 job=rows[0];m=next((x for x in job.get('tool_trace',[])if x.get('name')=='china_saved_question'),{})
 if m.get('bot_id')!=BOT or m.get('message_id')!=754 or m.get('reply_message_id')!=737:raise ValueError('Original reply scope changed')
 text=ask(w,job,IDS)
 if len(text)>450:raise ValueError('Pavel short question required')
 token=os.environ['CHINA_TELEGRAM_BOT_TOKEN'];url='https://api.telegram.org/bot'+token+'/'
 r=requests.post(url+'getChatMember',json={'chat_id':CHAT,'user_id':307200273},timeout=30)
 if not r.ok:raise RuntimeError('Membership unavailable')
 result=r.json().get('result',{})
 if result.get('user',{}).get('id')!=307200273 or result.get('user',{}).get('is_bot')is not False or result.get('status')not in ('creator','administrator','member'):raise ValueError('Pavel membership changed')
 state={'status':'sending','job_id':263,'input_message_id':754,'chat_id':CHAT,'bot_id':BOT,'text':text,'created_at':datetime.now(timezone.utc).isoformat(),'wb_writes':0,'model_calls':0}
 db.once(KEY,state)
 try:
  r=requests.post(url+'sendMessage',json={'chat_id':CHAT,'text':text,'reply_parameters':{'message_id':754,'allow_sending_without_reply':False}},timeout=35)
  if not r.ok:raise RuntimeError('Telegram HTTP '+str(r.status_code))
  value=r.json();receipt=value.get('result',{})
  if value.get('ok')is not True or receipt.get('chat',{}).get('id')!=CHAT or receipt.get('from',{}).get('id')!=BOT or type(receipt.get('message_id'))is not int:raise ValueError('Receipt scope mismatch')
  state.update(status='sent',message_id=receipt['message_id'],receipt=receipt);db.update(KEY,state,'sending')
 except Exception as exc:
  db.update(KEY,state|{'status':'uncertain','error_type':type(exc).__name__},'sending');raise RuntimeError('Delivery uncertain; never repeat blindly')from None
 bind(w,263,[receipt['message_id']],text)
 print(json.dumps({'status':'sent','message_id':receipt['message_id'],'question_key':QUESTION+'263'}))
if __name__=='__main__':main()
