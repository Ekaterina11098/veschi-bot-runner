"""Demand-driven preliminary FBS profit. No marketplace writes or message transport."""
import collections,copy,hashlib,json,math,os,re,time
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from china_expected_order_profit import buyout_from_product
MSK=ZoneInfo('Europe/Moscow')
ROOT='china_agent:profit_forecast:v1:'
CANCELLED={'canceled','canceled_by_client','declined','declined_by_client','cancelled','cancelled_by_client'}
UNKNOWN=('Окончательные удержания, обратная логистика и внешние/общие расходы подтверждены не полностью.',
 'FBS-заказы не доказанно охватывают весь кабинет; это прогноз по дате создания, не закрытая чистая прибыль.')

def now():return datetime.now(timezone.utc)
def num(v,positive=False):
 if type(v) not in (int,float) or not math.isfinite(v) or v<0 or positive and v<=0:raise ValueError('Missing/invalid monetary input')
 return float(v)
def fresh(p,clock,ttl):
 try:return p.get('cabinet')=='token_3' and 0<=(clock-datetime.fromisoformat(p['observed_at'])).total_seconds()<=ttl
 except (ValueError,KeyError,TypeError):return False

def ad_cost(p,day,ids=()):
 if p.get('all_statuses_included') is not True:raise ValueError('Advertising closed-campaign coverage unknown')
 rows=p.get('rows');catalog=p.get('catalogue')
 if not isinstance(rows,list) or not isinstance(catalog,list):raise ValueError('Advertising coverage missing')
 seen=set();campaigns=set();total=0.;selected=set(ids)
 for c in rows:
  cid=c['advertId']
  if cid in campaigns or cid not in catalog:raise ValueError('Duplicate/foreign advertising campaign')
  campaigns.add(cid)
  if c.get('currency')!='CNY':raise ValueError('Advertising currency unknown')
  if not isinstance(c.get('days'),list):raise ValueError('Advertising days missing')
  for d in c['days']:
   stamp=d['date'][:10];key=(cid,stamp)
   if stamp!=str(day) or key in seen:raise ValueError('Advertising day duplicated/outside period')
   seen.add(key)
   if not selected:total+=num(d.get('sum'));continue
   apps=d.get('apps')
   if not isinstance(apps,list):raise ValueError('SKU advertising breakdown missing')
   app_seen=set()
   for a in apps:
    ident=a.get('appType')
    if ident in app_seen:raise ValueError('Duplicate advertising app')
    app_seen.add(ident);nms=a.get('nms')
    if not isinstance(nms,list):raise ValueError('SKU advertising rows missing')
    nmseen=set()
    for n in nms:
     nm=n['nmId']
     if nm in nmseen:raise ValueError('Duplicate SKU advertising cost')
     nmseen.add(nm)
     if nm in selected:total+=num(n.get('sum'))
 return total,sorted(set(catalog)-campaigns)

def known_charges(p,day,ids=()):
 """Only non-unit published charges: never forPay, commission/logistics or ad funding."""
 if not p:return dict(expenses_cny=0.,credits_cny=0.,rows=0,complete=False,excluded_ad_payments_cny=0.)
 if p.get('cabinet')!='token_3' or not p.get('period_from','9999')<=str(day)<=p.get('period_to','0000'):raise ValueError('Finance scope/period mismatch')
 expense=credit=ads=0.;seen=set();count=0
 for r in p.get('rows',[]):
  if r.get('rrDate','')[:10]!=str(day):continue
  if ids and r.get('nmId') not in ids:continue
  rid=r['rrdId']
  if rid in seen:raise ValueError('Duplicate finance charge')
  seen.add(rid)
  if r.get('currency')!='CNY':raise ValueError('Finance currency unknown')
  # Missing fields remain unknown, not zero: only non-null published components count.
  for k in ['paidStorage','paidAcceptance','penalty']:
   if r.get(k) is not None:expense+=num(r[k])
  deduction=r.get('deduction')
  if deduction is not None:
   value=num(deduction)
   if re.search(r'wb promotion|реклам|продвиж|广告',str(r.get('bonusTypeName','')),re.I):ads+=value
   elif value:
    if not r.get('bonusTypeName'):raise ValueError('Unclassified deduction could duplicate advertising')
    expense+=value
  if r.get('additionalPayment') is not None:credit+=num(r['additionalPayment'])
  count+=1
 return dict(expenses_cny=expense,credits_cny=credit,excluded_ad_payments_cny=ads,rows=count,complete=p.get('complete') is True,
  source_key=p.get('source_key'),observed_at=p.get('observed_at'),basis='Published operation date, not identified FBS cohort')

def external_charges(p,day,ids,fx):
 """Explicit dated own costs, with identities and inclusion markers for deduplication."""
 if not p:return dict(expenses_cny=0.,credits_cny=0.,complete=False)
 if p.get('cabinet')!='token_3' or p.get('date_msk')!=str(day):raise ValueError('Own expense ledger scope/date mismatch')
 expense=credit=0.;seen=set()
 for r in p.get('rows',[]):
  if r.get('id') is None or r['id'] in seen or not r.get('source_ref'):raise ValueError('Own expense identity/source missing or duplicate')
  seen.add(r['id'])
  if ids and r.get('nm_id') not in ids:continue
  if r.get('included_in') in ['advertising','finance','cogs','commission','tax','logistics','handling']:continue
  if r.get('included_in')!='additional' or r.get('kind') not in ['expense','credit']:raise ValueError('Own cost allocation unclassified')
  value=num(r.get('amount'));currency=r.get('currency')
  if currency=='RUB':value/=fx
  elif currency!='CNY':raise ValueError('Own expense currency unknown')
  if r['kind']=='expense':expense+=value
  else:credit+=value
 return dict(expenses_cny=expense,credits_cny=credit,complete=p.get('complete') is True)

def calculate(inputs,policy,delivery,day,ids=()):
 """Deterministic arithmetic; raw order prices/convertedPrice are never seller revenue."""
 if inputs.get('cabinet')!='token_3':raise ValueError('Cabinet mismatch')
 parts=inputs['inputs'];orders=parts['orders'];fx=num(float(parts['fx']['rub_per_cny']),True)
 effective=date.fromisoformat(parts['fx']['effective_date'])
 if effective>day or (day-effective).days>10:raise ValueError('FX date mismatch')
 if orders.get('complete') is not True:raise ValueError('Order pagination incomplete')
 cutoff=datetime.fromisoformat(orders['cutoff_msk']).astimezone(MSK)
 if cutoff.date()!=day and cutoff!=datetime.combine(day+timedelta(days=1),datetime.min.time(),MSK):raise ValueError('Order cutoff mismatch')
 own={int(p['nm_id']):p for p in parts.get('own_products',{}).get('rows',[])}
 cohort=parts.get('own_products',{})
 if cohort.get('period_from') and (cohort['period_from']!=str(day-timedelta(days=30)) or cohort.get('period_to')!=str(day-timedelta(days=1))):raise ValueError('Buyout cohort must be30 completed days')
 prices={int(p['nm_id']):p for p in parts.get('prices',{}).get('rows',[])}
 costs={p['article'].casefold():p for p in parts.get('stock',{}).get('rows',[])}
 statuses=parts.get('statuses',{});status={s['id']:s for s in statuses.get('rows',[])}
 totals=collections.defaultdict(float);fallback=collections.Counter();details=[];missing=[];seen=set();chosen=set(ids)
 for o in orders['rows']:
  oid=o['id'];nm=o['nmId'];article=o['article']
  if oid in seen:raise ValueError('Duplicate FBS order')
  seen.add(oid)
  at=datetime.fromisoformat(o['createdAt'].replace('Z','+00:00')).astimezone(MSK)
  if at.date()!=day or at>cutoff:raise ValueError('Order outside requested window')
  if chosen and nm not in chosen:continue
  totals['orders']+=1
  try:
   p=own.get(nm);pr=prices.get(nm);st=costs.get(article.casefold(),{})
   b=buyout_from_product(p);q=float(b['probability'])
   if statuses.get('complete') is not True or oid not in status:raise ValueError('Order status unknown')
   s=status[oid];cancel=s.get('supplierStatus')=='cancel' or s.get('wbStatus') in CANCELLED
   if not s.get('wbStatus') or not s.get('supplierStatus'):raise ValueError('Order status unknown')
   if cancel:q=0
   elif s.get('wbStatus')=='sold':q=1
   if b['source']=='fallback':fallback['buyout50_orders']+=1
   if b['sample_size']<20:fallback['small_completed_sample_orders']+=1
   if not pr or pr.get('currency')!='CNY' or pr.get('article','').casefold()!=article.casefold():raise ValueError('Seller price unknown')
   price=num(pr.get('seller_price'),True);cost=st.get('price')
   if type(cost) in (int,float) and cost>0:cost=num(cost,True)/100
   else:
    cost=num((p or {}).get('cost_price'),True);fallback['cogs_own_mpstats_orders']+=1
   fee=(p or {}).get('total_commission_without_spp_in_sales')
   if type(fee) not in (int,float) or not 0<fee<100:fee=num(policy.get('commission_pct'));fallback['commission_policy_orders']+=1
   log=policy.get('logistics_by_nm',{}).get(str(nm))
   if not log:log=delivery.get('rows',{}).get(article);fallback['delivery_model_orders']+=1
   tax=num(policy.get('tax_pct'));handling=num(policy.get('handling_rub'))
   if fee>=100 or tax>=100:raise ValueError('Cost percentage invalid')
   z=dict(cancelled_orders=int(cancel),model_seller_amount_cny=price,expected_buyouts=q,expected_seller_revenue_cny=q*price,
    cogs_cny=q*cost/fx,commission_cny=q*price*fee/100,tax_cny=q*price*tax/100,logistics_cny=num((log or {}).get('delivery_cny')),handling_cny=handling/fx)
   z['pre_ad_profit_cny']=z['expected_seller_revenue_cny']-sum(z[k] for k in ['cogs_cny','commission_cny','tax_cny','logistics_cny','handling_cny'])
   for k,v in z.items():totals[k]+=v
   details.append(dict(order_id=oid,nm_id=nm,article=article,own_completed=b['sample_size'],buyout=q,**z))
  except (ValueError,KeyError,TypeError) as ex:missing.append(dict(order_id=oid,nm_id=nm,article=article,note=str(ex)))
 problems=[]
 try:spend,admissing=ad_cost(parts['advertising'],day,ids)
 except (ValueError,KeyError,TypeError) as ex:spend=None;admissing=[];problems.append(str(ex))
 try:charges=known_charges(parts.get('finance'),day,ids)
 except (ValueError,KeyError,TypeError) as ex:charges=None;problems.append(str(ex))
 try:
  extra=external_charges(parts.get('external_costs'),day,ids,fx)
  if charges:charges=dict(charges,expenses_cny=charges['expenses_cny']+extra['expenses_cny'],credits_cny=charges['credits_cny']+extra['credits_cny'],external_costs=extra)
 except (ValueError,KeyError,TypeError) as ex:charges=None;problems.append(str(ex))
 totals['advertising_cny']=spend
 totals['known_other_costs_cny']=charges['expenses_cny'] if charges else None
 totals['known_other_credits_cny']=charges['credits_cny'] if charges else None
 ready=not missing and spend is not None and charges is not None
 estimate=totals['pre_ad_profit_cny']-spend-charges['expenses_cny']+charges['credits_cny'] if ready else None
 totals.update(forecast_profit_cny=estimate,forecast_profit_rub=estimate*fx if estimate is not None else None)
 return dict(status='preliminary_model' if ready else 'incomplete_model',cabinet='token_3',day_msk=str(day),cutoff_msk=orders['cutoff_msk'],nm_ids=list(ids),
  model_version=1,is_actual=False,totals=dict(totals),modelled_orders=len(details),unmodelled=missing,details=details,fallbacks=dict(fallback),
  errors=problems,collection_errors=inputs.get('errors',{}),missing_ad_campaigns=admissing,known_charges=charges,fx=parts['fx'],
  source_times={k:v.get('observed_at') for k,v in parts.items()},assumptions=list(UNKNOWN)+[
   'Текущая цена продавца CNY — замена неподтверждённой цены продавца в момент заказа; convertedPrice не выручка.',
   'Свой выкуп за30 завершённых дней; 50% только без завершённой выборки, фактические0% сохранены.',
   'Комиссия своя или допущение политики; налог и обработка — модель политики. Историческая логистика на каждый созданный заказ, включая отмены.',
   'Общие опубликованные удержания/доплаты учтены по дате операции отдельно; связь с этой FBS-когортой не доказана. Пополнения РК не расходы.'],
  wb_writes=0,telegram_sends=0,grants_action_permission=False)

def collect(w,job,day):
 """Bounded single-demand reads; saved per-job checkpoints avoid identical retries."""
 import requests
 from china_analytic_dialog import Analyst,reading
 from china_cloud_cost_control import Cache,WB,validate_identity
 from china_moysklad_read import read_stock
 from china_intraday_analysis import rate
 from china_wb_evidence import Reports
 clock=now();key=ROOT+'inputs:'+str(day)+':job:'+str(job['id']);state=w.get(key)
 if state:return state,key
 latest=w.get(ROOT+'inputs:latest:'+str(day)) or {};prior=w.get(latest.get('source_key','')) if latest.get('source_key') else None
 if prior and fresh(prior,clock,600) and prior.get('status')=='complete' and all(fresh(dict(prior['inputs'].get(k,{}),cabinet='token_3'),clock,600) for k in ['orders','statuses','prices','stock','advertising']):return prior,latest['source_key']
 state=dict(cabinet='token_3',observed_at=clock.isoformat(),day_msk=str(day),status='collecting',inputs={},errors={},wb_writes=0,telegram_sends=0)
 w.save(key,state)
 def save():w.save(key,copy.deepcopy(state))
 def get(url,params=None,body=None):
  h={'Authorization':os.environ['WB_TOKEN_3']}
  r=requests.post(url,json=body,headers=h,timeout=55,allow_redirects=False) if body is not None else requests.get(url,params=params,headers=h,timeout=55,allow_redirects=False)
  if not r.ok:raise RuntimeError('Read HTTP '+str(r.status_code))
  return r.json()
 with reading():
  validate_identity(Cache(),WB())
  start=datetime.combine(day,datetime.min.time(),MSK);cutoff=min(now(),start+timedelta(days=1));cursor=0;rows={}
  try:
   for _ in range(40):
    j=get('https://marketplace-api.wildberries.ru/api/v3/orders',dict(limit=1000,next=cursor,dateFrom=int(start.timestamp()),dateTo=int(cutoff.timestamp())));part=j.get('orders')
    if not isinstance(part,list):raise ValueError('Orders array absent')
    for o in part:
     if o['id'] in rows and rows[o['id']]!=o:raise ValueError('Conflicting order ID')
     rows[o['id']]=o
    nxt=j.get('next')
    if not part or not nxt:break
    if nxt==cursor:raise ValueError('Order cursor stuck')
    cursor=nxt;time.sleep(.5)
   else:raise ValueError('Orders pagination incomplete')
   state['inputs']['orders']=dict(rows=[{k:r.get(k) for k in ['id','nmId','article','createdAt']} for r in rows.values()],complete=True,cutoff_msk=cutoff.astimezone(MSK).isoformat(),observed_at=now().isoformat());save()
  except Exception as ex:state['errors']['orders']=type(ex).__name__;save();return state,key
  wanted={r['nmId'] for r in rows.values()};articles=sorted({r['article'] for r in rows.values()})
  an=Analyst(w,job,[]);first=day-timedelta(days=30);last=day-timedelta(days=1)
  def statuses():
   out=[];order_ids=list(rows)
   for i in range(0,len(order_ids),1000):
    j=get('https://marketplace-api.wildberries.ru/api/v3/orders/status',body={'orders':order_ids[i:i+1000]})
    if not isinstance(j.get('orders'),list):raise ValueError('Statuses array absent')
    out+=j['orders']
   if len(out)!=len(rows) or {r['id'] for r in out}!=set(rows):raise ValueError('Statuses incomplete')
   return dict(rows=out,complete=True)
  def prices():
   out=[];seen=set()
   for offset in range(0,20000,1000):
    part=get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',dict(limit=1000,offset=offset)).get('data',{}).get('listGoods')
    if not isinstance(part,list):raise ValueError('Prices page absent')
    for p in part:
     nm=p.get('nmID')
     if nm not in wanted:continue
     if nm in seen:raise ValueError('Duplicate seller price')
     seen.add(nm);values={z.get('discountedPrice') for z in p.get('sizes',[])}
     if p.get('currencyIsoCode4217')=='CNY' and len(values)==1:
      value=next(iter(values))
      try:value=num(value,True)
      except ValueError:continue
      out.append(dict(nm_id=nm,article=p.get('vendorCode'),currency='CNY',seller_price=value))
    if len(part)<1000:break
   else:raise ValueError('Prices pagination incomplete')
   return dict(rows=out,missing_ids=sorted(wanted-{r['nm_id'] for r in out}),source='Current WB seller prices, ordered IDs only')
  def advertising():
   config=get('https://advert-api.wildberries.ru/api/advert/v1/config')
   if config.get('currency')!='CNY':raise ValueError('Advertising currency unknown')
   inv=get('https://advert-api.wildberries.ru/adv/v1/promotion/count')
   if not isinstance(inv.get('adverts'),list):raise ValueError('Campaign inventory absent')
   cids=sorted({a['advertId'] for g in inv['adverts'] for a in g.get('advert_list',[])})
   if len(cids)>1000:raise ValueError('Campaign inventory exceeds bound')
   out=[]
   for i in range(0,len(cids),50):
    j=get('https://advert-api.wildberries.ru/adv/v3/fullstats',dict(ids=','.join(map(str,cids[i:i+50])),beginDate=str(day),endDate=str(day)))
    if not isinstance(j,list):raise ValueError('Advertising array absent')
    out+=j
   return dict(rows=out,catalogue=cids,all_statuses_included=True)
  def own_products():
   # Explicit completed-day cohort, separate from today's order/advertising slices.
   from china_saved_products import saved_products
   value=saved_products(w,first,last,[])
   if value is None:value=an.collect('products',[],first,last)
   return dict(value,period_from=str(first),period_to=str(last))
  for name,fn in [('statuses',statuses),('fx',lambda:rate(w,day)),('own_products',own_products),
    ('prices',prices),('stock',lambda:read_stock(articles) if articles else dict(rows=[],coverage_complete=True)),('advertising',advertising),('finance',lambda:Reports(w).finance(str(day),str(day)))]:
   try:
    value=fn();state['inputs'][name]=dict(value,observed_at=value.get('observed_at') or now().isoformat(),collected_at=now().isoformat())
   except Exception as ex:state['errors'][name]=type(ex).__name__
   save()
  external=w.get('china_agent:profit_known_costs:v1:'+str(day))
  if external:state['inputs']['external_costs']=external
 state.update(status='complete' if not state['errors'] else 'partial',observed_at=now().isoformat());save()
 if w.get(key)!=state:raise ValueError('Profit inputs readback mismatch')
 w.save(ROOT+'inputs:latest:'+str(day),dict(source_key=key));return state,key

def render(r):
 t=r['totals'];v=t.get('forecast_profit_cny');stamp=datetime.fromisoformat(r['cutoff_msk']).astimezone(MSK).strftime('%d.%m %H:%M')
 lines=[('Предварительная прибыль: '+f'{v:,.2f} ¥ (≈{t["forecast_profit_rub"]:,.0f} ₽).' if v is not None else 'Общая предварительная прибыль пока не определена: входные данные неполны.'),
  f'Китай, {r["day_msk"]}, срез заказов {stamp} МСК. Создано FBS-заказов: {int(t["orders"])}; рассчитано: {r["modelled_orders"]}. Это ожидаемый результат с учётом выкупа, не закрытая чистая прибыль.']
 for label,k in [('Ожидаемые поступления','expected_seller_revenue_cny'),('Себестоимость','cogs_cny'),('Комиссия','commission_cny'),('Налог по модели','tax_cny'),('Логистика','logistics_cny'),('Обработка','handling_cny'),('Реклама','advertising_cny'),('Прочие известные удержания','known_other_costs_cny'),('Известные доплаты','known_other_credits_cny')]:
  value=t.get(k);lines.append(label+': '+('неизвестно' if value is None else f'{value:,.2f} ¥')+'.')
 lines.append('Цена — текущая продавца, а не подтверждённая цена в момент заказа. Свой выкуп — предыдущие30 завершённых дней; малые выборки: '+str(r['fallbacks'].get('small_completed_sample_orders',0))+' заказов, допущение50% без выборки: '+str(r['fallbacks'].get('buyout50_orders',0))+'.')
 if r['fallbacks'].get('cogs_own_mpstats_orders'):lines.append('Вместо текущей COGS использована датированная своя себестоимость: '+str(r['fallbacks']['cogs_own_mpstats_orders'])+' заказов.')
 if r['fallbacks'].get('commission_policy_orders'):lines.append('Комиссия по допущению политики вместо собственной фактической ставки: '+str(r['fallbacks']['commission_policy_orders'])+' заказов.')
 if r['missing_ad_campaigns']:lines.append('Не вернулись РК: '+', '.join(map(str,r['missing_ad_campaigns']))+'; расходы по ним неизвестны, оценка может снизиться.')
 if r['unmodelled']:lines.append('Не рассчитаны '+str(len(r['unmodelled']))+' заказов: '+', '.join(sorted({x['note'] for x in r['unmodelled']}))[:400]+'.')
 if r['errors'] or r['collection_errors']:lines.append('Пробелы: '+str(r['errors'] or r['collection_errors'])[:300]+'.')
 ch=r.get('known_charges') or {}
 lines.append('Прочие удержания/доплаты — по дате опубликованных операций, не доказанно этих заказов. '+('Финансовая выгрузка неполна/ещё не опубликована. ' if not ch.get('complete') else '')+'Историческая логистика, комиссия/налог/обработка — модель; обратная логистика и общие расходы полностью не подтверждены. Пополнения РК не вычитались.')
 lines.append('Источники: WB FBS/цены/реклама, МойСклад МСК, своя статистика MPStats, опубликованные финоперации WB, ЦБ. Время рекламы: '+str(r['source_times'].get('advertising','нет данных'))+'.')
 return '\n'.join(lines)

def requested(text):
 if re.search(r'научи|внедри|исправ|что такое|как (?:счита|рассчит)|объясни|запомни|сравни',text,re.I):return False
 return bool(re.search(r'прибыл|чистыми|финрезультат|сколько.*заработ|сколько.*зарабат',text,re.I) and re.search(r'сегодня|сейчас|вчера|предвар|посчитай|рассчитай|сколько',text,re.I))

def forecast(w,job,date_msk,nm_ids=()):
 day=date.fromisoformat(date_msk);today=w.now.astimezone(MSK).date()
 if day>today or (today-day).days>30:raise ValueError('Forecast needs one date within prior30 days')
 known={int(n) for n,_ in w.catalog()}
 if len(nm_ids)>30 or any(type(n)is not int or n not in known for n in nm_ids):raise ValueError('Exact China product identity required')
 state,source=collect(w,job,day)
 result=calculate(state,w.get('china_agent:new_ad_economics_policy:v1') or {},w.get('china_agent:expected_profit_delivery_model:v1') or {},day,nm_ids)
 result.update(source_key=source,observed_at=now().isoformat())
 key=ROOT+'result:'+str(day)+':job:'+str(job['id'])+':'+hashlib.sha256(json.dumps(sorted(nm_ids)).encode()).hexdigest()[:12]
 old=w.get(key)
 if old:result=old
 else:
  w.save(key,result)
  if w.get(key)!=result:raise ValueError('Profit calculation readback mismatch')
 result['calculation_key']=key;return result

def handle(w,job,history=()):
 text=job.get('request_text','')
 if not requested(text):return None
 from china_analytic_evidence import resolve_scope
 ids,unknown=resolve_scope(w.catalog(),text)
 if not ids and not unknown and re.search(r'этой модел|этого арт|этой сумк|по ней',text,re.I):
  for h in reversed(history[-4:]):
   ids,unknown=resolve_scope(w.catalog(),h.get('request_text',''))
   if ids or unknown:break
  if not ids:unknown=True
 if unknown:return 'Не удалось однозначно определить артикул для расчёта прибыли; общий кабинет вместо него не считал.',[dict(name='profit_scope_unresolved',read_only=True)]
 today=w.now.astimezone(MSK).date();day=today-timedelta(days=1 if re.search(r'вчера',text,re.I) else 0)
 explicit=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',text)
 if explicit:
  if len(set(explicit))!=1:return None
  try:day=date.fromisoformat(explicit[0])
  except ValueError:return None
 if day>today or re.search(r'недел|за.*\d+\s*дн',text,re.I):return None
 try:
  result=forecast(w,job,str(day),ids)
  return render(result),[dict(name='calculate_preliminary_profit',read_only=True,result={k:v for k,v in result.items() if k!='details'},source_key=result['calculation_key'])]
 except Exception as ex:
  return 'Предварительная прибыль не рассчитана: '+type(ex).__name__+'. Не хватает подтверждённых входных данных; неизвестные расходы и прибыль не считаю нулём.',[dict(name='calculate_preliminary_profit',read_only=True,result=dict(available=False,error=type(ex).__name__))]

