"""Durable one-time analytical assignments from explicit human chat requests."""
import hashlib,re
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow');PREFIX='china_agent:conversion_watch:v1:'

def requested(text):
 return bool(re.search(r'завтра',text,re.I) and re.search(r'статистик|отч[её]т',text,re.I) and re.search(r'дай|пришли|отправь|покажи|без напоминаний',text,re.I) and re.search(r'(?<!\d)\d{1,2}[.:]\d{2}(?!\d)',text))

def prepare(w,job):
 if job.get('origin')=='scheduled' or not requested(job.get('request_text','')):return None
 if not w.authorized(job):raise PermissionError('One-time report human scope')
 cfg=w.config();key=PREFIX+str(cfg['chat_id'])+':'+str(cfg['owner_user_id'])+':task_once_'+str(job['id'])
 old=w.get(key)
 if old:
  if old.get('last_job_id')!=job['id'] or old.get('source_sender_id')!=job['sender_id']:raise ValueError('One-time schedule identity mismatch')
  return old['last_confirmation']
 text=job['request_text'];h,m=map(int,re.search(r'(?<!\d)(\d{1,2})[.:](\d{2})(?!\d)',text).groups())
 if h>23 or m>59:raise ValueError('Нужен час МСК 00:00–23:59')
 created=datetime.fromisoformat(job['created_at'].replace('Z','+00:00'))
 if created.tzinfo is None:raise ValueError('Question timestamp missing timezone')
 day=created.astimezone(MSK).date();target=datetime.combine(day+timedelta(days=1),datetime.min.time(),MSK).replace(hour=h,minute=m)
 if target<=w.now:raise ValueError('Срок разового отчёта уже прошёл; не переношу его молча на другой день')
 catalog={int(n):a for n,a in w.catalog()}
 def resolve(value):return sorted(n for n,a in catalog.items() if a.casefold() in value.casefold() or re.search(r'(?<!\d)'+str(n)+r'(?!\d)',value))
 ids=resolve(text);scope_job=job['id']
 if not ids:
  rows=w.db('GET','business_agent_jobs',params={'agent_id':'eq.china','chat_id':'eq.'+str(job['chat_id']),'sender_id':'eq.'+str(job['sender_id']),'id':'lt.'+str(job['id']),'select':'id,request_text,answer','order':'id.desc','limit':10}) or []
  for r in rows:
   ids=resolve((r.get('request_text')or'')+' '+(r.get('answer')or''))
   if ids:scope_job=r['id'];break
 if not 1<=len(ids)<=10:raise ValueError('Не удалось однозначно привязать 1–10 артикулов к разовому отчёту')
 names=[catalog[n] for n in ids];clock=f'{h:02}:{m:02}';wid=hashlib.sha256(key.encode()).hexdigest()[:8]
 task=('Разовый статистический отчёт по кабинету Китай token_3. Точные артикулы: '+', '.join(names)+'. '
       'Покажи по каждому отдельно '+str(day)+' (полный день) и '+str(day+timedelta(days=1))+' (неполный день до '+clock+' МСК). '
       'Формат: Markdown-таблица для доставки PNG. Колонки: артикул, расходы CNY и ДРР отдельно за каждый период. Сортировка по ДРР неполного дня по убыванию; неопределённую ДРР показать отдельно. '
       'Созданные заказы WB, рекламные расходы CNY и ДРР с датой/источником. ДРР=расход/атрибутированная сумма заказов; без суммы ДРР не определена. '
       'Не выдавать неполный день за полный или сравнение одинаковых окон. Это только статистика: никаких рекомендаций и изменений WB. '
       'Если источник задерживается, прямо указать время среза и пробел. Не обещать цифры, которых нет.')
 answer='Запланирован разовый отчёт '+wid+' на '+target.strftime('%d.%m.%Y около %H:%M')+' МСК: '+', '.join(names)+'. Периоды: '+str(day)+' полный и '+str(day+timedelta(days=1))+' до '+clock+' МСК. Отправка зависит от запуска облачного обработчика; точная минута не гарантирована.'
 watch=dict(id=wid,agent_id='china',chat_id=cfg['chat_id'],owner_user_id=cfg['owner_user_id'],source_sender_id=job['sender_id'],nm_id='task_once_'+str(job['id']),nm_ids=ids,articles=names,article=', '.join(names),kind='once_task',output_format='png_table',status='active',clock=clock,days=2,next_at=target.astimezone(timezone.utc).isoformat(),initial_pending=False,revision=1,last_job_id=job['id'],source_job_id=job['id'],scope_job_id=scope_job,task_text=task,last_confirmation=answer,execution_authorized=False,wb_writes=0,created_at=w.now.isoformat())
 if w.save(key,watch,insert=True) is False:raise ValueError('Concurrent one-time schedule creation; reread required')
 saved=w.get(key)
 if saved!=watch:raise ValueError('One-time schedule readback mismatch')
 return answer
