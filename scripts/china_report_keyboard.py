"""Attach existing selection-only controls to a verified, bound Telegram report."""
import os,re
from datetime import datetime,timezone
from urllib.parse import urlparse
TARGET=None
def allowed_transport(method,url,body):
 u=urlparse(url);bot=os.environ.get('CHINA_TELEGRAM_BOT_TOKEN','').strip()
 return bool(TARGET and bot and method.upper()=='POST'and u.scheme=='https'and u.hostname=='api.telegram.org'and u.path=='/bot'+bot+'/editMessageReplyMarkup'and isinstance(body,dict)and set(body)=={'chat_id','message_id','reply_markup'}and(body['chat_id'],body['message_id'])==TARGET)
def attach(w,p,mid,send=None):
 from china_loss_control import CHAT,BOT,digest
 from china_report_buttons import prepare,bind,ROOT
 if not(w.get(ROOT+'policy')or{}).get('enabled'):return None
 if type(mid)is not int or mid not in p.get('report_message_ids',[])or p.get('chat_id')!=CHAT or p.get('bot_id')!=BOT or digest(p['items'])!=p['plan_sha256']:raise ValueError('Report keyboard scope mismatch')
 if p.get('status')in('revoked','invalidated')or p.get('invalidated_at')or datetime.fromisoformat(p['expires_at'])<=datetime.now(timezone.utc):raise ValueError('Report keyboard plan expired or revoked')
 key=ROOT+'keyboard:'+str(mid);old=w.get(key)
 if old:
  if old.get('status')=='attached'and old.get('plan_sha256')==p['plan_sha256']:return old
  raise ValueError('Existing keyboard delivery requires reconciliation')
 keyboard=prepare(w,p,'drr')
 if not keyboard:return None
 if any(not re.fullmatch(r'cab1:[a-f0-9]{24}:[a-z0-9]+',b.get('callback_data',''))for row in keyboard['inline_keyboard']for b in row):raise ValueError('Unexpected report callback')
 record=dict(status='submitting',plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],message_id=mid,chat_id=CHAT,observed_at=datetime.now(timezone.utc).isoformat(),wb_writes=0)
 if not w.save(key,record,insert=True):raise ValueError('Concurrent keyboard attachment')
 if send is None:
  import requests
  send=requests.post
 global TARGET
 previous=TARGET;TARGET=(CHAT,mid)
 try:
  response=send('https://api.telegram.org/bot'+os.environ['CHINA_TELEGRAM_BOT_TOKEN'].strip()+'/editMessageReplyMarkup',json=dict(chat_id=CHAT,message_id=mid,reply_markup=keyboard),timeout=35)
  body=response.json();message=body.get('result')
  if response.status_code!=200 or body.get('ok')is not True or not isinstance(message,dict)or message.get('message_id')!=mid or message.get('chat',{}).get('id')!=CHAT or message.get('reply_markup')!=keyboard:raise ValueError('Telegram report keyboard readback mismatch')
  receipt={k:message[k]for k in ('message_id','chat','date')if k in message}
  bind(w,dict(plan_id=p['plan_id'],family='drr'),receipt)
  record.update(status='attached',keyboard=keyboard,receipt=receipt);w.save(key,record);return record
 except Exception:
  w.save(key,dict(record,status='uncertain'));raise
 finally:TARGET=previous
def main():
 from conversion_watches import runtime,saved_network_guard
 from china_loss_control import PLAN
 w=runtime();pid='dialog-menu-owner-moscow-economics-20261111-final';p=w.get(PLAN+pid)
 receipt=w.get('china_agent:conversion_watch_delivery:v1:owner_moscow_final_20261111:proposal_png:0')or{}
 if receipt.get('status')!='sent'or receipt.get('message_id')!=929:raise ValueError('Original final report delivery unverified')
 with saved_network_guard():result=attach(w,p,929)
 print(__import__('json').dumps(dict(status=result['status'],message_id=result['message_id'],wb_writes=0)))
if __name__=='__main__':main()

