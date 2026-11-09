"""Price control from supported exact-period product aggregates, no card_orders.

Expected order-date economics are a disclosed model, not settled cohort profit.
Missing inputs stay unknown and cannot generate a decrease.
"""
from datetime import datetime,timedelta
from decimal import Decimal

def build(worker):
    from china_agent.morning_pair import tracked_rows
    from china_agent.daily_expected_control import comparison_windows
    from china_agent.price_economic_target import verified_price_history,canonical_change_days,baseline_after_last_change,choose_target
    from china_agent.control_owner_preview import Preview
    from china_agent.expected_order_profit import buyout_from_product
    from china_agent.price_experiment_result import experiment_result
    from analytics.mpstats_primary import products
    from china_agent.daily_report_worker import MSK
    state=worker.get('china_agent:demand_watch:v1') or {}
    tracked=canonical_change_days(tracked_rows(state,worker.day),verified_price_history(worker))
    events=verified_price_history(worker)
    pairs={str(nm):baseline_after_last_change(comparison_windows(d,worker.day),nm,(c.get('before_price') or {}).get('current_cny'),d,events) for nm,e,c,d in tracked}
    end=worker.day-timedelta(days=1);rate_start=end-timedelta(days=29)
    windows={(str(rate_start),str(end))}
    for pair in pairs.values():
        if pair:windows.update((str(a),str(b)) for a,b in pair)
    # Aggregates replace per-SKU card tables/orders and dozens of daily requests.
    Preview.acquire(worker,windows)
    read=lambda t,p:worker.db('GET',t,params=p)
    datasets={};sources=[]
    for a,b in sorted(windows):
        rows,marker=products(read,'token_3',a,b,datetime.now(MSK))
        if not marker:raise RuntimeError('Price control exact-period source missing: '+a+':'+b)
        datasets[a,b]={str(r['nm_id']):r for r in rows};sources.append(marker['id'])
    rates=datasets[str(rate_start),str(end)]
    costs={r['article'].casefold():r for r in read('analytics_costs',dict(select='article,cost,observed_at,source',limit=5000)) or [] if r.get('article')}
    inputs=worker.get('china_agent:advertising_full_growth:'+str(worker.day)+':v1:inputs') or {}
    current_models=(inputs.get('economics') or {}).get('rows',{})
    output=[]
    def num(v):return type(v) in (int,float) and v>=0
    for nm,e,c,d in tracked:
        nm=str(nm);article=e['article'];pair=pairs[nm]
        item=dict(nm_id=nm,article=article,before_price=(c.get('before_price') or {}).get('current_cny'),after_price=(c.get('after_price') or {}).get('current_cny'),detected_at=str(d),full_days=max(0,(worker.day-d).days-1))
        if not pair:
            item.update(status='zero_full_days',result_action='Нет сопоставимого полного периода после последнего изменения.');output.append(item);continue
        own=rates.get(nm)
        try:q=buyout_from_product(own)
        except ValueError:
            item.update(status='insufficient_economics',result=dict(status='incomplete'),missing='Own completed buyout source missing');output.append(item);continue
        model=current_models.get(nm,{})
        cost=model.get('own_cogs_rub');delivery=model.get('logistics_cny')
        item.update(buyout_sample=q['sample_size'],buyout_fallback=q['source']=='fallback',buyout_percent=q['percent'])
        try:
            if model.get('fx_date')!=str(worker.day) or model.get('buyout_fallback') or model.get('commission_policy_fallback'):raise ValueError('current own economics unavailable')
            commission=model.get('commission_pct');tax=model.get('tax_pct');handling=model.get('handling_rub')
            if not all(num(v) for v in (commission,tax,handling,cost,delivery)):raise ValueError('own economics missing')
            retention=1-(commission+tax)/100;fx=float(model['fx_rub_per_cny']);dispatch=float(delivery)*fx+float(handling)
            if not 0<retention<=1 or fx<=0 or q['source']=='fallback':raise ValueError('own economics unverified')
            for label,(a,b),field in zip(('before','after'),pair,('before_price','after_price')):
                raw=datasets[str(a),str(b)].get(nm) or {}
                orders=raw.get('orders_count');views=raw.get('open_card_count');fo=raw.get('funnel_orders_count');ads=raw.get('advertisement')
                if not all(num(v) for v in (orders,views,fo,ads)) or views<=0 or fo>views or item[field] is None:raise ValueError('period row missing')
                n=(b-a).days+1
                daily_views=raw.get('sparkline_open_card')
                if not isinstance(daily_views,list) or len(daily_views)!=n or not all(num(v) for v in daily_views) or sum(daily_views)!=views:raise ValueError('product period views unverified')
                contribution=float(q['probability'])*(float(item[field])*fx*retention-float(cost))-dispatch
                profit=orders*contribution-ads
                item[label]=dict(days=n,orders=orders,views=views,funnel_orders=fo,conversion=fo/views,orders_per_day=orders/n,advertising_per_day=ads/n,expected_profit=profit,expected_profit_per_day=profit/n,period_from=str(a),period_to=str(b))
            before,after=item['before'],item['after']
            result=experiment_result(before['expected_profit_per_day'],after['expected_profit_per_day'],before['views'],before['funnel_orders'],after['views'],after['funnel_orders'],min(4,item['full_days']),q['sample_size'])
            # Owner: preserve price when orders hold, even if conversion falls.
            if after['orders_per_day']>=before['orders_per_day']:
                result.update(status='hold_orders_maintained',result_action='Заказы держатся; цену сохраняем.')
            item['result']=result
            if result.get('status')=='rollback_review' and q['sample_size']>=10 and item['before_price']<item['after_price']:
                item['economic_target']=choose_target(c['before_price'],c['after_price'],before,after,buyout_probability=q['probability'],retention=retention,cost=cost,dispatch=dispatch,fx=fx)
            item.update(status='expected_model',unknown_reverse_and_shared_costs=True,
                        economics_note='Own completed buyout, dated CBR, COGS/tax/commission and historical logistics. Unknown reverse/shared expenses are not zero; not settled profit.',model_source='china_agent:advertising_full_growth:'+str(worker.day)+':v1:inputs')
        except (KeyError,TypeError,ValueError,ZeroDivisionError) as exc:
            item.update(status='insufficient_economics',result=dict(status='incomplete'),missing=str(exc))
        output.append(item)
    value=dict(model_version='wb_profit_floor_price_hypothesis_v4',report_date=str(worker.day),status='complete_disclosed_forecast_model',products=output,source_snapshot_ids=sources,rate_period=[str(rate_start),str(end)],calculated_at=datetime.now(MSK).isoformat(),cohort_outcomes='unavailable_not_required_for_disclosed_expectation',wb_writes=0,telegram_calls=0)
    worker.save('china_agent:daily_expected_candidates:'+str(worker.day)+(':verify' if getattr(worker,'control_preview',False) else ''),value)
    return value

