"""One evidence-first article decision path. Pure evaluation; no execution or delivery."""
import math,re
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow')
FIELDS=('views','clicks','baskets','orders','spend','amount')
RULES=('Перед конкретной рекомендацией по артикулу используй diagnose_article: наличие МСК, '
'доступность варианта, показы, клики, корзины, заказы, экономика и журнал изменений. '
'Только завершённые дни после последнего verified изменения для выбора нового действия; сегодняшний трафик отдельно. '
'Не передавай владельцу задания получить тариф, сравнить цену или проверить видимость: сначала используй источники сам. '
'Если готового действия нет, рекомендация ровно «Нет», а конкретный пробел укажи отдельно. '
'Сценарий малого трафика не доказанная низкая ДРР; прогноз не фактическая прибыль. '
'Диагностика не создаёт план исполнения, подтверждение, расписание или WB-запись.')
def number(x):return type(x) in (int,float) and math.isfinite(x)
def at(value):
 try:
  d=datetime.fromisoformat(value.replace('Z','+00:00'))
  return d if d.tzinfo else None
 except (AttributeError,ValueError,TypeError):return None
def fresh(source,now,seconds=900):
 t=at((source or {}).get('observed_at'))
 return t is not None and 0<=(now-t).total_seconds()<=seconds
def scope(w,job,history):
 labels={int(n):a for n,a in w.catalog()};text=job.get('request_text','')
 def find(t):return [n for n,a in labels.items() if re.search(r'(?<![\w-])'+re.escape(a)+r'(?![\w-])',t,re.I) or re.search(r'(?<!\d)'+str(n)+r'(?!\d)',t)]
 ids=find(text)
 if ids:return ids
 # An unknown explicit SKU cannot silently inherit a previous article.
 if re.search(r'\b\d{1,4}-[a-z][a-z0-9_-]+',text,re.I):return []
 m=next((x for x in job.get('tool_trace',[]) if x.get('name')=='china_saved_question'),{})
 parent=m.get('parent_job_id')
 context=[h for h in history if h.get('id')==parent] if parent else history[-1:]
 return find(m.get('reply_text','')) or (find(context[-1].get('request_text','')) if context else [])
def requested(text):
 if re.search(r'\b(?:делай|сделай|выполни|согласен|поднимай|подними|повысь|подтверждаю|применяй|следи|наблюдай|напомни)\b',text,re.I):return False
 if re.search(r'(?:давай|давайте)\s+(?:подним|повыс|примен|попол)',text,re.I):return False
 if re.search(r'сколько|когда.*цен|прибыл|зарплат|заказы.*после.*повыш|были.*продаж',text,re.I):return False
 return bool(re.search(r'проанализ|разбер|диагност|нет.*(?:показ|клик)|мало.*показ|почему.*(?:заказ|прода)|что.*(?:сделать|предлож|рекоменд)|рекомендац|запуст.*продаж|провер.*видим|почему.*ставк|не\s*откруч',text,re.I))
def aggregate(days):
 out={k:0 for k in FIELDS}
 if not days:return {k:None for k in FIELDS}
 for d in days:
  for k in FIELDS:
   x=d.get(k)
   out[k]=None if out[k] is None or not number(x) or x<0 else out[k]+x
 out['drr_pct']=100*out['spend']/out['amount'] if out['amount'] and out['spend'] is not None else None
 out['ctr_pct']=100*out['clicks']/out['views'] if out['views'] and out['clicks'] is not None else None
 return out
def economics(f,target):
 p=f.get('price',{});s=f.get('stock',{});e=f.get('economy',{})
 price=p.get('seller_cny');cost=s.get('cogs_cny');shipping=e.get('logistics_cny');q=e.get('buyout');fee=e.get('commission_pct');tax=e.get('tax_pct',5);handling=e.get('handling_cny',10/12)
 required=[price,cost,shipping,q,fee,tax,handling,target]
 if not all(number(x) for x in required) or price<=0 or cost<=0 or shipping<0 or not 0<q<=1 or not 0<=fee<100 or not 0<=tax<100 or handling<0:return dict(available=False,reason='Цена/собственная COGS/логистика/выкуп/комиссия неполны')
 pre=q*(price*(1-(fee+tax)/100)-cost)-shipping-handling
 scenarios=[dict(click_order_pct=cr,ad_cost_per_order_cny=round(target/(cr/100),4),profit_per_order_cny=round(pre-target/(cr/100),4),profit_per_buyout_cny=round((pre-target/(cr/100))/q,4)) for cr in [1,2,3]]
 return dict(available=True,buyout=q,completed_sample=e.get('completed_sample'),logistics_source=e.get('logistics_source'),pre_ad_per_order_cny=round(pre,4),scenarios=scenarios,scenario_not_measured_forecast=True,unknown_reverse_and_shared_charges=True)
def evaluate(f,now,days=3,raise_percent=10):
 if not 2<=days<=14 or not number(raise_percent) or not 0<raise_percent<=30:raise ValueError('Нужны 2–14 полных дней и сценарий повышения до30%')
 today=now.astimezone(MSK).date();last=today-timedelta(days=1);first=last-timedelta(days=days-1)
 changes=[x for x in f.get('changes',[]) if x.get('verified') is True and at(x.get('at'))]
 verified_day=max((at(x['at']).astimezone(MSK).date() for x in changes),default=None)
 availability=[at(x.get('at')).astimezone(MSK).date() for x in f.get('availability_events',[]) if x.get('source')=='human_statement' and at(x.get('at'))]
 latest=max(([verified_day] if verified_day else [])+availability,default=None)
 review=latest+timedelta(days=2) if latest else None
 dates=[str(first+timedelta(days=i)) for i in range(days) if latest is None or first+timedelta(days=i)>latest]
 observations={d['date']:d for d in f.get('daily',[]) if first.isoformat()<=d.get('date','')<=last.isoformat()}
 traffic=aggregate([observations[d] for d in dates]) if all(d in observations for d in dates) else aggregate([])
 gaps=list(f.get('gaps',[]))
 out=dict(nm_id=f['nm_id'],article=f['article'],campaign_id=f.get('campaign',{}).get('id'),placement=f.get('campaign',{}).get('placement'),period_from=str(first),period_to=str(last),eligible_dates=dates,latest_verified_change=str(verified_day) if verified_day else None,last_availability_statement=str(max(availability)) if availability else None,review_from=str(review) if review else None,traffic=traffic,today_observation=f.get('today_observation'),all_source=f.get('all_source'),evidence={k:f.get(k,{}) for k in ['price','stock','campaign','visibility','quality','economy']},recommendation='Нет',action=None,stage='unknown',gaps=gaps,economics=None,execution_authorized=False,wb_writes=0)
 if f.get('unresolved_action'):
  out.update(stage='uncertain_action',reason='Есть незавершённая или uncertain операция по SKU; повтор и новый тест заблокированы до сверки');return out
 if not dates:
  out.update(stage='observe_change',reason='После изменения ещё не завершён первый полный день МСК' if verified_day==latest else 'После сообщения владельца о восстановлении наличия ещё не завершён первый полный день МСК; сообщение не является WB-квитанцией');return out
 if not f.get('history_checked'):
  gaps.append('Журнал выполненных действий не подтверждён')
 stock=f.get('stock',{});price=f.get('price',{});camp=f.get('campaign',{});card=f.get('visibility',{});quality=f.get('quality',{})
 if fresh(stock,now) and number(stock.get('available')) and stock['available']<=0:
  out.update(stage='stockout',reason='Свободный остаток МСК равен 0 или весь в резерве');return out
 if not fresh(stock,now) or not number(stock.get('available')):gaps.append('Текущий МСК stock-reserve')
 if not fresh(price,now) or price.get('currency')!='CNY' or not number(price.get('seller_cny')):gaps.append('Текущая цена продавца CNY')
 if not fresh(camp,now) or type(camp.get('status')) is not int:gaps.append('Текущий состав/статус/ставка РК')
 if fresh(camp,now) and type(camp.get('status')) is int and camp['status']!=9:
  out.update(stage='inactive_campaign',reason='Проверенный статус РК '+str(camp.get('status'))+'; активная открутка не подтверждена');return out
 if not fresh(camp,now) or not number(camp.get('budget_cny')):gaps.append('Текущий остаток бюджета РК')
 elif camp['budget_cny']<=0:
  out.update(stage='empty_budget',reason='В РК подтверждён нулевой бюджет; сумма ручного пополнения не согласована');return out
 if not fresh(card,now,86400) or card.get('orderable') is not True:gaps.append('Доступность точного варианта на витрине WB')
 if fresh(card,now,86400) and card.get('orderable') is False:
  out.update(stage='unorderable',reason='Точный вариант недоступен к заказу по проверке витрины');return out
 rating=quality.get('rating');count=quality.get('review_count')
 if not fresh(quality,now,86400) or (not (number(rating) and 0<rating<=5) and count!=0):gaps.append('Рейтинг/отзывы точного товара')
 elif number(rating) and 0<rating<quality.get('minimum_rating',4):
  out.update(stage='low_rating',reason='Подтверждён рейтинг '+str(rating)+'; это риск, а не доказанная причина отсутствия заказов');return out
 if any(traffic.get(k) is None for k in FIELDS):gaps.append('Полные строки SKU/дней рекламной воронки; пропуск не 0')
 if gaps:
  out.update(stage='incomplete',reason='Не завершена самостоятельная проверка: '+'; '.join(dict.fromkeys(gaps)));return out
 # CPC may have impressions at zero spend. Today's DRR is never a selection gate.
 if traffic['orders']>0:out.update(stage='orders',reason='Есть рекламные заказы; малую выборку не считаю доказанной эффективностью');return out
 if traffic['clicks']>0:
  out.update(stage='baskets_without_orders' if traffic['baskets']>0 else 'clicks_without_baskets',reason='Трафик уже есть; проверенная причина потери конверсии и готовое изменение карточки пока не установлены');return out
 if traffic['views']>20:
  out.update(stage='impressions_without_clicks',reason='Показы есть, кликов нет; повышение CPC не устраняет непроверенную причину низкой кликабельности');return out
 if camp.get('payment_type')!='cpc' or camp.get('currency')!='CNY':gaps.append('Тип CPC и валюта текущей РК')
 old=camp.get('bid_minor');minimum=camp.get('minimum_minor');step=camp.get('step_minor');maximum=camp.get('maximum_minor')
 if not all(type(x) is int and x>0 for x in [old,minimum,step,maximum]):gaps.append('Точные текущая ставка, минимум, шаг и максимум WB')
 if gaps:out.update(stage='incomplete',reason='; '.join(gaps));return out
 target=math.ceil(old*(1+raise_percent/100)/step)*step
 if target<minimum:
  out.update(stage='bid_limit',reason='Минимум WB требует повышения выше запрошенного процента; автоматически не увеличиваю масштаб теста');return out
 if target<=old or target>maximum:
  out.update(stage='bid_limit',reason='Допустимое повышение по минимуму/шагу/максимуму WB не найдено');return out
 if any(x.get('kind')=='bid' and at(x['at']).astimezone(MSK).date()==today for x in changes):
  out.update(stage='observe_change',reason='Сегодня ставку SKU уже меняли; повтор в другой РК запрещён');return out
 econ=economics(f,target/100);out['economics']=econ
 if not econ.get('available') or econ['scenarios'][0]['profit_per_order_cny']<=0:
  out.update(stage='economics_limit',reason=econ.get('reason','При сценарии конверсии1% запаса предварительной экономики для повышения нет'));return out
 out.update(stage='limited_traffic_test',action=dict(kind='bid_test_proposal',campaign_id=camp['id'],nm_id=f['nm_id'],placement=camp['placement'],old_minor=old,target_minor=target),recommendation=f"Проект теста: CPC {old/100:g} → {target/100:g} CNY в РК {camp['id']}.",reason='Малый трафик, текущие условия проверены; положительная предварительная экономика даже при сценарии CR1%, это не доказанная низкая ДРР')
 return out
def render(result):
 rows=result['rows'];first,last=result['period_from'],result['period_to']
 if not rows:return 'Нет. Не удалось однозначно определить артикул из текущего вопроса.'
 def stat(r):
  t=r['traffic'];fmt=lambda k:'?' if t.get(k) is None else f"{t[k]:g}"
  return ' / '.join(fmt(k) for k in ['views','clicks','baskets','orders'])
 if len(rows)==1:
  r=rows[0];out=f"{r['article']}"+(f" · РК {r['campaign_id']}" if r.get('campaign_id') else '')+f". За {first}—{last}, реклама: показы/клики/корзины/заказы {stat(r)}.\nРекомендация: {r['recommendation']}"
  if r['action']:
   e=r['economics'];out+=' Предварительно на заказ при CR1/2/3%: '+ '/'.join(f"{x['profit_per_order_cny']:g}" for x in e['scenarios'])+' CNY; сценарии, не измеренный прогноз. Выкуп '+str(round(e['buyout']*100,1))+'%, завершённая выборка '+str(e.get('completed_sample'))+'. Лимит выборки и неизвестные удержания сохраняются. Нужен отдельный подтверждённый план, сейчас изменений нет.'
  else:out+=' '+r['reason']+'.'
  general=r.get('all_source') or {}
  if general.get('missing'):out+=' Общая воронка WB не подтверждена; органику вычитанием рекламной атрибуции не определяю.'
  if number(general.get('orders')):out+=' Все заказы ('+general.get('source','источник')+'): '+str(general['orders'])+'; органику вычитанием рекламной атрибуции не определяю.'
  today=r.get('today_observation') or {}
  if today.get('counters'):
   t=today['counters'];out+=' Сегодня, отдельный неполный срез '+str(today.get('observed_at'))+': '+str(t.get('views','?'))+' показов / '+str(t.get('clicks','?'))+' кликов. Сегодняшние показатели не использованы для выбора нового теста.'
  condition_at=r.get('evidence',{}).get('campaign',{}).get('observed_at')
  if condition_at:out+=' Срез РК: '+condition_at+'.'
  if r.get('review_from'):out+=' Первый полный день после изменения — '+str(__import__('datetime').date.fromisoformat(r['review_from'])-timedelta(days=1))+', оценка с '+r['review_from']+'.'
  return out
 lines=[f'Полные дни {first}—{last}. Рекламные показы / клики / корзины / заказы.','| Артикул / РК | Воронка | Рекомендация |','|---|---|---|']
 for r in rows:lines.append(f"| {r['article']} / {r.get('campaign_id') or '?'} | {stat(r)} | {r['recommendation']} |")
 reasons=list(dict.fromkeys(r['reason'] for r in rows if r['recommendation']=='Нет'))
 if reasons:lines+=['Ограничения проверки: '+'; '.join(reasons[:4])+'.']
 if any(r['action'] for r in rows):lines+=['Проекты тестов, не исполнение. Экономика предварительная; CR1/2/3% — сценарии; неизвестные удержания не0.']
 return '\n'.join(lines)
