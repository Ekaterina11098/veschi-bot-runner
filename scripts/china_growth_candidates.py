"""Evidence-first additions and bid tests. No marketplace writes in collection/scoring."""
import base64,copy,hashlib,json,math,re
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow')
def stamp():return datetime.now(timezone.utc).isoformat()
def within_full_days(at,today,days=3):
 if not at:return False
 changed=datetime.fromisoformat(at.replace('Z','+00:00')).astimezone(MSK).date()
 return (today-changed).days<=days
def series(fullstats):
 result={}
 for c in fullstats:
  if c.get('currency')!='CNY':raise ValueError('Валюта статистики РК не CNY')
  for d in c.get('days',[]):
   for app in d.get('apps',[]):
    for n in app.get('nms',[]):
     key=str(c['advertId'])+':'+str(n['nmId']);v=result.setdefault(key,{}).setdefault(d['date'][:10],dict(spend=0,amount=0,orders=0,clicks=0,views=0))
     for field,name in [('spend','sum'),('amount','sum_price'),('orders','orders'),('clicks','clicks'),('views','views')]:v[field]+=n.get(name) or 0
 return result
def economics(row,price,stock,policy,drr=.05):
 nm=str(row['nm_id']);log=policy.get('logistics_by_nm',{}).get(nm);f=row.get('finished_orders');paid=row.get('is_payed')
 if not f or paid is None or stock.get('price') is None or not log:return None
 ratio=(row.get('price_after_spp') or 0)/(row.get('price_after_discount') or 1)
 if ratio<=0:return None
 fee=row.get('total_commission_without_spp_in_sales');fee=fee/100 if fee is not None and row.get('sales_sum_without_spp') else .20
 if not 0<=fee<1:return None
 fx=policy.get('fx_rub_cny');tax=policy.get('tax_rate',.05)
 if fx!=12:return None
 return paid/f*(price*fx*(1-fee-tax*ratio)-stock['price']/100)-log['delivery_cny']*fx-policy.get('handling_rub',10)-drr*price*fx
def excluded_history(w,current):
 prior=set()
 # Membership snapshots, not per-product attributed rows: related orders are not membership.
 from china_experience import read_rows
 for record in read_rows(w,'china_agent:advertising_source:',limit=35):
  for o in record['payload'].get('observations',[]):
   if o.get('tool')!='wbbidder_campaign':continue
   c=(o.get('data') or {}).get('campaign') or {}
   if c.get('status_id')!=9:continue
   for s in c.get('settings',[]):prior.update(n['nm_id'] for n in s.get('wb',{}).get('nm_bids',[]))
 active={n['nm_id'] for c in current.values() for n in c.get('nm_settings',[])}
 return prior-active
def review(io,nm,mp):
 import requests,time
 key='china_agent:growth_review:v1:'+str(nm);old=io.get(key)
 if old and 'negative' in old and datetime.now(timezone.utc)-datetime.fromisoformat(old['observed_at'])<timedelta(hours=24):return old
 seen={};complete=True
 for path,params in [('/api/v1/feedbacks',{'isAnswered':'false'}),('/api/v1/feedbacks',{'isAnswered':'true'}),('/api/v1/feedbacks/archive',{})]:
  r=requests.get('https://feedbacks-api.wildberries.ru'+path,headers={'Authorization':io.token},params=dict(nmId=nm,take=5000,skip=0,order='dateDesc',**params),timeout=40);time.sleep(.5)
  if not r.ok:complete=False;continue
  j=r.json();items=j.get('data',{}).get('feedbacks',[])
  if j.get('error') or len(items)>=5000:complete=False
  for f in items:
   if f.get('productDetails',{}).get('nmId')!=nm:complete=False;continue
   seen[f['id']]={k:f.get(k) for k in ['productValuation','createdDate','text','cons','pros']}
 negative=[dict(rating=f['productValuation'],date=f.get('createdDate'),text=f.get('text'),cons=f.get('cons')) for f in seen.values() if f.get('productValuation') is not None and f['productValuation']<=3]
 negative.sort(key=lambda f:f.get('date') or '',reverse=True)
 value=dict(observed_at=stamp(),rating=mp.get('commentsvaluation') if mp.get('commentsvaluation') is not None else mp.get('rating'),count=len(seen) if complete else None,complete=complete,count_scope='WB seller API exact SKU; not merged-card total',negative=negative[:20])
 io.put(key,value) if old else io.create(key,value)
 return value
def score(s,current,daily,mins,config,protected,recent,targets,today,days=3):
 from china_experience import assess_candidate
 active={n['nm_id'] for c in current.values() for n in c['nm_settings']};prices={r['nmID']:r for r in s['prices']};stocks={r['article'].casefold():r for r in s['stock'] if r.get('article')};result=[];blocked=[]
 dates=[str(today-timedelta(days=n)) for n in range(days,0,-1)];counts={}
 for o in s['orders']:counts[o['nmId']]=counts.get(o['nmId'],0)+1
 for r in s['products']:
  nm=int(r['nm_id']);article=r['sa_name'];pr=prices.get(nm);st=stocks.get(article.casefold())
  if not pr or not st or st.get('stock') is None or st.get('reserve') is None:continue
  free=st['stock']-st['reserve'];f=r.get('finished_orders') or 0;paid=r.get('is_payed');price=pr['sizes'][0]['discountedPrice']
  exp=economics(r,price,st,s['policy'])
  if free<5 or not f or paid is None or exp is None or exp<=0:continue
  base=dict(nm_id=nm,article=article,stock=free,paid=paid,finished=f,seller_cny=price,expected_rub_per_order_at5=round(exp,2),economics_method='preliminary; current COGS/historical logistics/fee or assumption/tax/fx; common deductions may be incomplete',risk='Собственная выборка мала' if f<5 else 'Прогноз, не закрытая прибыль')
  memory=assess_candidate((s.get('experience') or {}).get('experiences',[]),nm,dict(seller_price=price,stock_available=free,rating=r.get('commentsvaluation')))
  if memory['needs_review']:blocked.append(dict(nm_id=nm,article=article,reason='Негативный опыт: причина и изменение условий ещё не подтверждены',memory=memory));continue
  base['memory']=memory
  present=[(cid,c,n) for cid,c in current.items() for n in c['nm_settings'] if n['nm_id']==nm]
  if not present:
   if nm in protected:blocked.append(dict(nm_id=nm,article=article,reason='Ранее исключён: нужна проверка причины и изменившихся условий; не вечный запрет'));continue
   if nm in recent:continue
   if f<3 or not r.get('open_card_count') or not r.get('funnel_orders_count'):continue
   cat=r.get('subject_id');purpose='orders' if counts.get(nm,0)>0 else 'demand';target=targets.get((purpose,cat))
   if not target:continue
   cid,reference=target;required=reference/(.05*price*100)*100;cr=r['funnel_orders_count']/r['open_card_count']*100
   # Only a conservative screening proxy; never advertise it as paid conversion.
   if cr<required:continue
   result.append(dict(base,kind='ad_add_sku',campaign_id=cid,target_minor=reference,old_minor=None,subject_id=cat,purpose=purpose,confidence='diagnostic',general_click_order_pct=round(cr,2),required_paid_conversion_pct=round(required,2),drr=None,orders=None,reason='Есть спрос/остаток и предварительный запас экономики; новая реклама требует теста',basis='same-category live minimum; exact new-SKU minimum checked after addition',estimated_total_profit_rub=None))
   continue
  for cid,c,n in present:
   if nm in recent or cid in recent:continue
   if c.get('currency')!='CNY' or c.get('bid_type')!='manual' or c.get('settings',{}).get('payment_type')!='cpc' or c['settings'].get('placements')!={'search':False,'recommendations':True}:continue
   key=str(cid)+':'+str(nm);values=daily.get(key,{})
   if not all(day in values for day in dates):continue
   ds=[values[d] for d in dates];spend=sum(d['spend'] for d in ds);amount=sum(d['amount'] for d in ds);orders=sum(d['orders'] for d in ds);clicks=sum(d['clicks'] for d in ds)
   drr=spend/amount*100 if amount else None
   if f<5 or orders<5 or clicks<20 or spend<3 or drr is None or drr>=4:continue
   cp=[d['spend']/d['orders'] if d['orders'] else None for d in ds]
   if all(v is not None for v in cp) and all(a<b for a,b in zip(cp,cp[1:])):continue
   partial=values.get(str(today),{});tdrr=partial['spend']/partial['amount']*100 if partial.get('amount') else None
   if tdrr is not None and tdrr>5 or partial.get('spend',0)>=.05*price and not partial.get('orders'):continue
   old=n.get('bids_kopecks',{}).get('recommendations');minimum=mins.get((cid,nm));step=config.get('cpcStep')
   if type(old) is not int or type(minimum) is not int or type(step) is not int or step<=0:continue
   worst=max([d['spend']/d['amount']*100 for d in ds if d['amount']]+[drr]);ceiling=math.floor(old*4.5/worst/step)*step
   target=min(math.ceil(old*1.05/step)*step,ceiling,config['cpcMaxBid'])
   if target<=old or target<minimum:continue
   result.append(dict(base,kind='ad_raise_bid',campaign_id=cid,old_minor=old,target_minor=target,minimum_minor=minimum,subject_id=r.get('subject_id'),confidence='limited_test',drr=round(drr,2),orders=orders,daily=[dict(date=d,**values[d],drr=values[d]['spend']/values[d]['amount']*100 if values[d]['amount'] else None) for d in dates],today_drr=round(tdrr,2) if tdrr is not None else None,modeled_drr=round(drr*target/old,2),reason='Есть запас до ДРР5%; без последовательного роста стоимости заказа',estimated_total_profit_rub=round(orders*exp,2)))
 result.sort(key=lambda r:((r.get('orders') or counts.get(r['nm_id'],0)),r['stock']),reverse=True)
 return result[:12],blocked
def collect(w,kind='both',days=3):
 if kind not in ['both','add','raise'] or not 2<=days<=14:raise ValueError('Для подбора нужны2–14полныхдней')
 from china_price_apply import IO
 from china_new_ad_reports import source
 from china_loss_ads import current,http
 from china_ad_rule import minimums
 from china_experience import search,decision_context
 io=IO();today=w.now.astimezone(MSK).date();experience=decision_context(w);memory_ids=[e['event_id'] for e in experience['experiences']];fingerprint=hashlib.sha256(json.dumps([{k:e.get(k) for k in ['event_id','last_observed_at','business_outcome','advertising_outcome','context']} for e in experience['experiences']],sort_keys=True,default=str).encode()).hexdigest();cached=w.get('china_agent:growth_scan:'+str(today)+':'+str(days)+':v1')
 if cached and cached.get('experience_fingerprint')==fingerprint and datetime.now(timezone.utc)-datetime.fromisoformat(cached['observed_at'])<timedelta(minutes=30):return dict(cached,rows=[r for r in cached['rows'] if kind=='both' or (r['kind']=='ad_add_sku')==(kind=='add')],cached=True)
 s=source(io);cs=current(io);config=http(io,'/api/advert/v1/config')
 start=today-timedelta(days=days);stats=http(io,'/adv/v3/fullstats?ids='+','.join(map(str,cs))+'&beginDate='+str(start)+'&endDate='+str(today));daily=series(stats)
 protected=set(s.get('protected',[]))|excluded_history(w,cs);recent=set(experience['recent_changed_nm_ids'])
 for e in experience['experiences']:
  if e.get('record_type')=='verified_action' and within_full_days(e.get('started_at'),today):recent.update(e.get('action',{}).get('nm_ids',[]))
 targets={};tracking=io.get('china_agent:new_ad_tests:tracking:v1') or {}
 for plan in tracking.get('plans',{}).values():
  for item,cid in zip(plan.get('items',[]),plan.get('campaign_ids',[])):
   if cid not in cs:continue
   cats={n['subject']['id'] for n in cs[cid]['nm_settings']}
   if len(cats)!=1:continue
   cat=next(iter(cats));purpose='demand' if 'demand' in item.get('group','') else 'orders'
   target_nm=cs[cid]['nm_settings'][0]['nm_id'];ref=minimums(io,cid,{target_nm})[target_nm];targets[(purpose,cat)]=(cid,ref)
   if within_full_days(plan.get('started_at'),today):recent.update(n['nm_id'] for n in cs[cid]['nm_settings'])
 mins={}
 if True: # Cache always contains both kinds; a prior add-only request must not hide raises.
  for cid,c in cs.items():
   if c.get('settings',{}).get('payment_type')!='cpc':continue
   ids={n['nm_id'] for n in c['nm_settings'] if n['nm_id'] not in recent}
   if ids:mins.update({(cid,n):v for n,v in minimums(io,cid,ids).items()})
 rows,blocked=score(s,cs,daily,mins,config,protected,recent,targets,today,days)
 selected=[]
 for row in rows:
  mp=next(r for r in s['products'] if int(r['nm_id'])==row['nm_id']);rv=review(io,row['nm_id'],mp)
  if not rv['complete']:blocked.append(dict(nm_id=row['nm_id'],article=row['article'],reason='Не подтверждено число отзывов'));continue
  row['reviews']=rv;row['experience']=search(w,[row['nm_id']],limit=4)['experiences'];row['before_campaign']=cs[row['campaign_id']];selected.append(row)
 result=dict(status='complete',observed_at=stamp(),period_from=str(start),period_to=str(today-timedelta(days=1)),catalogue_count=len(s['products']),campaign_count=len(cs),rows=selected,blocked=blocked[:50],experience=experience,experience_ids=memory_ids,memory_used=True,requires_confirmation=True,limitations=['Экономика предварительная; неизвестные общие удержания не0','Повышение ставки не гарантирует показов/заказов/ДРР5','Рекламная атрибуция отдельно от WBзаказов','Прежний результат может измениться: проверить текущие условия, не объявлять изменение алгоритмов WB фактом без доказательств'],wb_writes=0)
 result['experience_fingerprint']=fingerprint
 w.save('china_agent:growth_scan:'+str(today)+':'+str(days)+':v1',result)
 return dict(result,rows=[r for r in selected if kind=='both' or (r['kind']=='ad_add_sku')==(kind=='add')])
