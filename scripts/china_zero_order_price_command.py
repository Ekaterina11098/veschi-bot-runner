"""Exact percent price commands bound to a delivered zero-order cohort."""
import re,json,hashlib
from datetime import datetime,timezone
from decimal import Decimal,ROUND_HALF_UP
ROOT='china_agent:zero_order_price_command:v1:'
def parse(text):
 if re.search(r'может|стоит ли|можно ли|предлож|рассчита|если|\?',text,re.I):return None
 if not re.search(r'добавь|увеличь|увеличивай|повышай|повысь|подними|поднимай|поднять',text,re.I):return None
 if not re.search(r'цен',text,re.I) or not re.search(r'без\s+заказ',text,re.I) or not re.search(r'все|всех|всем',text,re.I):return None
 if not re.search(r'увелич|повыс|подним|поднят',text,re.I):return None
 m=re.search(r'(\d+(?:[.,]\d+)?)\s*%',text)
 if not m:return None
 n=Decimal(m[1].replace(',','.'))
 if not 0<n<=100:raise ValueError('Процент должен быть от 0 до 100')
 return str(n)
def signature(job,source,percent):
 return hashlib.sha256(json.dumps(dict(job_id=job['id'],sender_id=job['sender_id'],request=job['request_text'],source=source,percent=percent),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def handle(w,job,history):
 percent=parse(job.get('request_text',''))
 if percent is None:return None
 day=w.now.astimezone(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date().isoformat()
 source='china_agent:zero_orders_correction:'+day+':job151:stock:v1';p=w.get(source) or {}
 if p.get('status')!='sent' or not p.get('report',{}).get('collection_complete'):
  return 'Не удалось привязать команду к полному доставленному списку без заказов. Цены не менялись; нужен точный список.',[dict(name='zero_order_price_command',status='blocked')]
 report=p['report'];rows=report['zero']
 if not 1<=len(rows)<=100 or len({r['nm_id'] for r in rows})!=len(rows):raise ValueError('Неоднозначный список товаров')
 key=ROOT+str(job['id'])
 same=w.db('GET','telegram_api_cache',params={'cache_key':'like.'+ROOT+'*','payload->>source_key':'eq.'+source,'payload->>percent':'eq.'+percent,'select':'cache_key,payload->status,payload->job_id','limit':20}) or []
 prior=[x for x in same if x['cache_key']!=key]
 if prior:return 'Такая команда для этого доставленного списка уже зарегистрирована. Повторные +'+percent+'% не отправляю. Проверяю результат исходной команды; неизвестное выполнение не повторяю.',[dict(name='zero_order_price_command',duplicate_prevented=True,command_key=prior[0]['cache_key'])]
 entry=dict(status='requested',job_id=job['id'],actor_user_id=job['sender_id'],request_text=job['request_text'],source_key=source,source_sent_at=p['sent_at'],percent=percent,cohort=[dict(nm_id=str(r['nm_id']),article=r['article']) for r in rows],created_at=datetime.now(timezone.utc).isoformat())
 entry['signature']=signature(job,source,percent)
 entry['manual_review_required']=job['id']==155
 old=w.get(key)
 if not old:w.save(key,entry)
 elif old.get('signature')!=entry['signature']:raise ValueError('Команда изменилась')
 return 'Команда принята: повысить цену продавца на '+percent+'% для '+str(len(rows))+' товаров из доставленного списка без заказов, включая товары без остатка. Готовлю точные старые → новые цены. Выполнение подтвержу после проверки WB; остальные товары не затрагиваются.',[dict(name='zero_order_price_command',status=(old or entry)['status'],command_key=key)]
def validate_command(io,a,j):
 entry=io.get(ROOT+str(a['report_job_id'])) or {};source=io.get(entry.get('source_key','')) or {};job=dict(id=a['report_job_id'],sender_id=a['actor_user_id'],request_text=j['request_text'])
 if j.get('sender_id',a['actor_user_id'])!=a['actor_user_id']:raise ValueError('Original sender changed')
 if parse(j['request_text'])!=entry.get('percent') or entry.get('actor_user_id')!=a['actor_user_id'] or entry.get('signature')!=signature(job,entry.get('source_key'),entry.get('percent')):raise ValueError('Exact percent command identity changed')
 if entry.get('approval_key')!=a['approval_key'] or entry.get('selections')!=a['selections'] or source.get('status')!='sent':raise ValueError('Price command binding changed')
 expected={(str(r['nm_id']),r['article']) for r in source['report']['zero']}
 if {(r['nm_id'],r['article']) for r in entry['cohort']}!=expected:raise ValueError('Delivered cohort changed')
 for s in a['selections']:
  nominal=Decimal(s['current_cny'])*(1+Decimal(entry['percent'])/100)
  legal=(Decimal(s['base_cny'])*(1+Decimal(entry['percent'])/100)).quantize(Decimal('1'),rounding=ROUND_HALF_UP)*Decimal(100-s['seller_discount'])/100
  exact=Decimal(s['target_cny'])==nominal
  rounded=s.get('rounding_policy')=='nearest_WB_base_unit_preserve_discount' and Decimal(s['target_cny'])==legal and s.get('nominal_target_cny')==str(nominal)
  if (s['nm_id'],s['article']) not in expected or not (exact or rounded):raise ValueError('Target is not the requested percent or its declared legal WB step')
 if a['report_sha256']!=hashlib.sha256(j['request_text'].encode()).hexdigest():raise ValueError('Original command changed')

