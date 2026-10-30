"""Read-only hourly analysis; cabinet identity and denomination are independent checks."""
import re,math
from datetime import datetime,date,timedelta,timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from xml.etree import ElementTree as ET
MSK=ZoneInfo('Europe/Moscow')
ROOT='china_agent:hourly_orders:v1:'
FX='china_agent:cbr_cny:v1:'
CBR='https://www.cbr.ru/scripts/XML_daily.asp'

def number(x):
 if isinstance(x,bool) or x is None:raise ValueError('Missing numeric evidence')
 n=Decimal(str(x).replace(',','.'))
 if not n.is_finite() or n<0:raise ValueError('Invalid numeric evidence')
 return n

def parse_rate(xml,day):
 root=ET.fromstring(xml)
 effective=datetime.strptime(root.attrib['Date'],'%d.%m.%Y').date()
 if effective>day or (day-effective).days>10:raise ValueError('CBR effective date mismatch')
 rows=[r for r in root.findall('Valute') if r.findtext('CharCode')=='CNY']
 if len(rows)!=1:raise ValueError('CBR CNY missing')
 r=rows[0];nominal=number(r.findtext('Nominal'));value=number(r.findtext('Value'))
 if nominal<=0 or value<=0:raise ValueError('CBR positive rate required')
 return dict(requested_date=str(day),effective_date=str(effective),rub_per_cny=str(value/nominal),source=CBR)

def rate(w,day):
 key=FX+str(day);r=w.get(key)
 if r and r.get('source')==CBR and r.get('requested_date')==str(day):
  eff=date.fromisoformat(r['effective_date'])
  if eff<=day and (day-eff).days<=10 and number(r['rub_per_cny'])>0:return r
 import requests
 response=requests.get(CBR,params={'date_req':day.strftime('%d/%m/%Y')},timeout=20)
 response.raise_for_status();r=parse_rate(response.content,day);w.save(key,r);return r

def money_cny(w,value,currency,day,rates):
 if value is None:return None
 value=number(value)
 if currency=='CNY':return value
 if currency!='RUB':raise ValueError('Unknown source currency')
 r=rate(w,day);rates[str(day)]=r
 return value/number(r['rub_per_cny'])

def hourly(w,p,day):
 if not p or p.get('cabinet')!='token_3' or p.get('seller_identity_verified') is not True or p.get('complete') is not True:
  raise ValueError('Cabinet identity or completeness unverified')
 if p.get('period_from')!=str(day) or p.get('period_to')!=str(day):raise ValueError('Order period mismatch')
 observed=datetime.fromisoformat(p['observed_at']).astimezone(MSK)
 if observed>w.now.astimezone(MSK)+timedelta(minutes=2):raise ValueError('Future snapshot')
 currency=p.get('currency')
 if currency not in ('CNY','RUB'):raise ValueError('Source currency unverified')
 known={int(nm) for nm,_ in w.catalog()};seen={};rates={}
 bins={h:dict(hour=h,orders=0,amount=Decimal(0),amount_complete=True,cancelled=0) for h in range(24)}
 for r in p['rows']:
  if r['nm_id'] not in known:raise ValueError('Foreign or unresolved product identity')
  ident=str(r['order_id'])
  if ident in seen:
   if seen[ident]!=r:raise ValueError('Conflicting duplicate order')
   continue
  seen[ident]=r
  stamp=datetime.fromisoformat(r['created_at'].replace('Z','+00:00'))
  if stamp.tzinfo is None:
   if p.get('timezone')!='Europe/Moscow':raise ValueError('Order timezone unknown')
   stamp=stamp.replace(tzinfo=MSK)
  stamp=stamp.astimezone(MSK)
  if stamp.date()!=day or stamp>observed:raise ValueError('Order outside source window')
  b=bins[stamp.hour];b['orders']+=1
  if r.get('cancelled') is True:b['cancelled']+=1
  try:a=money_cny(w,r.get('amount'),currency,day,rates)
  except Exception:a=None
  if a is None:b['amount_complete']=False
  else:b['amount']+=a
 last_hour=observed.hour if observed.date()==day else 23
 rows=[]
 for h in range(last_hour+1):
  b=bins[h];a=b.pop('amount');b['amount_cny']=float(a) if b.pop('amount_complete') else None
  b['average_cny']=float(a/b['orders']) if b['orders'] and b['amount_cny'] is not None else None
  b['complete_hour']=observed.date()>day or h<observed.hour;rows.append(b)
 return dict(rows=rows,observed_at=p['observed_at'],source=p['source'],source_key=p.get('source_key'),
  cabinet='token_3',currency='CNY',rates=rates,order_basis=p.get('order_basis','created_all_statuses'),
  wb_writes=0,available=True)

def requested(text,history):
 if re.search(r'по\s*час|почас|разбивк.*час',text,re.I):return True
 if re.search(r'сумм|средн.*чек',text,re.I):
  return any(re.search(r'по\s*час|почас',h.get('request_text',''),re.I) for h in history[-3:])
 return False

def handle(w,job,history=()):
 text=job.get('request_text','')
 if not requested(text,history):return None
 day=w.now.astimezone(MSK).date()-timedelta(days=1 if re.search(r'вчера',text,re.I) else 0)
 key=ROOT+str(day);p=w.get(key)
 if not p:
  raw=w.get('china_agent:intraday_orders:'+str(day))
  if raw and raw.get('status')=='complete':
   p=dict(raw,complete=True,currency='CNY',timezone='Europe/Moscow',
    source_key='china_agent:intraday_orders:'+str(day),
    rows=[dict(order_id=r['srid'],nm_id=r['nmId'],created_at=r['date'],amount=None,cancelled=r.get('isCancel')) for r in raw['rows']])
 try:
  data=hourly(w,p,day)
  stamp=datetime.fromisoformat(data['observed_at']).astimezone(MSK).strftime('%d.%m %H:%M')
  lines=[f'Китай, {day}; срез {stamp} МСК. Заказы по времени оформления, не выкупы. Суммы в CNY.',
   'Час | заказы | сумма CNY | средний чек CNY']
  def n(v):return 'нет данных' if v is None else f'{v:.2f}'
  for r in data['rows']:
   marker=' (неполный)' if not r['complete_hour'] else ''
   lines.append(f'{r["hour"]:02d}–{r["hour"]+1:02d}{marker} | {r["orders"]} | {n(r["amount_cny"])} | {n(r["average_cny"])}')
  lines.append('Учтены созданные заказы всех статусов; отмены не вычитаются из оформлений. Источник: '+data['source']+'.')
  if data['rates']:
   lines.append('RUB пересчитаны по ЦБ: '+'; '.join(f'{r["effective_date"]}: {r["rub_per_cny"]} RUB за 1 CNY' for r in data['rates'].values()))
  lines.append('Почасовых посещений за те же часы в этом источнике нет: почасовую конверсию не вычисляю. Дневные посещения, рекламные клики и снимки с пересчётом атрибуции её не заменяют. Количество и средний чек объясняют сумму арифметически, но не доказывают причину изменения спроса.')
  return '\n'.join(lines),[dict(name='hourly_orders_evidence',result=data,read_only=True)]
 except Exception as exc:
  return ('Полной проверенной почасовой выгрузки за '+str(day)+' нет: '+str(exc)+'. Конверсию без посещений за те же часы не вычисляю; неизвестные суммы не ноль. Перевод валюты не исправляет чужой кабинет.',[dict(name='hourly_orders_evidence',result=dict(available=False,error=type(exc).__name__,wb_writes=0),read_only=True)])
