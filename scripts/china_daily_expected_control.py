"""Daily approved China price-control model; dates and facts recomputed every run."""
from datetime import datetime,date,timedelta,timezone
from decimal import Decimal
import json,os,base64,re,time

def comparison_windows(detected,today):
 n=min(4,max(0,(today-detected).days-1))
 if not n:return None
 return ((detected-timedelta(days=n),detected-timedelta(days=1)),(detected+timedelta(days=1),detected+timedelta(days=n)))

def all_days(a,b):return [a+timedelta(days=i) for i in range((b-a).days+1)]


def order_outcomes(wb_rows, details, nm, article, start, end):
 """WB is the order universe; identical-time unit multiplicity is preserved."""
 unique={}
 for row in wb_rows:
  if str(row.get('nmId'))!=str(nm) or not start<=str(row.get('date',''))[:10]<=end:continue
  if row.get('supplierArticle','').casefold()!=article.casefold():raise RuntimeError('WB article mismatch')
  key=str(row['srid'])
  if key not in unique or row.get('lastChangeDate','')>=unique[key].get('lastChangeDate',''):unique[key]=row
 groups={}
 for row in unique.values():groups.setdefault((row['date'],str(row.get('barcode',''))),[]).append(row)
 result=dict(orders=len(unique),paid=0,cancelled=0,returned=0,pending=0,unknown=0)
 for key,rows in groups.items():
  matches=[r for r in details if (str(r.get('order_dt','')).replace(' ','T'),str(r.get('barcode','')))==key]
  if all(r['isCancel'] for r in rows):result['cancelled']+=len(rows);continue
  if any(r['isCancel'] for r in rows):result['unknown']+=len(rows);continue
  if len(matches)!=len(rows):result['unknown']+=len(rows);continue
  for r in matches:
   if str(r.get('nm_id'))!=str(nm) or r.get('api_id')!=10026946 or r.get('sa_name','').casefold()!=article.casefold():raise RuntimeError('Outcome identity mismatch')
   billed=r.get('billed_times');returned=r.get('refunded_times');back=r.get('backlogistic_times')
   if billed not in (0,1) or returned not in (0,1) or returned>billed:result['unknown']+=1
   elif returned:result['returned']+=1
   elif billed:result['paid']+=1
   elif back:result['cancelled']+=1
   else:result['pending']+=1
 result['completed']=result['paid']+result['cancelled']+result['returned']
 if result['orders']!=sum(result[k] for k in ('paid','cancelled','returned','pending','unknown')):raise RuntimeError('Order balance mismatch')
 return result

def acquire_outcomes(worker, tracked, pairs, registry):
 from analytics.mpstats_probe import discover
 from analytics.mpstats_gaps import execute_reads
 key='china_agent:period_cohort_raw:'+str(worker.day)
 cached=worker.get(key) or {};observations={}
 for p in cached.get('products',[]):
  if p.get('observation',{}).get('status')=='received':observations[str(p['nm_id'])]=p
 requests=[];output={}
 def unpack(nm,obs,a,b,pid):
  if obs.get('status')!='received' or obs.get('scope_verified') is not True:raise RuntimeError('Cohort source incomplete')
  body=obs['data']
  if isinstance(body.get('data'),dict):body=body['data']
  rows=body.get('data');filters=body.get('filterModel') or {};dates=filters.get('order_dt') or {}
  if not isinstance(rows,list) or len(rows)!=body.get('total') or len(rows)>=300:raise RuntimeError('Cohort pagination incomplete')
  if str((filters.get('product_id') or {}).get('filter'))!=pid or dates.get('dateFrom','z')>a or dates.get('dateTo','')<b:raise RuntimeError('Cohort filter mismatch')
  output[nm]=rows
 for nm,e,c,d in tracked:
  nm=str(nm);pair=pairs[nm]
  if not pair:continue
  a=str(pair[0][0]);b=str(pair[1][1]);pid=registry[nm]['pid'];saved=observations.get(nm)
  if saved:
   try:unpack(nm,saved['observation'],a,b,pid);continue
   except RuntimeError:pass
  worker.control_allowed_cohorts=getattr(worker,'control_allowed_cohorts',set())|{(pid,a,b)}
  requests.append(dict(cabinet='token_3',tool='lk_wb_card_orders',key=nm,priority=90,arguments=dict(type='products',value=pid,date_from=a,date_to=b,start_row=0,end_row=300)))
 def persist(cabinet,obs):
  nm=str(obs['request_key']);req=next(r for r in requests if r['key']==nm);args=req['arguments']
  if cabinet!='token_3':raise RuntimeError('Cohort cabinet mismatch')
  unpack(nm,obs,args['date_from'],args['date_to'],args['value'])
  observations[nm]=dict(nm_id=nm,pid=args['value'],article=registry[nm]['article'],observation=obs)
  worker.save(key,dict(status='acquiring',products=list(observations.values()),telegram_calls=0,wb_writes=0))
 if requests:
  def extra(call,checks,known):return execute_reads(call,checks,known,requests,{},persist,max_requests=len(requests))
  discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=extra)
 if any(str(nm) not in output for nm,e,c,d in tracked if pairs[str(nm)]):raise RuntimeError('Missing cohort outcomes')
 worker.save(key,dict(status='acquired',products=list(observations.values()),telegram_calls=0,wb_writes=0))
 return output

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
 wb={};wb_raw=[];token=os.environ['WB_TOKEN_3'].strip()
 for day in sorted(needed):
  key='china_agent:wb_order_gaps:day:'+str(day);cached=worker.get(key) or {}
  valid=(cached.get('cabinet')=='token_3' and cached.get('date')==str(day) and cached.get('status')=='complete' and cached.get('seller_identity_verified') is True)
  if valid:
   try:valid=datetime.fromisoformat(cached['observed_at'].replace('Z','+00:00')).astimezone(MSK).date()==worker.day and datetime.fromisoformat(cached['observed_at'].replace('Z','+00:00'))>=datetime.combine(day+timedelta(days=1),datetime.min.time(),MSK)
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
  wb_raw.extend(cached['rows'])
  wb[str(day)]=counts(cached['rows'],day,targets)
  for value in wb[str(day)].values():value['orders']+=value['cancelled']
 costs={r['article'].casefold():r['cost'] for r in read('analytics_costs',dict(select='article,cost',limit=5000)) or [] if r.get('article') and r.get('cost') is not None}
 model=worker.get('china_agent:expected_profit_delivery_model:v1') or {}
 if model.get('cabinet')!='token_3':raise RuntimeError('Saved delivery model missing')
 outcome_rows=acquire_outcomes(worker,tracked,pairs,registry)
 output=[]
 for nm,e,change,detected in tracked:
  nm=str(nm);article=e['article'];pair=pairs[nm];params=rate_rows.get(nm)
  outcomes={}
  if pair:
   for label,(a,b) in zip(('before','after'),pair):outcomes[label]=order_outcomes(wb_raw,outcome_rows[nm],nm,article,str(a),str(b))
  base=outcomes.get('before',{})
  resolved=resolved_buyout_rate(base.get('paid'),base.get('completed'))
  item=dict(nm_id=nm,article=article,detected_at=str(detected),before_price=(change.get('before_price') or {}).get('current_cny'),after_price=(change.get('after_price') or {}).get('current_cny'),buyout_percent=resolved['percent'],buyout_sample=resolved['sample_size'],buyout_fallback=resolved['source']=='fallback',assessment_date=str(detected+timedelta(days=5)))
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
   item[label]=dict(outcomes=outcomes[label],period_from=str(a),period_to=str(b),orders=total,views=views,funnel_orders=funnel,conversion=funnel/views if views else None,advertising=ads,expected_profit=calculated['expected_profit'])
  a,b=item['before'],item['after'];full_days=(pair[1][1]-pair[1][0]).days+1
  result=experiment_result(a['expected_profit'],b['expected_profit'],a['views'],a['funnel_orders'],b['views'],b['funnel_orders'],full_days,resolved['sample_size'])
  if a['orders']==b['orders']==0:result.update(status='no_orders',result_action='Заказов в обоих периодах нет. Разница результата связана с рекламными расходами; влияние цены не оценено.')
  after=outcomes['after']
  if after['completed'] and after['paid']==0:item['zero_buyout_signal']=dict(attention=True,message='Заказы есть, подтверждённых выкупов нет; проверить причины отмен/возвратов. Не связывать с качеством без проверки.')
  item.update(full_days=full_days,result=result);output.append(item)
 value=dict(model_version='wb_orders_baseline_buyout_v2',report_date=str(worker.day),status='complete_disclosed_forecast_model',products=output,rate_period=[str(rate_start),str(end)],calculated_at=datetime.now(MSK).isoformat(),telegram_calls=0,wb_writes=0)
 worker.save(('china_agent:daily_expected_candidates:' if candidate_review else 'china_agent:daily_expected_control:')+str(worker.day)+(':verify' if getattr(worker,'control_preview',False) else ''),value)
 return value

def _money(x):return f'{x:,.0f}'.replace(',',' ')
def _pct(x):return f'{x*100:.2f}%'.replace('.',',')
def _num(x):return f'{x:g}'.replace('.',',')
def _cr(p):
 if p['views'] is None:return 'история воронки не возвращена'
 return _pct(p['conversion']) if p['views'] else 'не рассчитывается: 0 просмотров'
def render_item(item):
 lines=[item['article']]
 if item.get('status')=='zero_full_days':return item['article']+'\n'+item['result_action']
 a,b=item['before'],item['after'];p=item['buyout_percent']/100
 rate=('50% — принято для расчёта, завершённой собственной статистики базового периода нет' if item['buyout_fallback'] else _pct(p)+' — '+str(a['outcomes']['paid'])+' из '+str(item['buyout_sample'])+' завершённых заказов'+('; выборка очень мала' if item['buyout_sample']<10 else ''))
 lines+=['Базовый выкуп: '+rate+'.']
 for label,title in (('before','До повышения'),('after','После повышения')):
  v=item[label];o=v['outcomes']
  lines+=['',title+', '+v['period_from']+'–'+v['period_to']+':',
   '• Цена: '+_num(item[label+'_price'])+' ¥.',
   '• Заказы: '+str(v['orders'])+', в том числе отмены — '+str(o['cancelled'])+'.',
   '• Прогноз прибыли: '+_money(v['expected_profit'])+' ₽'+(', если выкуп сохранится на уровне '+_pct(p) if label=='after' else ' при выкупе '+_pct(p))+'.',
   '• Конверсия: '+_cr(v)+'.',
   '• Реклама, включённая в расчёт: '+_money(v['advertising'])+' ₽.',
   '• Известные исходы: '+str(o['paid'])+' выкупов, '+str(o['cancelled'])+' отмен, '+str(o['returned'])+' возвратов, '+str(o['pending'])+' незавершённых заказов, '+str(o['unknown'])+' с неизвестным исходом.']
 r=item['result'];action=r['result_action'].replace('Ожидаемая прибыль','Условный прогноз прибыли').replace('Ожидаемую прибыль','Условный прогноз прибыли')
 lines+=['','Разница за равные периоды: '+_money(r['profit_delta_rub'])+' ₽'+(' / '+_num(r['profit_delta_percent'])+'%' if r['profit_delta_percent'] is not None else '')+'.','Результат и действие: '+action]
 if b['advertising']>a['advertising']:lines.append('Рост рекламных расходов учитываем отдельно; ухудшение не доказывает влияние цены.')
 if item.get('zero_buyout_signal',{}).get('message'):lines.append(item['zero_buyout_signal']['message'])
 if item['full_days']<4:lines.append('Промежуточно. Первая четырёхдневная оценка — '+item['assessment_date']+'.')
 return '\n'.join(lines)

def model_notes():
 return ('Заказы включают отмены; дубли исключены. При расхождениях приоритет WB. Незавершённые заказы не считаются отказами. '
 'Процент базового периода зафиксирован для обеих сторон сравнения: прогноз после изменения условен при сохранении выкупа. '
 'Модель: 12 ₽/¥, наша себестоимость, наблюдавшиеся удержания артикула, доставка по сохранённой модели 03.10 и приёмка 10 ₽. '
 'Реклама вычтена полностью. Пока сохранён резерв доставки на каждый заказ, включая отменённые; расходы отмен до отправки требуют уточнения. '
 'Дополнительные возвраты продавцу и нераспределённые расходы не включены. Это предварительный прогноз по учтённым расходам, не фактически полученная прибыль. '
 'День обнаружения и сегодняшний день исключены, периоды равны по длительности. Новая корректировка сбрасывает отсчёт. Все изменения цены согласовываем.')

def render(value):
 if value.get('model_version')!='wb_orders_baseline_buyout_v2':raise RuntimeError('Legacy forecast forbidden')
 return '\n\n'.join(['Китай • контроль изменений цен • '+value['report_date']+'\nПод наблюдением: '+str(len(value['products']))+' товаров.']+[render_item(p) for p in value['products']]+[model_notes()])

def render_candidates(worker):
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
  for v in daily[str(day)].values():v['orders']+=v['cancelled']
 initial=[]
 for price in rows:
  nm=str(price['nmID'])
  if nm not in targets:continue
  entry=state.get('price_history',{}).get(nm,{})
  values=[daily[str(d)][nm]['orders'] for d in wanted]
  if not entry.get('increase') and not entry.get('last_price_change') and all(v>=1 for v in values):
   proposal=demand.offer(price)
   if proposal:initial.append((targets[nm],nm,values,proposal))
 review=build(worker,candidate_review=True)
 lines=['Китай • кандидаты на повышение и проверку снижения • '+str(worker.day),'Период: '+str(wanted[0])+'–'+str(wanted[-1])+'. Проверен каталог: '+str(len(targets))+' товаров.','ПЕРВОЕ ПОВЫШЕНИЕ +10%: '+str(len(initial))]
 for article,nm,values,p in sorted(initial):
  cancels=sum(daily[str(d)][nm]['cancelled'] for d in wanted)
  lines+=['',article+'\nЗаказы по дням: '+('/'.join(map(str,values)))+'; отмены: '+str(cancels)+'.\nЦена продавца после скидки: '+_num(p['current_cny'])+' → '+_num(p['target_cny'])+' ¥.\nСкидка продавца сохраняется — '+_num(p['discount'])+'%.\nРезультат и действие: предлагается первый эксперимент с повышением на 10%, затем контроль прогнозной прибыли, конверсии и выкупа. Все изменения согласовываем.']
 lines+=['','Повторное повышение — только по отдельному контролю ожидаемой прибыли и конверсии.','ПРОВЕРКА ВОЗМОЖНОГО СНИЖЕНИЯ: '+str(len(review['products']))]
 lines.extend(render_item(p) for p in review['products'])
 lines.append(model_notes())
 return '\n\n'.join(lines)
