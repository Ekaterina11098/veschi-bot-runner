"""One configured Telegram group's read-only dialog; isolated from stopped queues."""
import os,sys,json,time,uuid,hmac,hashlib
from datetime import datetime,timezone,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'review-approval-preparation'))

def schedule_answer(text):
 import re
 if not re.search(r'расписани|(?:постоянн|регулярн).*отч[её]т',text,re.I):return None
 root=Path(__file__).parent/'.github/workflows'
 known={
  'stock-daily-1630-prepared.yml':["0 4 * * *","30 13 * * 0-6"],
  'reviews-morning.yml':["0,20,40 5-7 * * *"],
  'questions-morning.yml':["10,30,50 5-7 * * *"]}
 if not all(all(value in (root/name).read_text(encoding='utf8') for value in values) for name,values in known.items()):
  return 'Настройки расписания изменились. Не могу подтвердить время отчётов без проверки действующих запусков.'
 return ('Постоянные рассылки, время МСК:\n'
  '• Остатки: запуск ежедневно в 07:00 и 16:30. После завершения — итог изменений и необходимые ручные увеличения.\n'
  '• Проверка остатков МСК 1–19 шт.: после тех же запусков; отдельный блок «Нет в продаже на ВБ». Пустой список не отправляется.\n'
  '• Отзывы трёх кабинетов: с 08:00, повторные проверки каждые 20 минут до 10:40. Карточки, требующие согласования, приходят сюда.\n'
  '• Вопросы трёх кабинетов: с 08:10, повторные проверки каждые 20 минут до 10:50.\n'
  'Фактическая доставка может быть позже из-за очереди запуска и ограничений WB.\n'
  'Ежемесячную проверку «Подделки» этим обработчиком подтвердить нельзя. Даты сохранённых данных не являются расписанием отчётов.')

def main():
 import psycopg,requests
 from review_telegram_approval import Repository
 root=os.environ['SUPABASE_SECRET_KEY'].encode()
 password=hmac.new(root,b'veschi:review-approval-login:20261015:v1',hashlib.sha256).hexdigest()
 with psycopg.connect(host='aws-0-eu-central-1.pooler.supabase.com',port=5432,dbname='postgres',user='review_approval_login_20261015.abxgjoqlddhtcmjcjwxw',password=password,sslmode='require',autocommit=True,connect_timeout=15) as conn:
  repo=Repository(conn,postgres=True)
  row=conn.execute("SELECT payload FROM review_approval.source_cache WHERE cache_key='reviews:content-group:v1'").fetchone()
  policy=row[0] if row else {}
  if not policy.get('chat_id'):return {'status':'unconfigured'}
  chat=str(policy['chat_id']);token=os.environ['TELEGRAM_BOT_TOKEN']
  def tg(method,body):
   r=requests.post('https://api.telegram.org/bot'+token+'/'+method,json=body,timeout=15)
   data=r.json()
   if not r.ok or not data.get('ok'):raise RuntimeError('Telegram '+method+' unconfirmed')
   return data['result']
  webhook=tg('getWebhookInfo',{})
  with repo.transaction():repo.put('events','content-group:webhook-health:v1',dict(pending_update_count=webhook.get('pending_update_count'),last_error_date=webhook.get('last_error_date'),last_error_message=webhook.get('last_error_message'),allowed_updates=webhook.get('allowed_updates'),checked_at=time.time()))
  bot=tg('getMe',{});group=tg('getChat',{'chat_id':chat});member=tg('getChatMember',{'chat_id':chat,'user_id':bot['id']})
  if str(bot['id'])!=str(policy['bot_id']) or bot['username'].lower()!='veschi_brand_ai_bot' or str(group['id'])!=chat or group['type'] not in ('group','supergroup') or member['status']!='administrator':raise RuntimeError('Group identity or administrator access mismatch')
  with repo.transaction():repo.put('events','content-group:preflight:v1',dict(chat_id=chat,bot_id=str(bot['id']),title=group.get('title'),chat_type=group['type'],bot_status=member['status'],checked_at=time.time(),run_id=os.getenv('GITHUB_RUN_ID')))
  if not policy.get('enabled') or not policy.get('destination_verified'):return {'status':'preflight_verified','chat_type':group['type'],'bot_status':member['status']}
  # One connection receipt; never resend an unknown Telegram outcome.
  key='content-group:connection:v1'
  if not repo.get('events',key):
   with repo.transaction():repo.put('events',key,dict(status='sending',chat_id=chat,created_at=time.time()))
   response=tg('sendMessage',{'chat_id':chat,'text':'Контент-агент подключён. Все участники этой группы могут задавать вопросы, дорабатывать ответы и подтверждать публикации в WB. Новые карточки отзывов и вопросов и плановые отчёты по остаткам будут поступать сюда. Уже согласованные ответы продолжают обрабатываться без повторной отправки.'})
   if str(response.get('chat',{}).get('id'))!=chat or not response.get('message_id'):raise RuntimeError('Connection receipt unconfirmed')
   with repo.transaction():repo.put('events',key,dict(status='confirmed',chat_id=chat,message_id=response['message_id'],checked_at=time.time()))
  # Claim only this exact group's jobs. Other agents and old queues stay untouched.
  from business_agents import conversation as dialog
  native_tools=dialog.tools
  allowed={'get_status','find_products','get_product','get_stock_context','get_mpstats_data','get_check_status'}
  dialog.tools=lambda agent:[t for t in native_tools(agent) if t['name'] in allowed]
  native_explicit=dialog.explicit_check;dialog.explicit_check=lambda text:None
  def db(method,params=None,body=None):
   key=os.environ['SUPABASE_SECRET_KEY'];headers={'apikey':key,'Content-Type':'application/json','Prefer':'return=representation'}
   if not key.startswith('sb_secret_'):headers['Authorization']='Bearer '+key
   r=requests.request(method,os.environ['SUPABASE_URL']+'/rest/v1/business_agent_jobs',params=params,json=body,headers=headers,timeout=20)
   r.raise_for_status();return r.json() if r.content else []

  # Correct our exact delivered schedule answer if an earlier model confused snapshot dates with schedules.
  recent=db('GET',{'agent_id':'eq.operations','chat_id':'eq.'+chat,'status':'eq.done','order':'id.desc','limit':'10'})
  for saved in recent:
   correct=schedule_answer(saved['request_text'])
   if not correct or saved.get('answer')==correct:continue
   receipt=repo.get('events','content-group:answer:'+str(saved['id']))
   if not receipt or receipt.get('status')!='confirmed' or str(receipt.get('chat_id'))!=chat:continue
   response=tg('editMessageText',{'chat_id':chat,'message_id':receipt['message_id'],'text':correct})
   if str(response.get('chat',{}).get('id'))!=chat:raise RuntimeError('Correction identity mismatch')
   db('PATCH',{'id':'eq.'+str(saved['id']),'chat_id':'eq.'+chat},{'answer':correct,'tool_trace':[{'name':'content_report_schedule','source':'deployed_workflows'}]})
   with repo.transaction():repo.put('events','content-group:schedule-correction:'+str(saved['id']),dict(status='confirmed',message_id=receipt['message_id'],checked_at=time.time()))

  report={'done':0,'errors':0}
  try:
   rows=db('GET',{'agent_id':'eq.operations','chat_id':'eq.'+chat,'status':'eq.pending','retry_at':'lte.'+datetime.now(timezone.utc).isoformat(),'order':'id.asc','limit':'6'})
   for job in rows:
    lease=str(uuid.uuid4());claimed=db('PATCH',{'id':'eq.'+str(job['id']),'status':'eq.pending'},{'status':'running','lease_token':lease,'lease_until':(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat(),'attempts':job['attempts']+1})
    if not claimed:continue
    def patch(body):return db('PATCH',{'id':'eq.'+str(job['id']),'lease_token':'eq.'+lease},body)
    try:
     membership=tg('getChatMember',{'chat_id':chat,'user_id':job['sender_id']})
     if membership.get('user',{}).get('id')!=job['sender_id'] or membership.get('status') not in ('creator','administrator','member'):raise ValueError('Sender no longer a group member')
     history=db('GET',{'agent_id':'eq.operations','chat_id':'eq.'+chat,'status':'eq.done','id':'lt.'+str(job['id']),'select':'agent_id,chat_id,request_text,answer','order':'id.desc','limit':'6'})
     def model_request(body):
      response=requests.post('https://api.openai.com/v1/responses',headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},json=body,timeout=(10,100))
      if response.status_code!=200:raise RuntimeError('Content model unavailable')
      return response.json()
     known_schedule=schedule_answer(job['request_text'])
     if known_schedule:answer,trace=known_schedule,[{'name':'content_report_schedule','source':'deployed_workflows'}]
     else:answer,trace=dialog.run_dialog(job,request=model_request,previous=list(reversed(history)))
     patch({'answer':answer,'tool_trace':trace})
     # Commit send intent first: an unknown send outcome is never retried blindly.
     key='content-group:answer:'+str(job['id'])
     old=repo.get('events',key)
     if old:raise ValueError('Existing delivery requires reconciliation')
     with repo.transaction():repo.put('events',key,dict(status='sending',job_id=job['id'],chat_id=chat,created_at=time.time()))
     response=tg('sendMessage',{'chat_id':chat,'text':answer[:3500]})
     if str(response.get('chat',{}).get('id'))!=chat or not response.get('message_id'):raise RuntimeError('Answer identity unconfirmed')
     with repo.transaction():repo.put('events',key,dict(status='confirmed',job_id=job['id'],chat_id=chat,message_id=response['message_id'],checked_at=time.time()))
     patch({'status':'done','completed_at':datetime.now(timezone.utc).isoformat(),'lease_until':None,'error':None});report['done']+=1
    except Exception as exc:
     # Failed jobs remain visible and cannot loop or affect publication workers.
     patch({'status':'failed','lease_until':None,'error':type(exc).__name__});report['errors']+=1
  finally:dialog.tools=native_tools;dialog.explicit_check=native_explicit
  with repo.transaction():repo.put('events','content-group:dialog-health:v1',dict(**report,checked_at=time.time(),run_id=os.getenv('GITHUB_RUN_ID')))
  return report

if __name__=='__main__':
 try:print(json.dumps(main()))
 except Exception as exc:print(json.dumps({'error_type':type(exc).__name__}));raise SystemExit(1)
