"""Deterministic China break-even analysis. Saved reads only; never writes/sends."""
import re
from datetime import datetime,timedelta
from decimal import Decimal,ROUND_CEILING
from zoneinfo import ZoneInfo
from china_expected_order_profit import dec,buyout_from_product
MSK=ZoneInfo('Europe/Moscow')
def intent(text):
 return bool(re.search(r'безубыт|безубыточ|break.?even',text,re.I))
def resolve(text,catalogue):
 value=text.casefold()
 exact=[(str(n),a) for n,a in catalogue if re.search(r'(?<![\w-])'+re.escape(a.casefold())+r'(?![\w-])',value)]
 if not exact:
  exact=[(str(n),a) for n,a in catalogue if re.search(r'(?<!\d)'+str(n)+r'(?!\d)',value)]
 if not exact:
  codes=re.findall(r'(?:артикул\w*|арт[.:]?)\s*(\d{1,6})(?!\d)|(\d{1,6})\s*(?:артикул\w*|арт\b)',value)
  numbers={x or y for x,y in codes}
  exact=[(str(n),a) for n,a in catalogue if a.split('-')[0] in numbers]
 if not exact:
  stripped=re.sub(r'\b\d{4}-\d{2}-\d{2}\b|\d+\s*%|(?:за|последни\w*)\s+\d+\s+дн\w*','',value)
  numbers=re.findall(r'(?<![\w-])\d{1,6}(?![\w-])',stripped)
  if len(numbers)==1:exact=[(str(n),a) for n,a in catalogue if a.split('-')[0]==numbers[0]]
 if len(exact)!=1:raise ValueError('Укажите один точный артикул: короткий номер неоднозначен или товар не найден.')
 return exact[0]
def windows(text,now):
 end=now.astimezone(MSK).date()-timedelta(days=1)
 dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',text)
 if dates:
  if len(dates)!=2:raise ValueError('Укажите обе даты периода в формате ГГГГ-ММ-ДД.')
  start,end=map(lambda s:datetime.fromisoformat(s).date(),dates)
 else:
  m=re.search(r'(?:за|последни\w*)\s+(\d+)\s+(?:полн\w+\s+)?дн',text,re.I)
  start=end-timedelta(days=(int(m[1]) if m else 30)-1)
 if not 1<=(end-start).days+1<=90 or end>=now.astimezone(MSK).date():raise ValueError('Нужен период до90 полных прошедших дней.')
 return start,end
def calculate(cost,dispatch,ads_per_order,reserve_per_order,probability,commission,tax,buyer_ratio,fx,discount):
 p=dec(probability);comm=dec(commission);tax=dec(tax);factor=1-dec(discount)/100
 if not 0<=p<=1 or not 0<=comm<1 or not 0<=tax<1 or not 0<factor<=1 or dec(fx)<=0:
  raise ValueError('Invalid break-even parameters')
 numerator=p*dec(cost)+dec(dispatch)+dec(reserve_per_order)
 output=[]
 for label,drr in (('current',Decimal(0)),('drr5_orders',Decimal('.05'))):
  denominator=p*(1-comm-tax*dec(buyer_ratio))-drr
  fixed=dec(ads_per_order) if label=='current' else Decimal(0)
  if denominator<=0:
   output.append(dict(scenario=label,status='no_finite_break_even'));continue
  raw=(numerator+fixed)/denominator/dec(fx)
  base=(raw/factor).to_integral_value(rounding=ROUND_CEILING)
  after=base*factor
  output.append(dict(scenario=label,status='calculated',raw_after_cny=float(raw),base_cny=int(base),seller_after_cny=float(after),
   buyer_rub=int((after*dec(fx)*dec(buyer_ratio)).quantize(Decimal('1')))))
 return output
def _latest_audits(w,prefix):
 rows=w.db('GET','telegram_api_cache',params={'cache_key':'like.'+prefix+'*','select':'cache_key,payload,updated_at','order':'updated_at.desc','limit':100}) or []
 if len(rows)>=100:raise ValueError('Audit list incomplete')
 return rows
def finance(w,start,end):
 for item in _latest_audits(w,'china_agent:commission_return_audit:'):
  p=item['payload']
  if p.get('status')!='complete' or p.get('cabinet')!='token_3' or not p.get('terminal_204'):continue
  if p.get('period_from','z')>str(start) or p.get('period_to','')<str(end):continue
  rows=[]
  for page in p.get('pages',[]):
   saved=w.get(page['cache_key']) or {}
   part=saved.get('rows',[])
   if saved.get('cabinet')!='token_3' or len(part)!=page['rows']:raise ValueError('Finance audit page incomplete')
   rows+=part
  if len(rows)!=p['row_count'] or len({r['rrdId'] for r in rows})!=len(rows):raise ValueError('Finance audit integrity failure')
  return [r for r in rows if str(start)<=r.get('rrDate','')[:10]<=str(end)],item['cache_key']
 return [],None
def overhead(w,start,end):
 for item in _latest_audits(w,'china_agent:economics_audit:'):
  p=item['payload'].get('extra_reads') or {}
  if p.get('cabinet')!='token_3':continue
  daily=(p.get('reports',{}).get('lk_wb_dashboard_table',{}).get('data') or {}).get('data')
  wanted=[str(start+timedelta(days=i)) for i in range((end-start).days+1)]
  if not isinstance(daily,dict) or any(d not in daily for d in wanted):continue
  return sum((dec(daily[d].get('deduction')) for d in wanted),Decimal(0)),item['cache_key']
 return None,None
def answer(w,job,history=()):
 text=job['request_text']
 if not intent(text):return None
 trace=[]
 try:
  nm,article=resolve(text,w.catalog())
  start,end=windows(text,w.now)
  from analytics.mpstats_primary import products
  rows,marker=products(lambda t,p:w.db('GET',t,params=p),'token_3',start,end,w.now)
  if not marker:raise ValueError('Нет проверенного полного среза расходов за '+str(start)+'–'+str(end)+'. Нужен срез, а не повторный ввод себестоимости.')
  matched=[r for r in rows if str(r['nm_id'])==nm and r['sa_name'].casefold()==article.casefold()]
  if len(matched)!=1:raise ValueError('Экономика точного артикула не подтверждена.')
  product=matched[0];rate=buyout_from_product(product)
  costs=w.db('GET','analytics_costs',params={'article':'eq.'+article,'select':'article,cost,observed_at','limit':2}) or []
  if len(costs)!=1 or dec(costs[0]['cost'])<=0:raise ValueError('Не найдена собственная себестоимость '+article+'.')
  model=w.get('china_agent:expected_profit_delivery_model:v1') or {}
  if model.get('cabinet')!='token_3':raise ValueError('Не подтверждены параметры доставки Китая.')
  fx=dec(model.get('rub_per_cny'));handling=dec(model.get('acceptance_rub_per_dispatch'))
  current=w.get('china_agent:prices:v1') or {}
  if current.get('cabinet')!='token_3' or datetime.fromisoformat(current['observed_at']).astimezone(MSK).date()!=w.now.astimezone(MSK).date():raise ValueError('Нет сегодняшней сохранённой цены Китая.')
  price_rows=[r for r in current.get('rows',[]) if str(r.get('nmID'))==nm and r.get('vendorCode')==article]
  if len(price_rows)!=1:raise ValueError('Неоднозначная текущая цена.')
  price=price_rows[0];sizes=price.get('sizes') or []
  values={dec(s.get('discountedPrice')) for s in sizes}
  if price.get('currencyIsoCode4217')!='CNY' or len(values)!=1:raise ValueError('Цена размеров или валюта не подтверждены.')
  current_cny=values.pop();buyer=dec(product.get('price_after_spp'))
  if current_cny<=0 or buyer<=0:raise ValueError('Нет положительной покупательской цены.')
  ratio=buyer/(current_cny*fx)
  raw,key=finance(w,start,end)
  own=[r for r in raw if str(r.get('nmId'))==nm and r.get('vendorCode')==article]
  fees=[r for r in own if r.get('sellerOperName')=='销售']
  if fees:
   commissions={dec(r.get('commissionPercent'))/100 for r in fees}
   acquiring={dec(r.get('acquiringFee')) for r in fees}
   if len(commissions)!=1 or acquiring!={Decimal(0)}:raise ValueError('Ставка комиссии или отдельный эквайринг требуют сверки.')
   commission=commissions.pop()
  else:
   gross=dec(product.get('sales_ret_sum'))
   if gross<=0:raise ValueError('Фактическая комиссия артикула пока не установлена.')
   commission=(dec(product.get('total_commission_without_spp'))+dec(product.get('acquiring')))/gross
  logistics=[dec(r['deliveryService']) for r in own if r.get('sellerOperName')=='配送' and dec(r.get('deliveryService'))>0]
  if logistics:delivery=sum(logistics)/len(logistics);delivery_source='WB Finance CNY'
  else:
   value=(model.get('rows',{}).get(article) or {}).get('delivery_cny')
   if value is None:raise ValueError('Нет ни фактической, ни согласованной расчётной доставки артикула.')
   delivery=dec(value);delivery_source='согласованный расчётный тариф'
  net_sales=dec(product.get('sales_sum'))-dec(product.get('returns_sum'))
  if net_sales<=0:raise ValueError('Налоговая ставка по сохранённым продажам не установлена.')
  tax=(dec(product.get('taxes'))/net_sales).quantize(Decimal('.0001'))
  n=dec(product.get('orders_count'));all_orders=sum((dec(r.get('orders_count')) for r in rows),Decimal(0))
  ads=dec(product.get('advertisement'))
  if n<=0:raise ValueError('Нет заказов для расчёта рекламного расхода на заказ.')
  deductions,overhead_source=overhead(w,start,end)
  if deductions is None or all_orders<=0:raise ValueError('Не получены общие удержания за тот же период; полный порог пока не подтверждён.')
  own_deductions=sum((dec(r.get('deduction')) for r in rows),Decimal(0))
  reserve=max(Decimal(0),deductions-own_deductions)/all_orders+dec(product.get('deduction'))/n
  extra=sum((dec(product.get(k)) for k in ('penalty','storage_fee','acceptance','total_cashback')),Decimal(0))/n
  reserve+=extra
  scenarios=calculate(costs[0]['cost'],delivery*fx+handling,ads/n,reserve,rate['probability'],commission,tax,ratio,fx,price['discount'])
  fmt=lambda v:format(dec(v).quantize(Decimal('.01')),'f').replace('.',',')
  percent=fmt(rate['percent'])
  lines=[article+' · WB '+nm,str(start)+'–'+str(end)+' · полные дни МСК',
   'Выкуп сейчас: '+percent+'%'+(' — '+str(product.get('is_payed',0))+' из '+str(rate['sample_size'])+' завершённых заказов.' if rate['source']=='own_article' else ' — принято для расчёта, собственной завершённой статистики нет.'),
   'Незавершённые заказы не включены в знаменатель.'+(' Выборка небольшая.' if 0<rate['sample_size']<10 else ''),
   'Цена безубыточности, продавец после скидки:']
  for s in scenarios:
   label='При текущем расходе на рекламу ('+fmt(ads)+' ₽ за период)' if s['scenario']=='current' else 'При ДРР 5% от суммы заказов до скидки WB'
   lines.append(label+': '+(fmt(s['seller_after_cny'])+' ¥; покупатель ≈'+str(s['buyer_rub'])+' ₽ (прогноз).' if s['status']=='calculated' else 'конечной безубыточной цены нет при текущем выкупе/расходах.'))
  lines+=['Текущая цена продавца: '+fmt(current_cny)+' ¥. Скидка продавца '+str(price['discount'])+'%.',
   'Учтено: себестоимость '+fmt(costs[0]['cost'])+' ₽; комиссия '+fmt(commission*100)+'%; налог '+fmt(tax*100)+'% (настройка MPStats); доставка '+fmt(delivery*fx)+' ₽/заказ; обработка '+fmt(handling)+' ₽/заказ; резерв общих удержаний '+fmt(reserve)+' ₽/заказ.',
   'Обычный возврат на склад WB в России включён в доставку. Доставка: '+delivery_source+'. Курс расчёта '+fmt(fx)+' ₽/¥.',
   'Общие удержания распределены по числу заказов — расчётный резерв, а не установленный расход именно этого товара. Возможное пересечение с оплатой WB Promotion пока не исключено.',
   'Скидки WB для прогноза покупательской цены считаются неизменными. Целевая прибыль 30% в пороги не заложена. Цены не менялись.']
  trace=[dict(name='china_break_even',version=1,nm_id=nm,article=article,period_from=str(start),period_to=str(end),source_snapshot_id=marker['id'],finance_audit=key,overhead_source=overhead_source,
   buyout={k:v for k,v in rate.items() if k!='probability'},scenarios=scenarios,ads=float(ads),orders=float(n),shared_reserve_per_order=float(reserve),wb_writes=0)]
  return '\n'.join(lines),trace
 except (ValueError,KeyError,TypeError,ArithmeticError) as exc:
  return 'Расчёт безубыточности пока не завершён: '+str(exc)+' Пропуски не считаются нулями. Цены не менялись.',[dict(name='china_break_even',status='incomplete',detail=str(exc),wb_writes=0)]
