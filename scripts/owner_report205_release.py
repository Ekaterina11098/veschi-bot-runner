"""Deliver only the reviewed existing report205 through its original receipts."""
import hashlib,json,os
from datetime import datetime,date
from zoneinfo import ZoneInfo
import requests
from conversion_watches import runtime,saved_network_guard,split_message,RECEIPTS
from china_cloud_cost_control import Cache,stamp
WATCH='china_agent:conversion_watch:v1:-1004342917488:5122667182:task_once_205'
REPORT='report:b85939ba:2026-11-01'
SHA='bfb0e97b393da87117c1882bc64c67e3280f8dfe67712ac29dad5db4567e975a'
def main():
 if datetime.now(ZoneInfo('Europe/Moscow')).date()!=date(2026,11,1):raise ValueError('Dated release expired')
 w=runtime();cfg=w.config();live=w.get(WATCH);prepared=w.get(RECEIPTS+REPORT)
 if cfg['chat_id']!=-1004342917488 or cfg['bot_id']!=8780468043 or cfg['owner_user_id']!=5122667182:raise ValueError('Destination changed')
 if not live or live['id']!='b85939ba' or live['revision']!=1 or live.get('initial_pending')or live['nm_ids']!=[1473243911,1473245494,1473245495,1473245508]:raise ValueError('Exact existing watch changed')
 if not prepared or prepared['chat_id']!=cfg['chat_id'] or hashlib.sha256(prepared['text'].encode()).hexdigest()!=SHA:raise ValueError('Reviewed report changed')
 parts=split_message(prepared['text'])
 def send(chat,text):
  if chat!=cfg['chat_id']or text not in parts:raise ValueError('Send outside exact reviewed report')
  # No automatic HTTP retry; native send_once owns uncertainty and durable deduplication.
  r=requests.post('https://api.telegram.org/bot'+os.environ['CHINA_TELEGRAM_BOT_TOKEN'].strip()+'/sendMessage',json=dict(chat_id=chat,text=text),timeout=35)
  return r.json()
 w.transport=send;w.watches=lambda:[(WATCH,w.get(WATCH))]
 with saved_network_guard():
  w.bot_check()
  if live['status']=='active':w.reports()
  elif live['status']!='completed':raise ValueError('Uncertain or cancelled report: do not repeat')
 final=w.get(WATCH);receipts=[w.get(RECEIPTS+REPORT+':part:'+str(i))for i in range(len(parts))]
 if final.get('status')!='completed' or final.get('next_at')is not None or any(not r or r.get('status')!='sent' or type(r.get('message_id'))is not int for r in receipts):raise RuntimeError('Delivery not verified; inspect original receipts, never blind retry')
 audit=dict(status='delivered',watch_key=WATCH,text_sha256=SHA,message_ids=[r['message_id']for r in receipts],verified_at=stamp(),wb_writes=0,price_writes=0,budget_writes=0,duplicate_schedule_created=False)
 c=Cache();key='china_agent:owner_report205:2026-11-01:v1:delivery'
 if not c.get(key):c.create(key,audit)
 print(json.dumps(audit))
if __name__=='__main__':main()

