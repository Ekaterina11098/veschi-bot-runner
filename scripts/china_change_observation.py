"""All verified China changes: sourced observations, total-profit comparisons, no execution."""
import contextlib,hashlib,json,os,re
from datetime import datetime,date,timedelta,timezone
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow')
ROOT='china_agent:change_observation:v2:'
MANIFEST='china_agent:change_observation_manifest:v2'
KINDS={'price_change','bid_change','sku_exclusion','new_campaign'}

def stamp():return datetime.now(timezone.utc).isoformat()
def num(v):
 if isinstance(v,bool) or not isinstance(v,(int,float)) or not __import__('math').isfinite(v):raise ValueError('Missing finite amount')
 return v
def window(e,today):
 changed=datetime.fromisoformat(e['started_at'].replace('Z','+00:00')).astimezone(MSK).date()
 # Price decisions require four full days; preserve specifically agreed ad windows.
 target=4 if e['action']['kind']=='price_change' else int(e.get('comparison',{}).get('days',4))
 n=min(target,max(0,(today-changed).days-1))
 return dict(changed_on=str(changed),days=n,target_days=target,final=n==target,
  before_from=str(changed-timedelta(days=n)),before_to=str(changed-timedelta(days=1)),
  after_from=str(changed+timedelta(days=1)),after_to=str(changed+timedelta(days=n)),
  evaluate_from=str(changed+timedelta(days=target+1)),excluded_change_day=str(changed))

class BudgetExceeded(RuntimeError):pass
class Reader:
 def __init__(self,w,budget=40):self.w=w;self.left=budget;self.requests=0
 def read(self,tool,args):
  identity=json.dumps(dict(tool=tool,args=args),sort_keys=True)
  key=ROOT+'source:'+hashlib.sha256(identity.encode()).hexdigest()
  cached=self.w.get(key)
  if cached and cached.get('day_msk')==str(self.w.now.astimezone(MSK).date()):return cached['observation'],key
  if self.left<=0:raise BudgetExceeded('Read budget; continue on existing backup')
  from analytics.mpstats_probe import discover
  from analytics.mpstats_gaps import execute_reads
  pause=self.w.db('GET','telegram_api_cache',params=dict(cache_key='eq.mpstats:cooldown',expires_at='gt.'+stamp(),select='cache_key',limit=1))
  if pause:raise BudgetExceeded('Shared MPStats cooldown')
  observations=[]
  def persist(cabinet,obs):
   if cabinet!='token_3' or obs.get('tool')!=tool or obs.get('arguments')!=args:raise ValueError('Observation source scope')
   if obs.get('retry_after'):
    seconds=max(60,int(obs['retry_after']))
    self.w.db('POST','telegram_api_cache',params={'on_conflict':'cache_key'},body=dict(cache_key='mpstats:cooldown',payload=dict(pending=True,source='change_observation'),updated_at=stamp(),expires_at=(datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat()),prefer='resolution=merge-duplicates,return=representation')
    raise BudgetExceeded('MPStats cooldown; no blind retry')
   if obs.get('scope_verified') is True and obs.get('status')=='received':observations.append(obs)
  task=dict(cabinet='token_3',tool=tool,key=key,priority=75,arguments=args)
  def extra(call,checks,known):return execute_reads(call,checks,known,[task],{},persist,max_requests=1)
  self.left-=1;self.requests+=1
  discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=extra)
  if len(observations)!=1:raise ValueError('MPStats observation incomplete')
  value=dict(day_msk=str(self.w.now.astimezone(MSK).date()),observation=observations[0],observed_at=stamp())
  self.w.save(key,value);return observations[0],key
 def wb_orders(self,first,last,ids):
  key=ROOT+'wb_orders:'+first+':'+last
  saved=self.w.get(key)
  if saved and saved.get('day_msk')==str(self.w.now.astimezone(MSK).date()):return saved,key
  if self.left<=0:raise BudgetExceeded('WB read budget')
  from china_analytic_dialog import Analyst
  self.left-=1;self.requests+=1
  result=Analyst(self.w,{},[]).collect('orders',ids,date.fromisoformat(first),date.fromisoformat(last))
  if result.get('orders') is None:raise ValueError('WB order universe unavailable')
  saved=dict(result,day_msk=str(self.w.now.astimezone(MSK).date()));self.w.save(key,saved);return saved,key
 def advertising(self,first,last,campaign_ids):
  ids=sorted(set(campaign_ids));key=ROOT+'ad_funnel:'+first+':'+last+':'+hashlib.sha256(str(ids).encode()).hexdigest()[:12]
  old=self.w.get(key)
  if old and old.get('day_msk')==str(self.w.now.astimezone(MSK).date()):return old,key
  import requests
  rows=[]
  for offset in range(0,len(ids),50):
   if self.left<=0:raise BudgetExceeded('Advertising read budget')
   self.left-=1;self.requests+=1
   response=requests.get('https://advert-api.wildberries.ru/adv/v3/fullstats',headers={'Authorization':os.environ['WB_TOKEN_3']},params=dict(ids=','.join(map(str,ids[offset:offset+50])),beginDate=first,endDate=last),timeout=60)
   if not response.ok:raise ValueError('Advertising HTTP '+str(response.status_code))
   data=response.json()
   if not isinstance(data,list):raise ValueError('Advertising report malformed')
   for campaign in data:
    if campaign['advertId'] not in ids or campaign.get('currency')!='CNY':raise ValueError('Advertising identity/currency unconfirmed')
    for day in campaign.get('days',[]):
     if not first<=day['date'][:10]<=last:raise ValueError('Ad day outside period')
     for app in day.get('apps',[]):
      for sku in app.get('nms',[]):rows.append(dict(campaign_id=campaign['advertId'],date=day['date'][:10],nm_id=sku['nmId'],views=sku.get('views'),clicks=sku.get('clicks'),orders=sku.get('orders'),amount_cny=sku.get('sum_price'),spend_cny=sku.get('sum')))
  value=dict(day_msk=str(self.w.now.astimezone(MSK).date()),rows=rows,source='WB fullstats SKU/app, historical and current campaign IDs; absent rows unknown',observed_at=stamp())
  self.w.save(key,value);return value,key
 def campaign_ids(self):
  key=ROOT+'campaign_catalogue:'+str(self.w.now.astimezone(MSK).date());old=self.w.get(key)
  if old:return old['ids']
  if self.left<=0:raise BudgetExceeded('Campaign catalogue read budget')
  import requests
  self.left-=1;self.requests+=1
  r=requests.get('https://advert-api.wildberries.ru/adv/v1/promotion/count',headers={'Authorization':os.environ['WB_TOKEN_3']},timeout=40)
  if not r.ok:raise ValueError('Campaign catalogue HTTP '+str(r.status_code))
  ids=sorted({a['advertId'] for group in r.json().get('adverts',[]) for a in group.get('advert_list',[])})
  self.w.save(key,dict(ids=ids,observed_at=stamp(),all_statuses=True));return ids
 def table(self,tool,args,nm=None):
  rows=[];keys=[];offset=0;total=None
  while True:
   size=300 if tool=='lk_wb_card_orders' else 1000
   a=dict(args,start_row=offset,end_row=offset+size);o,key=self.read(tool,a);body=o['data']
   if isinstance(body.get('data'),dict):body=body['data']
   part=body.get('data');count=body.get('total')
   if not isinstance(part,list) or type(count) is not int or body.get('need_update') not in (None,0):raise ValueError('Report not complete')
   if total is not None and total!=count:raise ValueError('Pagination total changed')
   total=count;keys.append(key);rows+=part
   if tool=='lk_wb_card_orders':
    filters=body.get('filterModel') or {};d=filters.get('order_dt') or {};p=filters.get('product_id') or {}
    if str(p.get('filter'))!=str(args['value']) or d.get('dateFrom')!=args['date_from'] or d.get('dateTo')!=args['date_to']:raise ValueError('Order filter mismatch')
    if any(int(r.get('nm_id',0))!=nm or r.get('api_id')!=10026946 for r in part):raise ValueError('Order cabinet/SKU mismatch')
   if len(rows)==total:return rows,keys
   if len(rows)>total or not part or offset>=20000:raise ValueError('Pagination incomplete')
   offset+=size

def outcomes(rows,nm,article,first,last):
 result=dict(orders=0,paid=0,returned=0,refused=0,cancelled=0,pending=0,unknown=0,completed=0);seen={};selected=[]
 for row in rows:
  if int(row.get('nm_id',0))!=nm or row.get('sa_name','').casefold()!=article.casefold():raise ValueError('Cohort identity mismatch')
  at=datetime.fromisoformat(row['order_dt'].replace('Z','+00:00'));day=str(at.date() if at.tzinfo is None else at.astimezone(MSK).date())
  if not first<=day<=last:raise ValueError('Order outside requested period')
  rid=row.get('srid')
  # gnumber may cover multiple real units. Only srid authorizes deduplication.
  if rid:
   rid=str(rid)
   if rid in seen:
    if seen[rid]!=row:raise ValueError('Conflicting duplicate order')
    continue
   seen[rid]=row
  elif not row.get('gnumber'):raise ValueError('Order reference missing')
  selected.append(row);result['orders']+=1
  billed,returned=row.get('billed_times'),row.get('refunded_times');back=row.get('backlogistic_times');cancel=row.get('is_canceled_order')
  if billed not in (0,1) or returned not in (0,1) or returned>billed:result['unknown']+=1
  elif returned:result['returned']+=1
  elif billed:result['paid']+=1
  elif cancel in (1,True):result['cancelled']+=1
  elif back in (1,True):result['refused']+=1
  elif cancel in (0,False) and back==0:result['pending']+=1
  else:result['unknown']+=1
 result['completed']=sum(result[k] for k in ['paid','returned','refused','cancelled'])
 result['buyout_pct']=100*result['paid']/result['completed'] if result['completed'] else None
 return result,selected

def expected(rows,cohort,own,stock,policy):
 """Accounted expected total, not full actual/closed profit. Every assumption disclosed."""
 missing=['Общие удержания SKU не подтверждены','Дополнительный возврат на склад РФ не подтверждён']
 notes=[];fx=num(policy.get('fx_rub_cny'));handling=num(policy.get('handling_rub'))
 if fx!=12:raise ValueError('Agreed valuation changed')
 done=cohort['completed'];paid=cohort['paid'];basis='own_period_completed'
 if not done:
  done=own.get('finished_orders');paid=own.get('is_payed');basis='own_30_full_days_scenario_not_period_buyout'
 if done is None or paid is None:raise ValueError('Own completed sample incomplete')
 if done==0:p=.5;basis='fallback50_no_own_completed_sample';notes.append('50% только сценарий: собственной завершённой выборки нет')
 else:
  if not 0<=paid<=done:raise ValueError('Buyout counts invalid')
  p=paid/done
 cost=num(stock.get('price'))/100
 log=policy.get('logistics_by_nm',{}).get(str(own['nm_id'])) or {};delivery=num(log.get('delivery_cny'))*fx
 if cost<=0 or delivery<=0 or handling<0:raise ValueError('Own cost/logistics not verified')
 rate=own.get('total_commission_without_spp_in_sales')
 if rate is None:rate=num(policy.get('commission_pct'));missing.append('Комиссия сценарная, не подтверждённый тариф каждого заказа')
 fee=rate/100;tax=num(policy.get('tax_pct'))/100
 missing.append('Налог '+str(policy['tax_pct'])+'% — сценарное допущение кабинета')
 if not 0<=fee<1 or not 0<=tax<1:raise ValueError('Fee/tax outside range')
 advertising=num(own.get('_period_advertising_rub'));value=-advertising
 for row in rows:
  revenue=num(row.get('retail_price_withdisc_rub'))
  if revenue<=0:raise ValueError('Order seller revenue not verified')
  # Delivery reserve covers every order; cancellations before dispatch still unresolved.
  value+=p*(revenue*(1-fee-tax)-cost)-delivery-handling
 notes+=['Логистика историческая; резерв на каждый заказ, включая отменённые', 'Цена каждого заказа retail_price_withdisc_rub; COGS текущая МойСклад', 'Реклама вычтена один раз полностью; WBPromotion повторно не добавлен', 'Выкуп каждого периода отдельно; незавершённые исключены']
 return dict(value=round(value,2),method='expected_accounted_order_date_v2',is_actual=False,all_expenses_confirmed=False,
  currency='RUB',fx_rub_cny=fx,buyout_probability=p,buyout_basis=basis,buyout_sample=done,
  missing_costs=missing,assumptions=notes,advertising_rub=advertising)

def closed_profit(bundle,first,last):
 """Only an explicitly reconciled order-cohort ledger can be called full actual profit."""
 if not bundle:return dict(value=None,method='actual_closed_order_cohort',missing=['Нет полного сверенного реестра расходов закрытой когорты'])
 required=['closed','reconciled','tax_confirmed','cogs_confirmed','all_logistics_confirmed','all_shared_costs_confirmed','advertising_reconciled']
 if bundle.get('period_from')!=first or bundle.get('period_to')!=last or not all(bundle.get(k) is True for k in required) or not bundle.get('source_ids'):return dict(value=None,method='actual_closed_order_cohort',missing=['Реестр расходов/закрытие когорты не подтверждены'])
 ids=bundle.get('expense_ids')
 if not isinstance(ids,list) or len(ids)!=len(set(ids)):raise ValueError('Duplicate or missing cost identities')
 if bundle.get('currency')!='RUB':raise ValueError('Actual profit currency mismatch')
 return dict(value=num(bundle.get('net_profit_rub')),method='actual_closed_order_cohort',currency='RUB',source_ids=bundle['source_ids'],is_actual=True)

def ad_funnel(rows,nm,first,last):
 selected=[r for r in rows if r['nm_id']==nm and first<=r['date']<=last]
 if not selected:return dict(views=None,clicks=None,orders=None,ctr_pct=None,cpc_cny=None,click_order_pct=None,status='missing_SKU_rows_not_zero',scope='advertising_only')
 fields=['views','clicks','orders','spend_cny']
 if any(any(r.get(f) is None for f in fields) for r in selected):raise ValueError('Advertising funnel incomplete')
 v={f:sum(r[f] for r in selected) for f in fields}
 return dict(v,ctr_pct=100*v['clicks']/v['views'] if v['views'] else None,cpc_cny=v['spend_cny']/v['clicks'] if v['clicks'] else None,
  click_order_pct=100*v['orders']/v['clicks'] if v['clicks'] else None,status='observed_advertising_rows',scope='advertising_only',
  day_count=len({r['date'] for r in selected}),note='Only returned SKU/app rows; organic impressions and organic clicks not inferred')

def general_traffic(w,nm,first,last,ad):
 """Accept only verified all-channel or disjoint organic/ad observations; never add overlapping totals."""
 source=w.get('china_agent:total_traffic:v1:'+str(nm)+':'+first+':'+last)
 result=dict(total_impressions=None,organic_impressions=None,total_ctr_pct=None,scope='all_sources',status='unavailable',
  missing='Общие показы есть в расширенной воронке WB UI, но отсутствуют в проверенной API/MCP выгрузке. Нужна выгрузка точного SKU/периода.',algorithm_change='not_established')
 if not source:return result
 if source.get('cabinet')!='token_3' or source.get('nm_id')!=nm or source.get('period_from')!=first or source.get('period_to')!=last or not source.get('source_id') or source.get('semantics_verified') is not True:return dict(result,status='unverified_source')
 total=source.get('total_impressions');organic=source.get('organic_impressions');paid=source.get('advertising_impressions')
 if total is not None:total=num(total)
 if organic is not None:organic=num(organic)
 if any(v is not None and num(v)<0 for v in [total,organic,paid,source.get('total_clicks')]):raise ValueError('Negative traffic counter')
 comparable=source.get('components_disjoint') is True and source.get('same_unit_and_period') is True
 if total is None and organic is not None and paid is not None and comparable:total=organic+num(paid)
 if organic is None and total is not None and paid is not None and comparable and total>=num(paid):organic=total-paid
 clicks=source.get('total_clicks')
 return dict(result,total_impressions=total,organic_impressions=organic,total_ctr_pct=100*clicks/total if total and clicks is not None else None,
  status='verified' if total is not None else 'components_not_reconcilable',source_id=source['source_id'],missing=None if total is not None else result['missing'],
  note='Общие показы уже включают рекламу; рекламные не добавлены повторно. Сопоставление периодов, единиц и непересечения обязательно.')

def verdict(before,after,win,confounders,current_matches):
 expected_b,expected_a=before['expected'],after['expected'];actual_b,actual_a=before['actual'],after['actual']
 actual=actual_b.get('value') is not None and actual_a.get('value') is not None
 b,a=(actual_b,actual_a) if actual else (expected_b,expected_a)
 delta=a['value']-b['value'];orders_delta=after['orders']-before['orders']
 decline=before.get('click_order_pct') is not None and after.get('click_order_pct') is not None and after['click_order_pct']<before['click_order_pct']
 sample=min(expected_b['buyout_sample'],expected_a['buyout_sample'])
 status='positive' if delta>0 else 'negative' if delta<0 else 'unchanged'
 if delta>0 and (orders_delta<0 or decline):status='mixed'
 if after['orders']==0 and delta>0:status='mixed' # Saved expense is not growth in earnings.
 if not win['final']:status='interim_'+status
 reliable=actual or (expected_b.get('all_expenses_confirmed') and expected_a.get('all_expenses_confirmed'))
 rollback=win['final'] and delta<0 and (orders_delta<0 or decline) and reliable and sample>=5 and min(before['orders'],after['orders'])>=5 and not confounders and current_matches
 action='Предложить возврат прежнего параметра; требуется подтверждение' if rollback else 'Разобрать ухудшение: прибыль предварительная/малая выборка/параллельные изменения' if delta<0 else 'Сохранить параметр; пересмотреть при изменении условий'
 if not win['final']:action='Промежуточно; оценка '+win['evaluate_from']
 return dict(status=status,delta_total_profit_rub=round(delta,2),profit_basis='actual' if actual else 'expected_preliminary',
  delta_orders=orders_delta,conversion_declined=decline,rollback_recommended=rollback,recommendation=action,
  execution_authorized=False,causality='not_established',sample_size=sample,confounders=confounders,current_parameter_matches=current_matches,
  missing_costs=sorted(set(expected_b.get('missing_costs',[])+expected_a.get('missing_costs',[]))) if not actual else [])

def parameter_matches(action,nm,source):
 kind=action['kind']
 if kind=='price_change':
  prices=[r for r in source['prices'] if r['nmID']==nm]
  return len(prices)==1 and abs(prices[0]['sizes'][0]['discountedPrice']-float(action['after']))<.011
 campaign=source['campaigns'].get(action.get('campaign_id')) or source['campaigns'].get(str(action.get('campaign_id')))
 member=next((r for r in (campaign or {}).get('nm_settings',[]) if r['nm_id']==nm),None)
 if kind=='sku_exclusion':return member is None and campaign is not None
 if kind=='bid_change':return member is not None and member.get('bids_kopecks',{}).get('recommendations')==action['after']
 return campaign is not None and member is not None

def observe_event(w,e,events,source,reader):
 win=window(e,w.now.astimezone(MSK).date());ids=e['action']['nm_ids'];results=[]
 if not win['days']:return dict(status='waiting_full_days',event_id=e['event_id'],window=win,rows=[],next_evaluation=win['evaluate_from'])
 if source is None:raise BudgetExceeded('Register first; source collection pending')
 catalogue={int(r['nm_id']):r for r in source['products']};stocks={r.get('article','').casefold():r for r in source['stock']};sources=[]
 for nm in ids:
  own=catalogue.get(nm)
  if not own:raise ValueError('Own SKU absent; not zero')
  article=own['sa_name'];pid=own.get('p_id');stock=stocks.get(article.casefold())
  if pid is None or not stock:raise ValueError('Product mapping/COGS missing')
  pair=[]
  for label in ['before','after']:
   first,last=win[label+'_from'],win[label+'_to']
   products,keys=reader.table('lk_wb_products',dict(date_from=first,date_to=last));sources+=keys
   variants=[r for r in products if int(r.get('nm_id',0))==nm]
   if len(variants)!=1:raise ValueError('Period product missing/ambiguous')
   r=variants[0];raw,keys=reader.table('lk_wb_card_orders',dict(type='products',value=str(pid),date_from=first,date_to=last),nm);sources+=keys
   cohort,raw=outcomes(raw,nm,article,first,last)
   counts=r.get('orders_count');spark=r.get('sparkline_orders')
   wb,key=reader.wb_orders(first,last,list(catalogue));sources.append(key)
   wb_count=sum(o['nmId']==nm for o in wb['orders'])
   # WB is the independent order universe; cancellation exclusions are disclosed.
   if wb_count!=cohort['orders']:raise ValueError('WB and MPStats cohort counts differ; do not substitute order universes')
   if counts not in [cohort['orders'],cohort['orders']-cohort['cancelled']] or not isinstance(spark,list) or sum(spark)!=counts:raise ValueError('Product counters do not reconcile')
   ad=num(r.get('advertisement'));amount=num(r.get('orders_sum'))
   exp=expected(raw,cohort,dict(own,_period_advertising_rub=ad),stock,source['policy'])
   bundle=w.get('china_agent:closed_profit_ledger:v1:'+str(nm)+':'+first+':'+last)
   actual=closed_profit(bundle,first,last)
   views=r.get('open_card_count');fo=r.get('funnel_orders_count')
   try:
    campaign_ids=reader.campaign_ids();ad_source,ad_key=reader.advertising(first,last,campaign_ids);sources.append(ad_key)
    advertising=ad_funnel(ad_source['rows'],nm,first,last)
   except BudgetExceeded:raise
   except Exception as ex:advertising=dict(scope='advertising_only',status='source_unavailable',views=None,clicks=None,missing=type(ex).__name__)
   traffic=general_traffic(w,nm,first,last,advertising)
   pair.append(dict(period_from=first,period_to=last,days=win['days'],orders=cohort['orders'],outcomes=cohort,
    views=views,funnel_orders=fo,click_order_pct=100*fo/views if views and fo is not None else None,
    actual_drr_pct=100*ad/amount if amount else None,ad_spend_rub=ad,order_amount_rub=amount,expected=exp,actual=actual,
    wb_orders=wb_count,product_statistic_orders=counts,orders_include_cancellations=True,advertising_funnel=advertising,general_traffic=traffic,
    customer_price=r.get('price_after_spp'),spp=r.get('price_spp'),price_note='Current source snapshot, not historical SPP'))
  confounders=[]
  for other in events:
   if other['event_id']==e['event_id'] or nm not in other.get('action',{}).get('nm_ids',[]):continue
   day=datetime.fromisoformat(other['started_at'].replace('Z','+00:00')).astimezone(MSK).date()
   if win['before_from']<=str(day)<=win['after_to']:confounders.append(other['event_id'])
  result=verdict(*pair,win,confounders,parameter_matches(e['action'],nm,source))
  rollback=dict(kind=e['action']['kind'],nm_id=nm,article=article,campaign_id=e['action'].get('campaign_id'),current=e['action'].get('after'),proposed=e['action'].get('before'),requires_fresh_minimum=True if e['action']['kind']=='bid_change' else None,execution_authorized=False)
  if e['action']['kind']=='new_campaign':rollback['proposed']='Предложить исключение только этого SKU из созданной РК; общую РК не останавливать'
  results.append(dict(nm_id=nm,article=article,before=pair[0],after=pair[1],result=result,rollback=rollback,
   context=dict(stock_available=stock['stock']-stock['reserve'],seller_price=next((p['sizes'][0]['discountedPrice'] for p in source['prices'] if p['nmID']==nm),None))))
 total_before=sum(r['before']['expected']['value'] for r in results);total_after=sum(r['after']['expected']['value'] for r in results)
 totals=dict(expected_before_rub=round(total_before,2),expected_after_rub=round(total_after,2),delta_expected_rub=round(total_after-total_before,2),
  actual_before_rub=sum(r['before']['actual']['value'] for r in results) if all(r['before']['actual'].get('value') is not None for r in results) else None,
  actual_after_rub=sum(r['after']['actual']['value'] for r in results) if all(r['after']['actual'].get('value') is not None for r in results) else None,
  expected_is_preliminary=True,profit_per_order_used_for_selection=False)
 return dict(status='observed',event_id=e['event_id'],observed_at=stamp(),window=win,rows=results,totals=totals,source_keys=sorted(set(sources)),wb_writes=0)

def refresh(w,source,budget=40):
 from china_experience import sync,read_rows,save,ROOT as EXPERIENCE
 sync(w);events=[r['payload'] for r in read_rows(w,EXPERIENCE,limit=5000) if r.get('payload',{}).get('record_type')=='verified_action' and r['payload'].get('action',{}).get('kind') in KINDS]
 if len(events)>=5000:raise ValueError('History pagination required; coverage cannot be claimed')
 today=str(w.now.astimezone(MSK).date());reader=Reader(w,budget);counts={};records=[]
 for e in sorted(events,key=lambda x:x['started_at']):
  key=ROOT+e['event_id'];old=w.get(key);win=window(e,w.now.astimezone(MSK).date())
  if old and old.get('checked_day')==today and old.get('status') in ['observed','waiting_full_days']:
   records.append(old);continue
  try:record=observe_event(w,e,events,source,reader)
  except BudgetExceeded:
   record=dict(status='pending_read_budget',event_id=e['event_id'],window=win,rows=[],retry_on_existing_backup=True)
  except Exception as ex:
   record=dict(status='incomplete',event_id=e['event_id'],window=win,rows=[],error=type(ex).__name__,missing=str(ex)[:240] if isinstance(ex,(ValueError,RuntimeError)) else 'Источник недоступен')
  record.update(checked_day=today,action=e['action'],started_at=e['started_at'],source_key=e['source_key']);save(w,key,record);records.append(record)
  if record['status']=='observed':
   save(w,ROOT+'history:'+e['event_id']+':'+today,record)
   prior=w.get(EXPERIENCE+e['event_id']);observations=prior.setdefault('observations',[])
   observations.append(dict(observation_schema='change_outcomes_v2',observed_at=stamp(),window=win,rows=record['rows'],source_keys=record['source_keys']))
   prior['observations']=observations # Preserve positive and negative observations, including revisions.
   directions={r['result']['status'] for r in record['rows']};delta=record['totals']['delta_expected_rub'];prior['expected_outcome']='negative' if win['final'] and delta<0 else 'positive' if win['final'] and delta>0 and 'mixed' not in directions else 'mixed' if win['final'] else 'pending'
   prior['business_outcome']=prior['expected_outcome'] if all(r['result']['profit_basis']=='actual' for r in record['rows']) else 'inconclusive' if win['final'] else 'pending'
   prior.update(latest_change_observation=record,last_observed_at=stamp(),outcome_basis='expected_preliminary_or_explicit_closed_actual',causality='not_established')
   save(w,EXPERIENCE+e['event_id'],prior)
 for r in records:counts[r['status']]=counts.get(r['status'],0)+1
 manifest=dict(checked_day=today,observed_at=stamp(),event_count=len(events),counts=counts,event_ids=[e['event_id'] for e in events],
  status='complete_coverage' if all(r['status'] in ['observed','waiting_full_days'] for r in records) else 'partial',source_requests=reader.requests,wb_writes=0,
  note='Every verified change retained, including incomplete and waiting. No automatic rollback. Existing backup continues cached reads.')
 save(w,MANIFEST,manifest);return manifest

def compact(w,include_all=False):
 manifest=w.get(MANIFEST) or {};lines=[]
 cohort=w.get('china_agent:loss_cohort:v1') or {};tracked={int(r['nm_id']) for r in cohort.get('items',[])};seen=set()
 for eid in reversed(manifest.get('event_ids',[])):
  e=w.get(ROOT+eid) or {};win=e.get('window',{})
  if not win.get('final'):continue # No waiting/non-informative block before evaluation.
  for row in e.get('rows',[]):
   if row['nm_id'] in seen:continue
   r=row['result']
   if not include_all and row['nm_id'] not in tracked and r['status'] not in ['negative','mixed']:continue
   seen.add(row['nm_id']);b,a=row['before'],row['after'];basis=r['profit_basis'];field='actual' if basis=='actual' else 'expected'
   money=lambda p:str(round(p[field]['value'])) if p[field].get('value') is not None else 'нет данных'
   lines.append(row['article']+' | '+money(b)+' → '+money(a)+' ₽ | Δ '+str(round(r['delta_total_profit_rub']))+' ₽ | '+r['recommendation']+(' · предварительная' if basis!='actual' else ' · закрытая когорта')+' · '+b['period_from']+'–'+b['period_to']+' → '+a['period_from']+'–'+a['period_to'])
 return lines

@contextlib.contextmanager
def network_guard():
 import requests
 from urllib.parse import urlparse
 from china_analytic_dialog import allowed_read,reading
 original=requests.sessions.Session.request;host=urlparse(os.environ['SUPABASE_URL']).hostname
 def bounded(session,method,url,*a,**kw):
  u=urlparse(url);m=method.upper();body=kw.get('json') or {}
  database=u.hostname==host and u.path.startswith('/rest/v1/') and (m=='GET' or m in ['POST','PATCH'] and u.path.rsplit('/',1)[-1] in ['telegram_api_cache','analytics_snapshots'])
  card=u.hostname=='mcp.mpstats.io' and u.path=='/mcp' and m=='POST' and body.get('method')=='tools/call' and body.get('params',{}).get('name')=='lk_wb_card_orders'
  if not (database or card or allowed_read(m,url,body)):raise PermissionError('Outcome collection is read-only, no Telegram/WB writes')
  return original(session,method,url,*a,**kw)
 with reading():
  requests.sessions.Session.request=bounded
  try:yield
  finally:requests.sessions.Session.request=original

def daily(budget=60,verify=False):
 from conversion_watches import runtime
 from china_price_apply import IO
 from china_new_ad_reports import source
 w=runtime();day=str(w.now.astimezone(MSK).date());pair=w.get('china_agent:advertising_delivery:'+day+':v1') or {}
 if not verify and (pair.get('status')!='delivered' or {p.get('kind') for p in pair.get('parts',[]) if p.get('status')=='sent' and p.get('message_id')}!={'drr','budgets'}):return dict(status='waiting_advertising_pair',wb_writes=0)
 previous=w.get(MANIFEST) or {}
 if previous.get('checked_day')==day and previous.get('status')=='complete_coverage':return dict(status='already_checked',wb_writes=0)
 with network_guard():
  registry=refresh(w,None,0)
  if registry['status']=='complete_coverage':return registry
  class SourceIO(IO):
   # JSON object keys are strings in durable storage. Normalize only this read-source
   # cache; marketplace execution state machines and their readback checks stay intact.
   def put(self,key,value):return super().put(key,json.loads(json.dumps(value)))
   def create(self,key,value):return super().create(key,json.loads(json.dumps(value)))
   def wb(self,path,method='GET',body=None):
    if method!='GET':raise PermissionError('Observation source WB writes forbidden')
    return super().wb(path,method,body)
  try:s=source(SourceIO())
  except Exception as ex:
   w.save(ROOT+'source_error:'+day,dict(status='blocked',error=type(ex).__name__,detail=str(ex)[:500],observed_at=stamp(),registry=registry,wb_writes=0))
   return dict(registry,status='source_blocked')
  return refresh(w,s,budget)

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--verify',action='store_true');p.add_argument('--budget',type=int,default=60);args=p.parse_args()
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner':raise SystemExit('Public runner only')
 try:value=daily(max(1,min(args.budget,120)),args.verify)
 except Exception as ex:
  from conversion_watches import runtime
  try:runtime().save(ROOT+'run_error',dict(error=type(ex).__name__,detail=str(ex)[:600],observed_at=stamp(),wb_writes=0))
  except Exception:pass
  print(json.dumps(dict(status='blocked',error=type(ex).__name__,wb_writes=0)));raise SystemExit(1) from None
 print(json.dumps({k:value.get(k) for k in ['status','event_count','counts','source_requests','wb_writes']}))

