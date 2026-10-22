"""Isolated post-dialog executor. Never receives arbitrary URLs or request bodies."""
import argparse,base64,json,os,time
from datetime import datetime,timezone
from urllib.parse import quote
from china_price_apply import IO as BaseIO
from china_loss_control import *

class IO(BaseIO):
 def request(self,path,body):
  import requests
  r=requests.post('https://content-api.wildberries.ru'+path,headers={'Authorization':self.token},json=body,timeout=40)
  if not r.ok:raise RuntimeError('Content HTTP '+str(r.status_code))
  data=r.json()
  if data.get('error'):raise RuntimeError('Content rejected')
  return data
 def card(self,nm):
  j=self.request('/content/v2/get/cards/list',{'settings':{'cursor':{'limit':100},'filter':{'textSearch':str(nm),'withPhoto':-1}}})
  cs=[c for c in j.get('cards',[]) if c.get('nmID')==nm]
  if len(cs)!=1:raise ValueError('Exact card missing')
  return cs[0]
 def update_card(self,c):return self.request('/content/v2/cards/update',[c])
 def validate_owner(self,a):
  if a['sender_id']!=OWNER or a['chat_id']!=CHAT or a['bot_id']!=BOT:raise ValueError('Owner mismatch')
  cfg=self.db('business_agent_config?agent_id=eq.china&select=active,chat_id,bot_id,owner_user_id')
  if len(cfg)!=1 or cfg[0]!=dict(active=True,chat_id=CHAT,bot_id=BOT,owner_user_id=OWNER):raise ValueError('Registration changed')
  j=self.db('business_agent_jobs?id=eq.'+str(a['job_id'])+'&agent_id=eq.china&select=id,request_text,sender_id,chat_id,tool_trace')
  if len(j)!=1 or j[0]['sender_id']!=OWNER or j[0]['chat_id']!=CHAT or not is_all(j[0]['request_text']):raise ValueError('Original command missing')
  if marker(j[0]).get('reply_message_id')!=a['reply_message_id']:raise ValueError('Reply changed')
  member=self.tg('getChatMember',dict(chat_id=CHAT,user_id=OWNER))
  if member.get('user',{}).get('id')!=OWNER or member.get('status') not in ['creator','administrator','member']:raise ValueError('Owner left')
  try:
   token=self.token.split('.')[1];claims=json.loads(base64.urlsafe_b64decode(token+'='*(-len(token)%4)))
  except Exception:raise ValueError('WB token not verified')
  if claims.get('t') is not False or claims.get('exp',0)<=time.time() or int(claims.get('s',0))&(1<<30):raise ValueError('Read-only/expired token')
  rows=self.db('analytics_snapshots?cabinet=eq.token_3&source=eq.seller_identity&status=eq.complete&select=payload&limit=100')
  sids={r['payload'].get('sid') for r in rows}
  if len(sids)!=1 or claims.get('sid') not in sids:raise ValueError('WB seller scope unknown')

def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 io=IO();rows=io.db('telegram_api_cache?cache_key=like.'+quote(APPROVAL+'*',safe='')+'&select=payload&limit=100')
 if len(rows)>=100:raise RuntimeError('Approval pagination incomplete')
 for row in rows:
  a=row['payload']
  if a.get('status')!='approved':continue
  p=io.get(PLAN+a['plan_id'])
  if not p:continue
  # Expiration gates new writes; an existing execution may only recover readback.
  if datetime.now(timezone.utc)>datetime.fromisoformat(p['expires_at']) and not io.get(EXEC+str(a['job_id'])):continue
  e=process(io,a);body=summary(e);delivery='china_agent:loss_plan_delivery:v1:'+str(a['job_id'])+':'+digest(body)
  if io.get(delivery):continue
  if not io.create(delivery,dict(status='sending',text=body)):continue
  try:
   r=io.tg('sendMessage',dict(chat_id=CHAT,text=body,reply_parameters={'message_id':a['input_message_id'],'allow_sending_without_reply':True}))
   io.put(delivery,dict(status='sent',text=body,message_id=r['message_id'],chat_id=CHAT))
   latest=io.get(LATEST)
   if latest and latest['plan_id']==a['plan_id']:
    latest['reply_ids']=list(set(latest.get('reply_ids',[])+[r['message_id']]))
    io.put(LATEST,latest)
  except Exception:io.put(delivery,dict(status='uncertain',text=body,chat_id=CHAT))
  print(json.dumps(dict(plan_id=a['plan_id'],status=e['status'],items=[dict(id=x['id'],status=x['status']) for x in e['items']]),ensure_ascii=False))
if __name__=='__main__':run()
