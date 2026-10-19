"""Single owner-requested preview of the saved 19 October morning report."""
import os,json,hashlib
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import requests
from html import escape
CHAT=-1004342917488
KEY='china_agent:narrow_row_preview:2026-10-19:v1'
BASE=os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/'
SECRET=os.environ['SUPABASE_SECRET_KEY']
HEAD={'apikey':SECRET,'Authorization':'Bearer '+SECRET}
def db(method,table,**kwargs):
 r=requests.request(method,BASE+table,headers=HEAD,timeout=40,**kwargs)
 r.raise_for_status()
 return r.json() if r.content else None
def telegram(method,body):
 r=requests.post('https://api.telegram.org/bot'+os.environ['CHINA_TELEGRAM_BOT_TOKEN']+'/'+method,json=body,timeout=40)
 # Never print response URLs or token-bearing exceptions.
 try:value=r.json()
 except Exception:raise RuntimeError('Telegram response not JSON') from None
 if not r.ok or not value.get('ok'):raise RuntimeError('Telegram request not confirmed') from None
 return value['result']
def main():
 if str(datetime.now(ZoneInfo('Europe/Moscow')).date())!='2026-10-19':raise RuntimeError('Preview date expired')
 old=db('GET','telegram_api_cache',params=dict(cache_key='eq.'+KEY,select='payload'))
 if old:
  print(json.dumps(dict(status=old[0]['payload']['status'],already_recorded=True)));return
 saved=db('GET','telegram_api_cache',params=dict(cache_key='eq.china_agent:approved_price_table:2026-10-19:v1',select='payload'))
 if len(saved)!=1:raise RuntimeError('Approved report missing')
 source=saved[0]['payload']
 if source.get('status')!='sent' or source.get('chat_id')!=CHAT or source.get('report_date')!='2026-10-19':raise RuntimeError('Approved report scope mismatch')
 matches=[]
 for line in source['answer'].splitlines():
  cells=[v.strip() for v in line.split('|')]
  if len(cells)==4 and cells[1]=='590-PamelaBag-brown':matches.append(cells)
 if len(matches)!=1:raise RuntimeError('Exact report row missing')
 action,article,seller,buyer=matches[0]
 if action!='Повышение' or ' → ' not in seller or ' → ' not in buyer:raise RuntimeError('Report pair mismatch')
 text=('<b>Арт | Цены: старая → новая</b>\n\n<b>'+escape(action)+'</b> · '
  '<a href="https://www.wildberries.ru/catalog/1473245510/detail.aspx">'+escape(article)+'</a>'
  ' | Продавец: <b>'+escape(seller)+'</b>\n'
  ' | Покупатель: <b>'+escape(buyer)+'</b>\n'
  ' | Новая цена покупателя — прогноз')
 if telegram('getMe',{})['id']!=8780468043 or telegram('getChat',dict(chat_id=CHAT))['id']!=CHAT:raise RuntimeError('Recipient identity mismatch')
 receipt=dict(status='sending',chat_id=CHAT,report_date='2026-10-19',article=article,text_html=text,started_at=datetime.now(timezone.utc).isoformat(),wb_writes=0)
 db('POST','telegram_api_cache',json=dict(cache_key=KEY,payload=receipt,expires_at='2036-10-19T00:00:00Z'))
 check=db('GET','telegram_api_cache',params=dict(cache_key='eq.'+KEY,select='payload'))
 if len(check)!=1 or check[0]['payload']!=receipt:raise RuntimeError('Reservation readback mismatch')
 try:
  result=telegram('sendMessage',dict(chat_id=CHAT,text=text,parse_mode='HTML',link_preview_options=dict(is_disabled=True)))
  if result['chat']['id']!=CHAT:raise RuntimeError('Recipient response mismatch')
 except Exception:
  receipt.update(status='uncertain',finished_at=datetime.now(timezone.utc).isoformat())
  db('PATCH','telegram_api_cache',params=dict(cache_key='eq.'+KEY),json=dict(payload=receipt))
  raise RuntimeError('Preview outcome uncertain; do not resend') from None
 receipt.update(status='sent',message_id=result['message_id'],telegram_date=result['date'],finished_at=datetime.now(timezone.utc).isoformat())
 db('PATCH','telegram_api_cache',params=dict(cache_key='eq.'+KEY),json=dict(payload=receipt))
 check=db('GET','telegram_api_cache',params=dict(cache_key='eq.'+KEY,select='payload'))
 if len(check)!=1 or check[0]['payload']!=receipt:raise RuntimeError('Receipt readback mismatch')
 print(json.dumps(dict(status='sent',message_id=receipt['message_id'],chat_id=CHAT,messages=1,wb_writes=0)))
if __name__=='__main__':
 try:main()
 except Exception as exc:
  print(json.dumps(dict(status='failed',error_type=type(exc).__name__)))
  raise SystemExit(1)
