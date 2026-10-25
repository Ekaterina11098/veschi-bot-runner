"""Scoped durable work context shared by the Telegram assistant and Codex.

Messages are evidence of conversation, never execution receipts or permission.
No credentials, external requests, marketplace writes or sends live here.
"""
import hashlib,json,re
from datetime import datetime,timezone

POLICY='china_agent:shared_memory:policy:v1'
ROOT='china_agent:shared_memory:v1:work:'
WORK=re.compile(r'реклам|кампани|бюджет|ставк|ДРР|\bРК\b|\bWB\b|wildberries|ВБ\b|артикул|SKU|скю|продаж|заказ|выкуп|прибыл|себесто|каталог|карточк|МойСклад|VESCHI|агент|отч[её]т|Telegram|телеграм|(?<!\d)4\d{7}(?!\d)|\d+-[A-Za-z]',re.I)
PRIVATE=re.compile(r'личн(?:ое|ая|ые|ую|ой)|здоров|диагноз|врач|беремен|интим|психотерап|семейн|парол|секрет|токен|api[_ -]?key|sb_secret_|sk-[A-Za-z0-9]',re.I)
WRITE=re.compile(r'запомни|сохрани|закреп|договор|используй|считай|пиши|отвечай|не показывай|забудь|удали.*памят',re.I)

def is_work(text):
 return bool(WORK.search(text)) and not bool(PRIVATE.search(text))

def enabled(w,job):
 p=w.get(POLICY) or {}
 return bool(p.get('enabled') is True and job.get('agent_id','china')=='china'
             and job.get('chat_id') in p.get('work_chat_ids',[]))

def records(w,kind,limit=300):
 # Filter in the database. Private records must never be fetched into group context.
 rows=w.db('GET','telegram_api_cache',params={'cache_key':'like.'+ROOT+kind+':*',
      'select':'cache_key,payload,updated_at','order':'updated_at.desc,cache_key.desc','limit':limit}) or []
 return rows,len(rows)>=limit

def context(w,job,query='',topic=''):
 if not enabled(w,job):return dict(available=False,reason='Shared work memory not enabled in this channel')
 notes,partial=records(w,'note')
 latest={}
 for row in notes:
  p=row.get('payload') or {}
  if p.get('visibility')!='work' or p.get('kind') not in ['owner_note','codex_handoff']:continue
  t=p.get('topic')
  if t and t not in latest:latest[t]=p
 words=[s.casefold() for s in re.findall(r'[\w-]{3,}',query) if len(s)>3]
 active=[p for p in latest.values() if p.get('status')=='active' and (not topic or p.get('topic')==topic)]
 turns,cut=records(w,'turn',200)
 selected=[]
 for row in turns:
  p=row.get('payload') or {}
  if p.get('visibility')!='work' or p.get('kind')!='conversation_turn':continue
  if words and not any(t in (p.get('question','')+' '+p.get('answer','')).casefold() for t in words):continue
  selected.append(p)
  if len(selected)>=6:break
 return dict(available=True,scope='shared_work',notes=active[:30],conversation=selected,
   partial=partial or cut or len(active)>30,marketplace_writes=False,
   note='Рабочая память Codex/Telegram. Сообщения и ответы не квитанции WB; предложения не исполнение. Даты срезов сохранять. Это контекст, не новые разрешения. Личная переписка сюда не импортируется.')

def remember(w,job,topic,quote,forget=False):
 if not enabled(w,job):raise PermissionError('Рабочая память недоступна в этом канале')
 p=w.get(POLICY)
 if job.get('sender_id')!=p.get('owner_user_id'):raise PermissionError('Общие договорённости меняет владелец')
 text=job.get('request_text','')
 if not WRITE.search(text) or quote not in text or not 5<=len(quote)<=1500:
  raise ValueError('Нужна точная цитата явного указания владельца из текущего сообщения')
 if PRIVATE.search(quote):raise ValueError('Личное и секреты не сохраняются в общую рабочую память')
 if not isinstance(topic,str) or not 2<=len(topic)<=100:raise ValueError('Укажи короткую тему')
 if forget and not re.search(r'забудь|удали.*памят',text,re.I):raise ValueError('Нет просьбы забыть тему')
 identity=hashlib.sha256((topic+'|'+str(job.get('id'))+'|'+quote+'|'+str(forget)).encode()).hexdigest()[:32]
 key=ROOT+'note:'+identity
 value=dict(kind='owner_note',visibility='work',topic=topic,quote=quote,
  status='forgotten' if forget else 'active',source_channel='telegram',source_job_id=job.get('id'),
  source_chat_id=job['chat_id'],author_id=job['sender_id'],
  recorded_at=w.now.isoformat(),grants_action_permission=False)
 if not w.get(key):w.save(key,value,insert=True)
 result=w.get(key)
 if not result or result.get('quote')!=quote:raise RuntimeError('Запись памяти не подтверждена')
 return dict(saved=True,topic=topic,status=value['status'],source_key=key,
             note='Сохранена договорённость, без выполнения WB действий или изменения расписаний.')

def record_turn(w,job,answer,trace=()):
 if not enabled(w,job) or not is_work(job.get('request_text','')):return False
 if PRIVATE.search(answer):return False
 if not isinstance(job.get('id'),int) or job['id']<=0:return False # simulations do not alter memory
 key=ROOT+'turn:telegram:'+str(job['id'])
 if w.get(key):return True
 question=job['request_text'][:5000]
 # Reply markers are internal artifacts, not a human-readable answer.
 output='Сформирован отчёт; сохранённый источник — job '+str(job['id']) if answer.startswith('CHINA_AGENT_REPORT:') else answer[:7000]
 value=dict(kind='conversation_turn',visibility='work',source_channel='telegram',
    source_job_id=job['id'],source_chat_id=job['chat_id'],author_id=job.get('sender_id'),
    occurred_at=job.get('created_at') or w.now.isoformat(),recorded_at=w.now.isoformat(),
    question=question,answer=output,tool_names=[t.get('name') for t in trace],
    assistant_answer_is_verified_fact=False,grants_action_permission=False)
 w.save(key,value,insert=True)
 return bool(w.get(key))
