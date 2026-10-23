"""Complete focused read plan for yesterday/today order-decline questions."""
from datetime import timedelta
from zoneinfo import ZoneInfo
MSK=ZoneInfo('Europe/Moscow')

def ad_rows(rows,ids):
 out={}
 for row in rows:
  if row.get('level')!='SKU_app' or row.get('nm_id') not in ids:continue
  key=(row['nm_id'],str(row['date'])[:10]);r=out.setdefault(key,dict(spend=0,amount=0,orders=0,clicks=0,views=0))
  for k,field in [('spend','sum'),('amount','sum_price'),('orders','orders'),('clicks','clicks'),('views','views')]:r[k]=None if r[k] is None or row.get(field) is None else r[k]+row[field]
 for r in out.values():
  r['drr_pct']=100*r['spend']/r['amount'] if r['amount'] and r['spend'] is not None else None
  r['ctr_pct']=100*r['clicks']/r['views'] if r['views'] and r['clicks'] is not None else None
  r['cpc_cny']=r['spend']/r['clicks'] if r['clicks'] and r['spend'] is not None else None
  r['click_order_pct']=100*r['orders']/r['clicks'] if r['clicks'] and r['orders'] is not None else None
  r['scope']='advertising_only'
 return out

def selected(orders,maximum=10):
 rows={}
 for key in ['top_yesterday_declines','top_today_declines']:
  for r in orders.get(key,[])[:6]:rows[r['nm_id']]=r
 return sorted(rows.values(),key=lambda r:min(r.get('delta_yesterday') or 0,r.get('delta_today_matched_clock') or 0))[:maximum]

def collect(analyst):
 from china_analytic_dialog import reading
 from china_experience import decision_context
 from china_change_observation import general_traffic
 from china_price_apply import IO
 from china_loss_ads import http
 from china_ad_rule import minimums
 w=analyst.w;today=w.now.astimezone(MSK).date();dates=[str(today-timedelta(days=i)) for i in [2,1,0]];sources=[];gaps=[]
 def live(topic,ids,first,last):
  try:
   value=analyst.live(topic,ids,first,last);sources.append({k:value.get(k) for k in ['source','source_key','observed_at','period_from','period_to','cached']});return value
  except Exception as ex:
   gaps.append(dict(topic=topic,date_from=first,date_to=last,error=type(ex).__name__,note=str(ex)[:200] if isinstance(ex,(ValueError,RuntimeError)) else 'Транспорт источника'));return {}
 orders=live('orders',[],dates[0],dates[2]);focus=selected(orders);ids=[r['nm_id'] for r in focus]
 if not ids:return dict(status='complete' if orders else 'partial',orders=orders,rows=[],gaps=gaps,sources=sources,wb_writes=0)
 daily={day:{int(r['nm_id']):r for r in live('products',ids,day,day).get('rows',[])} for day in dates}
 stock={r['article'].casefold():r for r in live('stock',ids,dates[0],dates[2]).get('rows',[])}
 prices={r['nm_id']:r for r in live('prices',ids,dates[0],dates[2]).get('rows',[])}
 # WB is primary for identical metrics; MPStats stays as separately labelled evidence.
 from china_wb_evidence import Reports,settlement
 wb_funnel={};wb_finance={}
 with reading():
  reports=Reports(w)
  try:
   f=reports.funnel(dates[1],dates[1])
   if not f.get('complete'):gaps.append(dict(topic='WB funnel',status=f.get('status','pagination_pending'),retry_at=f.get('retry_at')))
   for p in f.get('rows',[]):
    if p['nm_id'] in ids:
     wb_funnel[(p['nm_id'],dates[1])]=p['selected'];wb_funnel[(p['nm_id'],dates[0])]=p['past']
   sources.append(dict(source=f.get('source'),source_key=f.get('source_key'),observed_at=f.get('observed_at'),update_delay_hours=2))
  except Exception as ex:gaps.append(dict(topic='WB funnel',error=type(ex).__name__))
  try:
   finance=reports.finance(dates[0],dates[1]);costs={int(nm):stock.get(article.casefold(),{}).get('cost_rub') for nm,article in w.catalog()}
   wb_finance=settlement(finance,dates[0],dates[1],ids,costs)
   if not finance.get('complete'):gaps.append(dict(topic='WB Finance',status=finance.get('status','pagination_pending'),retry_at=finance.get('retry_at')))
  except Exception as ex:gaps.append(dict(topic='WB Finance',error=type(ex).__name__))
 advertising=live('advertising',[],dates[0],dates[2]);ads=ad_rows(advertising.get('rows',[]),ids);campaigns=advertising.get('campaigns',[])
 history=decision_context(w,ids);io_=IO();mins={};config={}
 with reading():
  try:config=http(io_,'/api/advert/v1/config')
  except Exception as ex:gaps.append(dict(topic='WB bid step',error=type(ex).__name__))
  for c in campaigns:
   members={n['nm_id'] for n in c.get('nm_settings',[])}&set(ids)
   if not members or c.get('settings',{}).get('payment_type')!='cpc':continue
   try:mins.update({(c['id'],nm):v for nm,v in minimums(io_,c['id'],members).items()})
   except Exception as ex:gaps.append(dict(topic='WB minimum bid',campaign_id=c['id'],error=type(ex).__name__))
 result=[];labels=dict(w.catalog())
 for base in focus:
  nm=base['nm_id'];article=labels.get(str(nm),base['article']);funnel=[]
  for day in dates:
   p=daily[day].get(nm);views=p.get('open_card_count') if p else None;count=p.get('funnel_orders_count') if p else None;history_prices=p.get('sparkline_prices') if p else None
   mpstats=dict(clicks=views,orders=count);primary=wb_funnel.get((nm,day))
   if primary is not None:views=primary['clicks'];count=primary['orders']
   traffic=general_traffic(w,nm,day,day,ads.get((nm,day),{}))
   funnel.append(dict(date=day,total_traffic=traffic,primary_source='WB' if primary else 'MPStats fallback',wb_funnel=primary,mpstats_counters=mpstats,source_discrepancy=bool(primary and (views!=mpstats['clicks'] or count!=mpstats['orders'])),clicks_scope='all_sources',clicks=views,funnel_orders=count,click_order_pct=100*count/views if views and count is not None else None,customer_daily_price=history_prices[0] if isinstance(history_prices,list) and len(history_prices)==1 else None,customer_price_snapshot=p.get('price_after_spp') if p else None,spp_snapshot=p.get('price_spp') if p else None,advertising=ads.get((nm,day))))
  participation=[]
  for c in campaigns:
   n=next((n for n in c.get('nm_settings',[]) if n['nm_id']==nm),None)
   if n:participation.append(dict(campaign_id=c['id'],status=c['status'],bid_type=c.get('bid_type'),currency=c.get('currency'),payment_type=c.get('settings',{}).get('payment_type'),placements=c.get('settings',{}).get('placements'),current_bid_minor=n.get('bids_kopecks',{}).get('recommendations'),minimum_minor=mins.get((c['id'],nm)),step_minor=config.get('cpcStep'),members=len(c.get('nm_settings',[]))))
  events=[dict(event_id=e['event_id'],source_key=e['source_key'],started_at=e.get('started_at'),action=e.get('action'),comparison=e.get('comparison'),business_outcome=e.get('business_outcome'),advertising_outcome=e.get('advertising_outcome')) for e in history['experiences'] if nm in e.get('action',{}).get('nm_ids',[])]
  result.append(dict(base,article=article,funnel_daily=funnel,stock=stock.get(article.casefold()),seller_price=prices.get(nm),active_campaigns=participation,verified_history=events))
 if wb_finance:sources.append(dict(source='WB Finance',basis=wb_finance['basis'],publication_latest=wb_finance['publication_latest'],operation_latest=wb_finance['operation_latest']))
 return dict(status='complete' if not gaps else 'partial',wb_finance=wb_finance,orders={k:v for k,v in orders.items() if k in ['daily','cutoff_msk','yesterday_same_clock','total_orders']},rows=result,gaps=gaps,sources=sources,wb_writes=0,notes=['Заказы WB и заказы воронки/рекламная атрибуция — отдельно','Для общих заказов нужны общие показы и клики всех источников; рекламные показы/CTR/CPC анализировать отдельно. Общую органику не вычитать/не складывать без доказанных единиц и непересечения. Недоступные общие показы не означают отсутствие охвата','Сегодня сравнивать с вчера до того же часа только там, где получен совпадающий час. Воронка/реклама сегодня — неполный день, не сравнивать с полными сутками','История цены покупателя — только проверенная дневная sparkline. Цена/СПП snapshot не доказывают ретроспективную СПП','Текущие остатки не доказывают наличие вчера. Изменения/совпадения не доказывают причинность','Уже отключённое не отключать повторно. При ДРР>5% — конкретная проверенная рекомендация; без проверенных min/step не выдумывать новую ставку'])



