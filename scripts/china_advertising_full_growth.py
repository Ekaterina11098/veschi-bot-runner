"""Whole-cabinet daily growth evidence. Read-only; resumes stages, never sends or changes WB."""
import copy,json,math
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo
ROOT='china_agent:advertising_full_growth:'
def normalized(v):return json.loads(json.dumps(v))
def save_analytic_cache(io,key,value):
 """Analyst cache entries are new per period; PATCH cannot create a missing row."""
 if not key.startswith('china_agent:analytic_read:v1:'):
  raise ValueError('Unexpected analytical cache key')
 value=normalized(value)
 if io.get(key) is None:
  io.create(key,value)
 else:
  io.put(key,value)
 if io.get(key)!=value:
  raise RuntimeError('Analytical cache readback mismatch')
def stamp():return datetime.now(timezone.utc).isoformat()
def enabled(io):return (io.get('china_agent:advertising_format:v2')or{}).get('full_cabinet_growth_review_required')is True
def collect(io,s,day):
 from china_advertising_v2 import http,history
 from china_morning_readiness import published_stock,PendingAdvertisingDay
 from china_moysklad_read import read_stock
 from china_advertising_economic_review import model_rows
 from china_analytic_dialog import Analyst,reading
 from china_intraday_analysis import rate
 from urllib.parse import urlencode
 key=ROOT+day+':v1:inputs';v=io.get(key)or dict(status='collecting',created_at=stamp(),cabinet='token_3')
 def save():io.put(key,normalized(v)) if io.get(key) else io.create(key,normalized(v))
 class Work:
  now=datetime.now(timezone.utc)
  def get(self,k):return io.get(k)
  def save(self,k,value,**kw):save_analytic_cache(io,k,value)
  def db(self,method,table,params=None):
   if method!='GET'or table!='analytics_snapshots':raise ValueError('Only own analytics reads')
   return io.db(table+'?'+urlencode(params or{}))
  def catalog(self):return [(str(r['nmID']),r['vendorCode'])for r in s['catalogue']['rows']]
 policy=io.get('china_agent:advertising_format:v2')or{}
 excluded=set(policy.get('growth_excluded_nm_ids',[1473245494,1473245510,1473244000]))
 ids=v.get('screened_nm_ids')or sorted({int(r['nmID'])for r in s['catalogue']['rows']}-excluded)
 end=date.fromisoformat(day)-timedelta(days=1);first=end-timedelta(days=29)
 try:
  if 'own'not in v:
   with reading():v['own']=Analyst(Work(),dict(request_text='Полный разбор рекламного роста'),[]).live('products',[],str(first),str(end))
   v['own'].update(period_from=str(first),period_to=str(end));save()
  if 'prices'not in v:
   goods=[]
   for offset in range(0,20000,1000):
    part=io.wb('/api/v2/list/goods/filter?limit=1000&offset='+str(offset)).get('listGoods')
    if not isinstance(part,list):raise ValueError('Price pagination unknown')
    goods+=part
    if len(part)<1000:break
   else:raise ValueError('Price pagination bound')
   catalogue={int(r['nmID']):r for r in s['catalogue']['rows']}
   catalogue.update({int(g['nmID']):g for g in goods})
   ids=sorted(set(catalogue)-excluded);v['catalogue']=dict(s['catalogue'],rows=list(catalogue.values()));v['screened_nm_ids']=ids
   rows=[];missing={}
   for nm in ids:
    matches=[g for g in goods if g['nmID']==nm]
    if len(matches)!=1:missing[str(nm)]='missing_or_ambiguous';continue
    g=matches[0];vals={z.get('discountedPrice')for z in g.get('sizes',[])}
    price=next(iter(vals),None)
    if g.get('currencyIsoCode4217')!='CNY'or len(vals)!=1 or type(price)not in(int,float)or price<=0:
     missing[str(nm)]='exact_positive_CNY_price_unavailable';continue
    rows.append(dict(nm_id=nm,article=g['vendorCode'],currency='CNY',seller_price=price,size_ids=[z['sizeID']for z in g['sizes']]))
   v['prices']=dict(rows=rows,missing=missing,observed_at=stamp());save()
  if 'published_stock'not in v:
   v['published_stock']=published_stock(io,v['prices'],[r['nm_id']for r in v['prices']['rows']]);save()
  if 'stock'not in v:
   v['stock']=read_stock(list(dict.fromkeys(r['article']for r in v['prices']['rows'])));save()
  if 'fx'not in v:v['fx']=rate(Work(),date.fromisoformat(day));save()
  if 'economics'not in v:
   v['economics']=model_rows(dict(products=v['own'],prices=v['prices'],stock=v['stock'],fx=dict(rub_per_cny=v['fx']['rub_per_cny'])),io.get('china_agent:new_ad_economics_policy:v1'),io.get('china_agent:expected_profit_delivery_model:v1'))
   for nm,e in v['economics']['rows'].items():e.update(published_stock=v['published_stock']['amounts'].get(nm),published_stock_observed_at=v['published_stock']['observed_at'],fx_rub_per_cny=float(v['fx']['rub_per_cny']),fx_date=day)
   save()
  if 'campaigns'not in v:
   v['campaigns']=http(io,'/api/advert/v2/adverts?ids='+','.join(map(str,s['ids'])))['adverts'];save()
  if 'budgets'not in v:
   active=[c['id']for c in v['campaigns']if c['status']==9]
   v['budgets']=http(io,'/api/advert/v2/budget','POST',dict(advertIds=active));v['budgets_observed_at']=stamp();save()
  if 'config'not in v:v['config']=http(io,'/api/advert/v1/config');save()
  v.setdefault('minimums',{});v.setdefault('addition_quotes',{});v['quote_errors']={}
  for cp in v['campaigns']:
   if cp['status']!=9 or cp['bid_type']!='manual'or cp['settings']['payment_type']!='cpc':continue
   cid=cp['id'];zone='search'if cp['settings']['placements'].get('search')else'recommendation'
   wanted=[n['nm_id']for n in cp['nm_settings']if n['nm_id']not in excluded and v['economics']['rows'].get(str(n['nm_id']),{}).get('expected_margin_before_ads_cny',-1)>0 and v['economics']['rows'].get(str(n['nm_id']),{}).get('published_stock') is not None and v['economics']['rows'].get(str(n['nm_id']),{}).get('published_stock')>0]
   if wanted and str(cid)not in v['minimums']:
    try:v['minimums'][str(cid)]=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=cid,nm_ids=wanted,payment_type='cpc',placement_types=[zone]));save()
    except Exception as ex:v['quote_errors'][str(cid)]=str(ex);save()
  # Scan every non-member; removed products require a separate owner reinstatement review.
  members={n['nm_id']for cp in v['campaigns']if cp['status']in[9,11]for n in cp['nm_settings']}
  removed={x['nm']for x in history(s.get('executions',[]))if x['kind']=='excluded'}
  own={int(r['nm_id']):r for r in v['own']['rows']}
  v['addition_candidates']=[]
  for nm in ids:
   if nm in members or nm in removed:continue
   e=v['economics']['rows'].get(str(nm),{});o=own.get(nm,{})
   if e.get('expected_margin_before_ads_cny',-1)<=0 or e.get('stock_free',0)<=0 or (e.get('published_stock')is None or e['published_stock']<=0) or e.get('sample_size',0)<5 or e.get('buyout_fallback'):continue
   if o.get('is_payed',0)<3 or not o.get('open_card_count')or o.get('funnel_orders_count',0)/o['open_card_count']<.005:continue
   targets=[cp for cp in v['campaigns']if cp['status']==9 and cp['bid_type']=='manual'and cp['settings']['payment_type']=='cpc'and cp['settings']['placements'].get('recommendations')and{n['subject']['id']for n in cp['nm_settings']}=={o.get('subject_id')}and cp.get('restrictions',{}).get('can_change_nms')and len(cp['nm_settings'])<50]
   if not targets:continue
   cid=min(cp['id']for cp in targets);v['addition_candidates'].append(dict(nm_id=nm,campaign_id=cid))
   if str(nm)not in v['addition_quotes']:
    try:v['addition_quotes'][str(nm)]=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=cid,nm_ids=[nm],payment_type='cpc',placement_types=['recommendation']));save()
    except Exception as ex:
     if 'HTTP 400'in str(ex):v['addition_quotes'][str(nm)]=dict(unavailable=str(ex),observed_at=stamp());save()
     else:v['quote_errors']['add:'+str(nm)]=str(ex);save()
  # A transient quote failure is retried by the existing next preparation, never relabelled no candidates.
  if v['quote_errors']:raise ValueError('Exact growth quotes unavailable')
  v.update(status='complete',observed_at=stamp(),catalogue_count=len(v.get('catalogue',s['catalogue'])['rows']),screened_nm_ids=ids,excluded_nm_ids=sorted(excluded),wb_writes=0,telegram_calls=0,model_calls=0,grants_action_permission=False);save()
 except Exception as ex:
  v.update(status='collecting',last_error=type(ex).__name__+': '+str(ex),last_attempt_at=stamp());save()
  raise PendingAdvertisingDay('Full cabinet growth inputs incomplete; staged read-only collection will resume')from ex
 out=copy.deepcopy(s);out['catalogue']=v.get('catalogue',s['catalogue']);out['economics']=v['economics'];out['observed_at']=v['observed_at']
 current={c['id']:c for c in v['campaigns']};cash={r['advertId']:r for r in v['budgets']['adverts']}
 for batch in out.get('batches',{}).values():
  batch['campaigns']['adverts']=[current.get(cp['id'],cp)for cp in batch['campaigns']['adverts']]
  batch['budgets']['adverts']=[cash.get(row['advertId'],row)for row in batch['budgets'].get('adverts',[])if row is not None]
 out['budget_balance_observed_at_iso']=v.get('budgets_observed_at',v['observed_at'])
 out['morning_fresh_inputs']=dict(errors={},selected_nm_ids=ids,own_period=[str(first),str(end)],source_times={k:v[k]['observed_at']for k in['own','prices','stock']},wb_writes=0)
 out['full_growth_inputs']=v
 out['full_growth_review']=dict(status='complete',input_key=key,catalogue_count=v['catalogue_count'],current_price_count=len(v['prices']['rows']),missing_prices=v['prices']['missing'],missing_economics=v['economics']['missing'],missing_published_stock=v['published_stock']['missing_nm_ids'],observed_at=v['observed_at'])
 out['addition_scan']=dict(status='complete',period_from=str(first),period_to=str(end),observed_at=v['own']['observed_at'],candidate_ids=[r['nm_id']for r in v['addition_candidates']],catalogue_count=v['catalogue_count'])
 out['addition_bid_quotes']={}
 for r in v['addition_candidates']:
  q=v['addition_quotes'].get(str(r['nm_id']),{})
  vals=[b['value']for row in q.get('bids',[])if row['nm_id']==r['nm_id']for b in row['bids']if b['type']=='recommendation'and b['currency']=='CNY']
  if len(vals)==1:out['addition_bid_quotes'][str(r['nm_id'])]=dict(campaign_id=r['campaign_id'],target_minor=vals[0],bid_verified=True,observed_at=v['observed_at'])
 return out
def proposed_actions(s):
 """Every current placement is evaluated; no top8/top12 truncation and no forced count."""
 from china_advertising_v2 import history,event_time
 v=s['full_growth_inputs'];end=date.fromisoformat(s['period_to']);today=end+timedelta(days=1);changes=history(s['executions'])
 metrics={};campaign_spend={}
 for batch in s['batches'].values():
  for cp in batch['stats']:
   campaign_spend[cp['advertId']]=sum(d['sum']for d in cp['days']if str(end-timedelta(days=2))<=d['date'][:10]<=str(end))
   for d in cp['days']:
    for app in d.get('apps',[]):
     for n in app.get('nms',[]):
      m=metrics.setdefault((cp['advertId'],n['nmId']),{}).setdefault(d['date'][:10],dict(spend=0,amount=0,orders=0,clicks=0,views=0))
      for a,b in[('spend','sum'),('amount','sum_price'),('orders','orders'),('clicks','clicks'),('views','views')]:m[a]+=n.get(b,0)
 own={int(r['nm_id']):r for r in v['own']['rows']};price={r['nm_id']:r for r in v['prices']['rows']}
 balances={r['advertId']:r['total']for r in v['budgets']['adverts']};actions=[];unready=[];extra={}
 for cp in v['campaigns']:
  if cp['status']!=9 or cp['bid_type']!='manual'or cp['settings']['payment_type']!='cpc':continue
  cid=cp['id'];zone='search'if cp['settings']['placements'].get('search')else'recommendations';typ='search'if zone=='search'else'recommendation'
  for n in cp['nm_settings']:
   nm=n['nm_id'];e=v['economics']['rows'].get(str(nm),{});o=own.get(nm,{})
   if nm in v['excluded_nm_ids']or e.get('sample_size',0)<5 or e.get('buyout_fallback')or e.get('commission_policy_fallback')or e.get('stock_free',0)<=0 or (e.get('published_stock')is None or e['published_stock']<=0):continue
   if o.get('commentsvaluation',0)not in[0,None]and o['commentsvaluation']<4.5:continue
   relevant=[x for x in changes if x['nm']==nm and x['kind']in['bid','price','added','returned','relaunch','excluded']]
   ats=[event_time(x['at']).astimezone(ZoneInfo('Europe/Moscow')).date()for x in relevant]
   if cp.get('timestamps',{}).get('started'):ats.append(event_time(cp['timestamps']['started']).astimezone(ZoneInfo('Europe/Moscow')).date())
   latest=max(ats,default=end-timedelta(days=7))
   days=[str(d)for d in[end-timedelta(days=i)for i in(2,1,0)]if d>latest]
   ds=metrics.get((cid,nm),{})
   if not days or not all(d in ds for d in days):continue
   m={k:sum(ds[d][k]for d in days)for k in['spend','amount','orders','clicks','views']}
   if m['orders']<2 or m['clicks']<30 or ds[days[-1]]['orders']<1 or m['amount']<=0:continue
   if e['published_stock']<math.ceil(m['orders']/len(days)*3):continue
   old=n['bids_kopecks'][zone];step=v['config']['cpcStep'];target=math.ceil((old+max(1,old*.05))/step)*step
   vals=[b['value']for q in v['minimums'].get(str(cid),{}).get('bids',[])if q['nm_id']==nm for b in q['bids']if b['type']==typ and b['currency']=='CNY']
   if len(vals)!=1 or not old<target<=old*1.15 or target<vals[0]or target>v['config']['cpcMaxBid']:continue
   fx=e['fx_rub_per_cny'];delivery=max(e['logistics_cny'],(o.get('average_delivery_cost')or 0)/fx)
   reverse=(o.get('backwardlogisticsum')or 0)/e['sample_size']/fx
   margin=e['expected_margin_before_ads_cny']-(delivery-e['logistics_cny'])-reverse
   stress=margin-.2*e['buyout']*(e['seller_price_cny']*(1-(e['commission_pct']+e.get('tax_pct',5))/100)-e['own_cogs_rub']/fx)
   cpa=m['spend']/m['orders']*target/old;last_cpa=ds[days[-1]]['spend']/ds[days[-1]]['orders']*target/old
   if stress<=max(cpa,last_cpa)*1.25:continue
   ev=dict(e,cabinet='token_3',currency='CNY',article=price[nm]['article'],observed_at=v['observed_at'],prices_observed_at=e['price_observed_at'],buyout_observed_at=v['own']['observed_at'],price_cny=e['seller_price_cny'],minimum_minor=vals[0],expected_margin_before_ads_cny=margin,stress_margin_before_ads_cny=stress,shipping_reserve_cny=delivery,observed_reverse_cost_per_created_order_cny=reverse,period_from=days[0],period_to=days[-1],decision_days=days,metrics=m,modeled_cpa_same_cr=cpa,margin_after_target_same_cr=margin-cpa,small_sample=m['orders']<10 or e['sample_size']<20,preliminary=True,unknown_costs=True,source_key=ROOT+str(today)+':v1:inputs',manual_strategy_proposal=True)
   actions.append(dict(id=str(cid)+':'+str(nm),kind='ad_set_bid',direction='raise',campaign_id=cid,nm_id=nm,article=price[nm]['article'],placement=zone,old_minor=old,target_minor=target,growth_evidence=ev,manual_experiment=True))
 # Keep best-supported placement per SKU. No simultaneous increases in different campaigns.
 actions.sort(key=lambda a:(-a['growth_evidence']['metrics']['orders'],a['growth_evidence']['modeled_cpa_same_cr']))
 result=[];seen=set()
 for a in actions:
  nm=a['nm_id'];cid=a['campaign_id'];e=a['growth_evidence']
  if nm in seen:continue
  increase=e['metrics']['clicks']/len(e['decision_days'])*3*(a['target_minor']-a['old_minor'])/100
  if balances.get(cid,-1)<campaign_spend.get(cid,1e99)+extra.get(cid,0)+increase:
   unready.append(dict(nm_id=nm,campaign_id=cid,reason='Insufficient three-day reserve for proposed increase'));continue
  extra[cid]=extra.get(cid,0)+increase;seen.add(nm);result.append(a)
 return result,unready
def addition_actions(s,raises):
 """New products need an exact non-member quote; CPA remains unknown for a new test."""
 v=s['full_growth_inputs'];own={int(r['nm_id']):r for r in v['own']['rows']};prices={r['nm_id']:r for r in v['prices']['rows']};result=[]
 balances={r['advertId']:r['total']for r in v['budgets']['adverts']};reserve={};end=date.fromisoformat(s['period_to'])
 for batch in s['batches'].values():
  for cp in batch['stats']:reserve[cp['advertId']]=sum(d['sum']for d in cp['days']if str(end-timedelta(days=2))<=d['date'][:10]<=str(end))
 for a in raises:
  e=a['growth_evidence'];reserve[a['campaign_id']]+=e['metrics']['clicks']/len(e['decision_days'])*3*(a['target_minor']-a['old_minor'])/100
 for r in v.get('addition_candidates',[]):
  nm=r['nm_id'];cid=r['campaign_id'];e=v['economics']['rows'].get(str(nm),{});o=own.get(nm,{})
  quote=(s.get('addition_bid_quotes')or{}).get(str(nm),{})
  target=quote.get('target_minor');step=v['config']['cpcStep']
  if quote.get('bid_verified')is not True or type(target)is not int or target<=0 or target%step or target>v['config']['cpcMaxBid']:continue
  if e.get('commission_policy_fallback')or e.get('buyout_fallback')or e.get('sample_size',0)<5 or e.get('published_stock',0)<3:continue
  margin=e.get('expected_margin_before_ads_cny',-1)
  if margin<=0:continue
  # New traffic has no proven CPA. Reserve a disclosed diagnostic forecast, not a technical SKU cap.
  reserve_extra=90*target/100
  if balances.get(cid,-1)<reserve.get(cid,1e99)+reserve_extra:continue
  reserve[cid]+=reserve_extra
  evidence=dict(e,cabinet='token_3',currency='CNY',article=prices[nm]['article'],observed_at=v['observed_at'],price_cny=e['seller_price_cny'],minimum_minor=target,period_to=s['period_to'],period_from=v['own']['period_from'],subject_id=o['subject_id'],ad_cpa_unknown=True,preliminary=True,unknown_costs=True,manual_strategy_proposal=True,source_key=ROOT+str(date.fromisoformat(s['period_to'])+timedelta(days=1))+':v1:inputs',test_review_after_first_completed_day=True,ad_traffic_forecast_clicks_per_day=30,campaign_reserve_required_cny=reserve[cid],forecast_not_a_spend_cap=True)
  result.append(dict(id=str(cid)+':add:'+str(nm),kind='ad_add_sku',direction='add',campaign_id=cid,nm_id=nm,article=prices[nm]['article'],placement='recommendations',target_minor=target,subject_id=o['subject_id'],manual_experiment=True,exact_addition_quote=True,growth_evidence=evidence))
 return result
def validate_addition(io,item,before):
 """Execution preflight only; this function makes no marketplace writes."""
 import requests
 from china_advertising_v2 import http
 from china_morning_readiness import current_prices,published_stock
 from china_moysklad_read import read_stock
 from china_advertising_growth import fresh
 e=item.get('growth_evidence')or{};now=datetime.now(timezone.utc)
 if item.get('direction')!='add'or item.get('exact_addition_quote')is not True or not fresh(e.get('observed_at'),now,2)or e.get('period_to','9999')>=str(now.astimezone(ZoneInfo('Europe/Moscow')).date()):raise ValueError('Addition evidence stale or not exact')
 nm=item['nm_id'];cid=item['campaign_id']
 if before['id']!=cid or before['status']!=9 or before['currency']!='CNY'or before['bid_type']!='manual'or before['settings']['payment_type']!='cpc'or before['settings']['placements'].get(item['placement'])is not True or not before.get('restrictions',{}).get('can_change_nms')or len(before['nm_settings'])>=50:raise ValueError('Addition campaign changed')
 if {n['subject']['id']for n in before['nm_settings']}!={item['subject_id']}:raise ValueError('Addition category changed')
 prices=current_prices(io,[nm]);p=prices['rows'][0];stock=read_stock([item['article']]);pub=published_stock(io,prices,[nm])
 if p['article'].casefold()!=item['article'].casefold()or p['seller_price']!=e['price_cny']or not stock['coverage_complete']or stock['rows'][0]['stock']-stock['rows'][0]['reserve']<=0 or pub['amounts'].get(str(nm),0)<=0:raise ValueError('Addition price/stock unknown or changed')
 st=stock['rows'][0];delta=e['buyout']*(st['price']/100-e['own_cogs_rub'])/e['fx_rub_per_cny']
 if st['price']<=0 or e['expected_margin_before_ads_cny']-delta<=0:raise ValueError('Addition current economics no longer positive')
 cfg=http(io,'/api/advert/v1/config')
 if cfg['currency']!='CNY'or item['target_minor']%cfg['cpcStep']or item['target_minor']>cfg['cpcMaxBid']:raise ValueError('Addition bid step changed')
 q=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=cid,nm_ids=[nm],payment_type='cpc',placement_types=['recommendation']))
 vals=[b['value']for row in q.get('bids',[])if row['nm_id']==nm for b in row['bids']if b['currency']=='CNY'and b['type']=='recommendation']
 if len(vals)!=1 or vals[0]>item['target_minor']:raise ValueError('Exact addition minimum changed')
 balance=http(io,'/api/advert/v2/budget','POST',dict(advertIds=[cid]))['adverts']
 if len(balance)!=1 or balance[0]['currency']!='CNY'or balance[0]['total']<e['campaign_reserve_required_cny']:raise ValueError('Addition three-day reserve unavailable')

def enrich(io,s,bundle):
 from china_advertising_growth import merge
 actions,unready=proposed_actions(s)
 result=merge(bundle,actions)
 additions=addition_actions(s,actions)
 for a in additions:
  cp=next(c for c in result['campaigns']if c['id']==a['campaign_id'])
  row=dict(nm=a['nm_id'],article=a['article'],action=a,decision='Тест: добавить, ставка '+str(a['target_minor']/100)+' CNY.',reason='Рекламная стоимость заказа неизвестна; предварительная собственная экономика положительна.',economics=a['growth_evidence'],period=None,daily=[],period_drr=None,growth=True)
  cp.setdefault('focus',[]).append(row);cp.setdefault('attention',[]).append(copy.deepcopy(row))
 result['growth_review']=dict(status='complete',observed_at=s['full_growth_inputs']['observed_at'],period_to=s['period_to'],scope=s['full_growth_review'])
 result['full_cabinet_growth_review']=dict(s['full_growth_review'],raise_candidates=len(actions),addition_candidates=len(additions),unready=unready,automatic_actions=False)
 return result
