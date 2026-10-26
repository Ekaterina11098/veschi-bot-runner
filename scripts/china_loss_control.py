"""Reply-bound owner loss plans; no model writes, independent item receipts."""
import copy,hashlib,json,re
from datetime import datetime,timezone,timedelta
CHAT=-1004342917488
BOT=8780468043
OWNER=5122667182
LATEST='china_agent:loss_plan:latest:v1'
PLAN='china_agent:loss_plan:v1:'
APPROVAL='china_agent:loss_plan_approval:v1:'
EXEC='china_agent:loss_plan_execution:v1:'
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def is_all(t):
 if re.fullmatch(r'(?:(?:да|хорошо|ок)[, ]+)?(?:(?:делай|сделай|давай)\s+(?:добавляй|добавим)(?:\s+в\s+(?:рекламу|рк))?|(?:давай\s+)?(?:меняем|меняй|повышай|увеличь)\s+ставки|давай\s+повышай)[.!]?',t.strip(),re.I):return True
 return bool(re.fullmatch(r'(?:(?:да|хорошо|ок|ладно)[, ]+)?(?:сделай(?:\s+вс[её])?|делай|выполни(?:\s+вс[её])?|выполняй|примени(?:\s+вс[её])?|применяй|подтверждаю|согласен|согласна|согласовано|одобряю|запускай|запускаем|можно запускать|давай|ок|хорошо|да)[.!]?',t.strip(),re.I))
def marker(job):return next((x for x in job.get('tool_trace',[]) if x.get('name')=='china_saved_question'),{})
def context(w):
 from china_loss_policy import POLICY,evaluate
 value=w.get('china_agent:loss_economics:latest:v1')
 if not value:return POLICY
 assessed=[];missing=[]
 for row in value.get('records',[]):
  try:
   v=evaluate(row)
   if v['expected_total_profit_rub']<0:assessed.append(dict(article=row['article'],nm_id=row['nm_id'],**v))
  except (ValueError,KeyError,TypeError):missing.append(row.get('article'))
 info=dict(period_from=value.get('period_from'),period_to=value.get('period_to'),observed_at=value.get('observed_at'),catalogue_count=value.get('catalogue_count'),assessed_count=len(value.get('records',[]))-len(missing),unassessed_count=len(missing),losses=assessed,limitations=value.get('limitations'),current=False)
 return POLICY+'\nСохранённый расчёт (даты обязательны, это не новая проверка): '+json.dumps(info,ensure_ascii=False)
def handle(w,job):
 from china_daily_ad_actions import handle as daily_handle
 daily_result=daily_handle(w,job)
 if daily_result is not None:return daily_result
 """DB-only hook; explicit execution queued for isolated post-dialog phase."""
 m=marker(job);latest=w.get(LATEST)
 from china_group_permissions import allowed
 if not is_all(job.get('request_text','')):
  if latest and allowed(w,job) and m.get('reply_message_id') in latest.get('reply_ids',[]):
   text=job.get('request_text','')
   if re.search(r'см|замер|фото|материал|рем[её]н|подклад|размер|натуральн|горловин',text,re.I):
    key='china_agent:loss_plan_clarification:v1:'+str(job['id'])
    w.save(key,dict(plan_id=latest['plan_id'],sender_id=job['sender_id'],input_text=text,message_id=m.get('message_id'),received_at=w.now.isoformat()),insert=True)
    return ('Уточнение сохранено для плана '+latest['plan_id']+'. Проверю его применимость к указанному артикулу. Неполные замеры и фотографии не подменяю предположениями; несвязанные пункты не меняю.',[{'name':'loss_plan_clarification','key':key}])
  return None
 from china_group_permissions import allowed
 if not allowed(w,job) or m.get('bot_id')!=BOT:
  return ('Запускать план могут действующие участники этой группы.',[])
 if not latest or latest.get('status')=='retired':return ('Нет сохранённого плана. Ответьте на новую таблицу рекомендаций.',[])
 p=w.get(PLAN+latest['plan_id'])
 if not p or p.get('chat_id')!=CHAT or p.get('bot_id')!=BOT or p.get('plan_sha256')!=digest(p['items']):raise ValueError('План изменился')
 if m.get('reply_message_id') not in p.get('report_message_ids',[]):return ('Ответьте «Сделай всё» именно на таблицу или сообщение с этим планом. Другие отчёты не запускаю.',[])
 created=datetime.fromisoformat(p['created_at']);at=datetime.fromisoformat(job['created_at'].replace('Z','+00:00'))
 if not created<=at<=datetime.fromisoformat(p['expires_at']):return ('Этот план устарел; сначала обновлю рекомендации, затем потребуется подтверждение нового плана.',[])
 k=APPROVAL+str(job['id'])
 a=dict(status='approved',plan_id=latest['plan_id'],plan_sha256=p['plan_sha256'],job_id=job['id'],update_id=job['update_id'],sender_id=job['sender_id'],chat_id=CHAT,bot_id=BOT,input_message_id=m.get('message_id'),reply_message_id=m['reply_message_id'],created_at=job['created_at'],price_changes=False)
 w.save(k,a,insert=True)
 return ('Команда принята по таблице '+latest['plan_id']+'. Выполню готовые пункты. По остальным пришлю конкретный список недостающих данных. Цены не меняю.',[{'name':'loss_plan_approval','key':k,'plan_id':latest['plan_id']}])

def build_card_update(card,item):
 if card.get('nmID')!=item['nm_id'] or card.get('vendorCode')!=item['article']:raise ValueError('Карточка не совпадает с планом')
 text=card.get('description')
 if not isinstance(text,str) or not text:raise ValueError('Нет полного описания')
 before=text
 for old,new in item['replacements']:
  if old not in text:
   if new in text:continue
   raise ValueError('Описание изменилось; требуется новый план')
  text=text.replace(old,new)
 if before==text:return None
 required=['nmID','vendorCode','title','brand','dimensions','characteristics','sizes']
 if any(k not in card for k in required):raise ValueError('Карточка неполна; перезапись запрещена')
 result={k:copy.deepcopy(card[k]) for k in required}
 if 'kizMarked' in card:result['kizMarked']=card['kizMarked']
 result['description']=text
 result['dimensions']={k:v for k,v in result['dimensions'].items() if k in ['length','width','height','weightBrutto']}
 result['characteristics']=[{k:v for k,v in c.items() if k in ['id','value']} for c in result['characteristics']]
 result['sizes']=[{k:v for k,v in s.items() if k in ['chrtID','techSize','wbSize','skus']} for s in result['sizes']]
 return result

def process(io,a):
 p=io.get(PLAN+a['plan_id']);key=EXEC+str(a['job_id']);e=io.get(key)
 if not p or a['plan_sha256']!=p['plan_sha256'] or digest(p['items'])!=p['plan_sha256']:raise ValueError('Plan scope')
 if type(a.get('sender_id')) is not int or a['sender_id']<=0 or a.get('chat_id')!=CHAT or a.get('bot_id')!=BOT or a.get('price_changes') is not False:raise ValueError('Owner scope')
 if e and e.get('status')=='done':return e
 if not e:
  e=dict(status='running',plan_id=a['plan_id'],approval_job=a['job_id'],items=[])
  if not io.create(key,e):return io.get(key)
 io.validate_owner(a)
 for item in p['items']:
  state=next((x for x in e['items'] if x['id']==item['id']),None)
  if state:
   if state['status'] in ['submitting','accepted','uncertain']:
    # Read-only recovery; never repeat the write.
    if state.get('after'):
     try:
      c=io.card(item['nm_id'])
      if c.get('description')==state['after']['description']:state['status']='verified'
      else:state['status']='uncertain'
     except Exception:state['status']='uncertain'
   io.put(key,e);continue
  state=dict(id=item['id'],article=item['article'],status='pending');e['items'].append(state)
  if item['kind']=='needs_data':state.update(status='needs_data',question=item['question']);io.put(key,e);continue
  if item['kind']!='card_text_replace':state.update(status='blocked',question='Тип операции пока не подтверждён для WB');io.put(key,e);continue
  try:
   c=io.card(item['nm_id']);after=build_card_update(c,item)
   if after is None:state['status']='already_at_target';io.put(key,e);continue
   state.update(status='submitting',before=c,after=after);io.put(key,e)
   io.update_card(after)
   state['status']='accepted';io.put(key,e)
   got=io.card(item['nm_id'])
   state['status']='verified' if got.get('description')==after['description'] else 'accepted'
  except Exception as ex:
   state.update(status='uncertain' if state['status']=='submitting' else 'blocked',reason=str(ex)[:200] if isinstance(ex,(ValueError,RuntimeError)) else type(ex).__name__)
  io.put(key,e)
 e['status']='awaiting_verification' if any(x['status'] in ['accepted','submitting'] for x in e['items']) else 'done';e['finished_at']=datetime.now(timezone.utc).isoformat();io.put(key,e)
 return e

def summary(e):
 lines=['Обработка «Сделай всё» по таблице '+e['plan_id']+'.','Ошибочный ответ про119 удалён; к этому плану он не относится.','Цены не менялись.']
 for x in e['items']:
  labels={'verified':'Выполнено, проверено WB','already_at_target':'Уже соответствует плану','accepted':'WB принял, отображение ещё проверяется','uncertain':'Результат записи не подтверждён; повтор не выполняю','blocked':'Не выполнено','needs_data':'Нужно уточнение/данные'}
  label='Нужно подготовить точное предложение по рекламе' if x['status']=='needs_data' and x['id'].endswith('_ad') else labels.get(x['status'],x['status'])
  details=x.get('question') or x.get('reason')
  if details=='Content HTTP 403':details='Токен WB не дал доступ к карточке; требуется проверить право «Контент» этого кабинета.'
  lines.append(x['article']+' — '+label+('. '+details if details else ''))
 lines.append('По рекламе: точные РК/SKU и ставка старая→новая либо отключениеSKU предложу отдельно после проверки данных. ДРР не записывается вWB как настройка; общиеРК целиком не останавливаю.')
 return '\n'.join(lines)



