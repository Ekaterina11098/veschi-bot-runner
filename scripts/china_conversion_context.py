"""Ground current cabinet-conversion answers in actual read evidence."""
import math,re
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow')
ROOT='china_agent:conversion_overview:v1:'
def is_question(text):
 return bool(re.search(r'конверс',text,re.I) and re.search(r'сегодня|сейчас',text,re.I) and re.search(r'хуже|лучше|сравн|средн|какая|как|сколько',text,re.I) and not re.search(r'что такое|что значит|объясни термин|реклам|кампан|\\bрк\\b|[0-9]+-[a-z]',text,re.I))
def metrics(row):
 values=[row.get(k) for k in ('views','carts','orders')]
 if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in values):raise ValueError('Incomplete funnel counters')
 views,carts,orders=values
 return dict(row,card_cart_pct=100*carts/views if views else None,cart_order_pct=100*orders/carts if carts else None,card_order_pct=100*orders/views if views else None)
def collect(w):
 day=w.now.astimezone(MSK).date();prior=day-timedelta(days=1)
 cached=w.get(ROOT+str(day))
 if cached and cached.get('cabinet')=='token_3' and cached.get('complete') is True and cached.get('scope')=='all_sources' and cached.get('current',{}).get('day')==str(day) and cached.get('previous',{}).get('day')==str(prior):
  age=(w.now-datetime.fromisoformat(cached['observed_at'])).total_seconds()
  if 0<=age<=1200:
   return dict(cached,current=metrics(cached['current']),previous=metrics(cached['previous']),cached=True,matched_clock=False)
 from china_analytic_dialog import reading
 from china_wb_evidence import Reports
 with reading():state=Reports(w).funnel(str(day),str(day))
 if not state.get('complete'):raise RuntimeError('WB funnel incomplete or unavailable; no cabinet ratio computed')
 rows=state.get('rows',[])
 if not rows:raise RuntimeError('WB funnel returned no product rows; unknown is not zero')
 out={}
 for part,d in [('selected',day),('past',prior)]:
  total=dict(day=str(d),views=0,carts=0,orders=0)
  for row in rows:
   r=row[part]
   if r.get('period_from')!=str(d) or r.get('period_to')!=str(d):raise ValueError('WB funnel period mismatch')
   checked=metrics(dict(views=r.get('clicks'),carts=r.get('cart_count'),orders=r.get('orders')))
   for key in ('views','carts','orders'):total[key]+=checked[key]
  out['current' if part=='selected' else 'previous']=metrics(total)
 result=dict(out,observed_at=state['observed_at'],source=state.get('source'),source_key=state.get('source_key'),cabinet='token_3',scope='all_sources',complete=True,matched_clock=False,cached=False,update_delay_hours=state.get('update_delay_hours',2))
 w.save(ROOT+str(day),result)
 return result
def render(data):
 cur,old=data['current'],data['previous']
 def n(v):return f'{v:,.0f}'.replace(',',' ')
 def pct(v):return 'не определена' if v is None else f'{v:.2f}%'.replace('.',',')
 at=datetime.fromisoformat(data['observed_at']).astimezone(MSK).strftime('%d.%m %H:%M')
 lines=[f'Общая воронка WB, срез {at} МСК: {n(cur["views"])} переходов, {n(cur["carts"])} корзин, {n(cur["orders"])} заказанных товаров.',
 f'Карточка→корзина {pct(cur["card_cart_pct"])}, корзина→заказ {pct(cur["cart_order_pct"])}, карточка→заказ {pct(cur["card_order_pct"])}.',
 f'За полный предыдущий день {old["day"]}: {pct(old["card_cart_pct"])}, {pct(old["cart_order_pct"])} и {pct(old["card_order_pct"])} соответственно.']
 if cur['cart_order_pct'] is not None and old['cart_order_pct'] is not None and cur['cart_order_pct']<old['cart_order_pct']:
  lines.append('В текущем срезе слабее переход из корзины в заказ относительно вчерашнего суточного уровня.')
 lines.append('Сегодня день неполный; покупки могут быть отложенными, WB догружает данные. Это предварительный ориентир: вчерашнего среза до того же часа нет, окончательный вывод о падении или росте конверсии за день не подтверждён.')
 return '\n'.join(lines)
def handle(w,job):
 if not is_question(job.get('request_text','')):return None
 try:
  data=collect(w)
  return render(data),[dict(name='conversion_funnel_evidence',result=data,read_only=True)]
 except Exception as exc:
  result=dict(available=False,source='WB general funnel',error=type(exc).__name__,wb_writes=0)
  return ('Проверка общей воронки WB выполнена, но полный подтверждённый срез не получен. Конверсию и её изменение пока не вычисляю: неполные данные не ноль. Снижение количества заказов само по себе не доказывает снижение конверсии.',[dict(name='conversion_funnel_evidence',result=result,read_only=True)])
