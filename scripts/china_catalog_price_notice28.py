"""One owner-requested corrective Telegram reply from canonical WB receipts. Never changes WB."""
import json,os,copy
from datetime import datetime,timezone
import requests
from china_cloud_cost_control import Cache
from conversion_watches import Worker
ROOT='china_agent:catalog_price_command:v1:2026-10-28'
NOTICE='china_agent:catalog_price_notice:2026-10-28:v1'
REPLY=480;CHAT=-1004342917488;BOT=8780468043;PAVEL=307200273
def stamp():return datetime.now(timezone.utc).isoformat()
def run():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main only')
 c=Cache();p=c.get(ROOT) or {}
 if p.get('status') not in ['verified','partial'] or not p.get('completed_at'):raise ValueError('Completed canonical execution required')
 prior=c.get(NOTICE)
 if prior:
  print(json.dumps(dict(status=prior.get('status'),message_id=prior.get('message_id'),existing=True)));return
 items=[]
 for key in p.get('executions',[]):
  e=c.get(key) or {}
  if e.get('status')!='done':raise ValueError('Price execution unresolved')
  for i in e.get('items',[]):
   s=i['selection'];rb=i.get('readback') or {}
   if i.get('status')!='applied' or rb.get('currencyIsoCode4217')!='CNY' or rb.get('vendorCode')!=s['article'] or not rb.get('sizes') or any(str(z['discountedPrice'])!=str(float(s['target_cny'])) and __import__('decimal').Decimal(str(z['discountedPrice']))!=__import__('decimal').Decimal(s['target_cny']) for z in rb['sizes']):raise ValueError('Independent exact price verification failed')
   if s['nm_id'] in p['excluded_prior']:raise ValueError('Protected SKU was written')
   items.append(s)
 if len({s['nm_id'] for s in items})!=len(items) or len(items)!=p['verified_count']:raise ValueError('Receipt count mismatch')
 noel=[s for s in items if 'noel' in s['article'].casefold()]
 if any(s['percent']!='10' for s in noel) or any(s['percent']!='5' for s in items if s not in noel):raise ValueError('Percent rule mismatch')
 # Exercise the actual fresh Worker route on Pavel's last confirmation, without model/marketplace/Telegram actions.
 class Replay(Worker):
  def __init__(self):self.now=datetime.now(timezone.utc)
  def get(self,key):return c.get(key)
  def authorized(self,job):raise ValueError('Replay must be read-only status, not a new command')
 j=dict(id=173,agent_id='china',chat_id=CHAT,sender_id=PAVEL,request_text='Согласен. Делай',tool_trace=[dict(name='china_saved_question',bot_id=BOT,message_id=480,parent_job_id=172)])
 answer,trace=Replay().saved_question(j,[])
 if trace[0].get('name')!='catalog_price_confirmation' or not trace[0].get('duplicate_prevented') or str(len(items)) not in answer or 'нет инструмента' in answer:raise ValueError('Fresh agent route regression')
 c.put(ROOT+':route_replay',dict(status='verified',checked_at=stamp(),job_id=173,route='catalog_price_confirmation',wb_writes=0,telegram_sends=0,duplicate_prevented=True))
 # Validate the original recipient and current bot before crossing the only send boundary.
 cfg=requests.get(c.url.rsplit('/',1)[0]+'/business_agent_config',params=dict(agent_id='eq.china',select='active,chat_id,bot_id,owner_user_id'),headers=c.h,timeout=30)
 if not cfg.ok or cfg.json()!=[dict(active=True,chat_id=CHAT,bot_id=BOT,owner_user_id=5122667182)]:raise ValueError('Current chat identity mismatch')
 token=os.environ['CHINA_TELEGRAM_BOT_TOKEN']
 def read(method,body):
  r=requests.post('https://api.telegram.org/bot'+token+'/'+method,json=body,timeout=30)
  j=r.json()
  if not r.ok or not j.get('ok'):raise ValueError('Telegram identity read unavailable')
  return j['result']
 if read('getMe',{}).get('id')!=BOT:raise ValueError('Bot identity mismatch')
 member=read('getChatMember',dict(chat_id=CHAT,user_id=PAVEL))
 if member.get('user',{}).get('id')!=PAVEL or member.get('user',{}).get('is_bot') or member.get('status') not in ['member','administrator','creator']:raise ValueError('Pavel recipient is not a current human member')
 text=('Павел, цены уже повышены и проверены в WB 28 октября в 21:31 МСК.\n'
       '• Все '+str(len(noel))+' артикулов NoelBag — +10%.\n'
       '• '+str(len(items)-len(noel))+' других товаров — +5%.\n'
       '• '+str(len(p['excluded_prior']))+' товаров с утренними +30% не затронуты.\n'
       '• Titang-170zel и Titang-170ser не изменены: исходная цена WB равна 0.\n'
       'Скидки сохранены, цены округлены до допустимого шага WB. Всего подтверждено '+str(len(items))+' изменений.\n'
       'Предыдущий ответ «нет инструмента / не подтверждено» устарел. Обработчик исправлен; повторное «делай» вернёт статус этого плана, повторно цены не повысит.')
 payload=dict(chat_id=CHAT,text=text,reply_parameters=dict(message_id=REPLY,allow_sending_without_reply=False),link_preview_options=dict(is_disabled=True))
 record=dict(status='sending',text=text,reply_to=REPLY,chat_id=CHAT,recipient_user_id=PAVEL,source_execution=ROOT,created_at=stamp(),owner_source='explicit_codex_send_request_2026-10-28')
 if not c.create(NOTICE,record):raise ValueError('Notice claimed by another sender')
 try:
  r=requests.post('https://api.telegram.org/bot'+token+'/sendMessage',json=payload,timeout=35);j=r.json()
  if not r.ok or not j.get('ok'):raise ValueError('Telegram send not confirmed')
  result=j['result']
  if result.get('chat',{}).get('id')!=CHAT or result.get('from',{}).get('id')!=BOT or result.get('reply_to_message',{}).get('message_id')!=REPLY or result.get('reply_to_message',{}).get('from',{}).get('id')!=PAVEL:raise ValueError('Telegram receipt binding mismatch')
  record.update(status='sent',message_id=result['message_id'],receipt=result,sent_at=stamp());c.put(NOTICE,record)
 except Exception:
  record.update(status='uncertain',error='Delivery needs receipt reconciliation; never repeat blindly');c.put(NOTICE,record)
 print(json.dumps(dict(status=record['status'],message_id=record.get('message_id'),wb_writes=0)))
if __name__=='__main__':
 try:run()
 except Exception as e:
  print(json.dumps(dict(status='blocked_before_send',error_type=type(e).__name__)))
  raise SystemExit(1)
