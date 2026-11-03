"""Completed-day cost-containment proposals from dated own inputs; never executes writes."""
import copy,math
from datetime import datetime,timezone,timedelta

def finite(v):return type(v) in (int,float) and math.isfinite(v)

def model_rows(inputs,policy,delivery):
 from china_expected_order_profit import buyout_from_product
 own={int(r['nm_id']):r for r in inputs['products']['rows']}
 prices={int(r['nm_id']):r for r in inputs['prices']['rows']}
 stocks={r['article'].casefold():r for r in inputs['stock']['rows']}
 fx=float(inputs['fx']['rub_per_cny']);out={};missing={}
 if not finite(fx) or fx<=0:raise ValueError('Verified FX missing')
 for nm,pr in prices.items():
  try:
   p=own.get(nm);b=buyout_from_product(p)
   q=float(b['probability']);st=stocks[pr['article'].casefold()]
   cost=st.get('cost_rub') if 'cost_rub' in st else st.get('price',0)/100
   free=st.get('available') if 'available' in st else st['stock']-st['reserve']
   price=pr['seller_price']
   if finite(free) and free<=0:
    out[str(nm)]=dict(stock_free=free,stock_observed_at=inputs['stock']['observed_at'],price_observed_at=inputs['prices']['observed_at'],seller_price_cny=price,observed_at=inputs['products']['observed_at'],model_unavailable='No available MSK stock; missing valuation is not zero COGS')
    continue
   if not all(finite(v) for v in [cost,free,price]) or cost<=0 or price<=0:raise ValueError('Current cost, stock or price invalid')
   fee=p.get('total_commission_without_spp_in_sales');fee_fallback=not finite(fee) or not 0<fee<100
   if fee_fallback:fee=policy['commission_pct']
   log=policy.get('logistics_by_nm',{}).get(str(nm)) or delivery.get('rows',{}).get(pr['article'])
   if not log or not finite(log.get('delivery_cny')):raise ValueError('Logistics model missing')
   before=q*(price*(1-(fee+policy['tax_pct'])/100)-cost/fx)-log['delivery_cny']-policy['handling_rub']/fx
   out[str(nm)]=dict(observed_at=inputs['products']['observed_at'],own_cogs_rub=cost,seller_revenue_rub=price*fx,seller_price_cny=price,
    stock_free=free,stock_observed_at=inputs['stock']['observed_at'],price_observed_at=inputs['prices']['observed_at'],
    expected_margin_before_ads_cny=before,owner_strategy_review=True,buyout=q,sample_size=b['sample_size'],sample_reliable=b['sample_size']>=20,
    commission_pct=fee,commission_policy_fallback=fee_fallback,buyout_fallback=b['source']=='fallback',logistics_cny=log['delivery_cny'],logistics_historical=True,
    period_from=inputs['products']['period_from'],period_to=inputs['products']['period_to'],source_ids=['own_buyout','seller_price_CNY','MSK_stock_reserve_COGS','CBR','historical_logistics'],
    unknown_reverse_and_shared_costs=True,preliminary=True)
  except (KeyError,ValueError,TypeError,ZeroDivisionError) as ex:missing[str(nm)]=str(ex)
 return dict(status='available',rows=out,missing=missing,observed_at=inputs['products']['observed_at'])

def apply(bundle,source,minima):
 """A high completed-day DRR at minimum CPC is reviewed now, not postponed indefinitely."""
 out=copy.deepcopy(bundle);states={c['id']:c for b in source['batches'].values() for c in b['campaigns']['adverts']}
 economics=source.get('economics',{}).get('rows',{});clock=datetime.now(timezone.utc)
 def dated(at,hours):
  try:return 0<=(clock-datetime.fromisoformat(at.replace('Z','+00:00'))).total_seconds()<=hours*3600
  except (ValueError,TypeError,AttributeError):return False
 for c in out['campaigns']:
  state=states[c['id']]
  if c['status']!=9 or c['payment']!='cpc':continue
  settings={r['nm_id']:r for r in state['nm_settings']}
  zone='search' if state['settings']['placements'].get('search') else 'recommendations'
  for r in c.get('focus',[]):
   if r['nm'] not in settings:
    r['action']=None;r['already_excluded']=True;continue
   if r.get('pending_first_day'):continue
   p=(r.get('comparison') or {}).get('after') or r['period'];spend=p['spend'];orders=p['orders'];amount=p['amount']
   risk=spend>0 and (orders==0 or amount<=0 or spend/amount>.05)
   existing=r.get('action')or{}
   cost_action=existing.get('kind')=='ad_exclude_sku' or (existing.get('kind')=='ad_set_bid' and existing.get('target_minor',0)<existing.get('old_minor',0))
   if not risk and not cost_action:continue
   e=economics.get(str(r['nm']),{});old=settings[r['nm']]['bids_kopecks'][zone];minimum=minima.get(str(c['id'])+':'+str(r['nm']))
   r['current_bid_minor']=old;r['minimum_bid_minor']=minimum
   if finite(e.get('stock_free')) and e['stock_free']<=0 and dated(e.get('stock_observed_at'),24):
    r['candidate_for_manual_review']=False;r['economics']=copy.deepcopy(e)
    r['action']=dict(id=str(c['id'])+':'+str(r['nm']),kind='ad_exclude_sku',campaign_id=c['id'],nm_id=r['nm'],placement=zone,old_minor=old,article=r['article']) if len(state['nm_settings'])>1 and state.get('restrictions',{}).get('can_change_nms') is True else None
    r['decision']='Исключить из этой РК до возврата доступного остатка МСК.' if r['action'] else 'Не повышать ставку и не пополнять: доступный остаток МСК отсутствует.'
    r['reason']='Остаток МСК минус резерв '+str(e['stock_free'])+'. Stockout не доказывает слабый спрос.'
    continue
   complete=e and dated(e.get('observed_at'),48) and dated(e.get('stock_observed_at'),24) and dated(e.get('price_observed_at',e.get('observed_at')),24)
   if not complete or not all(finite(e.get(k)) for k in ['expected_margin_before_ads_cny','stock_free','own_cogs_rub','seller_price_cny']) or type(minimum)is not int:
    r['action']=None;r['data_blocker']='Exact dated economics/price/stock/minimum unavailable'
    r['decision']=f'Не повышать {old/100:g} ¥ и не пополнять до восстановления точных данных.'
    continue
   r['economics']=copy.deepcopy(e);r['candidate_for_manual_review']=False
   model_before=e['expected_margin_before_ads_cny'];r['model_profit_for_attributed_orders_cny']=orders*model_before-spend
   drr=100*spend/amount if amount>0 else None
   facts=f'{spend:.2f} ¥; {int(p["clicks"])} кликов; {int(orders)} прямых заказов; '+(f'ДРР {drr:.2f}%.' if drr is not None else 'ДРР не определена.')
   r['reason']=facts+' Экономика предварительная; ассоциированные заказы и неизвестные общие расходы не распределены.'
   if e.get('buyout_fallback'):r['reason']+=' Нет завершённой собственной выборки: выкуп50% — допущение, не факт.'
   base=dict(id=str(c['id'])+':'+str(r['nm']),campaign_id=c['id'],nm_id=r['nm'],placement=zone,old_minor=old,article=r['article'])
   own_model=e.get('sample_size',0)>=5 and not e.get('buyout_fallback') and not e.get('commission_policy_fallback')
   meaningful=(p['clicks']>=100 or own_model and model_before<=0 and p['clicks']>=30) and spend>=max(0,model_before,e['seller_price_cny']*.05)
   bounded_loss=orders==0 and p['clicks']>=30 and own_model and model_before>0 and spend>=max(model_before,e['seller_price_cny']*.05)
   positive_own_model=(orders>0 and r['model_profit_for_attributed_orders_cny']>0 and not e.get('buyout_fallback') and not e.get('commission_policy_fallback') and e.get('sample_size',0)>=5)
   if positive_own_model:
    # A target DRR is not a break-even threshold; preserve uncertainty and a finite review.
    r['action']=None
    r['decision']=f'Сохранить {old/100:g} ¥ до оценки следующего полного дня: предварительная экономика положительна.'
    r['reason']+=' Расчёт не доказывает закрытую прибыль; превышение цели ДРР само по себе не основание для снижения или исключения.'
   elif old>minimum and (meaningful or bounded_loss):
    r['action']=dict(base,kind='ad_set_bid',target_minor=minimum)
    r['decision']=f'Снизить {old/100:g} → {minimum/100:g} ¥ (минимум WB).'
   elif old==minimum and orders>0 and drr is not None and 5<drr<=6 and r['model_profit_for_attributed_orders_cny']>0:
    r['action']=None
    limit=round(min(model_before,e['seller_price_cny']*.05),2)
    r['test_proposal']=dict(days=1,max_additional_spend_cny=limit,requires_separate_approval=True,execution_authorized=False)
    r['decision']=f'Оставить минимум {old/100:g} ¥ только как отдельно согласованный тест на 1 полный день; лимит допрасхода {limit:g} ¥; без пополнения.'
    r['reason']+=' Цель5% превышена незначительно; это предложение исключения из лимита на один день, не разрешение продолжать автоматически.'
   elif old==minimum and meaningful and len(state['nm_settings'])>1 and state.get('restrictions',{}).get('can_change_nms') is True:
    r['action']=dict(base,kind='ad_exclude_sku');r['decision']='Исключить из этой РК: ставка уже на минимуме WB.'
   else:
    r['action']=None
    r['decision']=f'Сохранить {old/100:g} ¥: малая выборка; повторная оценка после следующего полного дня.'
    r['reason']+=' База для снижения/исключения пока мала; это не разрешение бессрочного теста или пополнения.'
  c['attention']=[r for r in c.get('focus',[]) if r.get('action')]
 out['economic_review_complete']=not any(r.get('data_blocker') for c in out['campaigns'] for r in c.get('focus',[]))
 out['economic_review_blockers']=[dict(campaign_id=c['id'],article=r['article'],blocker=r['data_blocker']) for c in out['campaigns'] for r in c.get('focus',[]) if r.get('data_blocker')]
 return out

