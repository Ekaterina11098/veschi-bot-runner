"""Consent to calculate an advertising proposal is never consent to execute it."""
import re,hashlib
from datetime import datetime,timedelta,timezone
CHAT=-1004342917488
BOT=8780468043
QUESTION='china_agent:ad_prepare_question:v1:'
BIND='china_agent:ad_prepare_message:v1:'
ACCEPT='china_agent:ad_prepare_accept:v1:'
def stamp():return datetime.now(timezone.utc).isoformat()
def marker(job):return next((x for x in job.get('tool_trace',[])if x.get('name')=='china_saved_question'),{})
def sha(text):return hashlib.sha256(text.encode()).hexdigest()
def ask(w,job,ids):
 if job.get('chat_id')!=CHAT or marker(job).get('bot_id')!=BOT or marker(job).get('forwarded'):raise ValueError('Proposal question scope mismatch')
 if len(ids)>50 or len(set(ids))!=len(ids) or any(type(n)is not int or n<=0 for n in ids):raise ValueError('Exact proposal scope required')
 key=QUESTION+str(job['id']);old=w.get(key)
 if old:
  if old.get('nm_ids')!=ids or old.get('sender_id')!=job['sender_id']:raise ValueError('Proposal scope changed')
  return old['text']
 subject='этим '+str(len(ids))+' товарам' if ids else 'товарам кабинета'
 text='Подготовить по '+subject+' конкретное предложение после расчётов — с РК, размещением, ставками и бюджетом? Сам проверю экономику и наличие и пришлю план на подтверждение. До отдельного подтверждения готового плана ничего не запускаю.'
 now=stamp();q=dict(status='awaiting_consent',job_id=job['id'],chat_id=CHAT,bot_id=BOT,sender_id=job['sender_id'],input_message_id=marker(job).get('message_id'),source_reply_message_id=marker(job).get('reply_message_id'),nm_ids=list(ids),original_request_text=job.get('request_text',''),text=text,text_sha256=sha(text),created_at=now,expires_at=(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat(),wb_action_permission=False,grants_action_permission=False)
 if not w.save(key,q,insert=True):raise ValueError('Proposal question already claimed')
 return text
def bind(w,job_id,message_ids,answer):
 q=w.get(QUESTION+str(job_id))
 if not q:return
 if q.get('text')!=answer or q.get('text_sha256')!=sha(answer):raise ValueError('Delivered proposal question changed')
 for mid in message_ids:
  if type(mid)is not int:raise ValueError('Actual message id required')
  value=dict(question_job_id=job_id,chat_id=CHAT,bot_id=BOT,message_id=mid,text_sha256=q['text_sha256'])
  key=BIND+str(mid);old=w.get(key)
  if old and old!=value:raise ValueError('Proposal question message changed')
  if not old and not w.save(key,value,insert=True):raise ValueError('Proposal message binding lost')
def handle(w,job):
 m=marker(job);b=w.get(BIND+str(m.get('reply_message_id')))
 if not b:return None
 if job.get('chat_id')!=CHAT or m.get('bot_id')!=BOT or m.get('forwarded') or b.get('chat_id')!=CHAT or b.get('bot_id')!=BOT:return 'Подтвердите подготовку ответом на исходный вопрос бота в этой группе.'
 from china_group_permissions import allowed
 if not allowed(w,job):return 'Подготовку предложения могут подтвердить действующие участники группы.'
 q=w.get(QUESTION+str(b['question_job_id']))or{}
 if q.get('chat_id')!=CHAT or q.get('bot_id')!=BOT or q.get('text_sha256')!=b.get('text_sha256') or sha(q.get('text',''))!=b.get('text_sha256'):raise ValueError('Proposal consent binding changed')
 if job['sender_id']not in (q.get('sender_id'),5122667182):return 'Жду ответ автора запроса или владельца.'
 now=datetime.now(timezone.utc);at=datetime.fromisoformat(job['created_at'].replace('Z','+00:00'))
 if now>datetime.fromisoformat(q['expires_at']) or at<datetime.fromisoformat(q['created_at']):return 'Уточнение устарело. Запросите подготовку свежего предложения; запуск не выполнялся.'
 text=re.sub(r'^/codex\s+','',job.get('request_text','').strip(),flags=re.I)
 yes=bool(re.fullmatch(r'(?:(?:да|давай|ок|хорошо)[,.!]?\s*)?(?:подготовь(?:\s+(?:предложение|план))?|сделай\s+(?:предложение|план)|создай\s+предложение)|(?:да|давай|ок|хорошо|делай|согласен|согласна)[.!]?',text,re.I))
 # Natural scoped refinements remain consent to preparation, never execution.
 if re.match(r'^(?:да|давай|хорошо|согласен|согласна)(?:[.!,:;]|\s)',text,re.I) and not re.search(r'запускай|пополни|поменяй|исключи|не\s+(?:готовь|надо|подготавливай)|отмен',text,re.I):yes=True
 no=bool(re.fullmatch(r'(?:нет|не\s+надо|не\s+готовь|отмена|отмени)[.!]?',text,re.I))
 if not yes and not no:return 'Уточняю только подготовку расчётов и предложения. Ответьте «Да, подготовь» или «Нет». Готовый план потребует отдельного подтверждения перед запуском.'
 count=re.search(r'(?:около|примерно|до|лучше)\s+(\d+)\b|(\d+)\s*(?:товар|кандидат|артикул)',text,re.I)
 maximum=int(next(v for v in count.groups()if v)) if count else None
 if maximum is not None and not 1<=maximum<=50:return 'Для одного предложения укажите до 50 товаров. Запуск не выполнялся.'
 expanded=bool(yes and (re.search(r'больше|ещ[её]|найди|найти',text,re.I) and maximum and maximum>len(q['nm_ids'])))
 ids=[] if expanded else q['nm_ids']
 accepted=w.get(ACCEPT+str(q['job_id']))
 if accepted and accepted.get('job_id')!=job['id']:return 'На это уточнение уже получен ответ. Повторную подготовку и запуск не создаю.'
 if not accepted:
  value=dict(job_id=job['id'],question_job_id=q['job_id'],decision='prepare' if yes else 'decline',nm_ids=ids,seed_nm_ids=q['nm_ids'],maximum_count=maximum,chat_id=CHAT,created_at=stamp(),grants_action_permission=False)
  if not w.save(ACCEPT+str(q['job_id']),value,insert=True):return 'Ответ уже принят; повторную подготовку не создаю.'
 if no:return 'Хорошо, предложение по этому запросу не готовлю. Запуска и изменений нет.'
 from china_free_ads import prepare
 return prepare(w,job,ids,source_question_job_id=q['job_id'],maximum_count=maximum,seed_nm_ids=q['nm_ids'])

