import os,sys,json,hashlib,html
from datetime import datetime,timezone,timedelta
from urllib.parse import urlparse
import requests
sys.path.insert(0,'private-source')
from advertising_agent import agent_store as s
MESSAGES=["Реклама за 18 октября 2026 · цель ДРР до 5%\n\nРК       │ ДРР    │ Выше 5% / примечание\n─────────┼────────┼─────────────────────\n35654841 │ 2,82%  │ Превышений нет\n36514081 │ 1,18%  │ Превышений нет\n37155100 │ 10,60% │ 0-NoelBag-green — 10,60%\n37363108 │ —      │ 1 100 ₽ без прямых заказов\n37757330 │ —      │ 2 ₽ без прямых заказов\n39410834 │ 7,74%  │ Выше 5%:\n         │        │ 534-NoelBag-emerald — 11,51%\n         │        │ 141-PamelaBag-brown — 10,37%\n         │        │ 021-AdeleBag-brown — 7,58%\n         │        │ 600-JessicaBag-blue — 6,94%\n         │        │ Остальные с ДРР — до 5%\n39483230 │ —      │ 182 ₽ без прямых заказов;\n         │        │ РК приостановлена\n39634287 │ 4,33%  │ Превышений нет\n40192945 │ —      │ Расхода и прямых заказов нет\n40428505 │ —      │ 761 ₽ без прямых заказов;\n         │        │ РК приостановлена\n40428689 │ 4,92%  │ Превышений нет\n\nДРР — по прямым заказам. «Превышений нет» — только среди товаров с рассчитанным ДРР. Товары без заказов или данных не считаются нормой.\n\nС подтверждённым посткликом: РК 37155100 — 2,38%; РК 37363108 — 9,29%. Распределение этих заказов по товарам не подтверждено.","Бюджеты · наблюдения 19 октября 2026\nВремя — МСК.\n\nРК       │ Баланс   │ Время │ На сколько хватит*\n─────────┼──────────┼───────┼────────────────────\n35654841 │  3 250 ₽ │ 12:22 │ ≈ 7,6 дня\n36514081 │  8 829 ₽ │ 12:22 │ ≈ 268 дней**\n37155100 │  2 900 ₽ │ 12:22 │ ≈ 5 дней\n37363108 │  8 807 ₽ │ 12:42 │ ≈ 8 дней\n37757330 │  7 619 ₽ │ 12:22 │ Расход всего 2 ₽/сутки\n39410834 │  2 830 ₽ │ 12:22 │ ≈ 4,5 часа\n39483230 │  3 898 ₽ │ 11:42 │ Приостановлена\n39634287 │  9 803 ₽ │ 12:22 │ ≈ 5,8 дня\n40192945 │  8 386 ₽ │ 12:22 │ Расхода нет\n40428505 │ 27 816 ₽ │ 08:21 │ Приостановлена\n40428689 │  7 186 ₽ │ 12:22 │ ≈ 12,7 дня\n\nСамый короткий запас — у РК 39410834.\n\n*Баланс на момент наблюдения / суточный расход 18 октября. Условная длительность при сохранении темпа, не точное время исчерпания. Последующий расход не вычтен; это не текущие балансы на момент чтения. Для приостановленных РК срок не рассчитывается.\n**У РК 36514081 расход лишь 33 ₽/сутки: долгосрочная оценка неустойчива. У РК 37757330 расход слишком мал для полезной оценки срока."]
native=requests.sessions.Session.request
host=urlparse(os.environ['SUPABASE_URL']).hostname
calls=0
def guard(session,method,url,*a,**kw):
 global calls
 u=urlparse(url)
 if u.hostname==host and u.path.startswith('/rest/v1/'): pass
 elif u.hostname=='api.telegram.org' and method.upper()=='POST' and u.path.endswith('/sendMessage'):
  calls+=1
  if calls>2: raise RuntimeError('Two sends maximum')
 else: raise PermissionError('No sources or WB')
 return native(session,method,url,*a,**kw)
requests.sessions.Session.request=guard
reg=s.registration()
assert int(reg['chat_id'])==-1004378639510
if datetime.now(timezone.utc).date().isoformat()!='2026-10-19':raise RuntimeError('Authorization expired')
for i,text in enumerate(MESSAGES,1):
 key='advertising:ip:compact18:approved-delivery:20261019:'+str(i)
 digest=hashlib.sha256(text.encode()).hexdigest()
 old=s.cache_get(key)
 if old:
  print(json.dumps({'part':i,'status':old.get('status'),'message_id':old.get('message_id'),'already_recorded':True}))
  if old.get('status')!='confirmed':raise RuntimeError('Prior uncertain send; no retry')
  continue
 claim={'status':'prepared','sha256':digest,'chat_id':reg['chat_id'],'at':datetime.now(timezone.utc).isoformat()}
 rows=s.db('POST','telegram_api_cache',params={'on_conflict':'cache_key'},body={'cache_key':key,'payload':claim,'expires_at':(datetime.now(timezone.utc)+timedelta(days=365)).isoformat(),'updated_at':datetime.now(timezone.utc).isoformat()},prefer='resolution=ignore-duplicates,return=representation') or []
 if len(rows)!=1:raise RuntimeError('Claim conflict; no send')
 assert s.cache_get(key)==claim
 # Persist uncertain before network: crash cannot lead to blind retry.
 claim['status']='uncertain';s.cache_set(key,claim,ttl_days=365)
 assert s.cache_get(key)==claim
 try:
  r=requests.post('https://api.telegram.org/bot'+os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()+'/sendMessage',json={'chat_id':reg['chat_id'],'text':'<pre>'+html.escape(text)+'</pre>','parse_mode':'HTML'},timeout=(10,30))
  b=r.json();m=b.get('result') or {}
  if r.status_code!=200 or not b.get('ok') or (m.get('chat') or {}).get('id')!=reg['chat_id'] or not isinstance(m.get('message_id'),int):raise RuntimeError('Unconfirmed Telegram outcome')
  receipt=dict(claim,status='confirmed',message_id=m['message_id'],confirmed_at=datetime.now(timezone.utc).isoformat())
  s.cache_set(key,receipt,ttl_days=365)
  assert s.cache_get(key)==receipt
  print(json.dumps({'part':i,'status':'confirmed','message_id':m['message_id'],'chat_id':reg['chat_id'],'receipt_readback':True}))
 except Exception:
  print(json.dumps({'part':i,'status':'uncertain','no_retry':True}))
  raise RuntimeError('Delivery not confirmed; no blind retry') from None
