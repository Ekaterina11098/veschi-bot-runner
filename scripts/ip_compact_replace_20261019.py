import os,sys,json,hashlib,html
from datetime import datetime,timezone
from urllib.parse import urlparse
import requests
sys.path.insert(0,'private-source')
from advertising_agent import agent_store as s
MESSAGES=["Реклама за 18 октября 2026 · цель ДРР до 5%\n\nДРР РК — с подтверждённым посткликом.\nПо артикулам — прямой ДРР: постклик по товарам не распределён.\n\nРК       │ ДРР / результат      │ Выше 5% по артикулам\n─────────┼──────────────────────┼────────────────────\n35654841 │ 2,82%                │ Превышений нет\n36514081 │ 1,18%                │ Превышений нет\n37155100 │ 2,38%                │ 0-NoelBag-green — 10,60%\n37363108 │ 9,29%                │ Прямых заказов нет;\n         │                      │ потрачено 1 100 ₽\n37757330 │ Без заказов          │ Потрачено 2 ₽\n39410834 │ 6,64%                │ 534-NoelBag-emerald — 11,51%\n         │                      │ 141-PamelaBag-brown — 10,37%\n         │                      │ 021-AdeleBag-brown — 7,58%\n         │                      │ 600-JessicaBag-blue — 6,94%\n         │                      │ Остальные с ДРР — до 5%\n39483230 │ Без заказов          │ 182 ₽; РК приостановлена\n39634287 │ 3,57%                │ Превышений нет\n40192945 │ Нет расхода          │ Заказов нет\n40428505 │ Без заказов          │ 761 ₽; РК приостановлена\n40428689 │ 4,92%                │ Превышений нет\n\nПостклик уже включён в итог РК один раз. У РК 37155100 прямой ДРР — 10,60%, с посткликом — 2,38%; у 39410834 — 7,74% → 6,64%; у 39634287 — 4,33% → 3,57%. У 37363108 заказ подтверждён только через постклик.\n\n«Превышений нет» — только среди товаров с рассчитанным прямым ДРР. Отсутствие заказов или данных не считается нормой.","Бюджеты · наблюдения 19 октября 2026\nВремя — МСК.\n\nРК       │ Баланс   │ Время │ На сколько хватит*\n─────────┼──────────┼───────┼────────────────────\n35654841 │  3 250 ₽ │ 12:22 │ ≈ 7,6 дня\n36514081 │  8 829 ₽ │ 12:22 │ ≈ 268 дней**\n37155100 │  2 900 ₽ │ 12:22 │ ≈ 5 дней\n37363108 │  8 807 ₽ │ 12:42 │ ≈ 8 дней\n37757330 │  7 619 ₽ │ 12:22 │ Расход всего 2 ₽/сутки\n39410834 │  2 830 ₽ │ 12:22 │ ≈ 4,5 часа\n39483230 │  3 898 ₽ │ 11:42 │ Приостановлена\n39634287 │  9 803 ₽ │ 12:22 │ ≈ 5,8 дня\n40192945 │  8 386 ₽ │ 12:22 │ Расхода нет\n40428505 │ 27 816 ₽ │ 08:21 │ Приостановлена\n40428689 │  7 186 ₽ │ 12:22 │ ≈ 12,7 дня\n\nСамый короткий запас — у РК 39410834.\n\n*Баланс на момент наблюдения / суточный расход 18 октября. Условная длительность при сохранении темпа, не точное время исчерпания. Последующий расход не вычтен; это не текущие балансы на момент чтения. Для приостановленных РК срок не рассчитывается.\n**У РК 36514081 расход лишь 33 ₽/сутки: долгосрочная оценка неустойчива. У РК 37757330 расход слишком мал для полезной оценки срока."]
native=requests.sessions.Session.request
host=urlparse(os.environ['SUPABASE_URL']).hostname
counts={'deleteMessage':0,'sendMessage':0}
def guard(session,method,url,*a,**kw):
 u=urlparse(url);kind=u.path.rsplit('/',1)[-1]
 if u.hostname==host and u.path.startswith('/rest/v1/'):pass
 elif u.hostname=='api.telegram.org' and method.upper()=='POST' and kind in counts:
  counts[kind]+=1
  if counts[kind]>2:raise RuntimeError('Exact two deletes and sends maximum')
 else:raise PermissionError('Sources/WB forbidden')
 return native(session,method,url,*a,**kw)
requests.sessions.Session.request=guard
reg=s.registration();assert int(reg['chat_id'])==-1004378639510
token=os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()
def operation(kind,idx,body):
 key='advertising:ip:compact18:postclick-replacement:20261019:'+kind+':'+str(idx)
 prior=s.cache_get(key)
 if prior:
  if prior.get('status')!='confirmed':raise RuntimeError('Unknown previous outcome; no blind retry')
  print(json.dumps(prior));return
 claim={'status':'uncertain','operation':kind,'part':idx,'chat_id':reg['chat_id'],'at':datetime.now(timezone.utc).isoformat()}
 s.cache_set(key,claim,ttl_days=365);assert s.cache_get(key)==claim
 r=requests.post('https://api.telegram.org/bot'+token+'/'+kind,json=body,timeout=(10,30))
 b=r.json()
 if r.status_code!=200 or b.get('ok') is not True:raise RuntimeError('Telegram outcome unconfirmed; no blind retry')
 result=b.get('result')
 if kind=='deleteMessage':
  if result is not True:raise RuntimeError('Delete unconfirmed')
  proof=dict(claim,status='confirmed',message_id=body['message_id'])
 else:
  if (result.get('chat') or {}).get('id')!=reg['chat_id'] or not isinstance(result.get('message_id'),int):raise RuntimeError('Receipt mismatch')
  proof=dict(claim,status='confirmed',message_id=result['message_id'],text_sha256=hashlib.sha256(MESSAGES[idx-1].encode()).hexdigest())
 s.cache_set(key,proof,ttl_days=365);assert s.cache_get(key)==proof
 print(json.dumps(dict(proof,readback=True)))
for idx,mid in enumerate((13,14),1):
 receipt=s.cache_get('advertising:ip:compact18:approved-delivery:20261019:'+str(idx))
 assert receipt and receipt.get('status')=='confirmed' and receipt.get('message_id')==mid and receipt.get('chat_id')==reg['chat_id']
 operation('deleteMessage',idx,{'chat_id':reg['chat_id'],'message_id':mid})
for idx,text in enumerate(MESSAGES,1):
 operation('sendMessage',idx,{'chat_id':reg['chat_id'],'text':'<pre>'+html.escape(text)+'</pre>','parse_mode':'HTML'})
print(json.dumps({'complete':True,'source_calls':0,'wb_changes':0,'telegram_counts':counts}))
