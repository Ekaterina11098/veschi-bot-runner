"""Owner requested all-source no-order report14-27Oct, no marketplace writes."""
import base64,hashlib,json,os,sys,requests
from datetime import datetime,timezone
from urllib.parse import urlencode
from china_advertising_state import AdvertisingIO
from china_zero_orders import collect
from china_zero_orders_stock import render
ROOT='china_agent:zero_orders_correction:2026-10-28:job151:stock:v1';CHAT=-1004342917488;BOT=8780468043
class W:
 def __init__(self,io):self.io=io;self.now=datetime.now(timezone.utc)
 def get(self,k):return self.io.get(k)
 def save(self,k,p):
  if self.get(k) is None:
   if not self.io.create(k,p):raise ValueError('Report state race')
  else:self.io.put(k,p)
 def db(self,method,table,params=None,body=None,prefer=None):return self.io.db(table+('?' +urlencode(params) if params else ''),method,body,prefer)
 def catalog(self):
  p=self.get('china_agent:prices:v1') or {}
  if p.get('cabinet')!='token_3' or not p.get('rows'):raise ValueError('China catalogue unavailable')
  return [(int(x['nmID']),x['vendorCode']) for x in p['rows']]
def run(mode):
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 io=AdvertisingIO();e=io.get(ROOT)
 if mode in ['prepare','refresh']:
  if e and (e.get('status')=='sent' or e.get('status')=='prepared' and mode!='refresh'):print(json.dumps(dict(status=e['status'],duplicate_prevented=True)));return
  report=collect(W(io),'2026-10-14','2026-10-27')
  if not report['collection_complete']:raise ValueError('Source incomplete; do not send a zero-order assertion')
  files=render(report)
  e=dict(status='prepared',report=report,files=[dict(family=f['family'],page=f['page'],total=f['total'],b64=base64.b64encode(f['bytes']).decode(),sha256=hashlib.sha256(f['bytes']).hexdigest()) for f in files],created_at=datetime.now(timezone.utc).isoformat(),wb_writes=0)
  if mode=='refresh':io.put(ROOT,e)
  elif not io.create(ROOT,e):raise ValueError('Build race')
  print(json.dumps(dict(status=e['status'],zero=report['zero_count'],unknown=report['unknown_count'],pages=len(files))));return
 if mode!='apply' or not e or e.get('visual_review')!='approved':raise ValueError('Reviewed exact source report required')
 if e['status']=='sent':print(json.dumps(dict(status='sent',duplicate_prevented=True)));return
 if io.tg('getMe',{}).get('id')!=BOT:raise ValueError('Bot identity')
 for i,f in enumerate(e['files']):
  key=ROOT+':delivery:'+str(i);prior=io.get(key)
  if prior:
   if prior.get('status')=='sent':continue
   raise ValueError('Delivery uncertain; no repeat')
  caption='Дополнение к списку без заказов за 14–27 октября: разделение по текущим остаткам МойСклад / МСК. '+('Неполные данные заказов — не ноль.' if f['family']=='unknown_orders' else 'Текущие остатки не доказывают наличие за весь период.')+' '+str(f['page'])+'/'+str(f['total'])+'. Изменений WB нет.'
  record=dict(status='sending',sha256=f['sha256'],family=f['family'],chat_id=CHAT,bot_id=BOT,created_at=datetime.now(timezone.utc).isoformat())
  if not io.create(key,record):raise ValueError('Send race')
  raw=base64.b64decode(f['b64'],validate=True)
  if hashlib.sha256(raw).hexdigest()!=f['sha256']:raise ValueError('Artifact changed')
  try:answer=requests.post('https://api.telegram.org/bot'+io.bot+'/sendPhoto',data=dict(chat_id=CHAT,caption=caption,reply_parameters=json.dumps(dict(message_id=404,allow_sending_without_reply=False))),files={'photo':('zero-orders.png',raw,'image/png')},timeout=45).json()
  except Exception:raise RuntimeError('Telegram uncertain; do not retry') from None
  if not answer.get('ok'):raise ValueError('Telegram rejected '+str(answer.get('error_code')))
  receipt=answer['result']
  if receipt['chat']['id']!=CHAT or receipt['from']['id']!=BOT:raise ValueError('Receipt identity')
  record.update(status='sent',message_id=receipt['message_id'],receipt=receipt);io.put(key,record)
 e.update(status='sent',sent_at=datetime.now(timezone.utc).isoformat());io.put(ROOT,e)
 print(json.dumps(dict(status='sent',pages=len(e['files']),wb_writes=0)))
if __name__=='__main__':run(json.load(open('ops/china-zero14-stock-trigger.json'))['mode'])

