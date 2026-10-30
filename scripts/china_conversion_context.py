"""Read-only conversion answers, including context-bound period follow-ups."""
import math,re
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow')
ROOT='china_agent:conversion_overview:v1:'
WEEK_ROOT='china_agent:conversion_week_overview:v1:'
EXCLUDED=r'что такое|что значит|объясни термин|реклам|кампан|\bрк\b|[0-9]+-[a-z]|ставк|бюджет|пополн|цен[ауые]|выкуп|органическ'
def intent(text,history=()):
 if re.search(EXCLUDED,text,re.I):return None
 topic=bool(re.search(r'конверс|карточк.*корзин|корзин.*заказ',text,re.I))
 period=bool(re.search(r'недел|дней|сегодня|сейчас|вчера',text,re.I))
 if not topic and period and re.search(r'сравн|средн|а за|а если|а вчера',text,re.I):
  for h in reversed(list(history)[-4:]):
   q=h.get('request_text','')
   if not q or q==text:continue
   if re.search(EXCLUDED,q,re.I):break
   if re.search(r'конверс|карточк.*корзин|корзин.*заказ',q,re.I):topic=True;break
   if not re.search(r'сравн|средн|а за|а если|а вчера',q,re.I):break
 if not topic or not period:return None
 if re.search(r'недел',text,re.I):
  if re.search(r'две|2\s*недел',text,re.I):return 14
  if re.search(r'прошл|календар',text,re.I):return None
  return 7
 m=re.search(r'(7|14|30)\s*(?:полных\s*|завершённых\s*)?дн',text,re.I)
 if m:return int(m[1])
 if re.search(r'сегодня|сейчас|вчера',text,re.I):return 1
 return None
def is_question(text):return intent(text) is not None
def metrics(row):
 values=[row.get(k) for k in ('views','carts','orders')]
 if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in values):raise ValueError('Incomplete funnel counters')
 views,carts,orders=values
 return dict(row,card_cart_pct=100*carts/views if views else None,cart_order_pct=100*orders/carts if carts else None,card_order_pct=100*orders/views if views else None)
def fresh(w,p):
 try:return 0<=(w.now-datetime.fromisoformat(p['observed_at'])).total_seconds()<=1200
 except (KeyError,TypeError,ValueError):return False
def valid(p):return bool(p and p.get('cabinet')=='token_3' and p.get('complete') is True and p.get('scope')=='all_sources')
def total(state,part,first,last):
 if not state.get('complete') or state.get('cabinet')!='token_3' or not state.get('rows'):raise ValueError('Incomplete cabinet funnel')
 result=dict(period_from=str(first),period_to=str(last),views=0,carts=0,orders=0)
 seen=set()
 for row in state['rows']:
  nm=row['nm_id']
  if nm in seen:raise ValueError('Duplicate product row')
  seen.add(nm);r=row[part]
  if r.get('period_from')!=str(first) or r.get('period_to')!=str(last) or r.get('scope')!='all_sources':raise ValueError('Funnel period/scope mismatch')
  values=metrics(dict(views=r.get('clicks'),carts=r.get('cart_count'),orders=r.get('orders')))
  for key in ('views','carts','orders'):result[key]+=values[key]
 return metrics(result)
def read(w,first,last):
 from china_analytic_dialog import reading
 from china_wb_evidence import Reports
 with reading():return Reports(w).funnel(str(first),str(last))
def collect(w):
 day=w.now.astimezone(MSK).date();prior=day-timedelta(days=1);cached=w.get(ROOT+str(day))
 if valid(cached) and fresh(w,cached) and cached.get('current',{}).get('day')==str(day) and cached.get('previous',{}).get('day')==str(prior):
  return dict(cached,current=metrics(cached['current']),previous=metrics(cached['previous']),cached=True,matched_clock=False)
 state=read(w,day,day)
 result=dict(current=dict(total(state,'selected',day,day),day=str(day)),previous=dict(total(state,'past',prior,prior),day=str(prior)),observed_at=state['observed_at'],source=state.get('source'),source_key=state.get('source_key'),cabinet='token_3',scope='all_sources',complete=True,matched_clock=False,cached=False)
 w.save(ROOT+str(day),result);return result
def collect_period(w,days):
 day=w.now.astimezone(MSK).date();first=day-timedelta(days=days);last=day-timedelta(days=1)
 key=WEEK_ROOT+str(day) if days==7 else WEEK_ROOT+str(day)+':'+str(days)
 cached=w.get(key)
 if valid(cached) and fresh(w,cached) and cached.get('period')=={'from':str(first),'to':str(last)} and (cached.get('current',{}).get('day') or cached.get('current',{}).get('date'))==str(day):
  return dict(cached,current=metrics(cached['current']),previous=metrics(cached['totals']),cached=True,days=days)
 # Compatibility with the privately verified UI observation schema.
 if valid(cached) and fresh(w,cached) and cached.get('period')=={'from':str(first),'to':str(last)} and cached.get('current',{}).get('date')==str(day):
  return dict(cached,current=metrics(cached['current']),previous=metrics(cached['totals']),days=days,cached=True)
 current=collect(w)
 try:
  state=read(w,first,last);previous=total(state,'selected',first,last)
 except Exception as exc:
  return dict(current,days=days,comparison_available=False,comparison_error=type(exc).__name__,period={'from':str(first),'to':str(last)})
 result=dict(current,previous=previous,days=days,period={'from':str(first),'to':str(last)},comparison_observed_at=state['observed_at'],comparison_source_key=state.get('source_key'),comparison_available=True)
 w.save(key,dict(result,totals=previous))
 return result
def render(data):
 cur,old=data['current'],data['previous']
 def n(v):return f'{v:,.0f}'.replace(',',' ')
 def pct(v):return 'не определена' if v is None else f'{v:.2f}%'.replace('.',',')
 at=datetime.fromisoformat(data['observed_at']).astimezone(MSK).strftime('%d.%m %H:%M')
 lines=[f'Общая воронка WB, срез {at} МСК: {n(cur["views"])} переходов, {n(cur["carts"])} корзин, {n(cur["orders"])} заказанных товаров.',
 f'Карточка→корзина {pct(cur["card_cart_pct"])}, корзина→заказ {pct(cur["cart_order_pct"])}, карточка→заказ {pct(cur["card_order_pct"])}.']
 if data.get('comparison_available') is False:
  lines.append('Воронку за запрошенный завершённый период запросила, но полный подтверждённый ответ не получен. Недельное сравнение не вычисляю; отсутствие данных не ноль.')
 else:
  if data.get('days',1)>1:
   p=data['period'];label=f'За {data["days"]} завершённых дней {p.get("from",p.get("from_"))}–{p["to"]}'
   lines.append(f'{label}: {n(old["views"])} переходов, {n(old["carts"])} корзин, {n(old["orders"])} заказанных товаров.')
  else:label=f'За полный предыдущий день {old["day"]}'
  lines.append(f'{label}: {pct(old["card_cart_pct"])}, {pct(old["cart_order_pct"])} и {pct(old["card_order_pct"])} соответственно.')
  if cur['cart_order_pct'] is not None and old['cart_order_pct'] is not None and cur['cart_order_pct']<old['cart_order_pct']:
   lines.append('Текущий показатель корзина→заказ ниже этого ориентира.')
 lines.append('Проценты рассчитаны из суммарных счётчиков, не средним процентов товаров или дней. Сегодня день неполный; сумки могут покупать позже, WB догружает данные. Это ориентир: сравнения до того же часа нет, окончательный вывод о падении или росте конверсии за день не подтверждён.')
 return '\n'.join(lines)
def requested_day(w,text,history=()):
 context=text
 if re.search(r'хочу общий|а общий|за день|за \d{1,2} число',text,re.I):
  context=' '.join(h.get('request_text','') for h in history[-4:])+' '+text
 today=w.now.astimezone(MSK).date()
 full=re.findall(r'(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)',context)
 short=re.findall(r'за\s+(\d{1,2})(?:\s+число|[.]([01]?\d)(?:[.](\d{4}))?)',context,re.I)
 if full:return datetime.fromisoformat(full[-1]).date()
 if short:
  d,m,y=short[-1];return today.replace(day=int(d),month=int(m) if m else today.month,year=int(y) if y else today.year)
 if re.search(r'вчера',text,re.I):return today-timedelta(days=1)
 return None

def completed_day(w,day):
 if day>=w.now.astimezone(MSK).date():raise ValueError('Requested completed day is not closed')
 state=read(w,day,day);row=total(state,'selected',day,day)
 def pct(v):return 'не определена' if v is None else f'{v:.2f}%'.replace('.',',')
 at=datetime.fromisoformat(state['observed_at']).astimezone(MSK).strftime('%d.%m %H:%M')
 text=(f'Общая воронка WB за полный {day}, срез {at} МСК: {row["views"]} переходов, {row["carts"]} корзин, {row["orders"]} заказанных товаров. '
       f'Карточка→корзина {pct(row["card_cart_pct"])}, корзина→заказ {pct(row["cart_order_pct"])}, карточка→заказ {pct(row["card_order_pct"])}. '
       'Проценты из суммарных счётчиков, не среднее процентов SKU. Это общая воронка, рекламные заказы отдельно.')
 return text,[dict(name='conversion_funnel_evidence',requested_date=str(day),result=dict(row,observed_at=state['observed_at'],source_key=state.get('source_key'),cabinet='token_3'),read_only=True)]

def handle(w,job,history=()):
 from china_intraday_analysis import handle as hourly_handle
 hourly_reply=hourly_handle(w,job,history)
 if hourly_reply is not None:return hourly_reply
 text=job.get('request_text','')
 context_conversion=any(re.search(r'конверс|показатель.*число',h.get('request_text',''),re.I) for h in history[-4:])
 try:
  day=requested_day(w,text,history)
  if day and not re.search(EXCLUDED,text,re.I) and (intent(text,history) is not None or context_conversion):return completed_day(w,day)
 except Exception as exc:
  return ('Общую конверсию за запрошенный полный день пока не подтвердил: '+type(exc).__name__+'. Сегодняшний срез не подставляю вместо него.',[dict(name='conversion_funnel_evidence',result=dict(available=False,error=type(exc).__name__),read_only=True)])
 days=intent(job.get('request_text',''),history)
 if days is None:return None
 try:
  data=collect_period(w,days) if days>1 else collect(w)
  return render(data),[dict(name='conversion_funnel_evidence',requested_completed_days=days,result=data,read_only=True)]
 except Exception as exc:
  result=dict(available=False,source='WB general funnel',error=type(exc).__name__,wb_writes=0)
  return ('Запрос общей воронки WB не дал полного подтверждённого среза. Конверсию и её изменение пока не вычисляю: неполные данные не ноль. Снижение количества заказов само по себе не доказывает снижение конверсии.',[dict(name='conversion_funnel_evidence',requested_completed_days=days,result=result,read_only=True)])
