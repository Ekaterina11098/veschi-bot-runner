"""Single owner-requested PDF preview; no WB access or daily schedule changes."""
import os,json,base64,hashlib
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import requests
CHAT=-1004342917488
SOURCE='china_agent:pdf_preview_source:2026-10-19:v1'
KEY='china_agent:pdf_preview_delivery:2026-10-19:v1'
EXPECTED='12bf54b1ed58803f74d00b5a09fbf95a642ac4b8738ae3fac20a992d7baef31c'
BASE=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/'
SECRET=os.environ['SUPABASE_SECRET_KEY']
HEAD={'apikey':SECRET,'Authorization':'Bearer '+SECRET}
def db(method,table,**kwargs):
 r=requests.request(method,BASE+table,headers=HEAD,timeout=40,**kwargs);r.raise_for_status()
 return r.json() if r.content else None
def tg(method,body):
 r=requests.post('https://api.telegram.org/bot'+os.environ['CHINA_TELEGRAM_BOT_TOKEN']+'/'+method,json=body,timeout=40)
 value=r.json()
 if not r.ok or not value.get('ok'):raise RuntimeError('Telegram identity unconfirmed')
 return value['result']
def main():
 if str(datetime.now(ZoneInfo('Europe/Moscow')).date())!='2026-10-19':raise RuntimeError('Preview date expired')
 old=db('GET','telegram_api_cache',params=dict(cache_key='eq.'+KEY,select='payload'))
 if old:
  print(json.dumps(dict(status=old[0]['payload']['status'],already_recorded=True)));return
 rows=db('GET','telegram_api_cache',params=dict(cache_key='eq.'+SOURCE,select='payload'))
 if len(rows)!=1:raise RuntimeError('PDF source missing')
 source=rows[0]['payload']
 if source.get('report_date')!='2026-10-19' or source.get('chat_id')!=CHAT or source.get('sha256')!=EXPECTED or source.get('pages')!=1 or source.get('products')!=5:raise RuntimeError('PDF scope mismatch')
 pdf=base64.b64decode(source['base64'],validate=True)
 if hashlib.sha256(pdf).hexdigest()!=EXPECTED or not pdf.startswith(b'%PDF-'):raise RuntimeError('PDF checksum mismatch')
 if tg('getMe',{})['id']!=8780468043 or tg('getChat',dict(chat_id=CHAT))['id']!=CHAT:raise RuntimeError('Recipient identity mismatch')
 receipt=dict(status='sending',chat_id=CHAT,report_date='2026-10-19',source_key=SOURCE,sha256=EXPECTED,filename=source['filename'],started_at=datetime.now(timezone.utc).isoformat(),wb_writes=0)
 db('POST','telegram_api_cache',json=dict(cache_key=KEY,payload=receipt,expires_at='2036-10-19T00:00:00Z'))
 saved=db('GET','telegram_api_cache',params=dict(cache_key='eq.'+KEY,select='payload'))
 if len(saved)!=1 or saved[0]['payload']!=receipt:raise RuntimeError('Reservation readback mismatch')
 try:
  response=requests.post('https://api.telegram.org/bot'+os.environ['CHINA_TELEGRAM_BOT_TOKEN']+'/sendDocument',
   data=dict(chat_id=str(CHAT),caption='Рекомендации по ценам · 19.10.2026\nПробный PDF. Нажмите на артикул внутри таблицы, чтобы открыть товар.'),
   files=dict(document=(source['filename'],pdf,'application/pdf')),timeout=(10,60))
  value=response.json()
  if not response.ok or value.get('ok') is not True:raise RuntimeError('PDF send not confirmed')
  result=value['result']
  if result['chat']['id']!=CHAT or result['document'].get('mime_type')!='application/pdf':raise RuntimeError('PDF recipient response mismatch')
 except Exception:
  receipt.update(status='uncertain',finished_at=datetime.now(timezone.utc).isoformat())
  db('PATCH','telegram_api_cache',params=dict(cache_key='eq.'+KEY),json=dict(payload=receipt))
  raise RuntimeError('PDF outcome uncertain; do not resend') from None
 receipt.update(status='sent',message_id=result['message_id'],document=result['document'],telegram_date=result['date'],finished_at=datetime.now(timezone.utc).isoformat())
 db('PATCH','telegram_api_cache',params=dict(cache_key='eq.'+KEY),json=dict(payload=receipt))
 saved=db('GET','telegram_api_cache',params=dict(cache_key='eq.'+KEY,select='payload'))
 if len(saved)!=1 or saved[0]['payload']!=receipt:raise RuntimeError('Receipt readback mismatch')
 print(json.dumps(dict(status='sent',message_id=receipt['message_id'],chat_id=CHAT,documents=1,wb_writes=0)))
if __name__=='__main__':
 try:main()
 except Exception as exc:
  print(json.dumps(dict(status='failed',error_type=type(exc).__name__)))
  raise SystemExit(1)
