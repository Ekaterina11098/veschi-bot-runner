"""Format correction only: reply with the exact reviewed table, never regenerate data."""
import os,json,hashlib,requests
from datetime import datetime,date
from zoneinfo import ZoneInfo
from china_cloud_cost_control import Cache,stamp
from china_once_report_png import render
KEY='china_agent:conversion_watch_delivery:v1:report:b85939ba:2026-11-01:png:v1'
ROOT='china_agent:conversion_watch_delivery:v1:report:b85939ba:2026-11-01'
def main():
 if datetime.now(ZoneInfo('Europe/Moscow')).date()!=date(2026,11,1):raise ValueError('Dated correction expired')
 c=Cache();prior=c.get(KEY)
 if prior:print(json.dumps(dict(status=prior['status'],existing=True)));return
 prepared=c.get(ROOT);old=c.get(ROOT+':part:0');watch=c.get('china_agent:conversion_watch:v1:-1004342917488:5122667182:task_once_205')
 if not prepared or hashlib.sha256(prepared['text'].encode()).hexdigest()!='bfb0e97b393da87117c1882bc64c67e3280f8dfe67712ac29dad5db4567e975a':raise ValueError('Source changed')
 if old.get('status')!='sent' or old.get('message_id')!=598 or old.get('chat_id')!=-1004342917488 or watch.get('status')!='completed':raise ValueError('Original delivery not verified')
 names=dict(zip(watch['nm_ids'],watch['articles']));blob=render(prepared,names)
 if not blob.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Not PNG')
 token=os.environ['CHINA_TELEGRAM_BOT_TOKEN'].strip()
 me=requests.post('https://api.telegram.org/bot'+token+'/getMe',timeout=25).json()
 if not me.get('ok')or me['result']['id']!=8780468043:raise ValueError('Wrong bot')
 receipt=dict(status='sending',chat_id=-1004342917488,reply_to_message_id=598,source_key=ROOT,png_sha256=hashlib.sha256(blob).hexdigest(),created_at=stamp(),wb_writes=0,telegram_edits=0,telegram_deletes=0)
 if not c.create(KEY,receipt):raise ValueError('Concurrent format correction')
 try:
  r=requests.post('https://api.telegram.org/bot'+token+'/sendPhoto',data=dict(chat_id=-1004342917488,caption='Китай · отчёт Павлу за 31.10 и неполное 01.11. Таблица PNG к сообщению598: те же данные, срез18:16МСК; сортировка по ДРР1ноября.',reply_parameters=json.dumps(dict(message_id=598))),files={'photo':('pavel-report-1800.png',blob,'image/png')},timeout=40).json()
  if not r.get('ok'):receipt.update(status='rejected',code=r.get('error_code'))
  else:
   m=r['result']
   if m.get('chat',{}).get('id')!=-1004342917488 or m.get('from',{}).get('id')!=8780468043 or not m.get('photo')or type(m.get('message_id'))is not int:raise ValueError('Photo receipt mismatch')
   receipt.update(status='sent',message_id=m['message_id'],telegram_receipt=m,sent_at=stamp())
 except Exception as ex:receipt.update(status='uncertain',reason=type(ex).__name__)
 c.put(KEY,receipt)
 print(json.dumps({k:receipt.get(k)for k in ['status','message_id','reply_to_message_id','png_sha256','wb_writes']}))
if __name__=='__main__':main()

