"""Price control from supported exact-period product aggregates, no card_orders.

Expected order-date economics are a disclosed model, not settled cohort profit.
Missing inputs stay unknown and cannot generate a decrease.
"""
from datetime import datetime,timedelta
from decimal import Decimal


def ensure_fresh_cards(worker):
    """Scheduled price controls need a current linked-card composition before qualification."""
    import os
    from business_agents.data import Data
    read=lambda table,params:worker.db('GET',table,params=params)
    current=Data('china',read).snapshot('cards','token_3')
    if current.get('available') and current.get('fresh'):return current
    import analytics.collect as collector
    original=collector.fetch
    def immediate(*args,**kwargs):
        kwargs['max_retry_wait']=0
        return original(*args,**kwargs)
    collector.fetch=immediate
    try:
        collector.cards('token_3',os.environ['WB_TOKEN_3'].strip())
    finally:
        collector.fetch=original
    current=Data('china',read).snapshot('cards','token_3')
    if not current.get('available') or not current.get('fresh'):
        raise RuntimeError('Fresh linked-card composition unavailable after bounded collection')
    worker.audit['linked_cards_observed_at']=current['observed_at']
    return current

def build(worker):
    ensure_fresh_cards(worker)
    from china_agent.morning_pair import tracked_rows
    from china_agent.daily_expected_control import comparison_windows
    from china_agent.price_economic_target import verified_price_history,canonical_change_days,baseline_after_last_change,choose_target
    from china_agent.control_owner_preview import Preview
    from china_agent.expected_order_profit import buyout_from_product
    from china_agent.price_experiment_result import experiment_result
    from analytics.mpstats_primary import products
    from china_price_period import period
    from china_agent.daily_report_worker import MSK
    state=worker.get('china_agent:demand_watch:v1') or {}
    events=verified_price_history(worker)
    tracked=canonical_change_days(tracked_rows(state,worker.day),events)
    pairs={str(nm):baseline_after_last_change(comparison_windows(d,worker.day),nm,(c.get('before_price') or {}).get('current_cny'),d,events) for nm,e,c,d in tracked}
    end=worker.day-timedelta(days=1);rate_start=end-timedelta(days=29)
    windows={(str(rate_start),str(end))}
    for pair in pairs.values():
        if pair:windows.update((str(a),str(b)) for a,b in pair)
    # Aggregates replace per-SKU card tables/orders and dozens of daily requests.
    Preview.acquire(worker,windows)
    read_cache={}
    def read(t,p):
        import json
        key=(t,json.dumps(p,sort_keys=True))
        if key not in read_cache:read_cache[key]=worker.db('GET',t,params=p)
        return read_cache[key]
    datasets={};sources=[]
    for a,b in sorted(windows):
        rows,marker=period(worker,a,b)
        grouped={}
        for row in rows:grouped.setdefault(str(row['nm_id']),[]).append(row)
        datasets[a,b]={nm:values[0] for nm,values in grouped.items() if len(values)==1}
        if marker:sources.append(marker['id'])
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
                contribution=float(q['probability'])*(float(item[field])*fx*retention-float(cost))-dispatch
                profit=orders*contribution-ads
                item[label]=dict(days=n,orders=orders,views=views,funnel_orders=fo,conversion=fo/views,orders_per_day=orders/n,advertising_per_day=ads/n,expected_profit=profit,expected_profit_per_day=profit/n,period_from=str(a),period_to=str(b))
            before,after=item['before'],item['after']
            delta=after['expected_profit_per_day']-before['expected_profit_per_day']
            early_possible=(item['full_days']>=1 and before['expected_profit_per_day']>0
                and delta/before['expected_profit_per_day']<=-.2
                and before['views']>=100 and after['views']>=100
                and before['funnel_orders']+after['funnel_orders']>=30 and q['sample_size']>=10
                and after['conversion']<before['conversion'])
            if delta<0 and item['full_days']>=4:
                result=dict(status='rollback_review',profit_delta_rub=delta,early_review_criteria_met=False,conversion_fisher_p=None)
            elif delta<0 and early_possible and nm not in ('1473245494','1473245510'):
                result=experiment_result(before['expected_profit_per_day'],after['expected_profit_per_day'],before['views'],before['funnel_orders'],after['views'],after['funnel_orders'],min(4,item['full_days']),q['sample_size'])
            else:
                result=dict(status='observe',profit_delta_rub=delta,early_review_criteria_met=False,conversion_fisher_p=None)
            # Owner: preserve price when orders hold, even if conversion falls.
            if after['orders_per_day']>=before['orders_per_day']:
                result.update(status='hold_orders_maintained',result_action='Заказы держатся; цену сохраняем.')
            item['result']=result
            if result.get('status')=='rollback_review' and q['sample_size']>=10 and item['before_price']<item['after_price']:
                from business_agents.data import Data
                from china_agent.linked import compare,qualify
                context=compare(Data('china',read),nm,pair[0][0],pair[0][1],pair[1][0],pair[1][1],datetime.now(MSK),(e.get('increase') or {}).get('baseline_group'))
                qualified=qualify(dict(action='lower'),context,baseline_known=bool((e.get('increase') or {}).get('baseline_group',{}).get('available')))
                item['linked_context']=qualified['linked_context']
                if qualified['action']=='lower':
                    item['economic_target']=choose_target(c['before_price'],c['after_price'],before,after,buyout_probability=q['probability'],retention=retention,cost=cost,dispatch=dispatch,fx=fx)
            item.update(status='expected_model',unknown_reverse_and_shared_costs=True,
                        own_cogs_rub=cost,economics_note='Own completed buyout, dated CBR, COGS/tax/commission and historical logistics. Unknown reverse/shared expenses are not zero; not settled profit.',model_source='china_agent:advertising_full_growth:'+str(worker.day)+':v1:inputs')
        except (KeyError,TypeError,ValueError,ZeroDivisionError) as exc:
            item.update(status='insufficient_economics',result=dict(status='incomplete'),missing=str(exc))
        output.append(item)
    value=dict(model_version='wb_profit_floor_price_hypothesis_v4',report_date=str(worker.day),status='complete_disclosed_forecast_model',products=output,source_snapshot_ids=sources,rate_period=[str(rate_start),str(end)],calculated_at=datetime.now(MSK).isoformat(),cohort_outcomes='unavailable_not_required_for_disclosed_expectation',wb_writes=0,telegram_calls=0)
    worker.save('china_agent:daily_expected_candidates:'+str(worker.day)+(':verify' if getattr(worker,'control_preview',False) else ''),value)
    return value

