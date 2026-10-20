"""Durable two-photo China delivery. Never repeat a sending/uncertain part."""
import hashlib
from datetime import datetime,timezone
CHAT=-1004342917488
BOT=8780468043
def deliver(io,day,files,sender):
 key='china_agent:advertising_delivery:'+day+':v1'
 e=io.get(key)
 if e and e.get('status')=='delivered':return e
 if not e:
  e=dict(status='ready',day=day,chat_id=CHAT,parts=[],created_at=datetime.now(timezone.utc).isoformat(),wb_writes=0)
  if not io.create(key,e):raise RuntimeError('Concurrent delivery')
 kinds=[x['kind'] for x in files]
 if kinds!=['drr','budgets']:raise ValueError('Expected the approved ordered two-photo report')
 for f in files:
  digest=hashlib.sha256(f['bytes']).hexdigest()
  part=next((x for x in e['parts'] if x['kind']==f['kind']),None)
  if part:
   if part['sha256']!=digest:raise ValueError('Frozen report changed after delivery began')
   if part['status']=='sent':continue
   if part['status'] in ['sending','uncertain']:raise RuntimeError('Uncertain Telegram result; no blind retry')
  else:
   part=dict(kind=f['kind'],sha256=digest,status='ready');e['parts'].append(part)
  part['status']='sending';e['status']='sending';io.put(key,e)
  try:
   receipt=sender(f)
   if receipt.get('chat',{}).get('id')!=CHAT or type(receipt.get('message_id')) is not int:raise RuntimeError('Telegram receipt mismatch')
   part.update(status='sent',message_id=receipt['message_id'],receipt=receipt,sent_at=datetime.now(timezone.utc).isoformat())
   e['status']='partial';io.put(key,e)
  except Exception:
   part['status']='uncertain';e['status']='uncertain';io.put(key,e);raise RuntimeError('Telegram result uncertain; delivery not repeated') from None
 e['status']='delivered';e['completed_at']=datetime.now(timezone.utc).isoformat();io.put(key,e)
 return e
def telegram_sender(io):
 import requests
 if io.tg('getMe',{}).get('id')!=BOT:raise ValueError('Wrong China bot')
 def send(f):
  caption=f.get('caption','')
  r=requests.post('https://api.telegram.org/bot'+io.bot+'/sendPhoto',data={'chat_id':str(CHAT),'caption':caption},files={'photo':(f['kind']+'.png',f['bytes'],'image/png')},timeout=60)
  j=r.json()
  if not r.ok or not j.get('ok'):raise RuntimeError('Telegram send failed')
  return j['result']
 return send
