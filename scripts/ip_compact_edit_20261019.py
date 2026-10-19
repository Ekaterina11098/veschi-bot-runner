import os,sys,json,hashlib,html
from datetime import datetime,timezone
from urllib.parse import urlparse
import requests
sys.path.insert(0,'private-source')
from advertising_agent import agent_store as s
TEXT="Реклама за 18 октября 2026 · цель ДРР до 5%\n\nРК       │ ДРР / результат       │ Примечание\n─────────┼───────────────────────┼─────────────────────\n35654841 │ 2,82%                 │ Превышений нет\n36514081 │ 1,18%                 │ Превышений нет\n37155100 │ 10,60%                │ 0-NoelBag-green — 10,60%\n37363108 │ 9,29% с посткликом     │ 1 100 ₽; прямых заказов нет\n37757330 │ Без прямых заказов    │ Потрачено 2 ₽\n39410834 │ 7,74%                 │ Выше 5%:\n         │                       │ 534-NoelBag-emerald — 11,51%\n         │                       │ 141-PamelaBag-brown — 10,37%\n         │                       │ 021-AdeleBag-brown — 7,58%\n         │                       │ 600-JessicaBag-blue — 6,94%\n         │                       │ Остальные с ДРР — до 5%\n39483230 │ Без прямых заказов    │ Потрачено 182 ₽;\n         │                       │ РК приостановлена\n39634287 │ 4,33%                 │ Превышений нет\n40192945 │ Нет расхода           │ Прямых заказов нет\n40428505 │ Без прямых заказов    │ Потрачено 761 ₽;\n         │                       │ РК приостановлена\n40428689 │ 4,92%                 │ Превышений нет\n\nДРР — по прямым заказам, кроме отдельно указанного постклика. «Превышений нет» — только среди товаров с рассчитанным ДРР. Товары без заказов или данных не считаются нормой.\n\nС подтверждённым посткликом: РК 37155100 — 2,38%; РК 37363108 — 9,29%. Распределение этих заказов по товарам не подтверждено."
OLD_SHA=""
native=requests.sessions.Session.request
host=urlparse(os.environ['SUPABASE_URL']).hostname
calls=0
def guard(session,method,url,*a,**kw):
 global calls
 u=urlparse(url)
 if u.hostname==host and u.path.startswith('/rest/v1/'):pass
 elif u.hostname=='api.telegram.org' and method.upper()=='POST' and u.path.endswith('/editMessageText'):
  calls+=1
  if calls>1:raise RuntimeError('One edit only')
 else:raise PermissionError('No sends, sources or WB allowed')
 return native(session,method,url,*a,**kw)
requests.sessions.Session.request=guard
reg=s.registration()
assert int(reg['chat_id'])==-1004378639510
key='advertising:ip:compact18:approved-delivery:20261019:1'
old=s.cache_get(key)
assert old and old.get('status')=='confirmed' and old.get('message_id')==13 and old.get('chat_id')==reg['chat_id']
editkey=key+':edit-labels-v1'
if s.cache_get(editkey):raise RuntimeError('Existing edit record; inspect without retry')
s.cache_set(editkey,{'status':'uncertain','message_id':13,'at':datetime.now(timezone.utc).isoformat()},ttl_days=365)
r=requests.post('https://api.telegram.org/bot'+os.environ['ADVERTISING_TELEGRAM_BOT_TOKEN'].strip()+'/editMessageText',json={'chat_id':reg['chat_id'],'message_id':13,'text':'<pre>'+html.escape(TEXT)+'</pre>','parse_mode':'HTML'},timeout=(10,30))
b=r.json();m=b.get('result') or {}
if r.status_code!=200 or b.get('ok') is not True or m.get('message_id')!=13 or (m.get('chat') or {}).get('id')!=reg['chat_id'] or m.get('text')!=TEXT:raise RuntimeError('Edit not confirmed; no blind retry')
proof={'status':'confirmed','message_id':13,'chat_id':reg['chat_id'],'sha256':hashlib.sha256(TEXT.encode()).hexdigest(),'at':datetime.now(timezone.utc).isoformat(),'sendMessage_calls':0,'editMessageText_calls':calls,'source_calls':0}
s.cache_set(editkey,proof,ttl_days=365)
assert s.cache_get(editkey)==proof
updated=dict(old,edited_sha256=proof['sha256'],edit_receipt_key=editkey)
s.cache_set(key,updated,ttl_days=365)
assert s.cache_get(key)==updated
print(json.dumps(dict(proof,receipt_readback=True)))
