"""Daily approved China price-control model; dates and facts recomputed every run."""
from datetime import datetime,date,timedelta,timezone
from decimal import Decimal
import json,os,base64,re,time

def comparison_windows(detected,today):
 n=min(4,max(0,(today-detected).days-1))
 if not n:return None
 return ((detected-timedelta(days=n),detected-timedelta(days=1)),(detected+timedelta(days=1),detected+timedelta(days=n)))

def all_days(a,b):return [a+timedelta(days=i) for i in range((b-a).days+1)]

def build(worker,candidate_review=False):
 from china_agent.morning_pair import tracked_rows
 from china_agent import demand
 from china_agent.control_owner_preview import Preview
 from china_agent.daily_report_worker import MSK
 from china_agent.expected_order_profit import resolved_buyout_rate,expected_profit
 from china_agent.price_experiment_result import experiment_result,zero_buyout_signal
 from china_agent.wb_order_gaps import counts
 from analytics.mpstats_primary import products
 from analytics.mpstats_probe import discover
 from analytics.mpstats_gaps import execute_reads
 from analytics.collect import _fetch_transport
 state=worker.get(demand.STATE_KEY) or {};tracked=tracked_rows(state,worker.day)
 if candidate_review:
  tracked=[]
  for nm,result in (state.get('latest',{}).get('results') or {}).items():
   before=result.get('conversion_before');after=result.get('conversion_after')
   entry=state.get('price_history',{}).get(nm,{})
   change=entry.get('last_price_change') or entry.get('increase') or {}
   if result.get('full_days',0)>=4 and before is not None and after is not None and after<before and change.get('baseline_from') and change.get('baseline_to'):
    detected=datetime.fromisoformat(change['detected_at']).astimezone(MSK).date()
    tracked.append((nm,entry,change,detected))
 end=worker.day-timedelta(days=1);rate_start=end-timedelta(days=29)
 pairs={str(nm):comparison_windows(d,worker.day) for nm,e,c,d in tracked}
 if candidate_review:
  pairs={str(nm):((date.fromisoformat(c['baseline_from']),date.fromisoformat(c['baseline_to'])),(worker.day-timedelta(days=4),end)) for nm,e,c,d in tracked}
  if any((a[1]-a[0]).days!=(b[1]-b[0]).days for a,b in pairs.values()):raise RuntimeError('Candidate comparison periods differ in length')
 windows={(str(rate_start),str(end))}
 for pair in pairs.values():
  if pair:windows.update((str(a),str(b)) for a,b in pair)
 Preview.acquire(worker,windows)
 worker.now=datetime.now(MSK)
 read=lambda t,p:worker.db('GET',t,params=p)
 datasets={}
 for a,b in windows:
  rows,marker=products(read,'token_3',a,b,worker.now)
  if not marker:raise RuntimeError('Price control exact-period source missing')
  datasets[(a,b)]={str(r['nm_id']):r for r in rows}
 rate_rows=datasets[(str(rate_start),str(end))]
 registry=worker.get('china_agent:price_control_product_registry:v1') or {}
 for nm,r in rate_rows.items():registry[nm]=dict(pid=str(r['p_id']),article=r['sa_name'])
 worker.save('china_agent:price_control_product_registry:v1',registry)
 missing={nm for nm,pair in pairs.items() if pair for a,b in pair if nm not in datasets[(str(a),str(b))]}
 card_tables={}
 if missing:
  requests=[]
  for nm in missing:
   item=registry.get(nm)
   if not item:raise RuntimeError('Missing product mapping for daily detail')
   worker.control_allowed_pids=getattr(worker,'control_allowed_pids',set())|{item['pid']}
   requests.append(dict(cabinet='token_3',tool='lk_wb_card_table',key='control-card:'+nm,priority=90,arguments=dict(type='products',value=item['pid'],period_type='30days',self_redemption=False)))
  def persist(cabinet,obs):
   if cabinet!='token_3' or obs.get('scope_verified') is not True or obs.get('status')!='received':raise RuntimeError('Daily card source unavailable')
   nm=obs['request_key'].split(':')[-1];body=obs['data']
   if body.get('status')!='success' or not isinstance(body.get('data'),dict):raise RuntimeError('Daily card detail invalid')
   card_tables[nm]=body['data'];worker.save('china_agent:control_card:'+str(worker.day)+':'+nm,obs)
  pending=[]
  for req in requests:
   nm=req['key'].split(':')[-1];old=worker.get('china_agent:control_card:'+str(worker.day)+':'+nm) or {}
   if old.get('status')=='received' and old.get('scope_verified') is True:card_tables[nm]=old['data']['data']
   else:pending.append(req)
  if pending:
   def extra(call,checks,known):return execute_reads(call,checks,known,pending,{},persist,max_requests=len(pending))
   result=discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=extra)
   if set(missing)-set(card_tables):raise RuntimeError('Daily missing card evidence unavailable')
 needed=set(all_days(worker.day-timedelta(days=4),worker.day-timedelta(days=1)))
 for pair in pairs.values():
  if pair:
   for a,b in pair:needed.update(all_days(a,b))
 worker.control_allowed_days={str(d) for d in needed}
 targets={str(nm):e['article'] for nm,e,c,d in tracked}
 wb={};token=os.environ['WB_TOKEN_3'].strip()
 for day in sorted(needed):
  key='china_agent:wb_order_gaps:day:'+str(day);cached=worker.get(key) or {}
  valid=(cached.get('cabinet')=='token_3' and cached.get('date')==str(day) and cached.get('status')=='complete' and cached.get('seller_identity_verified') is True)
  if valid:
   try:valid=datetime.fromisoformat(cached['observed_at'].replace('Z','+00:00'))>=datetime.combine(day+timedelta(days=1),datetime.min.time(),MSK)
   except (ValueError,KeyError):valid=False
  if not valid:
   segment=token.split('.')[1];claims=json.loads(base64.urlsafe_b64decode(segment+'='*(-len(segment)%4)))
   identity=read('analytics_snapshots',dict(source='eq.seller_identity',cabinet='eq.token_3',status='eq.complete',select='payload',order='id.desc',limit=1)) or []
   if len(identity)!=1 or not claims.get('sid') or str(claims['sid'])!=str(identity[0]['payload'].get('sid')):raise RuntimeError('China seller identity unverified')
   deadline=time.monotonic()+300
   while True:
    try:
     rows=_fetch_transport('GET','https://statistics-api.wildberries.ru/api/v1/supplier/orders',token,params=dict(dateFrom=str(day),flag=1),max_retry_wait=0);break
    except RuntimeError as exc:
     match=re.search(r'(?:Shared WB cooldown;|Source HTTP 429;) retry after (\d+) seconds',str(exc))
     if not match or time.monotonic()+int(match[1])+1>deadline:raise
     time.sleep(min(60,int(match[1])+1))
   counts(rows,day,targets)
   keep=('date','lastChangeDate','nmId','supplierArticle','srid','isCancel','cancelDate','barcode')
   cached=dict(cabinet='token_3',date=str(day),status='complete',seller_identity_verified=True,scope='flag=1 exact Moscow day',observed_at=datetime.now(timezone.utc).isoformat(),rows=[{k:r[k] for k in keep if k in r} for r in rows])
   worker.save(key,cached)
  wb[str(day)]=counts(cached['rows'],day,targets)
 costs={r['article'].casefold():r['cost'] for r in read('analytics_costs',dict(select='article,cost',limit=5000)) or [] if r.get('article') and r.get('cost') is not None}
 model=worker.get('china_agent:expected_profit_delivery_model:v1') or {}
 if model.get('cabinet')!='token_3':raise RuntimeError('Saved delivery model missing')
 output=[]
 for nm,e,change,detected in tracked:
  nm=str(nm);article=e['article'];pair=pairs[nm];params=rate_rows.get(nm)
  resolved=resolved_buyout_rate(params.get('is_payed') if params else None,params.get('finished_orders') if params else None,params.get('is_payed_percent_after_returns') if params else None)
  item=dict(nm_id=nm,article=article,detected_at=str(detected),before_price=(change.get('before_price') or {}).get('current_cny'),after_price=(change.get('after_price') or {}).get('current_cny'),buyout_percent=resolved['percent'],buyout_sample=resolved['sample_size'],buyout_fallback=resolved['source']=='fallback',assessment_date=str(detected+timedelta(days=5)))
  if params:item['zero_buyout_signal']=zero_buyout_signal(params['orders_count'],params['is_payed'],params['finished_orders'],params['not_finished_orders'],params['is_not_payed'],params['finish_as_return'])
  if not pair:item.update(status='zero_full_days',result_action='Нет завершённых дней после изменения; ждём первый полный день.');output.append(item);continue
  retention=None
  if params:
   gross=Decimal(str(params['sales_ret_sum']))
   retention=1-(Decimal(str(params['total_commission_without_spp']))+Decimal(str(params['acquiring'])))/gross if gross>0 else 1-Decimal(str(params['default_comission']))/100
  for label,(a,b),field in zip(('before','after'),pair,('before_price','after_price')):
   total=sum(wb[str(d)][nm]['orders'] for d in all_days(a,b));raw=datasets[(str(a),str(b))].get(nm)
   if raw:
    ads=raw['advertisement'];views=raw['open_card_count'];funnel=raw['funnel_orders_count']
   else:
    details=[card_tables[nm].get(str(d)) for d in all_days(a,b)]
    if any(not isinstance(r,dict) or r.get('advertisement') is None for r in details):raise RuntimeError('Explicit daily advertising missing')
    ads=sum(r['advertisement'] for r in details);views=funnel=None
   scenarios=[]
   if total:
    cost=costs.get(article.casefold());delivery=(model.get('rows',{}).get(article) or {}).get('delivery_cny')
    if cost is None or delivery is None or retention is None or item[field] is None:raise RuntimeError('Expected-profit scenario input missing')
    dispatch=Decimal(str(delivery))*Decimal(str(model['rub_per_cny']))+Decimal(str(model['acceptance_rub_per_dispatch']))
    unit=Decimal(str(item[field]))*Decimal(str(model['rub_per_cny']))*retention-Decimal(str(cost))-dispatch
    scenarios=[dict(order_id=str(i),buyout_profit=unit,nonbuyout_profit=-dispatch) for i in range(total)]
   calculated=expected_profit(scenarios,resolved['probability'],ads,0)
   item[label]=dict(period_from=str(a),period_to=str(b),orders=total,views=views,funnel_orders=funnel,conversion=funnel/views if views else None,advertising=ads,expected_profit=calculated['expected_profit'])
  a,b=item['before'],item['after'];full_days=(pair[1][1]-pair[1][0]).days+1
  result=experiment_result(a['expected_profit'],b['expected_profit'],a['views'],a['funnel_orders'],b['views'],b['funnel_orders'],full_days,resolved['sample_size'])
  if a['orders']==b['orders']==0:result.update(status='no_orders',result_action='Заказов в обоих периодах нет. Разница результата связана с рекламными расходами; влияние цены не оценено.')
  if item.get('zero_buyout_signal',{}).get('attention'):result.update(status='zero_buyout_attention',result_action='⚠️ Заказы есть, выкупов нет — проверить причины невыкупа товара отдельно от изменения цены.')
  item.update(full_days=full_days,result=result);output.append(item)
 value=dict(report_date=str(worker.day),status='complete_disclosed_forecast_model',products=output,rate_period=[str(rate_start),str(end)],calculated_at=datetime.now(MSK).isoformat(),telegram_calls=0,wb_writes=0)
 worker.save(('china_agent:daily_expected_candidates:' if candidate_review else 'china_agent:daily_expected_control:')+str(worker.day)+(':verify' if getattr(worker,'control_preview',False) else ''),value)
 return value

def render(value):
 fmt=lambda x:f'{x:g}'.replace('.',',')
 money=lambda x:f'{x:,.0f}'.replace(',',' ')
 cr=lambda p:'нет возвращённой истории' if p['views'] is None else 'не рассчитывается: 0 просмотров' if p['views']==0 else f"{p['conversion']*100:.2f}%".replace('.',',')
 lines=['Китай • контроль результата изменения цен • '+value['report_date'],
 'Ожидаемая прибыль по дате заказа, скорректированная на текущий % выкупа артикула. Прогноз по учтённым расходам, не фактическая чистая прибыль.',
 'Под наблюдением: '+str(len(value['products']))+' товаров.']
 for item in value['products']:
  if item['before_price'] is None or item['after_price'] is None:raise RuntimeError('Price observation missing')
  lines+=['','• '+item['article']+' | цена '+fmt(item['before_price'])+' → '+fmt(item['after_price'])+' ¥; обнаружено '+item['detected_at']+'.',
   'Выкуп: '+fmt(round(item['buyout_percent'],2))+'%'+(' — принято для расчёта, собственной статистики недостаточно.' if item['buyout_fallback'] else '; завершённых заказов в выборке: '+str(item['buyout_sample'])+'.')]
  if item.get('status')=='zero_full_days':lines+=['Результат и действие: '+item['result_action'],'Первая четырёхдневная оценка: '+item['assessment_date']+'.'];continue
  a,b=item['before'],item['after'];r=item['result']
  lines+=['Периоды: '+a['period_from']+'–'+a['period_to']+' → '+b['period_from']+'–'+b['period_to']+'.',
   'Заказы: '+str(a['orders'])+' → '+str(b['orders'])+'; ожидаемая прибыль: '+money(a['expected_profit'])+' → '+money(b['expected_profit'])+' ₽; разница '+money(r['profit_delta_rub'])+' ₽'+(' ('+fmt(r['profit_delta_percent'])+'%)' if r['profit_delta_percent'] is not None else '')+'.',
   'Конверсия: '+cr(a)+' → '+cr(b)+'.','Результат и действие: '+r['result_action']]
  alert=item.get('zero_buyout_signal') or {}
  if alert.get('message'):lines.append(alert['message'])
 lines+=['','Процент выкупа: завершённые заказы с учётом возвратов за '+value['rate_period'][0]+'–'+value['rate_period'][1]+'. Для сравнения применён один текущий процент артикула.',
 'Заказы — WB, без отмен и дублей; конверсия — воронка MPStats, счётчики имеют разные определения.',
 'Расчётная модель: наблюдаемые цены до/после, 12 ₽/¥, наша себестоимость, доставка по сохранённой модели 03.10, приёмка 10 ₽ за отправку, налог 0%. Реклама вычитается полностью.',
 'Удержания артикула: наблюдавшиеся по его продажам за период, при отсутствии продаж — комиссия из MPStats; одинаковые условия до/после. Дополнительный возврат продавцу и нераспределённые расходы не включены.',
 'Отсутствие истории конверсии выделяется явно, нулём не заменяется. День обнаружения и сегодняшний день исключены. Новая корректировка начинает отсчёт заново.',
 'Рекомендация возврата цены — после четырёх полных дней и проверки связки. Все изменения цены согласовываем.']
 return '\n'.join(lines)

def render_candidates(worker):
 """Keep first-raise selection on the same verified WB order days as control."""
 from china_agent import demand
 from china_agent.wb_order_gaps import counts
 from business_agents.data import Data
 prices=worker.get('china_agent:prices:v1') or {};state=worker.get(demand.STATE_KEY) or {}
 rows=prices.get('rows',[]);data=Data('china',lambda t,p:worker.db('GET',t,params=p))
 targets={str(r['nmID']):r['vendorCode'] for r in rows if not data.excluded(r.get('vendorCode',''))}
 wanted=all_days(worker.day-timedelta(days=4),worker.day-timedelta(days=1));daily={}
 for day in wanted:
  receipt=worker.get('china_agent:wb_order_gaps:day:'+str(day)) or {}
  if receipt.get('status')!='complete' or receipt.get('seller_identity_verified') is not True:raise RuntimeError('Candidate WB day incomplete')
  daily[str(day)]=counts(receipt['rows'],day,targets)
 initial=[]
 for price in rows:
  nm=str(price['nmID'])
  if nm not in targets:continue
  entry=state.get('price_history',{}).get(nm,{})
  values=[daily[str(d)][nm]['orders'] for d in wanted]
  if not entry.get('increase') and not entry.get('last_price_change') and all(v>=1 for v in values):
   proposal=demand.offer(price)
   if proposal:initial.append((targets[nm],nm,values,proposal))
 lower=[]
 review=build(worker,candidate_review=True)
 expected={r['nm_id']:r for r in review['products']}
 for nm,result in (state.get('latest',{}).get('results') or {}).items():
  before=result.get('conversion_before');after=result.get('conversion_after')
  if nm in targets and result.get('full_days',0)>=4 and before is not None and after is not None and after<before:
   lower.append((targets[nm],nm,[daily[str(d)][nm]['orders'] for d in wanted],before,after))
 lines=['Китай • кандидаты на повышение и снижение • '+str(worker.day),'Период: '+str(wanted[0])+'–'+str(wanted[-1])+' — четыре полных дня.','Заказы сверены с WB, отмены и дубли исключены. Каталог: '+str(len(targets))+' товаров.','', 'ПЕРВОЕ ПОВЫШЕНИЕ +10%: '+str(len(initial))]
 for article,nm,values,p in sorted(initial):lines+=['• '+article+' / nmID '+nm+': заказы '+('/'.join(map(str,values)))+'; цена после скидки '+f"{p['current_cny']:g}"+' → '+f"{p['target_cny']:g}"+' ¥.']
 lines+=['','ПОВТОРНОЕ ПОВЫШЕНИЕ: решение только по ожидаемой прибыли и конверсии в отдельном контроле изменений цены. Старую прибыль по дате продажи не используем.','','ПРОВЕРКА ВОЗМОЖНОГО СНИЖЕНИЯ: '+str(len(lower))]
 for article,nm,values,b,a in sorted(lower):
  item=expected.get(nm)
  if not item:raise RuntimeError('Expected-profit comparison missing for lower candidate')
  before=item['before'];after=item['after'];result=item['result']
  f=lambda v:f'{v:,.0f}'.replace(',',' ')
  lines+=['• '+article+' / nmID '+nm+': заказы '+('/'.join(map(str,values)))+'; конверсия '+f'{b:.1%}'+' → '+f'{a:.1%}'+'.',
   '  Ожидаемая прибыль '+before['period_from']+'–'+before['period_to']+' → '+after['period_from']+'–'+after['period_to']+': '+f(before['expected_profit'])+' → '+f(after['expected_profit'])+' ₽; разница '+f(result['profit_delta_rub'])+' ₽'+(' ('+str(result['profit_delta_percent'])+'%)' if result['profit_delta_percent'] is not None else '')+'.',
   '  Выкуп '+str(round(item['buyout_percent'],2))+'%'+(' — принято, своей статистики недостаточно.' if item['buyout_fallback'] else '; завершённых заказов '+str(item['buyout_sample'])+'.'),
   '  Результат и действие: '+result['result_action'],'  Перед снижением проверить связку; изменение цены только по согласованию.']
 lines+=['Предварительный отбор снижения: ожидаемая прибыль скорректирована на текущий % выкупа артикула и относится к датам заказов. Расчёт по согласованной модели учтённых расходов; не фактическая чистая прибыль. Связка проверяется до решения. Конверсия — MPStats, счётчик заказов воронки отличается от статистики WB.','Все изменения цены согласовываем.']
 return '\n'.join(lines)
