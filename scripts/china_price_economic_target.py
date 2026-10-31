"""Read-only price hypothesis: retain pre-increase daily profit, no extrapolation.

Demand is interpolated between observed seller prices at the latest traffic
level. This is a testable hypothesis, never a causal estimate or execution grant.
All monetary inputs use the same currency and daily periods.
"""
import math
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from datetime import datetime,timedelta,timezone

def verified_price_history(worker):
    """Canonical standard receipts only; applied requires an exact CNY readback."""
    rows=worker.db('GET','telegram_api_cache',params=dict(cache_key='like.china_agent:price_execution:v1:*',select='cache_key,payload',limit=1000)) or []
    if len(rows)>=1000:raise RuntimeError('Price history pagination required')
    events={}
    for row in rows:
        receipt=row.get('payload') or {}
        for item in receipt.get('items',[]):
            selection=item.get('selection') or {};readback=item.get('readback') or {}
            at=item.get('verified_at') or receipt.get('completed_at')
            if item.get('status') not in ('applied','verified') or not at or readback.get('currencyIsoCode4217')!='CNY':continue
            nm=str(selection.get('nm_id'));target=selection.get('target_cny')
            sizes=readback.get('sizes') or []
            if str(readback.get('nmID'))!=nm or target is None or not sizes:continue
            if any(Decimal(str(s.get('discountedPrice')))!=Decimal(str(target)) for s in sizes):continue
            try:day=datetime.fromisoformat(at.replace('Z','+00:00')).astimezone(timezone(timedelta(hours=3))).date()
            except (ValueError,TypeError):continue
            events.setdefault(nm,[]).append(dict(day=day,price_cny=Decimal(str(target)),source_key=row['cache_key']))
    return events

def baseline_after_last_change(pair, nm, previous_price, detected, events):
    if not pair:return None
    if previous_price is None:return None
    prior=[e for e in events.get(str(nm),[]) if e['day']<detected]
    if not prior:return pair
    latest=max(prior,key=lambda e:e['day'])
    if latest['price_cny']!=Decimal(str(previous_price)):return None
    changed=latest['day']
    first=max(pair[0][0],changed+timedelta(days=1))
    return ((first,pair[0][1]),pair[1]) if first<=pair[0][1] else None

def canonical_change_days(tracked,events):
    output=[]
    for nm,entry,change,detected in tracked:
        after=(change.get('after_price') or {}).get('current_cny')
        matches=[e for e in events.get(str(nm),[]) if after is not None and e['day']<=detected and e['price_cny']==Decimal(str(after))]
        actual=max((e['day'] for e in matches),default=detected)
        output.append((nm,entry,change,actual))
    return output

def feasible_prices(previous, current):
    low=Decimal(str(previous['current_cny']));high=Decimal(str(current['current_cny']))
    if not 0<low<high:return []
    result={}
    def add(base,discount):
        base=Decimal(str(base));discount=Decimal(str(discount))
        value=(base*(1-discount/100)).quantize(Decimal('.01'))
        if base>0 and 0<=discount<100 and low<=value<high:
            result[value]=dict(price_cny=float(value),base_cny=float(base),discount=float(discount))
    for source in (previous,current):
        discount=Decimal(str(source['discount']));factor=1-discount/100
        if factor<=0:continue
        first=int((low/factor).to_integral_value(rounding=ROUND_CEILING))
        last=int((high/factor).to_integral_value(rounding=ROUND_FLOOR))
        if last-first>100000:raise ValueError('Unbounded price candidate range')
        for base in range(first,last+1):add(base,discount)
        add(source['base_cny'],discount)
    return [result[p] for p in sorted(result)]

def choose_target(previous,current,before,after,*,buyout_probability,retention,cost,dispatch,fx):
    """Choose closest feasible profit to the old daily floor, at or above it.

    Priority is a lower price at the same profit floor, rather than maximizing
    contribution per item. No price below the pre-increase seller price is used.
    """
    result=dict(status='not_calculated',execution_authorized=False,
                basis='profit_floor_demand_hypothesis',profit_floor_basis='before_increase_daily',
                price_floor_cny=previous.get('current_cny'),hypothesis=True)
    try:
        old=float(previous['current_cny']);now=float(current['current_cny'])
        q=float(buyout_probability);keep=float(retention);c=float(cost);d=float(dispatch);fx=float(fx)
        floor=float(before['expected_profit_per_day']);ads=float(after['advertising_per_day'])
        nb=float(before['orders_per_day']);na=float(after['orders_per_day'])
        vb=float(before['views'])/before['days'];va=float(after['views'])/after['days']
        values=(old,now,q,keep,c,d,fx,floor,ads,nb,na,vb,va)
        if not all(math.isfinite(v) for v in values) or not (0<old<now and 0<q<=1 and 0<keep<=1 and fx>0 and c>=0 and d>=0 and ads>=0 and nb>0 and na>0 and vb>0 and va>0):raise ValueError()
    except (KeyError,TypeError,ValueError,ZeroDivisionError):
        return dict(result,status='incomplete_economic_inputs')
    # Relative order intensity is normalized by traffic, not an average of CRs.
    elasticity=math.log((nb/vb)/(na/va))/math.log(old/now)
    result.update(profit_floor_per_day=floor,demand_elasticity_hypothesis=elasticity,
                  fixed_advertising_per_day=ads,traffic_per_day=va,
                  assumptions=['same traffic and advertising per day as after the increase',
                               'same own buyout rate, costs, retention and delivery',
                               'observed demand response is a hypothesis, confounders not excluded'])
    if elasticity>=0:return dict(result,status='no_supported_demand_recovery')
    options=[]
    for target in feasible_prices(previous,current):
        p=target['price_cny']
        contribution=q*(p*fx*keep-c)-d
        if contribution<=0:continue
        orders=na*(p/now)**elasticity
        profit=orders*contribution-ads
        options.append(dict(target,predicted_orders_per_day=orders,
                            required_orders_per_day=(floor+ads)/contribution,
                            predicted_profit_per_day=profit,
                            expected_profit_advantage_per_day=profit-floor))
    acceptable=[v for v in options if v['predicted_profit_per_day']>=floor]
    if not acceptable:
        return dict(result,status='profit_floor_not_reached',best_scenario=max(options,key=lambda v:v['predicted_profit_per_day']) if options else None)
    # Nearest nonnegative gap to the requested profit floor. At equal profit,
    # favor the lower price. Always disclose the required order hypothesis.
    choice=min(acceptable,key=lambda v:(v['expected_profit_advantage_per_day'],v['price_cny']))
    return dict(result,**choice,status='recommended',profit_currency='RUB',price_currency='CNY')

