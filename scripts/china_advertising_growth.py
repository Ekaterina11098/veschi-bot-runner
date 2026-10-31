"""Bounded completed-day growth proposals; read-only, no sends or marketplace writes."""
import copy,json,math
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow')
ROOT='china_agent:daily_growth:'
def stamp():return datetime.now(timezone.utc).isoformat()
def fresh(at,now,hours=24):
 try:return 0<=(now-datetime.fromisoformat(at.replace('Z','+00:00'))).total_seconds()<=hours*3600
 except (TypeError,ValueError,AttributeError):return False
def shortlist(s):
 from china_advertising_v2 import history,event_time
 changes=history(s.get('executions',[]));today=date.fromisoformat(s['period_to'])+timedelta(days=1)
 cs=[c for b in s['batches'].values()for c in b['campaigns']['adverts']]
 stats={c['advertId']:c for b in s['batches'].values()for c in b['stats']};out=[]
 for c in cs:
  if c.get('status')!=9 or c.get('currency')!='CNY' or c.get('bid_type')!='manual' or c['settings']['payment_type']!='cpc':continue
  zone='search'if c['settings']['placements'].get('search')else'recommendations'
  raw=stats.get(c['id'],{});daily={}
  for d in raw.get('days',[]):
   day=d['date'][:10]
   if day>=str(today):continue
   for app in d.get('apps',[]):
    for n in app.get('nms',[]):
     r=daily.setdefault(n['nmId'],{}).setdefault(day,dict(spend=0,amount=0,orders=0,clicks=0,views=0))
     for field,key in [('spend','sum'),('amount','sum_price'),('orders','orders'),('clicks','clicks'),('views','views')]:r[field]+=n.get(key,0)
  for n in c['nm_settings']:
   nm=n['nm_id'];old=n['bids_kopecks'].get(zone)
   if type(old)is not int or old<=0:continue
   events=[x for x in changes if x['nm']==nm and x['kind']in['price','bid','added','returned','relaunch']]
   dates=[event_time(x['at']).astimezone(MSK).date()for x in events]
   start=c.get('timestamps',{}).get('started')
   if start:dates.append(event_time(start).astimezone(MSK).date())
   latest=max(dates)if dates else today-timedelta(days=7)
   # Existing first-full-day tests must not be compounded, even in another campaign.
   wanted=[str(today-timedelta(days=i))for i in [3,2,1]if today-timedelta(days=i)>latest]
   ds=daily.get(nm,{})
   if len(wanted)<2 or not all(d in ds for d in wanted):continue # missing row is unknown
   totals={k:sum(ds[d][k]for d in wanted)for k in ['spend','amount','orders','clicks','views']}
   if totals['orders']<5 or totals['clicks']<80 or totals['amount']<=0:continue
   drr=100*totals['spend']/totals['amount'];last=ds[wanted[-1]]
   if drr>4 or last['orders']<1 or last['amount']<=0 or last['spend']/last['amount']>.05:continue
   worst=max(100*ds[d]['spend']/ds[d]['amount']if ds[d]['amount']>0 else 100 for d in wanted)
   if worst>5:continue
   out.append(dict(campaign_id=c['id'],nm_id=nm,placement=zone,old_minor=old,dates=wanted,metrics=totals,drr=drr,worst_drr=worst,last_change_day=str(latest),history=[dict(x)for x in events[-8:]]))
 out.sort(key=lambda r:(-r['metrics']['orders'],r['drr']))
 # One new test per product avoids simultaneous changes in different placements.
 unique=[];seen=set()
 for r in out:
  if r['nm_id']not in seen:unique.append(r);seen.add(r['nm_id'])
 return unique
def assess(r,e,cfg,now):
 required=['observed_at','stock_observed_at','prices_observed_at','buyout_observed_at']
 if any(not fresh(e.get(k),now)for k in required):return None
 if e.get('cabinet')!='token_3' or e.get('currency')!='CNY':return None
 if any(not isinstance(e.get(k),(int,float))or e[k]<=0 for k in ['stock_free','published_stock']):return None
 if not e.get('rating')or e['rating']<4.5 or e.get('finished',0)<10 or e.get('paid',0)<3:return None
 if e.get('expected_margin_before_ads_cny',-1)<=0 or e.get('stress_margin_before_ads_cny',-1)<=0:return None
 if e.get('negative_experience_requires_review'):return None
 old=r['old_minor'];step=cfg.get('cpcStep');minimum=e.get('minimum_minor')
 if cfg.get('currency')!='CNY' or type(step)is not int or step<=0 or type(minimum)is not int:return None
 target=min(math.ceil(old*1.1/step)*step,math.floor(old*4.5/r['worst_drr']/step)*step,cfg.get('cpcMaxBid',0))
 if not old<target<=old*1.15 or target<minimum:return None
 cpa=r['metrics']['spend']/r['metrics']['orders']*target/old
 if cpa>=e['stress_margin_before_ads_cny']:return None
 ev=copy.deepcopy(e);ev.update(period_from=r['dates'][0],period_to=r['dates'][-1],decision_days=r['dates'],metrics=r['metrics'],experience=r['history'],modeled_drr_same_cr=r['drr']*target/old,modeled_cpa_same_cr=cpa,margin_after_target_same_cr=e['expected_margin_before_ads_cny']-cpa,preliminary=True,unknown_costs=True)
 return dict(id=str(r['campaign_id'])+':'+str(r['nm_id']),kind='ad_set_bid',direction='raise',campaign_id=r['campaign_id'],nm_id=r['nm_id'],article=e['article'],placement=r['placement'],old_minor=old,target_minor=target,growth_evidence=ev)
def collect_evidence(io,s,rough):
 import requests,xml.etree.ElementTree as ET
 from china_moysklad_read import read_stock
 from analytics.mpstats_probe import discover
 from analytics.mpstats_gaps import execute_reads
 import os
 end=date.fromisoformat(s['period_to']);start=end-timedelta(days=29);found=[]
 tasks=[dict(cabinet='token_3',tool='lk_wb_products',key='daily-growth-completed-'+str(end),priority=80,arguments=dict(date_from=str(start),date_to=str(end),start_row=0,end_row=1000))]
 def persist(cabinet,obs):
  if cabinet=='token_3'and obs.get('scope_verified')is True and obs.get('status')=='received':found.append(obs)
 def extra(call,checks,known):return execute_reads(call,checks,known,tasks,{},persist,max_requests=1)
 discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=extra)
 if len(found)!=1:raise ValueError('No completed own China history')
 body=found[0].get('data',{}).get('data',{});rows=body.get('data',[])
 if body.get('need_update')!=0 or body.get('total')!=len(rows):raise ValueError('Own history incomplete')
 own={int(r['nm_id']):r for r in rows};observed=stamp()
 pr=requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',headers={'Authorization':io.token},params={'limit':1000,'offset':0},timeout=50);pr.raise_for_status();goods=pr.json()['data']['listGoods']
 if len(goods)>=1000:raise ValueError('Price scope incomplete')
 prices={g['nmID']:g for g in goods};price_at=stamp();wanted=[]
 for r in rough[:8]:
  p=own.get(r['nm_id'],{});g=prices.get(r['nm_id'],{})
  if p.get('sa_name')!=g.get('vendorCode')or g.get('currencyIsoCode4217')!='CNY':continue
  if p.get('commentsvaluation',0)<4.5 or p.get('finished_orders',0)<10:continue
  wanted.append(dict(r,article=g['vendorCode']))
 if not wanted:return {},dict(total_shortlisted=len(rough),checked=0)
 stock=read_stock(list(dict.fromkeys(r['article']for r in wanted)))
 sm={r['article']:r for r in stock['rows']};ids={r['nm_id']for r in wanted};sizes={z['sizeID']:g['nmID']for g in goods if g['nmID']in ids for z in g['sizes']}
 rr=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',headers={'Authorization':io.token},json={'chrtIds':list(sizes)},timeout=45);rr.raise_for_status();pub={}
 for v in rr.json()['stocks']:
  if v['chrtId']not in sizes:raise ValueError('Unexpected stock identity')
  nm=sizes[v['chrtId']];pub[nm]=pub.get(nm,0)+v['amount']
 fxr=requests.get('https://www.cbr.ru/scripts/XML_daily.asp',params={'date_req':(end+timedelta(days=1)).strftime('%d/%m/%Y')},timeout=40);fxr.raise_for_status();tree=ET.fromstring(fxr.content);v=next(v for v in tree.findall('Valute')if v.findtext('CharCode')=='CNY');fx=float(v.findtext('Value').replace(',','.'))/int(v.findtext('Nominal'))
 shipping=(io.get('china_agent:expected_profit_delivery_model:v1')or{}).get('rows',{});evidence={}
 from china_experience import read_rows
 prior=[r['payload']for r in read_rows(io,'china_agent:experience:v1:',limit=5000)]
 for r in wanted:
  nm=r['nm_id'];cid=r['campaign_id'];p=own[nm];g=prices[nm];st=sm.get(r['article'],{});f=p.get('finished_orders');paid=p.get('is_payed');log=shipping.get(r['article'],{}).get('delivery_cny')
  if not f or paid is None or st.get('price')is None or log is None:continue
  vals={z['discountedPrice']for z in g['sizes']}
  if len(vals)!=1:continue
  price=next(iter(vals));q=paid/f;fee=p.get('total_commission_without_spp_in_sales')
  if fee is None or not 0<=fee<100:continue
  cogs=st['price']/100/fx;delivery=max(log,(p.get('average_delivery_cost')or 0)/fx);reverse=(p.get('backwardlogisticsum')or 0)/f/fx
  margin=q*(price*(1-fee/100-.05)-cogs)-delivery-10/fx-reverse;stress=margin-max(0,35-delivery)
  from china_advertising_v2 import http
  typ='search'if r['placement']=='search'else'recommendation';j=http(io,'/api/advert/v1/bids/min','POST',dict(advert_id=cid,nm_ids=[nm],payment_type='cpc',placement_types=[typ]));vs=[v['value']for x in j.get('bids',[])if x['nm_id']==nm for v in x['bids']if v['currency']=='CNY'and v['type']==typ]
  if len(vs)!=1:continue
  relevant=[v for v in prior if nm in v.get('action',{}).get('nm_ids',[])]
  negative=any(v.get(k)=='negative'for v in relevant for k in ['business_outcome','advertising_outcome','expected_outcome'])
  evidence[str(cid)+':'+str(nm)]=dict(cabinet='token_3',currency='CNY',article=r['article'],observed_at=stamp(),stock_observed_at=stock['observed_at'],prices_observed_at=price_at,buyout_observed_at=observed,buyout_period=[str(start),str(end)],stock_free=st['stock']-st['reserve'],published_stock=pub.get(nm),rating=p.get('commentsvaluation'),finished=f,paid=paid,price_cny=price,cogs_cny=cogs,minimum_minor=vs[0],expected_margin_before_ads_cny=margin,stress_margin_before_ads_cny=stress,shipping_reserve_cny=delivery,shipping_model_date='2026-10-03',fx_rub_per_cny=fx,source='own_completed_history_current_WB_targeted_MSK',experience_ids=[v['event_id']for v in relevant],negative_experience_requires_review=negative)
 return evidence,dict(total_shortlisted=len(rough),checked=len(wanted),bounded_limit=8,older_or_missing_evidence_is_not_zero=True)
def enrich(io,s,bundle):
 # Keep collection failures private; a missing raise never fills report cells with explanations.
 if not all(k in s for k in ['period_to','batches','config']):return bundle
 day=str(date.fromisoformat(s['period_to'])+timedelta(days=1));key=ROOT+day+':v1';prior=io.get(key)
 if prior:return merge(bundle,prior.get('actions',[]))
 rough=shortlist(s);record=dict(status='complete',observed_at=stamp(),period_to=s['period_to'],actions=[],wb_writes=0,telegram_calls=0)
 try:
  if rough:
   evidence,scope=collect_evidence(io,s,rough);record.update(scope=scope,evidence=evidence)
   for r in rough[:8]:
    action=assess(r,evidence.get(str(r['campaign_id'])+':'+str(r['nm_id']),{}),s['config'],datetime.now(timezone.utc))
    if action:record['actions'].append(action)
 except Exception as ex:record.update(status='blocked',reason=type(ex).__name__+(': '+str(ex)if isinstance(ex,ValueError)else''))
 if not io.create(key,record):record=io.get(key)
 return merge(bundle,record.get('actions',[]))
def merge(bundle,actions):
 bundle=copy.deepcopy(bundle)
 for a in actions:
  campaign=next((c for c in bundle['campaigns']if c['id']==a['campaign_id']),None)
  if not campaign:continue
  # A reduction or exclusion from the same report takes precedence.
  if any((r.get('action')or{}).get('nm_id')==a['nm_id']for r in campaign.get('attention',[])):continue
  e=a['growth_evidence'];m=e['metrics']
  row=dict(nm=a['nm_id'],article=a['article'],action=a,decision=f"Повысить {a['old_minor']/100:g} → {a['target_minor']/100:g} CNY.",reason='',period=m,period_drr=m['spend']/m['amount']*100,done='Новый ограниченный тест',daily=[],growth=True)
  campaign.setdefault('attention',[]).append(row)
  # Recompute funding separately at the post-action composition; no auto deposit.
  campaign['growth_reserve_extra_cny']=campaign.get('growth_reserve_extra_cny',0)+m['clicks']/len(e['decision_days'])*3*(a['target_minor']-a['old_minor'])/100
  funding=campaign.get('budget_action')
  if funding and funding.get('kind')=='topup_campaign':
   base=campaign.setdefault('growth_base_forecast',campaign.get('forecast')or 0)
   need=base+campaign['growth_reserve_extra_cny'];gap=need-campaign['balance']
   amount=max(campaign.get('minimum_topup_cny',100),math.ceil(gap/50)*50)
   funding.update(amount_cny=amount,target_balance=campaign['balance']+amount)
   campaign.update(forecast=need,budget_recommendation=f'Пополнить на {amount:g} CNY.')
 return bundle
def validate_raise(io,item,before):
 import requests
 e=item.get('growth_evidence')or{};now=datetime.now(timezone.utc)
 if item.get('direction')!='raise' or not fresh(e.get('observed_at'),now,2) or e.get('period_to','9999')>=str(now.astimezone(MSK).date()):raise ValueError('Raise evidence stale or incomplete-day')
 old=item['old_minor'];target=item['target_minor']
 if not old<target<=old*1.15 or e.get('stress_margin_before_ads_cny',-1)<=e.get('modeled_cpa_same_cr',1e9):raise ValueError('Raise outside reviewed economics')
 cfg=requests.get('https://advert-api.wildberries.ru/api/advert/v1/config',headers={'Authorization':io.token},timeout=40);cfg.raise_for_status();cfg=cfg.json()
 if cfg.get('currency')!='CNY'or not cfg.get('cpcStep')or target%cfg['cpcStep']or target>cfg.get('cpcMaxBid',0):raise ValueError('Raise step or maximum changed')
 # A second placement must not compound an already verified raise on the same MSK day.
 for cid,key in (io.get('china_agent:verified_campaign_state:v1')or{}).items():
  receipt=io.get(key)or{};at=receipt.get('submitted_at')or receipt.get('verified_at')
  if receipt.get('status')!='verified'or not at:continue
  if datetime.fromisoformat(at.replace('Z','+00:00')).astimezone(MSK).date()!=now.astimezone(MSK).date():continue
  b=next((n for n in receipt.get('before',{}).get('nm_settings',[])if n['nm_id']==item['nm_id']),None);a=next((n for n in receipt.get('after',{}).get('nm_settings',[])if n['nm_id']==item['nm_id']),None)
  if b and a and any(a['bids_kopecks'].get(z,0)>b['bids_kopecks'].get(z,0)for z in ['search','recommendations']):raise ValueError('Product already raised today; no second raise')
 # A fresh marketplace price and published-stock preflight prevents execution from a stale PNG.
 rr=requests.get('https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter',headers={'Authorization':io.token},params={'limit':1000,'offset':0},timeout=45);rr.raise_for_status();goods=rr.json()['data']['listGoods']
 if len(goods)>=1000:raise ValueError('Price scope incomplete')
 g=next(g for g in goods if g['nmID']==item['nm_id'])
 if g['vendorCode']!=item['article']or g['currencyIsoCode4217']!='CNY' or {z['discountedPrice']for z in g['sizes']}!={e['price_cny']}:raise ValueError('Raise price changed')
 sizes=[z['sizeID']for z in g['sizes']];rr=requests.post('https://marketplace-api.wildberries.ru/api/v3/stocks/2126188',headers={'Authorization':io.token},json={'chrtIds':sizes},timeout=40);rr.raise_for_status();stock=rr.json()['stocks']
 if {z['chrtId']for z in stock}!=set(sizes)or sum(z['amount']for z in stock)<=0:raise ValueError('Raise stock unavailable')
